import asyncio
import json
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pytest

from komora.agent.basket import (
    GUEST_PICK,
    NO_DECLINE_WHY,
    OVER_QUESTION,
    OVER_RAISE,
    PICK_TOKENS_PER_INTENT,
    SLOT_LOOKAHEAD,
    AssemblyError,
    HistoryItem,
    Naming,
    PlanLine,
    Tracer,
    _order_moment,
    _processing_of,
    _slicing_habit,
    agent_picks,
    assemble_list,
    build_lines,
    considered_options,
    delivery_options_live,
    forget_intents,
    is_service_item,
    kind_key,
    line_quantity,
    manual_item,
    pantry_live,
    related_to,
    slots_query,
    strip_other_processing,
    swap_option,
    terms_from_slot,
    to_cart_line,
)
from komora.agent.kinds import Kind
from komora.agent.llm import Decision, Usage
from komora.api.schemas import BuildRequest, Reason
from komora.config import Settings
from komora.core import slicing
from komora.core.ambiguity import MAX_QUESTIONS
from komora.core.ceilings import MIN_NEEDS
from komora.core.cycles import Keeps
from komora.core.feedback import Changes
from komora.core.location import Location, source_note
from komora.core.location import Source as BranchSource
from komora.core.pantry import manual_id
from komora.core.plan import Refusal
from komora.core.understanding import ANSWER_WAIT_S
from komora.mcp.client import SilpoMCP

SLOT = {
    "start": "2026-08-14T11:30:00+00:00",
    "end": "2026-08-14T13:00:00+00:00",
    "available": True,
    "deliveryType": "DeliveryHome",
    "deliveryCost": 89,
    "deliveryCostMap": [
        {"cost": 59, "fromOrderCost": 1199},
        {"cost": 1, "fromOrderCost": 1699},
    ],
    "minOrderCost": 599,
    "maxWeight": 50,
}


def _product(pid: int, name: str, price: float, stock: int) -> dict:
    return {
        "id": f"00000000-0000-4000-8000-{pid:012d}",
        "name": name,
        "slug": f"slug-{pid}",
        "price": price,
        "oldPrice": None,
        "stock": stock,
        "available": True,
        "image": None,
        "weighted": False,
        "step": 1,
        "displayRatio": "1шт",
        "companyId": "00000000-0000-4000-8000-000000000001",
        "branchId": "00000000-0000-4000-8000-000000000002",
        "externalProductId": pid,
    }


def _with_ratio(product: dict, ratio: str) -> dict:
    return {**product, "displayRatio": ratio}


@pytest.fixture
def mcp(tmp_path) -> SilpoMCP:
    (tmp_path / "silpo_get_time_slots.json").write_text(
        json.dumps({"slots": [SLOT]}), encoding="utf-8"
    )
    (tmp_path / "silpo_get_my_offline_orders.json").write_text(
        json.dumps(
            {
                "orders": [
                    {
                        "createdAt": "2026-07-18",
                        "products": [
                            {
                                "lagerId": 101,
                                "name": "Молоко Ферма 2,5%",
                                "unit": "шт",
                                "quantity": 2,
                                "price": 53,
                            },
                        ],
                    },
                    {
                        "createdAt": "2026-07-25",
                        "products": [
                            {
                                "lagerId": 101,
                                "name": "Молоко Ферма 2,5%",
                                "unit": "шт",
                                "quantity": 2,
                                "price": 53,
                            },
                        ],
                    },
                    {
                        "createdAt": "2026-08-01",
                        "products": [
                            {
                                "lagerId": 101,
                                "name": "Молоко Ферма 2,5%",
                                "unit": "шт",
                                "quantity": 2,
                                "price": 53,
                            },
                        ],
                    },
                    {
                        "createdAt": "2026-08-08",
                        "products": [
                            {
                                "lagerId": 101,
                                "name": "Молоко Ферма 2,5%",
                                "unit": "шт",
                                "quantity": 2,
                                "price": 53,
                            },
                        ],
                    },
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
                        "query": "молоко",
                        "products": [
                            _product(101, "Молоко Ферма 2,5%", 53.49, 20),
                            _product(102, "Молоко Яготинське 2,6%", 75.99, 9),
                        ],
                    },
                    {
                        "query": "шафран",
                        "products": [],
                    },
                    {
                        "query": "кава",
                        "products": [_product(201, "Кава Lavazza", 245.0, 2)],
                    },
                    {
                        "query": "молоко кава",
                        "products": [],
                    },
                    {
                        "query": "ром горілка",
                        "products": [_product(301, "Ром Bacardi Carta Blanca", 599.0, 12)],
                    },
                    {
                        "query": "ром",
                        "products": [_product(301, "Ром Bacardi Carta Blanca", 599.0, 12)],
                    },
                    {
                        "query": "горілка",
                        "products": [_product(302, "Горілка Nemiroff De Luxe", 389.0, 15)],
                    },
                    {
                        "query": "кава мелена",
                        "products": [_product(201, "Кава Lavazza", 245.0, 12)],
                    },
                    {
                        "query": "мелена",
                        "products": [_product(203, "Кава Lavazza мелена", 265.0, 9)],
                    },
                    {
                        "query": "Молоко Ферма 2,5%",
                        "products": [_product(101, "Молоко Ферма 2,5%", 53.49, 20)],
                    },
                ]
            }
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
                        "apartment": "2",
                        "latitude": 49.22,
                        "longitude": 28.45,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "silpo_get_available_delivery_types.json").write_text(
        json.dumps(
            {
                "options": [
                    {"deliveryType": "DeliveryHome", "branchId": BRANCH_FROM_ADDRESS},
                    {"deliveryType": "SelfPickup", "branchId": None},
                ]
            }
        ),
        encoding="utf-8",
    )
    demo = Settings.model_construct()
    return _Recording(settings=demo, fixtures_dir=tmp_path)


BRANCH_FROM_ADDRESS = "00000000-0000-4000-8000-0000000000aa"


class _Recording(SilpoMCP):

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.calls: list[tuple[str, dict]] = []

    async def call(self, tool: str, arguments: dict | None = None):
        self.calls.append((tool, arguments or {}))
        return await super().call(tool, arguments)

    def args_of(self, tool: str) -> dict:
        return next(args for name, args in self.calls if name == tool)


async def test_assemble_from_history_without_agent(mcp):
    request = BuildRequest.model_validate(
        {"mode": "week", "shoppingList": ["молоко", "шафран", "кава"]}
    )
    assembled = await assemble_list(mcp, llm=None, request=request)

    assert assembled.unresolved == ["шафран"]
    basket = assembled.basket
    assert basket.stats.model == "без агента"

    milk = next(line for line in basket.lines if line.external_product_id == "101")
    assert milk.qty == Decimal(2), "звична кількість — з історії (2 чеки по 2)"
    assert milk.at_risk is False

    coffee = next(line for line in basket.lines if line.external_product_id == "201")
    assert coffee.at_risk is True
    assert coffee.chain == [], "малий залишок без ланцюжка"
    assert coffee.mandate is not None and "не підбирати" in coffee.mandate, (
        "без ланцюжка -- «заміни не підбирати» за замовчуванням (11.09)"
    )

    assert basket.total == Decimal("53.49") * 2 + Decimal("245.0")
    assert basket.blockers == ["order.cost.min"], "до мінімуму 599 не добрано"
    assert basket.delivery_cost == Decimal(89)


async def test_every_call_asks_the_branch_from_the_guest_address(mcp):
    request = BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко"]})
    await assemble_list(mcp, llm=None, request=request)

    assert mcp.args_of("silpo_get_time_slots")["branchId"] == BRANCH_FROM_ADDRESS
    assert mcp.args_of("silpo_get_my_offline_orders")["branchId"] == BRANCH_FROM_ADDRESS
    assert mcp.args_of("silpo_find_products_batch")["branchId"] == BRANCH_FROM_ADDRESS


def test_pickup_slot_has_no_delivery_cost_and_that_is_legal():
    terms = terms_from_slot(
        {
            "deliveryCost": None,
            "deliveryCostMap": [],
            "minOrderCost": 199,
            "maxWeight": 0,
        }
    )

    assert terms.base_cost == Decimal(0)
    assert terms.min_order_cost == Decimal("199")
    assert terms.max_weight_kg == Decimal(0)


async def test_slots_are_asked_from_now_not_from_dawn(mcp):
    moment = datetime(2026, 8, 14, 14, 30, 5, 991538, tzinfo=UTC)
    request = BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко"]})
    await assemble_list(mcp, llm=None, request=request, now=moment)

    args = mcp.args_of("silpo_get_time_slots")
    assert args["limit"] == SLOT_LOOKAHEAD
    assert args["start"] == "2026-08-14T14:30:05+00:00"


def test_a_naive_since_is_refused_instead_of_shifting_the_window():
    naive = datetime(2026, 8, 18, 23, 47)  # noqa: DTZ001

    with pytest.raises(ValueError, match="часового поясу"):
        slots_query("branch-1", "DeliveryHome", SLOT_LOOKAHEAD, since=naive)


def test_an_aware_since_keeps_its_offset_in_the_query():
    kyiv = datetime(2026, 8, 18, 23, 47, tzinfo=ZoneInfo("Europe/Kyiv"))

    assert slots_query(None, "SelfPickup", 5, since=kyiv)["start"] == ("2026-08-18T23:47:00+03:00")


async def test_slot_step_names_the_ceiling_it_looked_through(mcp):
    request = BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко"]})
    assembled = await assemble_list(mcp, llm=None, request=request)

    step = next(s for s in assembled.basket.trace if s.id == "step-slots")
    assert "найближчих" in step.result_summary
    assert step.args["limit"] == SLOT_LOOKAHEAD


async def test_slot_step_says_WHY_this_one_and_not_just_that_it_is_valid(mcp):
    request = BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко"]})
    assembled = await assemble_list(mcp, llm=None, request=request)

    step = next(s for s in assembled.basket.trace if s.id == "step-slots")
    assert step.decision == "єдиний вільний з 1 найближчих — вибору не було"


async def test_the_slot_reason_reaches_the_screen_as_the_same_words(mcp):
    request = BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко"]})
    assembled = await assemble_list(mcp, llm=None, request=request)

    step = next(s for s in assembled.basket.trace if s.id == "step-slots")
    assert assembled.basket.slot is not None
    assert assembled.basket.slot.note == step.decision


async def test_a_free_cart_slot_keeps_its_place_and_says_so(tmp_path, mcp):
    (tmp_path / "silpo_get_time_slots.json").write_text(
        json.dumps({"slots": [{**SLOT, "start": "2026-08-14T09:00:00+00:00"}, SLOT]}),
        encoding="utf-8",
    )
    (tmp_path / "silpo_get_my_shopping_cart.json").write_text(
        json.dumps({"shoppingCartId": "00000000-0000-4000-8000-00000000c0de"}),
        encoding="utf-8",
    )
    (tmp_path / "silpo_get_shopping_cart_by_id.json").write_text(
        json.dumps(
            {
                "cart": {
                    "deliveryType": "DeliveryHome",
                    "timeslot": {"start": SLOT["start"], "end": SLOT["end"]},
                    "shipments": [{"branchId": BRANCH_FROM_ADDRESS, "products": []}],
                    "calculation": {"validations": []},
                }
            }
        ),
        encoding="utf-8",
    )
    request = BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко"]})
    assembled = await assemble_list(mcp, llm=None, request=request)

    step = next(s for s in assembled.basket.trace if s.id == "step-slots")
    assert step.decision == "слот уже стояв у кошику і досі вільний — не міняли"
    assert step.tag is None


async def test_no_free_slot_says_it_is_our_window(tmp_path, mcp):
    (tmp_path / "silpo_get_time_slots.json").write_text(
        json.dumps(
            {
                "slots": [
                    {
                        "start": "2026-08-14T06:00:00+00:00",
                        "end": "2026-08-14T08:00:00+00:00",
                        "available": False,
                        "deliveryType": "DeliveryHome",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    request = BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко"]})
    with pytest.raises(AssemblyError) as failure:
        await assemble_list(mcp, llm=None, request=request)

    assert str(failure.value) == (
        "серед 1 найближчих слотів DeliveryHome немає жодного вільного — збирати нема під що"
    )


async def test_trace_says_where_the_branch_came_from(mcp):
    request = BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко"]})
    assembled = await assemble_list(mcp, llm=None, request=request)

    step = next(s for s in assembled.basket.trace if s.id == "step-place")
    assert step.result_summary == source_note(BranchSource.ADDRESS)
    assert step.tag is None, "за адресою — це норма, попереджати нема про що"
    assert all("Соборна" not in step.result_summary for step in assembled.basket.trace), (
        "адреси в трейсі немає: він лягає в журнал прогону на диск"
    )


async def test_without_an_address_the_basket_admits_the_branch_is_not_yours(tmp_path, mcp):
    (tmp_path / "silpo_get_my_delivery_addresses.json").write_text(
        json.dumps({"addresses": []}), encoding="utf-8"
    )
    borrowed = ("silpo_get_time_slots", "silpo_get_my_offline_orders", "silpo_find_products_batch")
    for name in borrowed:
        (tmp_path / f"{name}.json").write_text(
            (mcp._fixtures_dir / f"{name}.json").read_text(encoding="utf-8"), encoding="utf-8"
        )
    cfg = Settings(branch_id="b-config", _env_file=None)  # type: ignore[call-arg]
    stand = _Recording(settings=cfg, fixtures_dir=tmp_path)
    request = BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко"]})
    assembled = await assemble_list(stand, llm=None, request=request, settings=cfg)

    step = next(s for s in assembled.basket.trace if s.id == "step-place")
    assert step.result_summary == source_note(BranchSource.CONFIG)
    assert step.tag == "не за адресою" and step.tag_tone == "warn"
    assert stand.args_of("silpo_find_products_batch")["branchId"] == "b-config"


async def test_known_place_saves_the_two_calls(mcp):
    request = BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко"]})
    where = Location(
        branch_id=BRANCH_FROM_ADDRESS,
        source=BranchSource.ADDRESS,
        branches={"DeliveryHome": BRANCH_FROM_ADDRESS},
    )
    await assemble_list(mcp, llm=None, request=request, place=where)

    tools = [name for name, _ in mcp.calls]
    assert "silpo_get_my_delivery_addresses" not in tools
    assert "silpo_get_available_delivery_types" not in tools
    assert mcp.args_of("silpo_find_products_batch")["branchId"] == BRANCH_FROM_ADDRESS


async def test_delivery_options_ask_each_type_its_own_branch(mcp):
    where = Location(
        branch_id=BRANCH_FROM_ADDRESS,
        source=BranchSource.ADDRESS,
        branches={"DeliveryHome": BRANCH_FROM_ADDRESS, "LongDelivery": "b-long"},
        offered=frozenset({"DeliveryHome", "LongDelivery", "SelfPickup"}),
    )
    options = await delivery_options_live(mcp, place=where)

    asked = {
        args["deliveryTypes"][0]: args["branchId"]
        for name, args in mcp.calls
        if name == "silpo_get_time_slots"
    }
    assert asked["DeliveryHome"] == BRANCH_FROM_ADDRESS
    assert asked["LongDelivery"] == "b-long", "у типу своя філія — питаємо її"

    by_id = {option.id: option for option in options}
    assert by_id["DeliveryHome"].available is True
    express = by_id["DeliveryExpressByPromise"]
    assert express.available is False
    assert express.unavailable_reason == "за твоєю адресою так не возять"
    assert asked["SelfPickup"] == BRANCH_FROM_ADDRESS
    assert by_id["SelfPickup"].available is True

    post = by_id["NovaPoshta"]
    assert post.available is False
    assert "відділення" in (post.unavailable_reason or "")


async def test_delivery_options_without_an_address_do_not_claim_anything(mcp):
    where = Location(branch_id="b-config", source=BranchSource.CONFIG)
    options = await delivery_options_live(
        mcp,
        settings=Settings(branch_id="b-config", _env_file=None),  # type: ignore[call-arg]
        place=where,
    )
    by_id = {option.id: option for option in options}
    assert by_id["DeliveryHome"].available is True
    assert by_id["LongDelivery"].available is True, "не питали — не «недоступно»"


async def test_pantry_is_counted_for_the_guest_branch(mcp):
    await pantry_live(mcp)
    assert mcp.args_of("silpo_get_time_slots")["branchId"] == BRANCH_FROM_ADDRESS
    assert mcp.args_of("silpo_get_my_offline_orders")["branchId"] == BRANCH_FROM_ADDRESS


async def test_assemble_risky_line_carries_mandate(mcp):
    request = BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко"]})
    picks = {"молоко": {"intent": "молоко", "chosen_id": "102", "qty": 1, "reason": "тест"}}
    candidates = {
        "молоко": [
            _product(101, "Молоко Ферма 2,5%", 53.49, 20),
            _product(102, "Молоко Яготинське 2,6%", 75.99, 9),
        ]
    }
    lines, unresolved, _ = build_lines(["молоко"], candidates, {}, picks)
    assert unresolved == []
    line = lines[0]
    assert line.product["externalProductId"] == 102, "вибір агента шанується"
    assert line.risky is True, "залишок 9 — нижче порога"
    assert line.mandate is not None and "Ферма" in line.mandate
    del request


def test_build_lines_falls_back_to_history_match():
    candidates = {"молоко": [_product(101, "Молоко Ферма", 53.49, 20)]}
    hints = {
        "молоко": HistoryItem(
            lager_id="101",
            name="Молоко Ферма",
            unit="шт",
            receipts=4,
            recent_receipts=4,
            qty_recent=Decimal(8),
            qty_total=Decimal(8),
        )
    }
    lines, _, _ = build_lines(["молоко"], candidates, hints, picks={})
    assert lines[0].qty == 2, "без агента кількість — звична з історії"
    assert "історії" in lines[0].reason


def test_a_history_match_the_guest_stopped_buying_is_not_called_a_habit():
    candidates = {"молоко": [_product(101, "Молоко Ферма", 53.49, 20)]}
    stale = {
        "молоко": HistoryItem(
            lager_id="101",
            name="Молоко Ферма",
            unit="шт",
            receipts=4,
            recent_receipts=0,
            qty_total=Decimal(8),
        )
    }

    lines, _, _ = build_lines(["молоко"], candidates, stale, picks={})

    assert "звичне" not in lines[0].reason
    assert lines[0].reason == "брав це раніше, але не останнім часом"


def test_a_single_purchase_is_not_a_habit_either():
    candidates = {"кукурудза": [_product(101, "Кукурудза WellDar", 41.9, 20)]}
    once = {
        "кукурудза": HistoryItem(
            lager_id="101",
            name="Кукурудза WellDar",
            unit="шт",
            receipts=1,
            recent_receipts=1,
            qty_recent=Decimal(1),
            qty_total=Decimal(1),
        )
    }

    lines, _, _ = build_lines(["кукурудза"], candidates, once, picks={})

    assert "звичне" not in lines[0].reason
    assert "чеків" not in lines[0].reason


async def test_empty_list_without_needs_is_a_loud_error(mcp):
    from datetime import UTC, datetime

    now = datetime(2026, 8, 10, tzinfo=UTC)
    with pytest.raises(AssemblyError, match="за циклами зараз нічого не закінчується"):
        await assemble_list(mcp, llm=None, request=BuildRequest(mode="week"), now=now)


async def test_empty_list_builds_from_cycle_needs(mcp):
    from datetime import UTC, datetime

    now = datetime(2026, 8, 20, tzinfo=UTC)
    assembled = await assemble_list(mcp, llm=None, request=BuildRequest(mode="week"), now=now)
    line = assembled.basket.lines[0]
    assert line.external_product_id == "101"
    assert line.reason.value == "cycle"
    assert "закінчується за циклом" in line.explanation
    assert any(step.id == "step-needs" for step in assembled.basket.trace)


def _trust_stand(tmp_path, mcp, now: datetime) -> None:
    from datetime import timedelta

    def when(days: int) -> str:
        return (now - timedelta(days=days)).strftime("%Y-%m-%d")

    def bought(days: int, lager: int, name: str) -> dict:
        return {
            "createdAt": when(days),
            "products": [
                {
                    "lagerId": lager,
                    "name": name,
                    "unit": "шт",
                    "quantity": 1,
                    "price": 50,
                    "catalogProduct": {"price": 50},
                }
            ],
        }

    milk, ice, ketchup = "Молоко Ферма 2,5%", "Морозиво Рудь пломбір", "Кетчуп Торчин"
    (tmp_path / "silpo_get_my_offline_orders.json").write_text(
        json.dumps(
            {
                "orders": [
                    bought(33, 101, milk),
                    bought(26, 101, milk),
                    bought(19, 101, milk),
                    bought(12, 101, milk),
                    bought(171, 301, ice),
                    bought(141, 301, ice),
                    bought(111, 301, ice),
                    bought(76, 301, ice),
                    bought(82, 401, ketchup),
                    bought(80, 401, ketchup),
                    bought(78, 401, ketchup),
                    bought(10, 401, ketchup),
                ]
            }
        ),
        encoding="utf-8",
    )
    batch = json.loads((tmp_path / "silpo_find_products_batch.json").read_text(encoding="utf-8"))
    batch["queries"] += [
        {"query": ice, "products": [_product(301, ice, 89.0, 30)]},
        {"query": ketchup, "products": [_product(401, ketchup, 45.0, 30)]},
    ]
    (tmp_path / "silpo_find_products_batch.json").write_text(json.dumps(batch), encoding="utf-8")
    del mcp


async def test_a_silent_kind_rides_with_its_own_words_not_the_cycles(tmp_path, mcp):
    from datetime import UTC, datetime

    now = datetime(2026, 8, 20, tzinfo=UTC)
    _trust_stand(tmp_path, mcp, now)

    assembled = await assemble_list(mcp, llm=None, request=BuildRequest(mode="week"), now=now)

    lines = {line.name: line for line in assembled.basket.lines}
    assert "закінчується за циклом ~7 дн" in lines["Молоко Ферма 2,5%"].explanation
    ice = lines["Морозиво Рудь пломбір"]
    assert "давно не брав: 76 дн при звичних ~30" in ice.explanation
    assert ice.reason.value == "cycle", "підстава та сама, слова інші"


async def test_a_kind_with_a_jumping_rhythm_never_becomes_a_weekly_need(tmp_path, mcp):
    from datetime import UTC, datetime

    now = datetime(2026, 8, 20, tzinfo=UTC)
    _trust_stand(tmp_path, mcp, now)

    assembled = await assemble_list(mcp, llm=None, request=BuildRequest(mode="week"), now=now)

    assert not any("Кетчуп" in line.name for line in assembled.basket.lines)
    step = next(s for s in assembled.basket.trace if s.id == "step-needs")
    assert "1 давно не брав" in step.result_summary
    assert "ще 1 вид не беру" in step.result_summary
    assert step.args["не беру"] == {"ритм нерівний": 1}
    assert step.args["rare"] == 1


def test_a_rare_kind_stays_in_the_pantry_but_without_a_number():
    from datetime import UTC, datetime, timedelta

    from komora.agent.basket import HistoryItem, receipts_pantry

    now = datetime(2026, 8, 20, tzinfo=UTC)
    ketchup = HistoryItem(
        lager_id="401",
        name="Кетчуп Торчин",
        unit="шт",
        receipts=3,
        qty_total=Decimal(3),
        recent_receipts=3,
        qty_recent=Decimal(3),
        moments=[
            now - timedelta(days=82),
            now - timedelta(days=80),
            now - timedelta(days=78),
            now - timedelta(days=10),
        ],
    )

    row = receipts_pantry([ketchup], now=now)[0]

    assert row.cycle_days is None
    assert row.left_ratio is None and row.days_left is None
    assert row.qty is None
    assert row.running_out is False, "«закінчилось» без циклу — твердження без опори"
    assert "береш нерівно: між покупками від 2 до 68 дн" in row.state
    assert "остання 10 дн тому" in row.state


def test_a_silent_pantry_row_names_the_silence_instead_of_the_cycle():
    from datetime import UTC, datetime, timedelta

    from komora.agent.basket import HistoryItem, receipts_pantry

    now = datetime(2026, 8, 20, tzinfo=UTC)
    ice = HistoryItem(
        lager_id="301",
        name="Морозиво Рудь",
        unit="шт",
        receipts=3,
        qty_total=Decimal(3),
        recent_receipts=3,
        qty_recent=Decimal(3),
        moments=[
            now - timedelta(days=171),
            now - timedelta(days=141),
            now - timedelta(days=111),
            now - timedelta(days=76),
        ],
    )

    row = receipts_pantry([ice], now=now)[0]

    assert row.cycle_days == 30, "число лишається — воно рахується з рівних проміжків"
    assert row.running_out is True, "воно справді скінчилось"
    assert "давно не брав: 76 дн при звичних ~30" in row.state
    assert "мабуть, закінчилось" not in row.state


async def test_stop_words_do_not_become_intents(mcp):
    from datetime import UTC, datetime

    now = datetime(2026, 8, 10, tzinfo=UTC)
    request = BuildRequest.model_validate({"mode": "week", "shoppingList": ["треба купити молоко"]})
    assembled = await assemble_list(mcp, llm=None, request=request, now=now)
    assert [line.external_product_id for line in assembled.basket.lines] == ["101"]
    split_step = next(s for s in assembled.basket.trace if s.id == "step-split")
    assert "→ молоко" in split_step.result_summary, "у розкладанні лише товарне слово"


async def test_space_separated_list_falls_back_to_words(mcp):
    request = BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко кава"]})
    assembled = await assemble_list(mcp, llm=None, request=request)
    ids = {line.external_product_id for line in assembled.basket.lines}
    assert ids == {"101", "201"}, "обидва слова знайшли свій товар"
    split_step = next(s for s in assembled.basket.trace if s.id == "step-split")
    assert "молоко кава" in split_step.result_summary


async def test_an_answer_survives_the_model_rewriting_the_intent(mcp):
    from datetime import UTC, datetime

    now = datetime(2026, 8, 10, tzinfo=UTC)
    request = BuildRequest.model_validate(
        {
            "mode": "week",
            "shoppingList": ["молоко"],
            "answers": [{"intent": "  Молоко ", "skip": True}],
        }
    )

    with pytest.raises(AssemblyError):
        await assemble_list(mcp, llm=None, request=request, now=now)


async def test_a_fuzzy_half_answer_still_splits_the_list(mcp):
    from datetime import UTC, datetime

    now = datetime(2026, 8, 10, tzinfo=UTC)
    request = BuildRequest.model_validate({"mode": "week", "shoppingList": ["ром горілка"]})
    assembled = await assemble_list(mcp, llm=None, request=request, now=now)

    ids = {line.external_product_id for line in assembled.basket.lines}
    assert ids == {"301", "302"}, "обидва наміри гостя доїхали до кошика"
    split = next(s for s in assembled.basket.trace if s.id == "step-split")
    assert "не про фразу" in split.result_summary


async def test_a_narrowing_word_does_not_become_its_own_intent(mcp):
    from datetime import UTC, datetime

    now = datetime(2026, 8, 10, tzinfo=UTC)
    request = BuildRequest.model_validate(
        {"mode": "week", "shoppingList": ["молоко", "кава мелена"]}
    )
    assembled = await assemble_list(mcp, llm=None, request=request, now=now)

    ids = {line.external_product_id for line in assembled.basket.lines}
    assert "203" not in ids, "уточнення не стало власним рядком кошика"
    split = next(s for s in assembled.basket.trace if s.id == "step-split")
    assert "лишив цілими" in split.result_summary
    stray = next(s for s in assembled.basket.trace if s.id == "step-stray")
    assert "зі словом: 1" in stray.result_summary, "фраза чесно каже «не знайшлось»"
    assert stray.args["слова"] == ["кава мелена"]


async def test_a_phrase_with_a_preposition_is_not_scattered_into_ingredients(mcp):
    from datetime import UTC, datetime

    now = datetime(2026, 8, 10, tzinfo=UTC)
    with pytest.raises(AssemblyError, match="шафран"):
        await assemble_list(
            mcp,
            llm=None,
            request=BuildRequest.model_validate(
                {"mode": "week", "shoppingList": ["шафран з молоком"]}
            ),
            now=now,
        )


async def test_nothing_found_is_409_not_empty_basket(mcp):
    from datetime import UTC, datetime

    now = datetime(2026, 8, 10, tzinfo=UTC)
    with pytest.raises(AssemblyError, match="шафран"):
        await assemble_list(
            mcp,
            llm=None,
            request=BuildRequest.model_validate({"mode": "week", "shoppingList": ["шафран"]}),
            now=now,
        )


async def test_a_basket_emptied_by_refusals_says_so_and_not_that_nothing_was_found(mcp):
    from datetime import UTC, datetime

    now = datetime(2026, 8, 10, tzinfo=UTC)
    llm = _AskingLLM(
        [{"intent": "молоко", "chosen_id": "", "qty": 1, "swap": "скляної пляшки тут немає"}]
    )

    with pytest.raises(AssemblyError) as failure:
        await assemble_list(
            mcp,
            llm,
            BuildRequest.model_validate({"shoppingList": ["молоко"]}),
            now=now,
        )

    assert str(failure.value) == (
        "агент не взяв жодної позиції: «молоко» — скляної пляшки тут немає"
        " — зніми правило або назви іншу фасовку"
    )


async def test_unresolved_rides_in_the_basket(mcp):
    request = BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко", "шафран"]})
    assembled = await assemble_list(mcp, llm=None, request=request)
    assert assembled.basket.unresolved == ["шафран"], (
        "нерозпізнаний намір їде гостю словами, а не зникає"
    )


async def test_auto_swap_gives_price_fork_instead_of_approval(mcp):
    request = BuildRequest.model_validate(
        {"mode": "week", "shoppingList": ["кава"], "autoSwap": True}
    )
    assembled = await assemble_list(mcp, llm=None, request=request)
    coffee = assembled.basket.lines[0]
    assert coffee.at_risk is True
    assert coffee.mandate is not None
    assert "марки" not in coffee.mandate
    assert "220,5–269,5 грн" in coffee.mandate, "245 ₴ ±10%, округлено назовні"
    assert not assembled.lines[0].needs_approval


async def test_the_guest_sees_the_same_fork_the_collector_will_read(mcp):
    request = BuildRequest.model_validate(
        {"mode": "week", "shoppingList": ["кава"], "autoSwap": True}
    )
    assembled = await assemble_list(mcp, llm=None, request=request)
    coffee = assembled.basket.lines[0]

    assert coffee.swap_fork is not None
    assert (coffee.swap_fork.low, coffee.swap_fork.high) == (
        Decimal("220.5"),
        Decimal("269.5"),
    )
    assert coffee.swap_fork.per == "шт", "за штуку теж називається (власник 11.09)"
    assert coffee.mandate is not None
    from komora.core.mandate import money

    assert f"{money(coffee.swap_fork.low)}–{money(coffee.swap_fork.high)} грн" in (coffee.mandate)


async def test_without_auto_swap_there_are_no_bounds_to_show(mcp):
    request = BuildRequest.model_validate({"mode": "week", "shoppingList": ["кава"]})
    assembled = await assemble_list(mcp, llm=None, request=request)
    coffee = assembled.basket.lines[0]

    assert coffee.swap_fork is None
    assert assembled.lines[0].needs_approval is False
    assert "не підбирати" in (assembled.lines[0].mandate or "")


def test_a_chain_leaves_no_fork_because_it_is_not_what_governs_the_line():
    whole = _product(201, "Хліб «Рум'янець» цільнозерновий пшеничний", 57.21, 4)
    other = _product(202, "Хліб «Київхліб» цільнозерновий пшеничний", 49.34, 30)

    lines, _, _ = build_lines(["хліб"], {"хліб": [whole, other]}, {}, {}, auto_swap=True)

    [line] = lines
    assert line.chain, "другий товар того самого виду — це ланка"
    assert line.swap_fork is None
    assert line.mandate is not None and "у межах" not in line.mandate


async def test_the_agent_names_the_axis_of_the_swap_and_the_code_adds_the_fork(mcp):
    from komora.agent.basket import assemble_list

    llm = _AskingLLM(
        [
            {
                "intent": "кава",
                "chosen_id": "201",
                "qty": 1,
                "reason": "звичне",
                "swap": "інша мелена арабіка, 225 г",
            }
        ]
    )
    request = BuildRequest.model_validate(
        {"mode": "week", "shoppingList": ["кава"], "autoSwap": True}
    )
    assembled = await assemble_list(mcp, llm=llm, request=request)
    coffee = assembled.basket.lines[0]

    assert coffee.mandate is not None
    assert "інша мелена арабіка, 225 г" in coffee.mandate, "вісь називає агент"
    assert "220,5–269,5 грн" in coffee.mandate, "вилку рахує код і приклеює до тексту"
    assert "марки" not in coffee.mandate

    assert "swap" in llm.system_seen and "інша марка" in llm.system_seen


async def test_steps_that_went_to_the_network_carry_their_time(mcp, monkeypatch):
    import komora.agent.steps.place as place_module
    import komora.agent.steps.shelf as shelf_module
    from komora.agent.kinds import Kind

    real_place = place_module.resolve_place

    async def slow_place(*args, **kwargs):
        await asyncio.sleep(0.03)
        return await real_place(*args, **kwargs)

    async def narrow_with_time(*args, **kwargs):
        return {"молоко": Kind("молоко", "Молоко", "moloko-1", [])}, 214

    monkeypatch.setattr(place_module, "resolve_place", slow_place)
    monkeypatch.setattr(shelf_module, "narrow_kinds", narrow_with_time)
    monkeypatch.setattr(shelf_module, "load_tree", _tree_stub)

    request = BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко"]})
    assembled = await assemble_list(mcp, llm=None, request=request)
    steps = {step.id: step for step in assembled.basket.trace}

    assert steps["step-address"].duration_ms is not None
    assert steps["step-address"].duration_ms >= 25, (
        "крок несе не свій час: підкладено 30 мс походу за адресою, "
        f"а в кроці {steps['step-address'].duration_ms} мс"
    )
    assert steps["step-kind"].duration_ms == 214, "перелік виду везе СВІЙ час"
    assert steps["step-batch"].duration_ms != 214


async def test_a_step_nobody_timed_carries_none_and_not_a_zero(mcp, monkeypatch):
    import komora.agent.steps.shelf as shelf_module

    monkeypatch.setattr(shelf_module, "load_tree", _tree_stub)
    request = BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко"]})
    assembled = await assemble_list(mcp, llm=None, request=request)
    steps = {step.id: step for step in assembled.basket.trace}

    for pure in ("step-weight", "step-plan-done"):
        assert steps[pure].duration_ms is None, f"{pure} ніхто не міряв — це не нуль"

    assert steps["step-economics"].duration_ms is not None

    assert steps["step-batch"].duration_ms is not None, "пошук везе свій час"
    assert steps["step-kinds"].duration_ms is None, "без бази читання не було"
    assert "читання не було" in steps["step-kinds"].result_summary


async def test_a_read_that_failed_is_counted_as_refused_and_not_as_done(mcp):
    request = BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко"]})
    assembled = await assemble_list(mcp, llm=None, request=request)
    done = next(s for s in assembled.basket.trace if s.id == "step-plan-done")

    broke = done.args["кроки"][str(Refusal.BROKE)]
    assert len(broke) == 1 and broke[0].startswith("place.cart — кошик не прочитався")
    assert done.args["кроки"][str(Refusal.EMPTY)] == [
        "decide.pick — без моделі: план зібрано кодом за історією"
    ]
    assert done.args["кроки"][str(Refusal.RULE)] == []
    assert "place.cart" not in done.args["кроки"]["виконано"]
    assert "place.cart" not in done.args["кроки"]["не знадобилось"]
    assert done.tag_tone == "warn"
    assert "place.decide" in done.args["кроки"]["виконано"]
    assert "history.model" in done.args["кроки"]["виконано"]


async def test_the_place_taken_from_session_memory_says_so_instead_of_a_zero(mcp):
    from komora.core.location import Location

    request = BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко"]})
    known = Location(branch_id="00000000-0000-4000-8000-000000000002")
    assembled = await assemble_list(mcp, llm=None, request=request, place=known)
    steps = {step.id: step for step in assembled.basket.trace}

    assert "step-address" not in steps, "місце з пам'яті сесії походу не робить"
    assert "з пам'яті сесії" in steps["step-place"].result_summary


async def test_the_catalogue_map_is_timed_together_with_the_read(mcp, monkeypatch):
    import komora.agent.basket as basket_module
    import komora.agent.steps.shelf as shelf_module

    async def slow_load(_pool, articles):
        await asyncio.sleep(0.03)
        return {article: frozenset({"m-iasni-rulety-4747"}) for article in articles}

    monkeypatch.setattr(shelf_module, "load_tree", _tree_stub)
    monkeypatch.setattr(basket_module.catalog_store, "load", slow_load)

    request = BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко"]})
    assembled = await assemble_list(mcp, llm=None, request=request, pool=_DeadPool())
    step = next(s for s in assembled.basket.trace if s.id == "step-kinds")

    assert step.duration_ms is not None and step.duration_ms > 0


def test_delivery_type_mapping_accepts_demo_ids_and_raw_types():
    from komora.agent.basket import delivery_type_for

    assert delivery_type_for("courier") == "DeliveryHome"
    assert delivery_type_for("pickup") == "SelfPickup"
    assert delivery_type_for("LongDelivery") == "LongDelivery"
    assert delivery_type_for("") == "DeliveryHome"


def test_option_from_slots_takes_numbers_from_api():
    from decimal import Decimal

    from komora.agent.basket import option_from_slots

    option = option_from_slots(
        "DeliveryHome", "кур'єр", "слот 2 години", [SLOT], now=datetime(2026, 8, 26, 12, tzinfo=UTC)
    )
    assert option.cost == Decimal(89)
    assert "вільний слот" in option.note
    assert "найближчий" in option.note
    assert option.min_order == Decimal(599)
    assert option.threshold == Decimal(1699), "поріг — найвищий рівень costMap"
    assert option.max_weight_kg == Decimal(50)
    assert option.available is True


def test_pickup_option_names_its_service_fee():
    from decimal import Decimal

    from komora.agent.basket import option_from_slots

    pickup = {**SLOT, "deliveryType": "SelfPickup", "deliveryCost": None, "serviceFee": 9}
    option = option_from_slots(
        "SelfPickup", "самовивіз", "", [pickup], now=datetime(2026, 8, 26, 12, tzinfo=UTC)
    )
    assert option.cost == Decimal(0)
    assert option.service_fee == Decimal(9)

    courier = option_from_slots(
        "DeliveryHome", "кур'єр", "", [{**SLOT, "serviceFee": None}],
        now=datetime(2026, 8, 26, 12, tzinfo=UTC),
    )
    assert courier.service_fee is None


def test_option_from_slots_without_free_slots_is_honest():
    from komora.agent.basket import option_from_slots

    busy = {**SLOT, "available": False}
    option = option_from_slots(
        "DeliveryHome", "кур'єр", "слот 2 години", [busy], now=datetime(2026, 8, 26, 12, tzinfo=UTC)
    )
    assert option.available is False
    assert option.unavailable_reason == "немає вільних слотів"
    assert option.note == "слот 2 години"
    option_none = option_from_slots(
        "NovaPoshta", "НП", "", [], now=datetime(2026, 8, 26, 12, tzinfo=UTC)
    )
    assert option_none.available is False


def test_history_prefers_recent_window():
    from komora.agent.basket import HistoryItem, history_matches

    old_favorite = HistoryItem(
        lager_id="1",
        name="Огірки солоні відро",
        unit="шт",
        receipts=20,
        qty_total=Decimal(20),
        recent_receipts=0,
    )
    fresh_pick = HistoryItem(
        lager_id="2",
        name="Огірки свіжі",
        unit="кг",
        receipts=3,
        qty_total=Decimal(3),
        recent_receipts=3,
        qty_recent=Decimal(3),
    )
    ranked = history_matches("огірки", [old_favorite, fresh_pick])
    assert ranked[0].lager_id == "2", "3 свіжі чеки важать більше за 20 давніх"
    assert len(ranked) == 2, "агенту віддаються ОБИДВА збіги — вибір за ним"


def test_typical_qty_comes_from_recent_window():
    from komora.agent.basket import HistoryItem

    item = HistoryItem(
        lager_id="1",
        name="Молоко",
        unit="шт",
        receipts=10,
        qty_total=Decimal(40),
        recent_receipts=4,
        qty_recent=Decimal(8),
    )
    assert item.typical_qty == 2, "звична кількість — зі свіжого вікна"


def test_typical_qty_normalizes_grams_to_kilograms():
    from komora.agent.basket import HistoryItem

    pickles = HistoryItem(
        lager_id="9",
        name="Огірки солоні",
        unit="г",
        receipts=2,
        qty_total=Decimal(2000),
        recent_receipts=2,
        qty_recent=Decimal(2000),
    )
    assert pickles.typical_qty == 1, "2 чеки по 1000 г — це 1 кг, а не 1000 шт"


def test_receipts_pantry_estimates_cycle_and_leftover():
    from datetime import UTC, datetime, timedelta

    from komora.agent.basket import HistoryItem, receipts_pantry

    now = datetime(2026, 8, 14, tzinfo=UTC)
    fresh = HistoryItem(
        lager_id="1",
        name="Молоко",
        unit="шт",
        receipts=3,
        qty_total=Decimal(6),
        recent_receipts=3,
        qty_recent=Decimal(6),
        moments=[
            now - timedelta(days=28),
            now - timedelta(days=19),
            now - timedelta(days=10),
            now - timedelta(days=1),
        ],
    )
    out = HistoryItem(
        lager_id="2",
        name="Хліб",
        unit="шт",
        receipts=3,
        qty_total=Decimal(3),
        recent_receipts=3,
        qty_recent=Decimal(3),
        moments=[
            now - timedelta(days=15),
            now - timedelta(days=12),
            now - timedelta(days=9),
            now - timedelta(days=6),
        ],
    )
    single = HistoryItem(lager_id="3", name="Разове", unit="шт", receipts=1)
    bags = HistoryItem(
        lager_id="4",
        name="Пакет Сільпо Пакет з Пакетів 12кг",
        unit="шт",
        receipts=9,
        qty_total=Decimal(9),
        recent_receipts=9,
        qty_recent=Decimal(9),
        moments=[now - timedelta(days=9), now - timedelta(days=2)],
    )

    pantry = receipts_pantry([fresh, out, single, bags], now=now)
    assert [p.id for p in pantry] == ["2", "1"], (
        "що закінчується — згори; разове і службові пакети не в рахунок"
    )
    bread = pantry[0]
    assert bread.running_out is True, "цикл 3 дні, минуло 6 — мабуть, закінчилось"
    assert bread.left_ratio == 0.0 and bread.days_left == 0
    assert bread.qty is None, "хліб беруть по одному — штуки тут не вісь (#62)"
    milk = pantry[1]
    assert milk.running_out is False
    assert milk.days_left == 8 and milk.qty == Decimal(2)
    assert milk.state.startswith("оцінка:"), "це оцінка з чеків, і вона так і називається"


def test_the_pantry_row_carries_its_cycle_as_a_number():
    from datetime import UTC, datetime, timedelta

    from komora.agent.basket import HistoryItem, receipts_pantry

    now = datetime(2026, 8, 21, tzinfo=UTC)
    bread = HistoryItem(
        lager_id="1",
        name="Хліб Київський",
        unit="шт",
        receipts=3,
        qty_total=Decimal(3),
        recent_receipts=3,
        qty_recent=Decimal(3),
        moments=[
            now - timedelta(days=15),
            now - timedelta(days=12),
            now - timedelta(days=9),
            now - timedelta(days=6),
        ],
    )

    row = receipts_pantry([bread], now=now)[0]

    assert row.cycle_days == 3
    assert "цикл ~3 дн" in row.state, "число і слова про той самий цикл не розходяться"


def test_a_weighed_pantry_row_counts_kilograms_not_pieces():
    from datetime import UTC, datetime, timedelta

    from komora.agent.basket import HistoryItem, receipts_pantry

    now = datetime(2026, 8, 20, tzinfo=UTC)
    pork = HistoryItem(
        lager_id="1",
        name="Свинина охолоджена",
        unit="г",
        receipts=3,
        qty_total=Decimal(900),
        recent_receipts=3,
        qty_recent=Decimal(900),
        moments=[
            now - timedelta(days=32),
            now - timedelta(days=22),
            now - timedelta(days=12),
            now - timedelta(days=2),
        ],
    )

    row = receipts_pantry([pork], now=now)[0]

    assert row.unit == "кг"
    assert row.qty == Decimal("0.2") and row.running_out is False


def test_pantry_never_shows_zero_while_the_cycle_is_not_over():
    from datetime import UTC, datetime, timedelta

    from komora.agent.basket import HistoryItem, receipts_pantry

    now = datetime(2026, 8, 19, tzinfo=UTC)
    juice = HistoryItem(
        lager_id="1",
        name="Сік Садочок",
        unit="шт",
        receipts=3,
        qty_total=Decimal(6),
        recent_receipts=3,
        qty_recent=Decimal(6),
        moments=[
            now - timedelta(days=27),
            now - timedelta(days=20),
            now - timedelta(days=13),
            now - timedelta(days=6),
        ],
    )
    row = receipts_pantry([juice], now=now)[0]
    assert row.running_out is False, "цикл 7 днів, минуло 6 — ще не мало закінчитись"
    assert row.qty == Decimal(1), "2 * 0.14 округлилось би в нуль — і це був баг"
    assert row.days_left == 1


def test_a_hand_added_kind_takes_its_unit_from_the_guests_receipts():
    history = [
        HistoryItem(lager_id="7", name="Свинина охолоджена", unit="г", receipts=2),
        HistoryItem(lager_id="8", name="Молоко Ферма 2,5%", unit="шт", receipts=5),
    ]

    row = manual_item("свинина", history)

    assert row.unit == "кг", "грами в чеку — це вага, і рядок каже кілограми"
    assert row.source == "manual"
    assert "Свинина охолоджена" in row.state, "звідки одиниця — тим самим рядком"


def test_a_hand_added_kind_without_receipts_keeps_the_unit_empty():
    row = manual_item("васабі", [HistoryItem(lager_id="1", name="Молоко", unit="шт")])

    assert row.unit == ""
    assert row.qty is None, "гість назвав ВИД, а не облік — кількості не вигадуємо"
    assert row.left_ratio is None and row.days_left is None, "оцінки циклу тут немає"


def test_a_kind_absent_from_receipts_says_why_it_has_no_numbers():
    row = manual_item("васабі", [HistoryItem(lager_id="1", name="Молоко", unit="шт")])

    assert "у чеках «Сільпо» такого немає" in row.state
    assert row.source == "manual"


def test_a_kind_the_pantry_already_tracks_comes_back_as_its_own_row():
    from datetime import UTC, datetime, timedelta

    from komora.agent.basket import receipts_pantry

    now = datetime(2026, 8, 23, tzinfo=UTC)
    milk = HistoryItem(
        lager_id="42",
        name="Молоко Селянське 2,5%",
        unit="шт",
        receipts=3,
        qty_total=Decimal(6),
        recent_receipts=3,
        qty_recent=Decimal(6),
        moments=[
            now - timedelta(days=28),
            now - timedelta(days=19),
            now - timedelta(days=10),
            now - timedelta(days=1),
        ],
    )

    row = manual_item("молоко", [milk], now=now)

    assert row.id == "42", "id виду, а не «manual:молоко» — інакше це другий рядок"
    assert row.source == "receipts"
    assert row.cycle_days is not None and row.left_ratio is not None
    assert row == receipts_pantry([milk], now=now)[0]


def test_a_kind_with_too_few_receipts_names_the_threshold():
    from datetime import UTC, datetime, timedelta

    now = datetime(2026, 8, 23, tzinfo=UTC)
    rare = HistoryItem(
        lager_id="7",
        name="Васабі паста",
        unit="шт",
        receipts=2,
        qty_total=Decimal(2),
        recent_receipts=2,
        qty_recent=Decimal(2),
        moments=[now - timedelta(days=40), now - timedelta(days=5)],
    )

    row = manual_item("васабі", [rare], now=now)

    assert row.id == manual_id(kind_key("васабі")), "вести його ще нема з чого — це рядок гостя"
    assert "васабі" not in row.id
    assert "Васабі паста" in row.state, "звідки одиниця — тим самим рядком"
    assert "брав 2" in row.state and "з 3" in row.state, "поріг названий числом"
    assert row.left_ratio is None, "цикл з одного інтервалу — здогад, а не цикл"


def test_a_pack_unit_is_packs_not_kilograms():
    history = [HistoryItem(lager_id="9", name="Печиво вівсяне", unit="100г", receipts=3)]

    assert manual_item("печиво", history).unit == "уп"


def test_the_word_of_the_guest_matches_by_words_not_by_substring():
    history = [HistoryItem(lager_id="5", name="Фільтри для чаю", unit="шт", receipts=4)]

    assert "такого немає" in manual_item("чай", history).state


def test_chain_from_decision_keeps_the_guests_order():
    from komora.agent.basket import chain_from_decision
    from komora.api.schemas import SwapDecision

    candidates = {
        "1": {"externalProductId": "1", "name": "Поляна Квасова", "price": 39, "stock": 4},
        "2": {"externalProductId": "2", "name": "Моршинська сильногаз", "price": 27, "stock": 40},
    }
    decision = SwapDecision.model_validate(
        {"externalProductId": "9", "policy": "substitute", "chain": ["1", "2"]}
    )
    chain = chain_from_decision(decision, candidates)

    assert [alt.name for alt in chain] == ["Поляна Квасова", "Моршинська сильногаз"]
    assert all(alt.source.value == "manual" for alt in chain), "джерело — рішення гостя"


def test_a_link_that_is_not_on_this_slot_does_not_break_the_chain():
    from komora.agent.basket import chain_from_decision
    from komora.api.schemas import SwapDecision

    candidates = {"2": {"externalProductId": "2", "name": "Моршинська", "price": 27, "stock": 40}}
    decision = SwapDecision.model_validate(
        {"externalProductId": "9", "policy": "substitute", "chain": ["1", "2"]}
    )
    assert [alt.name for alt in chain_from_decision(decision, candidates)] == ["Моршинська"]


def test_skip_is_a_decision_not_a_pending_approval():
    from komora.agent.basket import mandate_for_decision
    from komora.api.schemas import SwapDecision

    skip = SwapDecision.model_validate({"externalProductId": "9", "policy": "skip"})
    mandate, needs_approval = mandate_for_decision(skip, ())
    assert needs_approval is False
    assert mandate and "не підбирати" in mandate

    call = SwapDecision.model_validate({"externalProductId": "9", "policy": "call"})
    assert mandate_for_decision(call, ()) == (None, True)

    silent = SwapDecision.model_validate({"externalProductId": "9", "policy": "substitute"})
    assert mandate_for_decision(silent, ()) is None


def test_a_choice_that_did_not_survive_asks_instead_of_promising():
    from komora.agent.basket import mandate_for_decision
    from komora.api.schemas import SwapDecision

    chosen = SwapDecision.model_validate(
        {"externalProductId": "9", "policy": "substitute", "chain": ["777"]}
    )
    assert mandate_for_decision(chosen, (), risky=True) == (None, True)

    assert mandate_for_decision(chosen, (), risky=False) is None


def test_a_lost_choice_never_becomes_the_same_kind_promise():
    from komora.api.schemas import SwapDecision

    candidates = {"рулет": [_product(401, "Рулет курячий домашній в/г", 719.0, 4)]}
    decision = SwapDecision.model_validate(
        {"externalProductId": "401", "policy": "substitute", "chain": ["900"]}
    )
    lines, _, _ = build_lines(
        ["рулет"],
        candidates,
        {},
        picks={},
        auto_swap=True,
        swaps={"401": decision},
    )
    line = lines[0]
    assert line.decided, "слово гостя позначає рядок: він більше не просить слова (11.09)"
    assert line.risky, "залишок 4 — нижче порога"
    assert line.mandate is None, "у comment не їде нічого — обіцяти нема чого"
    assert line.needs_approval, "рядок чекає слова гостя, а не вигаданого мандата"
    assert "того самого виду" not in (line.mandate or "")


async def test_guest_chain_rides_into_the_mandate_even_on_a_calm_line(mcp):
    request = BuildRequest.model_validate(
        {
            "mode": "week",
            "shoppingList": ["молоко"],
            "swaps": [{"externalProductId": "101", "policy": "substitute", "chain": ["102"]}],
        }
    )
    assembled = await assemble_list(mcp, llm=None, request=request)
    line = next(line for line in assembled.lines if str(line.product["externalProductId"]) == "101")

    assert line.risky is False, "залишок 20 — правило малого залишку тут ні до чого"
    assert line.mandate and "Молоко Яготинське 2,6%" in line.mandate
    assert [alt.name for alt in line.chain] == ["Молоко Яготинське 2,6%"]


async def test_conveyor_marks_still_have_as_at_home(mcp):
    from datetime import UTC, datetime

    request = BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко"]})
    now = datetime(2026, 8, 10, tzinfo=UTC)
    assembled = await assemble_list(mcp, llm=None, request=request, now=now)
    line = assembled.basket.lines[0]
    assert line.reason.value == "at_home"
    assert line.explanation == "схоже, ще є вдома"
    assert assembled.basket.total == Decimal(0), "«ще є вдома» не купується"
    assert any(step.id == "step-pantry" for step in assembled.basket.trace)


def test_pantry_merges_sku_twins_into_kind():
    from datetime import UTC, datetime, timedelta

    from komora.agent.basket import HistoryItem, receipts_pantry

    now = datetime(2026, 8, 14, tzinfo=UTC)
    twin_a = HistoryItem(
        lager_id="1",
        name="Вода мінеральна Моршинська Спортик негазована",
        unit="шт",
        receipts=2,
        qty_total=Decimal(2),
        recent_receipts=2,
        qty_recent=Decimal(2),
        moments=[now - timedelta(days=34), now - timedelta(days=29)],
    )
    twin_b = HistoryItem(
        lager_id="2",
        name="Вода мінеральна Моршинська Спорт н/газ",
        unit="шт",
        receipts=2,
        qty_total=Decimal(2),
        recent_receipts=2,
        qty_recent=Decimal(2),
        moments=[now - timedelta(days=24), now - timedelta(days=19)],
    )
    pantry = receipts_pantry([twin_a, twin_b], now=now)
    assert len(pantry) == 1, "близнюки злились в один вид"
    row = pantry[0]
    assert row.label.startswith("Вода мінеральна"), "показується вид, не SKU"
    assert row.cycle_days == 5
    assert row.running_out is True, "минуло 19 дн при циклі 5"
    assert "давно не брав: 19 дн при звичних ~5" in row.state


def test_pantry_names_rows_by_intent_and_splits_subtypes():
    from datetime import UTC, datetime, timedelta

    from komora.agent.basket import HistoryItem, Naming, receipts_pantry

    now = datetime(2026, 8, 14, tzinfo=UTC)

    def item(lager: str, name: str, days: tuple[int, ...]) -> HistoryItem:
        return HistoryItem(
            lager_id=lager,
            name=name,
            unit="шт",
            receipts=len(days),
            qty_total=Decimal(len(days)),
            recent_receipts=len(days),
            qty_recent=Decimal(len(days)),
            moments=[now - timedelta(days=d) for d in days],
        )

    fillet_a = item("1", "Куряче філе охолоджене", (34, 29))
    fillet_b = item("2", "Філе куряче Наша Ряба", (24, 19))
    soda = item("3", "Напій Geo лимонад", (18, 12, 6))
    mineral = item("4", "Вода мінеральна Регіна", (17, 11, 5))

    names = {
        "куряче філе": Naming("філе куряче"),
        "філе куряче": Naming("філе куряче"),
        "напій geo": Naming("вода газована", "солодка"),
        "вода мінеральна": Naming("вода газована", "мінеральна"),
    }
    pantry = receipts_pantry([fillet_a, fillet_b, soda, mineral], now=now, names=names)

    labels = sorted(row.label for row in pantry)
    assert labels == [
        "вода газована · мінеральна",
        "вода газована · солодка",
        "філе куряче",
    ], "філе злилось за наміром, підтипи води — окремі рядки"
    fillet = next(row for row in pantry if row.label == "філе куряче")
    assert fillet.cycle_days == 5, "цикл рахується по злитому наміру"
    assert "~5" in fillet.state


def test_the_kind_rule_proves_but_never_refutes():
    from komora.agent.basket import name_proves_kind

    assert name_proves_kind("рулет", "Рулет курячий «Алан» домашній в/г")
    assert not name_proves_kind("рулет", "Вермішель Мівіна з куркою 59,2 г")
    assert name_proves_kind("сир", "Сир твердий Джюгас 12 міс.")
    assert name_proves_kind("сир", "Сир кисломолочний Яготинський 9%")
    assert not name_proves_kind("банан", "Банан «Премія» сушений цілий")
    assert name_proves_kind("банан", "Банан «Премія» сушений цілий", like="Банан сушений ваговий")


def test_chain_never_adds_processing():
    candidates = {
        "банан": [
            _product(301, "Банан", 65.42, 3),
            _product(302, "Банан «Премія» сушений цілий", 37.99, 20),
            _product(303, "Банан чіпси смажені", 45.0, 15),
        ]
    }
    lines, _, _ = build_lines(["банан"], candidates, {}, picks={})
    line = lines[0]
    assert line.risky, "залишок 3 — нижче порога"
    assert line.chain == (), "сушений і чіпси відсіяні: краще «не підбирати», ніж крінж-заміна"
    assert line.needs_approval is False
    assert "не підбирати" in (line.mandate or ""), "без ланцюжка -- «заміни не підбирати» (11.09)"


def test_chain_keeps_processing_the_guest_already_buys():
    candidates = {
        "банан сушений": [
            _product(302, "Банан «Премія» сушений цілий", 37.99, 2),
            _product(304, "Банан сушений «Спокуса»", 33.0, 20),
        ]
    }
    lines, _, _ = build_lines(["банан сушений"], candidates, {}, picks={})
    assert len(lines[0].chain) == 1
    assert "Спокуса" in lines[0].chain[0].name


def _cherry() -> dict[str, list[dict]]:
    return {
        "Томат черрі": [
            _with_ratio(_product(605375, "Томат черрі", 154.0, 32), "250г"),
            _with_ratio(_product(998781, "Томат Ріана черрі рожевий", 92.99, 4), "250г"),
            _with_ratio(_product(979172, "Томат Гордій Черрі", 71.99, 62), "250г"),
            _with_ratio(_product(872219, "Томат Green Agro черрі на гілці", 77.99, 54), "250г"),
        ]
    }


def test_without_an_answer_from_the_agent_the_code_takes_the_cheapest_per_unit():
    plan, _, _ = build_lines(["Томат черрі"], _cherry(), {}, picks={})

    assert plan[0].product["externalProductId"] == 979172
    assert plan[0].reason == "найдешевший за спільну одиницю під намір"


def test_mixed_units_leave_the_shops_own_order_alone():
    candidates = _cherry()
    candidates["Томат черрі"][2] = _product(979172, "Томат Гордій Черрі", 71.99, 62)

    plan, _, _ = build_lines(["Томат черрі"], candidates, {}, picks={})

    assert plan[0].product["externalProductId"] == 605375
    assert plan[0].reason == "перший доступний під намір"


def test_an_article_from_any_receipt_beats_the_head_of_the_search():
    owned = {"979172": _bought("Томат Гордій Черрі", "шт", "1", lager="979172")}

    plan, _, _ = build_lines(["Томат черрі"], _cherry(), {}, picks={}, owned=owned)

    assert plan[0].product["externalProductId"] == 979172
    assert "звичне з історії" in plan[0].reason


def test_the_receipts_axis_does_not_reach_past_the_guests_own_word():
    candidates = {
        "Спрайт": [
            _product(1, "Напій Sprite 0,5л", 30.0, 10),
            _product(2, "Зубна паста Splat", 99.0, 10),
        ]
    }
    owned = {"2": _bought("Зубна паста Splat", "шт", "1", lager="2")}

    plan, _, _ = build_lines(["Спрайт"], candidates, {}, picks={}, owned=owned)

    assert plan[0].product["externalProductId"] == 1


def test_the_price_axis_cuts_inside_the_kind_not_across_the_whole_set():
    candidates = {
        "Рулет курячий": [
            _with_ratio(_product(1, "Рулет карамельний", 40.0, 10), "300г"),
            _with_ratio(_product(2, "Рулет Глобино з індички", 120.0, 10), "300г"),
        ]
    }
    hints = {"Рулет курячий": _bought("Рулет курячий Алан", "г", "300", lager="900")}
    kinds = {"900": frozenset({"m-iasni-rulety"}), "2": frozenset({"m-iasni-rulety"})}

    plan, _, _ = build_lines(["Рулет курячий"], candidates, hints, picks={}, kinds=kinds)

    assert plan[0].product["externalProductId"] == 2, "дешевший, але чужого виду, не береться"


def test_without_the_map_the_price_axis_stays_exactly_as_it_was():
    candidates = {
        "Рулет курячий": [
            _with_ratio(_product(1, "Рулет карамельний", 40.0, 10), "300г"),
            _with_ratio(_product(2, "Рулет Глобино з індички", 120.0, 10), "300г"),
        ]
    }
    hints = {"Рулет курячий": _bought("Рулет курячий Алан", "г", "300", lager="900")}

    plan, _, _ = build_lines(["Рулет курячий"], candidates, hints, picks={})

    assert plan[0].product["externalProductId"] == 1


def test_the_receipts_axis_stops_at_the_kind_word():
    candidates = {
        "Слива чорна": [
            _product(11, "Слива", 39.99, 10),
            _product(12, "Нектарин", 89.99, 10),
        ]
    }
    owned = {"12": _bought("Нектарин", "шт", "1", lager="12")}

    plan, _, _ = build_lines(["Слива чорна"], candidates, {}, picks={}, owned=owned)

    assert plan[0].product["externalProductId"] == 11
    assert plan[0].reason != "звичне з історії — 3 чеків"


def test_a_pick_without_a_reason_code_says_the_agent_chose_it():
    picks = {"Томат черрі": {"chosen_id": "605375", "qty": 1}}

    plan, _, _ = build_lines(["Томат черрі"], _cherry(), {}, picks=picks)

    assert plan[0].product["externalProductId"] == 605375
    assert plan[0].reason == "обрав агент під намір"


def test_the_guests_own_chip_says_the_guest_chose_it():
    picks = {"Томат черрі": {"chosen_id": "605375", "qty": 1, "why": GUEST_PICK}}

    plan, _, _ = build_lines(["Томат черрі"], _cherry(), {}, picks=picks)

    assert plan[0].reason == "ти обрав це сам під намір"


def test_the_guests_own_article_still_beats_the_price():
    hints = {"Томат черрі": _bought("Томат Ріана черрі рожевий", "шт", "1", lager="998781")}

    plan, _, _ = build_lines(["Томат черрі"], _cherry(), hints, picks={})

    assert plan[0].product["externalProductId"] == 998781
    assert "звичне з історії" in plan[0].reason


def _cfg(**extra) -> Settings:
    return Settings(_env_file=None, **extra)


async def test_run_log_is_written_only_when_asked(mcp, tmp_path, monkeypatch):
    monkeypatch.setattr("komora.agent.basket.RUNS_DIR", tmp_path / "runs")
    request = BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко"]})

    silent = await assemble_list(mcp, llm=None, request=request, settings=_cfg())
    assert silent.run_log is None
    assert not (tmp_path / "runs").exists(), "живий режим сам по собі журналу не просить"

    asked = await assemble_list(mcp, llm=None, request=request, settings=_cfg(run_log=True))
    assert asked.run_log is not None and asked.run_log.exists()


async def test_run_log_holds_the_whole_run_not_a_summary(mcp, tmp_path, monkeypatch):
    monkeypatch.setattr("komora.agent.basket.RUNS_DIR", tmp_path / "runs")
    assembled = await assemble_list(
        mcp,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко"]}),
        settings=_cfg(run_log=True),
    )
    assert assembled.run_log is not None
    saved = json.loads(assembled.run_log.read_text(encoding="utf-8"))
    assert saved["request"]["shoppingList"] == ["молоко"]
    assert saved["basket"]["lines"], "кошик у журналі, а не лише запит"
    assert saved["basket"]["trace"], "трейс теж: без нього «чому» не відновити"
    assert saved["recorded_at"]


async def test_run_log_failure_does_not_kill_the_build(mcp, tmp_path, monkeypatch):
    blocked = tmp_path / "не-каталог"
    blocked.write_text("", encoding="utf-8")
    monkeypatch.setattr("komora.agent.basket.RUNS_DIR", blocked)
    assembled = await assemble_list(
        mcp,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко"]}),
        settings=_cfg(run_log=True),
    )
    assert assembled.run_log is None
    assert assembled.basket.lines, "кошик зібрано попри мертвий журнал"


def test_checkout_service_lines_never_become_intents():
    assert is_service_item("Послуга доставки") is True
    assert is_service_item("Послуга Підписка Плюхс 1 місяць") is True
    assert is_service_item("Пакет біорозкладний 3кг 958358") is True
    assert is_service_item("В скарбничку") is True

    assert is_service_item("Піцета по-італійськи") is False
    assert is_service_item("Набір цукерок Kilojo Манго фруктових сушених") is False
    assert is_service_item("Контейнер для зберігання Sp Berner 680мл") is False
    assert is_service_item("") is False


async def test_broad_word_is_narrowed_by_its_kind(tmp_path, mcp):
    for name in (
        "silpo_get_time_slots",
        "silpo_get_my_offline_orders",
        "silpo_find_products_batch",
        "silpo_get_my_delivery_addresses",
        "silpo_get_available_delivery_types",
    ):
        (tmp_path / f"{name}.json").write_text(
            (mcp._fixtures_dir / f"{name}.json").read_text(encoding="utf-8"), encoding="utf-8"
        )
    (tmp_path / "silpo_get_categories.json").write_text(
        json.dumps(
            {
                "categories": [{"id": "c1", "title": "Молоко", "slug": "moloko-253"}],
                "meta": {"total": 1},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "silpo_get_products.json").write_text(
        json.dumps({"products": [_product(999, "Молоко Селянське 2,5%", 41.9, 12)]}),
        encoding="utf-8",
    )
    stand = _Recording(settings=Settings.model_construct(), fixtures_dir=tmp_path)

    request = BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко"]})
    assembled = await assemble_list(stand, llm=None, request=request)

    step = next(s for s in assembled.basket.trace if s.id == "step-kind")
    assert "звужено видом: 1" in step.result_summary and "+1" in step.result_summary
    assert any("Молоко" in said for said in step.args["види"])

    args = stand.args_of("silpo_get_products")
    assert args["category"] == "moloko-253"
    assert args["branchId"] == BRANCH_FROM_ADDRESS, "вид питаємо на філії за адресою"


def test_processing_markers_come_from_the_live_shelf():
    assert _processing_of("Свинячі реберця PREMIA Party line в маринаді охолоджені")
    assert _processing_of("Шашлик із свинини Львівський напівфабрикат кулінарний")
    assert _processing_of("Ковбаски гриль #ЦЕМ'ЯСО Баварські свинячі охолоджені")
    assert _processing_of("Свинячий смалець фермерський")

    assert _processing_of("Свинина корейське барбекю в'ялена")
    assert _processing_of("Свинина Biovela рвана томлена, 780 г")

    assert not _processing_of("Свиняча грудинка охолоджена"), "сире лишається сирим"
    assert not _processing_of("Свинячий окіст для шніцеля охолоджений")
    assert not _processing_of("Свинина, стейк з ошийка охолоджений фасований")


async def test_kind_empty_on_this_slot_is_not_the_same_as_not_found(tmp_path, mcp):
    for name in (
        "silpo_get_time_slots",
        "silpo_get_my_offline_orders",
        "silpo_get_my_delivery_addresses",
        "silpo_get_available_delivery_types",
    ):
        (tmp_path / f"{name}.json").write_text(
            (mcp._fixtures_dir / f"{name}.json").read_text(encoding="utf-8"), encoding="utf-8"
        )
    (tmp_path / "silpo_find_products_batch.json").write_text(
        json.dumps(
            {
                "queries": [
                    {"query": "молоко", "products": [_product(101, "Молоко", 53.49, 20)]},
                    {"query": "свинина", "products": []},
                    {"query": "Молоко", "products": [_product(101, "Молоко", 53.49, 20)]},
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "silpo_get_categories.json").write_text(
        json.dumps(
            {
                "categories": [
                    {"id": "c1", "title": "Свинина", "slug": "svynyna-4413"},
                    {"id": "c2", "title": "Молоко", "slug": "moloko-253"},
                ],
                "meta": {"total": 2},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "silpo_get_products.json").write_text(
        json.dumps({"products": []}), encoding="utf-8"
    )
    stand = _Recording(settings=Settings.model_construct(), fixtures_dir=tmp_path)

    request = BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко", "свинина"]})
    assembled = await assemble_list(stand, llm=None, request=request)

    assert assembled.basket.not_collected == ["свинина"]
    assert "свинина" not in assembled.basket.unresolved, (
        "інші слова тут не допоможуть — порада мусить бути про слот"
    )


async def test_dried_banana_does_not_pass_for_fresh_when_the_kind_is_empty(tmp_path, mcp):
    for name in (
        "silpo_get_time_slots",
        "silpo_get_my_offline_orders",
        "silpo_get_my_delivery_addresses",
        "silpo_get_available_delivery_types",
    ):
        (tmp_path / f"{name}.json").write_text(
            (mcp._fixtures_dir / f"{name}.json").read_text(encoding="utf-8"), encoding="utf-8"
        )
    (tmp_path / "silpo_find_products_batch.json").write_text(
        json.dumps(
            {
                "queries": [
                    {"query": "молоко", "products": [_product(101, "Молоко", 53.49, 20)]},
                    {
                        "query": "банан",
                        "products": [_product(202, "Банан сушений цілий", 37.99, 9)],
                    },
                    {"query": "Молоко", "products": [_product(101, "Молоко", 53.49, 20)]},
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "silpo_get_categories.json").write_text(
        json.dumps(
            {
                "categories": [
                    {"id": "c1", "title": "Банани", "slug": "banany-4792"},
                    {"id": "c2", "title": "Молоко", "slug": "moloko-253"},
                ],
                "meta": {"total": 2},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "silpo_get_products.json").write_text(
        json.dumps({"products": []}), encoding="utf-8"
    )
    stand = _Recording(settings=Settings.model_construct(), fixtures_dir=tmp_path)

    request = BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко", "банан"]})
    assembled = await assemble_list(stand, llm=None, request=request)

    names = [line.name for line in assembled.basket.lines]
    assert not any("сушен" in name.lower() for name in names), (
        "сушений банан не є свіжим і не має їхати мовчки"
    )
    assert assembled.basket.not_collected == ["банан"]


def test_the_gate_works_only_where_the_tree_proved_the_kind():
    candidates = {
        "банан": [{"externalProductId": "202", "name": "Банан сушений цілий"}],
        "огірки": [{"externalProductId": "303", "name": "Огірки солоні"}],
    }
    narrowed = {
        "банан": Kind("банан", "Банани", "banany-4792", []),
        "огірки": Kind(
            "огірки", "Огірки", "ogirky-1", [{"externalProductId": "404", "name": "Огірок"}]
        ),
    }

    emptied = strip_other_processing(candidates, narrowed)

    assert emptied == ["банан"]
    assert "банан" not in candidates
    assert candidates["огірки"] == [{"externalProductId": "303", "name": "Огірки солоні"}], (
        "вид не порожній — рішення за агентом, не за фільтром"
    )


def test_intent_that_names_the_processing_keeps_it():
    candidates = {"банан сушений": [{"externalProductId": "202", "name": "Банан сушений цілий"}]}
    narrowed = {"банан сушений": Kind("банан сушений", "Банани", "banany-4792", [])}

    assert strip_other_processing(candidates, narrowed) == []
    assert len(candidates["банан сушений"]) == 1


class _AskingLLM:

    model = "fake-model"

    def __init__(self, picks: list[dict]) -> None:
        self.picks = picks
        self.payloads: list[dict] = []
        self.system_seen = ""

    async def decide(self, *, system, user, schema, schema_name="decision", max_tokens=2048, **_):
        from komora.agent.llm import Decision, Usage

        self.payloads.append(json.loads(user))
        self.system_seen = system
        return Decision(
            data={"picks": self.picks},
            text="",
            model=self.model,
            usage=Usage(1, 1),
            duration_ms=1,
        )


def _clarify_stand(tmp_path, mcp, *, products: list[dict] | None = None) -> _Recording:
    for name in (
        "silpo_get_time_slots",
        "silpo_get_my_offline_orders",
        "silpo_get_my_delivery_addresses",
        "silpo_get_available_delivery_types",
    ):
        (tmp_path / f"{name}.json").write_text(
            (mcp._fixtures_dir / f"{name}.json").read_text(encoding="utf-8"), encoding="utf-8"
        )
    (tmp_path / "silpo_find_products_batch.json").write_text(
        json.dumps(
            {
                "queries": [
                    {
                        "query": "сир",
                        "products": [_with_ratio(_product(301, "Сир Гауда", 99.0, 5), "200г")],
                    },
                    {
                        "query": "сир твердий 50%",
                        "products": [_product(303, "Сир твердий 50%", 129.0, 4)],
                    },
                    {
                        "query": "сироп кленовий",
                        "products": [_product(305, "Топінг кленовий", 89.0, 7)],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "silpo_get_categories.json").write_text(
        json.dumps(
            {
                "categories": [
                    {"id": "c1", "title": "Сири", "slug": "syry"},
                    {"id": "c2", "title": "Молочні продукти", "slug": "dairy"},
                    {
                        "id": "c3",
                        "title": "Сир кисломолочний",
                        "slug": "syr-kyslo",
                        "parentId": "c2",
                    },
                ],
                "meta": {"total": 3},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "silpo_get_products.json").write_text(
        json.dumps(
            {
                "products": products
                if products is not None
                else [_with_ratio(_product(302, "Сир Гауда 45%", 99.0, 5), "350г")]
            }
        ),
        encoding="utf-8",
    )
    return _Recording(settings=Settings.model_construct(), fixtures_dir=tmp_path)


async def test_readings_and_unit_price_reach_the_agent(tmp_path, mcp):
    stand = _clarify_stand(tmp_path, mcp)
    llm = _AskingLLM([{"intent": "сир", "chosen_id": "301", "qty": 1, "reason": "звичний"}])

    await assemble_list(
        stand, llm, BuildRequest.model_validate({"mode": "week", "shoppingList": ["сир"]})
    )

    picked = next(p for p in llm.payloads if "наміри" in p)
    intent = next(item for item in picked["наміри"] if item["намір"] == "сир")
    assert intent["прочитання"] == ["Сир кисломолочний"]
    assert [candidate["за_100г"] for candidate in intent["кандидати"]] == [49.5, 28.29]


async def test_an_asked_intent_does_not_travel_to_the_basket(tmp_path, mcp):
    stand = _clarify_stand(tmp_path, mcp)
    llm = _AskingLLM(
        [
            {
                "intent": "сир",
                "chosen_id": "",
                "qty": 1,
                "reason": "два різні види",
                "ask": "Сир твердий чи кисломолочний?",
            }
        ]
    )

    assembled = await assemble_list(
        stand, llm, BuildRequest.model_validate({"mode": "week", "shoppingList": ["сир"]})
    )

    basket = assembled.basket
    assert [q.intent for q in basket.questions] == ["сир"]
    assert basket.questions[0].question == "Сир твердий чи кисломолочний?"
    assert basket.lines == []
    assert "сир" not in basket.unresolved, "питання — не «не знайшлось»"
    step = next(s for s in basket.trace if s.id == "step-ask")
    assert "чекає на уточнення: 1 питання" in step.result_summary
    assert any("сир" in asked for asked in step.args["питання"])


async def test_chips_carry_live_prices_of_the_slot(tmp_path, mcp):
    stand = _clarify_stand(tmp_path, mcp)
    llm = _AskingLLM(
        [
            {
                "intent": "сир",
                "chosen_id": "",
                "qty": 1,
                "reason": "двояко",
                "ask": "Сир кисломолочний чи твердий?",
            }
        ]
    )

    assembled = await assemble_list(
        stand, llm, BuildRequest.model_validate({"mode": "week", "shoppingList": ["сир"]})
    )

    options = assembled.basket.questions[0].options
    assert [option.title for option in options] == ["Сир кисломолочний"]
    assert options[0].slug == "syr-kyslo"
    assert options[0].price_from == Decimal("99.0")
    assert options[0].count == 1
    assert options[0].query is None


async def test_a_question_without_an_axis_gets_candidates_instead_of_chips(tmp_path, mcp):
    stand = _clarify_stand(tmp_path, mcp)
    llm = _AskingLLM(
        [{"intent": "сир", "chosen_id": "", "qty": 1, "reason": "двояко", "ask": "Який сир?"}]
    )

    assembled = await assemble_list(
        stand, llm, BuildRequest.model_validate({"mode": "week", "shoppingList": ["сир"]})
    )

    question = assembled.basket.questions[0]
    assert question.options == []
    assert [pick.name for pick in question.picks] == ["Сир Гауда", "Сир Гауда 45%"]
    step = next(item for item in assembled.basket.trace if item.id == "step-ask")
    assert step.args["знято не на осі питання"] == 1
    assert any(
        "жодного: відповідають самі кандидати" in said for said in step.args["звідки варіанти"]
    )


async def test_the_model_names_the_options_and_the_shelf_signs_them(tmp_path, mcp):
    stand = _clarify_stand(tmp_path, mcp)
    llm = _AskingLLM(
        [
            {
                "intent": "сир",
                "chosen_id": "",
                "qty": 1,
                "reason": "двояко",
                "ask": "Твердий чи кисломолочний?",
                "ask_options": ["сир твердий 50%", "сир"],
            }
        ]
    )

    assembled = await assemble_list(
        stand, llm, BuildRequest.model_validate({"mode": "week", "shoppingList": ["сир"]})
    )

    options = assembled.basket.questions[0].options
    assert [option.title for option in options] == ["сир твердий 50%"]
    assert options[0].slug == ""
    assert options[0].query == "сир твердий 50%"
    assert options[0].price_from == Decimal("129.0")
    step = next(item for item in assembled.basket.trace if item.id == "step-ask")
    assert step.args["знято повторів слова"] == 1
    assert any("1 від моделі" in said for said in step.args["звідки варіанти"])


async def test_the_guests_own_phrase_survives_the_stray_cut(tmp_path, mcp):
    stand = _clarify_stand(tmp_path, mcp)

    assembled = await assemble_list(
        stand,
        None,
        BuildRequest.model_validate(
            {
                "mode": "week",
                "shoppingList": ["сироп"],
                "answers": [{"intent": "сироп", "query": "сироп кленовий"}],
            }
        ),
    )

    line = next(line for line in assembled.lines if line.intent == "сироп")
    assert line.product["name"] == "Топінг кленовий"
    step = next(item for item in assembled.basket.trace if item.id == "step-answers")
    assert "гість обрав варіант: 1 намір" in step.result_summary
    assert step.args["варіанти"] == {"сироп": "сироп кленовий"}


async def test_an_empty_node_never_becomes_a_chip(tmp_path, mcp):
    stand = _clarify_stand(tmp_path, mcp, products=[])
    llm = _AskingLLM(
        [{"intent": "сир", "chosen_id": "", "qty": 1, "reason": "двояко", "ask": "Який сир?"}]
    )

    assembled = await assemble_list(
        stand, llm, BuildRequest.model_validate({"mode": "week", "shoppingList": ["сир"]})
    )

    assert assembled.basket.questions[0].options == []


async def test_the_answer_is_a_decision_not_a_hint(tmp_path, mcp):
    stand = _clarify_stand(tmp_path, mcp)
    llm = _AskingLLM(
        [
            {
                "intent": "сир",
                "chosen_id": "301",
                "qty": 1,
                "reason": "обрано за відповіддю",
                "ask": "Який сир?",
            }
        ]
    )

    assembled = await assemble_list(
        stand,
        llm,
        BuildRequest.model_validate(
            {
                "mode": "week",
                "shoppingList": ["сир"],
                "answers": [{"intent": "сир", "slug": "syr-kyslo"}],
            }
        ),
    )

    assert assembled.basket.questions == [], "питати вдруге означає «тебе не почули»"
    assert [line.name for line in assembled.basket.lines] == ["Сир Гауда"]
    picked = next(p for p in llm.payloads if "наміри" in p)
    intent = next(item for item in picked["наміри"] if item["намір"] == "сир")
    assert intent["уточнення_гостя"] == "Сир кисломолочний"
    assert stand.args_of("silpo_get_products")["category"] == "syr-kyslo"


async def test_free_text_answer_becomes_its_own_query(tmp_path, mcp):
    stand = _clarify_stand(tmp_path, mcp)
    llm = _AskingLLM(
        [{"intent": "сир", "chosen_id": "303", "qty": 1, "reason": "за словами гостя"}]
    )

    assembled = await assemble_list(
        stand,
        llm,
        BuildRequest.model_validate(
            {
                "mode": "week",
                "shoppingList": ["сир"],
                "answers": [{"intent": "сир", "text": "твердий 50%"}],
            }
        ),
    )

    searched = [
        args["products"] for tool, args in stand.calls if tool == "silpo_find_products_batch"
    ]
    assert ["сир твердий 50%"] in searched
    assert [line.name for line in assembled.basket.lines] == ["Сир твердий 50%"]
    step = next(s for s in assembled.basket.trace if s.id == "step-answers")
    assert "гість уточнив словами: 1 намір" in step.result_summary
    assert step.args["слова"] == {"сир": "твердий 50%"}


async def test_i_do_not_need_it_removes_the_intent(tmp_path, mcp):
    stand = _clarify_stand(tmp_path, mcp)
    llm = _AskingLLM([])

    with pytest.raises(AssemblyError):
        await assemble_list(
            stand,
            llm,
            BuildRequest.model_validate(
                {
                    "mode": "week",
                    "shoppingList": ["сир"],
                    "answers": [{"intent": "сир", "skip": True}],
                }
            ),
        )

    searched = [
        query
        for tool, args in stand.calls
        if tool == "silpo_find_products_batch"
        for query in args["products"]
    ]
    assert "сир" not in searched, "шукати те, від чого гість щойно відмовився, — зайвий виклик"


_WITH_NEEDS = datetime(2026, 8, 20, tzinfo=UTC)


class _QueueLLM(_AskingLLM):

    def __init__(self, picks: list[dict], expendable: list[dict] | None = None) -> None:
        super().__init__(picks)
        self.expendable = expendable or []

    async def decide(self, *, system, user, schema, schema_name="decision", max_tokens=2048, **_):
        decision = await super().decide(
            system=system, user=user, schema=schema, max_tokens=max_tokens
        )
        decision.data["expendable"] = self.expendable
        return decision


async def test_the_limit_rides_to_the_agent_as_a_condition(mcp):
    llm = _QueueLLM([{"intent": "кава", "chosen_id": "201", "qty": 1, "reason": "звична"}])

    await assemble_list(
        mcp,
        llm,
        BuildRequest.model_validate({"mode": "week", "shoppingList": ["кава"], "budget": 800}),
        now=_WITH_NEEDS,
    )

    payload = llm.payloads[-1]
    assert payload["межа_кошика"] == 800
    sources = {item["намір"]: item["джерело"] for item in payload["наміри"]}
    assert sources["кава"] == "список гостя"
    assert sources["Молоко Ферма 2,5%"] == "потреби з циклів"


async def test_the_code_cuts_by_the_agents_queue_and_names_the_price(mcp):
    llm = _QueueLLM(
        [
            {"intent": "кава", "chosen_id": "201", "qty": 1, "reason": "звична"},
            {"intent": "Молоко Ферма 2,5%", "chosen_id": "101", "qty": 2, "reason": "звичне"},
        ],
        expendable=[{"intent": "Молоко Ферма 2,5%", "why": "брав два тижні тому, ще постоїть"}],
    )

    assembled = await assemble_list(
        mcp,
        llm,
        BuildRequest.model_validate({"mode": "week", "shoppingList": ["кава"], "budget": 300}),
        now=_WITH_NEEDS,
    )

    basket = assembled.basket
    assert [line.external_product_id for line in basket.lines] == ["201"]
    assert [item.intent for item in basket.trimmed] == ["Молоко Ферма 2,5%"]
    cut = basket.trimmed[0]
    assert cut.name == "Молоко Ферма 2,5%"
    assert cut.price == Decimal("106.98"), "ціна рядка, а не одиниці: 53,49 × 2"
    assert cut.reason == "брав два тижні тому, ще постоїть"
    step = next(s for s in basket.trace if s.id == "step-budget")
    assert "зняв 1: Молоко Ферма 2,5%" in step.result_summary
    assert step.args["зняв"] == ["Молоко Ферма 2,5%"]
    assert step.tag.startswith("нижче цілі на "), step.tag
    assert basket.total == sum(
        (line.price * line.qty for line in basket.lines if line.reason != Reason.AT_HOME),
        Decimal(0),
    )


async def test_the_cut_under_the_budget_reports_itself_as_the_settle_the_plan_asked_for(mcp):
    llm = _QueueLLM(
        [
            {"intent": "кава", "chosen_id": "201", "qty": 1, "reason": "звична"},
            {"intent": "Молоко Ферма 2,5%", "chosen_id": "101", "qty": 2, "reason": "звичне"},
        ],
        expendable=[{"intent": "Молоко Ферма 2,5%", "why": "брав два тижні тому, ще постоїть"}],
    )

    assembled = await assemble_list(
        mcp,
        llm,
        BuildRequest.model_validate({"mode": "week", "shoppingList": ["кава"], "budget": 300}),
        now=_WITH_NEEDS,
    )

    assert [item.intent for item in assembled.basket.trimmed] == ["Молоко Ферма 2,5%"]
    done = next(s for s in assembled.basket.trace if s.id == "step-plan-done")
    assert done.args["кроки"]["виконано"].count("economy.settle") == 2
    assert "economy.settle" not in done.args["кроки"]["не знадобилось"]


async def test_a_basket_that_fits_leaves_the_second_settle_honestly_unneeded(mcp):
    llm = _QueueLLM(
        [
            {"intent": "кава", "chosen_id": "201", "qty": 1, "reason": "звична"},
            {"intent": "Молоко Ферма 2,5%", "chosen_id": "101", "qty": 2, "reason": "звичне"},
        ],
        expendable=[{"intent": "Молоко Ферма 2,5%", "why": "брав два тижні тому, ще постоїть"}],
    )

    assembled = await assemble_list(
        mcp,
        llm,
        BuildRequest.model_validate({"mode": "week", "shoppingList": ["кава"], "budget": 3000}),
        now=_WITH_NEEDS,
    )

    assert assembled.basket.trimmed == []
    done = next(s for s in assembled.basket.trace if s.id == "step-plan-done")
    assert "economy.settle" in done.args["кроки"]["не знадобилось"]
    assert done.args["кроки"]["виконано"].count("economy.settle") == 1


def test_the_names_of_what_was_cut_fit_the_phrase_or_give_way_to_a_number():
    from komora.agent.basket import _named_within

    assert _named_within(["Кава", "Хліб"], budget=40) == "Кава, Хліб"
    assert _named_within(["Кава", "Хліб", "Сир"], budget=12) == "Кава, Хліб і ще 1"
    assert _named_within(["Пюре Mark&Mart запечене яблучко-морквочка"], budget=20) == ""
    assert _named_within([], budget=40) == ""


def _two_needs_stand(tmp_path, mcp) -> _Recording:
    orders = {
        "orders": [
            {
                "createdAt": day,
                "products": [
                    {
                        "lagerId": 101,
                        "name": "Молоко Ферма 2,5%",
                        "unit": "шт",
                        "quantity": 2,
                        "price": 53,
                    },
                    {
                        "lagerId": 201,
                        "name": "Кава Lavazza",
                        "unit": "шт",
                        "quantity": 1,
                        "price": 245,
                    },
                ],
            }
            for day in ("2026-07-18", "2026-07-25", "2026-08-01", "2026-08-08")
        ]
    }
    (tmp_path / "silpo_get_my_offline_orders.json").write_text(json.dumps(orders), encoding="utf-8")
    batch = json.loads((tmp_path / "silpo_find_products_batch.json").read_text(encoding="utf-8"))
    batch["queries"].append(
        {"query": "Кава Lavazza", "products": [_product(201, "Кава Lavazza", 245.0, 20)]}
    )
    (tmp_path / "silpo_find_products_batch.json").write_text(json.dumps(batch), encoding="utf-8")
    return mcp


_MANY_NEEDS = 10


def _crowded_stand(tmp_path, mcp) -> _Recording:
    pairs = [(300 + i, f"Товар {i}") for i in range(_MANY_NEEDS)]
    orders = {
        "orders": [
            {
                "createdAt": day,
                "products": [
                    {
                        "lagerId": lager,
                        "name": name,
                        "unit": "шт",
                        "quantity": 1,
                        "price": 40 + index,
                    }
                ],
            }
            for index, (lager, name) in enumerate(pairs)
            for day in ("2026-07-18", "2026-07-25", "2026-08-01", "2026-08-08")
        ]
    }
    (tmp_path / "silpo_get_my_offline_orders.json").write_text(json.dumps(orders), encoding="utf-8")
    batch = json.loads((tmp_path / "silpo_find_products_batch.json").read_text(encoding="utf-8"))
    batch["queries"].extend(
        {"query": name, "products": [_product(lager, name, float(40 + index), 20)]}
        for index, (lager, name) in enumerate(pairs)
    )
    (tmp_path / "silpo_find_products_batch.json").write_text(json.dumps(batch), encoding="utf-8")
    return mcp


async def test_the_ceiling_shows_its_derivation_not_just_its_result(tmp_path, mcp):
    assembled = await assemble_list(
        _crowded_stand(tmp_path, mcp),
        llm=None,
        request=BuildRequest.model_validate({"mode": "week"}),
        now=_WITH_NEEDS,
    )

    step = next(s for s in assembled.basket.trace if s.id == "step-needs")
    assert step.decision is not None
    assert "це твій звичний кошик з чеків, а не число з коду" in step.decision
    derivation = step.args["як порахована стеля"]
    assert "медіана 1, p75 1, беру 6" in derivation
    assert "нижня межа стелі, не p75" in derivation, (
        "стелю поставили межі, а не чеки — і це інша відповідь на «з чого»"
    )


async def test_what_the_ceiling_postponed_carries_its_price(tmp_path, mcp):
    assembled = await assemble_list(
        _crowded_stand(tmp_path, mcp),
        llm=None,
        request=BuildRequest.model_validate({"mode": "week"}),
        now=_WITH_NEEDS,
    )

    postponed = assembled.basket.postponed
    assert len(postponed) == _MANY_NEEDS - MIN_NEEDS
    assert all(item.refillable for item in postponed)
    assert all(item.estimate is not None and item.estimate > 0 for item in postponed)
    by_intent = {item.intent: item for item in postponed}
    assert by_intent["Товар 9"].estimate == Decimal("49.00")


async def test_an_ambiguous_intent_is_postponed_but_not_refillable(tmp_path, mcp):
    words = ["сир", "хліб", "риба", "олія"]
    batch = json.loads((tmp_path / "silpo_find_products_batch.json").read_text(encoding="utf-8"))
    batch["queries"].extend(
        {"query": word, "products": [_product(400 + i, word.title(), 50.0, 20)]}
        for i, word in enumerate(words)
    )
    (tmp_path / "silpo_find_products_batch.json").write_text(json.dumps(batch), encoding="utf-8")
    llm = _AskingLLM(
        [
            {
                "intent": word,
                "chosen_id": str(400 + i),
                "qty": 1,
                "reason": "звичне",
                "ask": f"який саме {word}?",
            }
            for i, word in enumerate(words)
        ]
    )

    assembled = await assemble_list(
        mcp,
        llm,
        BuildRequest.model_validate({"mode": "week", "shoppingList": words}),
        now=datetime(2026, 8, 10, tzinfo=UTC),
    )

    basket = assembled.basket
    assert len(basket.questions) == MAX_QUESTIONS
    beyond = [item for item in basket.postponed if "стелю" in item.reason]
    assert [item.intent for item in beyond] == ["олія"]
    assert beyond[0].refillable is False
    assert beyond[0].estimate is None, "ціни немає — і вигадувати її нема з чого"


async def test_the_limit_does_not_cut_a_basket_that_fits_into_it(mcp):
    llm = _QueueLLM(
        [{"intent": "кава", "chosen_id": "201", "qty": 1, "reason": "звична"}],
        expendable=[{"intent": "Молоко Ферма 2,5%", "why": "ще постоїть"}],
    )

    assembled = await assemble_list(
        mcp,
        llm,
        BuildRequest.model_validate({"mode": "week", "shoppingList": ["кава"], "budget": 3000}),
        now=_WITH_NEEDS,
    )

    basket = assembled.basket
    assert basket.trimmed == [], "у межі — нічого не знімаємо, хоч черга і є"
    assert basket.total <= Decimal(3000)
    step = next(s for s in basket.trace if s.id == "step-budget")
    assert "у межі" in step.result_summary
    assert step.tag.startswith("нижче цілі на "), step.tag
    assert step.tag_tone == "muted"
    assert "НИЖЧЕ коридору" in step.result_summary


async def test_the_queue_is_not_walked_further_than_the_limit_requires(tmp_path, mcp):
    stand = _two_needs_stand(tmp_path, mcp)
    llm = _QueueLLM(
        [
            {"intent": "Кава Lavazza", "chosen_id": "201", "qty": 1, "reason": "звична"},
            {"intent": "Молоко Ферма 2,5%", "chosen_id": "101", "qty": 2, "reason": "звичне"},
        ],
        expendable=[
            {"intent": "Кава Lavazza", "why": "пачки вистачає на довше"},
            {"intent": "Молоко Ферма 2,5%", "why": "ще постоїть"},
        ],
    )

    assembled = await assemble_list(
        stand,
        llm,
        BuildRequest.model_validate({"mode": "week", "budget": 300}),
        now=_WITH_NEEDS,
    )

    basket = assembled.basket
    assert [item.intent for item in basket.trimmed] == ["Кава Lavazza"]
    assert [line.name for line in basket.lines] == ["Молоко Ферма 2,5%"], (
        "після зняття кави 106,98 грн уже в межі — далі черга не йде"
    )


async def test_what_the_guest_named_is_never_cut(mcp):
    llm = _QueueLLM(
        [{"intent": "кава", "chosen_id": "201", "qty": 1, "reason": "найдорожче в кошику"}],
        expendable=[{"intent": "кава", "why": "найдорожче в кошику"}],
    )

    assembled = await assemble_list(
        mcp,
        llm,
        BuildRequest.model_validate({"mode": "week", "shoppingList": ["кава"], "budget": 100}),
        now=datetime(2026, 8, 10, tzinfo=UTC),
    )

    basket = assembled.basket
    assert [line.external_product_id for line in basket.lines] == ["201"]
    assert basket.trimmed == []
    step = next(s for s in basket.trace if s.id == "step-budget")
    assert "добір не вліз за цінами" in step.result_summary
    assert basket.fill_cut, "докинуте нами і зняте нами ж називає себе поіменно"
    assert all(item.name and item.price is not None for item in basket.fill_cut)


def _named_over_the_limit() -> _QueueLLM:
    return _QueueLLM(
        [
            {"intent": "кава", "chosen_id": "201", "qty": 1, "reason": "найдорожче в кошику"},
            {"intent": "молоко", "chosen_id": "101", "qty": 1, "reason": "звичне"},
        ],
        expendable=[{"intent": "кава", "why": "найдорожче в кошику"}],
    )


async def _over_limit_run(mcp, answer, **extra):
    return await assemble_list(
        mcp,
        _named_over_the_limit(),
        BuildRequest.model_validate(
            {"mode": "week", "shoppingList": ["кава", "молоко"], "budget": 100, **extra}
        ),
        now=datetime(2026, 8, 10, tzinfo=UTC),
        answer_of=answer,
    )


async def test_the_over_limit_question_names_the_row_the_sum_and_the_new_target(mcp):
    asked: list[tuple[str, float]] = []

    async def _silent(question_id: str, seconds: float) -> str | None:
        asked.append((question_id, seconds))
        return None

    assembled = await _over_limit_run(mcp, _silent)

    step = next(s for s in assembled.basket.trace if s.id == "step-over")
    assert step.question is not None
    assert asked and asked[0][0] == OVER_QUESTION and asked[0][1] > 0
    labels = [option.label for option in step.question.options]
    assert any(label.startswith("зняти Кава") and "лишиться" in label for label in labels)
    raised = next(o for o in step.question.options if o.id == OVER_RAISE)
    assert raised.target is not None
    assert Decimal(str(raised.target)) * Decimal("1.1") >= assembled.basket.total


async def test_the_over_limit_answer_cuts_the_row_the_guest_chose(mcp):

    async def _cut(question_id: str, seconds: float) -> str | None:
        return "cut:201"

    assembled = await _over_limit_run(mcp, _cut)

    assert [line.name for line in assembled.basket.lines] == ["Молоко Ферма 2,5%"]
    assert [item.intent for item in assembled.basket.trimmed] == ["кава"]
    assert assembled.basket.trimmed[0].reason == "ти обрав зняти це під межу"
    said = [s for s in assembled.basket.trace if s.id == "step-over"][-1]
    assert "знімаю з кошика" in said.result_summary and said.tag == "відповідь"


async def test_the_raised_target_rides_in_the_basket_not_only_in_the_trace(mcp):

    async def _raise(question_id: str, seconds: float) -> str | None:
        return OVER_RAISE

    assembled = await _over_limit_run(mcp, _raise)

    basket = assembled.basket
    assert basket.budget is not None and basket.budget > 100
    assert basket.total <= basket.budget * Decimal("1.1")
    assert [line.external_product_id for line in basket.lines] == ["201", "101"], (
        "піднята ціль нічого не знімає — вона лише розширює коридор"
    )


async def test_an_over_limit_question_without_an_answer_leaves_the_basket_as_it_was(mcp):

    async def _silent(question_id: str, seconds: float) -> str | None:
        return None

    assembled = await _over_limit_run(mcp, _silent)

    said = [s for s in assembled.basket.trace if s.id == "step-over"][-1]
    assert "не дочекався" in said.result_summary and said.tag == "без відповіді"
    assert [line.external_product_id for line in assembled.basket.lines] == ["201", "101"]


async def test_without_a_channel_the_over_limit_question_is_not_asked_at_all(mcp):
    assembled = await assemble_list(
        mcp,
        _named_over_the_limit(),
        BuildRequest.model_validate(
            {"mode": "week", "shoppingList": ["кава", "молоко"], "budget": 100}
        ),
        now=datetime(2026, 8, 10, tzinfo=UTC),
    )

    assert all(step.id != "step-over" for step in assembled.basket.trace)
    assert [line.external_product_id for line in assembled.basket.lines] == ["201", "101"]


async def test_a_row_the_guest_added_by_hand_never_becomes_an_option(mcp):

    async def _silent(question_id: str, seconds: float) -> str | None:
        return None

    assembled = await _over_limit_run(mcp, _silent, keep=["201"])

    assert all(step.id != "step-over" for step in assembled.basket.trace)


async def test_over_the_limit_is_said_out_loud_with_the_difference(mcp):
    llm = _QueueLLM([{"intent": "кава", "chosen_id": "201", "qty": 1, "reason": "звична"}])

    assembled = await assemble_list(
        mcp,
        llm,
        BuildRequest.model_validate({"mode": "week", "shoppingList": ["кава"], "budget": 100}),
        now=datetime(2026, 8, 10, tzinfo=UTC),
    )

    basket = assembled.basket
    assert basket.budget == Decimal("100"), "межа їде назад: повзунок живе своїм життям"
    step = next(s for s in basket.trace if s.id == "step-budget")
    assert "вище межі" in step.result_summary
    assert f"на {basket.total - Decimal('100.00')} грн" in step.result_summary
    assert step.tag_tone == "warn"


async def test_the_limit_that_ate_everything_says_so(mcp):
    llm = _QueueLLM(
        [{"intent": "Молоко Ферма 2,5%", "chosen_id": "101", "qty": 2, "reason": "звичне"}],
        expendable=[{"intent": "Молоко Ферма 2,5%", "why": "ще постоїть"}],
    )

    with pytest.raises(AssemblyError, match="не влізло в межу"):
        await assemble_list(
            mcp, llm, BuildRequest.model_validate({"mode": "week", "budget": 40}), now=_WITH_NEEDS
        )


async def test_without_a_limit_there_is_no_budget_step(mcp):
    assembled = await assemble_list(
        mcp,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week", "shoppingList": ["кава"]}),
        now=datetime(2026, 8, 10, tzinfo=UTC),
    )
    assert not any(step.id == "step-budget" for step in assembled.basket.trace)


def test_the_pick_schema_accepts_the_fields_the_agent_really_sends():
    from komora.agent.basket import pick_schema
    from komora.agent.llm.validation import validate

    validate(
        {
            "picks": [
                {"intent": "кава", "chosen_id": "201", "qty": 1, "why": "звичне"},
                {"intent": "сир", "chosen_id": "", "qty": 1, "ask": "Який?"},
            ],
            "expendable": [{"intent": "олія", "why": "брав раз за півроку"}],
        },
        pick_schema(with_queue=True),
        model="test",
    )


def _rotating_history(tmp_path, mcp, *, kinds: int, per_receipt: int, now: datetime) -> None:
    from datetime import timedelta

    groups = [
        list(range(start, min(start + per_receipt, kinds)))
        for start in range(0, kinds, per_receipt)
    ]
    day = now - timedelta(days=3 * (len(groups) * 4 - 1) + 3 * len(groups) + 1)
    orders = []
    for round_no in range(4):
        for group in groups:
            orders.append(
                {
                    "createdAt": (day + timedelta(days=len(orders) * 3)).strftime("%Y-%m-%d"),
                    "products": [
                        {
                            "lagerId": 900 + i,
                            "name": f"Товар {i}",
                            "unit": "шт",
                            "quantity": 1,
                            "price": 10,
                        }
                        for i in group
                    ],
                }
            )
        assert round_no >= 0
    (tmp_path / "silpo_get_my_offline_orders.json").write_text(
        json.dumps({"orders": orders}), encoding="utf-8"
    )
    batch = json.loads((tmp_path / "silpo_find_products_batch.json").read_text(encoding="utf-8"))
    batch["queries"] += [
        {"query": f"Товар {i}", "products": [_product(900 + i, f"Товар {i}", 10.0, 30)]}
        for i in range(kinds)
    ]
    (tmp_path / "silpo_find_products_batch.json").write_text(json.dumps(batch), encoding="utf-8")


async def test_the_needs_ceiling_says_how_much_it_cut(tmp_path, mcp):
    _rotating_history(tmp_path, mcp, kinds=20, per_receipt=5, now=datetime(2026, 8, 20, tzinfo=UTC))

    assembled = await assemble_list(
        mcp, llm=None, request=BuildRequest(mode="week"), now=datetime(2026, 8, 20, tzinfo=UTC)
    )

    step = next(s for s in assembled.basket.trace if s.id == "step-needs")
    assert "беру 6 видів: 6 за циклом" in step.result_summary
    assert "ще 14 видів не беру" in step.result_summary
    assert step.args["не беру"] == {"не влізло в звичний кошик": 14}
    assert len(step.args["беру"]) == 6
    assert step.tag == "+6 зі 20"
    assert step.tag_tone == "warn", "обрізане — це попередження, а не звіт"


async def test_the_ceiling_grows_with_the_guests_own_basket(tmp_path, mcp):
    _rotating_history(
        tmp_path, mcp, kinds=20, per_receipt=16, now=datetime(2026, 8, 20, tzinfo=UTC)
    )

    assembled = await assemble_list(
        mcp, llm=None, request=BuildRequest(mode="week"), now=datetime(2026, 8, 20, tzinfo=UTC)
    )

    step = next(s for s in assembled.basket.trace if s.id == "step-needs")
    assert "беру 16" in step.result_summary
    assert "скільки брати за раз — 16 видів" in (step.decision or "")
    assert "твій звичний кошик з чеків" in (step.decision or "")


async def test_the_fourth_ambiguous_intent_does_not_ride_in_silently(tmp_path, mcp):
    stand = _clarify_stand(tmp_path, mcp)
    batch = json.loads((tmp_path / "silpo_find_products_batch.json").read_text(encoding="utf-8"))
    batch["queries"] += [
        {"query": word, "products": [_product(400 + i, f"{word.capitalize()} Товар", 20.0, 10)]}
        for i, word in enumerate(("хліб", "молоко", "олія"))
    ]
    (tmp_path / "silpo_find_products_batch.json").write_text(json.dumps(batch), encoding="utf-8")
    llm = _QueueLLM(
        [
            {"intent": word, "chosen_id": "", "qty": 1, "reason": "двояко", "ask": f"Який {word}?"}
            for word in ("сир", "хліб", "молоко", "олія")
        ]
    )

    assembled = await assemble_list(
        stand,
        llm,
        BuildRequest.model_validate(
            {"mode": "week", "shoppingList": ["сир", "хліб", "молоко", "олія"]}
        ),
    )

    basket = assembled.basket
    assert len(basket.questions) == 3, "стеля питань лишається"
    asked = {q.intent for q in basket.questions}
    silent = [line.explanation_detail for line in basket.lines]
    assert basket.lines == [], f"поза стелею вибір не робиться мовчки: {silent}"
    step = next(s for s in basket.trace if s.id == "step-ask")
    assert "поза стелею" in step.result_summary
    assert len(asked) == 3


async def _tree_stub(*args, **kwargs):
    from komora.core.dictionary import Dictionary, Node

    return Dictionary([Node("milk", "Молоко", None, "moloko-1")])


class _DeadPool:

    @asynccontextmanager
    async def connection(self, **_: Any):
        raise RuntimeError("бази немає")
        yield  # pragma: no cover


async def test_kept_article_survives_a_rebuild(mcp):
    now = datetime(2026, 8, 10, tzinfo=UTC)
    request = BuildRequest.model_validate({"mode": "week", "keep": ["101"]})

    assembled = await assemble_list(mcp, llm=None, request=request, now=now)

    assert [line.external_product_id for line in assembled.basket.lines] == ["101"]


async def test_kept_article_is_not_an_auto_need(mcp):
    now = datetime(2026, 8, 10, tzinfo=UTC)
    request = BuildRequest.model_validate({"mode": "week", "keep": ["101"]})

    assembled = await assemble_list(mcp, llm=None, request=request, now=now)

    assert assembled.lines[0].auto_need is False


async def test_unknown_kept_article_is_named_not_dropped(mcp):
    now = datetime(2026, 8, 10, tzinfo=UTC)
    request = BuildRequest.model_validate(
        {"mode": "week", "shoppingList": ["молоко"], "keep": ["999"]}
    )

    assembled = await assemble_list(mcp, llm=None, request=request, now=now)

    assert [item.intent for item in assembled.basket.postponed] == ["999"]
    assert "руками" in assembled.basket.postponed[0].reason


def test_kept_article_is_never_substituted_by_a_lookalike():
    options = {"молоко": [_product(101, "Молоко Ферма 2,5%", 53.49, 20)]}

    plan, unresolved, _ = build_lines(["молоко"], options, {}, {}, must_match={"молоко": "999"})

    assert plan == []
    assert unresolved == ["молоко"]


def test_kept_article_picks_exactly_its_own_product():
    options = {
        "молоко": [
            _product(101, "Молоко Ферма 2,5%", 53.49, 20),
            _product(102, "Молоко Яготинське 2,6%", 75.99, 9),
        ]
    }

    plan, _, _ = build_lines(["молоко"], options, {}, {}, must_match={"молоко": "102"})

    assert str(plan[0].product["externalProductId"]) == "102"


def test_rejected_candidates_stay_with_the_line():
    options = {
        "молоко": [
            _product(101, "Молоко Ферма 2,5%", 53.49, 20),
            _product(102, "Молоко Яготинське 2,6%", 75.99, 9),
        ]
    }

    plan, _, _ = build_lines(["молоко"], options, {}, {})

    assert [str(p["externalProductId"]) for p in plan[0].considered] == ["102"]
    assert plan[0].considered_total == 2


def test_the_count_stays_honest_above_the_ceiling():
    from komora.agent.basket import MAX_CONSIDERED

    many = [_product(200 + n, f"Товар {n}", 10.0 + n, 5) for n in range(MAX_CONSIDERED + 3)]

    plan, _, _ = build_lines(["щось"], {"щось": many}, {}, {})

    assert len(plan[0].considered) == MAX_CONSIDERED
    assert plan[0].considered_total == len(many)


def test_a_single_candidate_means_there_was_no_choice():
    plan, _, _ = build_lines(
        ["молоко"], {"молоко": [_product(101, "Молоко Ферма 2,5%", 53.49, 20)]}, {}, {}
    )

    assert plan[0].considered == ()
    assert plan[0].considered_total == 1


def test_every_built_line_has_at_least_one_candidate():
    options = {
        "молоко": [_product(101, "Молоко Ферма 2,5%", 53.49, 20)],
        "хліб": [
            _product(201, "Хліб Київхліб", 32.99, 12),
            _product(202, "Хліб Дарницький", 22.50, 4),
        ],
    }

    plan, _, _ = build_lines(["молоко", "хліб"], options, {}, {})

    assert len(plan) == 2
    assert all(line.considered_total >= 1 for line in plan)


def test_the_chosen_one_is_not_among_the_rejected():
    options = {
        "молоко": [
            _product(101, "Молоко Ферма 2,5%", 53.49, 20),
            _product(102, "Молоко Яготинське 2,6%", 75.99, 9),
        ]
    }

    plan, _, _ = build_lines(["молоко"], options, {}, {}, must_match={"молоко": "102"})

    chosen = str(plan[0].product["externalProductId"])
    assert chosen not in [str(p["externalProductId"]) for p in plan[0].considered]


def test_candidates_reach_the_contract_line():
    options = {
        "молоко": [
            _product(101, "Молоко Ферма 2,5%", 53.49, 20),
            _product(102, "Молоко Яготинське 2,6%", 75.99, 9),
        ]
    }
    plan, _, _ = build_lines(["молоко"], options, {}, {})

    line = to_cart_line(plan[0])

    assert [option.name for option in line.considered] == ["Молоко Яготинське 2,6%"]
    assert line.considered_total == 2


def test_weighted_stock_is_not_a_whole_number():
    option = swap_option(
        {"externalProductId": 7, "name": "Філе лосося", "price": 272.46, "stock": 2.5}
    )

    assert float(option.stock) == 2.5


def test_ratio_survives_a_number_from_the_api():
    assert (
        swap_option({"externalProductId": 7, "name": "X", "price": 1, "displayRatio": 100}).ratio
        == "100"
    )


def test_a_broken_candidate_costs_one_row_not_the_whole_basket():
    line = PlanLine(
        intent="риба",
        product=_product(701, "Філе лосося", 272.46, 3),
        qty=Decimal(1),
        reason="звичне",
        from_history=None,
        considered=({"externalProductId": 702, "price": 10},),
        considered_total=2,
    )

    assert considered_options(line) == []


def test_a_broken_candidate_does_not_pass_silently(capsys):
    line = PlanLine(
        intent="риба",
        product=_product(701, "Філе лосося", 272.46, 3),
        qty=Decimal(1),
        reason="звичне",
        from_history=None,
        considered=({"externalProductId": 702, "price": 10},),
        considered_total=2,
    )

    considered_options(line)

    assert "considered_skipped" in capsys.readouterr().out


def test_the_line_still_builds_when_a_candidate_is_broken():
    line = PlanLine(
        intent="риба",
        product=_product(701, "Філе лосося", 272.46, 3),
        qty=Decimal(1),
        reason="звичне",
        from_history=None,
        considered=(
            {"externalProductId": 702, "price": 10},
            {"externalProductId": 703, "name": "Форель", "price": 300, "stock": 1.5},
        ),
        considered_total=3,
    )

    built = to_cart_line(line)

    assert [option.name for option in built.considered] == ["Форель"]
    assert built.considered_total == 3, "число лишається чесним, хоч рядок і випав"


def _weighed(pid: int, name: str, price: float, *, step: float = 0.1) -> dict:
    return _product(pid, name, price, 20) | {
        "weighted": True,
        "step": step,
        "displayRatio": "100г",
    }


def _bought(
    name: str, unit: str, qty: str, *, lager: str = "901", recent: int | None = None
) -> HistoryItem:
    item = HistoryItem(lager_id=lager, name=name, unit=unit)
    item.receipts = 3
    item.recent_receipts = 3 if recent is None else recent
    item.qty_total = Decimal(qty) * 3
    item.qty_recent = Decimal(qty) * item.recent_receipts
    return item


def test_grams_in_a_receipt_are_a_weight_not_a_count():
    assert _bought("Рулет курячий", "г", "300").typical_weight == Decimal("0.3")


def test_pieces_never_turn_into_a_weight():
    assert _bought("Молоко", "шт", "2").typical_weight is None
    assert HistoryItem(lager_id="1", name="Х", unit="г").typical_weight is None


def test_a_weighed_line_takes_the_weight_from_the_receipts():
    qty, unit, note = line_quantity(
        _weighed(901, "Рулет курячий «Алан» домашній в/г", 719.0),
        hint=_bought("Рулет курячий «Алан» домашній в/г", "г", "300"),
    )

    assert (qty, unit) == (Decimal("0.3"), "кг")
    assert note is not None and "звична вага з чеків" in note


def test_the_card_step_quantizes_the_weight():
    qty, _, _ = line_quantity(
        _weighed(902, "Окіст свинячий", 272.46, step=0.4),
        hint=_bought("Окіст свинячий", "г", "300"),
    )

    assert qty == Decimal("0.4")


def test_without_a_weight_in_the_receipts_the_smallest_step_is_taken():
    qty, unit, note = line_quantity(_weighed(903, "Сир Джюгас", 899.0))

    assert (qty, unit) == (Decimal("0.1"), "кг")
    assert note is not None and "ваги в чеках немає" in note


def test_the_agents_count_does_not_apply_to_a_weighed_line():
    qty, _, _ = line_quantity(
        _weighed(904, "Рулет курячий", 719.0),
        pick={"qty": 2, "chosen_id": "904", "reason": "звичне"},
        hint=_bought("Рулет курячий", "г", "300"),
    )

    assert qty == Decimal("0.3")


def test_a_piece_line_still_counts_in_pieces():
    qty, unit, note = line_quantity(
        _product(101, "Молоко Ферма 2,5%", 53.49, 20),
        pick={"qty": 2, "chosen_id": "101", "reason": "звичне"},
    )

    assert (qty, unit, note) == (Decimal(2), "шт", None)


def test_the_weighed_row_on_the_screen_is_kilograms_and_a_price_per_kilogram():
    candidates = {"рулет": [_weighed(901, "Рулет курячий «Алан» домашній в/г", 719.0)]}
    hints = {"рулет": _bought("Рулет курячий «Алан» домашній в/г", "г", "300")}

    plan, _, _ = build_lines(["рулет"], candidates, hints, picks={})
    line = to_cart_line(plan[0])

    assert (line.qty, line.unit, line.step) == (Decimal("0.3"), "кг", Decimal("0.1"))
    assert line.price == Decimal("719"), "ціна лишається ціною кілограма"
    assert line.qty * line.price == Decimal("215.7")
    assert "вагове" in (line.explanation_detail or "")


_QUIET = datetime(2026, 8, 13, tzinfo=UTC)


def _packed(pid: int, name: str, price: float, ratio: str) -> dict:
    return _product(pid, name, price, 20) | {"displayRatio": ratio}


async def test_weight_without_packaging_is_not_a_silent_zero(mcp):
    assembled = await assemble_list(
        mcp,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко", "кава"]}),
        now=_QUIET,
    )

    basket = assembled.basket
    assert [line.weight_kg for line in basket.lines] == [None, None]
    assert basket.total_weight_kg == Decimal(0)
    assert "order.weight.max" not in basket.blockers, "невідома вага не вигадує перевищення"

    step = next(s for s in basket.trace if s.id == "step-weight")
    assert "без 2 рядків" in step.result_summary


async def test_the_line_weighs_its_packaging_and_the_basket_sums_it(tmp_path, mcp):
    (tmp_path / "silpo_find_products_batch.json").write_text(
        json.dumps(
            {
                "queries": [
                    {"query": "вода", "products": [_packed(401, "Вода Моршинська", 25.0, "1,5л")]},
                    {"query": "сир", "products": [_weighed(902, "Сир Джюгас", 899.0)]},
                ]
            }
        ),
        encoding="utf-8",
    )

    assembled = await assemble_list(
        mcp,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week", "shoppingList": ["вода", "сир"]}),
        now=_QUIET,
    )

    basket = assembled.basket
    water = next(line for line in basket.lines if line.external_product_id == "401")
    cheese = next(line for line in basket.lines if line.external_product_id == "902")
    assert water.weight_kg == Decimal("1.5")
    assert cheese.weight_kg == Decimal(1), "у вагового кількість це вже кілограми"
    assert basket.total_weight_kg == Decimal("1.6")

    step = next(s for s in basket.trace if s.id == "step-weight")
    assert "без" not in step.result_summary, "оцінка повна — виправдовуватись нема чим"


async def test_the_slot_limit_is_named_with_the_number_of_trips(tmp_path, mcp):
    (tmp_path / "silpo_get_time_slots.json").write_text(
        json.dumps({"slots": [SLOT | {"maxWeight": 2}]}), encoding="utf-8"
    )
    (tmp_path / "silpo_find_products_batch.json").write_text(
        json.dumps(
            {
                "queries": [
                    {"query": "вода", "products": [_packed(401, "Вода Моршинська", 25.0, "1,5л")]}
                ]
            }
        ),
        encoding="utf-8",
    )
    llm = _AskingLLM([{"intent": "вода", "chosen_id": "401", "qty": 3, "reason": "звична"}])

    assembled = await assemble_list(
        mcp,
        llm,
        BuildRequest.model_validate({"mode": "week", "shoppingList": ["вода"]}),
        now=_QUIET,
    )

    basket = assembled.basket
    assert basket.total_weight_kg == Decimal("4.5")
    assert "order.weight.max" in basket.blockers

    step = next(s for s in basket.trace if s.id == "step-weight")
    assert step.tag == "понад ліміт на 2,5 кг"
    assert step.decision == "одним замовленням це не поїде: рейсів за вагою — 3"


def _water_needs_stand(tmp_path, mcp, *, max_weight: int) -> _Recording:
    (tmp_path / "silpo_get_time_slots.json").write_text(
        json.dumps({"slots": [SLOT | {"maxWeight": max_weight}]}), encoding="utf-8"
    )
    (tmp_path / "silpo_get_my_offline_orders.json").write_text(
        json.dumps(
            {
                "orders": [
                    {
                        "createdAt": day,
                        "products": [
                            {
                                "lagerId": 401,
                                "name": "Вода Моршинська 1,5л",
                                "unit": "шт",
                                "quantity": 6,
                                "price": 25,
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
                    {"query": "кава", "products": [_product(201, "Кава Lavazza", 245.0, 20)]},
                    {
                        "query": "Вода Моршинська 1,5л",
                        "products": [_packed(401, "Вода Моршинська 1,5л", 25.0, "1,5л")],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    return mcp


async def test_the_weight_limit_changes_the_composition_and_names_the_price(tmp_path, mcp):
    stand = _water_needs_stand(tmp_path, mcp, max_weight=5)
    llm = _QueueLLM(
        [
            {"intent": "кава", "chosen_id": "201", "qty": 1, "reason": "звична"},
            {"intent": "Вода Моршинська 1,5л", "chosen_id": "401", "qty": 6, "reason": "звична"},
        ],
        expendable=[{"intent": "Вода Моршинська 1,5л", "why": "вода є з-під крана"}],
    )

    assembled = await assemble_list(
        stand,
        llm,
        BuildRequest.model_validate({"mode": "week", "shoppingList": ["кава"]}),
        now=_WITH_NEEDS,
    )

    basket = assembled.basket
    assert [line.external_product_id for line in basket.lines] == ["201"]
    assert [item.intent for item in basket.trimmed] == ["Вода Моршинська 1,5л"]
    assert basket.trimmed[0].reason == "вода є з-під крана. Разом кошик важчий за ліміт слота"
    assert "order.weight.max" not in basket.blockers, "після зняття кошик у ліміт вліз"


async def test_the_guests_own_line_is_never_cut_by_the_weight(tmp_path, mcp):
    stand = _water_needs_stand(tmp_path, mcp, max_weight=1)
    llm = _QueueLLM(
        [
            {"intent": "кава", "chosen_id": "201", "qty": 1, "reason": "звична"},
            {"intent": "Вода Моршинська 1,5л", "chosen_id": "401", "qty": 6, "reason": "звична"},
        ],
        expendable=[{"intent": "кава", "why": "можна і без кави"}],
    )

    assembled = await assemble_list(
        stand,
        llm,
        BuildRequest.model_validate(
            {
                "mode": "week",
                "shoppingList": ["кава", "Вода Моршинська 1,5л"],
                "keep": [],
            }
        ),
        now=_WITH_NEEDS,
    )

    basket = assembled.basket
    assert "201" in [line.external_product_id for line in basket.lines]
    assert basket.trimmed == [], "черга з названого гостем — не черга"
    assert "order.weight.max" in basket.blockers, "різати нема чого, отже кажемо вголос"


def _fill_and_water_stand(tmp_path, mcp, max_weight: int):
    (tmp_path / "silpo_get_time_slots.json").write_text(
        json.dumps({"slots": [SLOT | {"maxWeight": max_weight}]}), encoding="utf-8"
    )
    orders = [
        {
            "createdAt": day,
            "products": [
                {
                    "lagerId": 401,
                    "name": "Вода Моршинська 1,5л",
                    "unit": "шт",
                    "quantity": 6,
                    "price": 25,
                }
            ],
        }
        for day in ("2026-07-18", "2026-07-25", "2026-08-01", "2026-08-08")
    ] + [
        {
            "createdAt": day,
            "products": [
                {
                    "lagerId": 501,
                    "name": "Сік Садочок 1л",
                    "unit": "шт",
                    "quantity": 4,
                    "price": 40,
                }
            ],
        }
        for day in ("2026-05-11", "2026-06-10", "2026-07-10", "2026-08-09")
    ]
    (tmp_path / "silpo_get_my_offline_orders.json").write_text(
        json.dumps({"orders": orders}), encoding="utf-8"
    )
    (tmp_path / "silpo_find_products_batch.json").write_text(
        json.dumps(
            {
                "queries": [
                    {
                        "query": "Вода Моршинська 1,5л",
                        "products": [_packed(401, "Вода Моршинська 1,5л", 25.0, "1,5л")],
                    },
                    {
                        "query": "Сік Садочок 1л",
                        "products": [_packed(501, "Сік Садочок 1л", 40.0, "1л")],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    return mcp


async def test_our_fill_cut_by_the_weight_is_not_reported_as_a_price_cut(tmp_path, mcp):
    stand = _fill_and_water_stand(tmp_path, mcp, max_weight=10)
    llm = _QueueLLM(
        [
            {"intent": "Вода Моршинська 1,5л", "chosen_id": "401", "qty": 6, "reason": "звична"},
            {"intent": "Сік Садочок 1л", "chosen_id": "501", "qty": 4, "reason": "звичний"},
        ],
        expendable=[],
    )

    assembled = await assemble_list(
        stand,
        llm,
        BuildRequest.model_validate({"mode": "week", "budget": 2000}),
        now=_WITH_NEEDS,
    )

    basket = assembled.basket
    assert assembled.fill_intents == ("Сік Садочок 1л",), "стенд: сік докинули МИ під ціль"
    assert [line.name for line in basket.lines] == ["Вода Моршинська 1,5л"]
    budget = next(s for s in basket.trace if s.id == "step-budget")
    assert "добір не вліз за цінами" not in budget.result_summary
    weight = next(s for s in basket.trace if s.id == "step-weight")
    assert weight.args["наш добір, знятий вагою"] == ["Сік Садочок 1л"]
    assert "наш добір не вліз за вагою: 1 поз." in weight.result_summary


async def test_the_weight_cut_goes_on_after_the_agents_queue_runs_out(tmp_path, mcp):
    stand = _water_needs_stand(tmp_path, mcp, max_weight=5)
    llm = _QueueLLM(
        [{"intent": "Вода Моршинська 1,5л", "chosen_id": "401", "qty": 6, "reason": "звична"}],
        expendable=[],
    )

    assembled = await assemble_list(
        stand,
        llm,
        BuildRequest.model_validate({"mode": "week", "shoppingList": ["кава"]}),
        now=_WITH_NEEDS,
    )

    basket = assembled.basket
    assert [item.intent for item in basket.trimmed] == ["Вода Моршинська 1,5л"]
    assert "черга агента вичерпана" in basket.trimmed[0].reason
    assert "order.weight.max" not in basket.blockers, "після зняття кошик у ліміт вліз"


async def test_a_slot_without_a_limit_does_not_invent_one(tmp_path, mcp):
    slot = {key: value for key, value in SLOT.items() if key != "maxWeight"}
    (tmp_path / "silpo_get_time_slots.json").write_text(
        json.dumps({"slots": [slot]}), encoding="utf-8"
    )
    (tmp_path / "silpo_find_products_batch.json").write_text(
        json.dumps(
            {
                "queries": [
                    {"query": "вода", "products": [_packed(401, "Вода Моршинська", 25.0, "1,5л")]}
                ]
            }
        ),
        encoding="utf-8",
    )

    assembled = await assemble_list(
        mcp,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week", "shoppingList": ["вода"]}),
        now=_QUIET,
    )

    basket = assembled.basket
    assert "order.weight.max" not in basket.blockers
    step = next(s for s in basket.trace if s.id == "step-weight")
    assert "ліміту слот не назвав" in step.result_summary


def test_the_form_wish_reaches_the_collector_only_when_the_shelf_has_both():
    whole = _product(201, "Хліб «Рум'янець» цільнозерновий пшеничний", 57.21, 4)
    sliced = _product(202, "Хліб «Рум'янець» «Австрійський» нарізаний", 49.34, 30)
    picks = {"хліб": {"intent": "хліб", "chosen_id": "201", "qty": 1, "reason": "тест"}}

    alone, _, _ = build_lines(["хліб"], {"хліб": [whole]}, {}, picks, auto_swap=True)
    assert alone[0].mandate is not None
    assert "нарізки" not in alone[0].mandate

    both, _, _ = build_lines(["хліб"], {"хліб": [whole, sliced]}, {}, picks)
    assert both[0].mandate is not None and both[0].mandate.endswith("без нарізки")


def test_the_line_says_when_the_form_disagrees_with_the_receipts():
    whole = _product(201, "Хліб «Рум'янець» цільнозерновий пшеничний", 57.21, 30)
    sliced = _product(202, "Хліб «Рум'янець» «Австрійський» нарізаний", 49.34, 30)
    guest = slicing.Habit(sliced=False, sliced_receipts=1, plain_receipts=7)

    lines, _, _ = build_lines(
        ["хліб"],
        {"хліб": [whole, sliced]},
        {},
        {"хліб": {"intent": "хліб", "chosen_id": "202", "qty": 1, "reason": "тест"}},
        habits={"хліб": guest},
    )
    assert lines[0].slicing_note == "у твоїх чеках цей вид 7 без нарізки, 1 нарізаним"
    assert to_cart_line(lines[0]).sliced is True

    same, _, _ = build_lines(
        ["хліб"],
        {"хліб": [whole, sliced]},
        {},
        {"хліб": {"intent": "хліб", "chosen_id": "201", "qty": 1, "reason": "тест"}},
        habits={"хліб": guest},
    )
    assert same[0].slicing_note is None, "збіг мовчить"
    assert to_cart_line(same[0]).sliced is False


def test_the_habit_counts_every_sku_of_the_kind_not_the_freshest():
    every = [
        HistoryItem(
            lager_id="202",
            name="Хліб Рум'янець З льоном нарізний",
            unit="шт",
            receipts=1,
            qty_total=Decimal(1),
        ),
        HistoryItem(
            lager_id="201",
            name="Хліб «Рум'янець» цільнозерновий пшеничний",
            unit="шт",
            receipts=7,
            qty_total=Decimal(7),
        ),
    ]
    assert _slicing_habit(every).sliced is False
    assert _slicing_habit(every[:1]).sliced is None, "один чек звичкою не робить"


async def test_the_agent_sees_the_form_and_the_guest_habit():
    seen: dict[str, Any] = {}

    class _Fake:
        async def decide(self, *, system, user, schema, max_tokens, **_):
            seen["user"] = json.loads(user)
            return Decision(
                data={"picks": []}, text="", model="fake", usage=Usage(1, 1), duration_ms=1
            )

    history = [
        HistoryItem(
            lager_id="201",
            name="Хліб «Рум'янець» цільнозерновий пшеничний",
            unit="шт",
            receipts=7,
            qty_total=Decimal(7),
        ),
        HistoryItem(
            lager_id="202",
            name="Хліб Рум'янець З льоном нарізний",
            unit="шт",
            receipts=1,
            qty_total=Decimal(1),
        ),
    ]
    await agent_picks(
        _Fake(),
        ["хліб"],
        {
            "хліб": [
                _product(201, "Хліб «Рум'янець» цільнозерновий пшеничний", 57.21, 30),
                _product(202, "Хліб «Рум'янець» «Австрійський» нарізаний", 49.34, 30),
            ]
        },
        {"хліб": history},
        rules=[],
    )

    intent = seen["user"]["наміри"][0]
    assert [c.get("нарізка") for c in intent["кандидати"]] == [None, True]
    assert intent["нарізка_в_чеках"] == "у твоїх чеках цей вид 7 без нарізки, 1 нарізаним"


async def test_a_tie_in_the_receipts_reaches_the_agent_as_silence():
    seen: dict[str, Any] = {}

    class _Fake:
        async def decide(self, *, system, user, schema, max_tokens, **_):
            seen["user"] = json.loads(user)
            return Decision(
                data={"picks": []}, text="", model="fake", usage=Usage(1, 1), duration_ms=1
            )

    history = [
        HistoryItem(
            lager_id="301",
            name="Хліб Київхліб Тост нарізаний",
            unit="шт",
            receipts=1,
            qty_total=Decimal(1),
        ),
        HistoryItem(
            lager_id="302",
            name="Хліб Київхліб Оксамитовий",
            unit="шт",
            receipts=1,
            qty_total=Decimal(1),
        ),
    ]
    await agent_picks(
        _Fake(),
        ["хліб"],
        {"хліб": [_product(301, "Хліб Київхліб Тост нарізаний", 38.84, 30)]},
        {"хліб": history},
        rules=[],
    )

    assert "нарізка_в_чеках" not in seen["user"]["наміри"][0]


def _with_cart_switches(tmp_path, changes: str | None) -> None:
    (tmp_path / "silpo_get_my_shopping_cart.json").write_text(
        json.dumps({"shoppingCartId": "00000000-0000-4000-8000-00000000c0de"}),
        encoding="utf-8",
    )
    cart: dict[str, Any] = {
        "id": "00000000-0000-4000-8000-00000000c0de",
        "deliveryType": "DeliveryHome",
        "timeslot": {"start": SLOT["start"], "end": SLOT["end"]},
        "shipments": [{"branchId": BRANCH_FROM_ADDRESS, "products": []}],
        "calculation": {"validations": []},
    }
    if changes is not None:
        cart["feedbackChanges"] = changes
    (tmp_path / "silpo_get_shopping_cart_by_id.json").write_text(
        json.dumps({"cart": cart}), encoding="utf-8"
    )


async def test_the_risk_step_stops_promising_the_collector_when_swaps_are_banned(mcp, tmp_path):
    _with_cart_switches(tmp_path, "disapprovedChanges")
    request = BuildRequest.model_validate(
        {"mode": "week", "shoppingList": ["кава"], "autoSwap": True}
    )
    assembled = await assemble_list(mcp, llm=None, request=request)

    step = next(s for s in assembled.basket.trace if s.id == "step-risk")
    assert "не спрацює" in step.decision
    assert "до слота" in step.decision, "своя рука мусить назватись"
    assert assembled.basket.feedback.changes is Changes.DISAPPROVED


async def test_the_risk_step_promises_the_collector_when_swaps_are_allowed(mcp, tmp_path):
    _with_cart_switches(tmp_path, "approvedChanges")
    request = BuildRequest.model_validate(
        {"mode": "week", "shoppingList": ["кава"], "autoSwap": True}
    )
    assembled = await assemble_list(mcp, llm=None, request=request)

    step = next(s for s in assembled.basket.trace if s.id == "step-risk")
    assert "ляжуть у comment збирачу" in step.decision
    assert assembled.basket.feedback.changes is Changes.APPROVED


async def test_an_unread_cart_promises_nothing_about_the_collector(mcp):
    request = BuildRequest.model_validate(
        {"mode": "week", "shoppingList": ["кава"], "autoSwap": True}
    )
    assembled = await assemble_list(mcp, llm=None, request=request)

    step = next(s for s in assembled.basket.trace if s.id == "step-risk")
    assert "не звіряли" in step.decision
    assert assembled.basket.feedback.changes is None


def test_a_chain_rides_as_a_mandate_at_any_distance_to_the_slot():
    whole = _product(201, "Хліб «Рум'янець» цільнозерновий пшеничний", 57.21, 40)
    other = _product(202, "Хліб «Київхліб» цільнозерновий пшеничний", 49.34, 30)

    near, _, _ = build_lines(["хліб"], {"хліб": [whole, other]}, {}, {}, hours_to_slot=2)
    far, _, _ = build_lines(["хліб"], {"хліб": [whole, other]}, {}, {}, hours_to_slot=44)

    assert near[0].mandate is not None and "Київхліб" in near[0].mandate, (
        "полиця повна, слот через дві години -- а ланцюжок є, і він їде"
    )
    assert far[0].mandate is not None and "Київхліб" in far[0].mandate
    assert far[0].risky is False, "залишок 40 — це не малий залишок"
    assert far[0].ahead is True and near[0].ahead is True


def test_a_line_without_a_chain_rides_with_a_do_not_substitute_mandate():
    lonely = _product(301, "Кава мелена «Своя Лінія» 225 г", 129.0, 55)

    lines, _, _ = build_lines(["кава"], {"кава": [lonely]}, {}, {}, hours_to_slot=44)

    [line] = lines
    assert line.chain == (), "заміняти нема на що — кандидат один"
    assert line.mandate is not None and "не підбирати" in line.mandate
    assert line.needs_approval is False
    assert line.ahead is True, "мандат є -- він і підписується наперед"


def test_a_distant_slot_with_standing_consent_falls_back_to_the_price_fork():
    lonely = _product(301, "Кава мелена «Своя Лінія» 225 г", 129.0, 55)

    lines, _, _ = build_lines(
        ["кава"], {"кава": [lonely]}, {}, {}, auto_swap=True, hours_to_slot=44
    )

    [line] = lines
    assert line.swap_fork is not None
    assert line.mandate is not None and "у межах" in line.mandate
    assert line.ahead is True
    assert line.needs_approval is False


async def test_the_trace_names_the_gap_that_prepared_the_rest_of_the_basket(mcp):
    from datetime import UTC, datetime

    request = BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко"]})
    assembled = await assemble_list(
        mcp, llm=None, request=request, now=datetime(2026, 8, 13, 12, tzinfo=UTC)
    )

    [line] = assembled.lines
    assert line.risky is False and line.ahead is True
    step = next(s for s in assembled.basket.trace if s.id == "step-risk")
    assert "до слота 24 год" in step.result_summary
    assert "при стелі 18" in step.result_summary


class _OccasionLLM:

    model = "fake-model"

    def __init__(self, *, add=(), skip=(), picks=(), fail: bool = False) -> None:
        self.add = list(add)
        self.skip = list(skip)
        self.picks = list(picks)
        self.fail = fail
        self.occasion_payload: dict | None = None
        self.understand_payload: dict | None = None
        self.pick_payload: dict | None = None
        self.pick_system = ""

    async def decide(self, *, system, user, schema, schema_name="decision", max_tokens=2048, **_):
        payload = json.loads(user)
        if "questions" in schema["properties"]:
            self.understand_payload = payload
            return Decision(
                data={"questions": [], "add": [], "drop": []},
                text="",
                model=self.model,
                usage=Usage(1, 1),
                duration_ms=1,
            )
        if "add" in schema["properties"]:
            if self.fail:
                raise RuntimeError("модель мовчить")
            self.occasion_payload = payload
            data = {"add": self.add, "skip": self.skip}
        else:
            self.pick_payload = payload
            self.pick_system = system
            data = {"picks": self.picks}
        return Decision(data=data, text="", model=self.model, usage=Usage(1, 1), duration_ms=1)


def _occasion_step(assembled):
    return next(s for s in assembled.basket.trace if s.id == "step-occasion")


def _step(assembled, step_id: str):
    return next((s for s in assembled.basket.trace if s.id == step_id), None)


async def test_the_list_mode_takes_the_guests_words_and_never_the_cycles(mcp):
    listed = await assemble_list(
        mcp,
        llm=None,
        request=BuildRequest.model_validate({"mode": "list", "shoppingList": ["кава"]}),
    )

    assert [line.intent for line in listed.lines] == ["кава"]
    assert _step(listed, "step-needs") is None, "кроку потреб немає, бо потреб не рахували"


async def test_the_week_mode_still_reads_the_cycles_next_to_the_same_list(mcp):
    week = await assemble_list(
        mcp,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week", "shoppingList": ["кава"]}),
    )

    assert {line.intent for line in week.lines} >= {"кава", "Молоко Ферма 2,5%"}
    assert _step(week, "step-needs") is not None


async def test_the_list_mode_takes_the_written_list_and_leaves_the_pantry_notes(mcp):
    listed = await assemble_list(
        mcp,
        llm=None,
        request=BuildRequest.model_validate({"mode": "list"}),
        wanted={"кава": "кава"},
        manual={"молоко": "молоко"},
    )
    week = await assemble_list(
        mcp,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week"}),
        wanted={"кава": "кава"},
        manual={"молоко": "молоко"},
    )

    assert [line.intent for line in listed.lines] == ["кава"]
    assert _step(listed, "step-manual") is None, "комору в цьому режимі не читали"
    assert _step(week, "step-manual") is not None, (
        "а в тижні читали — інакше пара нічого не доводить"
    )


async def test_the_list_mode_does_not_fill_up_to_the_named_sum(mcp):
    listed = await assemble_list(
        mcp,
        llm=None,
        request=BuildRequest.model_validate(
            {"mode": "list", "shoppingList": ["кава"], "budget": 3000}
        ),
    )

    assert _step(listed, "step-target") is None
    assert [line.intent for line in listed.lines] == ["кава"]


async def test_the_mode_step_stands_always_and_names_where_the_intents_came_from(mcp):
    listed = await assemble_list(
        mcp,
        llm=None,
        request=BuildRequest.model_validate({"mode": "list", "shoppingList": ["кава"]}),
    )
    week = await assemble_list(
        mcp,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week", "shoppingList": ["кава"]}),
    )

    said = _step(listed, "step-mode")
    assert said is not None
    assert "зі списку" in said.result_summary
    assert "з поля: 1" in said.result_summary
    assert "цикли вимкнено" in said.result_summary

    other = _step(week, "step-mode")
    assert other is not None
    assert "за циклами:" in other.result_summary


async def test_an_empty_list_mode_refuses_by_naming_the_list_and_not_the_cycles(mcp):
    with pytest.raises(AssemblyError) as failure:
        await assemble_list(mcp, llm=None, request=BuildRequest.model_validate({"mode": "list"}))

    assert "у списку порожньо" in str(failure.value)
    assert "цикл" not in str(failure.value)


async def test_the_style_of_the_event_reaches_the_choice_prompt(mcp):
    llm = _OccasionLLM(
        picks=[{"intent": "молоко", "chosen_id": "101", "qty": 1, "reason": "звичне"}]
    )
    request = BuildRequest.model_validate(
        {
            "mode": "event",
            "shoppingList": ["молоко"],
            "occasionPeople": 4,
            "eventStyle": "ready",
        }
    )
    await assemble_list(mcp, llm=llm, request=request)

    assert llm.pick_payload is not None
    assert "бере готове" in llm.pick_payload["привід"]
    assert "нарізк" in llm.pick_payload["що_означає_привід"]


async def test_an_ordinary_week_leaves_no_occasion_step_because_nothing_happened(mcp):
    llm = _OccasionLLM(picks=[])
    assembled = await assemble_list(
        mcp,
        llm=llm,
        request=BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко"]}),
    )

    assert llm.occasion_payload is None, "звичайний тиждень моделі не коштує нічого"
    assert not [s for s in assembled.basket.trace if s.id == "step-occasion"]
    assert llm.pick_payload is not None and "привід" not in llm.pick_payload


async def test_the_occasion_adds_a_line_that_explains_itself_by_the_occasion(mcp):
    llm = _OccasionLLM(
        add=[{"intent": "кава", "why": "до гостей — щоб було чим завершити стіл"}],
        picks=[{"intent": "кава", "chosen_id": "201", "qty": 1, "reason": "звичне"}],
    )
    request = BuildRequest.model_validate(
        {"shoppingList": ["молоко"], "mode": "event", "occasionPeople": 4}
    )
    assembled = await assemble_list(mcp, llm=llm, request=request)

    coffee = next(line for line in assembled.lines if line.intent == "кава")
    assert coffee.reason_code is Reason.OCCASION
    assert coffee.explanation == "до гостей — щоб було чим завершити стіл"

    step = _occasion_step(assembled)
    assert "подія, 4 людини" in step.result_summary
    assert "докинув 1 — кава" in step.result_summary
    assert step.tag == "+1"


async def test_the_occasion_removes_the_regular_and_says_so_by_name(mcp):
    llm = _OccasionLLM(
        skip=[{"intent": "Молоко Ферма 2,5%", "why": "зіпсується без тебе вдома"}],
        picks=[{"intent": "кава", "chosen_id": "201", "qty": 1, "reason": "звичне"}],
    )
    request = BuildRequest.model_validate({"shoppingList": ["кава"], "mode": "event"})
    assembled = await assemble_list(mcp, llm=llm, request=request)

    assert [line.intent for line in assembled.lines] == ["кава"]
    step = _occasion_step(assembled)
    assert "зняв 1 — Молоко Ферма 2,5%" in step.result_summary
    assert step.tag == "-1"


async def test_the_occasion_cannot_remove_what_the_guest_wrote_himself(mcp):
    llm = _OccasionLLM(
        skip=[{"intent": "молоко", "why": "зіпсується"}],
        picks=[{"intent": "молоко", "chosen_id": "101", "qty": 1, "reason": "звичне"}],
    )
    request = BuildRequest.model_validate({"shoppingList": ["молоко"], "mode": "event"})
    assembled = await assemble_list(mcp, llm=llm, request=request)

    assert [line.intent for line in assembled.lines] == ["молоко"]
    assert "зняв" not in _occasion_step(assembled).result_summary


async def test_an_occasion_that_empties_the_basket_names_the_occasion_not_the_cycles(mcp):
    llm = _OccasionLLM(skip=[{"intent": "Молоко Ферма 2,5%", "why": "регулярна покупка"}])
    request = BuildRequest.model_validate({"mode": "event"})

    with pytest.raises(AssemblyError) as failure:
        await assemble_list(mcp, llm=llm, request=request)

    assert "подія" in str(failure.value)


async def test_a_silent_occasion_would_be_the_bug_itself_so_failure_speaks(mcp):
    llm = _OccasionLLM(
        fail=True,
        picks=[{"intent": "молоко", "chosen_id": "101", "qty": 1, "reason": "звичне"}],
    )
    request = BuildRequest.model_validate({"shoppingList": ["молоко"], "mode": "event"})
    assembled = await assemble_list(mcp, llm=llm, request=request)

    step = _occasion_step(assembled)
    assert step.tag == "не спрацював" and step.tag_tone == "warn"
    assert "не застосувався" in step.result_summary
    assert assembled.lines, "привід не спрацював — але кошик зібрався"


async def test_the_choice_prompt_learns_the_occasion_because_quantity_is_its_half(mcp):
    llm = _OccasionLLM(
        picks=[{"intent": "молоко", "chosen_id": "101", "qty": 3, "reason": "гостей четверо"}]
    )
    request = BuildRequest.model_validate(
        {"shoppingList": ["молоко"], "mode": "event", "occasionPeople": 8}
    )
    await assemble_list(mcp, llm=llm, request=request)

    assert llm.pick_payload is not None
    assert llm.pick_payload["привід"] == "подія, 8 людей"
    assert "стіл" in llm.pick_payload["що_означає_привід"]
    assert "механічно" in llm.pick_system.lower() or "Механічно" in llm.pick_system


async def test_the_occasion_line_may_be_cut_by_the_budget_but_the_guests_word_may_not(mcp):
    llm = _OccasionLLM(
        add=[{"intent": "кава", "why": "до столу"}],
        picks=[
            {"intent": "молоко", "chosen_id": "101", "qty": 1, "reason": "звичне"},
            {"intent": "кава", "chosen_id": "201", "qty": 1, "reason": "до столу"},
        ],
    )
    request = BuildRequest.model_validate(
        {"shoppingList": ["молоко"], "mode": "event", "occasionPeople": 4}
    )
    await assemble_list(mcp, llm=llm, request=request)

    assert llm.pick_payload is not None
    sources = {item["намір"]: item["джерело"] for item in llm.pick_payload["наміри"]}
    assert sources["кава"] == "привід"
    assert sources["молоко"] == "список гостя"


async def test_the_basket_says_why_it_is_not_filled_up_to_the_limit(tmp_path, mcp):
    from datetime import UTC, datetime

    now = datetime(2026, 8, 20, tzinfo=UTC)
    _trust_stand(tmp_path, mcp, now)

    assembled = await assemble_list(
        mcp, llm=None, request=BuildRequest(mode="week", budget=Decimal(3000)), now=now
    )

    note = assembled.basket.cycles_note
    assert note is not None
    assert "2 з 3" in note, "числа мусять бути обидва: доведені і всі"
    assert "напиши, що треба" in note, "порада веде в поле «Додати ще» поруч"


async def test_the_list_mode_does_not_explain_itself_with_the_receipts(tmp_path, mcp):
    from datetime import UTC, datetime

    now = datetime(2026, 8, 20, tzinfo=UTC)
    _trust_stand(tmp_path, mcp, now)

    assembled = await assemble_list(
        mcp,
        llm=None,
        request=BuildRequest.model_validate({"mode": "list", "shoppingList": ["молоко"]}),
        now=now,
    )

    note = assembled.basket.cycles_note
    assert note is not None
    assert "покупок у різні дні" not in note, "чеки в акаунті є, і ніхто їх не питав"
    assert "зі списку" in note
    assert "напиши, що треба" in note, "порада веде в поле «Додати ще» поруч"


async def test_a_need_that_found_nothing_stays_on_the_screen(tmp_path, mcp):
    import json
    from datetime import UTC, datetime

    now = datetime(2026, 8, 20, tzinfo=UTC)
    _trust_stand(tmp_path, mcp, now)
    batch = json.loads((tmp_path / "silpo_find_products_batch.json").read_text(encoding="utf-8"))
    for query in batch["queries"]:
        if query["query"] == "Морозиво Рудь пломбір":
            query["products"] = []
    (tmp_path / "silpo_find_products_batch.json").write_text(json.dumps(batch), encoding="utf-8")

    assembled = await assemble_list(mcp, llm=None, request=BuildRequest(mode="week"), now=now)
    basket = assembled.basket

    assert not any("Морозиво" in line.name for line in basket.lines)
    lost = next(item for item in basket.postponed if "Морозиво" in item.intent)
    assert "давно не брав" in lost.reason, "підстава та сама, що в рядка кошика"
    assert "не знайшлось" in lost.reason
    assert lost.estimate is not None, "ціну дав його ж чек"
    assert lost.refillable is False, "кнопка добору впала б так само"
    assert not basket.unresolved and not basket.not_collected


async def test_the_trace_names_the_needs_that_found_no_product(tmp_path, mcp):
    import json
    from datetime import UTC, datetime

    now = datetime(2026, 8, 20, tzinfo=UTC)
    _trust_stand(tmp_path, mcp, now)
    batch = json.loads((tmp_path / "silpo_find_products_batch.json").read_text(encoding="utf-8"))
    for query in batch["queries"]:
        if query["query"] == "Морозиво Рудь пломбір":
            query["products"] = []
    (tmp_path / "silpo_find_products_batch.json").write_text(json.dumps(batch), encoding="utf-8")

    steps = {
        step.id: step
        for step in (
            await assemble_list(mcp, llm=None, request=BuildRequest(mode="week"), now=now)
        ).basket.trace
    }

    assert "без жодного кандидата: 1" in steps["step-batch"].result_summary
    assert steps["step-batch"].tag == "1 без товару"
    assert "не знайшлось: 1" in steps["step-missing"].result_summary
    assert any("Морозиво" in kind for kind in steps["step-missing"].args["види"])
    assert steps["step-missing"].tag == "-1 поз."


async def test_a_need_whose_receipt_name_finds_nothing_is_narrowed_to_its_kind(tmp_path, mcp):
    import json
    from datetime import UTC, datetime

    now = datetime(2026, 8, 20, tzinfo=UTC)
    _trust_stand(tmp_path, mcp, now)
    batch = json.loads((tmp_path / "silpo_find_products_batch.json").read_text(encoding="utf-8"))
    for query in batch["queries"]:
        if query["query"] == "Морозиво Рудь пломбір":
            query["products"] = []
    batch["queries"].append(
        {
            "query": "Морозиво Рудь",
            "products": [
                _product(999, "Йогурт полуничний", 30.0, 30),
                _product(302, "Морозиво Рудь пломбір ванільний", 92.0, 30),
            ],
        }
    )
    (tmp_path / "silpo_find_products_batch.json").write_text(json.dumps(batch), encoding="utf-8")

    assembled = await assemble_list(mcp, llm=None, request=BuildRequest(mode="week"), now=now)
    basket = assembled.basket

    names = [line.name for line in basket.lines]
    assert "Морозиво Рудь пломбір ванільний" in names
    assert "Йогурт полуничний" not in names, "звужений запит судить сам себе"
    assert not basket.postponed and not basket.unresolved

    step = next(s for s in basket.trace if s.id == "step-narrow")
    assert "звузив до виду: 1" in step.result_summary
    assert "Морозиво Рудь" in step.args["запити"].values()
    assert step.tag == "+1 поз."


class _NamingLLM:

    model = "fake-model"

    def __init__(self, kinds: dict[str, str]) -> None:
        self.kinds = kinds
        self.queries_seen: list[str] = []

    async def decide(self, *, system, user, schema, schema_name="decision", max_tokens=2048, **_):
        from komora.agent.llm import Decision, Usage

        payload = json.loads(user)
        if "назви" in payload:
            data = {
                "kinds": [
                    {"name": name, "intent": self.kinds.get(name, name), "subtype": None}
                    for name in payload["назви"]
                ]
            }
        else:
            data = {"picks": []}
        return Decision(data=data, text="", model=self.model, usage=Usage(1, 1), duration_ms=1)


async def test_the_kind_phrase_is_asked_as_its_own_query(tmp_path, mcp):
    from datetime import UTC, datetime

    now = datetime(2026, 8, 20, tzinfo=UTC)
    _trust_stand(tmp_path, mcp, now)
    batch = json.loads((tmp_path / "silpo_find_products_batch.json").read_text(encoding="utf-8"))
    batch["queries"].append(
        {
            "query": "морозиво вершкове",
            "products": [
                _product(310, "Морозиво вершкове Лімо", 70.0, 30),
                _product(311, "Морозиво вершкове Ласуня", 72.0, 30),
            ],
        }
    )
    (tmp_path / "silpo_find_products_batch.json").write_text(json.dumps(batch), encoding="utf-8")

    llm = _NamingLLM({"Морозиво Рудь пломбір": "морозиво вершкове"})
    assembled = await assemble_list(mcp, llm=llm, request=BuildRequest(mode="week"), now=now)

    step = next(s for s in assembled.basket.trace if s.id == "step-kind-query")
    assert "2 нових кандидатів до 1 намірів" in step.result_summary
    assert "морозиво вершкове" in step.args["фрази"].values()
    assert step.tag == "+2 поз."


async def test_the_kind_phrase_has_a_ceiling_of_its_own(tmp_path, mcp):
    from datetime import UTC, datetime

    from komora.agent.steps.shelf import KIND_QUERY_TAKE

    now = datetime(2026, 8, 20, tzinfo=UTC)
    _trust_stand(tmp_path, mcp, now)
    batch = json.loads((tmp_path / "silpo_find_products_batch.json").read_text(encoding="utf-8"))
    batch["queries"].append(
        {
            "query": "морозиво вершкове",
            "products": [
                _product(320 + i, f"Морозиво вершкове {i}", 70.0 + i, 30)
                for i in range(KIND_QUERY_TAKE + 4)
            ],
        }
    )
    (tmp_path / "silpo_find_products_batch.json").write_text(json.dumps(batch), encoding="utf-8")

    llm = _NamingLLM({"Морозиво Рудь пломбір": "морозиво вершкове"})
    assembled = await assemble_list(mcp, llm=llm, request=BuildRequest(mode="week"), now=now)

    step = next(s for s in assembled.basket.trace if s.id == "step-kind-query")
    assert step.tag == f"+{KIND_QUERY_TAKE} поз.", "стеля ріже видачу видової фрази"


async def test_a_kind_phrase_equal_to_the_intent_is_not_asked_twice(tmp_path, mcp):
    from datetime import UTC, datetime

    now = datetime(2026, 8, 20, tzinfo=UTC)
    _trust_stand(tmp_path, mcp, now)

    llm = _NamingLLM({"Морозиво Рудь пломбір": "Морозиво Рудь пломбір"})
    assembled = await assemble_list(mcp, llm=llm, request=BuildRequest(mode="week"), now=now)

    assert not any(s.id == "step-kind-query" for s in assembled.basket.trace)


async def test_the_ladder_does_not_touch_the_guests_own_words(tmp_path, mcp):
    from datetime import UTC, datetime

    now = datetime(2026, 8, 20, tzinfo=UTC)
    _trust_stand(tmp_path, mcp, now)

    assembled = await assemble_list(
        mcp,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week", "shoppingList": ["шафран"]}),
        now=now,
    )

    assert "шафран" in assembled.basket.unresolved
    assert not any(s.id == "step-narrow" for s in assembled.basket.trace)


async def test_nothing_running_out_still_fills_to_a_named_sum(tmp_path, mcp):
    from datetime import UTC, datetime, timedelta

    now = datetime(2026, 8, 20, tzinfo=UTC)

    def bought(days: int, lager: int, name: str) -> dict:
        return {
            "createdAt": (now - timedelta(days=days)).strftime("%Y-%m-%d"),
            "products": [
                {
                    "lagerId": lager,
                    "name": name,
                    "unit": "шт",
                    "quantity": 1,
                    "price": 50,
                    "catalogProduct": {"price": 50},
                }
            ],
        }

    kinds = [(101, "Молоко Ферма 2,5%"), (102, "Хліб Київхліб"), (103, "Сир Комо")]
    (tmp_path / "silpo_get_my_offline_orders.json").write_text(
        json.dumps(
            {
                "orders": [
                    bought(days, lager, name) for lager, name in kinds for days in (22, 15, 8, 1)
                ]
            }
        ),
        encoding="utf-8",
    )
    batch = json.loads((tmp_path / "silpo_find_products_batch.json").read_text(encoding="utf-8"))
    batch["queries"] += [
        {"query": name, "products": [_product(lager, name, 50.0, 30)]} for lager, name in kinds
    ]
    (tmp_path / "silpo_find_products_batch.json").write_text(json.dumps(batch), encoding="utf-8")

    with pytest.raises(AssemblyError, match="нічого не закінчується"):
        await assemble_list(mcp, llm=None, request=BuildRequest(mode="week"), now=now)

    assembled = await assemble_list(
        mcp,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week", "budget": 150}),
        now=now,
    )

    assert assembled.basket.lines, "добір під суму мусив зібрати кошик з комори"
    assert all(line.reason is Reason.FREQUENCY for line in assembled.basket.lines)


async def test_a_named_sum_is_a_target_and_the_basket_reaches_for_it(tmp_path, mcp):
    from datetime import UTC, datetime

    now = datetime(2026, 8, 20, tzinfo=UTC)
    _trust_stand(tmp_path, mcp, now)

    assembled = await assemble_list(
        mcp,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week", "budget": 400}),
        now=now,
    )
    basket = assembled.basket

    step = next(s for s in basket.trace if s.id == "step-target")
    assert "ціль 400 грн, коридор 360-440" in step.result_summary
    added = [line for line in basket.lines if line.reason is Reason.FREQUENCY]
    assert added, "кошик мусив потягнутись до цілі"
    assert all("закінчил" not in (line.explanation or "") for line in added)


async def test_what_was_added_for_the_target_is_not_muted_as_still_at_home(tmp_path, mcp):
    from datetime import UTC, datetime

    now = datetime(2026, 8, 20, tzinfo=UTC)
    _trust_stand(tmp_path, mcp, now)

    assembled = await assemble_list(
        mcp,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week", "budget": 400}),
        now=now,
    )

    added = [line for line in assembled.basket.lines if line.reason is Reason.FREQUENCY]
    assert added and all(line.reason is not Reason.AT_HOME for line in added)


async def test_without_a_named_sum_nothing_is_added(tmp_path, mcp):
    from datetime import UTC, datetime

    now = datetime(2026, 8, 20, tzinfo=UTC)
    _trust_stand(tmp_path, mcp, now)

    assembled = await assemble_list(mcp, llm=None, request=BuildRequest(mode="week"), now=now)

    assert not any(s.id == "step-target" for s in assembled.basket.trace)
    assert not any(line.reason is Reason.FREQUENCY for line in assembled.basket.lines)


class _Batched:

    def __init__(self, fail: set[str] | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self.max_tokens: list[int] = []
        self._fail = fail or set()

    async def decide(self, *, system, user, schema, max_tokens, **_):
        asked = json.loads(user)
        names = [item["намір"] for item in asked["наміри"]]
        self.calls.append(asked)
        self.max_tokens.append(max_tokens)
        if self._fail & set(names):
            raise RuntimeError("пачка не долетіла")
        return Decision(
            data={
                "picks": [{"intent": name, "chosen_id": "1", "qty": 1} for name in names],
                "expendable": [{"intent": name, "why": "рідке"} for name in names],
            },
            text="",
            model="fake",
            usage=Usage(10, 10),
            duration_ms=1,
        )


def _four_intents() -> tuple[list[str], dict[str, list[dict]]]:
    intents = ["молоко", "хліб", "кава", "чай"]
    return intents, {name: [_product(1, name, 10.0, 5)] for name in intents}


async def test_two_batches_ask_twice_and_split_the_intents():
    llm = _Batched()
    intents, candidates = _four_intents()

    picks, _queue, _model, _ms, _tokens, batched = await agent_picks(
        llm, intents, candidates, {}, rules=[], batches=2
    )

    assert len(llm.calls) == 2
    asked = [name for call in llm.calls for item in call["наміри"] for name in [item["намір"]]]
    assert sorted(asked) == sorted(intents)
    assert set(picks) == set(intents)
    assert batched.sent == 2 and batched.lost == ()


async def test_each_batch_tells_what_it_picked_the_moment_it_lands():
    llm = _Batched()
    intents, candidates = _four_intents()
    told: list[tuple[int, int, list[str]]] = []

    await agent_picks(
        llm,
        intents,
        candidates,
        {},
        rules=[],
        batches=2,
        on_batch=lambda number, of, names: told.append((number, of, names)),
    )

    assert sorted((number, of) for number, of, _ in told) == [(1, 2), (2, 2)]
    assert sorted(name for _, _, names in told for name in names) == sorted(intents)


async def test_the_ceiling_of_the_answer_counts_per_batch():
    llm = _Batched()
    intents, candidates = _four_intents()

    await agent_picks(llm, intents, candidates, {}, rules=[], batches=2)

    assert llm.max_tokens == [max(2048, PICK_TOKENS_PER_INTENT * 2)] * 2


async def test_the_guest_rules_ride_in_every_batch():
    llm = _Batched()
    intents, candidates = _four_intents()

    await agent_picks(llm, intents, candidates, {}, rules=["без свинини"], batches=2)

    assert all(call["правила_гостя"] == ["без свинини"] for call in llm.calls)


async def test_one_batch_lost_does_not_cost_the_other():
    llm = _Batched(fail={"хліб"})
    intents, candidates = _four_intents()

    picks, _queue, _model, _ms, _tokens, batched = await agent_picks(
        llm, intents, candidates, {}, rules=[], batches=2
    )

    assert picks, "друга пачка долетіла — її вибори мусять лишитись"
    assert "хліб" in batched.lost
    assert set(batched.lost).isdisjoint(picks)
    assert "не долетіло 1 з 2" in batched.note


async def test_every_batch_lost_is_the_old_breakage_and_it_raises():
    llm = _Batched(fail={"молоко", "хліб", "кава", "чай"})
    intents, candidates = _four_intents()

    with pytest.raises(RuntimeError):
        await agent_picks(llm, intents, candidates, {}, rules=[], batches=2)


async def test_a_batch_answers_only_for_its_own_intents():

    class _Loud(_Batched):
        async def decide(self, *, system, user, schema, max_tokens, **_):
            decision = await super().decide(
                system=system, user=user, schema=schema, max_tokens=max_tokens
            )
            decision.data["picks"].append({"intent": "чуже", "chosen_id": "999", "qty": 7})
            return decision

    llm = _Loud()
    intents, candidates = _four_intents()

    picks, _queue, _model, _ms, _tokens, _batched = await agent_picks(
        llm, intents, candidates, {}, rules=[], batches=2
    )

    assert "чуже" not in picks


async def test_the_trim_queues_of_two_batches_merge_by_turns():
    llm = _Batched()
    intents, candidates = _four_intents()

    _picks, queue, _model, _ms, _tokens, _batched = await agent_picks(
        llm, intents, candidates, {}, rules=[], batches=2
    )

    mine = {item["намір"] for item in llm.calls[0]["наміри"]}
    assert {name for name, _ in queue} == set(intents)
    assert (queue[0][0] in mine) is not (queue[1][0] in mine)


async def test_the_tokens_of_both_batches_are_counted():
    llm = _Batched()
    intents, candidates = _four_intents()

    *_, tokens, _batched = await agent_picks(llm, intents, candidates, {}, rules=[], batches=2)

    assert tokens == 40


class _ByLabel:

    def __init__(self, *, stray: str | None = None, queue: bool = False) -> None:
        self.calls: list[dict[str, Any]] = []
        self.schemas: list[dict[str, Any]] = []
        self.systems: list[str] = []
        self._stray = stray
        self._queue = queue

    async def decide(self, *, system, user, schema, max_tokens, **_):
        asked = json.loads(user)
        self.calls.append(asked)
        self.schemas.append(schema)
        self.systems.append(system)
        marks = [str(item["ключ"]) for item in asked["наміри"]]
        if self._stray is not None:
            marks = [self._stray, *marks[1:]]
        data: dict[str, Any] = {
            "picks": [{"intent": mark, "chosen_id": "1", "qty": 1} for mark in marks]
        }
        if self._queue:
            data["expendable"] = [{"intent": mark, "why": "рідке"} for mark in marks]
        return Decision(data=data, text="", model="fake", usage=Usage(10, 10), duration_ms=1)


async def test_the_intent_carries_its_label_into_the_prompt():
    intents, candidates = _four_intents()
    llm = _ByLabel()

    await agent_picks(llm, intents, candidates, {}, rules=[])

    asked = llm.calls[0]["наміри"]
    assert [item["ключ"] for item in asked] == ["мо01", "хл02", "ка03", "ча04"]
    assert [item["намір"] for item in asked] == intents


async def test_the_answer_named_by_label_still_fills_the_basket():
    intents, candidates = _four_intents()

    picks, *_ = await agent_picks(_ByLabel(), intents, candidates, {}, rules=[])

    assert sorted(picks) == sorted(intents)


async def test_a_label_from_another_request_costs_one_row_and_names_itself():
    intents, candidates = _four_intents()
    llm = _ByLabel(stray="зз99")

    picks, _queue, _model, _ms, _tokens, batched = await agent_picks(
        llm, intents, candidates, {}, rules=[]
    )

    assert sorted(picks) == ["кава", "хліб", "чай"]
    assert batched.stray == ("зз99",)
    assert "зз99" in batched.note


async def test_the_queue_is_asked_only_under_a_budget():
    intents, candidates = _four_intents()
    llm = _ByLabel()

    await agent_picks(llm, intents, candidates, {}, rules=[])

    assert "expendable" not in llm.schemas[0]["properties"]
    assert "expendable" not in llm.systems[0]

    await agent_picks(llm, intents, candidates, {}, rules=[], budget=Decimal(500))

    assert "expendable" in llm.schemas[-1]["properties"]
    assert "expendable" in llm.systems[-1]


async def test_the_queue_rows_are_named_by_label_too():
    intents, candidates = _four_intents()
    llm = _ByLabel(queue=True)

    _picks, queue, *_ = await agent_picks(
        llm, intents, candidates, {}, rules=[], budget=Decimal(500)
    )

    assert [name for name, _why in queue] == intents


async def test_an_explicit_refusal_does_not_become_the_first_candidate(tmp_path, mcp):
    from datetime import UTC, datetime

    now = datetime(2026, 8, 20, tzinfo=UTC)
    _trust_stand(tmp_path, mcp, now)
    llm = _AskingLLM([{"intent": "Молоко Ферма 2,5%", "chosen_id": "", "qty": 1}])

    assembled = await assemble_list(
        mcp, llm, BuildRequest.model_validate({"mode": "week", "shoppingList": []}), now=now
    )

    assert not any(line.intent == "Молоко Ферма 2,5%" for line in assembled.lines)
    assert not any(item.intent == "Молоко Ферма 2,5%" for item in assembled.basket.postponed)
    (declined,) = [item for item in assembled.basket.declined if item.intent == "Молоко Ферма 2,5%"]
    assert declined.why == "агент не назвав причини"


async def test_the_declined_step_names_every_refusal_and_its_reason(tmp_path, mcp):
    from datetime import UTC, datetime

    now = datetime(2026, 8, 20, tzinfo=UTC)
    _trust_stand(tmp_path, mcp, now)
    llm = _AskingLLM(
        [
            {
                "intent": "Молоко Ферма 2,5%",
                "chosen_id": "",
                "qty": 1,
                "swap": "фасовки 100 г під цей намір немає",
            }
        ]
    )

    assembled = await assemble_list(
        mcp, llm, BuildRequest.model_validate({"mode": "week", "shoppingList": []}), now=now
    )

    step = next(s for s in assembled.basket.trace if s.id == "step-declined")
    assert step.args["відмов"] == 1
    assert step.tag == "-1 поз."
    assert step.tag_tone == "warn"
    assert step.result_summary == (
        f"кандидати були під {step.args['виборів']} намір; під 1 агент сказав «жоден не той»"
    )
    assert step.args["чому"] == {"Молоко Ферма 2,5%": "фасовки 100 г під цей намір немає"}
    assert [(item.intent, item.why) for item in assembled.basket.declined] == [
        ("Молоко Ферма 2,5%", "фасовки 100 г під цей намір немає")
    ]
    assert "Молоко Ферма 2,5%" not in assembled.basket.unresolved


async def test_the_declined_step_says_zero_instead_of_going_quiet(tmp_path, mcp):
    from datetime import UTC, datetime

    now = datetime(2026, 8, 20, tzinfo=UTC)
    _trust_stand(tmp_path, mcp, now)
    llm = _AskingLLM([{"intent": "Молоко Ферма 2,5%", "chosen_id": "101", "qty": 1}])

    assembled = await assemble_list(
        mcp, llm, BuildRequest.model_validate({"mode": "week", "shoppingList": []}), now=now
    )

    step = next(s for s in assembled.basket.trace if s.id == "step-declined")
    assert step.args["відмов"] == 0
    assert step.tag == "жодної"
    assert step.result_summary == (
        f"кандидати були під {step.args['виборів']} намір; під кожен агент щось обрав"
    )
    assert assembled.basket.declined == []


def test_a_refusal_carries_the_reason_the_agent_named_in_swap():
    candidates = {"масло": [_product(101, "Масло Селянське 200 г", 89.9, 20)]}
    picks = {"масло": {"chosen_id": "", "qty": 1, "swap": "фасовки 100 г тут немає"}}

    lines, unresolved, declined = build_lines(["масло"], candidates, {}, picks)

    assert lines == []
    assert unresolved == ["масло"]
    assert declined == {"масло": "фасовки 100 г тут немає"}


def test_the_guests_own_answer_takes_the_ground_from_under_the_refusal():
    candidates = {"томат черрі": [_product(101, "Томат Гордій Черрі 250 г", 71.99, 12)]}
    picks = {"томат черрі": {"chosen_id": "", "qty": 1, "swap": "інший томат черрі на гілці"}}

    lines, unresolved, declined = build_lines(
        ["томат черрі"], candidates, {}, picks, answered=frozenset({"томат черрі"})
    )

    assert declined == {}, "підставу відмови зняв сам гість"
    assert unresolved == []
    [line] = lines
    assert str(line.product["externalProductId"]) == "101"


def test_words_typed_by_hand_do_not_take_that_ground():
    candidates = {"томат черрі": [_product(101, "Томат Гордій Черрі 250 г", 71.99, 12)]}
    picks = {"томат черрі": {"chosen_id": "", "qty": 1, "swap": "інший томат черрі на гілці"}}

    lines, unresolved, declined = build_lines(["томат черрі"], candidates, {}, picks)

    assert lines == []
    assert unresolved == ["томат черрі"]
    assert declined == {"томат черрі": "інший томат черрі на гілці"}


def test_a_refusal_without_a_reason_says_so_instead_of_going_silent():
    candidates = {"масло": [_product(101, "Масло Селянське 200 г", 89.9, 20)]}
    lines, _, declined = build_lines(
        ["масло"], candidates, {}, {"масло": {"chosen_id": "", "qty": 1}}
    )

    assert lines == []
    assert declined == {"масло": NO_DECLINE_WHY}
    assert NO_DECLINE_WHY == "агент не назвав причини"


def test_nothing_on_the_shelf_is_not_a_refusal():
    lines, unresolved, declined = build_lines(["шафран"], {"шафран": []}, {}, {})

    assert lines == []
    assert unresolved == ["шафран"]
    assert declined == {}


def test_a_kept_article_that_left_the_shelf_is_not_a_refusal_either():
    candidates = {"молоко": [_product(101, "Молоко Ферма 2,5%", 53.49, 20)]}
    _lines, unresolved, declined = build_lines(
        ["молоко"], candidates, {}, {}, must_match={"молоко": "999"}
    )

    assert unresolved == ["молоко"]
    assert declined == {}


async def test_a_missing_pick_still_falls_back_to_the_shelf():
    from komora.agent.basket import build_lines

    options = [_product(1, "Молоко Ферма 2,5%", 40.0, 10)]
    lines, unresolved, _ = build_lines(["молоко"], {"молоко": options}, hints={}, picks={})

    assert not unresolved
    assert [line.intent for line in lines] == ["молоко"]


def test_the_apostrophe_does_not_break_a_two_word_kind_phrase():
    assert related_to("мясо мідій", "М'ясо мідій «Премія»")
    assert related_to("травяний чай", "Чай трав'яний Ліптон")


def test_the_phone_apostrophe_matches_too():
    assert related_to("м\u2019ясо мідій", "М'ясо мідій «Премія»")


def test_the_apostrophe_cut_does_not_glue_different_kinds():
    assert not related_to("молоко", "Шоколад з молоком")
    assert not related_to("чай", "Фільтри для чаю")


def test_the_pantry_merge_key_keeps_its_apostrophe():
    assert kind_key("М'ясо мідій «Премія»") == "м'ясо мідій"


async def test_the_node_tier_reaches_the_prompt_and_reorders_the_candidates():
    seen: dict[str, Any] = {}

    class _Fake:
        async def decide(self, *, system, user, schema, max_tokens, **_):
            seen["user"] = json.loads(user)
            return Decision(
                data={"picks": []}, text="", model="fake", usage=Usage(1, 1), duration_ms=1
            )

    history = [
        HistoryItem(
            lager_id="301",
            name="Рулет курячий «Алан» домашній",
            unit="шт",
            receipts=5,
            qty_total=Decimal(5),
        )
    ]
    candidates = {
        "рулет": [
            _product(401, "Рулет Делікатесний рибний холодного копчення", 159.9, 30),
            _product(402, "Рулет «Фарро» курячий к/в", 121.5, 30),
        ]
    }
    kinds = {
        "301": frozenset({"m-iasni-rulety-4747"}),
        "401": frozenset({"kopchena-ryba-ta-moreprodukty-4442"}),
        "402": frozenset({"m-iasni-rulety-4747"}),
    }

    await agent_picks(_Fake(), ["рулет"], candidates, {"рулет": history}, rules=[], kinds=kinds)
    with_map = [c["id"] for c in seen["user"]["наміри"][0]["кандидати"]]

    await agent_picks(_Fake(), ["рулет"], candidates, {"рулет": history}, rules=[])
    without_map = [c["id"] for c in seen["user"]["наміри"][0]["кандидати"]]

    assert with_map[0] == "402", "м'ясний рулет мусить стояти перед рибним"
    assert without_map[0] == "401", "без карти лишається порядок чужої видачі"


async def test_a_cold_map_changes_nothing_in_the_prompt():
    seen: dict[str, Any] = {}

    class _Fake:
        async def decide(self, *, system, user, schema, max_tokens, **_):
            seen.setdefault("orders", []).append(
                [c["id"] for c in json.loads(user)["наміри"][0]["кандидати"]]
            )
            return Decision(
                data={"picks": []}, text="", model="fake", usage=Usage(1, 1), duration_ms=1
            )

    history = [
        HistoryItem(
            lager_id="301", name="Рулет курячий", unit="шт", receipts=5, qty_total=Decimal(5)
        )
    ]
    candidates = {
        "рулет": [
            _product(401, "Рулет рибний", 159.9, 30),
            _product(402, "Рулет курячий", 121.5, 30),
        ]
    }
    await agent_picks(_Fake(), ["рулет"], candidates, {"рулет": history}, rules=[], kinds={})
    await agent_picks(_Fake(), ["рулет"], candidates, {"рулет": history}, rules=[])
    assert seen["orders"][0] == seen["orders"][1]


def test_a_receipt_time_without_a_zone_is_KYIV_not_utc():
    moment = _order_moment({"createdAt": "2026-08-16T20:09:01"})
    assert moment is not None
    assert moment.utcoffset() == timedelta(hours=3), "літній Київ -- UTC+3"
    assert moment.astimezone(UTC).hour == 17


def test_a_purchase_after_midnight_stays_in_its_own_day():
    moment = _order_moment({"createdAt": "2026-08-17T01:30:00"})
    assert moment is not None
    assert moment.astimezone(UTC).date().isoformat() == "2026-08-16"


def test_a_receipt_time_WITH_a_zone_is_left_alone():
    moment = _order_moment({"createdAt": "2026-08-16T15:40:00+00:00"})
    assert moment is not None
    assert moment.utcoffset() == timedelta(0)


def test_a_receipt_without_a_time_is_not_a_crash():
    assert _order_moment({}) is None
    assert _order_moment({"createdAt": ""}) is None
    assert _order_moment({"createdAt": "коли завгодно"}) is None


def test_a_catalogue_name_with_a_latin_letter_is_still_related_to_the_word():
    assert related_to("хліб", "X\u043bі\u0431 Київський"), "латинська перша літера"
    assert related_to("хліб", "Хліб Київський"), "звичайний не має постраждати"


def test_the_alphabet_cut_does_not_glue_different_words():
    assert not related_to("чай", "Часник свіжий")


class TestIntentCacheCeiling:

    def setup_method(self) -> None:
        forget_intents()

    def teardown_method(self) -> None:
        forget_intents()

    def _naming(self, word: str) -> Naming:
        return Naming(intent=word, subtype="", drink=None, drink_known=False)

    def test_the_cache_stops_growing(self) -> None:
        from komora.agent import basket

        for number in range(basket.INTENT_CACHE_MAX + 50):
            basket._cache_names({f"Товар {number}": self._naming(f"товар {number}")})

        assert len(basket._INTENT_CACHE) == basket.INTENT_CACHE_MAX

    def test_the_oldest_goes_first_and_a_read_saves_a_row(self) -> None:
        from komora.agent import basket

        basket._cache_names({"Молоко Ферма": self._naming("молоко")})
        for number in range(basket.INTENT_CACHE_MAX - 1):
            basket._cache_names({f"Товар {number}": self._naming(f"товар {number}")})
            assert basket._cached_name("Молоко Ферма") is not None

        basket._cache_names({"Ще один": self._naming("ще один")})

        assert basket._cached_name("Молоко Ферма") is not None, "активна назва лишилась"
        assert basket._cached_name("Товар 0") is None, "найдавніша вилетіла першою"


def test_a_row_from_the_pantry_is_not_explained_by_an_intent_nobody_typed() -> None:
    from komora.agent.basket import PANTRY_MANUAL_WHY, reason_text

    common = {"chosen": {"name": "Лікер Morandini Limoncello"}, "options": [], "hint": None}
    assert PANTRY_MANUAL_WHY == "ти сам додав це в комору"
    assert (
        reason_text("під_намір", matched=False, subject="вид з комори", **common)
        == "під вид з комори відповідає точніше за решту"
    )
    assert (
        reason_text("єдине", matched=False, subject="вид з комори", **common)
        == "інших кандидатів під вид з комори не знайшлось"
    )
    plain = reason_text("під_намір", matched=False, **common)
    assert plain == "під намір відповідає точніше за решту"
    only = reason_text("єдине", matched=False, **common)
    assert only == "інших кандидатів під цей намір не знайшлось"


async def test_the_chip_learns_the_pool_before_the_basket_is_built(tmp_path, mcp):
    from datetime import UTC, datetime

    now = datetime(2026, 8, 20, tzinfo=UTC)
    _trust_stand(tmp_path, mcp, now)

    pantry = await pantry_live(mcp, now=now)

    assert pantry.target_pool == 3
    assert pantry.target_estimate == Decimal("150")


async def test_the_chip_and_the_target_step_count_one_and_the_same_pool(tmp_path, mcp):
    from datetime import UTC, datetime

    now = datetime(2026, 8, 20, tzinfo=UTC)
    _trust_stand(tmp_path, mcp, now)

    pantry = await pantry_live(mcp, now=now)
    assembled = await assemble_list(
        mcp,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week", "budget": 400}),
        now=now,
    )
    target = next(s for s in assembled.basket.trace if s.id == "step-target")
    needs = next(s for s in assembled.basket.trace if s.id == "step-needs")

    assert target.args["пул"] == 1, "кетчуп: цикл недоведений, за потребу він не їде"
    assert needs.args["due"] == 2, "молоко і морозиво вже закінчились за циклом"
    assert pantry.target_pool == target.args["пул"] + needs.args["due"]


class _UnderstandingLLM:

    model = "fake-model"

    def __init__(
        self, *, questions=(), add=(), drop=(), plan=(), cut=(), picks=(), fail=False
    ) -> None:
        self.cut = list(cut)
        self.questions = list(questions)
        self.add = list(add)
        self.drop = list(drop)
        self.plan = list(plan)
        self.picks = list(picks)
        self.fail = fail
        self.understand_payload: dict | None = None
        self.pick_payload: dict | None = None

    async def decide(self, *, system, user, schema, schema_name="decision", max_tokens=2048, **_):
        payload = json.loads(user)
        if "questions" in schema["properties"]:
            if self.fail:
                raise RuntimeError("модель мовчить")
            self.understand_payload = payload
            data = {
                "questions": self.questions,
                "cut": self.cut,
                "add": self.add,
                "drop": self.drop,
                "plan": self.plan,
            }
        elif "add" in schema["properties"]:
            data = {"add": [], "skip": []}
        else:
            self.pick_payload = payload
            data = {"picks": self.picks}
        return Decision(data=data, text="", model=self.model, usage=Usage(1, 1), duration_ms=1)


def _understand_step(assembled):
    return next(s for s in assembled.basket.trace if s.id == "step-understand")


async def test_the_stage_stands_in_the_trace_even_when_it_changed_nothing(mcp):
    llm = _UnderstandingLLM(
        picks=[{"intent": "молоко", "chosen_id": "101", "qty": 1, "reason": "звичне"}]
    )
    assembled = await assemble_list(
        mcp,
        llm=llm,
        request=BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко"]}),
    )

    step = _understand_step(assembled)
    assert "нічого не змінив" in step.result_summary
    assert step.tag == "без змін"


async def test_a_silent_stage_says_so_instead_of_pretending_it_worked(mcp):
    llm = _UnderstandingLLM(
        fail=True,
        picks=[{"intent": "молоко", "chosen_id": "101", "qty": 1, "reason": "звичне"}],
    )
    assembled = await assemble_list(
        mcp,
        llm=llm,
        request=BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко"]}),
    )

    step = _understand_step(assembled)
    assert step.tag == "не спрацював" and step.tag_tone == "warn"
    assert assembled.lines, "етап не спрацював — але кошик зібрався"


async def test_what_the_stage_added_becomes_a_line_and_explains_itself(mcp):
    llm = _UnderstandingLLM(
        add=[{"intent": "кава", "why": "до столу"}],
        picks=[
            {"intent": "молоко", "chosen_id": "101", "qty": 1, "reason": "звичне"},
            {"intent": "кава", "chosen_id": "201", "qty": 1, "reason": "до столу"},
        ],
    )
    assembled = await assemble_list(
        mcp,
        llm=llm,
        request=BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко"]}),
    )

    assert "кава" in {line.intent for line in assembled.lines}
    assert _understand_step(assembled).tag == "+1"


async def test_the_stage_sees_what_the_pantry_already_knows_so_it_does_not_ask_about_it(mcp):
    llm = _UnderstandingLLM(
        picks=[{"intent": "кава", "chosen_id": "201", "qty": 1, "reason": "звичне"}]
    )
    await assemble_list(
        mcp,
        llm=llm,
        request=BuildRequest.model_validate({"mode": "week", "shoppingList": ["кава"]}),
    )

    assert llm.understand_payload is not None
    assert llm.understand_payload["режим"] == "на тиждень"
    assert llm.understand_payload["комора_знає"]["видів_під_наглядом"] >= 1
    assert "Молоко Ферма 2,5%" in llm.understand_payload["комора_знає"]["закінчується"]
    assert llm.understand_payload["слова_гостя"] == ["кава"]


async def test_a_question_without_a_channel_is_not_asked_at_all(mcp):
    llm = _UnderstandingLLM(
        questions=[
            {"ask": "Готуєш сам?", "options": [{"label": "так"}, {"label": "ні"}]},
        ],
        picks=[{"intent": "молоко", "chosen_id": "101", "qty": 1, "reason": "звичне"}],
    )
    assembled = await assemble_list(
        mcp,
        llm=llm,
        request=BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко"]}),
    )

    step = next(s for s in assembled.basket.trace if s.id == "step-ask")
    assert step.question is None and step.tag == "без діалогу"


async def test_the_answer_reaches_the_choice_and_the_style_reaches_the_task(mcp):
    llm = _UnderstandingLLM(
        questions=[
            {
                "ask": "Готуєш сам чи береш готове?",
                "options": [
                    {"label": "готую сам", "style": "cooking", "intents": ["кава"]},
                    {"label": "беру готове", "style": "ready"},
                ],
            }
        ],
        picks=[
            {"intent": "молоко", "chosen_id": "101", "qty": 1, "reason": "звичне"},
            {"intent": "кава", "chosen_id": "201", "qty": 1, "reason": "з відповіді"},
        ],
    )

    async def _answer(question_id: str, seconds: float) -> str:
        assert seconds > 0
        return "o1"

    assembled = await assemble_list(
        mcp,
        llm=llm,
        request=BuildRequest.model_validate(
            {"mode": "event", "shoppingList": ["молоко"], "occasionPeople": 4}
        ),
        answer_of=_answer,
    )

    assert llm.pick_payload is not None
    assert any("готую сам" in rule for rule in llm.pick_payload["правила_гостя"])
    assert "сировин" in llm.pick_payload["що_означає_привід"].casefold()
    assert "кава" in {line.intent for line in assembled.lines}
    said = next(s for s in assembled.basket.trace if s.id == "step-answer")
    assert "готую сам" in said.result_summary and said.tag == "відповідь"


async def test_an_answer_that_never_came_names_the_question_and_goes_on(mcp):
    llm = _UnderstandingLLM(
        questions=[
            {"ask": "Готуєш сам?", "options": [{"label": "так"}, {"label": "ні"}]},
        ],
        picks=[{"intent": "молоко", "chosen_id": "101", "qty": 1, "reason": "звичне"}],
    )

    async def _silent(question_id: str, seconds: float) -> str | None:
        return None

    assembled = await assemble_list(
        mcp,
        llm=llm,
        request=BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко"]}),
        answer_of=_silent,
    )

    said = next(s for s in assembled.basket.trace if s.id == "step-answer")
    assert "не дочекався" in said.result_summary and "Готуєш сам?" in said.result_summary
    assert assembled.lines, "без відповіді кошик усе одно збирається"


async def test_the_question_rides_the_progress_channel_as_a_step(mcp):
    llm = _UnderstandingLLM(
        questions=[
            {
                "ask": "Готуєш сам?",
                "why": "від цього залежить, що брати",
                "options": [{"label": "так"}, {"label": "ні"}],
            }
        ],
        picks=[{"intent": "молоко", "chosen_id": "101", "qty": 1, "reason": "звичне"}],
    )

    async def _silent(question_id: str, seconds: float) -> str | None:
        return None

    assembled = await assemble_list(
        mcp,
        llm=llm,
        request=BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко"]}),
        answer_of=_silent,
    )

    step = next(s for s in assembled.basket.trace if s.id == "step-ask")
    assert step.question is not None
    assert step.question.ask == "Готуєш сам?"
    assert [option.label for option in step.question.options] == ["так", "ні"]
    assert step.question.wait_s == int(ANSWER_WAIT_S)


async def test_the_stage_may_move_a_gated_step_of_the_plan(mcp):
    llm = _UnderstandingLLM(
        plan=[{"change": "skip", "step": "shelf.by_article", "why": "усе своє вже в видачі"}],
        picks=[{"intent": "молоко", "chosen_id": "101", "qty": 1, "reason": "звичне"}],
    )
    assembled = await assemble_list(
        mcp,
        llm=llm,
        request=BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко"]}),
    )

    step = _understand_step(assembled)
    assert "правок плану 1" in step.result_summary
    assert step.args["правки плану"] == ["skip shelf.by_article"]
    assert not any(s.id == "step-article" for s in assembled.basket.trace)


GOLDEN = Path(__file__).parent / "fixtures" / "route_golden.json"


def _snapshot(assembled) -> dict:
    basket = assembled.basket
    return {
        "кроки": [
            {"id": step.id, "tool": step.tool, "фраза": step.result_summary, "ярлик": step.tag}
            for step in basket.trace
        ],
        "рядки": [
            {
                "артикул": line.external_product_id,
                "назва": line.name,
                "кількість": str(line.qty),
                "ціна": str(line.price),
                "причина": str(line.reason),
                "пояснення": line.explanation,
                "ризик": line.at_risk,
            }
            for line in basket.lines
        ],
        "сума": str(basket.total),
        "не знайшлось": list(basket.unresolved),
        "відмови": [d.intent for d in basket.declined],
        "питання": [q.intent for q in basket.questions],
        "блокери": list(basket.blockers),
    }


async def test_the_pipeline_gives_exactly_what_it_gave_before_the_steps_moved(mcp):
    request = BuildRequest.model_validate(
        {"mode": "week", "shoppingList": ["молоко", "шафран", "кава"]}
    )
    assembled = await assemble_list(
        mcp, llm=None, request=request, now=datetime(2026, 8, 14, 9, tzinfo=UTC)
    )

    now = _snapshot(assembled)
    if not GOLDEN.exists():  # pragma: no cover -- перше зняття, руками
        GOLDEN.write_text(json.dumps(now, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    was = json.loads(GOLDEN.read_text(encoding="utf-8"))

    assert now["кроки"] == was["кроки"], "трейс розійшовся зі знімком до рефакторингу"
    assert now["рядки"] == was["рядки"], "кошик розійшовся зі знімком до рефакторингу"
    assert {k: now[k] for k in ("сума", "не знайшлось", "відмови", "питання", "блокери")} == {
        k: was[k] for k in ("сума", "не знайшлось", "відмови", "питання", "блокери")
    }


async def test_the_model_re_reads_the_raw_text_and_the_comma_stops_being_a_border(mcp):
    llm = _UnderstandingLLM(
        cut=["морозиво хрещатик фісташка"],
        picks=[{"intent": "морозиво хрещатик фісташка", "chosen_id": "101", "qty": 1}],
    )
    assembled = await assemble_list(
        mcp,
        llm=llm,
        request=BuildRequest.model_validate(
            {
                "mode": "week",
                "shoppingList": ["морозиво", "хрещатик", "фісташка"],
                "listText": "морозиво, хрещатик, фісташка",
            }
        ),
    )

    assert llm.understand_payload is not None
    assert llm.understand_payload["набране_гостем"] == "морозиво, хрещатик, фісташка"
    assert "морозиво хрещатик фісташка" in assembled.basket.unresolved
    assert "хрещатик" not in assembled.basket.unresolved

    step = _understand_step(assembled)
    assert step.args["переріз тексту"] == 1


async def test_what_the_cut_did_not_take_reaches_the_guest_by_name(mcp):
    llm = _UnderstandingLLM(
        cut=["молоко"],
        picks=[{"intent": "молоко", "chosen_id": "101", "qty": 1}],
    )
    assembled = await assemble_list(
        mcp,
        llm=llm,
        request=BuildRequest.model_validate(
            {
                "mode": "week",
                "shoppingList": ["привіт", "молоко", "0501234567"],
                "listText": "привіт, молоко, 0501234567",
            }
        ),
    )

    step = _understand_step(assembled)
    assert step.args["не взяв із тексту"] == ["привіт", "0501234567"]


def _milk_hint(now: datetime, *, keeps: Keeps | None, every: int = 4) -> HistoryItem:
    return HistoryItem(
        lager_id="101",
        name="Молоко Ферма 2,5%",
        unit="шт",
        receipts=4,
        qty_total=Decimal(4),
        recent_receipts=4,
        qty_recent=Decimal(4),
        moments=[now - timedelta(days=every * step) for step in (3, 2, 1, 0)],
        keeps=keeps,
    )


def test_shelf_life_rides_the_mandate_computed_from_the_cycle():
    now = datetime(2026, 8, 23, tzinfo=UTC)
    candidates = {
        "молоко": [
            _product(101, "Молоко Ферма 2,5%", 53.49, 9),
            _product(102, "Молоко Яготинське 2,6%", 75.99, 40),
        ]
    }
    lines, _, _ = build_lines(
        ["молоко"],
        candidates,
        {"молоко": _milk_hint(now, keeps=Keeps.DAYS)},
        picks={},
        slot_day=date(2026, 8, 24),
    )
    line = lines[0]
    assert line.shelf_life == "термін придатності не менше ніж до 30.08", "24.08 + цикл 4 + буфер 2"
    assert line.mandate is not None
    assert line.shelf_life in line.mandate, "вимога їде збирачу, а не лишається в рядку"


def test_a_kind_that_keeps_for_months_asks_for_nothing():
    now = datetime(2026, 8, 23, tzinfo=UTC)
    candidates = {
        "молоко": [
            _product(101, "Молоко Ферма 2,5%", 53.49, 9),
            _product(102, "Молоко Яготинське 2,6%", 75.99, 40),
        ]
    }
    lines, _, _ = build_lines(
        ["молоко"],
        candidates,
        {"молоко": _milk_hint(now, keeps=Keeps.MONTHS)},
        picks={},
        slot_day=date(2026, 8, 24),
    )
    assert lines[0].shelf_life is None
    assert lines[0].mandate is not None and "термін" not in lines[0].mandate


def test_the_requirement_rides_with_the_default_mandate():
    now = datetime(2026, 8, 23, tzinfo=UTC)
    trace = Tracer()
    lines, _, _ = build_lines(
        ["молоко"],
        {"молоко": [_product(101, "Молоко Ферма 2,5%", 53.49, 40)]},
        {"молоко": _milk_hint(now, keeps=Keeps.DAYS)},
        picks={},
        slot_day=date(2026, 8, 24),
        trace=trace,
    )
    assert lines[0].shelf_life is not None, "порахована"
    assert lines[0].mandate is not None and "термін" in lines[0].mandate
    step = next(s for s in trace.steps if s.id == "step-shelf-life")
    assert "вимога до терміну на 1 рядках" in step.result_summary


def test_the_shelf_life_step_speaks_even_when_nothing_was_asked():
    now = datetime(2026, 8, 23, tzinfo=UTC)
    trace = Tracer()
    build_lines(
        ["молоко"],
        {"молоко": [_product(101, "Молоко Ферма 2,5%", 53.49, 9)]},
        {"молоко": _milk_hint(now, keeps=None)},
        picks={},
        slot_day=date(2026, 8, 24),
        trace=trace,
    )
    step = next(s for s in trace.steps if s.id == "step-shelf-life")
    assert "жоден вид" in step.result_summary


def test_without_a_slot_no_requirement_and_no_step():
    now = datetime(2026, 8, 23, tzinfo=UTC)
    trace = Tracer()
    lines, _, _ = build_lines(
        ["молоко"],
        {"молоко": [_product(101, "Молоко Ферма 2,5%", 53.49, 9)]},
        {"молоко": _milk_hint(now, keeps=Keeps.DAYS)},
        picks={},
        trace=trace,
    )
    assert lines[0].shelf_life is None
    assert not [s for s in trace.steps if s.id == "step-shelf-life"]


def test_amount_text_rounds_the_receipt_average_to_hundredths():
    from komora.agent.basket import _amount_text

    assert _amount_text(Decimal("0.89") / 3) == "0,3"
    assert _amount_text(Decimal("1.255")) == "1,26"
    assert _amount_text(Decimal("4")) == "4"
    assert _amount_text(Decimal("1.5")) == "1,5"
