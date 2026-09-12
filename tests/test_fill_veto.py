from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from komora.agent import basket
from komora.agent.basket import Naming, assemble_list
from komora.api.schemas import BuildRequest
from komora.core.bar import DrinkKind
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

STOCKED = "Паляничка сирна"

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
        "displayRatio": "400г",
        "companyId": "00000000-0000-4000-8000-000000000001",
        "branchId": "00000000-0000-4000-8000-000000000002",
        "externalProductId": pid,
    }


def _bought(days_ago: int, lager: int, name: str, price: float = 60.0) -> dict:
    return {
        "createdAt": (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%d"),
        "products": [
            {
                "lagerId": lager,
                "name": name,
                "unit": "400г",
                "quantity": 1,
                "price": price,
            }
        ],
    }


def _stand(tmp_path, *, orders: list[dict], shelf: dict[str, list[dict]]) -> SilpoMCP:
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
            {"queries": [{"query": query, "products": cards} for query, cards in shelf.items()]}
        ),
        encoding="utf-8",
    )
    return SilpoMCP(fixtures_dir=tmp_path)


class _Silent:

    model = "fake-model"

    async def decide(self, **_kw: object) -> object:
        raise RuntimeError("моделі тут бути не має: вето питає кеш, а не її")


@pytest.fixture
def named(monkeypatch: pytest.MonkeyPatch) -> None:
    basket._cache_names({STOCKED: Naming(intent="паляничка", subtype="сирна")})

    class _Judged:
        keeps = None
        sanity = "паляничку з'їдають за раз"
        rhythm_lies = True
        per_day = None
        per_day_unit = None

    async def _sense(_llm: object, labels: object, **_kw: object) -> dict[str, object]:
        return {"паляничка · сирна": _Judged()}

    async def _keeps(_llm: object, labels: object, **_kw: object) -> dict[str, object]:
        return {}

    monkeypatch.setattr("komora.agent.steps.intents.intent_sense", _sense)
    monkeypatch.setattr("komora.agent.steps.intents.intent_keeps", _keeps)


def _stocked() -> list[dict]:
    return [_bought(day, 401, STOCKED) for day in (2, 9, 16, 23)]


def _due() -> list[dict]:
    return [_bought(day, 501, DUE, price=40.0) for day in (20, 27, 34, 41)]


@pytest.mark.anyio
async def test_the_verdict_reaches_the_fill_pool(tmp_path, named) -> None:
    mcp = _stand(
        tmp_path,
        orders=_stocked() + _due(),
        shelf={
            STOCKED: [_card(402, STOCKED, 60.0)],
            DUE: [_card(502, DUE, 40.0)],
        },
    )

    assembled = await assemble_list(
        mcp,
        llm=_Silent(),
        request=BuildRequest.model_validate({"mode": "week", "budget": 3000}),
        now=NOW,
    )

    got = {line.name: line for line in assembled.basket.lines}
    assert DUE in got, "потреба за циклом мусить лишитись -- різ не про неї"
    assert STOCKED in got, "вето не прибирає кандидата -- воно міняє ярус"
    why = got[STOCKED].explanation or ""
    assert "береш нерівно" in why, why


@pytest.mark.anyio
async def test_the_step_says_how_many_it_judged_and_how_many_it_did_not(tmp_path, named) -> None:
    mcp = _stand(
        tmp_path,
        orders=_stocked() + _due(),
        shelf={
            STOCKED: [_card(402, STOCKED, 60.0)],
            DUE: [_card(502, DUE, 40.0)],
        },
    )

    assembled = await assemble_list(
        mcp,
        llm=_Silent(),
        request=BuildRequest.model_validate({"mode": "week", "budget": 3000}),
        now=NOW,
    )

    step = next(s for s in assembled.basket.trace if s.id == "step-target")
    assert "суджено поза потребами" in step.args
    assert "не питали (холодний кеш)" in step.args


STALE = "Морозиво Tonitto з фундуком"


@pytest.mark.anyio
async def test_a_kind_silent_beyond_the_pool_window_is_not_topped_up(tmp_path, named) -> None:
    mcp = _stand(
        tmp_path,
        orders=_due() + [_bought(day, 601, STALE, price=90.0) for day in (322, 400, 584)],
        shelf={DUE: [_card(502, DUE, 40.0)], STALE: [_card(602, STALE, 90.0)]},
    )
    assembled = await assemble_list(
        mcp,
        llm=_Silent(),
        request=BuildRequest.model_validate({"mode": "week", "budget": 3000}),
        now=NOW,
    )
    names = {line.name for line in assembled.basket.lines}
    assert DUE in names, "потреба за циклом лишається"
    assert STALE not in names, "рік мовчання -- не підстава докидати"
    target = next(step for step in assembled.basket.trace if step.id == "step-target")
    assert target.args["поза вікном"] == 1


BEER = "Пиво спеціальне Hike Blanche світле з/б"


@pytest.mark.anyio
async def test_a_drink_is_not_topped_up_under_the_target(tmp_path) -> None:
    basket._cache_names(
        {BEER: basket.Naming(intent="пиво", subtype="", drink=DrinkKind.LIGHT, drink_known=True)}
    )
    mcp = _stand(
        tmp_path,
        orders=_due() + [_bought(day, 701, BEER, price=30.0) for day in (40, 70, 100)],
        shelf={DUE: [_card(502, DUE, 40.0)], BEER: [_card(702, BEER, 30.0)]},
    )
    assembled = await assemble_list(
        mcp,
        llm=_Silent(),
        request=BuildRequest.model_validate({"mode": "week", "budget": 3000}),
        now=NOW,
    )
    names = {line.name for line in assembled.basket.lines}
    assert DUE in names
    assert BEER not in names, "напій живе в барі, не в тижневому кошику"


@pytest.mark.anyio
async def test_an_unnamed_beer_is_still_a_drink_by_its_word(tmp_path) -> None:
    basket._cache_names({})
    mcp = _stand(
        tmp_path,
        orders=_due() + [_bought(day, 701, BEER, price=30.0) for day in (40, 70, 100)],
        shelf={DUE: [_card(502, DUE, 40.0)], BEER: [_card(702, BEER, 30.0)]},
    )
    assembled = await assemble_list(
        mcp,
        llm=_Silent(),
        request=BuildRequest.model_validate({"mode": "week", "budget": 3000}),
        now=NOW,
    )
    names = {line.name for line in assembled.basket.lines}
    assert DUE in names
    assert BEER not in names, "неназване пиво -- усе одно пиво"


@pytest.mark.anyio
async def test_the_guests_word_lets_the_bar_into_the_weekly_basket(tmp_path) -> None:
    basket._cache_names(
        {BEER: basket.Naming(intent="пиво", subtype="", drink=DrinkKind.LIGHT, drink_known=True)}
    )
    mcp = _stand(
        tmp_path,
        orders=_due() + [_bought(day, 701, BEER, price=30.0) for day in (40, 70, 100)],
        shelf={DUE: [_card(502, DUE, 40.0)], BEER: [_card(702, BEER, 30.0)]},
    )
    assembled = await assemble_list(
        mcp,
        llm=_Silent(),
        request=BuildRequest.model_validate({"mode": "week", "budget": 3000, "barInWeek": True}),
        now=NOW,
    )
    assert BEER in {line.name for line in assembled.basket.lines}


SPICE = "Перець чорний «Мрія» мелений"


@pytest.mark.anyio
async def test_a_spice_never_rides_by_cycle_or_fill(tmp_path) -> None:
    from komora.agent import aisle

    basket._cache_names({SPICE: Naming(intent="перець мелений")})
    aisle._CACHE["перець мелений"] = "Соуси і спеції"
    mcp = _stand(
        tmp_path,
        orders=_due() + [_bought(day, 801, SPICE, price=25.0) for day in (3, 6, 9, 12)],
        shelf={DUE: [_card(502, DUE, 40.0)], SPICE: [_card(802, SPICE, 25.0)]},
    )
    assembled = await assemble_list(
        mcp,
        llm=_Silent(),
        request=BuildRequest.model_validate({"mode": "week", "budget": 3000}),
        now=NOW,
    )
    names = {line.name for line in assembled.basket.lines}
    assert DUE in names
    assert SPICE not in names, "спеція за циклом і добором не їде"
    step = next(s for s in assembled.basket.trace if s.id == "step-needs")
    assert step.args["не беру"]["лише за твоїм словом (спеції)"] == 1


@pytest.mark.anyio
async def test_an_event_survives_an_unnamed_beer_in_the_bar_list(tmp_path) -> None:
    basket._cache_names({})
    mcp = _stand(
        tmp_path,
        orders=_due() + [_bought(day, 701, BEER, price=30.0) for day in (40, 70, 100)],
        shelf={DUE: [_card(502, DUE, 40.0)], BEER: [_card(702, BEER, 30.0)]},
    )
    assembled = await assemble_list(
        mcp,
        llm=_Silent(),
        request=BuildRequest.model_validate({"mode": "event", "occasionPeople": 4, "budget": 3000}),
        now=NOW,
    )
    assert DUE in {line.name for line in assembled.basket.lines}


FILLET = ("Куряче філе зі стегна", "Куряче філе", "Філе куряче «Епікур» охолоджене")


@pytest.mark.anyio
async def test_needs_of_one_named_kind_fold_into_one_line(tmp_path) -> None:
    basket._cache_names({name: Naming(intent="філе куряче") for name in FILLET})
    orders = _due()
    for n, name in enumerate(FILLET):
        orders += [_bought(day, 810 + n, name, price=200.0) for day in (3, 6, 9, 12)]
    shelf = {name: [_card(820 + n, name, 200.0)] for n, name in enumerate(FILLET)}
    mcp = _stand(tmp_path, orders=orders, shelf={DUE: [_card(502, DUE, 40.0)], **shelf})
    assembled = await assemble_list(
        mcp,
        llm=_Silent(),
        request=BuildRequest.model_validate({"mode": "week", "budget": 3000}),
        now=NOW,
    )
    names = [line.name for line in assembled.basket.lines]
    assert len([n for n in names if n in FILLET]) == 1, names
    step = next(s for s in assembled.basket.trace if s.id == "step-needs")
    assert step.args["не беру"]["згорнуто в один рядок"] == 2


CHERRY = "Томат Гордій Черрі"
PINK = "Томат Есміра рожевий"


@pytest.mark.anyio
async def test_a_chain_link_is_never_another_line_of_the_same_basket(tmp_path) -> None:
    basket._cache_names(
        {
            CHERRY: Naming(intent="томат", subtype="черрі"),
            PINK: Naming(intent="томат", subtype="рожевий"),
        }
    )
    cards = [_card(901, CHERRY, 72.0), _card(902, PINK, 60.0)]
    orders = _due()
    for lager, name in ((901, CHERRY), (902, PINK)):
        orders += [_bought(day, lager, name, price=70.0) for day in (3, 6, 9, 12)]
    mcp = _stand(
        tmp_path,
        orders=orders,
        shelf={DUE: [_card(502, DUE, 40.0)], CHERRY: cards, PINK: cards},
    )
    assembled = await assemble_list(
        mcp,
        llm=_Silent(),
        request=BuildRequest.model_validate({"mode": "week", "budget": 3000}),
        now=NOW,
    )
    lines = [line for line in assembled.basket.lines if line.name in (CHERRY, PINK)]
    assert len(lines) == 2, [line.name for line in lines]
    ids = {line.external_product_id for line in lines}
    for line in lines:
        links = {alt.external_product_id for alt in line.chain}
        others = ids - {line.external_product_id}
        assert not (links & others), (line.name, links)


PRICEY = "Сир Пармезан витриманий"


@pytest.mark.anyio
async def test_the_code_keeps_cutting_when_the_agents_queue_is_empty(tmp_path) -> None:
    basket._cache_names({})
    mcp = _stand(
        tmp_path,
        orders=_due() + [_bought(day, 901, PRICEY, price=900.0) for day in (3, 6, 9, 12)],
        shelf={DUE: [_card(502, DUE, 40.0)], PRICEY: [_card(902, PRICEY, 900.0)]},
    )
    assembled = await assemble_list(
        mcp,
        llm=_Silent(),
        request=BuildRequest.model_validate({"mode": "week", "budget": 300}),
        now=NOW,
    )
    names = {line.name for line in assembled.basket.lines}
    assert PRICEY not in names and DUE in names, names
    step = next(s for s in assembled.basket.trace if s.id == "step-budget")
    assert "зняв" in step.result_summary


@pytest.mark.anyio
async def test_an_event_asks_what_to_put_on_the_table_from_the_guests_bar(tmp_path) -> None:
    from komora.agent.basket import BAR_ASK_INTENT

    basket._cache_names({})
    shelf = {
        DUE: [_card(502, DUE, 40.0)],
        BEER: [_card(701, BEER, 30.0)],
        "701": [_card(701, BEER, 30.0)],
    }
    orders = _due() + [_bought(day, 701, BEER, price=30.0) for day in (40, 70, 100)]
    event = await assemble_list(
        _stand(tmp_path, orders=orders, shelf=shelf),
        llm=_Silent(),
        request=BuildRequest.model_validate({"mode": "event", "occasionPeople": 4, "budget": 3000}),
        now=NOW,
    )
    ask = next(q for q in event.basket.questions if q.intent == BAR_ASK_INTENT)
    assert [pick.name for pick in ask.picks] == [BEER]
    assert any(s.id == "step-bar-ask" for s in event.basket.trace)
    week = await assemble_list(
        _stand(tmp_path, orders=orders, shelf=shelf),
        llm=_Silent(),
        request=BuildRequest.model_validate({"mode": "week", "budget": 3000}),
        now=NOW,
    )
    assert all(q.intent != BAR_ASK_INTENT for q in week.basket.questions)


@pytest.mark.anyio
async def test_an_event_does_not_offer_to_close_the_rest_of_the_week(tmp_path) -> None:
    kinds = {
        500 + i: f"{name} Ферма"
        for i, name in enumerate(
            ("Молоко", "Хліб", "Сир", "Кефір", "Масло", "Йогурт", "Сметана", "Ряжанка"), start=1
        )
    }
    shelf = {name: [_card(pid, name, 40.0)] for pid, name in kinds.items()}
    orders = [
        _bought(day, pid, name, price=40.0)
        for pid, name in kinds.items()
        for day in (20, 27, 34, 41)
    ]

    async def build(mode: str):
        basket._cache_names({})
        return await assemble_list(
            _stand(tmp_path, orders=orders, shelf=shelf),
            llm=_Silent(),
            request=BuildRequest.model_validate(
                {"mode": mode, "occasionPeople": 4, "budget": 3000}
            ),
            now=NOW,
        )

    week = await build("week")
    needs = next(s for s in week.basket.trace if s.id == "step-needs")
    assert needs.args["не беру"].get("не влізло в звичний кошик", 0) > 0, (
        "стенд мусить упертись у стелю"
    )
    assert any(item.refillable for item in week.basket.postponed)
    event = await build("event")
    needs = next(s for s in event.basket.trace if s.id == "step-needs")
    assert needs.args["не беру"].get("не влізло в звичний кошик", 0) > 0, (
        "стеля названа і під подію"
    )
    assert not any(item.refillable for item in event.basket.postponed)
