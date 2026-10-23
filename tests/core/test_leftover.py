from __future__ import annotations

from decimal import Decimal

from komora.core.leftover import leftover


def test_fresh_purchase_leaves_the_whole_cycle():
    left = leftover(cycle_days=7, days_since=0, typical_qty=3)
    assert left.left_ratio == 1.0
    assert left.days_left == 7
    assert left.running_out is False
    assert left.qty == 3


def test_the_cycle_runs_out_on_the_day_it_ends():
    assert leftover(cycle_days=7, days_since=6, typical_qty=2).running_out is False
    assert leftover(cycle_days=7, days_since=7, typical_qty=2).running_out is True
    assert leftover(cycle_days=7, days_since=99, typical_qty=2).running_out is True


def test_what_ran_out_shows_an_empty_bar_and_zero_days():
    left = leftover(cycle_days=3, days_since=9, typical_qty=4)
    assert left.left_ratio == 0.0, "смуга порожня, а не від'ємна"
    assert left.days_left == 0
    assert left.qty == 0, "нуль лишається там, де він означає «закінчилось»"


def test_days_left_counts_down_with_the_cycle():
    assert leftover(cycle_days=7, days_since=4, typical_qty=1).days_left == 3
    assert leftover(cycle_days=7, days_since=1, typical_qty=1).days_left == 6


def test_the_share_left_is_the_bar():
    left = leftover(cycle_days=10, days_since=3, typical_qty=1)
    assert left.left_ratio == 0.7


def test_a_kind_taken_one_at_a_time_has_no_number_at_all():
    assert leftover(cycle_days=7, days_since=4, typical_qty=1).qty is None
    assert leftover(cycle_days=7, days_since=9, typical_qty=1).qty is None
    assert leftover(cycle_days=7, days_since=0, typical_qty=0).qty is None


def test_something_that_is_still_at_home_never_shows_zero():
    assert leftover(cycle_days=7, days_since=6, typical_qty=2).qty == 1
    assert leftover(cycle_days=7, days_since=4, typical_qty=3).qty == 1


def test_the_number_of_pieces_follows_the_share_left():
    assert leftover(cycle_days=10, days_since=1, typical_qty=6).qty == 5
    assert leftover(cycle_days=10, days_since=5, typical_qty=6).qty == 3
    assert leftover(cycle_days=10, days_since=8, typical_qty=6).qty == 1


def test_a_weighed_kind_is_measured_in_parts_not_in_pieces():
    half = leftover(
        cycle_days=10,
        days_since=5,
        typical_qty=Decimal("0.3"),
        smallest=Decimal("0.1"),
    )

    assert half.qty == Decimal("0.2"), "0,3 * 0,5 — це 150 г, тобто десь 0,2 кг"


def test_the_weighed_floor_is_its_own_step_not_a_whole_unit():
    nearly = leftover(
        cycle_days=10,
        days_since=9,
        typical_qty=Decimal("0.3"),
        smallest=Decimal("0.1"),
    )

    assert nearly.qty == Decimal("0.1")


def test_a_weight_smaller_than_its_own_step_has_no_number():
    assert (
        leftover(
            cycle_days=10,
            days_since=2,
            typical_qty=Decimal("0.1"),
            smallest=Decimal("0.1"),
        ).qty
        is None
    )


def test_a_stock_ahead_shows_more_than_a_full_cycle():
    left = leftover(cycle_days=7, days_since=-21, typical_qty=1)

    assert left.running_out is False
    assert left.left_ratio == 4.0
    assert left.days_left == 28


def test_a_stock_ahead_gives_a_quantity_where_the_usual_one_could_not():
    assert leftover(cycle_days=7, days_since=0, typical_qty=1).qty is None
    assert leftover(cycle_days=7, days_since=-21, typical_qty=1).qty == Decimal(4)


def test_a_double_purchase_is_already_enough_to_show_the_number():
    assert leftover(cycle_days=7, days_since=-7, typical_qty=1).qty == Decimal(2)


def test_a_weighed_stock_ahead_stays_on_its_own_step():
    left = leftover(
        cycle_days=10,
        days_since=-20,
        typical_qty=Decimal("0.3"),
        smallest=Decimal("0.1"),
    )

    assert left.qty == Decimal("0.9")
    assert left.days_left == 30
