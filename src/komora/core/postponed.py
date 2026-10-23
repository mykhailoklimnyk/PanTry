from collections.abc import Iterable
from enum import StrEnum


class Remedy(StrEnum):

    REFILL = "refill"
    MANUAL = "manual"
    NEXT_RUN = "next_run"
    PROMO = "promo"
    SHELF = "shelf"


FIX_ORDER = (
    Remedy.REFILL,
    Remedy.MANUAL,
    Remedy.NEXT_RUN,
    Remedy.PROMO,
    Remedy.SHELF,
)


def in_fix_order[T](tagged: Iterable[tuple[Remedy, T]]) -> list[T]:
    rank = {remedy: place for place, remedy in enumerate(FIX_ORDER)}
    return [item for _, item in sorted(tagged, key=lambda pair: rank[pair[0]])]
