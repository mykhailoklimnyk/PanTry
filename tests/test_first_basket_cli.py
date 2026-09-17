from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "first_basket", Path(__file__).resolve().parents[1] / "scripts" / "first_basket.py"
)
assert _SPEC and _SPEC.loader
first_basket = importlib.util.module_from_spec(_SPEC)
sys.modules["first_basket"] = first_basket
_SPEC.loader.exec_module(first_basket)


def test_slug_answer_picks_the_node() -> None:
    (answer,) = first_basket.parse_answers(["сир=syr-kyslomolochnyi-4988"])
    assert answer.intent == "сир"
    assert answer.slug == "syr-kyslomolochnyi-4988"
    assert answer.text is None and answer.skip is False


def test_words_answer_stays_words() -> None:
    (answer,) = first_basket.parse_answers(["сир=бринза для салату"])
    assert answer.slug is None
    assert answer.text == "бринза для салату"


def test_skip_is_a_full_answer() -> None:
    (answer,) = first_basket.parse_answers(["сир=«не треба»"])
    assert answer.skip is True
    assert answer.slug is None and answer.text is None


def test_several_answers_travel_together() -> None:
    answers = first_basket.parse_answers(["сир=syry", "вода = негазована"])
    assert [a.intent for a in answers] == ["сир", "вода"]
    assert answers[1].text == "негазована"


@pytest.mark.parametrize("raw", ["сир", "=syry", "сир=", "  =  "])
def test_a_broken_answer_is_loud(raw: str) -> None:
    with pytest.raises(ValueError, match="намір=відповідь"):
        first_basket.parse_answers([raw])
