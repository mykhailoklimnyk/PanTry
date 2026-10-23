from __future__ import annotations

from decimal import Decimal

import pytest

from komora.core.promo import (
    BELOW_CATALOG,
    BELOW_OWN_MAX,
    CATALOG,
    MIN_DISCOUNTED,
    MIN_PURCHASES,
    OWN_MAX,
    SHELF,
    Habit,
    Purchase,
    habit,
    is_discounted,
    on_sale,
    proof,
    purchase_of,
    regular_of,
    sale_phrase,
)


def _p(paid: str, qty: int = 1, seen: str | None = None) -> Purchase:
    return Purchase(
        paid=Decimal(paid), qty=Decimal(qty), seen=None if seen is None else Decimal(seen)
    )


def test_below_the_catalogue_by_the_threshold_is_a_discount():
    assert is_discounted(_p("46.99", seen="61.99"), regular=Decimal("46.99"))


def test_a_price_rise_of_a_few_percent_is_not_a_discount():
    assert not is_discounted(_p("45.99", seen="49.34"), regular=Decimal("45.99"))


def test_exactly_the_threshold_is_not_yet_a_discount():
    seen = Decimal(100)
    edge = seen * (1 - BELOW_CATALOG)
    assert not is_discounted(Purchase(paid=edge, seen=seen), regular=edge)
    assert is_discounted(Purchase(paid=edge - Decimal("0.01"), seen=seen), regular=edge)


def test_below_the_own_maximum_counts_without_a_catalogue_price():
    assert is_discounted(_p("29.99"), regular=Decimal("46.49"))
    assert not is_discounted(_p("44.99"), regular=Decimal("46.49"))


def test_the_own_maximum_threshold_is_its_own_number():
    regular = Decimal(100)
    edge = regular * (1 - BELOW_OWN_MAX)
    assert not is_discounted(Purchase(paid=edge), regular=regular)
    assert is_discounted(Purchase(paid=edge - Decimal("0.01")), regular=regular)


def test_a_free_or_broken_price_is_never_a_discount():
    assert not is_discounted(_p("0", seen="50"), regular=Decimal(50))
    assert not is_discounted(_p("-1", seen="50"), regular=Decimal(50))
    assert not is_discounted(_p("10", seen="0"), regular=Decimal(0))


def test_mostly_on_sale_needs_two_thirds_and_at_least_three_purchases():
    beer = habit(
        [
            _p("29.99", 6, "50.99"),
            _p("31.99", 12, "50.99"),
            _p("29.99", 6, "50.99"),
            _p("31.99", 6, "50.99"),
            _p("46.49", 2, "50.99"),
        ]
    )
    assert beer.mostly
    assert (beer.purchases, beer.discounted) == (5, 4)

    once = habit([_p("46.99", 1, "61.99"), _p("61.6", 1, "61.99"), _p("61.6", 1, "61.99")])
    assert not once.mostly
    assert (once.purchases, once.discounted) == (3, 1)


def test_two_of_two_is_a_coincidence_not_a_habit():
    assert MIN_PURCHASES == 3
    two = habit([_p("30", 1, "60"), _p("30", 1, "60")])
    assert (two.purchases, two.discounted) == (2, 2)
    assert not two.mostly


def test_the_two_thirds_edge_is_inclusive():
    assert habit([_p("30", 1, "60"), _p("30", 1, "60"), _p("60", 1, "60")]).mostly
    assert not habit([_p("30", 1, "60")] * 3 + [_p("60", 1, "60")] * 2).mostly


def test_one_discounted_purchase_among_many_is_not_enough():
    assert MIN_DISCOUNTED == 2
    assert not habit([_p("30", 1, "60"), _p("60", 1, "60"), _p("60", 1, "60")]).mostly


def test_the_usual_quantity_is_the_median_of_discounted_purchases_only():
    water = habit(
        [_p("15", 5, "20"), _p("15", 6, "20"), _p("15", 5, "20"), _p("20", 1, "20")],
    )
    assert water.usual_qty == Decimal(5)


def test_the_usual_quantity_rounds_to_whole_pieces():
    lemonade = habit([_p("40", 1, "60"), _p("40", 2, "60"), _p("60", 1, "60")])
    assert lemonade.usual_qty == Decimal(2)


def test_without_discounted_purchases_there_is_no_usual_quantity():
    plain = habit([_p("60", 3, "60"), _p("60", 3, "60"), _p("60", 3, "60")])
    assert plain.usual_qty is None
    assert not plain.mostly


def test_a_weighed_kind_is_blind_on_purpose():
    cucumbers = habit([_p("30", 1, "60")] * 4, weighed=True)
    assert cucumbers.weighed
    assert cucumbers.discounted == 4
    assert not cucumbers.mostly
    assert cucumbers.phrase() == ""


def test_broken_prices_are_left_out_of_the_count():
    seen = habit([_p("0", 1, "60"), _p("30", 1, "60"), _p("30", 1, "60"), _p("60", 1, "60")])
    assert seen.purchases == 3


def test_an_empty_history_gives_an_empty_habit():
    assert habit([]) == Habit()
    assert not Habit().mostly


def test_the_regular_price_is_the_dearest_purchase_of_this_article():
    whiskas = habit([_p("30", 20), _p("30", 20), _p("50", 4)])
    assert whiskas.discounted == 2
    assert whiskas.mostly
    assert whiskas.usual_qty == Decimal(20)


def test_the_phrase_names_the_share_and_the_quantity():
    beer = habit([_p("29.99", 6, "50.99")] * 4 + [_p("46.49", 2, "50.99")])
    assert beer.phrase() == "береш по акції: 4 з 5, зазвичай по 6"


def test_the_phrase_drops_the_quantity_when_it_is_one():
    lemonade = habit([_p("46.99", 1, "61.99")] * 2 + [_p("61.6", 1, "61.99")])
    assert lemonade.phrase() == "береш по акції: 2 з 3"


def test_a_kind_without_the_habit_says_nothing_about_sales():
    assert habit([_p("60", 1, "60")] * 3).phrase() == ""


@pytest.mark.parametrize(
    ("product", "expected"),
    [
        ({"price": 46.99, "oldPrice": 61.99}, True),
        ({"price": "46.99", "oldPrice": "61.99"}, True),
        ({"price": 61.99, "oldPrice": None}, False),
        ({"price": 61.99}, False),
        ({"price": 61.99, "oldPrice": 61.99}, False),
        ({"price": 70, "oldPrice": 61.99}, False),
        ({"price": 46.99, "oldPrice": "стара"}, False),
        ({"oldPrice": 61.99}, False),
        ({"price": 46.99, "oldPrice": ""}, False),
    ],
)
def test_on_sale_means_an_old_price_above_the_current_one(product, expected):
    assert on_sale(product) is expected


def test_the_sale_phrase_quotes_both_numbers_from_the_same_card():
    assert sale_phrase({"price": 46.99, "oldPrice": 61.99}) == "було 61.99, стало 46.99"
    assert sale_phrase({"price": 61.99}) == ""


def test_a_one_hryvnia_purchase_is_a_purchase_not_a_broken_row():
    assert is_discounted(_p("1", seen="10"), regular=Decimal(1))
    assert is_discounted(_p("0.5"), regular=Decimal(1))
    assert is_discounted(Purchase(paid=Decimal("0.5"), seen=Decimal(1)), regular=Decimal("0.5"))
    cheap = habit([_p("1", 2, "10")] * 3)
    assert cheap.purchases == 3 and cheap.mostly


def test_custom_thresholds_reach_both_axes():
    strict = habit([_p("70", 1, "100")] * 3, below_catalog=Decimal("0.5"), below_own=Decimal("0.5"))
    assert strict.discounted == 0
    lax_catalog = habit(
        [_p("70", 1, "100")] * 3, below_catalog=Decimal("0.2"), below_own=Decimal("0.9")
    )
    assert lax_catalog.discounted == 3
    tight_own = habit(
        [_p("70"), _p("70"), _p("100")], below_catalog=Decimal("0.5"), below_own=Decimal("0.5")
    )
    assert tight_own.discounted == 0
    lax_own = habit(
        [_p("70"), _p("70"), _p("100")], below_catalog=Decimal("0.9"), below_own=Decimal("0.2")
    )
    assert lax_own.discounted == 2


def test_the_usual_quantity_ignores_broken_zero_quantities_and_keeps_one():
    zero = habit([_p("30", 0, "60"), _p("30", 6, "60"), _p("60", 1, "60")])
    assert zero.usual_qty == Decimal(6)
    ones = habit([_p("30", 1, "60")] * 3)
    assert ones.usual_qty == Decimal(1)


def test_the_shelf_proves_a_habit_the_receipt_alone_cannot():
    online = [_p("12.99", 20), _p("11.99", 24), _p("12.99", 12)]
    blind = habit(online)
    assert blind.discounted == 0 and not blind.mostly

    seen_on_shelf = habit(online, shelf=Decimal("21.59"))
    assert seen_on_shelf.discounted == 3
    assert seen_on_shelf.mostly
    assert seen_on_shelf.usual_qty == Decimal(20)


def test_the_shelf_stays_silent_where_the_receipt_carries_the_catalogue_price():
    bread = [_p("45.99", 1, "49.34")] * 3
    assert habit(bread, shelf=Decimal(60)).discounted == 0
    assert proof(_p("45.99", seen="49.34"), regular=Decimal("45.99"), shelf=Decimal(60)) is None


def test_a_zero_catalogue_price_is_a_missing_number_not_a_fact_about_the_price():
    assert proof(_p("12.99", seen="0"), regular=Decimal("12.99"), shelf=Decimal("21.59")) == SHELF


def test_the_shelf_uses_the_catalogue_threshold_and_its_edge_is_strict():
    shelf = Decimal(100)
    edge = shelf * (1 - BELOW_CATALOG)
    assert proof(Purchase(paid=edge), regular=edge, shelf=shelf) is None
    assert proof(Purchase(paid=edge - Decimal("0.01")), regular=edge, shelf=shelf) == SHELF


def test_a_broken_shelf_price_turns_the_axis_off_instead_of_guessing():
    assert proof(_p("12.99"), regular=Decimal("12.99"), shelf=None) is None
    assert proof(_p("12.99"), regular=Decimal("12.99"), shelf=Decimal(0)) is None
    assert proof(_p("12.99"), regular=Decimal("12.99"), shelf=Decimal(-5)) is None


def test_the_proof_names_the_axis_because_a_count_without_it_explains_nothing():
    assert proof(_p("46.99", seen="61.99"), regular=Decimal("46.99")) == CATALOG
    assert proof(_p("12.99"), regular=Decimal("12.99"), shelf=Decimal("21.59")) == SHELF
    assert proof(_p("29.99"), regular=Decimal("46.49")) == OWN_MAX
    assert proof(_p("46.49"), regular=Decimal("46.49")) is None
    assert is_discounted(_p("12.99"), regular=Decimal("12.99"), shelf=Decimal("21.59"))


def test_a_weighed_kind_stays_off_the_axis_even_with_a_shelf_price():
    weighed = habit([_p("29.99", 1)] * 3, weighed=True, shelf=Decimal("59.99"))
    assert weighed.discounted == 3
    assert not weighed.mostly


@pytest.mark.parametrize(
    ("product", "expected"),
    [
        ({"price": 12.99, "oldPrice": 21.59}, Decimal("21.59")),
        ({"price": 21.59, "oldPrice": None}, Decimal("21.59")),
        ({"price": 21.59}, Decimal("21.59")),
        ({"price": 21.59, "oldPrice": 21.59}, Decimal("21.59")),
        ({"price": 21.59, "oldPrice": 10}, Decimal("21.59")),
        ({"price": 21.59, "oldPrice": "стара"}, Decimal("21.59")),
        ({"oldPrice": 21.59}, None),
        ({}, None),
    ],
)
def test_the_regular_shelf_price_is_the_old_one_only_when_a_sale_stands(product, expected):
    assert regular_of(product) == expected


def test_a_live_receipt_row_brings_its_catalogue_price_from_the_card():
    got = purchase_of(
        {"price": 29.99, "catalogProduct": {"price": 50.99}, "priceSeen": 44}, Decimal(6)
    )
    assert got == Purchase(paid=Decimal("29.99"), qty=Decimal(6), seen=Decimal("50.99"))


def test_a_stored_receipt_row_brings_it_from_price_seen():
    got = purchase_of({"price": 29.99, "priceSeen": 50.99}, Decimal(6))
    assert got is not None and got.seen == Decimal("50.99")


def test_an_online_row_carries_only_what_it_paid():
    got = purchase_of({"price": 12.99, "quantity": 20, "subtotal": 259.8}, Decimal(20))
    assert got == Purchase(paid=Decimal("12.99"), qty=Decimal(20), seen=None)


def test_a_row_without_a_price_is_not_a_purchase():
    assert purchase_of({"name": "Хліб"}, Decimal(1)) is None
    assert purchase_of({"price": "не число"}, Decimal(1)) is None


def test_a_broken_catalogue_price_is_dropped_not_the_whole_purchase():
    got = purchase_of({"price": 29.99, "priceSeen": "не число"}, Decimal(1))
    assert got is not None and got.seen is None


def test_the_shelf_judges_a_kind_only_when_no_purchase_carries_a_catalogue_price():
    mixed = [_p("12.99", 20), _p("11.99", 24), _p("12.90", 20, "12.99")]
    assert habit(mixed, shelf=Decimal("21.59")).discounted == 0

    blind = [_p("12.99", 20), _p("11.99", 24), _p("12.90", 20)]
    assert habit(blind, shelf=Decimal("21.59")).discounted == 3


def test_a_zero_catalogue_price_does_not_count_as_a_price_for_that_rule():
    blind = [_p("12.99", 20), _p("11.99", 24), _p("12.90", 20, "0")]
    assert habit(blind, shelf=Decimal("21.59")).discounted == 3
