from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from komora.core.dictionary import Dictionary, Node
from komora.jobs.categories import fetch_all
from komora.logging import get_logger
from komora.mcp.client import MCPCallError, SilpoMCP, TokenRejected

log = get_logger(__name__)

TOOL = "silpo_get_products"

KIND_LIMIT = 40

MAX_KINDS = 8

MAX_PREPARED = 4

MAX_READINGS = 3

MAX_PROBES = 2

_TREE: Dictionary | None = None


@dataclass(frozen=True, slots=True)
class Kind:

    word: str
    title: str
    slug: str
    products: list[dict[str, Any]] = field(default_factory=list)
    narrowing: tuple[str, ...] = ()
    readings: tuple[str, ...] = ()
    """Інші ПРОЧИТАННЯ слова — назви вузлів з інших гілок дерева.

    «сир» лягає і на «Сири», і на «Сир кисломолочний»; «вода» — і на «Воду»,
    і на «Солодку воду». Вибрати між ними кодом нема чим: це різні наміри, а
    не різні точності. Тому список їде агентові, і саме він вирішує, брати
    перший чи спитати гостя."""
    also_in: dict[str, tuple[str, ...]] = field(default_factory=dict)
    """Артикул → назви ІНШИХ видів, у яких він теж лежить.

    Не прапорець «готове» навмисно. Рівнів обробки щонайменше три, і дерево
    їх розводить: сире («Свинина»), напівфабрикат («М'ясо для шашлику та
    барбекю» — 9 спільних позицій) і готове до їжі («Другі страви», де
    шашличні ковбаски гриль і нуль перетину зі «Свининою»). Мариновані
    реберця і шашлик з мангала — різні наміри, тож звести їх до одного слова
    означало б вирішити за гостя. Код везе факт, вибір лишається агентові."""

    @property
    def empty(self) -> bool:
        return not self.products


async def load_tree(mcp: SilpoMCP, *, branch_id: str) -> Dictionary | None:
    global _TREE
    if _TREE is not None:
        return _TREE
    try:
        nodes = await fetch_all(mcp, branch_id=branch_id)
    except TokenRejected:
        raise
    except MCPCallError as exc:
        log.warning("kinds.tree_unavailable", error=str(exc))
        return None
    if not nodes:
        return None
    _TREE = Dictionary(nodes)
    return _TREE


def forget_tree() -> None:
    global _TREE
    _TREE = None


def kind_of(tree: Dictionary, word: str) -> Node | None:
    match = tree.best(word)
    return match.node if match is not None and match.node.slug else None


def nodes_for(
    tree: Dictionary, word: str, chosen: Mapping[str, str] | None = None
) -> tuple[Node, ...]:
    answered = (chosen or {}).get(word)
    if answered:
        node = tree.by_slug(answered)
        if node is not None:
            return (node,)
    return tree.candidates(word, limit=MAX_READINGS)


async def narrow(
    mcp: SilpoMCP,
    words: Sequence[str],
    *,
    slot: dict[str, Any],
    branch_id: str | None,
    tree: Dictionary,
    limit: int = KIND_LIMIT,
    chosen: Mapping[str, str] | None = None,
) -> tuple[dict[str, Kind], int]:
    found: dict[str, Kind] = {}
    spent_ms = 0
    asked = 0
    for word in words:
        if len(found) >= MAX_KINDS:
            break
        readings = nodes_for(tree, word, chosen)
        if not readings or word in found:
            continue
        node = readings[0]
        products: list[dict[str, Any]] | None = None
        for probe in readings[:MAX_PROBES]:
            batch, spent = await fetch_listing(
                mcp, probe.slug, slot=slot, branch_id=branch_id, limit=limit, word=word
            )
            spent_ms += spent
            if batch:
                node, products = probe, batch
                break
            if batch is not None:
                products = []
        if products is None:
            continue
        also_in: dict[str, tuple[str, ...]] = {}
        mine = {str(p["externalProductId"]) for p in products}
        for sibling in tree.prepared_siblings(node.id):
            if asked >= MAX_PREPARED or not mine:
                break
            asked += 1
            listing, sibling_ms = await fetch_listing(
                mcp, sibling.slug, slot=slot, branch_id=branch_id, limit=limit
            )
            spent_ms += sibling_ms
            ids = {str(p["externalProductId"]) for p in listing or []}
            for pid in mine & ids:
                also_in[pid] = (*also_in.get(pid, ()), sibling.title)

        found[word] = Kind(
            word=word,
            title=node.title,
            slug=node.slug,
            products=products,
            narrowing=tuple(child.title for child in tree.children(node.id)),
            also_in=also_in,
            readings=tuple(other.title for other in readings if other.id != node.id),
        )
    return found, spent_ms


async def fetch_listing(
    mcp: SilpoMCP,
    slug: str,
    *,
    slot: dict[str, Any],
    branch_id: str | None,
    limit: int,
    word: str | None = None,
) -> tuple[list[dict[str, Any]] | None, int]:
    try:
        outcome = await mcp.call(
            TOOL,
            {
                "branchId": branch_id,
                "deliveryType": slot["deliveryType"],
                "timeslotStart": slot["start"],
                "timeslotEnd": slot["end"],
                "category": slug,
                "limit": limit,
                "inStock": True,
                "sortBy": "popularity",
            },
        )
    except TokenRejected:
        raise
    except MCPCallError as exc:
        log.warning("kinds.listing_failed", word=word, slug=slug, error=str(exc))
        return None, 0
    return (
        [
            product
            for product in outcome.payload_raw.get("products") or []
            if product.get("available") and product.get("externalProductId")
        ],
        outcome.duration_ms,
    )


def merge(
    candidates: dict[str, list[dict[str, Any]]], kinds: dict[str, Kind]
) -> tuple[int, list[str]]:
    added = 0
    empty: list[str] = []
    for word, kind in kinds.items():
        if kind.empty:
            empty.append(word)
            continue
        known = {str(p.get("externalProductId")) for p in candidates.get(word, [])}
        extra = [p for p in kind.products if str(p["externalProductId"]) not in known]
        if extra:
            candidates[word] = candidates.get(word, []) + extra
            added += len(extra)
    return added, empty


__all__ = [
    "KIND_LIMIT",
    "MAX_KINDS",
    "MAX_PREPARED",
    "MAX_PROBES",
    "MAX_READINGS",
    "TOOL",
    "Kind",
    "fetch_listing",
    "forget_tree",
    "kind_of",
    "load_tree",
    "merge",
    "narrow",
    "nodes_for",
]
