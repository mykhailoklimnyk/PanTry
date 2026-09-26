from decimal import Decimal

import pytest

from komora.core.delivery import (
    Candidate,
    CostTier,
    DeliveryTerms,
    SpecialPrice,
    delivery_cost,
    meets_minimum,
    multipack_advice,
    shortfall_to_minimum,
    topup_advice,
)

HOME = DeliveryTerms(
    base_cost=Decimal("89"),
    tiers=(
        CostTier(cost=Decimal("59"), from_order_cost=Decimal("1199")),
        CostTier(cost=Decimal("1"), from_order_cost=Decimal("1699")),
    ),
    min_order_cost=Decimal("599"),
    max_weight_kg=Decimal("50"),
)

LONG = DeliveryTerms(
    base_cost=Decimal("139"),
    tiers=(
        CostTier(cost=Decimal("89"), from_order_cost=Decimal("1399")),
        CostTier(cost=Decimal("1"), from_order_cost=Decimal("1999")),
    ),
    min_order_cost=Decimal("799"),
    max_weight_kg=Decimal("50"),
)


@pytest.mark.parametrize(
    ("total", "expected"),
    [
        ("0", "89"),
        ("1198.99", "89"),
        ("1199", "59"),
        ("1698.99", "59"),
        ("1699", "1"),
        ("5000", "1"),
    ],
)
def test_delivery_cost_steps_at_thresholds(total, expected):
    assert delivery_cost(HOME, Decimal(total)) == Decimal(expected)


def test_delivery_cost_uses_terms_not_hardcoded_numbers():
    assert delivery_cost(LONG, Decimal("1399")) == Decimal("89")
    assert delivery_cost(LONG, Decimal("1199")) == Decimal("139")


def test_tier_order_does_not_matter():
    shuffled = DeliveryTerms(
        base_cost=HOME.base_cost,
        tiers=tuple(reversed(HOME.tiers)),
        min_order_cost=HOME.min_order_cost,
        max_weight_kg=HOME.max_weight_kg,
    )
    assert delivery_cost(shuffled, Decimal("1699")) == Decimal("1")


@pytest.mark.parametrize(
    ("total", "ok"),
    [("598.99", False), ("599", True), ("600", True)],
)
def test_minimum_order(total, ok):
    assert meets_minimum(HOME, Decimal(total)) is ok


def test_shortfall_is_zero_when_minimum_reached():
    assert shortfall_to_minimum(HOME, Decimal("700")) == Decimal(0)
    assert shortfall_to_minimum(HOME, Decimal("500")) == Decimal("99")


def test_topup_reproduces_the_case_from_the_mcp_log():
    advice = topup_advice(
        HOME,
        Decimal("1660"),
        [
            Candidate("11111", "Хліб", Decimal("25")),
            Candidate("22222", "Молоко Селянське", Decimal("39")),
        ],
    )

    assert advice is not None
    assert advice.spend == Decimal("39")
    assert advice.saving == Decimal("58")
    assert advice.net == Decimal("19")
    assert advice.cost_before == Decimal("59")
    assert advice.cost_after == Decimal("1")
    assert [item.name for item in advice.items] == ["Молоко Селянське"]


def test_topup_prefers_one_item_over_cheap_pile():
    advice = topup_advice(
        HOME,
        Decimal("1690"),
        [
            Candidate("1", "Жуйка", Decimal("8")),
            Candidate("2", "Вода", Decimal("9")),
            Candidate("3", "Кефір", Decimal("32")),
        ],
    )
    assert advice is not None
    assert advice.spend == Decimal("9")
    assert [item.name for item in advice.items] == ["Вода"]


def test_no_topup_when_it_costs_more_than_it_saves():
    advice = topup_advice(
        HOME,
        Decimal("1000"),
        [Candidate("1", "Ікра", Decimal("900"))],
    )
    assert advice is None


def test_no_topup_without_candidates():
    assert topup_advice(HOME, Decimal("1660"), []) is None


def test_no_topup_above_the_last_threshold():
    assert topup_advice(HOME, Decimal("2000"), [Candidate("1", "Х", Decimal("10"))]) is None


def test_topup_needs_candidates_that_actually_reach_the_threshold():
    advice = topup_advice(HOME, Decimal("1000"), [Candidate("1", "Хліб", Decimal("25"))])
    assert advice is None


def test_multipack_taken_when_the_cycle_covers_it():
    level = multipack_advice(
        unit_price=Decimal("67.99"),
        special_prices=[SpecialPrice(price=Decimal("56.90"), count=2)],
        weekly_qty=Decimal("1"),
        horizon_weeks=2,
    )
    assert level is not None
    assert level.price == Decimal("56.90")


def test_multipack_refused_when_it_will_not_be_consumed():
    level = multipack_advice(
        unit_price=Decimal("67.99"),
        special_prices=[SpecialPrice(price=Decimal("56.90"), count=6)],
        weekly_qty=Decimal("1"),
        horizon_weeks=2,
    )
    assert level is None


def test_multipack_ignores_levels_that_are_not_cheaper():
    level = multipack_advice(
        unit_price=Decimal("50"),
        special_prices=[SpecialPrice(price=Decimal("50"), count=2)],
        weekly_qty=Decimal("5"),
        horizon_weeks=2,
    )
    assert level is None


def test_multipack_needs_a_positive_horizon():
    assert (
        multipack_advice(
            unit_price=Decimal("10"),
            special_prices=[SpecialPrice(price=Decimal("5"), count=2)],
            weekly_qty=Decimal("5"),
            horizon_weeks=0,
        )
        is None
    )


def test_topup_accumulates_when_no_single_item_covers_the_gap():
    advice = topup_advice(
        HOME,
        Decimal("1660"),
        [
            Candidate("11111", "Жуйка", Decimal("14")),
            Candidate("22222", "Хліб", Decimal("15")),
            Candidate("33333", "Кефір", Decimal("18")),
        ],
    )

    assert advice is not None
    assert len(advice.items) == 3
    assert advice.spend == Decimal("47")
    assert advice.net == Decimal("11")


def test_topup_takes_the_set_that_lands_exactly_on_the_threshold():
    advice = topup_advice(
        HOME,
        Decimal("1660"),
        [
            Candidate("11111", "Хліб", Decimal("19")),
            Candidate("22222", "Кефір", Decimal("20")),
        ],
    )

    assert advice is not None
    assert advice.spend == Decimal("39")
    assert len(advice.items) == 2
