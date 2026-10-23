from __future__ import annotations

from decimal import Decimal
from typing import Any

from komora.core.carryover import carried_over


def _row(product_id: str, name: str, **kwargs: Any) -> dict[str, Any]:
    return {
        "productId": product_id,
        "name": name,
        "quantity": kwargs.pop("quantity", 1),
        "total": kwargs.pop("total", "50.00"),
        **kwargs,
    }


def test_a_row_we_are_writing_is_not_carried_over():
    extras = carried_over([_row("a", "Молоко"), _row("b", "Кава")], writing={"a"})

    assert [row.name for row in extras.rows] == ["Кава"]


def test_an_empty_difference_is_falsy_and_costs_nothing():
    extras = carried_over([_row("a", "Молоко")], writing={"a"})

    assert not extras
    assert extras.total == Decimal(0)


def test_the_sum_comes_from_the_row_not_from_price_times_quantity():
    row = _row("a", "Рулет", quantity="0.3", total="215.70", price="719.00")

    extras = carried_over([row], writing=set())

    assert extras.rows[0].total == Decimal("215.70")
    assert extras.total == Decimal("215.70")


def test_the_total_sums_every_row():
    rows = [_row("a", "Молоко", total="42.50"), _row("b", "Кава", total="180.00")]

    assert carried_over(rows, writing=set()).total == Decimal("222.50")


def test_cart_order_survives():
    rows = [_row("c", "Ягоди"), _row("a", "Молоко"), _row("b", "Кава")]

    extras = carried_over(rows, writing=set())

    assert [row.name for row in extras.rows] == ["Ягоди", "Молоко", "Кава"]


def test_a_row_without_a_product_id_is_not_offered_for_removal():
    rows = [{"name": "Загадка", "total": "10"}, _row("b", "Кава")]

    extras = carried_over(rows, writing=set())

    assert [row.name for row in extras.rows] == ["Кава"]


def test_a_nameless_row_says_so_instead_of_vanishing():
    extras = carried_over([{"productId": "a", "total": "10"}], writing=set())

    assert extras.rows[0].name == "рядок без назви"


def test_a_broken_number_reads_as_zero_and_not_as_a_crash():
    rows = [{"productId": "a", "name": "Молоко", "quantity": None, "total": ""}]

    extras = carried_over(rows, writing=set())

    assert extras.rows[0].quantity == Decimal(0)
    assert extras.total == Decimal(0)


def test_the_product_id_travels_to_the_removal_call():
    extras = carried_over([_row("00000000-0000-4000-8000-000000000001", "Кава")], writing=set())

    assert extras.rows[0].product_id == "00000000-0000-4000-8000-000000000001"


def test_the_quantity_reaches_the_guest_as_the_cart_holds_it():
    rows = [_row("a", "Кава", quantity=2), _row("b", "Рулет", quantity="0.3")]

    extras = carried_over(rows, writing=set())

    assert [row.quantity for row in extras.rows] == [Decimal(2), Decimal("0.3")]
