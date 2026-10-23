from __future__ import annotations

from datetime import UTC, datetime

from komora.core.slots import MIN_ORDERS_FOR_HABIT, Basis, basis_note, choose

NOW = datetime(2026, 9, 6, 8, tzinfo=UTC)


def _window(hour: int, *, day: int = 6, free: bool = True) -> tuple[str, bool]:
    return (f"2026-09-{day:02d}T{hour:02d}:00:00+00:00", free)


def test_the_habitual_hour_wins_over_the_earliest_free():
    windows = [_window(6), _window(12)]

    choice = choose(windows, wanted=None, habit={15: 19}, now=NOW)

    assert choice is not None
    assert choice.index == 1
    assert choice.basis is Basis.HABIT
    assert choice.hour == 15


def test_the_habit_is_stronger_than_the_cart_slot():
    windows = [_window(6), _window(12)]

    choice = choose(windows, wanted=windows[0][0], habit={15: 19}, now=NOW)

    assert choice is not None
    assert choice.basis is Basis.HABIT
    assert choice.index == 1
    assert choice.over_cart
    assert basis_note(choice).endswith("слот, що стояв у кошику, не брали")


def test_the_habit_beats_the_cart_slot_even_when_it_points_at_the_first_free():
    windows = [_window(12), _window(6, day=7)]

    choice = choose(windows, wanted=windows[1][0], habit={15: 19}, now=NOW)

    assert choice is not None
    assert choice.basis is Basis.HABIT
    assert choice.index == 0
    assert choice.over_cart


def test_a_cart_slot_in_the_habitual_hour_is_kept_as_the_cart_slot():
    windows = [_window(6), _window(12)]

    choice = choose(windows, wanted=windows[1][0], habit={15: 19}, now=NOW)

    assert choice is not None
    assert choice.basis is Basis.CART
    assert choice.index == 1
    assert not choice.over_cart


def test_a_cart_slot_stays_while_the_habit_is_silent():
    windows = [_window(6), _window(12)]

    choice = choose(windows, wanted=windows[0][0], habit={15: MIN_ORDERS_FOR_HABIT - 1}, now=NOW)

    assert choice is not None
    assert choice.basis is Basis.CART
    assert choice.index == 0
    assert basis_note(choice) == "слот уже стояв у кошику і досі вільний — не міняли"


def test_a_busy_habitual_window_does_not_win():
    windows = [_window(6), _window(12, free=False)]

    choice = choose(windows, wanted=None, habit={15: 19}, now=NOW)

    assert choice is not None
    assert choice.index == 0
    assert choice.basis is Basis.ONLY


def test_without_enough_orders_there_is_no_habit():
    windows = [_window(6), _window(12)]

    choice = choose(windows, wanted=None, habit={15: MIN_ORDERS_FOR_HABIT - 1}, now=NOW)

    assert choice is not None
    assert choice.basis is Basis.FIRST
    assert choice.index == 0


def test_an_empty_habit_keeps_todays_behaviour():
    windows = [_window(6), _window(12)]

    assert choose(windows, wanted=None, habit={}, now=NOW) == choose(windows, wanted=None)


def test_the_first_window_being_habitual_is_not_a_choice():
    windows = [_window(12), _window(6)]

    choice = choose(windows, wanted=None, habit={15: 19}, now=NOW)

    assert choice is not None
    assert choice.basis is Basis.FIRST


def test_the_most_frequent_hour_wins_among_several_habitual():
    windows = [_window(6), _window(9), _window(12)]

    choice = choose(windows, wanted=None, habit={9: 4, 12: 5, 15: 19}, now=NOW)

    assert choice is not None
    assert choice.index == 2
    assert choice.hour == 15
    assert choice.hour_orders == 19


def test_an_hour_the_guest_never_took_is_not_preferred():
    windows = [_window(6), _window(7)]

    choice = choose(windows, wanted=None, habit={15: 19}, now=NOW)

    assert choice is not None
    assert choice.basis is Basis.FIRST


def test_the_note_names_its_evidence():
    windows = [_window(6), _window(12)]

    choice = choose(windows, wanted=None, habit={15: 19, 12: 13}, now=NOW)

    assert choice is not None
    note = basis_note(choice)
    assert "15:00" in note
    assert "19 з 32" in note


def test_without_a_clock_the_habit_says_nothing():
    windows = [_window(6), _window(12)]

    choice = choose(windows, wanted=None, habit={15: 19}, now=None)

    assert choice is not None
    assert choice.basis is Basis.FIRST


def test_exactly_three_orders_are_already_a_habit():
    windows = [_window(6), _window(12)]

    choice = choose(windows, wanted=None, habit={15: MIN_ORDERS_FOR_HABIT}, now=NOW)

    assert choice is not None
    assert choice.basis is Basis.HABIT
    assert choice.index == 1


def test_a_single_order_in_an_hour_is_still_a_habit():
    windows = [_window(6), _window(9)]

    choice = choose(windows, wanted=None, habit={12: 1, 15: 19}, now=NOW)

    assert choice is not None
    assert choice.basis is Basis.HABIT
    assert choice.index == 1
    assert choice.hour_orders == 1


def test_a_window_with_no_orders_never_becomes_the_habit():
    windows = [(None, True), _window(6)]

    choice = choose(windows, wanted=None, habit={15: 19}, now=NOW)

    assert choice is not None
    assert choice.basis is Basis.FIRST
    assert choice.hour_orders == 0


def test_an_unreadable_window_is_skipped_and_not_a_full_stop():
    windows = [("не дата", True), _window(12)]

    choice = choose(windows, wanted=None, habit={15: 19}, now=NOW)

    assert choice is not None
    assert choice.basis is Basis.HABIT
    assert choice.index == 1


def test_a_slot_without_a_timezone_is_read_in_the_guests_day():
    windows = [_window(6), ("2026-09-06T12:00:00", True)]

    choice = choose(windows, wanted=None, habit={15: 19}, now=NOW)

    assert choice is not None
    assert choice.basis is Basis.HABIT
    assert choice.hour == 15


def test_the_hour_is_kyivs_and_not_the_machines():
    windows = [_window(6), _window(21)]

    choice = choose(windows, wanted=None, habit={0: 19}, now=NOW)

    assert choice is not None
    assert choice.basis is Basis.HABIT
    assert choice.hour == 0


def test_a_tie_keeps_the_nearest_window():
    windows = [_window(9), _window(12)]

    choice = choose(windows, wanted=None, habit={12: 7, 15: 7}, now=NOW)

    assert choice is not None
    assert choice.basis is Basis.FIRST
    assert choice.index == 0
