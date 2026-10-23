from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from komora.core.promo import Habit
from komora.core.traits import (
    Bought,
    Brand,
    Proof,
    Rate,
    Traits,
    brand,
    brand_matters,
    brand_words,
    consumption,
    per_trip,
    promo_only,
    rate,
    sees_a_fraction,
    traits,
)

DAY = date(2026, 9, 4)


def _bought(name: str, qty: str = "1") -> Bought:
    return Bought(name=name, qty=Decimal(qty), at=DAY)


def test_the_head_of_the_name_is_the_kind_and_never_the_brand():
    assert "tmt" not in brand_words("Томат Гордій Черрі 250г")


def test_packaging_words_are_not_brands():
    assert brand_words("Печиво уп 300г") == ()


def test_the_same_brand_in_two_alphabets_is_one_word():
    assert brand_words("Йогурт Lekker") == brand_words("Йогурт Леккер")


def test_a_word_repeated_in_one_name_counts_once():
    assert brand_words("Йогурт Lekker Леккер") == ("lkr",)


def test_a_name_without_a_brand_word_gives_no_brand():
    assert brand([_bought("Хліб"), _bought("Хліб"), _bought("Хліб")]) is None


def test_the_brand_is_the_one_bought_most_and_it_says_how_often():
    top = brand([_bought("Томат Гордій"), _bought("Томат Гордій"), _bought("Томат Ласуня")])

    assert top is not None
    assert top.purchases == 2
    assert top.out_of == 3


def test_the_brand_keeps_the_spelling_from_the_receipt():
    top = brand([_bought("Томат Гордій"), _bought("Томат Гордій"), _bought("Томат Гордій")])

    assert top is not None
    assert "Гордій" in top.word


def test_a_share_of_nothing_is_zero_not_a_crash():
    assert Brand(word="Гордій", purchases=0, out_of=0).share == 0


def test_two_purchases_are_a_coincidence_not_a_brand():
    assert brand_matters([_bought("Томат Гордій"), _bought("Томат Гордій")]) is Proof.UNKNOWN


def test_a_kind_whose_names_carry_no_brand_stays_unknown():
    assert brand_matters([_bought("Хліб")] * 3) is Proof.UNKNOWN


def test_two_thirds_of_one_brand_is_a_rule():
    bought = [_bought("Томат Гордій"), _bought("Томат Гордій"), _bought("Томат Ласуня")]

    assert brand_matters(bought) is Proof.YES


def test_a_brand_below_two_thirds_is_the_receipts_saying_no():
    bought = [
        _bought("Томат Гордій"),
        _bought("Томат Ласуня"),
        _bought("Томат Angello"),
        _bought("Томат Чері"),
    ]

    assert brand_matters(bought) is Proof.NO


def test_a_weighed_kind_says_unknown_and_not_no():
    assert promo_only(Habit(purchases=9, discounted=9, weighed=True)) is Proof.UNKNOWN


def test_too_few_purchases_leave_the_promo_axis_silent():
    assert promo_only(Habit(purchases=2, discounted=2)) is Proof.UNKNOWN


def test_mostly_on_sale_is_a_proven_habit():
    assert promo_only(Habit(purchases=3, discounted=3)) is Proof.YES


def test_buying_it_at_full_price_is_the_receipts_answering():
    assert promo_only(Habit(purchases=5, discounted=1)) is Proof.NO


def test_a_kind_never_bought_has_no_quantity_per_trip():
    assert per_trip([]) is None


def test_a_row_with_zero_quantity_does_not_count_as_a_trip():
    assert per_trip([_bought("Вода", "0")]) is None


def test_one_big_stock_up_does_not_move_the_usual_trip():
    bought = [_bought("Вода", "1"), _bought("Вода", "1"), _bought("Вода", "30")]

    assert per_trip(bought) == Decimal(1)


@pytest.mark.parametrize("gap", [None, 0, -3])
def test_without_a_proven_gap_there_is_no_rate(gap: int | None):
    assert rate([_bought("Вода", "6")], gap_days=gap) is None


def test_without_purchases_there_is_no_rate():
    assert rate([], gap_days=7) is None


def test_the_rate_is_what_one_trip_brings_divided_by_the_gap():
    speed = rate([_bought("Вода", "6")], gap_days=3)

    assert speed is not None
    assert speed.per_day == Decimal(2)


def test_a_rate_without_days_is_zero_not_a_crash():
    assert Rate(per_trip=Decimal(6), gap_days=0).per_day == 0


def test_a_kind_with_too_few_purchases_says_nothing_about_consumption():
    bought = [_bought("Вода", "6"), _bought("Вода", "6")]

    assert consumption(bought, gap_days=3, keeps_days=365) is Proof.UNKNOWN


def test_without_a_gap_consumption_is_the_guests_to_tell():
    assert consumption([_bought("Вода", "6")] * 3, gap_days=None, keeps_days=365) is Proof.UNKNOWN


def test_a_gap_longer_than_the_kind_can_lie_is_about_our_blindness():
    bought = [_bought("Паляничка", "1")] * 4

    assert consumption(bought, gap_days=32, keeps_days=3) is Proof.NO


def test_a_gap_inside_the_shelf_life_is_a_proven_consumption():
    bought = [_bought("Вода", "6")] * 3

    assert consumption(bought, gap_days=3, keeps_days=180) is Proof.YES


def test_a_kind_without_a_known_shelf_life_is_not_accused():
    bought = [_bought("Вода", "6")] * 3

    assert consumption(bought, gap_days=3, keeps_days=None) is Proof.YES


def test_silence_is_named_in_a_fixed_order():
    quiet = Traits(promo=Proof.UNKNOWN, consumption=Proof.YES, brand=Proof.UNKNOWN)

    assert quiet.silent() == ("акція", "марка")


def test_a_kind_the_receipts_answered_asks_nothing():
    answered = Traits(promo=Proof.NO, consumption=Proof.YES, brand=Proof.NO)

    assert answered.silent() == ()


def test_the_note_carries_numbers_and_not_the_list():
    mixed = Traits(promo=Proof.YES, consumption=Proof.NO, brand=Proof.UNKNOWN)

    assert mixed.note() == "доведено 1, чеки заперечують 1, мовчать 1"


def test_all_three_axes_come_from_one_call():
    bought = [_bought("Томат Гордій", "1")] * 3

    got = traits(
        bought,
        habit=Habit(purchases=3, discounted=3),
        gap_days=7,
        keeps_days=14,
    )

    assert got == Traits(promo=Proof.YES, consumption=Proof.YES, brand=Proof.YES)


def test_without_a_norm_nothing_is_claimed():
    assert sees_a_fraction(None, bought_per_day=Decimal("0.05")) is False


def test_without_purchases_nothing_is_claimed_either():
    assert sees_a_fraction(Decimal(1), bought_per_day=None) is False
    assert sees_a_fraction(Decimal(1), bought_per_day=Decimal(0)) is False


def test_one_bottle_in_twenty_days_against_a_bottle_a_day_is_a_fraction():
    assert sees_a_fraction(Decimal(1), bought_per_day=Decimal("0.05")) is True


def test_buying_more_than_the_norm_is_never_held_against_the_row():
    assert sees_a_fraction(Decimal(1), bought_per_day=Decimal(3)) is False


def test_a_family_sized_gap_is_not_enough_to_veto():
    assert sees_a_fraction(Decimal(1), bought_per_day=Decimal("0.25")) is False
