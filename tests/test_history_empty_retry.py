from __future__ import annotations

from typing import Any

import pytest
from structlog.testing import capture_logs

from komora.agent.basket import _offline_pages
from komora.mcp.client import CallOutcome

SLOT = {"deliveryType": "delivery", "start": "2026-09-20T10:00", "end": "2026-09-20T12:00"}


class _Silpo:

    def __init__(self, pages: list[list[dict[str, Any]]]) -> None:
        self.pages = pages
        self.calls: list[dict[str, Any]] = []

    async def call(self, tool: str, args: dict[str, Any]) -> CallOutcome:
        self.calls.append(args)
        rows = self.pages[len(self.calls) - 1] if len(self.calls) <= len(self.pages) else []
        return CallOutcome(
            tool=tool,
            payload={},
            payload_raw={"orders": rows},
            duration_ms=7,
            attempts=1,
        )


@pytest.mark.asyncio
async def test_an_empty_first_page_is_asked_once_more() -> None:
    mcp = _Silpo([[], [{"id": "1"}, {"id": "2"}, {"id": "3"}]])

    orders, _spent = await _offline_pages(mcp, SLOT, "філія", since="2020-01-01")

    assert [row["id"] for row in orders] == ["1", "2", "3"]
    assert len(mcp.calls) == 2


@pytest.mark.asyncio
async def test_the_retry_says_so_even_when_it_helped() -> None:
    mcp = _Silpo([[], [{"id": "1"}]])

    with capture_logs() as written:
        await _offline_pages(mcp, SLOT, "філія", since="2020-01-01")

    said = [row for row in written if row["event"] == "history.empty_retry"]
    assert len(said) == 1
    assert said[0]["healed"] is True
    assert said[0]["orders"] == 1


@pytest.mark.asyncio
async def test_a_truly_empty_history_stays_empty_and_costs_one_retry() -> None:
    mcp = _Silpo([[], []])

    orders, _spent = await _offline_pages(mcp, SLOT, "філія", since="2020-01-01")

    assert orders == []
    assert len(mcp.calls) == 2


@pytest.mark.asyncio
async def test_the_retry_says_so_when_it_did_not_help() -> None:
    mcp = _Silpo([[], []])

    with capture_logs() as written:
        await _offline_pages(mcp, SLOT, "філія", since="2020-01-01")

    said = [row for row in written if row["event"] == "history.empty_retry"]
    assert len(said) == 1
    assert said[0]["healed"] is False


@pytest.mark.asyncio
async def test_a_later_empty_page_is_the_end_of_history_and_is_not_repeated() -> None:
    full = [{"id": str(number)} for number in range(50)]
    mcp = _Silpo([full, []])

    orders, _spent = await _offline_pages(mcp, SLOT, "філія", since="2020-01-01")

    assert len(orders) == 50
    assert len(mcp.calls) == 2
