from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

OUT = "out"
SOON = "soon"
PROMO = "promo"

_RANK = {OUT: 0, SOON: 1, PROMO: 2}


@dataclass(frozen=True, slots=True)
class Row:

    kind: str
    label: str
    running_out: bool
    days_left: int | None
    promo: bool = False
    manual: bool = False


@dataclass(frozen=True, slots=True)
class Pick:

    kind: str
    label: str
    reason: str
    days_left: int | None = None

    def rank(self) -> tuple[int, int]:
        return (_RANK.get(self.reason, len(_RANK)), self.days_left or 0)


def choose(rows: Sequence[Row], *, gap_days: int, limit: int) -> tuple[Pick, ...]:
    picks: list[Pick] = []
    for row in rows:
        if row.manual:
            continue
        if row.promo:
            picks.append(Pick(row.kind, row.label, PROMO, row.days_left))
            continue
        if row.running_out:
            picks.append(Pick(row.kind, row.label, OUT, row.days_left))
            continue
        if row.days_left is not None and row.days_left <= gap_days:
            picks.append(Pick(row.kind, row.label, SOON, row.days_left))
    picks.sort(key=Pick.rank)
    return tuple(picks[: max(0, limit)])


def why(pick: Pick) -> str:
    if pick.reason == PROMO:
        return "береш це по акції — без знижки не бери"
    if pick.reason == OUT:
        return "закінчилось" if pick.days_left is None else _out_phrase(pick.days_left)
    if pick.days_left is None:
        return "закінчиться до наступного походу"
    return f"закінчиться за {pick.days_left} дн — до наступного походу"


def _out_phrase(days_left: int) -> str:
    if days_left > 0:
        return f"майже закінчилось: лишилось ~{days_left} дн"
    if days_left == 0:
        return "закінчилось сьогодні"
    return f"мало закінчитись {-days_left} дн тому"


def changes(before: Mapping[str, str], after: Mapping[str, str]) -> tuple[str, ...]:
    added = [f"додав {after[kind]}" for kind in after if kind not in before]
    gone = [f"зняв {before[kind]} — більше не закінчується" for kind in before if kind not in after]
    return tuple(added + gone)


__all__ = ["OUT", "PROMO", "SOON", "Pick", "Row", "changes", "choose", "why"]
