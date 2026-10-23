from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

SLICED_MARKERS: frozenset[str] = frozenset({"наріз", "різан", "слайс", "скибочк"})

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)


def is_sliced(name: str) -> bool:
    return any(
        marker in word
        for word in _WORD.findall(name.lower())
        for marker in SLICED_MARKERS
    )


def form_of(name: str) -> str:
    return "нарізаний" if is_sliced(name) else "без нарізки"


@dataclass(frozen=True, slots=True)
class Habit:

    sliced: bool | None
    sliced_receipts: int
    plain_receipts: int

    def says(self) -> str:
        parts = []
        if self.plain_receipts:
            parts.append(f"{self.plain_receipts} без нарізки")
        if self.sliced_receipts:
            parts.append(f"{self.sliced_receipts} нарізаним")
        return "у твоїх чеках цей вид " + (", ".join(parts) or "не траплявся")


def habit(purchases: Iterable[tuple[str, int]]) -> Habit:
    sliced = plain = 0
    for name, receipts in purchases:
        if receipts <= 0:
            continue
        if is_sliced(name):
            sliced += receipts
        else:
            plain += receipts
    if sliced + plain < 2 or sliced == plain:
        return Habit(None, sliced, plain)
    return Habit(sliced > plain, sliced, plain)


def wish(chosen: str, options: Iterable[str]) -> str | None:
    forms = {is_sliced(name) for name in options}
    if len(forms) < 2:
        return None
    return form_of(chosen)


def note(chosen: str, guest: Habit) -> str | None:
    if guest.sliced is None or guest.sliced == is_sliced(chosen):
        return None
    return guest.says()
