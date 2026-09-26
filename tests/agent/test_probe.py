from __future__ import annotations

import json
from typing import Any

import pytest

from komora.agent.probe import (
    MAX_COVERS,
    MAX_QUESTIONS,
    Probe,
    intent_probe,
    intent_spread,
)

LABELS = [f"вид · {n}" for n in range(1, 21)]


class _Answering:
    model = "fake-model"

    def __init__(self, questions: list[dict[str, Any]]) -> None:
        self.questions = questions
        self.asked: list[dict[str, Any]] = []

    async def decide(self, *, system, user, schema, **_):
        from komora.agent.llm import Decision, Usage

        self.asked.append(json.loads(user))
        return Decision(
            data={"questions": self.questions},
            text="",
            model=self.model,
            usage=Usage(1, 1),
            duration_ms=1,
        )


async def test_without_a_model_there_are_no_questions() -> None:
    probes, thrown, tokens = await intent_probe(None, LABELS)

    assert (probes, thrown, tokens) == ([], [], 0)


async def test_an_invented_label_is_cut_one_by_one_and_names_itself() -> None:
    llm = _Answering(
        [
            {"label": "вигаданий", "ask": "як швидко?", "covers": []},
            {"label": "вид · 1", "ask": "як швидко йде вид · 1?", "covers": ["вид · 2"]},
        ]
    )

    probes, thrown, _tokens = await intent_probe(llm, LABELS)

    assert [probe.label for probe in probes] == ["вид · 1"]
    assert any("вигаданий" in line for line in thrown)


async def test_the_ceiling_on_questions_holds(monkeypatch: pytest.MonkeyPatch) -> None:
    llm = _Answering(
        [{"label": label, "ask": f"як швидко {label}?", "covers": []} for label in LABELS]
    )

    probes, _thrown, _tokens = await intent_probe(llm, LABELS)

    assert len(probes) == MAX_QUESTIONS


async def test_one_answer_may_not_explain_the_whole_pantry() -> None:
    llm = _Answering([{"label": "вид · 1", "ask": "як швидко?", "covers": LABELS[1:]}])

    probes, _thrown, _tokens = await intent_probe(llm, LABELS)

    assert len(probes[0].covers) == MAX_COVERS


async def test_the_same_label_is_never_asked_twice() -> None:
    llm = _Answering(
        [
            {"label": "вид · 1", "ask": "перше", "covers": ["вид · 2"]},
            {"label": "вид · 2", "ask": "друге", "covers": ["вид · 3"]},
            {"label": "вид · 1", "ask": "третє", "covers": []},
        ]
    )

    probes, thrown, _tokens = await intent_probe(llm, LABELS)

    assert [probe.label for probe in probes] == ["вид · 1"]
    assert len(thrown) == 2


async def test_nothing_to_ask_is_an_answer_and_not_a_failure() -> None:
    llm = _Answering([])

    probes, thrown, _tokens = await intent_probe(llm, LABELS)

    assert probes == [] and thrown == []


async def test_the_model_sees_the_closed_list_it_must_choose_from() -> None:
    llm = _Answering([])

    await intent_probe(llm, LABELS)

    assert llm.asked[0]["види"] == LABELS


async def test_a_probe_carries_what_it_promises_to_explain() -> None:
    llm = _Answering([{"label": "вид · 1", "ask": "як швидко?", "covers": ["вид · 2", "вид · 3"]}])

    probes, _thrown, _tokens = await intent_probe(llm, LABELS)

    assert probes == [Probe(label="вид · 1", ask="як швидко?", covers=("вид · 2", "вид · 3"))]


class _Spreading:
    model = "fake-model"

    def __init__(self, kinds: list[dict[str, Any]]) -> None:
        self.kinds = kinds
        self.asked: list[dict[str, Any]] = []

    async def decide(self, *, system, user, schema, **_):
        from komora.agent.llm import Decision, Usage

        self.asked.append(json.loads(user))
        return Decision(
            data={"kinds": self.kinds},
            text="",
            model=self.model,
            usage=Usage(1, 1),
            duration_ms=1,
        )


async def test_an_answer_puts_numbers_on_the_neighbours_it_promised() -> None:
    llm = _Spreading([{"label": "булка", "days": 5}, {"label": "батон", "days": 4}])

    spread, thrown, _tokens = await intent_spread(llm, {"хліб": (3, ["булка", "батон"])})

    assert spread == {"булка": (5, "хліб"), "батон": (4, "хліб")}
    assert thrown == []


async def test_a_neighbour_nobody_promised_is_cut_and_names_itself() -> None:
    llm = _Spreading([{"label": "порошок", "days": 30}])

    spread, thrown, _tokens = await intent_spread(llm, {"хліб": (3, ["булка"])})

    assert spread == {}
    assert any("порошок" in line for line in thrown)


async def test_a_number_outside_the_bounds_is_refused() -> None:
    llm = _Spreading([{"label": "булка", "days": 900}])

    spread, thrown, _tokens = await intent_spread(llm, {"хліб": (3, ["булка"])})

    assert spread == {}
    assert any("900" in line for line in thrown)


async def test_the_guest_word_is_never_overwritten_by_the_spread() -> None:
    llm = _Spreading([{"label": "хліб", "days": 9}])

    spread, thrown, _tokens = await intent_spread(
        llm, {"хліб": (3, ["хліб"]), "молоко": (2, ["хліб"])}
    )

    assert spread == {}
    assert any("сказав сам" in line for line in thrown)


async def test_without_neighbours_nothing_is_asked() -> None:
    llm = _Spreading([{"label": "булка", "days": 5}])

    spread, thrown, tokens = await intent_spread(llm, {"хліб": (3, [])})

    assert (spread, thrown, tokens) == ({}, [], 0)
    assert llm.asked == []


def test_a_spread_number_never_claims_the_guest_said_it() -> None:
    from datetime import UTC, datetime

    from komora.agent.basket import HistoryItem, apply_cycles, kind_row

    moment = datetime(2026, 9, 9, 12, 0, tzinfo=UTC)
    rows = [
        HistoryItem(
            lager_id="1",
            name="булка",
            unit="шт",
            receipts=3,
            qty_total=3,
            moments=[
                datetime(2026, 8, 20, tzinfo=UTC),
                datetime(2026, 8, 27, tzinfo=UTC),
                datetime(2026, 9, 3, tzinfo=UTC),
            ],
        )
    ]
    apply_cycles(rows, {"булка": 5}, {"булка": "хліб"})
    said = kind_row(rows[0], moment=moment)

    assert "як у «хліб»" in said.state
    assert "з твоїх слів" not in said.state


async def test_a_neighbour_of_another_kind_is_cut_and_says_so():
    llm = _Answering(
        [{"label": "папір туалетний", "ask": "як швидко?", "covers": ["батарейки · АА"]}]
    )

    probes, thrown, _ = await intent_probe(llm, ["папір туалетний", "батарейки · АА"])

    assert probes[0].covers == ()
    assert any("інший вид" in line for line in thrown), thrown


async def test_the_question_ceiling_names_what_it_cut() -> None:
    llm = _Answering(
        [{"label": label, "ask": f"як швидко {label}?", "covers": []} for label in LABELS]
    )

    probes, thrown, _tokens = await intent_probe(llm, LABELS)

    assert len(probes) == MAX_QUESTIONS
    assert any(str(len(LABELS) - MAX_QUESTIONS) in one for one in thrown), thrown


async def test_the_covers_ceiling_names_what_it_cut() -> None:
    llm = _Answering([{"label": "вид · 1", "ask": "як швидко?", "covers": LABELS[1:]}])

    probes, thrown, _tokens = await intent_probe(llm, LABELS)

    assert len(probes[0].covers) == MAX_COVERS
    assert any("покриття" in one for one in thrown), thrown


async def test_a_ceiling_that_did_not_fire_says_nothing() -> None:
    llm = _Answering([{"label": "вид · 1", "ask": "як швидко?", "covers": ["вид · 2"]}])

    _probes, thrown, _tokens = await intent_probe(llm, LABELS)

    assert thrown == []
