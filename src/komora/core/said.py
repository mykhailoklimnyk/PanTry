from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime

from komora.core.bar import DrinkKind

SOURCE_RECEIPTS = "receipts"
SOURCE_MANUAL = "manual"

GUEST = "guest"
PURCHASES = "purchases"

PANTRY = "pantry"
BAR = "bar"


def origin_of_list(source: str) -> str | None:
    return None if source == SOURCE_MANUAL else GUEST


@dataclass(frozen=True, slots=True)
class Said:

    scope: str = PANTRY
    source: str = SOURCE_RECEIPTS
    marks: Mapping[str, datetime] = field(default_factory=dict)
    cycles: Mapping[str, int] = field(default_factory=dict)
    cycle_sources: Mapping[str, str] = field(default_factory=dict)
    hidden: Sequence[str] = ()
    drinks: Mapping[str, DrinkKind] = field(default_factory=dict)
    apart: Sequence[str] = ()
    listed: Mapping[str, str] = field(default_factory=dict)
    written: Mapping[str, str] = field(default_factory=dict)

    def with_marks(self, extra: Mapping[str, datetime]) -> Said:
        return replace(self, marks={**self.marks, **extra})

    def with_hidden(self, kind: str, *, away: bool) -> Said:
        rest = tuple(key for key in self.hidden if key != kind)
        return replace(self, hidden=(*rest, kind) if away else rest)

    def with_apart(self, intent: str, *, apart: bool) -> Said:
        rest = tuple(name for name in self.apart if name != intent)
        return replace(self, apart=(*rest, intent) if apart else rest)

    def with_cycle_sources(self, sources: Mapping[str, str]) -> Said:
        return replace(self, cycle_sources=sources)

    def with_cycles(self, cycles: Mapping[str, int]) -> Said:
        return replace(self, cycles=cycles)


__all__ = [
    "BAR",
    "GUEST",
    "PANTRY",
    "PURCHASES",
    "SOURCE_MANUAL",
    "SOURCE_RECEIPTS",
    "Said",
    "origin_of_list",
]
