from __future__ import annotations

from collections.abc import Callable, Sequence
from decimal import Decimal

NOISE = Decimal("0.1")


def better[T](
    chosen: T,
    alternatives: Sequence[T],
    *,
    unit_price: Callable[[T], float | None],
    price: Callable[[T], Decimal | None],
    floor: Decimal = NOISE,
) -> T | None:
    mine_unit = unit_price(chosen)
    mine_price = price(chosen)
    if mine_unit is None or mine_unit <= 0 or mine_price is None or mine_price <= 0:
        return None
    edge = float(mine_unit) * float(1 - floor)
    best: T | None = None
    best_unit = mine_unit
    for other in alternatives:
        unit = unit_price(other)
        cost = price(other)
        if unit is None or unit <= 0 or cost is None or cost <= 0:
            continue
        if unit < edge and unit < best_unit and cost <= mine_price:
            best, best_unit = other, unit
    return best


__all__ = ["NOISE", "better"]
