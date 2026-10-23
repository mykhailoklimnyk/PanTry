from __future__ import annotations

import json

from komora.agent.llm import Decision, Usage
from komora.agent.occasion import (
    HISTORY_LIMIT,
    OccasionPlan,
    plan_of,
    rework,
)
from komora.core.occasion import OCCASION_LIMIT, occasion_of


class _LLM:

    model = "fake-model"

    def __init__(self, data: dict) -> None:
        self.data = data
        self.calls = 0
        self.payload: dict = {}
        self.system = ""

    async def decide(self, *, system, user, schema, schema_name="decision", max_tokens=2048, **_):
        self.calls += 1
        self.payload = json.loads(user)
        self.system = system
        return Decision(data=self.data, text="", model=self.model, usage=Usage(7, 3), duration_ms=4)


def test_the_occasion_may_not_remove_what_the_guest_named_himself():
    added, skipped, _ = plan_of(
        {"add": [], "skip": [{"intent": "молоко", "why": "зіпсується"}]},
        intents=["молоко", "Гречка Сквирянка"],
        protected=["молоко"],
    )

    assert added == ()
    assert skipped == (), "гість написав «молоко» руками — привід його не знімає"


def test_only_an_intent_that_is_in_the_list_can_be_removed_from_it():
    _, skipped, _ = plan_of(
        {"add": [], "skip": [{"intent": "сметана", "why": "зіпсується"}]},
        intents=["Молоко Ферма 2,5%"],
        protected=[],
    )

    assert skipped == ()


def test_the_occasion_does_not_add_a_twin_of_an_intent_already_in_the_list():
    added, _, _ = plan_of(
        {
            "add": [
                {"intent": "  Молоко  Ферма 2,5%", "why": "до столу"},
                {"intent": "чипси", "why": "до столу"},
                {"intent": "Чипси", "why": "ще раз те саме"},
            ],
            "skip": [],
        },
        intents=["Молоко Ферма 2,5%"],
        protected=[],
    )

    assert [change.intent for change in added] == ["чипси"]


def test_the_ceiling_cuts_the_tail_and_reports_how_much_it_cut():
    names = [f"вид {n}" for n in range(OCCASION_LIMIT + 3)]
    added, _, beyond = plan_of(
        {"add": [{"intent": name, "why": "привід"} for name in names], "skip": []},
        intents=[],
        protected=[],
    )

    assert len(added) == OCCASION_LIMIT
    assert beyond == 3
    assert [change.intent for change in added] == names[:OCCASION_LIMIT]


def test_an_empty_intent_is_not_a_line_with_an_empty_name():
    added, _, _ = plan_of(
        {"add": [{"intent": "   ", "why": "привід"}], "skip": []},
        intents=[],
        protected=[],
    )

    assert added == ()


def test_the_same_intent_named_twice_for_removal_is_removed_once():
    _, skipped, _ = plan_of(
        {
            "add": [],
            "skip": [
                {"intent": "сир", "why": "зіпсується"},
                {"intent": "Сир", "why": "зіпсується"},
            ],
        },
        intents=["сир"],
        protected=[],
    )

    assert len(skipped) == 1


async def test_a_mode_without_an_occasion_never_reaches_the_model():
    llm = _LLM({"add": [], "skip": []})

    plan = await rework(llm, occasion_of("week", None), intents=["молоко"], protected=[], habits=[])

    assert llm.calls == 0
    assert plan == OccasionPlan()
    assert not plan.touched


async def test_the_occasion_call_carries_the_guests_own_habits_and_its_ceiling():
    llm = _LLM({"add": [{"intent": "чипси", "why": "до столу"}], "skip": []})
    habits = [(f"вид {n}", 100 - n) for n in range(HISTORY_LIMIT + 20)]

    plan = await rework(
        llm,
        occasion_of("event", 4),
        intents=["молоко"],
        protected=["молоко"],
        habits=habits,
    )

    assert llm.calls == 1
    assert llm.payload["привід"] == "подія, 4 людини"
    assert "12" not in llm.payload["що_це_означає"]
    assert "4" in llm.payload["що_це_означає"], "число людей доїжджає в завдання"
    assert llm.payload["наміри"] == ["молоко"]
    assert len(llm.payload["купує_сам"]) == HISTORY_LIMIT, "стеля промпта — про машину"
    assert llm.payload["стеля_докидання"] == OCCASION_LIMIT
    assert plan.tokens == 10 and plan.model == "fake-model"
    assert [change.intent for change in plan.added] == ["чипси"]


def test_the_note_says_what_the_occasion_actually_did_including_nothing():
    from komora.agent.occasion import Change

    assert "не змінився" in OccasionPlan().note()

    touched = OccasionPlan(
        added=(Change("чипси", "до столу"),),
        skipped=(Change("сметана", "зіпсується"),),
    )
    note = touched.note()
    assert "докинув 1 — чипси" in note
    assert "зняв 1 — сметана" in note
    assert touched.touched

    many = OccasionPlan(added=tuple(Change(f"вид {n}", "") for n in range(7)))
    assert many.note().endswith("…"), "довгий перелік обривається видимо, а не мовчки"


def test_the_limit_and_the_usual_order_reach_the_model_and_its_target_comes_back():
    import asyncio
    from decimal import Decimal

    llm = _LLM({"add": [], "skip": [], "target": 3000, "target_why": "гості на шістьох"})
    plan = asyncio.run(
        rework(
            llm,
            occasion_of("event", 6),
            intents=["молоко"],
            protected=[],
            habits=[],
            budget=Decimal(1600),
            usual=Decimal(1520),
        )
    )
    assert llm.payload["межа_грн"] == "1600"
    assert llm.payload["звичне_замовлення_грн"] == "1520"
    assert plan.target == Decimal(3000) and plan.target_why == "гості на шістьох"


def test_a_missing_or_broken_target_is_nothing_not_zero():
    from komora.agent.occasion import target_of

    assert target_of({"add": [], "skip": []}) == (None, "")
    assert target_of({"target": None}) == (None, "")
    assert target_of({"target": "багато"}) == (None, "")
    assert target_of({"target": 0, "target_why": "x"}) == (None, "")
    assert target_of({"target": "2500", "target_why": " свято "})[1] == "свято"


async def test_the_occasion_call_carries_the_guests_bar_beyond_the_habit_ceiling():
    llm = _LLM({"add": [], "skip": []})
    await rework(
        llm,
        occasion_of("event", 4),
        intents=["молоко"],
        protected=["молоко"],
        habits=[("молоко", 9)],
        bar=[("ром", 2)],
    )
    assert llm.payload["бар_гостя"] == [{"напій": "ром", "чеків": 2}]

    silent = _LLM({"add": [], "skip": []})
    await rework(
        silent, occasion_of("event", 4), intents=["молоко"], protected=["молоко"], habits=[]
    )
    assert "бар_гостя" not in silent.payload
