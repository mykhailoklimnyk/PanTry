from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

CATCH_ALL = "Інше"

BY_WORD_ONLY = frozenset({"Соуси і спеції"})


def by_word_only(aisle: str | None) -> bool:
    return aisle is not None and aisle in BY_WORD_ONLY


@dataclass(frozen=True, slots=True)
class Aisle:

    title: str
    rows: int


@dataclass(frozen=True, slots=True)
class Aisled:

    of: Mapping[str, str]
    order: tuple[Aisle, ...]


def aisles(
    rows: Sequence[tuple[str, Iterable[str]]],
    catalog: Mapping[str, frozenset[str]],
    roots: Mapping[str, frozenset[str]],
    said: Mapping[str, str] | None = None,
) -> Aisled:
    node_root: dict[str, list[str]] = {}
    for title, slugs in roots.items():
        for slug in slugs:
            node_root.setdefault(slug, []).append(title)

    of: dict[str, str] = {}
    counted: dict[str, int] = {}
    order: list[str] = []
    for row, articles in rows:
        hits: dict[str, int] = {}
        for article in articles:
            for slug in catalog.get(article, frozenset()):
                for title in node_root.get(slug, ()):
                    hits[title] = hits.get(title, 0) + 1
        tree = min(hits.items(), key=lambda one: (-one[1], one[0]))[0] if hits else CATCH_ALL
        named = (said or {}).get(row) or ""
        pick = named if named and named != CATCH_ALL else tree
        of[row] = pick
        if pick not in counted:
            order.append(pick)
        counted[pick] = counted.get(pick, 0) + 1

    if not roots:
        return Aisled(of={}, order=())

    order.sort(key=lambda title: title == CATCH_ALL)
    return Aisled(of=of, order=tuple(Aisle(title=title, rows=counted[title]) for title in order))


__all__ = ["CATCH_ALL", "Aisle", "Aisled", "aisles"]
