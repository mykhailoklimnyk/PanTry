from datetime import date, timedelta

import pytest

from komora.core.cycles import (
    FOREIGN_NOTE,
    SILENCE_LIMIT,
    Keeps,
    Trust,
    ceiling_days,
    coverage_note,
    intervals_days,
    is_stable,
    median,
    rhythm,
    stddev,
)


def test_median_of_odd_and_even_samples():
    assert median([7.0, 1.0, 3.0]) == 3.0
    assert median([1.0, 3.0, 5.0, 7.0]) == 4.0


def test_median_of_empty_sample_is_an_error():
    with pytest.raises(ValueError, match="порожньої"):
        median([])


def test_stddev_of_single_point_is_zero():
    assert stddev([5.0]) == 0.0


def test_stddev_of_identical_values_is_zero():
    assert stddev([4.0, 4.0, 4.0]) == 0.0


def test_intervals_ignore_repeated_dates():
    dates = [date(2026, 8, 1), date(2026, 8, 1), date(2026, 8, 8)]
    assert intervals_days(dates) == [7.0]


def test_intervals_are_order_independent():
    assert intervals_days([date(2026, 8, 8), date(2026, 8, 1)]) == [7.0]


def test_intervals_of_single_purchase_are_empty():
    assert intervals_days([date(2026, 8, 1)]) == []


def test_water_is_stable_and_gets_a_date():
    assert is_stable(purchases_count=6, median_days=16.0, stddev_days=15.0) is True


def test_cheese_is_not_stable_and_gets_no_date():
    assert is_stable(purchases_count=6, median_days=45.0, stddev_days=45.0) is True
    assert is_stable(purchases_count=6, median_days=28.0, stddev_days=45.0) is False


def test_few_purchases_never_count_as_stable():
    assert is_stable(purchases_count=2, median_days=7.0, stddev_days=0.0) is False
    assert is_stable(purchases_count=3, median_days=7.0, stddev_days=0.0) is False
    assert is_stable(purchases_count=4, median_days=7.0, stddev_days=0.0) is True


def test_a_weekly_item_keeps_its_cycle():
    beat = rhythm(
        [date(2026, 7, 4), date(2026, 7, 11), date(2026, 7, 18), date(2026, 7, 25)],
        days_since=3,
    )

    assert beat.trust is Trust.CYCLE
    assert beat.cycle_days == 7
    assert beat.purchases == 4
    assert beat.proven
    assert beat.phrase() == "", "доведений цикл пояснює себе залишком, а не словами"


def test_a_seasonal_item_keeps_its_number_but_loses_the_claim():
    beat = rhythm(
        [date(2026, 4, 26), date(2026, 6, 1), date(2026, 7, 1), date(2026, 8, 6)],
        days_since=90,
    )

    assert beat.trust is Trust.SILENT
    assert beat.cycle_days == 36
    assert beat.silence == pytest.approx(90 / 36)
    assert "давно не брав" in beat.phrase()
    assert "90" in beat.phrase() and "36" in beat.phrase()


def test_a_burst_loses_the_cycle_because_the_median_measured_the_burst():
    beat = rhythm(
        [date(2026, 6, 6), date(2026, 6, 7), date(2026, 7, 4), date(2026, 7, 5)],
        days_since=20,
    )

    assert beat.trust is Trust.RARE
    assert beat.cycle_days is None
    assert beat.silence is None
    assert "від 1 до 27 дн" in beat.phrase()


def test_two_purchases_are_a_guess_not_a_cycle():
    beat = rhythm([date(2026, 8, 1), date(2026, 8, 11)], days_since=12)

    assert beat.trust is Trust.RARE
    assert beat.cycle_days is None
    assert beat.purchases == 2
    assert "ще дві, і скажу цикл" in beat.phrase()


def test_three_purchases_are_two_coincidences_and_still_not_a_cycle():
    beat = rhythm([date(2026, 8, 1), date(2026, 8, 8), date(2026, 8, 15)], days_since=7)

    assert beat.trust is Trust.RARE
    assert beat.cycle_days is None
    assert beat.purchases == 3
    assert "ще одна, і скажу цикл" in beat.phrase()


def test_a_kind_without_purchases_says_so_instead_of_falling():
    beat = rhythm([], days_since=None)

    assert beat.trust is Trust.RARE
    assert beat.cycle_days is None
    assert beat.shortest is None
    assert beat.phrase()


def test_silence_is_counted_forward_only():
    beat = rhythm(
        [date(2026, 6, 27), date(2026, 7, 4), date(2026, 7, 11), date(2026, 7, 18)],
        days_since=-14,
    )

    assert beat.trust is Trust.CYCLE
    assert beat.cycle_days == 7


def test_the_silence_limit_is_a_border_not_a_hint():
    dates = [date(2026, 6, 27), date(2026, 7, 4), date(2026, 7, 11), date(2026, 7, 18)]

    assert rhythm(dates, days_since=int(SILENCE_LIMIT * 7)).trust is Trust.CYCLE
    assert rhythm(dates, days_since=int(SILENCE_LIMIT * 7) + 1).trust is Trust.SILENT


def test_the_shortest_and_longest_gaps_are_the_proof_of_an_uneven_rhythm():
    beat = rhythm(
        [date(2026, 5, 30), date(2026, 6, 1), date(2026, 6, 3), date(2026, 8, 1)],
        days_since=5,
    )

    assert beat.shortest == 2
    assert beat.longest == 59
    assert "від 2 до 59 дн" in beat.phrase()
    assert "остання 5 дн тому" in beat.phrase()


def test_stddev_divides_by_the_sample_size():
    assert stddev([1.0, 2.0, 3.0, 4.0, 5.0]) == pytest.approx(1.5811, rel=1e-3)


def test_a_cycle_of_one_day_stays_one_day():
    beat = rhythm(
        [date(2026, 7, 31), date(2026, 8, 1), date(2026, 8, 2), date(2026, 8, 3)], days_since=1
    )

    assert beat.cycle_days == 1
    assert beat.trust is Trust.CYCLE


def test_a_zero_median_is_not_a_stable_cycle():
    assert is_stable(purchases_count=5, median_days=None, stddev_days=0.0) is False
    assert is_stable(purchases_count=5, median_days=0.0, stddev_days=0.0) is False


def test_the_gap_range_is_carried_by_every_rhythm_not_only_the_uneven_one():
    beat = rhythm(
        [date(2026, 6, 26), date(2026, 7, 4), date(2026, 7, 12), date(2026, 7, 18)], days_since=2
    )

    assert beat.trust is Trust.CYCLE
    assert (beat.shortest, beat.longest) == (6, 8)


def test_the_undershoot_names_both_numbers():
    note = coverage_note(takes_cycles=True, receipts=47, kinds=44, uneven=32, tracked_from=3)

    assert "12" in note and "44" in note
    assert "нерівно" in note
    assert "напиши, що треба" in note, "порада мусить пасувати причині"


def test_a_guest_without_receipts_is_not_told_that_nothing_runs_out():
    note = coverage_note(takes_cycles=True, receipts=0, kinds=0, uneven=0, tracked_from=3)

    assert "історії покупок ще немає" in note
    assert "закінчується" not in note


def test_receipts_without_a_single_tracked_kind_say_so():
    note = coverage_note(takes_cycles=True, receipts=5, kinds=0, uneven=0, tracked_from=3)

    assert "3 покупок у різні дні" in note
    assert "історії покупок ще немає" not in note


def test_a_pantry_without_a_single_proven_rhythm_does_not_claim_one():
    note = coverage_note(takes_cycles=True, receipts=20, kinds=7, uneven=7, tracked_from=3)

    assert "усі 7 видів" in note
    assert " 0 " not in note


def test_a_fully_proven_pantry_says_nothing_about_uneven_kinds():
    note = coverage_note(takes_cycles=True, receipts=20, kinds=7, uneven=0, tracked_from=3)

    assert "нерівно" not in note
    assert "7" in note


def test_the_list_mode_does_not_blame_the_receipts_of_the_guest():
    note = coverage_note(takes_cycles=False, receipts=5, kinds=0, uneven=0, tracked_from=3)

    assert "3 покупок у різні дні" not in note
    assert "історії покупок ще немає" not in note
    assert "зі списку" in note and "цикли" in note


def test_the_list_mode_leaves_the_guest_two_doors():
    note = coverage_note(takes_cycles=False, receipts=47, kinds=0, uneven=0, tracked_from=3)

    assert "напиши, що треба" in note
    assert "на тиждень" in note
    assert note.startswith("у режимі «зі списку»")
    assert note.endswith("на тиждень»")


def test_the_list_mode_wins_over_every_number_it_is_given():
    listed = coverage_note(takes_cycles=False, receipts=47, kinds=44, uneven=32, tracked_from=3)
    weekly = coverage_note(takes_cycles=True, receipts=47, kinds=44, uneven=32, tracked_from=3)

    assert "44" not in listed
    assert listed != weekly


def test_an_empty_history_in_the_list_mode_is_still_about_the_list():
    note = coverage_note(takes_cycles=False, receipts=0, kinds=0, uneven=0, tracked_from=3)

    assert "історії покупок ще немає" not in note
    assert "зі списку" in note


def test_a_foreign_cart_does_not_borrow_the_words_of_the_cycles():
    assert "хтось інший" in FOREIGN_NOTE
    assert "закінчується" not in FOREIGN_NOTE


def test_one_proven_rhythm_is_not_the_same_as_none():
    note = coverage_note(takes_cycles=True, receipts=20, kinds=7, uneven=6, tracked_from=3)

    assert "усі 7" not in note
    assert "1 з 7" in note


def _days(*ago: int) -> list[date]:
    today = date(2026, 8, 26)
    return [today - timedelta(days=n) for n in ago]


def test_the_named_cycle_beats_everything_the_receipts_say():
    days = _days(96, 64, 32, 0)

    from_receipts = rhythm(days, days_since=32)
    from_guest = rhythm(days, days_since=32, said_days=2)

    assert (from_receipts.trust, from_receipts.cycle_days) == (Trust.CYCLE, 32)
    assert (from_guest.trust, from_guest.cycle_days) == (Trust.SAID, 2)


def test_the_named_cycle_wins_even_where_there_was_no_cycle_at_all():
    uneven = _days(72, 70, 68, 2)
    assert rhythm(uneven, days_since=2).trust is Trust.RARE

    said = rhythm(uneven, days_since=2, said_days=10)

    assert said.trust is Trust.SAID
    assert said.cycle_days == 10
    assert said.proven is True


def test_the_named_cycle_never_turns_into_silence():
    days = _days(205, 170, 135, 100)

    assert rhythm(days, days_since=100).trust is Trust.SILENT
    assert rhythm(days, days_since=100, said_days=2).trust is Trust.SAID


def test_zero_days_is_an_empty_field_and_not_a_cycle():
    days = _days(21, 14, 7, 0)

    assert rhythm(days, days_since=0, said_days=0).trust is Trust.CYCLE
    assert rhythm(days, days_since=0, said_days=-3).trust is Trust.CYCLE
    assert rhythm(days, days_since=0, said_days=1).cycle_days == 1


def test_the_named_row_keeps_its_own_spread_as_evidence():
    said = rhythm(_days(72, 70, 68, 2), days_since=2, said_days=10)

    assert (said.shortest, said.longest) == (2, 66)
    assert said.purchases == 4


def test_the_named_cycle_explains_itself_by_the_row_and_not_by_a_phrase():
    assert rhythm(_days(72, 70, 68, 2), days_since=2, said_days=10).phrase() == ""


def test_silence_is_measured_in_the_named_cycles_too():
    said = rhythm(_days(72, 70, 68, 2), days_since=20, said_days=10)

    assert said.silence == 2.0


"""Стеля зберігання (#149): цикл, довший за неї, описує не дім, а нашу видимість."""


def test_bread_bought_once_a_month_stops_being_a_cycle():
    beat = rhythm(_days(128, 96, 64, 32), days_since=32, keeps=Keeps.DAYS)

    assert beat.trust is Trust.ELSEWHERE
    assert beat.cycle_days is None
    assert beat.receipts_days == 32
    assert "не тільки тут" in beat.phrase()


def test_spices_bought_once_a_month_stay_a_cycle():
    beat = rhythm(_days(128, 96, 64, 32), days_since=32, keeps=Keeps.YEARS)

    assert beat.trust is Trust.CYCLE
    assert beat.cycle_days == 32


def test_the_ceiling_is_one_sided_and_never_shortens_a_cycle():
    beat = rhythm(_days(12, 9, 6, 3), days_since=3, keeps=Keeps.DAYS)

    assert beat.trust is Trust.CYCLE
    assert beat.cycle_days == 3


def test_a_cycle_exactly_at_the_ceiling_is_not_vetoed():
    beat = rhythm(_days(28, 21, 14, 7), days_since=7, keeps=Keeps.DAYS)

    assert beat.cycle_days == 7


def test_the_guest_word_beats_the_ceiling_too():
    beat = rhythm(_days(128, 96, 64, 32), days_since=2, said_days=2, keeps=Keeps.DAYS)

    assert beat.trust is Trust.SAID
    assert beat.cycle_days == 2


def test_without_a_ceiling_nothing_changes():
    assert rhythm(_days(128, 96, 64, 32), days_since=32).trust is Trust.CYCLE


def test_the_tiers_that_have_no_ceiling_say_so():
    assert ceiling_days(Keeps.DAYS) == 7
    assert ceiling_days(Keeps.YEARS) is None
    assert ceiling_days(None) is None


def test_an_uneven_row_stays_uneven_and_does_not_borrow_the_ceilings_words():
    beat = rhythm(_days(72, 70, 68, 2), days_since=2, keeps=Keeps.DAYS)

    assert beat.trust is Trust.RARE
    assert "нерівно" in beat.phrase()


def test_a_kind_whose_purchases_are_not_its_consumption_loses_the_number():
    days = [date(2026, 8, 1), date(2026, 8, 8), date(2026, 8, 15), date(2026, 8, 22)]

    beat = rhythm(days, days_since=3, rhythm_lies=True)

    assert beat.trust is Trust.NOT_RHYTHM
    assert beat.cycle_days is None
    assert beat.receipts_days == 7


def test_the_word_of_the_guest_outranks_the_verdict_about_the_kind():
    days = [date(2026, 7, 25), date(2026, 8, 1), date(2026, 8, 8), date(2026, 8, 15)]

    beat = rhythm(days, days_since=1, said_days=2, rhythm_lies=True)

    assert beat.trust is Trust.SAID
    assert beat.cycle_days == 2


def test_a_kind_that_does_not_lie_keeps_its_cycle():
    days = [date(2026, 7, 25), date(2026, 8, 1), date(2026, 8, 8), date(2026, 8, 15)]

    beat = rhythm(days, days_since=1, rhythm_lies=False)

    assert beat.trust is Trust.CYCLE


def test_the_phrase_of_a_lying_rhythm_names_our_receipts_and_not_his_home():
    days = [date(2026, 7, 25), date(2026, 8, 1), date(2026, 8, 8), date(2026, 8, 15)]

    said = rhythm(days, days_since=3, rhythm_lies=True).phrase()

    assert "раз на 7 дн" in said
    assert "не дорівнює витрачанню" in said


"""СТЕЛЯ ЗБЕРІГАННЯ РАХУЄТЬСЯ І ТАМ, ДЕ ГІЛКА `ELSEWHERE` НЕДОСЯЖНА (07.09).

Вирок агента стоїть у `rhythm` попереду стелі, тож рядок, у якого правдиві
ОБИДВІ причини, до `ELSEWHERE` не доходить за побудовою. Читає цей факт не
лише та гілка, яка на ньому спиняється: різ питання в коморі питає рівно
його, і порахований усередині однієї гілки він був би невидимий другій.
"""


def test_a_lying_rhythm_still_counts_the_shelf_life_ceiling():
    beat = rhythm(_days(128, 96, 64, 32), days_since=32, keeps=Keeps.DAYS, rhythm_lies=True)

    assert beat.trust is Trust.NOT_RHYTHM
    assert beat.beyond_keeps is True


def test_a_lying_rhythm_within_the_shelf_life_is_not_beyond_it():
    days = [date(2026, 7, 25), date(2026, 8, 1), date(2026, 8, 8), date(2026, 8, 15)]

    beat = rhythm(days, days_since=3, keeps=Keeps.WEEKS, rhythm_lies=True)

    assert beat.trust is Trust.NOT_RHYTHM
    assert beat.beyond_keeps is False


def test_a_proven_cycle_is_never_beyond_its_own_ceiling():
    beat = rhythm(_days(120, 90, 60, 30), days_since=5, keeps=Keeps.YEARS)

    assert beat.trust is Trust.CYCLE
    assert beat.beyond_keeps is False


def test_the_phrase_of_a_lying_rhythm_beyond_the_ceiling_names_the_other_shop():
    beat = rhythm(_days(128, 96, 64, 32), days_since=32, keeps=Keeps.DAYS, rhythm_lies=True)
    said = beat.phrase()

    assert "не тільки тут" in said
    assert "не дорівнює витрачанню" not in said
