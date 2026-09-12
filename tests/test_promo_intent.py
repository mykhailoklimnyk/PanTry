from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from komora.agent.basket import (
    PROMO_WAIT_WHY,
    HistoryItem,
    assemble_list,
    history_kinds,
    load_history,
    receipts_pantry,
)
from komora.agent.llm import Decision, Usage
from komora.api.schemas import BuildRequest
from komora.core.promo import Purchase
from komora.mcp.client import SilpoMCP

NOW = datetime(2026, 9, 2, tzinfo=UTC)

SLOT = {
    "start": "2026-09-02T11:30:00+00:00",
    "end": "2026-09-02T13:00:00+00:00",
    "available": True,
    "deliveryType": "DeliveryHome",
    "deliveryCost": 89,
    "deliveryCostMap": [{"cost": 59, "fromOrderCost": 1199}],
    "minOrderCost": 599,
    "maxWeight": 50,
}

BEER = "Пиво Hike Blanche світле з/б"
MILK = "Молоко Ферма 2,5%"


def _card(pid: int, name: str, price: float, old: float | None = None) -> dict:
    return {
        "id": f"00000000-0000-4000-8000-{pid:012d}",
        "name": name,
        "slug": f"slug-{pid}",
        "price": price,
        "oldPrice": old,
        "stock": 40,
        "available": True,
        "image": None,
        "weighted": False,
        "step": 1,
        "displayRatio": "1шт",
        "companyId": "00000000-0000-4000-8000-000000000001",
        "branchId": "00000000-0000-4000-8000-000000000002",
        "externalProductId": pid,
    }


def _bought(days_ago: int, lager: int, name: str, *, price: float, qty: int, seen: float) -> dict:
    return {
        "createdAt": (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%d"),
        "products": [
            {
                "lagerId": lager,
                "name": name,
                "unit": "0,5л" if lager == 501 else "шт",
                "quantity": qty,
                "price": price,
                "catalogProduct": {"price": seen},
            }
        ],
    }


def _beer_orders(*, last_days_ago: int) -> list[dict]:
    days = [last_days_ago + 60, last_days_ago + 45, last_days_ago + 30, last_days_ago + 15]
    orders = [_bought(day, 501, BEER, price=29.99, qty=6, seen=50.99) for day in days]
    orders.append(_bought(last_days_ago, 501, BEER, price=46.49, qty=2, seen=50.99))
    return orders


def _milk_orders() -> list[dict]:
    return [_bought(day, 101, MILK, price=53, qty=1, seen=53) for day in (30, 23, 16, 9)]


def _stand(tmp_path, *, orders: list[dict], beer_on_shelf: dict | None) -> SilpoMCP:
    (tmp_path / "silpo_get_time_slots.json").write_text(
        json.dumps({"slots": [SLOT]}), encoding="utf-8"
    )
    (tmp_path / "silpo_get_my_offline_orders.json").write_text(
        json.dumps({"orders": orders}), encoding="utf-8"
    )
    (tmp_path / "silpo_get_my_shopping_cart.json").write_text(
        json.dumps({"shoppingCartId": None}), encoding="utf-8"
    )
    (tmp_path / "silpo_find_products_batch.json").write_text(
        json.dumps(
            {
                "queries": [
                    {"query": BEER, "products": [beer_on_shelf] if beer_on_shelf else []},
                    {"query": MILK, "products": [_card(101, MILK, 53.49)]},
                ]
            }
        ),
        encoding="utf-8",
    )
    return SilpoMCP(fixtures_dir=tmp_path)


_WEEK_WITH_BAR = BuildRequest.model_validate({"mode": "week", "barInWeek": True})


@pytest.mark.anyio
async def test_each_purchase_is_remembered_with_the_catalogue_price_beside_it(tmp_path):
    mcp = _stand(tmp_path, orders=_beer_orders(last_days_ago=20), beer_on_shelf=None)
    history, *_ = await load_history(mcp, SLOT, None, now=NOW)
    beer = next(item for item in history if item.lager_id == "501")
    assert len(beer.purchases) == 5
    assert beer.purchases[0].seen == Decimal("50.99")
    assert {purchase.qty for purchase in beer.purchases} == {Decimal(6), Decimal(2)}
    assert beer.promo.mostly
    assert beer.promo.usual_qty == Decimal(6)


def test_merging_sku_twins_carries_the_purchases_along():
    first = HistoryItem(
        lager_id="1",
        name="Пиво Hike Blanche світле з/б",
        unit="0,5л",
        receipts=2,
        purchases=[Purchase(Decimal("29.99"), Decimal(6), Decimal("50.99"))] * 2,
    )
    second = HistoryItem(
        lager_id="2",
        name="Пиво Hike Blanche світле ПЕТ",
        unit="0,5л",
        receipts=1,
        purchases=[Purchase(Decimal("31.99"), Decimal(6), Decimal("50.99"))],
    )
    (kind,) = history_kinds([first, second])
    assert len(kind.purchases) == 3
    assert kind.promo.mostly


def test_the_pantry_row_says_the_habit_in_words():
    beer = HistoryItem(
        lager_id="501",
        name=BEER,
        unit="0,5л",
        receipts=5,
        qty_total=Decimal(26),
        moments=[NOW - timedelta(days=day) for day in (80, 65, 50, 35, 20)],
        purchases=[Purchase(Decimal("29.99"), Decimal(6), Decimal("50.99"))] * 4
        + [Purchase(Decimal("46.49"), Decimal(2), Decimal("50.99"))],
    )
    plain = HistoryItem(
        lager_id="101",
        name=MILK,
        unit="шт",
        receipts=4,
        qty_total=Decimal(4),
        moments=[NOW - timedelta(days=day) for day in (30, 23, 16, 9)],
        purchases=[Purchase(Decimal(53), Decimal(1), Decimal(53))] * 4,
    )
    rows = {row.label: row for row in receipts_pantry([beer, plain], now=NOW)}
    assert rows[BEER].promo == "береш по акції: 4 з 5, зазвичай по 6"
    assert rows[MILK].promo is None


@pytest.mark.anyio
async def test_without_a_sale_on_the_shelf_the_kind_waits_instead_of_riding(tmp_path):
    mcp = _stand(
        tmp_path,
        orders=_beer_orders(last_days_ago=20) + _milk_orders(),
        beer_on_shelf=_card(501, BEER, 50.99),
    )
    assembled = await assemble_list(mcp, llm=None, request=_WEEK_WITH_BAR, now=NOW)

    assert [line.name for line in assembled.basket.lines] == [MILK]
    waiting = [p for p in assembled.basket.postponed if p.intent == BEER]
    assert len(waiting) == 1
    assert waiting[0].reason == PROMO_WAIT_WHY
    assert waiting[0].refillable is False
    assert BEER not in assembled.basket.unresolved
    step = next(s for s in assembled.basket.trace if s.id == "step-promo")
    assert step.tag == "чекає акції"
    assert "без акції 1" in step.result_summary


@pytest.mark.anyio
async def test_with_a_sale_the_kind_rides_in_the_sale_quantity(tmp_path):
    mcp = _stand(
        tmp_path,
        orders=_beer_orders(last_days_ago=20) + _milk_orders(),
        beer_on_shelf=_card(501, BEER, 29.99, old=50.99),
    )
    assembled = await assemble_list(mcp, llm=None, request=_WEEK_WITH_BAR, now=NOW)

    beer = next(line for line in assembled.basket.lines if line.name == BEER)
    assert beer.qty == 6
    assert beer.base_price == Decimal("50.99")
    assert beer.explanation == "береш по акції (4 з 5) — зараз акція: було 50.99, стало 29.99"
    assert all(p.intent != BEER for p in assembled.basket.postponed)
    plan = next(line for line in assembled.lines if line.intent == BEER)
    assert plan.promo is True
    step = next(s for s in assembled.basket.trace if s.id == "step-promo")
    assert step.tag == "+1"
    assert "беру акційною кількістю" in step.result_summary


@pytest.mark.anyio
async def test_a_kind_bought_recently_is_not_even_looked_for(tmp_path):
    mcp = _stand(
        tmp_path,
        orders=_beer_orders(last_days_ago=5) + _milk_orders(),
        beer_on_shelf=_card(501, BEER, 29.99, old=50.99),
    )
    assembled = await assemble_list(mcp, llm=None, request=_WEEK_WITH_BAR, now=NOW)

    assert [line.name for line in assembled.basket.lines] == [MILK]
    assert all(p.intent != BEER for p in assembled.basket.postponed)
    step = next(s for s in assembled.basket.trace if s.id == "step-promo")
    assert step.tag == "не час"
    assert "жодному ще не час" in step.result_summary


@pytest.mark.anyio
async def test_a_sale_kind_never_rides_as_a_cycle_need(tmp_path):
    mcp = _stand(
        tmp_path,
        orders=_beer_orders(last_days_ago=20) + _milk_orders(),
        beer_on_shelf=_card(501, BEER, 29.99, old=50.99),
    )
    assembled = await assemble_list(mcp, llm=None, request=_WEEK_WITH_BAR, now=NOW)
    beer = next(line for line in assembled.basket.lines if line.name == BEER)
    assert "за циклом" not in beer.explanation
    needs = next(s for s in assembled.basket.trace if s.id == "step-needs")
    assert "1 по акції поза стелею" in needs.result_summary


@pytest.mark.anyio
async def test_the_top_up_to_a_target_does_not_take_a_sale_kind_at_full_price(tmp_path):
    mcp = _stand(
        tmp_path,
        orders=_beer_orders(last_days_ago=5) + _milk_orders(),
        beer_on_shelf=_card(501, BEER, 50.99),
    )
    assembled = await assemble_list(
        mcp,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week", "budget": 1500, "barInWeek": True}),
        now=NOW,
    )
    assert all(line.name != BEER for line in assembled.basket.lines)
    target = next(s for s in assembled.basket.trace if s.id == "step-target")
    assert "по акції не добираю 1" in target.result_summary


@pytest.mark.anyio
async def test_a_sale_kind_missing_from_the_shelf_names_its_own_reason(tmp_path):
    mcp = _stand(
        tmp_path,
        orders=_beer_orders(last_days_ago=20) + _milk_orders(),
        beer_on_shelf=None,
    )
    assembled = await assemble_list(mcp, llm=None, request=_WEEK_WITH_BAR, now=NOW)
    missing = next(p for p in assembled.basket.postponed if p.intent == BEER)
    assert missing.reason.startswith("береш по акції, але на цей слот")


@pytest.mark.anyio
async def test_a_weighed_kind_is_never_a_sale_intent(tmp_path):
    cucumbers = "Огірок екстра"
    orders = [
        {
            "createdAt": (NOW - timedelta(days=day)).strftime("%Y-%m-%d"),
            "products": [
                {
                    "lagerId": 601,
                    "name": cucumbers,
                    "unit": "кг",
                    "quantity": 0.5,
                    "price": price,
                    "catalogProduct": {"price": 90},
                }
            ],
        }
        for day, price in ((30, 40), (23, 45), (16, 50), (9, 60))
    ]
    mcp = _stand(tmp_path, orders=orders + _milk_orders(), beer_on_shelf=None)
    batch = json.loads((tmp_path / "silpo_find_products_batch.json").read_text(encoding="utf-8"))
    batch["queries"].append(
        {"query": cucumbers, "products": [{**_card(601, cucumbers, 89.0), "weighted": True}]}
    )
    (tmp_path / "silpo_find_products_batch.json").write_text(json.dumps(batch), encoding="utf-8")

    assembled = await assemble_list(mcp, llm=None, request=_WEEK_WITH_BAR, now=NOW)
    assert all(p.reason != PROMO_WAIT_WHY for p in assembled.basket.postponed)
    assert all(s.id != "step-promo" for s in assembled.basket.trace)


class _RefusingLLM:

    model = "fake-model"

    def __init__(self, *, refuse: str) -> None:
        self.refuse = refuse
        self.systems: list[str] = []

    async def decide(self, *, system, user, schema, schema_name="decision", max_tokens=2048, **_):
        self.systems.append(system)
        asked = json.loads(user)
        picks = [
            {
                "intent": intent["ключ"],
                "chosen_id": ""
                if intent["намір"] == self.refuse
                else str(intent["кандидати"][0]["id"]),
                "qty": 1,
            }
            for intent in asked["наміри"]
        ]
        return Decision(
            data={"picks": picks}, text="", model=self.model, usage=Usage(1, 1), duration_ms=1
        )


@pytest.mark.anyio
async def test_the_agents_refusal_on_a_sale_kind_is_waiting_and_not_a_missing_shelf(tmp_path):
    mcp = _stand(
        tmp_path,
        orders=_beer_orders(last_days_ago=20) + _milk_orders(),
        beer_on_shelf=_card(501, BEER, 50.99),
    )
    llm = _RefusingLLM(refuse=BEER)
    assembled = await assemble_list(mcp, llm=llm, request=_WEEK_WITH_BAR, now=NOW)

    waiting = next(p for p in assembled.basket.postponed if p.intent == BEER)
    assert waiting.reason == PROMO_WAIT_WHY
    assert BEER not in assembled.basket.unresolved
    assert all("не знайшлось" not in p.reason for p in assembled.basket.postponed)
    step = next(s for s in assembled.basket.trace if s.id == "step-promo")
    assert "без акції 1" in step.result_summary


@pytest.mark.anyio
async def test_the_promo_skill_rides_into_the_prompt_and_names_itself_in_the_trace(tmp_path):
    mcp = _stand(
        tmp_path,
        orders=_beer_orders(last_days_ago=20) + _milk_orders(),
        beer_on_shelf=_card(501, BEER, 29.99, old=50.99),
    )
    llm = _RefusingLLM(refuse="")
    assembled = await assemble_list(mcp, llm=llm, request=_WEEK_WITH_BAR, now=NOW)

    step = next(s for s in assembled.basket.trace if s.id == "step-skills")
    assert step.result_summary == "підключено 1: акція"
    assert step.args["чому"].startswith("підключено: акція (акційна звичка: 1 вид)")
    assert step.tag == "+1"
    picking = [system for system in llm.systems if "обираєш під кожен намір" in system]
    assert picking and all("# Скіл «акція»" in system for system in picking)
    assert step.args["поля"] == {
        "акція": [
            "id",
            "ціна",
            "стара_ціна",
            "фасовка",
            "артикул",
            "акційна_звичка",
            "звична_кількість",
        ]
    }
    assert (
        "акція (акційна звичка: 1 вид) -- судить полями id, ціна, стара_ціна, фасовка, "
        "артикул, акційна_звичка, звична_кількість" in step.args["чому"]
    )


FOOD = "Корм для котів Whiskas з яловичиною 75г"


def _online(days_ago: int, *, price: float, qty: int) -> dict:
    return {
        "orderId": f"order-{days_ago}",
        "status": "received",
        "createdAt": (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%S"),
        "amount": price * qty,
        "products": [
            {
                "id": f"00000000-0000-4000-8000-{days_ago:012d}",
                "name": FOOD,
                "price": price,
                "quantity": qty,
                "subtotal": price * qty,
                "removed": False,
                "image": None,
                "companyId": "00000000-0000-4000-8000-000000000001",
                "branchId": "00000000-0000-4000-8000-000000000002",
            },
            *(
                {
                    "id": f"00000000-0000-4000-8000-{days_ago:09d}{filler:03d}",
                    "name": f"Разова покупка {days_ago}-{filler}",
                    "price": 40,
                    "quantity": 1,
                    "subtotal": 40,
                    "removed": False,
                }
                for filler in range(5)
            ),
        ],
    }


def _food_orders() -> list[dict]:
    return [
        _online(60, price=12.99, qty=20),
        _online(45, price=12.99, qty=20),
        _online(30, price=11.99, qty=24),
        _online(15, price=12.99, qty=20),
    ]


def _food_stand(tmp_path, *, food_on_shelf: dict | None) -> SilpoMCP:
    (tmp_path / "silpo_get_time_slots.json").write_text(
        json.dumps({"slots": [SLOT]}), encoding="utf-8"
    )
    (tmp_path / "silpo_get_my_offline_orders.json").write_text(
        json.dumps({"orders": _milk_orders()}), encoding="utf-8"
    )
    (tmp_path / "silpo_get_my_online_orders.json").write_text(
        json.dumps({"orders": _food_orders()}), encoding="utf-8"
    )
    (tmp_path / "silpo_get_my_shopping_cart.json").write_text(
        json.dumps({"shoppingCartId": None}), encoding="utf-8"
    )
    (tmp_path / "silpo_find_products_batch.json").write_text(
        json.dumps(
            {
                "queries": [
                    {"query": FOOD, "products": [food_on_shelf] if food_on_shelf else []},
                    {"query": MILK, "products": [_card(101, MILK, 53.49)]},
                ]
            }
        ),
        encoding="utf-8",
    )
    return SilpoMCP(fixtures_dir=tmp_path)


@pytest.mark.anyio
async def test_the_shelf_proves_the_habit_the_online_receipt_cannot(tmp_path):
    mcp = _food_stand(tmp_path, food_on_shelf=_card(777, FOOD, 21.59))
    assembled = await assemble_list(mcp, llm=None, request=_WEEK_WITH_BAR, now=NOW)

    assert [line.name for line in assembled.basket.lines] == [MILK]
    waiting = next(p for p in assembled.basket.postponed if p.intent == FOOD)
    assert waiting.reason == PROMO_WAIT_WHY
    step = next(s for s in assembled.basket.trace if s.id == "step-promo")
    assert "1 довела полиця, не чек" in step.result_summary
    assert step.args["доведено полицею"] == [FOOD]


@pytest.mark.anyio
async def test_with_a_sale_the_online_only_kind_rides_in_its_sale_quantity(tmp_path):
    mcp = _food_stand(tmp_path, food_on_shelf=_card(777, FOOD, 12.99, old=21.59))
    assembled = await assemble_list(mcp, llm=None, request=_WEEK_WITH_BAR, now=NOW)

    food = next(line for line in assembled.basket.lines if line.name == FOOD)
    assert food.qty == 20
    assert food.explanation == "береш по акції (4 з 4) — зараз акція: було 21.59, стало 12.99"


@pytest.mark.anyio
async def test_the_shelf_axis_stays_silent_when_the_own_article_is_not_on_it(tmp_path):
    mcp = _food_stand(tmp_path, food_on_shelf=_card(778, "Корм для котів Whiskas 2кг", 431.80))
    assembled = await assemble_list(mcp, llm=None, request=_WEEK_WITH_BAR, now=NOW)

    assert any(line.intent == FOOD for line in assembled.lines)
    assert all(s.id != "step-promo" for s in assembled.basket.trace)


@pytest.mark.anyio
async def test_the_waiting_kind_is_off_the_shelf_and_off_the_bill_too(tmp_path):
    mcp = _stand(
        tmp_path,
        orders=_beer_orders(last_days_ago=20) + _milk_orders(),
        beer_on_shelf=_card(501, BEER, 50.99),
    )
    assembled = await assemble_list(mcp, llm=None, request=_WEEK_WITH_BAR, now=NOW)

    rows = sum((line.price * line.qty for line in assembled.basket.lines), Decimal(0))
    assert [line.name for line in assembled.basket.lines] == [MILK]
    assert assembled.basket.total == rows
    assert assembled.basket.total == Decimal("53.49")


@pytest.mark.anyio
async def test_a_basket_inside_the_corridor_is_not_announced_as_over_it(tmp_path):
    mcp = _stand(
        tmp_path,
        orders=_beer_orders(last_days_ago=20) + _milk_orders(),
        beer_on_shelf=_card(501, BEER, 50.99),
    )
    assembled = await assemble_list(
        mcp, llm=None, request=BuildRequest(mode="week", budget=55), now=NOW
    )

    step = next(s for s in assembled.basket.trace if s.id == "step-budget")
    assert "вище межі" not in step.result_summary
    assert "у межі" in step.result_summary
    assert step.tag == "у межі"
    assert assembled.basket.trimmed == []
