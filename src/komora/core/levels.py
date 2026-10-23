from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Level:

    id: str
    intent: str
    urgent: bool


@dataclass(frozen=True, slots=True)
class Folded:

    order: tuple[str, ...]
    group_of: Mapping[str, str]
    groups: int
    rows: int


def fold(levels: Sequence[Level], *, apart: Iterable[str] = ()) -> Folded:
    split = {name for name in apart if name}
    counts: dict[str, int] = {}
    for level in levels:
        if level.intent and level.intent not in split:
            counts[level.intent] = counts.get(level.intent, 0) + 1

    buckets: dict[tuple[bool, str], list[str]] = {}
    group_of: dict[str, str] = {}
    for level in levels:
        twin = bool(level.intent) and counts.get(level.intent, 0) > 1
        buckets.setdefault((twin, level.intent if twin else level.id), []).append(level.id)
        if twin:
            group_of[level.id] = level.intent
    order = tuple(row for members in buckets.values() for row in members)
    groups = sum(1 for twin, _ in buckets if twin)
    return Folded(order=order, group_of=group_of, groups=groups, rows=len(group_of))


@dataclass(frozen=True, slots=True)
class Seen:

    label: str
    unit: str
    receipts: int
    days_since: int | None
    article: str = ""


@dataclass(frozen=True, slots=True)
class Part:

    label: str
    unit: str
    receipts: int
    days_since: int | None
    fresh: bool


def parts(seen: Iterable[Seen], *, recent_days: int) -> tuple[Part, ...]:
    merged: dict[str, Seen] = {}
    for one in seen:
        was = merged.get(one.label)
        if was is None:
            merged[one.label] = one
            continue
        days = [value for value in (was.days_since, one.days_since) if value is not None]
        merged[one.label] = Seen(
            label=one.label,
            unit=was.unit or one.unit,
            receipts=was.receipts + one.receipts,
            days_since=min(days) if days else None,
            article=was.article or one.article,
        )
    ranked = sorted(
        merged.values(),
        key=lambda one: (one.days_since is None, one.days_since or 0, -one.receipts),
    )
    return tuple(
        Part(
            label=one.label,
            unit=one.unit,
            receipts=one.receipts,
            days_since=one.days_since,
            fresh=one.days_since is not None and one.days_since <= recent_days,
        )
        for one in ranked
    )


def own_chain(seen: Iterable[Seen], *, head: str, recent_days: int) -> tuple[Seen, ...]:
    ranked = sorted(
        (
            one
            for one in seen
            if one.article
            and one.article != head
            and one.days_since is not None
            and one.days_since <= recent_days
        ),
        key=lambda one: (one.days_since or 0, -one.receipts),
    )
    picked: dict[str, Seen] = {}
    for one in ranked:
        picked.setdefault(one.article, one)
    return tuple(picked.values())


def fresh_links(
    articles: Iterable[str], seen: Iterable[Seen], *, recent_days: int
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    stale = {
        one.article: one.days_since
        for one in seen
        if one.article and one.days_since is not None and one.days_since > recent_days
    }
    kept = tuple(article for article in articles if article not in stale)
    dropped = tuple(article for article in articles if article in stale)
    return kept, dropped


__all__ = [
    "Folded",
    "Level",
    "Part",
    "Seen",
    "fold",
    "fresh_links",
    "own_chain",
    "parts",
]
