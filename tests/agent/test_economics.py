from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from komora.agent.basket import PlanLine
from komora.agent.economics import ORDER_MIN, Economics, settle, topup_for
from komora.core.delivery import CostTier, DeliveryTerms

TERMS = DeliveryTerms(
    base_cost=Decimal(89),
    tiers=(
        CostTier(cost=Decimal(59), from_order_cost=Decimal(1199)),
        CostTier(cost=Decimal(1), from_order_cost=Decimal(1699)),
    ),
    min_order_cost=Decimal(599),
    max_weight_kg=Decimal(50),
)


def line(price: str, qty: str = "1", *, old: str | None = None, at_home: bool = False) -> PlanLine:
    product: dict[str, Any] = {"price": price, "externalProductId": 1, "name": "товар"}
    if old is not None:
        product["oldPrice"] = old
    return PlanLine(
        intent="намір",
        product=product,
        qty=Decimal(qty),
        reason="тест",
        from_history=None,
        at_home=at_home,
    )


def test_total_is_price_times_qty_across_lines():
    money = settle([line("53.49", "2"), line("245.0")], TERMS)
    assert money.total == Decimal("351.98")


def test_qty_may_be_fractional_and_survives_it():
    assert settle([line("400", "0.5")], TERMS).total == Decimal("200.0")


def test_line_left_at_home_costs_nothing():
    money = settle([line("100"), line("999", at_home=True)], TERMS)
    assert money.total == Decimal(100)


def test_empty_basket_is_zero_not_a_crash():
    assert settle([], TERMS).total == Decimal(0)


def test_an_empty_basket_still_counts_in_money_not_in_ints():
    money = settle([], TERMS)
    assert isinstance(money.total, Decimal)
    assert isinstance(money.base_total, Decimal)


def test_base_total_takes_the_price_before_the_promo():
    money = settle([line("53.49", "2", old="69.99")], TERMS)
    assert money.base_total == Decimal("139.98")
    assert money.discounted == Decimal("139.98")


def test_without_a_promo_there_is_nothing_to_strike_through():
    money = settle([line("53.49", "2")], TERMS)
    assert money.base_total == money.total
    assert money.discounted is None


def test_a_line_with_a_null_old_price_falls_back_to_the_price():
    money = settle([PlanLine(
        intent="намір",
        product={"price": "50", "oldPrice": None},
        qty=Decimal(2),
        reason="тест",
        from_history=None,
    )], TERMS)
    assert money.base_total == Decimal(100)


def test_delivery_falls_to_the_tier_the_sum_reaches():
    assert settle([line("1200")], TERMS).cost == Decimal(59)
    assert settle([line("1700")], TERMS).cost == Decimal(1)


def test_the_cart_price_beats_our_tiers():
    money = settle([line("300")], TERMS, actual_delivery_cost=Decimal(1))
    assert money.cost == Decimal(1)
    assert money.by_tiers == Decimal(89), "пороги лишаються видимими поруч"
    assert money.subscription_applies


def test_without_a_cart_the_tiers_are_the_answer():
    money = settle([line("300")], TERMS)
    assert money.cost == money.by_tiers == Decimal(89)
    assert not money.subscription_applies


def test_below_the_minimum_the_cart_says_so():
    assert ORDER_MIN in settle([line("300")], TERMS).blockers


def test_above_the_minimum_there_is_no_blocker():
    assert settle([line("600")], TERMS).blockers == []


def test_exactly_the_minimum_passes():
    assert settle([line("599")], TERMS).blockers == []


def test_the_api_blocker_is_not_duplicated_by_ours():
    money = settle([line("300")], TERMS, blockers=[ORDER_MIN])
    assert money.blockers == [ORDER_MIN]


def test_other_api_blockers_survive():
    money = settle([line("300")], TERMS, blockers=["product.offer.stock.max"])
    assert money.blockers == ["product.offer.stock.max", ORDER_MIN]


def test_the_incoming_blockers_are_not_mutated():
    incoming = ["product.offer.stock.max"]
    settle([line("300")], TERMS, blockers=incoming)
    assert incoming == ["product.offer.stock.max"]


def test_top_up_points_at_the_next_tier_not_the_first():
    money = settle([line("1300")], TERMS)
    assert money.top_up is not None
    assert money.top_up.threshold == Decimal(1699), "1199 уже пройдено"
    assert money.top_up.saving == Decimal(88), "89 базових мінус 1 на порозі"


def test_top_up_is_silent_when_delivery_is_already_the_cheapest():
    money = settle([line("300")], TERMS, actual_delivery_cost=Decimal(1))
    assert money.top_up is None


def test_top_up_is_silent_at_the_top_tier():
    assert settle([line("1700")], TERMS).top_up is None


def test_top_up_alone_returns_nothing_above_the_last_tier():
    assert topup_for(TERMS, Decimal(2000)) is None


def test_standing_exactly_on_a_tier_points_at_the_next_one():
    top_up = topup_for(TERMS, Decimal(1199))
    assert top_up is not None and top_up.threshold == Decimal(1699)


def test_a_slot_without_tiers_does_not_break_the_advice():
    flat = DeliveryTerms(
        base_cost=Decimal(89),
        tiers=(),
        min_order_cost=Decimal(599),
        max_weight_kg=Decimal(50),
    )
    money = settle([line("700")], flat)
    assert money.cost == Decimal(89)
    assert money.top_up is None


def test_top_up_carries_no_candidates_yet():
    top_up = topup_for(TERMS, Decimal(300))
    assert top_up is not None and top_up.items == []


def test_top_up_ignores_the_order_of_tiers_in_the_response():
    shuffled = DeliveryTerms(
        base_cost=TERMS.base_cost,
        tiers=tuple(reversed(TERMS.tiers)),
        min_order_cost=TERMS.min_order_cost,
        max_weight_kg=TERMS.max_weight_kg,
    )
    top_up = topup_for(shuffled, Decimal(300))
    assert top_up is not None and top_up.threshold == Decimal(1199)


def test_economics_is_frozen():
    money: Economics = settle([line("300")], TERMS)
    with pytest.raises(AttributeError):
        money.total = Decimal(0)  # type: ignore[misc]
