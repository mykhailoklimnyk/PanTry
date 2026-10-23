from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from komora.agent.basket import assemble_list
from komora.api.schemas import BuildRequest
from komora.mcp.client import SilpoMCP

NOW = datetime(2026, 9, 6, tzinfo=UTC)
SLOT = {
    "start": "2026-09-06T11:30:00+00:00",
    "end": "2026-09-06T13:00:00+00:00",
    "available": True,
    "deliveryType": "DeliveryHome",
    "deliveryCost": 89,
    "deliveryCostMap": [{"cost": 59, "fromOrderCost": 1199}],
    "minOrderCost": 599,
    "maxWeight": 50,
}

WATER = "Вода мінеральна Моршинська"
OTHER_WATER = "Вода дитяча Малятко"

SAID = "вода"

DUE = "Молоко Ферма"


def _card(pid: int, name: str, price: float) -> dict:
    return {
        "id": f"00000000-0000-4000-8000-{pid:012d}",
        "name": name,
        "slug": f"slug-{pid}",
        "price": price,
        "oldPrice": None,
        "stock": 30,
        "available": True,
        "image": None,
        "weighted": False,
        "step": 1,
        "displayRatio": "1.5л",
        "companyId": "00000000-0000-4000-8000-000000000001",
        "branchId": "00000000-0000-4000-8000-000000000002",
        "externalProductId": pid,
    }


def _bought(days_ago: int, lager: int, name: str, price: float) -> dict:
    return {
        "createdAt": (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%d"),
        "products": [
            {
                "lagerId": lager,
                "name": name,
                "unit": "1.5л",
                "quantity": 1,
                "price": price,
            }
        ],
    }


def _stand(tmp_path) -> SilpoMCP:
    (tmp_path / "silpo_get_time_slots.json").write_text(
        json.dumps({"slots": [SLOT]}), encoding="utf-8"
    )
    (tmp_path / "silpo_get_my_offline_orders.json").write_text(
        json.dumps(
            {
                "orders": [_bought(day, 401, WATER, 30.0) for day in (2, 9, 16, 23)]
                + [_bought(day, 411, OTHER_WATER, 20.0) for day in (5, 12, 19, 26)]
                + [_bought(day, 501, DUE, 40.0) for day in (20, 27, 34, 41)]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "silpo_get_my_shopping_cart.json").write_text(
        json.dumps({"shoppingCartId": None}), encoding="utf-8"
    )
    waters = [_card(401, WATER, 30.0), _card(411, OTHER_WATER, 20.0)]
    shelf = {
        SAID: waters,
        WATER: waters,
        OTHER_WATER: waters,
        "Вода мінеральна": waters,
        "Вода дитяча": waters,
        "Вода": waters,
        DUE: [_card(502, DUE, 40.0)],
        "Молоко": [_card(502, DUE, 40.0)],
    }
    (tmp_path / "silpo_find_products_batch.json").write_text(
        json.dumps(
            {"queries": [{"query": query, "products": cards} for query, cards in shelf.items()]}
        ),
        encoding="utf-8",
    )
    return SilpoMCP(fixtures_dir=tmp_path)


async def _build(tmp_path, said: list[str]):
    return await assemble_list(
        _stand(tmp_path),
        llm=None,
        request=BuildRequest.model_validate({"mode": "week", "budget": 3000, "shoppingList": said}),
        now=NOW,
    )


@pytest.mark.anyio
async def test_the_guest_word_covers_its_kind_in_the_fill(tmp_path) -> None:
    assembled = await _build(tmp_path, [SAID])

    step = next(s for s in assembled.basket.trace if s.id == "step-target")
    assert step.args["докинуто"] == []


@pytest.mark.anyio
async def test_the_step_counts_both_waters_as_covered(tmp_path) -> None:
    assembled = await _build(tmp_path, [SAID])

    step = next(s for s in assembled.basket.trace if s.id == "step-target")
    assert step.args["решта пулу"] == "2 того ж виду, що вже в кошику"


@pytest.mark.anyio
async def test_without_the_word_the_fill_still_brings_water(tmp_path) -> None:
    assembled = await _build(tmp_path, [])

    step = next(s for s in assembled.basket.trace if s.id == "step-target")
    assert step.args["докинуто"] == [OTHER_WATER]
    assert any(line.name == OTHER_WATER for line in assembled.basket.lines)
