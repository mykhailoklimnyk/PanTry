from __future__ import annotations

from datetime import UTC, datetime, timedelta

from komora.core.marks import bought_now, stocked_at

NOW = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)


def test_the_usual_amount_at_home_means_just_restocked():
    assert stocked_at(now=NOW, cycle_days=14, typical_qty=4, qty=4) == NOW


def test_half_the_usual_amount_is_half_the_cycle():
    assert stocked_at(now=NOW, cycle_days=14, typical_qty=4, qty=2) == NOW - timedelta(days=7)


def test_nothing_left_means_the_cycle_is_over():
    assert stocked_at(now=NOW, cycle_days=14, typical_qty=4, qty=0) == NOW - timedelta(days=14)


def test_more_than_usual_puts_the_point_into_the_future():
    assert stocked_at(now=NOW, cycle_days=14, typical_qty=4, qty=8) == NOW + timedelta(days=14)


def test_a_stock_ahead_holds_for_as_many_cycles_as_it_was_bought_for():
    said = stocked_at(now=NOW, cycle_days=7, typical_qty=1, qty=4)
    assert said == NOW + timedelta(days=21)


def test_the_stock_ahead_axis_is_the_same_one_for_weight():
    said = stocked_at(now=NOW, cycle_days=10, typical_qty=0.3, qty=0.9)
    assert said == NOW + timedelta(days=20)


def test_a_negative_amount_does_not_push_the_point_past_the_cycle():
    assert stocked_at(now=NOW, cycle_days=14, typical_qty=4, qty=-2) == NOW - timedelta(days=14)


def test_weight_works_on_the_same_axis_as_pieces():
    assert stocked_at(now=NOW, cycle_days=10, typical_qty=0.3, qty=0.15) == NOW - timedelta(
        days=5
    )


def test_without_a_usual_amount_any_number_means_it_is_at_home():
    assert stocked_at(now=NOW, cycle_days=14, typical_qty=0, qty=3) == NOW


def test_the_axis_is_daily_because_the_cycle_is_daily():
    said = stocked_at(now=NOW, cycle_days=7, typical_qty=3, qty=1)
    assert (NOW - said).seconds == 0


def test_bought_has_no_quantity_in_it():
    assert bought_now(NOW) == NOW
