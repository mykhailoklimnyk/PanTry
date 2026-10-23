from __future__ import annotations

import logging
from typing import Any, ClassVar

import pytest

import komora.notify as notify
from komora.config import Settings
from komora.logging import quiet_url_logs
from komora.mcp.client import MCPCallError, Pressure, is_throttled

pytestmark = pytest.mark.anyio


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_a_throttle_is_named_by_the_code_and_by_the_word():
    assert is_throttled(MCPCallError("t", "HTTP 429 slow down", attempts=1))
    assert is_throttled(RuntimeError("Rate limit exceeded"))
    assert is_throttled(RuntimeError("429 Too Many Requests"))


def test_a_plain_failure_is_not_called_a_throttle():
    assert not is_throttled(RuntimeError("HTTP 500 internal"))
    assert not is_throttled(RuntimeError("з'єднання розірвано"))


def test_a_retry_that_succeeded_still_leaves_a_trace():
    pressure = Pressure()
    pressure.saw(RuntimeError("HTTP 429"))
    assert (pressure.lost, pressure.throttled, pressure.failed) == (1, 1, 0)
    assert "429" in pressure.last


def test_the_word_of_the_api_is_kept_and_not_our_guess():
    pressure = Pressure()
    pressure.saw(RuntimeError("rate limit: 100 requests per minute"))
    assert "100 requests per minute" in pressure.last


def test_a_token_never_reaches_the_log():
    boom = "timeout for https://api.telegram.org/bot777:SECRET/sendMessage"
    hidden = notify.hide(boom, "777:SECRET")
    assert "SECRET" not in hidden
    assert "***" in hidden


def test_hiding_nothing_is_not_hiding_everything():
    assert notify.hide("просто помилка", None) == "просто помилка"


def test_the_library_does_not_print_the_url_behind_our_back(caplog: pytest.LogCaptureFixture):
    logging.getLogger("httpx2").setLevel(logging.INFO)
    quiet_url_logs()

    with caplog.at_level(logging.INFO):
        logging.getLogger("httpx2").info(
            "HTTP Request: POST https://api.telegram.org/bot777:SECRET/sendMessage"
        )

    assert "SECRET" not in caplog.text


async def test_without_a_channel_the_job_is_told_why_and_not_left_guessing():
    told = await notify.send("байдуже", config=Settings.model_construct())
    assert not told.ok
    assert "KOMORA_TELEGRAM_TOKEN" in told.why


class _Answer:
    def __init__(self, boom: Exception | None = None) -> None:
        self._boom = boom

    def raise_for_status(self) -> None:
        if self._boom is not None:
            raise self._boom


class _Client:

    sent: ClassVar[list[dict[str, Any]]] = []

    def __init__(self, boom: Exception | None = None, **_: Any) -> None:
        self._boom = boom

    async def __aenter__(self) -> _Client:
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None

    async def post(self, url: str, *, json: dict[str, Any]) -> _Answer:
        _Client.sent.append({"url": url, **json})
        return _Answer(self._boom)


def _channel() -> Settings:
    return Settings.model_construct(telegram_token="777:SECRET", telegram_chat="-100")


async def test_a_message_goes_where_it_was_told(monkeypatch: pytest.MonkeyPatch):
    _Client.sent.clear()
    monkeypatch.setattr(notify.httpx2, "AsyncClient", _Client)
    told = await notify.send("КОМОРА · обхід", config=_channel())
    assert told.ok
    assert _Client.sent[0]["chat_id"] == "-100"
    assert _Client.sent[0]["text"] == "КОМОРА · обхід"


async def test_a_message_longer_than_telegram_allows_is_cut_by_us(
    monkeypatch: pytest.MonkeyPatch,
):
    _Client.sent.clear()
    monkeypatch.setattr(notify.httpx2, "AsyncClient", _Client)
    await notify.send("я" * (notify.LIMIT + 100), config=_channel())
    assert len(_Client.sent[0]["text"]) == notify.LIMIT


async def test_a_dead_messenger_does_not_kill_the_run_and_does_not_leak(
    monkeypatch: pytest.MonkeyPatch,
):

    def broken(**kwargs: Any) -> _Client:
        return _Client(boom=RuntimeError("500 from https://api.telegram.org/bot777:SECRET/x"))

    monkeypatch.setattr(notify.httpx2, "AsyncClient", broken)
    told = await notify.send("звіт", config=_channel())
    assert not told.ok
    assert "SECRET" not in told.why


def test_the_failure_notice_names_the_unit_and_the_way_to_look():
    text = notify.about_failure("komora-catalog.service", host="fedora")
    assert "komora-catalog.service" in text
    assert "journalctl --user -u komora-catalog.service" in text
