from __future__ import annotations

import asyncio
import json
import random
import re
from dataclasses import dataclass
from pathlib import Path
from types import TracebackType
from typing import Any, Self

import httpx2
from mcp import ClientSession, types
from mcp.client.streamable_http import create_mcp_http_client, streamable_http_client

from komora.config import Settings
from komora.config import settings as _default_settings
from komora.core.homoglyphs import APOSTROPHES
from komora.core.instructions import rebind
from komora.core.silence import Silence
from komora.logging import get_logger
from komora.mcp import verdicts as verdict_register
from komora.mcp.inventory import canonical
from komora.mcp.redact import redact

log = get_logger(__name__)

RETRYABLE_STATUS = frozenset({408, 425, 429, 500, 502, 503, 504})

SEARCH_TOOL = "silpo_find_products_batch"

READ_TOOLS = frozenset(
    {
        "silpo_find_address",
        "silpo_find_nova_poshta_offices",
        "silpo_find_nova_poshta_settlements",
        "silpo_find_products_batch",
        "silpo_get_available_delivery_types",
        "silpo_get_categories",
        "silpo_get_categories_tree",
        "silpo_get_category",
        "silpo_get_coupon_details",
        "silpo_get_loyalty_info",
        "silpo_get_my_certificates",
        "silpo_get_my_coupons",
        "silpo_get_my_delivery_addresses",
        "silpo_get_my_family",
        "silpo_get_my_favorites",
        "silpo_get_my_food_restrictions",
        "silpo_get_my_offline_orders",
        "silpo_get_my_online_orders",
        "silpo_get_my_premium_subscription",
        "silpo_get_my_profile",
        "silpo_get_my_promos",
        "silpo_get_my_shopping_cart",
        "silpo_get_popular_categories",
        "silpo_get_product_details",
        "silpo_get_product_sets",
        "silpo_get_products",
        "silpo_get_promo_codes",
        "silpo_get_promotions",
        "silpo_get_replacements",
        "silpo_get_shopping_cart_by_id",
        "silpo_get_similar_products",
        "silpo_get_time_slots",
        "silpo_list_branches",
    }
)

WRITE_TOOLS = frozenset(
    {
        "silpo_create_shopping_cart",
        "silpo_add_or_update_cart_products",
        "silpo_remove_cart_products",
        "silpo_clear_shopping_cart",
        "silpo_update_shopping_cart",
        "silpo_add_or_update_favorite_products",
        "silpo_add_or_update_certificates",
    }
)


def counted_silence(seen: Silence, tool: str, raw: dict[str, Any]) -> Silence:
    if tool != SEARCH_TOOL:
        return seen
    rows = raw.get("queries")
    if not isinstance(rows, list):
        return seen
    empty = sum(1 for row in rows if isinstance(row, dict) and not (row.get("products") or []))
    return seen.plus(len(rows), empty)


class WriteBlocked(RuntimeError):
    ...


class MCPCallError(RuntimeError):

    def __init__(self, tool: str, message: str, *, attempts: int) -> None:
        super().__init__(f"{tool}: {message} (спроб: {attempts})")
        self.tool = tool
        self.attempts = attempts

    @property
    def reason(self) -> str:
        text = str(self)
        head, sep, tail = text.partition(": ")
        if sep and head == self.tool:
            text = tail
        return text.split(" (спроб:")[0].strip()[:160] or "без пояснення"


class TokenRejected(RuntimeError):

    def __init__(self, tool: str, message: str, *, attempts: int) -> None:
        super().__init__(f"{tool}: {message} (спроб: {attempts})")
        self.tool = tool
        self.attempts = attempts


TOKEN_STATUS = frozenset({401})


@dataclass(frozen=True, slots=True)
class CallOutcome:

    tool: str
    payload: dict[str, Any]
    payload_raw: dict[str, Any]
    duration_ms: int
    attempts: int


_STATUS_IN_TEXT = re.compile(r"(?:HTTP|status(?:\s+code)?|код)\D{0,4}(\d{3})", re.IGNORECASE)


def _status_of(exc: BaseException) -> int | None:
    if isinstance(exc, httpx2.HTTPStatusError):
        return exc.response.status_code
    found = _STATUS_IN_TEXT.search(str(exc))
    return int(found.group(1)) if found else None


def _is_token_rejected(exc: BaseException) -> bool:
    status = _status_of(exc)
    if status is not None:
        return status in TOKEN_STATUS
    return "invalid_token" in str(exc).lower()


def missing_resource(exc: BaseException) -> bool:
    return "resource not found" in str(exc).casefold()


_THROTTLE_WORDS = ("rate limit", "rate_limit", "too many requests")


def is_throttled(exc: BaseException) -> bool:
    if _status_of(exc) == 429:
        return True
    text = str(exc).casefold()
    return any(word in text for word in _THROTTLE_WORDS)


@dataclass(slots=True)
class Pressure:

    lost: int = 0
    throttled: int = 0
    failed: int = 0
    last: str = ""

    def saw(self, exc: BaseException) -> None:
        self.lost += 1
        if is_throttled(exc):
            self.throttled += 1
            self.last = str(exc)[:200]


def _is_retryable(exc: BaseException) -> bool:
    if isinstance(exc, httpx2.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_STATUS
    if isinstance(exc, (httpx2.TransportError, asyncio.TimeoutError)):
        return True
    found = _STATUS_IN_TEXT.search(str(exc))
    return found is not None and int(found.group(1)) in RETRYABLE_STATUS


def _extract_payload(result: types.CallToolResult) -> dict[str, Any]:
    if result.structured_content is not None:
        return dict(result.structured_content)

    for block in result.content:
        if isinstance(block, types.TextContent):
            try:
                parsed = json.loads(block.text)
            except json.JSONDecodeError:
                return {"text": block.text}
            return parsed if isinstance(parsed, dict) else {"items": parsed}

    return {}


_APOSTROPHE_QUERIES = {"silpo_find_products_batch": "products"}


def _straight_apostrophes(tool: str, args: dict[str, Any]) -> dict[str, Any]:
    field = _APOSTROPHE_QUERIES.get(tool)
    if field is None:
        return args
    queries = args.get(field)
    if not isinstance(queries, list):
        return args
    fixed = [
        "".join(APOSTROPHES.get(ch, ch) for ch in q) if isinstance(q, str) else q for q in queries
    ]
    if fixed == queries:
        return args
    log.info(
        "mcp.apostrophes_straightened",
        tool=tool,
        queries=sum(1 for a, b in zip(queries, fixed, strict=True) if a != b),
    )
    return {**args, field: fixed}


class SilpoMCP:

    def __init__(
        self,
        *,
        token: str | None = None,
        writes: bool = False,
        url: str | None = None,
        max_attempts: int | None = None,
        backoff_base_s: float | None = None,
        timeout_s: float | None = None,
        settings: Settings | None = None,
        fixtures_dir: Path | None = None,
    ) -> None:
        self._settings = settings if settings is not None else _default_settings
        self.url = url or self._settings.mcp_url
        self._token = token
        self._writes = writes
        self.max_attempts = max_attempts or self._settings.mcp_max_attempts
        self.backoff_base_s = backoff_base_s or self._settings.mcp_backoff_base_s
        self.timeout_s = timeout_s or self._settings.mcp_timeout_s
        self._fixtures_dir = fixtures_dir

        self._stack: list[Any] = []
        self._last_status: int | None = None
        self.pressure = Pressure()
        self.silence = Silence()
        self._session: ClientSession | None = None
        self._aliases: dict[str, str] | None = None

    async def __aenter__(self) -> Self:
        if self._fixtures_dir is not None:
            log.info("mcp.fixture_mode", dir=str(self._fixtures_dir))
            return self

        if not self._token:
            raise RuntimeError(
                "SilpoMCP без токена: доступ возить запит, а не конфіг. "
                "Гість підключає акаунт кнопкою, крон бере токен оператора "
                "через settings.require_operator()."
            )

        http_client = create_mcp_http_client(
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=httpx2.Timeout(self.timeout_s, connect=10.0),
        )
        http_client.event_hooks["response"].append(self._remember_status)
        await http_client.__aenter__()
        self._stack.append(http_client)

        try:
            transport = streamable_http_client(self.url, http_client=http_client)
            read_stream, write_stream = await transport.__aenter__()
            self._stack.append(transport)

            session = ClientSession(read_stream, write_stream, read_timeout_seconds=self.timeout_s)
            await session.__aenter__()
            self._stack.append(session)

            await session.initialize()
        except Exception as exc:
            await self._unwind(type(exc), exc, exc.__traceback__)
            if self._last_status in TOKEN_STATUS:
                raise TokenRejected(
                    "session.initialize", f"HTTP {self._last_status}", attempts=1
                ) from exc
            raise MCPCallError("session.initialize", str(exc)[:200], attempts=1) from exc

        self._session = session
        log.info("mcp.connected", url=self.url)
        return self

    async def _remember_status(self, response: httpx2.Response) -> None:
        self._last_status = response.status_code

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self._unwind(exc_type, exc, tb)

    async def _unwind(
        self,
        exc_type: type[BaseException] | None = None,
        exc: BaseException | None = None,
        tb: TracebackType | None = None,
    ) -> None:
        self._session = None
        while self._stack:
            resource = self._stack.pop()
            try:
                await resource.__aexit__(exc_type, exc, tb)
            except Exception:
                log.debug("mcp.close_failed", resource=type(resource).__name__)

    async def describe_tools(self) -> list[dict[str, Any]]:
        if self._fixtures_dir is not None:
            path = self._fixtures_dir / "tools.json"
            if not path.is_file():
                return []
            return canonical(json.loads(path.read_text(encoding="utf-8")))
        if self._session is None:
            raise RuntimeError("сесія не відкрита: використовуй `async with SilpoMCP() as mcp`")
        listed = await self._session.list_tools()
        return canonical(
            [
                {
                    "name": tool.name,
                    "description": tool.description or "",
                    "input_schema": getattr(tool, "inputSchema", None) or {},
                }
                for tool in listed.tools
            ]
        )

    async def call(self, tool: str, arguments: dict[str, Any] | None = None) -> CallOutcome:
        if tool not in READ_TOOLS and not self._writes:
            log.warning("mcp.write_blocked", tool=tool)
            what = (
                "змінює стан"
                if tool in WRITE_TOOLS
                else "не входить у READ_TOOLS, тож вважається таким, що змінює стан"
            )
            raise WriteBlocked(
                f"{tool} {what}, а цей клієнт відкритий на читання. "
                "Право писати береться явно: SilpoMCP(writes=True)."
            )

        args = _straight_apostrophes(tool, arguments or {})

        if self._fixtures_dir is not None:
            return self._from_fixture(tool, args)

        if self._session is None:
            raise RuntimeError("сесія не відкрита: використовуй `async with SilpoMCP() as mcp`")

        safe_args = redact(args)
        wire = (self._aliases or {}).get(tool, tool)
        try:
            return await self._dial(tool, wire, args, safe_args)
        except MCPCallError:
            found = await self._renamed_to(tool)
            if found is None or found == wire:
                raise
            wire = found
            log.warning("mcp.tool_renamed", was=tool, now=wire)
            return await self._dial(tool, wire, args, safe_args)

    async def _renamed_to(self, tool: str) -> str | None:
        if tool not in READ_TOOLS:
            return None
        if self._aliases is None:
            try:
                found = rebind(await self.describe_tools(), verdict_register.load())
            except Exception as exc:
                log.warning("mcp.inventory_unavailable", error=str(exc)[:160])
                found = ()
            self._aliases = {rename.was: rename.now for rename in found}
        return self._aliases.get(tool)

    async def _dial(
        self, tool: str, wire: str, args: dict[str, Any], safe_args: dict[str, Any]
    ) -> CallOutcome:
        assert self._session is not None
        started = asyncio.get_running_loop().time()
        last_error: BaseException | None = None
        attempt = 0

        attempts_allowed = self.max_attempts if tool in READ_TOOLS else 1

        for attempt in range(1, attempts_allowed + 1):
            try:
                result = await self._session.call_tool(wire, args)
            except Exception as exc:
                last_error = exc
                self.pressure.saw(exc)
                if attempt >= attempts_allowed or not _is_retryable(exc):
                    break
                await self._sleep_backoff(attempt, tool, str(exc))
                continue

            if not isinstance(result, types.CallToolResult):
                raise MCPCallError(
                    tool, f"несподіваний тип відповіді {type(result)}", attempts=attempt
                )

            if result.is_error:
                message = _extract_payload(result).get("text", "tool повернув is_error")
                last_error = MCPCallError(tool, str(message), attempts=attempt)
                self.pressure.saw(last_error)
                if attempt >= attempts_allowed or not _is_retryable(last_error):
                    break
                await self._sleep_backoff(attempt, tool, str(message))
                continue

            duration_ms = int((asyncio.get_running_loop().time() - started) * 1000)
            log.info("mcp.call", tool=tool, args=safe_args, ms=duration_ms, attempts=attempt)
            raw_payload = _extract_payload(result)
            self._count_silence(tool, raw_payload)
            return CallOutcome(
                tool=tool,
                payload=redact(raw_payload),
                payload_raw=raw_payload,
                duration_ms=duration_ms,
                attempts=attempt,
            )

        self.pressure.failed += 1
        log.error("mcp.call_failed", tool=tool, args=safe_args, error=str(last_error))
        if last_error is not None and _is_token_rejected(last_error):
            raise TokenRejected(tool, str(last_error), attempts=attempt)
        if self._last_status in TOKEN_STATUS:
            raise TokenRejected(tool, f"HTTP {self._last_status}", attempts=attempt)
        raise MCPCallError(tool, str(last_error), attempts=attempt)

    def _from_fixture(self, tool: str, args: dict[str, Any]) -> CallOutcome:
        assert self._fixtures_dir is not None
        path = self._fixtures_dir / f"{tool}.json"
        if not path.is_file():
            raise MCPCallError(
                tool,
                f"стенд на фікстурах: мережі немає, а файлу {path.name} теж",
                attempts=1,
            )
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raw = {"items": raw}
        log.info("mcp.fixture", tool=tool, args=redact(args))
        self._count_silence(tool, raw)
        return CallOutcome(
            tool=tool,
            payload=redact(raw),
            payload_raw=raw,
            duration_ms=0,
            attempts=1,
        )

    def _count_silence(self, tool: str, raw: dict[str, Any]) -> None:
        self.silence = counted_silence(self.silence, tool, raw)

    async def _sleep_backoff(self, attempt: int, tool: str, reason: str) -> None:
        delay = self.backoff_base_s**attempt * (0.5 + random.random())
        log.warning("mcp.retry", tool=tool, attempt=attempt, delay_s=round(delay, 2), reason=reason)
        await asyncio.sleep(delay)
