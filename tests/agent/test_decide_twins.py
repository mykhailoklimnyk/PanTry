from __future__ import annotations

import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, cast

import pytest

from komora.agent.steps.decide import Decide
from komora.agent.twins import TwinsPlan, verdicts_of
from komora.agent.twins import payload as twins_payload
from komora.core.twins import Group, Row, Verdict


@dataclass
class _Hint:

    receipts: int = 0
    recent_receipts: int = 0
    moments: list[Any] = field(default_factory=list)


@dataclass
class _Line:

    intent: str
    product: dict[str, Any]
    qty: Decimal = Decimal(1)
    auto_need: bool = True
    history_matched: bool = False
    at_home: bool = False
    chain: list[str] = field(default_factory=list)
    from_history: _Hint | None = None
    reason: str = ""

    @property
    def total(self) -> Decimal:
        return Decimal(str(self.product["price"])) * self.qty


_MODEL = object()


def _deciding(lines: list[_Line], llm: Any = _MODEL) -> Decide:
    deciding = Decide(ground=cast(Any, None), shelf=cast(Any, None))
    deciding.llm = llm
    deciding.lines.extend(lines)
    return deciding


def _tomatoes() -> list[_Line]:
    return [
        _Line(
            intent="Томат",
            product={"externalProductId": "32589", "name": "Томат", "price": 74.87},
            history_matched=True,
            from_history=_Hint(receipts=6, recent_receipts=3),
            reason="своє замість питання",
        ),
        _Line(
            intent="Томат Azura Черрі сливка",
            product={
                "externalProductId": "455724",
                "name": "Томат Есміра рожевий",
                "price": 154.0,
            },
        ),
    ]


PHRASES = {"Томат": "томати", "Томат Azura Черрі сливка": "томати"}


def _answer(keep: str, *, same: bool = True, key: str = "томати"):
    async def ask(pairs):
        return TwinsPlan(
            verdicts={key: Verdict(key=key, same=same, keep=keep)},
            model="підроблена",
            tokens=42,
        )

    return ask


@pytest.mark.asyncio
async def test_without_the_step_both_rows_of_one_kind_stay_in_the_basket():
    before = _deciding(_tomatoes())
    assert [line.intent for line in before.lines] == ["Томат", "Томат Azura Черрі сливка"]

    after = _deciding(_tomatoes())
    await after.twins({}, ask=_answer("32589"), phrases=PHRASES)

    assert [line.intent for line in after.lines] == ["Томат"]


@pytest.mark.asyncio
async def test_the_dropped_row_is_named_one_by_one_and_in_the_answer():
    deciding = _deciding(_tomatoes())

    made = await deciding.twins({}, ask=_answer("32589"), phrases=PHRASES)

    assert made.absent == ""
    assert [drop.name for drop in deciding.twins_dropped] == ["Томат Есміра рожевий"]
    assert deciding.twins_dropped[0].kept_name == "Томат"
    said = " ".join(made.args["знято"])
    assert "Томат Есміра рожевий" in said and "Томат" in said
    assert made.facts["lines"] is deciding.lines


@pytest.mark.asyncio
async def test_the_step_cuts_the_very_list_the_basket_holds():
    deciding = _deciding(_tomatoes())
    held = deciding.lines

    await deciding.twins({}, ask=_answer("32589"), phrases=PHRASES)

    assert deciding.lines is held
    assert len(held) == 1


@pytest.mark.asyncio
async def test_the_quantity_of_the_kept_row_is_not_summed():
    lines = _tomatoes()
    lines[0].qty = Decimal(2)
    lines[1].qty = Decimal(3)
    deciding = _deciding(lines)

    await deciding.twins({}, ask=_answer("32589"), phrases=PHRASES)

    assert deciding.lines[0].qty == Decimal(2)


@pytest.mark.asyncio
async def test_two_needs_stay_and_the_step_says_why():
    lines = [
        _Line(
            intent="Вода дитяча Малятко",
            product={"externalProductId": "386913", "name": "Вода дитяча", "price": 29.0},
            history_matched=True,
        ),
        _Line(
            intent="Вода питна Моршинка Спорт",
            product={"externalProductId": "369992", "name": "Моршинська спорт", "price": 34.0},
            history_matched=True,
        ),
    ]
    deciding = _deciding(lines)
    phrases = dict.fromkeys((line.intent for line in lines), "вода питна")

    made = await deciding.twins(
        {}, ask=_answer("386913", same=False, key="вода питна"), phrases=phrases
    )

    assert len(deciding.lines) == 2
    assert deciding.twins_dropped == ()
    assert made.args["лишено"] == {"вода питна": "агент каже: це різні потреби"}


@pytest.mark.asyncio
async def test_a_broken_answer_about_a_pair_leaves_it_whole_and_names_it():
    deciding = _deciding(_tomatoes())

    async def ask(pairs):
        return TwinsPlan(verdicts={"томати": Verdict(key="томати", same=True, keep="999")})

    made = await deciding.twins({}, ask=ask, phrases=PHRASES)

    assert len(deciding.lines) == 2
    assert made.args["лишено"] == {"томати": "агент не назвав, кого лишити"}


@pytest.mark.asyncio
async def test_the_step_stands_in_the_trace_even_when_there_are_no_pairs():
    lines = [
        _Line(intent="Банан", product={"externalProductId": "1", "name": "Банан", "price": 10.0}),
        _Line(intent="Хліб", product={"externalProductId": "2", "name": "Хліб", "price": 20.0}),
    ]
    called: list[Any] = []

    async def ask(pairs):
        called.append(pairs)
        raise AssertionError("виклику без груп бути не може")

    deciding = _deciding(lines)
    made = await deciding.twins({}, ask=ask, phrases={"Банан": "банани", "Хліб": "хліб"})

    assert called == []
    assert made.absent == ""
    assert made.args == {"рядків": 2}
    assert made.facts["lines"] is deciding.lines
    assert len(deciding.lines) == 2


@pytest.mark.asyncio
async def test_without_a_model_the_step_refuses_and_keeps_both_rows():
    deciding = _deciding(_tomatoes(), llm=None)

    async def ask(pairs):
        raise AssertionError("без моделі виклику бути не може")

    made = await deciding.twins({}, ask=ask, phrases=PHRASES)

    assert made.absent.startswith("без моделі")
    assert len(deciding.lines) == 2


@pytest.mark.asyncio
async def test_a_broken_model_does_not_take_the_basket_down_with_it():
    deciding = _deciding(_tomatoes())

    async def ask(pairs):
        raise RuntimeError("мережа впала")

    made = await deciding.twins({}, ask=ask, phrases=PHRASES)

    assert "мережа впала" in made.absent
    assert len(deciding.lines) == 2


@pytest.mark.asyncio
async def test_a_row_the_guest_named_is_never_dropped():
    lines = _tomatoes()
    lines[1].auto_need = False
    deciding = _deciding(lines)

    await deciding.twins({}, ask=_answer("32589"), phrases=PHRASES)

    assert [line.intent for line in deciding.lines] == ["Томат Azura Черрі сливка"]


@pytest.mark.asyncio
async def test_the_kind_key_is_the_fallback_when_the_phrase_is_missing():
    deciding = _deciding(_tomatoes())

    await deciding.twins(
        {},
        ask=_answer("32589", key="томат"),
        kinds={"Томат": "томат", "Томат Azura Черрі сливка": "томат azura"},
    )

    assert [line.intent for line in deciding.lines] == ["Томат"]


@pytest.mark.asyncio
async def test_a_row_already_at_home_is_not_a_twin():
    lines = _tomatoes()
    lines[1].at_home = True
    deciding = _deciding(lines)

    async def ask(pairs):
        raise AssertionError("груп тут бути не може")

    made = await deciding.twins({}, ask=ask, phrases=PHRASES)

    assert made.args == {"рядків": 1}
    assert len(deciding.lines) == 2


def test_the_payload_carries_the_numbers_the_rule_asks_the_model_to_use():
    group = Group(
        key="томати",
        rows=(
            Row(
                intent="Томат",
                article="32589",
                name="Томат",
                own_article=True,
                receipts=6,
                recent_receipts=3,
                unit_price="49.99 грн/кг",
                came_from="своє замість питання",
            ),
            Row(
                intent="Томат Azura",
                article="455724",
                name="Томат Есміра рожевий",
                unit_price="71.77 грн/кг",
                promo="було 82.49, стало 71.77",
                came_from="обрав агент",
            ),
        ),
    )

    said = json.loads(twins_payload([group]))
    own, other = said["групи"][0]["рядки"]

    assert own["своє_з_чеків"] == {"чеків": 6, "свіжих": 3}
    assert own["як_потрапив"] == "своє замість питання"
    assert own["ціна"] == "49.99 грн/кг"
    assert other["у_чеках_гостя"] is False
    assert other["акція"] == "було 82.49, стало 71.77"
    assert "своє_з_чеків" not in other


@pytest.mark.asyncio
async def test_the_step_fills_those_numbers_from_the_line_itself():
    seen: list[Any] = []

    async def ask(pairs):
        seen.append(pairs)
        return TwinsPlan(verdicts={})

    await _deciding(_tomatoes()).twins({}, ask=ask, phrases=PHRASES)

    own, other = seen[0][0].rows
    assert (own.receipts, own.recent_receipts) == (6, 3)
    assert own.came_from == "своє замість питання"
    assert own.unit_price == "74.87 грн/шт"
    assert (other.receipts, other.recent_receipts) == (0, 0)


def test_a_key_outside_the_asked_groups_is_not_bound_to_a_neighbour():
    pairs = [Group(key="томати", rows=(Row(intent="Томат", article="1", name="Томат"),))]

    known, stray = verdicts_of(
        {
            "pairs": [
                {"key": "томати", "same": True, "keep": "1"},
                {"key": "лимонад", "same": True, "keep": "2"},
                {"key": "  ", "same": True},
            ]
        },
        pairs,
    )

    assert set(known) == {"томати"}
    assert set(stray) == {"лимонад"}


@dataclass
class _Basket:

    total: Decimal
    budget: Decimal | None
    twins_dropped: tuple[Any, ...] = ()


@dataclass
class _Plan:
    basket: _Basket


def _called(monkeypatch: pytest.MonkeyPatch, plan: _Plan) -> list[Any]:
    import komora.agent.refill as module

    seen: list[Any] = []

    async def _refill(_mcp, _llm, run, request, **kwargs):
        seen.append(request)
        return run

    monkeypatch.setattr(module, "plan_of", lambda run: plan)
    monkeypatch.setattr(module, "refill", _refill)
    return seen


@pytest.mark.asyncio
async def test_a_basket_below_the_corridor_after_a_fold_is_topped_up(
    monkeypatch: pytest.MonkeyPatch,
):
    from komora.agent.refill import top_up_after_twins

    plan = _Plan(_Basket(total=Decimal(1400), budget=Decimal(1700), twins_dropped=(object(),)))
    seen = _called(monkeypatch, plan)

    await top_up_after_twins(cast(Any, None), _MODEL, cast(Any, "прогін"))

    assert len(seen) == 1, "кошик нижчий за коридор -- добір мусить статись"


@pytest.mark.asyncio
async def test_a_basket_inside_the_corridor_is_left_alone(monkeypatch: pytest.MonkeyPatch):
    from komora.agent.refill import top_up_after_twins

    plan = _Plan(_Basket(total=Decimal(1650), budget=Decimal(1700), twins_dropped=(object(),)))
    seen = _called(monkeypatch, plan)

    await top_up_after_twins(cast(Any, None), _MODEL, cast(Any, "прогін"))

    assert seen == []


@pytest.mark.asyncio
async def test_without_a_fold_or_without_a_named_sum_nothing_is_topped_up(
    monkeypatch: pytest.MonkeyPatch,
):
    from komora.agent.refill import top_up_after_twins

    no_fold = _Plan(_Basket(total=Decimal(1400), budget=Decimal(1700)))
    seen = _called(monkeypatch, no_fold)
    await top_up_after_twins(cast(Any, None), _MODEL, cast(Any, "прогін"))
    assert seen == []

    no_budget = _Plan(_Basket(total=Decimal(1400), budget=None, twins_dropped=(object(),)))
    seen = _called(monkeypatch, no_budget)
    await top_up_after_twins(cast(Any, None), _MODEL, cast(Any, "прогін"))
    assert seen == []


@pytest.mark.asyncio
async def test_a_refusal_of_the_refill_is_a_legal_answer_not_a_broken_basket(
    monkeypatch: pytest.MonkeyPatch,
):
    import komora.agent.refill as module
    from komora.agent.refill import RefillError, top_up_after_twins

    plan = _Plan(_Basket(total=Decimal(1400), budget=Decimal(1700), twins_dropped=(object(),)))

    async def _refill(*_args, **_kwargs):
        raise RefillError("добирати нема чого")

    monkeypatch.setattr(module, "plan_of", lambda run: plan)
    monkeypatch.setattr(module, "refill", _refill)

    assert await top_up_after_twins(cast(Any, None), _MODEL, cast(Any, "прогін")) == "прогін"


def _day(n: int) -> Any:
    from datetime import UTC, datetime

    return datetime(2026, 9, n, 12, tzinfo=UTC)


def _breads() -> list[_Line]:
    return [
        _Line(
            intent="Хліб Рум'янець цільнозерновий пшеничний",
            product={"externalProductId": "813640", "name": "Хліб «Рум'янець»", "price": 62.46},
            history_matched=True,
            from_history=_Hint(receipts=8, recent_receipts=3, moments=[_day(1), _day(2)]),
        ),
        _Line(
            intent="Булка подова Французька зернова",
            product={"externalProductId": "596031", "name": "Булка подова", "price": 47.99},
            history_matched=True,
            from_history=_Hint(receipts=4, moments=[_day(3), _day(4)]),
        ),
        _Line(
            intent="Багет подовий Французький Люкс",
            product={"externalProductId": "375210", "name": "Багет подовий", "price": 90.98},
            history_matched=True,
            from_history=_Hint(receipts=3, moments=[_day(5)]),
        ),
    ]


BREAD_PHRASES = {
    "Хліб Рум'янець цільнозерновий пшеничний": "хліб",
    "Булка подова Французька зернова": "булка",
    "Багет подовий Французький Люкс": "багет",
}
BREAD_SECTIONS = {
    article: frozenset({"Хлібобулочні вироби"}) for article in ("813640", "596031", "375210")
}


@pytest.mark.asyncio
async def test_without_sections_three_breads_never_reach_the_model():
    asked: list[Any] = []

    async def ask(pairs):
        asked.extend(pairs)
        return TwinsPlan(verdicts={})

    await _deciding(_breads()).twins({}, ask=ask, phrases=BREAD_PHRASES)
    assert asked == []

    deciding = _deciding(_breads())
    await deciding.twins(
        {},
        ask=_answer("813640", key="хлібобулочні вироби"),
        phrases=BREAD_PHRASES,
        sections=BREAD_SECTIONS,
    )

    assert [line.intent for line in deciding.lines] == ["Хліб Рум'янець цільнозерновий пшеничний"]


def test_the_answer_may_name_only_part_of_the_group_to_drop():
    pairs = [Group(key="овочі", rows=(Row(intent="Томат", article="1", name="Томат"),))]

    known, _stray = verdicts_of(
        {"pairs": [{"key": "овочі", "same": True, "keep": "1", "drop": ["2", " ", 3]}]},
        pairs,
    )

    assert known["овочі"].drop == ("2", "3")


def test_the_turns_fact_rides_only_with_a_section_group():
    rows = (
        Row(intent="Хліб", article="1", name="Хліб", bought=frozenset({"d1"})),
        Row(intent="Булка", article="2", name="Булка", bought=frozenset({"d2"})),
    )

    by_section = json.loads(twins_payload([Group(key="відділ", rows=rows, by_section=True)]))
    by_phrase = json.loads(twins_payload([Group(key="хліб", rows=rows)]))

    assert by_section["групи"][0]["як_беруть"]
    assert "як_беруть" not in by_phrase["групи"][0]
