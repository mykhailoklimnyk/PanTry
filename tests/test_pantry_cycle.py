from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from komora.agent.basket import (
    AssemblyError,
    HistoryItem,
    apply_cycles,
    apply_marks,
    assemble_list,
    mark_pantry,
    name_cycle,
    pantry_live,
    read_receipts,
    receipts_pantry,
    resolve_kind,
)
from komora.api.schemas import BuildRequest, PantryAdjustment
from komora.core.said import Said
from komora.mcp.client import SilpoMCP

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 8, 26, tzinfo=UTC)

SLOT = {
    "start": "2026-08-26T11:30:00+00:00",
    "end": "2026-08-26T13:00:00+00:00",
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


def test_the_row_does_not_call_the_guests_number_an_estimate():
    bread = _item("Хліб Київський", "1", days=[96, 64, 32, 0])
    apply_cycles([bread], {"хліб київський": 2})

    state = receipts_pantry([bread], now=NOW)[0].state

    assert state.startswith("вистачає на ~2 дн")
    assert "оцінка" not in state


def test_a_marked_row_says_whose_cycle_it_quotes():
    milk = _item("Молоко Ферма", "1", days=[28, 21, 14, 7], qty=4)
    apply_cycles([milk], {"молоко ферма": 8})
    apply_marks([milk], {"молоко ферма": NOW - timedelta(days=4)})

    state = receipts_pantry([milk], now=NOW)[0].state

    assert "цикл ~8 дн" in state


def test_forgetting_the_word_returns_the_estimate_and_not_emptiness():
    bread = _item("Хліб Київський", "1", days=[96, 64, 32, 0])

    apply_cycles([bread], {"хліб київський": 2})
    assert receipts_pantry([bread], now=NOW)[0].cycle_days == 2

    bread.said_cycle = None
    back = receipts_pantry([bread], now=NOW)[0]

    assert back.cycle_days == 32
    assert back.cycle_said is False


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
                            }
                        ],
                    }
                    for day in ("2026-06-20", "2026-06-22", "2026-08-10", "2026-08-12")
                ]
                + [
                    {
                        "createdAt": day,
                        "products": [
                            {
                                "lagerId": 201,
                                "name": "Молоко Ферма",
                                "unit": "шт",
                                "quantity": 1,
                                "price": 53,
                            }
                        ],
                    }
                    for day in ("2026-07-22", "2026-07-29", "2026-08-05", "2026-08-12")
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
                                "name": name,
                                "price": 30,
                                "stock": 10,
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


async def _say(stand: SilpoMCP, **payload: Any) -> tuple[str, int | None]:
    return await name_cycle(stand, PantryAdjustment.model_validate(payload), now=NOW)


async def test_the_word_is_keyed_by_kind_and_not_by_sku(stand: SilpoMCP) -> None:
    assert await _say(stand, id="101", action="cycle", days=2) == ("хліб київський", 2)


async def test_taking_the_word_back_says_so_by_a_none(stand: SilpoMCP) -> None:
    assert await _say(stand, id="101", action="forget_cycle") == ("хліб київський", None)


async def test_a_number_below_one_is_refused_out_loud(stand: SilpoMCP) -> None:
    with pytest.raises(AssemblyError, match="від одного"):
        await _say(stand, id="101", action="cycle", days=0)


async def test_a_kind_that_is_not_in_the_receipts_says_so(stand: SilpoMCP) -> None:
    with pytest.raises(AssemblyError, match="немає в твоїх чеках"):
        await _say(stand, id="manual:шафран", action="cycle", days=2)


async def test_the_refusal_to_mark_now_points_at_the_way_out(stand: SilpoMCP) -> None:
    with pytest.raises(AssemblyError, match="на скільки тобі його вистачає"):
        await mark_pantry(stand, PantryAdjustment.model_validate({"id": "101"}), now=NOW)


async def test_the_named_cycle_survives_into_the_basket(stand: SilpoMCP) -> None:
    before = await assemble_list(
        stand, llm=None, request=BuildRequest.model_validate({"mode": "week"}), now=NOW
    )
    assert {line.intent for line in before.lines} == {"Молоко Ферма"}

    after = await assemble_list(
        stand,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week"}),
        now=NOW,
        cycles={"хліб київський": 2},
    )

    assert "Хліб Київський" in {line.intent for line in after.lines}


async def test_the_word_about_time_still_reaches_the_basket_too(stand: SilpoMCP) -> None:
    built = await assemble_list(
        stand,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week"}),
        now=NOW,
        cycles={"хліб київський": 2},
        marks={"хліб київський": NOW},
    )

    assert {line.intent for line in built.lines} == {"Молоко Ферма"}


async def test_the_named_kind_is_the_last_thing_the_ceiling_cuts(stand: SilpoMCP) -> None:
    built = await assemble_list(
        stand,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week"}),
        now=NOW,
        cycles={"хліб київський": 2},
    )

    step = next(s for s in built.basket.trace if s.id == "step-needs")
    assert "беру 2" in step.result_summary
    assert built.lines[0].intent == "Хліб Київський", (
        "назване гостем стоїть першим у черзі потреб, а не останнім"
    )


async def test_one_reading_serves_both_steps_of_a_single_word(stand: SilpoMCP) -> None:
    paper = await read_receipts(stand, now=NOW)

    row = await resolve_kind(stand, "101", cycles={"хліб київський": 2}, now=NOW, receipts=paper)
    assert row.said_cycle == 2

    after = await pantry_live(stand, place=None, now=NOW, receipts=paper, said=Said(cycles={}))
    bread = next(item for item in after.items if item.label == "Хліб Київський")

    assert bread.cycle_said is False


async def test_a_word_taken_back_stops_showing_in_the_very_same_answer(
    stand: SilpoMCP,
) -> None:
    bread = _item("Хліб Київський", "1", days=[96, 64, 32, 0])
    apply_cycles([bread], {"хліб київський": 2})
    apply_marks([bread], {"хліб київський": NOW})

    apply_cycles([bread], {})
    apply_marks([bread], {})

    assert bread.said_cycle is None
    assert bread.marked_at is None


async def test_a_hand_written_kind_goes_through_naming_next_read(
    stand: SilpoMCP,
) -> None:
    asked: list[list[str]] = []

    class _Namer:
        model = "fake"

        async def decide(self, *, system, user, schema, **_):
            import json as _json

            from komora.agent.llm import Decision, Usage

            names = _json.loads(user)["назви"]
            asked.append(names)
            return Decision(
                data={
                    "kinds": [
                        {"name": name, "intent": name.split()[0].lower(), "subtype": None}
                        for name in names
                    ]
                },
                text="",
                model=self.model,
                usage=Usage(1, 1),
                duration_ms=1,
            )

    paper = await read_receipts(stand, now=NOW)
    pantry = await pantry_live(
        stand,
        llm=_Namer(),
        place=None,
        now=NOW,
        receipts=paper,
        said=Said(listed={"васабі": "васабі"}),
    )

    assert any("васабі" in batch for batch in asked), (
        "дописане слово їде в ТОЙ САМИЙ виклик, що й решта видів"
    )
    written = next(row for row in pantry.items if row.source == "manual")
    assert written.label == "васабі", "підпис лишився тим, що набрав гість"
