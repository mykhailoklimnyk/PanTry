from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from itertools import pairwise

from komora.core.words import plural

MIN_PURCHASES_FOR_CYCLE = 4

SILENCE_LIMIT = 2.0


class Keeps(StrEnum):

    DAYS = "дні"
    WEEKS = "тижні"
    MONTHS = "місяці"
    YEARS = "роки"


KEEPS_CEILING: dict[Keeps, int] = {
    Keeps.DAYS: 7,
    Keeps.WEEKS: 30,
    Keeps.MONTHS: 365,
}


def ceiling_days(keeps: Keeps | None) -> int | None:
    return None if keeps is None else KEEPS_CEILING.get(keeps)


class Trust(StrEnum):

    CYCLE = "cycle"

    SILENT = "silent"

    RARE = "rare"

    ELSEWHERE = "elsewhere"

    NOT_RHYTHM = "not_rhythm"

    SAID = "said"


@dataclass(frozen=True, slots=True)
class Rhythm:

    purchases: int

    trust: Trust
    cycle_days: int | None

    days_since: int | None
    receipts_days: int | None = None

    shortest: int | None = None
    longest: int | None = None

    beyond_keeps: bool = False

    @property
    def proven(self) -> bool:
        return self.cycle_days is not None

    @property
    def silence(self) -> float | None:
        if self.cycle_days is None or self.days_since is None:
            return None
        return self.days_since / self.cycle_days

    def phrase(self) -> str:
        if self.trust in (Trust.CYCLE, Trust.SAID):
            return ""
        since = "" if self.days_since is None else f", остання {self.days_since} дн тому"
        if self.trust is Trust.SILENT:
            return f"давно не брав: {self.days_since} дн при звичних ~{self.cycle_days}"
        if self.trust is Trust.ELSEWHERE or (self.trust is Trust.NOT_RHYTHM and self.beyond_keeps):
            return (
                f"у «Сільпо» раз на {self.receipts_days} дн, "
                "а стільки воно не лежить — схоже, береш це не тільки тут"
            )
        if self.trust is Trust.NOT_RHYTHM:
            return f"береш раз на {self.receipts_days} дн, але купівля тут не дорівнює витрачанню"
        if self.purchases < MIN_PURCHASES_FOR_CYCLE:
            left = MIN_PURCHASES_FOR_CYCLE - self.purchases
            more = {1: "одна", 2: "дві", 3: "три"}.get(left, str(left))
            return (
                f"{self.purchases} {plural(self.purchases, 'покупка', 'покупки', 'покупок')} "
                f"в різні дні — ще {more}, і скажу цикл{since}"
            )
        if self.shortest is None or self.longest is None:
            return f"береш нерівно{since}"
        return f"береш нерівно: між покупками від {self.shortest} до {self.longest} дн{since}"


def median(values: Sequence[float]) -> float:
    if not values:
        raise ValueError("медіана порожньої вибірки не визначена")
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return float(ordered[middle])
    return (ordered[middle - 1] + ordered[middle]) / 2


def stddev(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
    return math.sqrt(variance)


def intervals_days(purchase_dates: Sequence[date]) -> list[float]:
    ordered = sorted(set(purchase_dates))
    return [float((later - earlier).days) for earlier, later in pairwise(ordered)]


def is_stable(purchases_count: int, median_days: float | None, stddev_days: float) -> bool:
    if purchases_count < MIN_PURCHASES_FOR_CYCLE:
        return False
    if not median_days:
        return False
    return stddev_days <= median_days


def rhythm(
    purchase_dates: Sequence[date],
    *,
    days_since: int | None,
    said_days: int | None = None,
    keeps: Keeps | None = None,
    rhythm_lies: bool = False,
) -> Rhythm:
    days = sorted(set(purchase_dates))
    gaps = intervals_days(days)
    spread = stddev(gaps)
    middle = median(gaps) if gaps else None
    seen = max(1, round(middle)) if middle else None
    shortest = int(min(gaps)) if gaps else None
    longest = int(max(gaps)) if gaps else None
    limit = ceiling_days(keeps)
    beyond = limit is not None and seen is not None and seen > limit

    if said_days is not None and said_days > 0:
        return Rhythm(
            purchases=len(days),
            trust=Trust.SAID,
            cycle_days=said_days,
            days_since=days_since,
            receipts_days=seen,
            shortest=shortest,
            longest=longest,
            beyond_keeps=beyond,
        )

    if rhythm_lies:
        return Rhythm(
            purchases=len(days),
            trust=Trust.NOT_RHYTHM,
            cycle_days=None,
            days_since=days_since,
            receipts_days=seen,
            shortest=shortest,
            longest=longest,
            beyond_keeps=beyond,
        )

    if not is_stable(len(days), middle, spread) or middle is None:
        return Rhythm(
            purchases=len(days),
            trust=Trust.RARE,
            cycle_days=None,
            days_since=days_since,
            receipts_days=seen,
            shortest=shortest,
            longest=longest,
            beyond_keeps=beyond,
        )

    cycle = max(1, round(middle))
    if beyond:
        return Rhythm(
            purchases=len(days),
            trust=Trust.ELSEWHERE,
            cycle_days=None,
            days_since=days_since,
            receipts_days=cycle,
            shortest=shortest,
            longest=longest,
            beyond_keeps=beyond,
        )
    silent = days_since is not None and days_since > SILENCE_LIMIT * cycle
    return Rhythm(
        purchases=len(days),
        trust=Trust.SILENT if silent else Trust.CYCLE,
        cycle_days=cycle,
        days_since=days_since,
        receipts_days=cycle,
        shortest=shortest,
        longest=longest,
        beyond_keeps=beyond,
    )


FOREIGN_NOTE = "цей кошик наповнив хтось інший — за циклом я до нього нічого не добираю"

ASK_NOTE = "напиши, що треба"


def coverage_note(
    *,
    takes_cycles: bool,
    receipts: int,
    kinds: int,
    uneven: int,
    tracked_from: int,
    orders: int = 0,
) -> str:
    if not takes_cycles:
        return (
            "у режимі «зі списку» я беру рівно те, що ти назвав — "
            f"комору і цикли тут не читаю: {ASK_NOTE}, "
            "або перемкни режим на «на тиждень»"
        )
    if receipts == 0 and orders == 0:
        return f"історії покупок ще немає — за циклом добирати нема з чого, {ASK_NOTE}"
    if kinds == 0:
        return (
            f"жоден вид ще не набрав {tracked_from} покупок у різні дні — "
            f"за циклом добирати нема з чого, {ASK_NOTE}"
        )
    proven = kinds - uneven
    if proven <= 0:
        return (
            f"усі {kinds} {plural(kinds, 'вид', 'види', 'видів')} з твоїх чеків ти "
            f"береш нерівно — за циклом я їх не добираю, {ASK_NOTE}"
        )
    if uneven <= 0:
        return f"за циклом стежу за всіма {kinds} видами твоїх чеків"
    return (
        f"за циклом я добираю тільки те, що ти береш рівно: таких видів "
        f"{proven} з {kinds}. Решту ти береш нерівно — вгадувати не буду, "
        f"{ASK_NOTE}"
    )


__all__ = [
    "ASK_NOTE",
    "FOREIGN_NOTE",
    "MIN_PURCHASES_FOR_CYCLE",
    "SILENCE_LIMIT",
    "Rhythm",
    "Trust",
    "coverage_note",
    "intervals_days",
    "is_stable",
    "median",
    "rhythm",
    "stddev",
]
