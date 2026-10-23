from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from komora.agent.spending import WeekSpendError, week_spend
from komora.config import Settings
from komora.mcp.client import SilpoMCP

SLOT = {
    "start": "2026-08-19T06:00:00+00:00",
    "end": "2026-08-19T08:00:00+00:00",
    "available": True,
    "deliveryType": "DeliveryHome",
    "deliveryCost": 89,
    "minOrderCost": 599,
    "maxWeight": 50,
}

NOW = datetime(2026, 8, 18, 20, 47, tzinfo=UTC)


def stand(tmp_path, orders: list[dict], *, total: int | None = None, slots=(SLOT,)) -> SilpoMCP:
    (tmp_path / "silpo_get_time_slots.json").write_text(
        json.dumps({"slots": list(slots)}), encoding="utf-8"
    )
    (tmp_path / "silpo_get_my_offline_orders.json").write_text(
        json.dumps(
            {"orders": orders, "meta": {"total": len(orders) if total is None else total}}
        ),
        encoding="utf-8",
    )
    (tmp_path / "silpo_get_my_delivery_addresses.json").write_text(
        json.dumps(
            {
                "addresses": [
                    {
                        "id": "addr-1",
                        "city": "Вінниця",
                        "street": "вулиця Соборна",
                        "building": "1",
                        "latitude": 49.22,
                        "longitude": 28.45,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "silpo_get_available_delivery_types.json").write_text(
        json.dumps({"options": [{"deliveryType": "DeliveryHome", "branchId": "branch-1"}]}),
        encoding="utf-8",
    )
    return SilpoMCP(settings=Settings.model_construct(), fixtures_dir=tmp_path)


async def test_the_week_is_counted_from_monday_in_the_guests_time(tmp_path):
    mcp = stand(
        tmp_path,
        [
            {"createdAt": "2026-08-17T09:12:00", "sumReg": 597.66},
            {"createdAt": "2026-08-18T20:09:01", "sumReg": 402.34},
        ],
    )
    async with mcp:
        frame = await week_spend(mcp, now=NOW)

    assert frame.spent == Decimal("1000.00")
    assert frame.receipts == 2
    assert frame.since == datetime(2026, 8, 17)


async def test_the_receipts_are_asked_for_this_week_only(tmp_path):
    calls: list[dict] = []
    mcp = stand(tmp_path, [{"createdAt": "2026-08-17T09:12:00", "sumReg": 100}])
    original = mcp.call

    async def spy(tool: str, arguments: dict | None = None):
        if tool == "silpo_get_my_offline_orders":
            calls.append(arguments or {})
        return await original(tool, arguments)

    mcp.call = spy  # type: ignore[method-assign]
    async with mcp:
        await week_spend(mcp, now=NOW)

    assert calls[0]["dateStart"] == "2026-08-17T00:00:00"
    assert len(calls) == 1, "одна сторінка на два чеки — далі ходити нема за чим"


async def test_the_context_slot_is_asked_from_now_not_from_dawn(tmp_path):
    calls: list[dict] = []
    mcp = stand(tmp_path, [{"createdAt": "2026-08-17T09:12:00", "sumReg": 100}])
    original = mcp.call

    async def spy(tool: str, arguments: dict | None = None):
        if tool == "silpo_get_time_slots":
            calls.append(arguments or {})
        return await original(tool, arguments)

    mcp.call = spy  # type: ignore[method-assign]
    async with mcp:
        frame = await week_spend(mcp, now=NOW)

    assert calls[0]["start"] == "2026-08-18T20:47:00+00:00"
    assert frame.since == datetime(2026, 8, 17), "тиждень лишився місцевим"


async def test_paging_stops_on_the_total_the_api_reported(tmp_path):
    orders = [{"createdAt": "2026-08-17T09:00:00", "sumReg": 10} for _ in range(10)]
    mcp = stand(tmp_path, orders, total=10)
    async with mcp:
        frame = await week_spend(mcp, now=NOW)

    assert frame.receipts == 10, "друга сторінка не подвоює тиждень"


async def test_without_a_slot_the_frame_refuses_instead_of_showing_zero(tmp_path):
    mcp = stand(tmp_path, [], slots=())
    async with mcp:
        with pytest.raises(WeekSpendError, match="слота"):
            await week_spend(mcp, now=NOW)
