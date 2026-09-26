from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from itertools import pairwise

DEFAULT_NEEDS = 12

MIN_NEEDS = 6
MAX_NEEDS = 24

QTY_HEADROOM = 2

DEFAULT_MAX_QTY = 24


@dataclass(frozen=True, slots=True)
class Usual:

    receipts: int
    median: int
    p75: int
    limit: int

    @property
    def clamped(self) -> bool:
        return self.receipts > 0 and self.limit != self.p75

    def phrase(self) -> str:
        if not self.receipts:
            return f"чеків ще немає — беру {self.limit} за замовчуванням"
        said = f"медіана {self.median}, p75 {self.p75}, беру {self.limit}"
        if self.clamped:
            edge = "нижня" if self.limit == MIN_NEEDS else "верхня"
            return f"{said} ({edge} межа стелі, не p75)"
        return said


def usual_basket_stats(sizes: Sequence[int], *, default: int = DEFAULT_NEEDS) -> Usual:
    real = sorted(size for size in sizes if size > 0)
    if not real:
        return Usual(receipts=0, median=default, p75=default, limit=default)
    p75 = real[(len(real) * 3) // 4]
    return Usual(
        receipts=len(real),
        median=real[len(real) // 2],
        p75=p75,
        limit=max(MIN_NEEDS, min(MAX_NEEDS, p75)),
    )


def usual_basket(sizes: Sequence[int], *, default: int = DEFAULT_NEEDS) -> int:
    return usual_basket_stats(sizes, default=default).limit


DEFAULT_TRIP_GAP = 3

MAX_TRIP_GAP = 30


def trip_gap(days: Sequence[date]) -> int:
    ordered = sorted(set(days))
    if len(ordered) < 2:
        return DEFAULT_TRIP_GAP
    gaps = [(later - earlier).days for earlier, later in pairwise(ordered)]
    middle = sorted(gaps)[len(gaps) // 2]
    return max(1, min(MAX_TRIP_GAP, int(middle)))


def max_qty(typical: float | None) -> int:
    if typical is None or typical <= 0:
        return DEFAULT_MAX_QTY
    return max(1, min(DEFAULT_MAX_QTY, int(typical) * QTY_HEADROOM))


DEFAULT_ORDER = 1700

ORDER_ROUND = 100

P90_FROM = 10


@dataclass(frozen=True, slots=True)
class Spend:

    orders: int
    median: int
    p75: int
    target: int
    presets: tuple[int, ...]

    @property
    def guessed(self) -> bool:
        return self.orders == 0

    def phrase(self) -> str:
        if self.guessed:
            return f"твоїх замовлень ще не видно — став суму сам, поки беру {self.target} ₴"
        return f"твої замовлення: медіана {self.median}, p75 {self.p75} — беру {self.target} ₴"


def _rounded(value: float) -> int:
    return max(ORDER_ROUND, round(value / ORDER_ROUND) * ORDER_ROUND)


def usual_order(amounts: Sequence[float], *, default: int = DEFAULT_ORDER) -> Spend:
    real = sorted(float(value) for value in amounts if float(value) > 0)
    if not real:
        return Spend(
            orders=0,
            median=default,
            p75=default,
            target=default,
            presets=(default - 500, default, default + 600, default + 1300),
        )

    def at(share: float) -> int:
        return _rounded(real[min(len(real) - 1, int(len(real) * share))])

    median, p75 = at(0.5), at(0.75)
    top = at(0.9) if len(real) >= P90_FROM else p75
    steps = tuple(dict.fromkeys((at(0.25), median, p75, top)))
    return Spend(
        orders=len(real),
        median=median,
        p75=p75,
        target=median,
        presets=steps,
    )


__all__ = [
    "DEFAULT_MAX_QTY",
    "DEFAULT_NEEDS",
    "DEFAULT_ORDER",
    "DEFAULT_TRIP_GAP",
    "MAX_NEEDS",
    "MAX_TRIP_GAP",
    "MIN_NEEDS",
    "ORDER_ROUND",
    "P90_FROM",
    "QTY_HEADROOM",
    "Spend",
    "Usual",
    "max_qty",
    "trip_gap",
    "usual_basket",
    "usual_basket_stats",
    "usual_order",
]
