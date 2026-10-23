from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from komora.agent.basket import (
    OWN_PICK,
    HistoryItem,
    Tracer,
    assemble_list,
    build_lines,
    fresh_own,
)
from komora.agent.llm import Decision, Usage
from komora.api.schemas import BuildRequest
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

PARCELA = "Томат La Parcela Черрі Angello"
GORDIY = "Томат Гордій Черрі"
OTHER = "Томат черрі"
PLUM = "Слива чорна"
NECTARINE = "Нектарин Іспанія"


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
        "displayRatio": "250г",
        "companyId": "00000000-0000-4000-8000-000000000001",
        "branchId": "00000000-0000-4000-8000-000000000002",
        "externalProductId": pid,
    }


def _bought(days_ago: int, lager: int, name: str) -> dict:
    return {
        "createdAt": (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%d"),
        "products": [{"lagerId": lager, "name": name, "unit": "250г", "quantity": 1, "price": 80}],
    }


class _AskingLLM:

    model = "fake-model"

    def __init__(self, picks: list[dict]) -> None:
        self.picks = picks

    async def decide(self, *, system, user, schema, schema_name="decision", max_tokens=2048, **_):
        return Decision(
            data={"picks": self.picks},
            text="",
            model=self.model,
            usage=Usage(1, 1),
            duration_ms=1,
        )


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


def _parcela_due() -> list[dict]:
    return [_bought(day, 701, PARCELA) for day in (50, 40, 30, 20)]


ASK = "Взяти інші червоні томати черрі замість La Parcela Angello?"


@pytest.mark.anyio
async def test_a_fresh_own_article_of_the_same_kind_answers_the_question_itself(tmp_path):
    mcp = _stand(
        tmp_path,
        orders=_parcela_due() + [_bought(day, 702, GORDIY) for day in (12, 8, 4, 2)],
        shelf={PARCELA: [_card(703, OTHER, 154.0), _card(702, GORDIY, 71.99)]},
    )
    llm = _AskingLLM([{"intent": PARCELA, "chosen_id": "", "qty": 1, "ask": ASK}])

    assembled = await assemble_list(mcp, llm=llm, request=BuildRequest(mode="week"), now=NOW)

    assert assembled.basket.questions == []
    line = next(line for line in assembled.basket.lines if line.name == GORDIY)
    assert line.explanation_detail.startswith("своє замість питання: береш це останнім часом")
    assert "4 свіжих чеків із 4" in line.explanation_detail
    step = next(s for s in assembled.basket.trace if s.id == "step-own")
    assert step.tag == "-1 питань"
    assert "1 намір" in step.result_summary
    taken = " ".join(step.args["взято"])
    assert GORDIY in taken and "4 свіжих чеків" in taken
    assert all(s.id != "step-ask" for s in assembled.basket.trace)


@pytest.mark.anyio
async def test_an_own_article_without_fresh_receipts_leaves_the_question_standing(tmp_path):
    mcp = _stand(
        tmp_path,
        orders=_parcela_due() + [_bought(day, 702, GORDIY) for day in (420, 400, 380, 360)],
        shelf={PARCELA: [_card(703, OTHER, 154.0), _card(702, GORDIY, 71.99)]},
    )
    llm = _AskingLLM([{"intent": PARCELA, "chosen_id": "", "qty": 1, "ask": ASK}])

    assembled = await assemble_list(mcp, llm=llm, request=BuildRequest(mode="week"), now=NOW)

    assert [q.intent for q in assembled.basket.questions] == [PARCELA]
    assert all(line.name != GORDIY for line in assembled.basket.lines)
    assert all(s.id != "step-own" for s in assembled.basket.trace)


@pytest.mark.anyio
async def test_own_but_another_kind_does_not_answer_the_question(tmp_path):
    plum_due = [_bought(day, 801, PLUM) for day in (50, 40, 30, 20)]
    nectarine_fresh = [_bought(day, 802, NECTARINE) for day in (13, 9, 5, 2)]
    mcp = _stand(
        tmp_path,
        orders=plum_due + nectarine_fresh,
        shelf={PLUM: [_card(802, NECTARINE, 99.0)]},
    )
    llm = _AskingLLM(
        [{"intent": PLUM, "chosen_id": "", "qty": 1, "ask": "Сливи немає — взяти нектарин?"}]
    )

    assembled = await assemble_list(mcp, llm=llm, request=BuildRequest(mode="week"), now=NOW)

    assert [q.intent for q in assembled.basket.questions] == [PLUM]
    assert all(s.id != "step-own" for s in assembled.basket.trace)


def test_the_freshest_own_article_wins_among_several():
    from decimal import Decimal

    from komora.agent.basket import HistoryItem

    def item(lager: str, name: str, *, recent: int, total: int) -> HistoryItem:
        return HistoryItem(
            lager_id=lager,
            name=name,
            unit="250г",
            receipts=total,
            qty_total=Decimal(total),
            recent_receipts=recent,
            qty_recent=Decimal(recent),
        )

    owned = {
        "702": item("702", GORDIY, recent=4, total=6),
        "704": item("704", "Томат Есміра Черрі", recent=1, total=9),
        "705": item("705", "Томат Бузок Черрі", recent=0, total=12),
    }
    options = [
        _card(703, OTHER, 154.0),
        _card(705, "Томат Бузок Черрі", 60.0),
        _card(704, "Томат Есміра Черрі", 65.0),
        _card(702, GORDIY, 71.99),
    ]
    picked = fresh_own(PARCELA, options, owned)
    assert picked is not None and picked["externalProductId"] == 702
    assert fresh_own(PARCELA, options, {}) is None
    assert fresh_own(PARCELA, [], owned) is None
    assert OWN_PICK == "своє_свіже"


DECLINE = "інший томат черрі, 250 г"
MILK = "Молоко Яготинське 2,5%"


def _milk_due_with_gordiy() -> list[dict]:
    orders = [_bought(day, 901, MILK) for day in (50, 40, 30, 20)]
    for order in orders[2:]:
        order["products"].append(
            {"lagerId": 702, "name": GORDIY, "unit": "250г", "quantity": 1, "price": 80}
        )
    return orders


def _refusing(intent: str) -> _AskingLLM:
    return _AskingLLM(
        [
            {"intent": intent, "chosen_id": "", "qty": 1, "swap": DECLINE},
            {"intent": MILK, "chosen_id": "901", "qty": 1, "why": "звичне"},
        ]
    )


def _refused(
    intent: str,
    options: list[dict],
    owned: dict,
    *,
    hints: dict | None = None,
    auto: bool = True,
) -> tuple[list, dict, Tracer]:
    trace = Tracer()
    plan, _unresolved, declined = build_lines(
        [intent],
        {intent: options},
        hints or {},
        {intent: {"intent": intent, "chosen_id": "", "qty": 1, "swap": DECLINE}},
        auto_intents=frozenset({intent} if auto else ()),
        owned=owned,
        trace=trace,
    )
    return plan, declined, trace


def _item(lager: str, name: str, *, recent: int, total: int) -> HistoryItem:
    return HistoryItem(
        lager_id=lager,
        name=name,
        unit="250г",
        receipts=total,
        qty_total=Decimal(total),
        recent_receipts=recent,
        qty_recent=Decimal(recent),
    )


@pytest.mark.anyio
async def test_a_fresh_own_article_overrides_the_agent_refusal(tmp_path):
    mcp = _stand(
        tmp_path,
        orders=_parcela_due() + _milk_due_with_gordiy(),
        shelf={
            PARCELA: [_card(703, OTHER, 154.0), _card(702, GORDIY, 71.99)],
            MILK: [_card(901, MILK, 42.0)],
        },
    )

    assembled = await assemble_list(
        mcp, llm=_refusing(PARCELA), request=BuildRequest(mode="week"), now=NOW
    )

    assert [d.intent for d in assembled.basket.declined] == []
    assert PARCELA not in assembled.basket.unresolved
    line = next(line for line in assembled.basket.lines if line.name == GORDIY)
    assert line.explanation_detail.startswith("своє замість відмови: береш це останнім часом")
    assert "2 свіжих чеків із 2" in line.explanation_detail
    step = next(s for s in assembled.basket.trace if s.id == "step-own-declined")
    assert step.args["відмов на потребах з чеків"] == 1
    assert step.tag == "-1 відмов"
    assert GORDIY in " ".join(step.args["знято"])


def test_an_own_article_without_fresh_receipts_leaves_the_refusal_standing():
    plan, declined, trace = _refused(
        PARCELA,
        [_card(703, OTHER, 154.0), _card(702, GORDIY, 71.99)],
        {"702": _item("702", GORDIY, recent=0, total=6)},
    )

    assert list(declined) == [PARCELA] and plan == []
    step = next(s for s in trace.steps if s.id == "step-own-declined")
    assert step.args["відмов на потребах з чеків"] == 1 and step.args["знято"] == []
    assert step.tag == "нічого не знято"


def test_own_but_another_kind_does_not_lift_the_refusal():
    plan, declined, _trace = _refused(
        PLUM,
        [_card(802, NECTARINE, 99.0)],
        {"802": _item("802", NECTARINE, recent=4, total=4)},
    )

    assert list(declined) == [PLUM] and plan == []


def test_the_step_stays_silent_when_the_agent_refused_nothing():
    trace = Tracer()
    build_lines(
        [PARCELA],
        {PARCELA: [_card(702, GORDIY, 71.99)]},
        {},
        {PARCELA: {"intent": PARCELA, "chosen_id": "702", "qty": 1}},
        owned={"702": _item("702", GORDIY, recent=4, total=4)},
        trace=trace,
    )
    assert not [s for s in trace.steps if s.id == "step-own-declined"]


def test_the_refusal_stands_when_the_intents_own_article_is_on_the_shelf():
    plan, declined, trace = _refused(
        PARCELA,
        [_card(701, PARCELA, 120.0), _card(702, GORDIY, 71.99)],
        {"702": _item("702", GORDIY, recent=4, total=6)},
        hints={PARCELA: _item("701", PARCELA, recent=4, total=4)},
    )

    assert list(declined) == [PARCELA] and plan == []
    assert not [s for s in trace.steps if s.id == "step-own-declined"]


def test_the_refusal_on_a_guests_own_word_stands_too():
    plan, declined, trace = _refused(
        "молоко",
        [_card(702, "Молоко Гордій", 71.99)],
        {"702": _item("702", "Молоко Гордій", recent=4, total=6)},
        auto=False,
    )

    assert list(declined) == ["молоко"] and plan == []
    assert not [s for s in trace.steps if s.id == "step-own-declined"]


@pytest.mark.anyio
async def test_under_an_event_the_agents_refusal_stands(tmp_path):
    mcp = _stand(
        tmp_path,
        orders=_parcela_due() + _milk_due_with_gordiy(),
        shelf={
            PARCELA: [_card(703, OTHER, 154.0), _card(702, GORDIY, 71.99)],
            MILK: [_card(901, MILK, 42.0)],
        },
    )
    assembled = await assemble_list(
        mcp,
        llm=_refusing(PARCELA),
        request=BuildRequest.model_validate({"mode": "event", "occasionPeople": 4}),
        now=NOW,
    )
    names = {line.name for line in assembled.basket.lines}
    assert GORDIY not in names, "відмову під подію своїм артикулом не перекривають"
    assert PARCELA in assembled.basket.unresolved or any(
        d.intent == PARCELA for d in assembled.basket.declined
    )
