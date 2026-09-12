from __future__ import annotations

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from statistics import median

from komora.core import brands
from komora.core.promo import MIN_PURCHASES, MOSTLY, Habit

_NOT_A_BRAND = frozenset({"уп", "шт", "кг", "мл"})


class Proof(StrEnum):

    YES = "yes"
    """Доведено: покупок досить і вони згодні між собою."""

    NO = "no"
    """Чеки кажуть ПРОТИЛЕЖНЕ. Це відповідь, а не мовчання: питати про це
    гостя означало б перепитувати те, на що він уже відповів покупками."""

    UNKNOWN = "unknown"
    """Не доведено: покупок замало або вони не згодні. Саме тут і є сенс
    питати -- у решті станів питання коштує довіру, а не приносить факт."""


@dataclass(frozen=True, slots=True)
class Bought:

    name: str
    qty: Decimal
    at: date


@dataclass(frozen=True, slots=True)
class Brand:

    word: str
    """Слово назви, а не наш словник: переліку марок у коді немає (#108)."""
    purchases: int
    out_of: int

    @property
    def share(self) -> Decimal:
        return Decimal(self.purchases) / Decimal(self.out_of) if self.out_of else Decimal(0)


def brand_words(name: str) -> tuple[str, ...]:
    head = brands.head_word(name)
    seen: list[str] = []
    for token in brands.words(name):
        if token == head or token.casefold() in _NOT_A_BRAND:
            continue
        bones = brands.skeleton(token)
        if bones and bones not in seen:
            seen.append(bones)
    return tuple(seen)


def brand(bought: Sequence[Bought]) -> Brand | None:
    counted: Counter[str] = Counter()
    spelling: dict[str, str] = {}
    for purchase in bought:
        for bones in brand_words(purchase.name):
            counted[bones] += 1
            spelling.setdefault(bones, purchase.name)
    if not counted:
        return None
    bones, hits = counted.most_common(1)[0]
    return Brand(word=spelling[bones], purchases=hits, out_of=len(bought))


def brand_matters(bought: Sequence[Bought]) -> Proof:
    if len(bought) < MIN_PURCHASES:
        return Proof.UNKNOWN
    top = brand(bought)
    if top is None:
        return Proof.UNKNOWN
    share, out_of = MOSTLY
    if top.purchases * out_of >= top.out_of * share:
        return Proof.YES
    return Proof.NO


def promo_only(habit: Habit) -> Proof:
    if habit.weighed or habit.purchases < MIN_PURCHASES:
        return Proof.UNKNOWN
    return Proof.YES if habit.mostly else Proof.NO


@dataclass(frozen=True, slots=True)
class Rate:

    per_trip: Decimal
    """Скільки гість бере за один похід (медіана)."""
    gap_days: int
    """Скільки днів між походами по цей вид."""

    @property
    def per_day(self) -> Decimal:
        return self.per_trip / Decimal(self.gap_days) if self.gap_days else Decimal(0)


def per_trip(bought: Sequence[Bought]) -> Decimal | None:
    quantities = [purchase.qty for purchase in bought if purchase.qty > 0]
    if not quantities:
        return None
    return Decimal(str(median(quantities)))


def rate(bought: Sequence[Bought], *, gap_days: int | None) -> Rate | None:
    if gap_days is None or gap_days <= 0:
        return None
    amount = per_trip(bought)
    if amount is None:
        return None
    return Rate(per_trip=amount, gap_days=gap_days)


def consumption(bought: Sequence[Bought], *, gap_days: int | None, keeps_days: int | None) -> Proof:
    if rate(bought, gap_days=gap_days) is None or len(bought) < MIN_PURCHASES:
        return Proof.UNKNOWN
    if keeps_days is not None and gap_days is not None and gap_days > keeps_days:
        return Proof.NO
    return Proof.YES


NORM_GAP = 5


def sees_a_fraction(per_day: Decimal | None, *, bought_per_day: Decimal | None) -> bool:
    if per_day is None or bought_per_day is None or bought_per_day <= 0:
        return False
    return per_day >= bought_per_day * NORM_GAP


@dataclass(frozen=True, slots=True)
class Traits:

    promo: Proof = Proof.UNKNOWN
    consumption: Proof = Proof.UNKNOWN
    brand: Proof = Proof.UNKNOWN

    def silent(self) -> tuple[str, ...]:
        named = (("акція", self.promo), ("споживання", self.consumption), ("марка", self.brand))
        return tuple(label for label, proof in named if proof is Proof.UNKNOWN)

    def note(self) -> str:
        proven = sum(
            1 for proof in (self.promo, self.consumption, self.brand) if proof is Proof.YES
        )
        against = sum(
            1 for proof in (self.promo, self.consumption, self.brand) if proof is Proof.NO
        )
        return f"доведено {proven}, чеки заперечують {against}, мовчать {len(self.silent())}"


def traits(
    bought: Sequence[Bought],
    *,
    habit: Habit,
    gap_days: int | None,
    keeps_days: int | None,
) -> Traits:
    return Traits(
        promo=promo_only(habit),
        consumption=consumption(bought, gap_days=gap_days, keeps_days=keeps_days),
        brand=brand_matters(bought),
    )


__all__ = [
    "NORM_GAP",
    "Bought",
    "Brand",
    "Proof",
    "Rate",
    "Traits",
    "brand",
    "brand_matters",
    "brand_words",
    "consumption",
    "per_trip",
    "promo_only",
    "rate",
    "sees_a_fraction",
    "traits",
]
