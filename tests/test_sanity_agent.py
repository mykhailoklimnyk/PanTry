from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pytest

from komora.agent.prompts import digest_of
from komora.agent.sanity import forget_sense, intent_sense
from komora.db.facts import Facts

pytestmark = pytest.mark.anyio


@dataclass
class _Usage:
    input_tokens: int = 10
    output_tokens: int = 20


@dataclass
class _Decision:
    data: dict[str, Any]
    usage: _Usage = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.usage is None:
            self.usage = _Usage()


class _LLM:
    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        self.asked: list[dict[str, Any]] = []

    async def decide(self, **kwargs: Any) -> _Decision:
        self.asked.append(kwargs)
        return _Decision(self.data)


class _Dead:
    async def decide(self, **_kwargs: Any) -> _Decision:
        raise ConnectionError("модель не відповідає")


def _said(
    label: str,
    sanity: str = "з'їдають за раз",
    lies: bool = True,
    per_day: float = 1.0,
    unit: str = "шт",
) -> dict[str, Any]:
    return {
        "label": label,
        "sanity": sanity,
        "rhythm_lies": lies,
        "per_day": per_day,
        "per_day_unit": unit,
        "aisle": None,
    }


@pytest.fixture(autouse=True)
def _clean() -> None:
    forget_sense()


async def test_the_model_answers_and_the_verdict_comes_along():
    llm = _LLM({"kinds": [_said("паляничка")]})

    got = await intent_sense(llm, ["паляничка"])

    assert got["паляничка"] == Facts(
        sanity="з'їдають за раз",
        rhythm_lies=True,
        per_day=Decimal("1.0"),
        per_day_unit="шт",
    )


async def test_the_second_ask_costs_no_call():
    llm = _LLM({"kinds": [_said("паляничка")]})

    await intent_sense(llm, ["паляничка"])
    await intent_sense(llm, ["паляничка"])

    assert len(llm.asked) == 1


async def test_an_echo_that_lost_the_separator_still_lands_on_the_asked_label():
    llm = _LLM({"kinds": [_said("йогурт фруктовий")]})

    got = await intent_sense(llm, ["йогурт · фруктовий"])

    assert list(got) == ["йогурт · фруктовий"]


async def test_an_echo_that_drifted_lands_under_no_key_at_all():
    llm = _LLM({"kinds": [_said("паляничк")]})

    got = await intent_sense(llm, ["паляничка"])

    assert got == {}


async def test_an_empty_sentence_is_not_an_answer():
    llm = _LLM({"kinds": [_said("паляничка", sanity="  ")]})

    assert await intent_sense(llm, ["паляничка"]) == {}


async def test_a_dead_model_leaves_the_pantry_working():
    assert await intent_sense(_Dead(), ["паляничка"]) == {}


async def test_without_a_model_there_is_no_sense_and_no_crash():
    assert await intent_sense(None, ["паляничка"]) == {}


async def test_an_empty_label_is_never_asked_about():
    llm = _LLM({"kinds": []})

    await intent_sense(llm, ["", "  "])

    assert llm.asked == []


async def test_the_call_says_which_prompt_it_used():
    llm = _LLM({"kinds": []})

    await intent_sense(llm, ["паляничка"])

    assert llm.asked[0]["prompt"] == f"sanity@{digest_of('sanity')}"


async def test_the_answer_is_frozen_so_the_call_is_deterministic():
    llm = _LLM({"kinds": []})

    await intent_sense(llm, ["паляничка"])

    assert llm.asked[0]["temperature"] == 0.0


async def test_only_the_labels_we_do_not_know_go_into_the_call():
    llm = _LLM({"kinds": [_said("паляничка")]})
    await intent_sense(llm, ["паляничка"])

    llm.data = {"kinds": [_said("морозиво", sanity="сезон", lies=True)]}
    await intent_sense(llm, ["паляничка", "морозиво"])

    assert "паляничка" not in llm.asked[1]["user"]


class _Pool:

    def __init__(self, known: dict[str, Facts]) -> None:
        self.known = known
        self.saved: dict[str, Facts] = {}


async def test_the_database_answer_saves_the_call(monkeypatch: pytest.MonkeyPatch) -> None:
    llm = _LLM({"kinds": [_said("паляничка")]})
    pool = _Pool({"паляничка": Facts(sanity="з бази", rhythm_lies=False)})

    async def _load(_pool: Any, labels: Any) -> dict[str, Facts]:
        return {label: pool.known[label] for label in labels if label in pool.known}

    monkeypatch.setattr("komora.agent.sanity.facts_store.load", _load)

    got = await intent_sense(llm, ["паляничка"], pool=pool)

    assert llm.asked == []
    assert got["паляничка"].sanity == "з бази"


async def test_the_ceiling_clears_the_measured_tail_not_the_average() -> None:
    measured_max = 3129 / 40
    llm = _LLM({"kinds": []})

    await intent_sense(llm, [f"вид {i}" for i in range(40)])

    assert llm.asked[0]["max_tokens"] >= measured_max * 40 * 1.4


async def test_a_row_written_by_the_neighbour_is_not_an_answer_to_this_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = _LLM({"kinds": [_said("паляничка")]})

    async def _load(_pool: Any, labels: Any) -> dict[str, Facts]:
        return {label: Facts(keeps="дні") for label in labels}

    async def _save(_pool: Any, _sense: dict[str, Facts]) -> None:
        return None

    monkeypatch.setattr("komora.agent.sanity.facts_store.load", _load)
    monkeypatch.setattr("komora.agent.sanity.facts_store.save", _save)

    got = await intent_sense(llm, ["паляничка"], pool=object())

    assert llm.asked, "стеля сусіда не є відповіддю про глузд"
    assert got["паляничка"].sanity == "з'їдають за раз"


async def test_a_database_that_does_not_answer_does_not_stop_the_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = _LLM({"kinds": [_said("паляничка")]})

    async def _load(_pool: Any, _labels: Any) -> dict[str, Facts]:
        raise TimeoutError("база мовчить")

    monkeypatch.setattr("komora.agent.sanity.facts_store.load", _load)

    got = await intent_sense(llm, ["паляничка"], pool=_Pool({}))

    assert got["паляничка"].rhythm_lies is True


async def test_what_the_model_said_goes_back_into_the_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = _LLM({"kinds": [_said("паляничка")]})
    pool = _Pool({})

    async def _load(_pool: Any, _labels: Any) -> dict[str, Facts]:
        return {}

    async def _save(_pool: Any, sense: dict[str, Facts]) -> None:
        pool.saved.update(sense)

    monkeypatch.setattr("komora.agent.sanity.facts_store.load", _load)
    monkeypatch.setattr("komora.agent.sanity.facts_store.save", _save)

    await intent_sense(llm, ["паляничка"], pool=pool)

    assert pool.saved["паляничка"].sanity == "з'їдають за раз"


async def test_a_database_that_cannot_write_does_not_break_the_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = _LLM({"kinds": [_said("паляничка")]})

    async def _load(_pool: Any, _labels: Any) -> dict[str, Facts]:
        return {}

    async def _save(_pool: Any, _sense: dict[str, Facts]) -> None:
        raise TimeoutError("база мовчить")

    monkeypatch.setattr("komora.agent.sanity.facts_store.load", _load)
    monkeypatch.setattr("komora.agent.sanity.facts_store.save", _save)

    got = await intent_sense(llm, ["паляничка"], pool=_Pool({}))

    assert got["паляничка"].rhythm_lies is True


async def test_a_norm_the_model_does_not_know_is_zero_and_that_is_honest():
    llm = _LLM({"kinds": [_said("сіль", per_day=0)]})

    got = await intent_sense(llm, ["сіль"])

    assert got["сіль"].per_day is None


async def test_a_norm_that_is_not_a_number_does_not_break_the_pantry():
    llm = _LLM(
        {"kinds": [{"label": "сіль", "sanity": "рівно", "rhythm_lies": False, "per_day": "?"}]}
    )

    got = await intent_sense(llm, ["сіль"])

    assert got["сіль"].per_day is None


async def test_a_unit_we_cannot_compare_is_dropped_and_not_guessed():
    llm = _LLM({"kinds": [_said("вода", per_day=1500, unit="мл")]})

    got = await intent_sense(llm, ["вода"])

    assert got["вода"].per_day_unit is None
