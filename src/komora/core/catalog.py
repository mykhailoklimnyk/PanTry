from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

from komora.core.dictionary import Node
from komora.core.queries import head

DISPLAY_FLOOR = 0.5

DISPLAY_LEAST = 200


def kinds_of(articles: Iterable[str], catalog: Mapping[str, frozenset[str]]) -> frozenset[str]:
    found: set[str] = set()
    for article in articles:
        found |= catalog.get(article, frozenset())
    return frozenset(found)


def same_kind(article: str, kinds: frozenset[str], catalog: Mapping[str, frozenset[str]]) -> bool:
    mine = catalog.get(article, frozenset())
    if not kinds or not mine:
        return False
    return mine <= kinds or kinds <= mine


def roots_of(tree: Sequence[Node]) -> dict[str, frozenset[str]]:
    kids: dict[str, list[str]] = {}
    by_id = {node.id: node for node in tree}
    for node in tree:
        if node.parent_id:
            kids.setdefault(node.parent_id, []).append(node.id)

    def under(start: str) -> frozenset[str]:
        out: set[str] = set()
        stack = [start]
        while stack:
            current = stack.pop()
            node = by_id[current]
            out.add(node.slug or node.id)
            stack.extend(kids.get(current, ()))
        return frozenset(out)

    return {node.title: under(node.id) for node in tree if not node.parent_id}


def display_roots(
    found: Mapping[str, Iterable[str]],
    roots: Mapping[str, frozenset[str]],
    *,
    floor: float = DISPLAY_FLOOR,
    least: int = DISPLAY_LEAST,
) -> frozenset[str]:
    display: set[str] = set()
    per_root = {
        title: {article for article, nodes in found.items() if set(nodes) & slugs}
        for title, slugs in roots.items()
    }
    homes: dict[str, int] = {}
    for articles in per_root.values():
        for article in articles:
            homes[article] = homes.get(article, 0) + 1
    for title, articles in per_root.items():
        if len(articles) < least:
            continue
        alone = sum(1 for article in articles if homes[article] == 1)
        if alone / len(articles) < floor:
            display.add(title)
    return frozenset(display)


def kind_only(
    found: Mapping[str, Iterable[str]],
    roots: Mapping[str, frozenset[str]],
    *,
    floor: float = DISPLAY_FLOOR,
    least: int = DISPLAY_LEAST,
) -> tuple[dict[str, frozenset[str]], frozenset[str]]:
    display = display_roots(found, roots, floor=floor, least=least)
    drop: set[str] = set()
    for title in display:
        drop |= roots[title]
    return ({a: frozenset(set(n) - drop) for a, n in found.items()}, display)


__all__ = ["display_roots", "kind_only", "kinds_of", "roots_of", "same_kind"]


def kind_word(name: str) -> str:
    return (head(name, 1) or name).strip().lower()


@dataclass(frozen=True, slots=True)
class KindKeys:

    of: Mapping[str, str]
    by_word: Mapping[str, frozenset[str]]

    def key(self, name: str) -> str:
        return self.of.get(name) or kind_word(name)

    def covering(self, name: str) -> frozenset[str]:
        known = self.of.get(name)
        if known:
            return frozenset({known})
        word = kind_word(name)
        return self.by_word.get(word) or frozenset({word})


def kind_keys(
    rows: Iterable[tuple[str, str]],
    catalog: Mapping[str, frozenset[str]],
    *,
    unknown_merges: bool = True,
) -> KindKeys:
    groups: dict[str, list[tuple[str, frozenset[str]]]] = {}
    for name, article in rows:
        groups.setdefault(kind_word(name), []).append((name, catalog.get(article) or frozenset()))

    of: dict[str, str] = {}
    by_word: dict[str, set[str]] = {}
    for word, members in groups.items():
        parent = list(range(len(members)))

        def root(index: int, parent: list[int] = parent) -> int:
            while parent[index] != index:
                parent[index] = parent[parent[index]]
                index = parent[index]
            return index

        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                left, right = members[i][1], members[j][1]
                blank = not left or not right
                if (left & right) or (blank and unknown_merges):
                    parent[root(i)] = root(j)

        names: dict[int, list[str]] = {}
        for index, (name, _nodes) in enumerate(members):
            names.setdefault(root(index), []).append(name)
        for members_of_class in names.values():
            key = f"{word}·{min(members_of_class)}"
            by_word.setdefault(word, set()).add(key)
            for name in members_of_class:
                of[name] = key

    return KindKeys(of=of, by_word={word: frozenset(keys) for word, keys in by_word.items()})
