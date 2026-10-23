from __future__ import annotations

import pytest

from komora.core import words

FORMS = ("позиція", "позиції", "позицій")


@pytest.mark.parametrize("count", [1, 21, 101, 1001])
def test_one_takes_the_singular(count: int):
    assert words.plural(count, *FORMS) == "позиція"


@pytest.mark.parametrize("count", [2, 3, 4, 22, 33, 44, 102])
def test_two_to_four_take_the_short_plural(count: int):
    assert words.plural(count, *FORMS) == "позиції"


@pytest.mark.parametrize("count", [0, 5, 9, 10, 20, 25, 100])
def test_five_and_above_take_the_long_plural(count: int):
    assert words.plural(count, *FORMS) == "позицій"


@pytest.mark.parametrize("count", [11, 12, 13, 14, 111, 112, 113, 114])
def test_the_teens_break_the_last_digit_rule(count: int):
    assert words.plural(count, *FORMS) == "позицій"


def test_a_negative_number_keeps_the_same_rule():
    assert words.plural(-1, *FORMS) == "позиція"
    assert words.plural(-3, *FORMS) == "позиції"
    assert words.plural(-11, *FORMS) == "позицій"


@pytest.mark.parametrize(
    ("count", "word"),
    [(1, "рядок"), (2, "рядки"), (5, "рядків"), (11, "рядків"), (21, "рядок")],
)
def test_rows_are_the_same_rule_with_its_own_word(count: int, word: str):
    assert words.rows(count) == word
