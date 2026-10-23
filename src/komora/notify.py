from __future__ import annotations

import argparse
import socket
from dataclasses import dataclass

import httpx2

from komora import runtime
from komora.config import Settings
from komora.config import settings as _default_settings
from komora.logging import get_logger

log = get_logger(__name__)

API = "https://api.telegram.org"

LIMIT = 4096

TIMEOUT_S = 15.0


@dataclass(frozen=True, slots=True)
class Sent:

    ok: bool
    why: str = ""


def hide(message: str, token: str | None) -> str:
    return message.replace(token, "***") if token else message


async def send(text: str, *, config: Settings | None = None) -> Sent:
    cfg = config if config is not None else _default_settings
    token, chat = cfg.telegram_token, cfg.telegram_chat
    if not token or not chat:
        return Sent(False, "у .env немає KOMORA_TELEGRAM_TOKEN або KOMORA_TELEGRAM_CHAT")

    try:
        async with httpx2.AsyncClient(timeout=TIMEOUT_S) as http:
            answer = await http.post(
                f"{API}/bot{token}/sendMessage",
                json={
                    "chat_id": chat,
                    "text": text[:LIMIT],
                    "disable_web_page_preview": True,
                },
            )
            answer.raise_for_status()
    except Exception as exc:
        why = hide(str(exc), token)[:200]
        log.error("notify.failed", error=why)
        return Sent(False, why)

    log.info("notify.sent", chars=len(text))
    return Sent(True)


def about_failure(unit: str, *, host: str | None = None) -> str:
    where = host or socket.gethostname()
    return f"КОМОРА · упав юніт\n{unit} на {where}\n\njournalctl --user -u {unit} -n 50 --no-pager"


def main() -> int:
    runtime.console()
    parser = argparse.ArgumentParser(description="Сповіщення «Комори» в Telegram")
    parser.add_argument("--unit", help="юніт, який упав (підставляє systemd через %%i)")
    parser.add_argument("--text", help="довільний текст")
    args = parser.parse_args()

    if not args.unit and not args.text:
        parser.error("нема чого слати: назви --unit або --text")

    text = args.text or about_failure(args.unit)
    result = runtime.run(send(text))
    if not result.ok:
        print(f"не надіслано: {result.why}")
        return 1
    print("надіслано")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
