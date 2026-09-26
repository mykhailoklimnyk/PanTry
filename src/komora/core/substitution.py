from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from komora.core import brands
from komora.core.queries import MIN_WORD

REJECT_THRESHOLD = 2

DEFAULT_CHAIN_LENGTH = 3

LOW_STOCK_THRESHOLD = 10

SHELF_TURNOVER_HOURS = 18


class Source(StrEnum):

    HISTORY = "history"
    REPLACEMENTS = "replacements"
    SIMILAR = "similar"
    MANUAL = "manual"


_SOURCE_RANK = {
    Source.MANUAL: 0,
    Source.HISTORY: 1,
    Source.REPLACEMENTS: 2,
    Source.SIMILAR: 3,
}


@dataclass(frozen=True, slots=True)
class Alternative:
    external_product_id: str
    name: str
    source: Source
    price: Decimal | None = None
    stock: int | None = None
    available: bool = True
    accepted_count: int = 0
    rejected_count: int = 0
    pack: Decimal | None = None
    per_unit: Decimal | None = None
    ratio: str | None = None
    by_weight: bool = False


def acceptance_rate(alternative: Alternative) -> float:
    total = alternative.accepted_count + alternative.rejected_count
    if total == 0:
        return 0.5
    return alternative.accepted_count / total


def is_burned(alternative: Alternative) -> bool:
    return alternative.rejected_count >= REJECT_THRESHOLD


def is_risky(stock: int | None, *, threshold: int = LOW_STOCK_THRESHOLD) -> bool:
    if stock is None:
        return True
    return stock < threshold


class Readiness(StrEnum):

    REQUIRED = "required"
    AHEAD = "ahead"
    NONE = "none"


def readiness(
    stock: int | None,
    *,
    hours_to_slot: float,
    threshold: int = LOW_STOCK_THRESHOLD,
    horizon: float = SHELF_TURNOVER_HOURS,
) -> Readiness:
    if is_risky(stock, threshold=threshold):
        return Readiness.REQUIRED
    if hours_to_slot >= horizon:
        return Readiness.AHEAD
    return Readiness.NONE


def delivers_enough(pack: Decimal | None, *, want: Decimal | None) -> bool:
    return pack is None or want is None or pack >= want


def pack_rank(pack: Decimal | None, *, want: Decimal | None, usual: Decimal | None) -> int:
    if pack is None or want is None:
        return 0
    if pack < want:
        return 2
    return 0 if usual is None or pack <= max(want, usual) else 1


def kinship(name: str, like: str) -> int:
    mine = _named(like)
    if not mine:
        return 0
    return len(mine & _named(name))


def _named(name: str) -> set[str]:
    return {word.casefold() for word in brands.words(name) if len(word) >= MIN_WORD}


def covers(name: str, like: str) -> bool:
    mine = _named(like)
    return bool(mine) and mine <= _named(name)


def pack_distance(pack: Decimal | None, *, want: Decimal | None) -> Decimal:
    if pack is None or want is None:
        return Decimal(0)
    return abs(pack - want)


PRICE_SPREAD = Decimal("2")


def price_within(chosen_price: object, price: object, *, spread: Decimal = PRICE_SPREAD) -> bool:
    if chosen_price is None or price is None:
        return True
    try:
        base, other = Decimal(str(chosen_price)), Decimal(str(price))
    except ArithmeticError:
        return True
    if base <= 0 or other <= 0:
        return True
    return base / spread <= other <= base * spread


def rank_chain(
    alternatives: Iterable[Alternative],
    *,
    excluded_ids: frozenset[str] = frozenset(),
    max_length: int = DEFAULT_CHAIN_LENGTH,
    want: Decimal | None = None,
    usual: Decimal | None = None,
    like: str = "",
) -> tuple[Alternative, ...]:
    if max_length < 0:
        raise ValueError("max_length не може бути від'ємним")

    survivors = [
        alternative
        for alternative in alternatives
        if alternative.available
        and not is_burned(alternative)
        and alternative.external_product_id not in excluded_ids
    ]

    by_unit = all(a.per_unit is not None and a.per_unit > 0 for a in survivors)

    def value(alternative: Alternative) -> Decimal:
        chosen = alternative.per_unit if by_unit else alternative.price
        return chosen if chosen is not None else Decimal("Infinity")

    def order(alternative: Alternative) -> tuple[object, ...]:
        tier = pack_rank(alternative.pack, want=want, usual=usual)
        return (
            _SOURCE_RANK[alternative.source],
            -acceptance_rate(alternative),
            tier,
            -kinship(alternative.name, like),
            Decimal(0) if tier == 0 else pack_distance(alternative.pack, want=want),
            value(alternative),
            alternative.external_product_id,
        )

    survivors.sort(key=order)

    return tuple(survivors[:max_length])
