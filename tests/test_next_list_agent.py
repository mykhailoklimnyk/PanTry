from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from komora.agent.nextlist import NEXT_SYSTEM, compose
from komora.agent.prompts import digest_of
from komora.core.nextlist import OUT, PROMO, Pick

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


PICKS = (Pick("хліб", "Хліб", OUT, 0), Pick("пиво", "Пиво", PROMO, 1))


async def test_the_agent_orders_and_names_and_the_call_says_which_prompt() -> None:
    llm = _LLM({"list": [{"key": "пиво", "why": "візьму, якщо буде акція"}]})

    said = await compose(llm, PICKS)

    assert [row[0] for row in said.rows] == ["пиво"]
    assert said.rows[0][2] == "візьму, якщо буде акція"
    assert said.prompt == f"nextlist@{digest_of('nextlist')}"
    assert "зняв 1" in said.note, "знята позиція називається числом (#132)"


async def test_a_key_the_pantry_never_named_is_a_burnt_row_not_a_new_kind() -> None:
    llm = _LLM({"list": [{"key": "ікра", "why": "свято"}, {"key": "хліб", "why": "нема"}]})

    said = await compose(llm, PICKS)

    assert [row[0] for row in said.rows] == ["хліб"]


async def test_a_repeated_key_does_not_become_two_rows() -> None:
    llm = _LLM({"list": [{"key": "хліб", "why": "раз"}, {"key": "хліб", "why": "два"}]})

    assert [row[0] for row in (await compose(llm, PICKS)).rows] == ["хліб"]


async def test_an_empty_answer_falls_back_to_the_code_and_says_so() -> None:
    said = await compose(_LLM({"list": []}), PICKS)

    assert [row[0] for row in said.rows] == ["хліб", "пиво"]
    assert "з коду" in said.note


async def test_a_dead_model_does_not_take_the_list_with_it() -> None:
    said = await compose(_Dead(), PICKS)

    assert [row[0] for row in said.rows] == ["хліб", "пиво"]
    assert "модель не відповіла" in said.note


async def test_without_a_model_the_order_and_the_reasons_are_the_codes_own() -> None:
    said = await compose(None, PICKS)

    assert [row[2] for row in said.rows] == [
        "закінчилось сьогодні",
        "береш це по акції — без знижки не бери",
    ]
    assert said.note == "без агента: порядок і підстави з коду"


async def test_an_empty_pantry_is_not_a_call_to_the_model() -> None:
    llm = _LLM({"list": []})

    said = await compose(llm, ())

    assert said.rows == [] and not llm.asked
    assert "жодного виду" in said.note


async def test_the_reason_of_a_row_never_comes_back_empty() -> None:
    llm = _LLM({"list": [{"key": "хліб", "why": "   "}]})

    assert (await compose(llm, PICKS)).rows[0][2] == "закінчилось сьогодні"


async def test_the_prompt_the_call_carries_is_the_registered_one() -> None:
    llm = _LLM({"list": [{"key": "хліб", "why": "нема"}]})

    await compose(llm, PICKS)

    assert llm.asked[0]["system"] == NEXT_SYSTEM
    assert llm.asked[0]["schema_name"] == "nextlist"
