from __future__ import annotations

import httpx2
import pytest

from komora.mcp.client import (
    RETRYABLE_STATUS,
    TOKEN_STATUS,
    MCPCallError,
    TokenRejected,
    _is_retryable,
    _is_token_rejected,
)


def status_error(code: int) -> httpx2.HTTPStatusError:
    request = httpx2.Request("POST", "https://mcp.silpo.ua/mcp")
    return httpx2.HTTPStatusError(
        f"HTTP {code}", request=request, response=httpx2.Response(code, request=request)
    )


def test_401_is_a_rejected_token():
    assert _is_token_rejected(status_error(401))


@pytest.mark.parametrize("code", [400, 403, 404, 429, 500, 503])
def test_other_statuses_are_not(code):
    assert not _is_token_rejected(status_error(code))


def test_status_is_read_from_the_text_when_the_type_is_lost():
    assert _is_token_rejected(RuntimeError("upstream said HTTP 401 Unauthorized"))


def test_bare_number_in_the_text_is_not_a_status():
    assert not _is_token_rejected(RuntimeError("товар 401 недоступний"))


def test_rfc_term_is_recognised_without_a_code():
    assert _is_token_rejected(RuntimeError('{"error":"invalid_token"}'))


def test_ordinary_failure_is_not_a_rejected_token():
    assert not _is_token_rejected(RuntimeError("з'єднання розірвано"))
    assert not _is_token_rejected(TimeoutError())


def test_rejected_token_is_never_retried():
    assert not TOKEN_STATUS & RETRYABLE_STATUS
    assert not _is_retryable(status_error(401))


def test_the_general_catch_does_not_swallow_it():
    error = TokenRejected("silpo_get_my_shopping_cart", "HTTP 401", attempts=1)
    assert not isinstance(error, MCPCallError)
    assert error.tool == "silpo_get_my_shopping_cart"
    assert error.attempts == 1


def test_it_stays_an_ordinary_runtime_error():
    assert isinstance(TokenRejected("t", "HTTP 401", attempts=1), RuntimeError)


def test_client_remembers_the_status_it_saw():
    from komora.config import Settings
    from komora.mcp.client import SilpoMCP

    mcp = SilpoMCP(settings=Settings.model_construct(), token="х")
    assert mcp._last_status is None, "поки нічого не бачили — нічого й не знаємо"


async def test_status_hook_records_the_response():
    from komora.config import Settings
    from komora.mcp.client import SilpoMCP

    mcp = SilpoMCP(settings=Settings.model_construct(), token="х")
    await mcp._remember_status(httpx2.Response(401))
    assert mcp._last_status == 401


class _Closable:
    def __init__(self, name: str) -> None:
        self.name = name
        self.closed = False
        self.event_hooks: dict[str, list] = {"response": []}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args) -> None:
        self.closed = True


class _Transport(_Closable):
    async def __aenter__(self):
        return ("читання", "запис")


class _Session(_Closable):
    def __init__(self, *_args, **_kwargs) -> None:
        super().__init__("session")

    async def initialize(self) -> None:
        raise RuntimeError("Server returned an error response")


@pytest.fixture
def opened(monkeypatch) -> dict[str, _Closable]:
    from komora.mcp import client as module

    made: dict[str, _Closable] = {}

    def _http(**_kwargs) -> _Closable:
        made["http"] = _Closable("http")
        return made["http"]

    def _transport(*_args, **_kwargs) -> _Transport:
        made["transport"] = _Transport("transport")
        return made["transport"]

    def _session(*args, **kwargs) -> _Session:
        made["session"] = _Session(*args, **kwargs)
        return made["session"]

    monkeypatch.setattr(module, "create_mcp_http_client", _http)
    monkeypatch.setattr(module, "streamable_http_client", _transport)
    monkeypatch.setattr(module, "ClientSession", _session)
    return made


async def _connect(status: int | None) -> tuple[Exception, object]:
    from komora.config import Settings
    from komora.mcp.client import SilpoMCP

    mcp = SilpoMCP(settings=Settings.model_construct(), token="х")
    mcp._last_status = status
    with pytest.raises(Exception) as caught:
        await mcp.__aenter__()
    return caught.value, mcp


@pytest.mark.parametrize("status", [401, 500])
async def test_a_failed_login_closes_everything_it_opened(opened, status):
    _, mcp = await _connect(status)

    assert all(resource.closed for resource in opened.values())
    assert mcp._stack == []


async def test_a_dead_token_is_still_named_a_dead_token(opened):
    error, _ = await _connect(401)

    assert isinstance(error, TokenRejected)


async def test_a_server_crash_is_still_a_crash(opened):
    error, _ = await _connect(500)

    assert isinstance(error, MCPCallError) and not isinstance(error, TokenRejected)
