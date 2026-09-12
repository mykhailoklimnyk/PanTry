from __future__ import annotations

import asyncio
import json
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import ClassVar
from urllib.parse import parse_qs, urlparse

from mcp import ClientSession
from mcp.client.auth import AuthorizationCodeResult, OAuthClientProvider, TokenStorage
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client
from mcp.shared.auth import OAuthClientInformationFull, OAuthClientMetadata, OAuthToken

from komora import runtime
from komora.config import settings

runtime.console()

ROOT = Path(__file__).resolve().parents[1]
TOKEN_FILE = ROOT / ".mcp-token.json"

CALLBACK_PORT = 8765
REDIRECT_URI = f"http://localhost:{CALLBACK_PORT}/callback"

_PAGE_OK = """<!doctype html><meta charset="utf-8">
<title>Комора</title>
<body style="font:16px system-ui;padding:3rem;background:#17140f;color:#f0ece4">
<h1 style="font-weight:600">Готово</h1>
<p>Токен збережено. Можна закрити вкладку і повернутись у термінал.</p>
</body>"""

_PAGE_FAIL = """<!doctype html><meta charset="utf-8">
<title>Комора</title>
<body style="font:16px system-ui;padding:3rem;background:#17140f;color:#f0ece4">
<h1 style="font-weight:600">Не вийшло</h1>
<p>У відповіді немає коду авторизації. Спробуй ще раз.</p>
</body>"""


class FileTokenStorage(TokenStorage):

    def __init__(self, path: Path) -> None:
        self.path = path

    def _read(self) -> dict:
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _write(self, data: dict) -> None:
        text = json.dumps(data, ensure_ascii=False, indent=2)
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)

    async def get_tokens(self) -> OAuthToken | None:
        raw = self._read().get("tokens")
        return OAuthToken.model_validate(raw) if raw else None

    async def set_tokens(self, tokens: OAuthToken) -> None:
        data = self._read()
        data["tokens"] = tokens.model_dump(mode="json", exclude_none=True)
        self._write(data)

    async def get_client_info(self) -> OAuthClientInformationFull | None:
        raw = self._read().get("client")
        return OAuthClientInformationFull.model_validate(raw) if raw else None

    async def set_client_info(self, client_info: OAuthClientInformationFull) -> None:
        data = self._read()
        data["client"] = client_info.model_dump(mode="json", exclude_none=True)
        self._write(data)


class _CallbackHandler(BaseHTTPRequestHandler):
    result: ClassVar[dict] = {}
    done: ClassVar[threading.Event] = threading.Event()

    def do_GET(self) -> None:
        params = parse_qs(urlparse(self.path).query)
        code = params.get("code", [None])[0]
        _CallbackHandler.result = {
            "code": code,
            "state": params.get("state", [None])[0],
            "iss": params.get("iss", [None])[0],
        }
        body = (_PAGE_OK if code else _PAGE_FAIL).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
        _CallbackHandler.done.set()

    def log_message(self, format: str, *args: object) -> None:
        """Тиша: сирі HTTP-логи тут лише заважають читати підказки."""


async def _open_browser(url: str) -> None:
    print("\nВідкриваю браузер. Якщо не відкрився — перейди вручну:")
    print(f"\n  {url}\n")
    webbrowser.open(url)


async def _wait_for_callback() -> AuthorizationCodeResult:
    _CallbackHandler.result = {}
    _CallbackHandler.done.clear()

    server = HTTPServer(("localhost", CALLBACK_PORT), _CallbackHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"Чекаю на підтвердження (слухаю {REDIRECT_URI})…")

    try:
        await asyncio.get_running_loop().run_in_executor(
            None, _CallbackHandler.done.wait, 300
        )
    finally:
        server.shutdown()
        server.server_close()

    code = _CallbackHandler.result.get("code")
    if not code:
        raise RuntimeError("браузер не повернув код авторизації — спробуй ще раз")

    return AuthorizationCodeResult(
        code=code,
        state=_CallbackHandler.result.get("state"),
        iss=_CallbackHandler.result.get("iss"),
    )


async def login() -> str:
    storage = FileTokenStorage(TOKEN_FILE)

    oauth = OAuthClientProvider(
        server_url=settings.mcp_url,
        client_metadata=OAuthClientMetadata(
            client_name="Комора",
            redirect_uris=[REDIRECT_URI],
            grant_types=["authorization_code", "refresh_token"],
            response_types=["code"],
            token_endpoint_auth_method="none",
        ),
        storage=storage,
        redirect_handler=_open_browser,
        callback_handler=_wait_for_callback,
    )

    async with create_mcp_http_client(auth=oauth) as http_client:
        transport = streamable_http_client(settings.mcp_url, http_client=http_client)
        async with (
            transport as (read_stream, write_stream),
            ClientSession(read_stream, write_stream) as session,
        ):
            await session.initialize()
            tools = await session.list_tools()
            print(f"\nПідключено. Доступно tools: {len(tools.tools)}")

    tokens = await storage.get_tokens()
    if not tokens:
        raise RuntimeError("сесія відкрилась, але токен не збережено")
    return tokens.access_token


def main() -> int:
    print(f"MCP: {settings.mcp_url}")
    print("Логінься номером, на якому НЕМАЄ замовлень — для крона слотів")
    print("історія покупок не потрібна, а родинні чеки краще не чіпати.\n")

    try:
        token = runtime.run(login())
    except Exception as exc:
        print(f"\nHe вийшло: {exc}", file=sys.stderr)
        return 1

    print(f"Токен збережено у {TOKEN_FILE.name} (він у .gitignore).")
    print(f"Довжина токена: {len(token)}. У .env копіювати нічого не треба —")
    print("застосунок читає цей файл сам, якщо KOMORA_MCP_TOKEN не заданий.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
