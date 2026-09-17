from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

from komora.agent.kinds import KIND_LIMIT, MAX_READINGS, fetch_listing
from komora.core.ambiguity import MAX_OPTIONS, Option, axis_of, on_axis, option, usable
from komora.core.dictionary import Dictionary, Node, echoes
from komora.core.words import plural
from komora.mcp.client import SilpoMCP

MAX_PROBES = MAX_OPTIONS + 2

type Search = Callable[
    [SilpoMCP, list[str], dict[str, Any], str | None],
    Awaitable[tuple[dict[str, list[dict[str, Any]]], int]],
]


@dataclass(frozen=True, slots=True)
class Asked:

    options: tuple[Option, ...] = ()
    from_model: int = 0
    """Скільки чипів принесла модель -- разом з тими, що лягли на вузол."""
    from_tree: int = 0
    """Скільки чипів дало дерево запасним шляхом."""
    by_search: int = 0
    """З них підписані ПОШУКОМ, а не переліком вузла: вузла під фразою немає."""
    tautology: int = 0
    """Знято як повтор слова гостя -- «Сири» під «сир» (#280)."""
    off_axis: int = 0
    """Знято як відповідь не на ту вісь -- вино «Кава (Cava)» під «кава» (#308)."""
    empty: int = 0
    """Відпало через порожню полицю на цей слот."""
    spent_ms: int = 0

    @property
    def source(self) -> str:
        if not self.options:
            return "нічого"
        return "модель" if self.from_model else "дерево"

    @property
    def note(self) -> str:
        if self.from_model:
            head = f"{self.from_model} від моделі"
            if self.by_search:
                head += f" ({self.from_model - self.by_search} з дерева, "
                head += f"{self.by_search} з пошуку)"
            else:
                head += " (усі з дерева)"
        elif self.from_tree:
            head = f"{self.from_tree} з дерева"
        else:
            head = "жодного: відповідають самі кандидати"
        return (
            f"{head}, знято {self.tautology} "
            f"{plural(self.tautology, 'повтор', 'повтори', 'повторів')} слова, "
            f"{self.off_axis} не на осі питання, порожніх {self.empty}"
        )


def tree_nodes(tree: Dictionary, word: str, ask: str) -> tuple[tuple[Node, ...], int, int]:
    readings = tree.candidates(word, limit=MAX_READINGS)
    if not readings:
        return (), 0, 0
    axis = axis_of(ask, word)
    children = tree.children(readings[0].id)
    seen: set[str] = set()
    nodes: list[Node] = []
    dropped = 0
    aside = 0
    for node in (*readings, *children):
        if not node.slug or node.id in seen:
            continue
        seen.add(node.id)
        if echoes(word, node.title):
            dropped += 1
            continue
        if not on_axis(node.title, axis):
            aside += 1
            continue
        nodes.append(node)
    return tuple(nodes[:MAX_PROBES]), dropped, aside


def option_nodes(tree: Dictionary, word: str, ask: str) -> tuple[Node, ...]:
    return tree_nodes(tree, word, ask)[0]


async def _from_nodes(
    mcp: SilpoMCP,
    word: str,
    nodes: Sequence[Node],
    *,
    slot: dict[str, Any],
    branch_id: str | None,
    limit: int,
) -> tuple[list[Option], int, int]:
    found: list[Option] = []
    empty = 0
    spent_ms = 0
    for node in nodes:
        if len(found) >= MAX_OPTIONS:
            break
        products, spent = await fetch_listing(
            mcp, node.slug, slot=slot, branch_id=branch_id, limit=limit, word=word
        )
        spent_ms += spent
        if products:
            found.append(option(node.title, node.slug, products))
        else:
            empty += 1
    return found, empty, spent_ms


async def options_for(
    mcp: SilpoMCP,
    word: str,
    *,
    ask: str,
    tree: Dictionary,
    slot: dict[str, Any],
    branch_id: str | None,
    limit: int = KIND_LIMIT,
    wanted: Sequence[str] = (),
    search: Search | None = None,
) -> Asked:
    said = _phrases(word, wanted)
    tautology = len(_clean(wanted)) - len(said)
    spent_ms = 0
    found: list[Option] = []
    by_search = 0
    empty = 0

    unresolved: list[str] = []
    for phrase in said:
        node = _node_for(tree, word, phrase)
        if node is None:
            unresolved.append(phrase)
            continue
        products, spent = await fetch_listing(
            mcp, node.slug, slot=slot, branch_id=branch_id, limit=limit, word=phrase
        )
        spent_ms += spent
        if products:
            found.append(option(node.title, node.slug, products))
        else:
            unresolved.append(phrase)

    if unresolved and search is not None:
        batch, spent = await search(mcp, unresolved, slot, branch_id)
        spent_ms += spent
        for phrase in unresolved:
            products = batch.get(phrase) or []
            if products:
                found.append(option(phrase, "", products, query=phrase))
                by_search += 1
            else:
                empty += 1
    else:
        empty += len(unresolved)

    by_model = usable(found)
    if by_model:
        return Asked(
            options=by_model,
            from_model=len(by_model),
            by_search=by_search,
            tautology=tautology,
            empty=empty,
            spent_ms=spent_ms,
        )

    nodes, dropped, aside = tree_nodes(tree, word, ask)
    from_tree, tree_empty, tree_ms = await _from_nodes(
        mcp, word, nodes, slot=slot, branch_id=branch_id, limit=limit
    )
    by_tree = usable(from_tree)
    return Asked(
        options=by_tree,
        from_tree=len(by_tree),
        tautology=tautology + dropped,
        off_axis=aside,
        empty=empty + tree_empty,
        spent_ms=spent_ms + tree_ms,
    )


def _clean(wanted: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    kept: list[str] = []
    for raw in wanted:
        phrase = " ".join(str(raw).split())
        key = phrase.casefold()
        if phrase and key not in seen:
            seen.add(key)
            kept.append(phrase)
    return kept[:MAX_OPTIONS]


def _phrases(word: str, wanted: Sequence[str]) -> list[str]:
    return [phrase for phrase in _clean(wanted) if not echoes(word, phrase)]


def _node_for(tree: Dictionary, word: str, phrase: str) -> Node | None:
    node = next((item for item in tree.candidates(phrase, limit=1) if item.slug), None)
    if node is None or echoes(word, node.title):
        return None
    return node


__all__ = ["MAX_PROBES", "Asked", "Search", "option_nodes", "options_for", "tree_nodes"]
