from __future__ import annotations

from decimal import Decimal
from typing import Any

from komora.agent.basket import PlanLine, collapse_same_product

TOMATO = "Томат Гордій Черрі"


def _product(pid: str, name: str) -> dict[str, Any]:
    return {
        "externalProductId": pid,
        "name": name,
        "price": 71.99,
        "stock": 20,
        "available": True,
    }


def _line(intent: str, pid: str, name: str, qty: str = "1", **kw: Any) -> PlanLine:
    return PlanLine(
        intent=intent,
        product=_product(pid, name),
        qty=Decimal(qty),
        reason="тест",
        from_history=None,
        **kw,
    )


def test_three_kinds_one_shelf_item_make_one_row():
    lines = [
        _line("томат черрі", "979172", TOMATO),
        _line("томат", "979172", TOMATO),
        _line("томат рожевий", "979172", TOMATO),
        _line("молоко", "111", "Молоко Селянське 2,5%"),
    ]

    merged = collapse_same_product(lines)

    assert [line.intent for line in lines] == ["томат черрі", "молоко"]
    assert merged == [(TOMATO, 3)]


def test_the_quantity_is_the_largest_and_not_the_sum():
    lines = [
        _line("філе", "750297", "Філе куряче", qty="1.2"),
        _line("куряче філе", "750297", "Філе куряче", qty="0.6"),
    ]

    collapse_same_product(lines)

    assert [line.qty for line in lines] == [Decimal("1.2")]


def test_the_row_that_ships_survives_the_one_that_stays_home():
    lines = [
        _line("томат", "979172", TOMATO, at_home=True),
        _line("томат черрі", "979172", TOMATO),
    ]

    collapse_same_product(lines)

    assert [line.intent for line in lines] == ["томат черрі"]
    assert not lines[0].at_home


def test_two_rows_alike_in_every_field_still_collapse_to_one():
    lines = [
        _line("томат", "979172", TOMATO),
        _line("томат", "979172", TOMATO),
    ]

    merged = collapse_same_product(lines)

    assert len(lines) == 1
    assert merged == [(TOMATO, 2)]


def test_different_articles_are_left_alone():
    lines = [
        _line("томат черрі", "979172", TOMATO),
        _line("томат рожевий", "998781", "Томат Ріана черрі рожевий"),
    ]

    assert collapse_same_product(lines) == []
    assert len(lines) == 2
