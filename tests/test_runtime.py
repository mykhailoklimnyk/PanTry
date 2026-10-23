from __future__ import annotations

import asyncio

import pytest

from komora import runtime


async def _loop_name() -> str:
    return type(asyncio.get_running_loop()).__name__


def test_linux_needs_no_factory_of_its_own():
    assert runtime.loop_factory("linux") is None
    assert runtime.loop_factory("darwin") is None


def test_windows_gets_the_selector_loop():
    assert runtime.loop_factory("win32") is asyncio.SelectorEventLoop


def test_the_run_really_lands_on_a_selector_loop():
    assert "Selector" in runtime.run(_loop_name(), platform="win32")


def test_without_windows_the_run_is_plain_asyncio_run():
    assert runtime.run(_loop_name(), platform="linux")


def test_the_run_returns_what_the_coroutine_returned():
    async def answer() -> int:
        return 42

    assert runtime.run(answer()) == 42


class Stream:

    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []

    def reconfigure(self, **kwargs: str) -> None:
        self.calls.append(kwargs)


def test_the_console_is_left_alone_outside_windows():
    stream = Stream()
    assert runtime.console("linux", [stream]) == 0
    assert not stream.calls


def test_windows_streams_get_utf8_that_never_raises():
    out, err = Stream(), Stream()
    assert runtime.console("win32", [out, err]) == 2
    assert out.calls == [{"encoding": "utf-8", "errors": "replace"}]
    assert err.calls == out.calls


def test_a_stream_without_reconfigure_is_skipped_not_crashed():
    assert runtime.console("win32", [object(), Stream()]) == 1


def test_the_run_fixes_the_console_before_the_work_starts(monkeypatch: pytest.MonkeyPatch):
    fixed = []
    monkeypatch.setattr(runtime, "console", lambda platform=None: fixed.append(platform))

    async def work() -> str:
        return "готово"

    assert runtime.run(work(), platform="win32") == "готово"
    assert fixed == ["win32"]
