from __future__ import annotations

from collections.abc import Callable, Sequence


def shortlist[T](
    candidates: Sequence[T],
    *,
    own: Callable[[T], bool],
    bought: Callable[[T], bool] | None = None,
    same_kind: Callable[[T], bool] | None = None,
    related: Callable[[T], bool],
    cap: int,
) -> list[T]:

    def tier(item: T) -> int:
        if own(item):
            return 0
        if bought is not None and bought(item):
            return 1
        if same_kind is not None and same_kind(item):
            return 2
        return 3 if related(item) else 4

    ordered = sorted(
        range(len(candidates)),
        key=lambda index: (tier(candidates[index]), index),
    )
    kept = ordered if cap < 1 else ordered[:cap]
    return [candidates[index] for index in kept]


def cheapest[T](candidates: Sequence[T], *, unit_price: Callable[[T], float | None]) -> T | None:
    prices = [unit_price(candidate) for candidate in candidates]
    if not prices or any(price is None or price <= 0 for price in prices):
        return None
    best = min(range(len(prices)), key=lambda index: (prices[index], index))
    return candidates[best]


__all__ = ["cheapest", "shortlist"]
