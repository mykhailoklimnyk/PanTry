from datetime import date

from komora.core.cycles import Keeps
from komora.core.shelf_life import BUFFER_DAYS, required_until, shelf_life_phrase

SLOT = date(2026, 8, 17)


def test_date_is_computed_from_the_cycle_not_asked():
    assert required_until(slot_day=SLOT, cycle_days=5, keeps=Keeps.DAYS) == date(
        2026, 8, 17 + 5 + BUFFER_DAYS
    )


def test_the_countdown_starts_at_the_slot_not_at_today():
    later = required_until(slot_day=date(2026, 8, 20), cycle_days=5, keeps=Keeps.DAYS)
    assert later == date(2026, 8, 20 + 5 + BUFFER_DAYS)


def test_fast_and_slow_kinds_get_different_deadlines():
    milk = required_until(slot_day=SLOT, cycle_days=3, keeps=Keeps.DAYS)
    cheese = required_until(slot_day=SLOT, cycle_days=20, keeps=Keeps.WEEKS)
    assert milk is not None and cheese is not None
    assert milk < cheese


def test_without_a_slot_there_is_no_point_of_reference():
    assert required_until(slot_day=None, cycle_days=5, keeps=Keeps.DAYS) is None


def test_an_unproven_cycle_invents_nothing():
    assert required_until(slot_day=SLOT, cycle_days=None, keeps=Keeps.DAYS) is None


def test_a_non_positive_cycle_is_not_a_cycle():
    assert required_until(slot_day=SLOT, cycle_days=0, keeps=Keeps.DAYS) is None


def test_an_unnamed_tier_asks_for_nothing():
    assert required_until(slot_day=SLOT, cycle_days=5, keeps=None) is None


def test_shampoo_and_groats_stay_silent():
    assert required_until(slot_day=SLOT, cycle_days=5, keeps=Keeps.MONTHS) is None
    assert required_until(slot_day=SLOT, cycle_days=5, keeps=Keeps.YEARS) is None


def test_weeks_tier_still_asks():
    assert required_until(slot_day=SLOT, cycle_days=7, keeps=Keeps.WEEKS) is not None


def test_an_impossible_promise_is_not_made():
    assert required_until(slot_day=SLOT, cycle_days=6, keeps=Keeps.DAYS) is None


def test_the_edge_of_the_tier_is_still_asked_for():
    assert required_until(slot_day=SLOT, cycle_days=5, keeps=Keeps.DAYS) is not None


def test_phrase_names_a_date_because_that_is_what_a_human_can_do():
    assert shelf_life_phrase(date(2026, 8, 19)) == "термін придатності не менше ніж до 19.08"


def test_no_phrase_without_a_deadline():
    assert shelf_life_phrase(None) is None
