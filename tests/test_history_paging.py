from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

from komora.agent.basket import HISTORY_PAGE, load_history

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 9, 2, tzinfo=UTC)

SLOT = {
    "start": "2026-09-02T11:30:00+00:00",
    "end": "2026-09-02T13:00:00+00:00",
    "available": True,
    "deliveryType": "DeliveryHome",
}


def _receipt(number: int) -> dict[str, Any]:
    return {
        "createdAt": f"2026-0{1 + number % 8}-01T20:09:01",
        "sumReg": 100.0 + number,
        "products": [
            {"lagerId": 1000 + number, "name": f"Товар {number}", "unit": "шт", "quantity": 1}
        ],
    }


class _Silpo:

    def __init__(
        self, receipts: list[dict[str, Any]], *, cap: int, total: bool = True
    ) -> None:
        self.receipts = receipts
        self.cap = cap
        self.total = total
        self.pages: list[tuple[int, int]] = []

    async def call(self, tool: str, arguments: dict[str, Any] | None = None) -> Any:
        args = arguments or {}
        if tool != "silpo_get_my_offline_orders":
            return _Outcome({"orders": [], "meta": {"total": 0}})
        limit = min(int(args.get("limit", 10)), self.cap)
        offset = int(args.get("offset", 0))
        self.pages.append((offset, limit))
        page = {"orders": self.receipts[offset : offset + limit]}
        if self.total:
            page["meta"] = {"total": len(self.receipts)}
        return _Outcome(page)


class _Outcome:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload_raw = payload
        self.payload = payload
        self.duration_ms = 1


async def test_a_told_total_saves_the_blind_extra_page() -> None:
    stand = _Silpo([_receipt(n) for n in range(HISTORY_PAGE)], cap=HISTORY_PAGE)

    _, receipts, _, _, _ = await load_history(stand, SLOT, "філія", now=NOW)

    assert receipts == HISTORY_PAGE
    assert len(stand.pages) == 1


async def test_a_shorter_page_from_the_api_loses_no_receipts() -> None:
    stand = _Silpo([_receipt(n) for n in range(35)], cap=HISTORY_PAGE, total=False)

    _, receipts, _, _, _ = await load_history(stand, SLOT, "філія", now=NOW)

    assert receipts == 35, "зрізана сторінка не має губити хвіст історії"
    assert [offset for offset, _ in stand.pages] == [0, 10, 20, 30]


async def test_an_empty_history_stops_at_the_first_call() -> None:
    stand = _Silpo([], cap=HISTORY_PAGE)

    _, receipts, _, _, _ = await load_history(stand, SLOT, "філія", now=NOW)

    assert receipts == 0
    assert len(stand.pages) == 1


async def test_an_exact_page_asks_once_more_when_nobody_said_the_total() -> None:
    stand = _Silpo(
        [_receipt(n) for n in range(HISTORY_PAGE)], cap=HISTORY_PAGE, total=False
    )

    _, receipts, _, _, _ = await load_history(stand, SLOT, "філія", now=NOW)

    assert receipts == HISTORY_PAGE
    assert len(stand.pages) == 2


async def test_a_told_total_stops_us_on_the_page_that_reached_it() -> None:
    stand = _Silpo([_receipt(n) for n in range(HISTORY_PAGE)], cap=HISTORY_PAGE)

    _, receipts, _, _, _ = await load_history(stand, SLOT, "філія", now=NOW)

    assert receipts == HISTORY_PAGE
    assert len(stand.pages) == 1


async def test_a_capped_page_would_look_exactly_like_the_end_of_history() -> None:
    stand = _Silpo([_receipt(n) for n in range(35)], cap=HISTORY_PAGE, total=False)

    _, receipts, _, _, _ = await load_history(stand, SLOT, "філія", now=NOW)

    assert receipts == 35
    assert [offset for offset, _ in stand.pages] == [0, 10, 20, 30]
