from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from komora.agent.basket import (
    AssemblyError,
    HistoryItem,
    apply_marks,
    assemble_list,
    mark_pantry,
    receipts_pantry,
)
from komora.api.schemas import BuildRequest, PantryAdjustment
from komora.core.marks import stocked_at
from komora.mcp.client import SilpoMCP

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 8, 21, tzinfo=UTC)

SLOT = {
    "start": "2026-08-21T11:30:00+00:00",
    "end": "2026-08-21T13:00:00+00:00",
    "available": True,
    "deliveryType": "DeliveryHome",
    "deliveryCost": 89,
    "deliveryCostMap": [{"cost": 59, "fromOrderCost": 1199}],
    "minOrderCost": 599,
    "maxWeight": 50,
}


def _item(name: str, lager: str, *, days: list[int], qty: int = 1) -> HistoryItem:
    return HistoryItem(
        lager_id=lager,
        name=name,
        unit="шт",
        receipts=len(days),
        qty_total=Decimal(qty * len(days)),
        recent_receipts=len(days),
        qty_recent=Decimal(qty * len(days)),
        moments=[NOW - timedelta(days=day) for day in days],
    )


def test_the_guests_word_takes_the_row_out_of_running_out():
    bread = _item("Хліб Київський", "1", days=[15, 12, 9, 6])
    assert receipts_pantry([bread], now=NOW)[0].running_out is True

    apply_marks([bread], {"хліб київський": NOW})
    row = receipts_pantry([bread], now=NOW)[0]

    assert row.running_out is False
    assert row.state.startswith("взято сьогодні"), (
        "це слово ГОСТЯ, а не оцінка з чеків — і рядок мусить сказати саме так"
    )


def test_an_old_word_does_not_beat_a_fresh_receipt():
    milk = _item("Молоко Ферма", "1", days=[28, 19, 10, 1])
    apply_marks([milk], {"молоко ферма": NOW - timedelta(days=5)})

    row = receipts_pantry([milk], now=NOW)[0]
    assert row.state.startswith("оцінка:")
    assert milk.days_since_last(NOW) == 1


def test_the_mark_covers_every_sku_of_the_kind():
    first = _item("Хліб Київський житній", "1", days=[15, 12, 9, 6])
    second = _item("Хліб Київський пшеничний", "2", days=[16, 13, 10, 7])

    apply_marks([first, second], {"хліб київський": NOW})

    assert first.marked_at == second.marked_at == NOW
    assert [row.running_out for row in receipts_pantry([first, second], now=NOW)] == [False]


@pytest.fixture
def stand(tmp_path) -> SilpoMCP:
    (tmp_path / "silpo_get_time_slots.json").write_text(
        json.dumps({"slots": [SLOT]}), encoding="utf-8"
    )
    (tmp_path / "silpo_get_my_offline_orders.json").write_text(
        json.dumps(
            {
                "orders": [
                    {
                        "createdAt": day,
                        "products": [
                            {
                                "lagerId": 101,
                                "name": "Хліб Київський",
                                "unit": "шт",
                                "quantity": 1,
                                "price": 30,
                            },
                            {
                                "lagerId": 201,
                                "name": "Молоко Ферма",
                                "unit": "шт",
                                "quantity": 4,
                                "price": 53,
                            },
                        ],
                    }
                    for day in ("2026-07-18", "2026-07-25", "2026-08-01", "2026-08-08")
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "silpo_find_products_batch.json").write_text(
        json.dumps(
            {
                "queries": [
                    {
                        "query": name,
                        "products": [
                            {
                                "id": f"00000000-0000-4000-8000-{pid:012d}",
                                "name": name,
                                "slug": f"slug-{pid}",
                                "price": 30.0,
                                "oldPrice": None,
                                "stock": 20,
                                "available": True,
                                "image": None,
                                "weighted": False,
                                "step": 1,
                                "displayRatio": "1шт",
                                "companyId": "00000000-0000-4000-8000-000000000001",
                                "branchId": "00000000-0000-4000-8000-000000000002",
                                "externalProductId": pid,
                            }
                        ],
                    }
                    for pid, name in ((101, "Хліб Київський"), (201, "Молоко Ферма"))
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "silpo_get_my_shopping_cart.json").write_text(
        json.dumps({"shoppingCartId": None}), encoding="utf-8"
    )
    return SilpoMCP(fixtures_dir=tmp_path)


async def _ask(stand: SilpoMCP, **payload: Any) -> dict[str, datetime]:
    return await mark_pantry(stand, PantryAdjustment.model_validate(payload), now=NOW)


async def test_bought_moves_the_reference_point_to_today(stand):
    said = await _ask(stand, id="101", action="bought")

    assert said == {"хліб київський": NOW}


async def test_a_named_quantity_lands_on_the_same_axis(stand):
    said = await _ask(stand, id="201", action="qty", qty=2)

    [(kind, moment)] = said.items()
    assert kind == "молоко ферма"
    assert (NOW - moment).days == 4


async def test_a_row_that_is_not_in_the_receipts_says_so(stand):
    with pytest.raises(AssemblyError, match="немає в твоїх чеках"):
        await _ask(stand, id="manual:шафран", action="bought")


async def test_the_word_survives_into_the_next_basket(stand):
    before = await assemble_list(
        stand, llm=None, request=BuildRequest.model_validate({"mode": "week"}), now=NOW
    )
    assert "Хліб Київський" in {line.intent for line in before.lines}

    after = await assemble_list(
        stand,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week"}),
        now=NOW,
        marks={"хліб київський": NOW},
    )

    assert "Хліб Київський" not in {line.intent for line in after.lines}
    assert "Молоко Ферма" in {line.intent for line in after.lines}
    step = next(s for s in after.basket.trace if s.id == "step-needs")
    assert "ще 1 вид не беру" in step.result_summary
    assert step.args["не беру"] == {"ти сказав, що вже купив": 1}


def _weighed(name: str, lager: str, *, days: list[int], grams: int) -> HistoryItem:
    return HistoryItem(
        lager_id=lager,
        name=name,
        unit="г",
        receipts=len(days),
        qty_total=Decimal(grams * len(days)),
        recent_receipts=len(days),
        qty_recent=Decimal(grams * len(days)),
        moments=[NOW - timedelta(days=day) for day in days],
    )


def test_the_row_gives_the_guest_back_his_own_number():
    milk = _item("Молоко Ферма", "1", days=[28, 21, 14, 7], qty=4)
    assert receipts_pantry([milk], now=NOW)[0].running_out is True

    apply_marks([milk], {"молоко ферма": stocked_at(now=NOW, cycle_days=7, typical_qty=4, qty=2)})
    row = receipts_pantry([milk], now=NOW)[0]

    assert row.usual_qty == 4, "питання «скільки взяв» рахується від цього числа"
    assert row.qty == 2
    assert row.running_out is False
    assert "удома ~2 шт" in row.state


def test_the_state_does_not_invent_a_purchase_date():
    milk = _item("Молоко Ферма", "1", days=[28, 21, 14, 7], qty=4)
    apply_marks([milk], {"молоко ферма": stocked_at(now=NOW, cycle_days=7, typical_qty=4, qty=2)})

    assert "тому" not in receipts_pantry([milk], now=NOW)[0].state


def test_a_weighed_kind_is_measured_in_parts_of_a_kilo():
    fillet = _weighed("Філе куряче", "9", days=[28, 21, 14, 7], grams=600)

    usual, step = fillet.usual_amount
    assert (usual, step) == (Decimal("0.6"), Decimal("0.1"))

    apply_marks(
        [fillet],
        {"філе куряче": stocked_at(now=NOW, cycle_days=7, typical_qty=0.6, qty=0.3)},
    )
    row = receipts_pantry([fillet], now=NOW)[0]

    assert row.unit == "кг"
    assert row.usual_qty == Decimal("0.6")
    assert row.qty == Decimal("0.3")


def test_both_sides_measure_the_named_number_by_the_same_stick():
    pieces = _item("Молоко Ферма", "1", days=[28, 21, 14, 7], qty=4)
    weighed = _weighed("Філе куряче", "9", days=[28, 21, 14, 7], grams=600)

    assert [row.usual_qty for row in receipts_pantry([pieces, weighed], now=NOW)] == [
        pieces.usual_amount[0],
        weighed.usual_amount[0],
    ]


async def test_the_cart_does_not_invent_a_date_either(stand):
    built = await assemble_list(
        stand,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week", "shoppingList": ["Хліб Київський"]}),
        now=NOW,
        marks={"хліб київський": NOW},
    )

    [line] = [line for line in built.lines if line.at_home]
    assert line.reason.startswith("з твоїх слів")


def test_a_stock_ahead_holds_for_more_than_one_cycle():
    bread = _item("Хліб Київський", "1", days=[28, 21, 14, 7])
    assert receipts_pantry([bread], now=NOW)[0].running_out is True

    apply_marks(
        [bread], {"хліб київський": stocked_at(now=NOW, cycle_days=7, typical_qty=1, qty=4)}
    )
    row = receipts_pantry([bread], now=NOW)[0]

    assert row.running_out is False
    assert row.days_left == 28, "чотири звичні норми — це чотири цикли по сім днів"
    assert row.qty == 4, "звичне дорівнює одиниці, але сказане гостем — ні"


def test_the_row_names_the_surplus_instead_of_arguing_with_its_own_cycle():
    bread = _item("Хліб Київський", "1", days=[28, 21, 14, 7])
    apply_marks(
        [bread], {"хліб київський": stocked_at(now=NOW, cycle_days=7, typical_qty=1, qty=4)}
    )

    state = receipts_pantry([bread], now=NOW)[0].state

    assert "удома ~4 шт" in state
    assert "запас понад цикл ~7 дн" in state


def test_a_receipt_dated_in_the_future_still_does_not_fill_the_pantry():
    milk = _item("Молоко Ферма", "1", days=[21, 14, -30])

    row = receipts_pantry([milk], now=NOW)[0]

    assert milk.days_since_last(NOW) == 0
    assert row.cycle_days is None
    assert row.left_ratio is None and row.days_left is None


async def test_a_quantity_above_the_usual_one_is_accepted_whole(stand):
    said = await _ask(stand, id="201", action="qty", qty=8)

    [(kind, moment)] = said.items()
    assert kind == "молоко ферма"
    assert (moment - NOW).days == 7, "цикл 7 днів, узято дві норми — один наперед"


async def test_what_was_bought_ahead_does_not_come_back_in_the_next_basket(stand):
    ahead = stocked_at(now=NOW, cycle_days=7, typical_qty=1, qty=4)
    built = await assemble_list(
        stand,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week"}),
        now=NOW,
        marks={"хліб київський": ahead},
    )

    assert "Хліб Київський" not in {line.intent for line in built.lines}
    assert "Молоко Ферма" in {line.intent for line in built.lines}


async def test_a_stock_ahead_named_in_a_list_stays_at_home(stand):
    ahead = stocked_at(now=NOW, cycle_days=7, typical_qty=1, qty=4)
    built = await assemble_list(
        stand,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week", "shoppingList": ["Хліб Київський"]}),
        now=NOW,
        marks={"хліб київський": ahead},
    )

    [line] = [line for line in built.lines if line.at_home]
    assert line.reason.startswith("з твоїх слів")
