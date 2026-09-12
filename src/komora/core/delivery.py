from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class CostTier:

    cost: Decimal
    from_order_cost: Decimal


@dataclass(frozen=True, slots=True)
class DeliveryTerms:
    base_cost: Decimal
    tiers: tuple[CostTier, ...]
    min_order_cost: Decimal
    max_weight_kg: Decimal


@dataclass(frozen=True, slots=True)
class Candidate:

    external_product_id: str
    name: str
    price: Decimal


@dataclass(frozen=True, slots=True)
class TopUp:

    items: tuple[Candidate, ...]
    threshold: Decimal
    spend: Decimal
    saving: Decimal
    net: Decimal
    cost_before: Decimal
    cost_after: Decimal


def delivery_cost(terms: DeliveryTerms, order_total: Decimal) -> Decimal:
    cost = terms.base_cost
    for tier in sorted(terms.tiers, key=lambda t: t.from_order_cost):
        if order_total >= tier.from_order_cost:
            cost = tier.cost
    return cost


def meets_minimum(terms: DeliveryTerms, order_total: Decimal) -> bool:
    return order_total >= terms.min_order_cost


def shortfall_to_minimum(terms: DeliveryTerms, order_total: Decimal) -> Decimal:
    gap = terms.min_order_cost - order_total
    return gap if gap > 0 else Decimal(0)


def _cheapest_cover(
    pool: Sequence[Candidate],
    needed: Decimal,
) -> tuple[tuple[Candidate, ...], Decimal] | None:
    options: list[tuple[Decimal, tuple[Candidate, ...]]] = []

    accumulated: list[Candidate] = []
    running = Decimal(0)
    for candidate in pool:
        accumulated.append(candidate)
        running += candidate.price
        if running >= needed:
            options.append((running, tuple(accumulated)))
            break

    for candidate in pool:
        if candidate.price >= needed:
            options.append((candidate.price, (candidate,)))
            break

    if not options:
        return None

    spend, picked = min(options, key=lambda option: (option[0], len(option[1])))
    return picked, spend


def topup_advice(
    terms: DeliveryTerms,
    order_total: Decimal,
    candidates: Iterable[Candidate],
) -> TopUp | None:
    pool = sorted(candidates, key=lambda c: (c.price, c.external_product_id))
    if not pool:
        return None

    cost_before = delivery_cost(terms, order_total)
    best: TopUp | None = None

    for tier in sorted(terms.tiers, key=lambda t: t.from_order_cost):
        if tier.from_order_cost <= order_total:
            continue

        needed = tier.from_order_cost - order_total
        chosen = _cheapest_cover(pool, needed)
        if chosen is None:
            continue

        picked, spend = chosen
        cost_after = delivery_cost(terms, order_total + spend)
        saving = cost_before - cost_after
        net = saving - spend
        if net <= 0:
            continue

        if best is None or net > best.net:
            best = TopUp(
                items=tuple(picked),
                threshold=tier.from_order_cost,
                spend=spend,
                saving=saving,
                net=net,
                cost_before=cost_before,
                cost_after=cost_after,
            )

    return best


@dataclass(frozen=True, slots=True)
class SpecialPrice:

    price: Decimal
    count: int


def multipack_advice(
    unit_price: Decimal,
    special_prices: Sequence[SpecialPrice],
    weekly_qty: Decimal,
    horizon_weeks: int,
) -> SpecialPrice | None:
    if horizon_weeks <= 0:
        return None

    affordable = weekly_qty * horizon_weeks
    best: SpecialPrice | None = None
    for level in sorted(special_prices, key=lambda s: s.count):
        if level.count > affordable:
            continue
        if level.price >= unit_price:
            continue
        if best is None or level.price < best.price:
            best = level
    return best
