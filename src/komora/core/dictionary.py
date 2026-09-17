from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

STEM = 4

_APOSTROPHES = "'\u02bc\u2019\u2018"
_WORD = re.compile(rf"[^\W\d_]+(?:[{_APOSTROPHES}][^\W\d_]+)*", re.UNICODE)


FORM_TAIL = 1


class Level(StrEnum):

    TITLE = "title"
    """Назва вузла — це рівно слово гостя: «Молоко», «Свинина»."""
    FORM = "form"
    """Назва з одного слова, але в іншій формі: «сир» -> «Сири»."""
    WORD = "word"
    """Слово стоїть у назві серед інших: «Сир кисломолочний»."""
    NEAR = "near"
    """Інша форма серед інших слів: «лимон» -> «Лимонна кислота»."""
    STEM = "stem"
    """Спільний корінь у чотири літери: «сир» -> «Сиропи»."""


_RANK = {Level.TITLE: 0, Level.FORM: 1, Level.WORD: 2, Level.NEAR: 3, Level.STEM: 4}

STRONG = (Level.TITLE, Level.FORM, Level.WORD)


@dataclass(frozen=True, slots=True)
class Node:
    id: str
    title: str
    parent_id: str | None = None
    slug: str = ""


@dataclass(frozen=True, slots=True)
class Match:
    node: Node
    level: Level

    @property
    def strong(self) -> bool:
        return self.level in STRONG


ECHO = (Level.TITLE, Level.FORM)


def _level_of(needle: str, title: str) -> Level:
    if normalize(title) == needle:
        return Level.TITLE
    words = words_of(title)
    if len(words) == 1 and same_word(needle, words[0]):
        return Level.FORM
    if needle in words:
        return Level.WORD
    if any(same_word(needle, word) for word in words):
        return Level.NEAR
    return Level.STEM


def echoes(word: str, title: str) -> bool:
    needle = normalize(word)
    return bool(needle) and _level_of(needle, title) in ECHO


def normalize(word: str) -> str:
    lowered = word.strip().lower()
    for mark in _APOSTROPHES[1:]:
        lowered = lowered.replace(mark, "'")
    return lowered


def words_of(title: str) -> tuple[str, ...]:
    return tuple(normalize(word) for word in _WORD.findall(title))


def same_word(word: str, other: str, *, tail: int = FORM_TAIL) -> bool:
    common = 0
    for left, right in zip(word, other, strict=False):
        if left != right:
            break
        common += 1
    if common < max(3, len(word) - tail):
        return False
    return len(word) - common <= tail and len(other) - common <= tail


class Dictionary:

    __slots__ = ("_by_id", "_children", "_nodes", "_stems", "_titles", "_words")

    def __init__(self, nodes: Iterable[Node]) -> None:
        self._nodes = tuple(nodes)
        self._by_id = {node.id: node for node in self._nodes}
        self._children: dict[str | None, list[Node]] = defaultdict(list)
        self._titles: dict[str, list[Node]] = defaultdict(list)
        self._words: dict[str, list[Node]] = defaultdict(list)
        self._stems: dict[str, list[Node]] = defaultdict(list)
        for node in self._nodes:
            parent = node.parent_id if node.parent_id in self._by_id else None
            self._children[parent].append(node)
            self._titles[normalize(node.title)].append(node)
            for word in words_of(node.title):
                self._words[word].append(node)
                self._stems[word[:STEM]].append(node)

    def __len__(self) -> int:
        return len(self._nodes)

    @property
    def nodes(self) -> tuple[Node, ...]:
        return self._nodes

    def node(self, node_id: str) -> Node | None:
        return self._by_id.get(node_id)

    def by_slug(self, slug: str) -> Node | None:
        return next((node for node in self._nodes if node.slug == slug), None)

    def roots(self) -> tuple[Node, ...]:
        return tuple(self._children.get(None, ()))

    def children(self, node_id: str) -> tuple[Node, ...]:
        return tuple(self._children.get(node_id, ()))

    def ancestors(self, node_id: str) -> tuple[Node, ...]:
        path: list[Node] = []
        seen = {node_id}
        node = self._by_id.get(node_id)
        while node is not None and node.parent_id and node.parent_id not in seen:
            seen.add(node.parent_id)
            parent = self._by_id.get(node.parent_id)
            if parent is None:
                break
            path.append(parent)
            node = parent
        return tuple(path)

    def candidates(self, word: str, *, limit: int = 3) -> tuple[Node, ...]:
        picked: list[Node] = []
        for match in self.lookup(word):
            if len(picked) >= limit:
                break
            if not match.strong:
                continue
            if any(self.related(match.node.id, node.id) for node in picked):
                continue
            picked.append(match.node)
        return tuple(picked)

    def related(self, first: str, second: str) -> bool:
        if first == second:
            return True
        return second in {node.id for node in self.ancestors(first)} or first in {
            node.id for node in self.ancestors(second)
        }

    def lookup(self, word: str) -> tuple[Match, ...]:
        needle = normalize(word)
        if not needle:
            return ()

        found: dict[str, Node] = {}
        for nodes in (
            self._titles.get(needle, ()),
            self._words.get(needle, ()),
            self._stem_candidates(needle),
        ):
            for node in nodes:
                found.setdefault(node.id, node)

        return tuple(
            sorted(
                (Match(node, _level_of(needle, node.title)) for node in found.values()),
                key=lambda m: (
                    _RANK[m.level],
                    len(words_of(m.node.title)),
                    len(m.node.title),
                    m.node.title,
                ),
            )
        )

    def _stem_candidates(self, needle: str) -> list[Node]:
        if len(needle) >= STEM:
            return self._stems.get(needle[:STEM], [])
        return [
            node for word, nodes in self._words.items() if word.startswith(needle) for node in nodes
        ]

    def prepared_siblings(self, node_id: str) -> tuple[Node, ...]:
        node = self._by_id.get(node_id)
        if node is None or is_prepared_title(node.title):
            return ()
        return tuple(
            sibling
            for sibling in self._children.get(node.parent_id, ())
            if sibling.id != node.id and is_prepared_title(sibling.title)
        )

    def best(self, word: str) -> Match | None:
        matches = self.lookup(word)
        return matches[0] if matches else None

    def proves_intent(self, word: str) -> bool:
        return bool(self.lookup(word))

    def narrowing(self, word: str) -> tuple[str, ...]:
        match = self.best(word)
        if match is None:
            return ()
        return tuple(child.title for child in self.children(match.node.id))


PREPARED_TITLE_WORDS = frozenset(
    {
        "напівфабрикат",
        "напівфабрикати",
        "шашлик",
        "шашлику",
        "барбекю",
        "готові",
        "готова",
        "готовий",
        "кулінарія",
        "копчена",
        "копчені",
        "мариновані",
        "консерви",
        "пресерви",
        "снеки",
        "страви",
    }
)


def is_prepared_title(title: str) -> bool:
    return bool(set(words_of(title)) & PREPARED_TITLE_WORDS)


@dataclass(frozen=True, slots=True)
class Drift:

    added: tuple[Node, ...] = ()
    renamed: tuple[tuple[Node, Node], ...] = ()
    moved: tuple[tuple[Node, Node], ...] = ()
    gone: tuple[Node, ...] = ()

    @property
    def quiet(self) -> bool:
        return not (self.added or self.renamed or self.moved or self.gone)

    def summary(self) -> str:
        if self.quiet:
            return "дерево не змінилось"
        parts = [
            f"додано {len(self.added)}" if self.added else "",
            f"перейменовано {len(self.renamed)}" if self.renamed else "",
            f"переїхало {len(self.moved)}" if self.moved else "",
            f"зникло {len(self.gone)}" if self.gone else "",
        ]
        return ", ".join(part for part in parts if part)


def diff(before: Iterable[Node], after: Iterable[Node]) -> Drift:
    old = {node.id: node for node in before}
    new = {node.id: node for node in after}
    both = sorted(old.keys() & new.keys())
    return Drift(
        added=tuple(new[i] for i in sorted(new.keys() - old.keys())),
        renamed=tuple((old[i], new[i]) for i in both if old[i].title != new[i].title),
        moved=tuple((old[i], new[i]) for i in both if old[i].parent_id != new[i].parent_id),
        gone=tuple(old[i] for i in sorted(old.keys() - new.keys())),
    )


__all__ = [
    "ECHO",
    "PREPARED_TITLE_WORDS",
    "STEM",
    "Dictionary",
    "Drift",
    "Level",
    "Match",
    "Node",
    "diff",
    "echoes",
    "is_prepared_title",
    "normalize",
    "words_of",
]
