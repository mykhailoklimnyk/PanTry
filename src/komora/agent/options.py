from __future__ import annotations

from typing import Any

from komora.agent.basket import (
    SEARCH_LIMIT,
    Assembled,
    PlanLine,
    name_proves_kind,
    search_products,
    swap_option,
)
from komora.agent.cart import CartRun
from komora.agent.kinds import KIND_LIMIT, fetch_listing, load_tree, nodes_for
from komora.api.schemas import SwapOption
from komora.core.dictionary import Node
from komora.logging import get_logger

log = get_logger(__name__)


def line_of(run: Assembled | CartRun, article: str) -> PlanLine | None:
    plan = run.assembled if isinstance(run, CartRun) else run
    return next(
        (
            line
            for line in plan.lines
            if str(line.product.get("externalProductId")) == str(article)
        ),
        None,
    )


_option = swap_option


async def _kind_listing(
    mcp: Any, line: PlanLine, *, slot: dict[str, Any], branch_id: Any, limit: int
) -> tuple[Node | None, list[dict[str, Any]]]:
    tree = await load_tree(mcp, branch_id=str(branch_id or ""))
    if tree is None:
        return None, []
    for node in nodes_for(tree, line.intent):
        batch, _ = await fetch_listing(
            mcp, node.slug, slot=slot, branch_id=branch_id, limit=limit, word=line.intent
        )
        if batch:
            return node, batch
    return None, []


def _same_kind(
    product: dict[str, Any], line: PlanLine, known: frozenset[str]
) -> bool | None:
    if not known:
        return None
    if str(product["externalProductId"]) in known:
        return True
    return name_proves_kind(
        line.intent, str(product["name"]), like=str(line.product.get("name") or "")
    )


async def options_for(
    mcp: Any,
    run: Assembled | CartRun,
    *,
    article: str,
    query: str | None = None,
    limit: int = KIND_LIMIT,
) -> list[SwapOption]:
    plan = run.assembled if isinstance(run, CartRun) else run
    line = line_of(run, article)
    if line is None:
        return []
    branch_id = line.product.get("branchId")
    slot = plan.slot

    if query and query.strip():
        wanted = query.strip()
        found, _ = await search_products(mcp, [wanted], slot, branch_id)
        products = [
            p
            for p in (found.get(wanted) or [])[:limit]
            if str(p["externalProductId"]) != article
        ]
        if not products:
            return []
        node, listing = await _kind_listing(
            mcp, line, slot=slot, branch_id=branch_id, limit=limit
        )
        known = frozenset(str(p["externalProductId"]) for p in listing)
        judged = [(p, _same_kind(p, line, known)) for p in products]
        foreign = sum(1 for _, verdict in judged if verdict is False)
        if foreign:
            log.info("swaps.other_kind_offered", intent=line.intent, count=foreign)
        return [
            _option(
                p,
                same_kind=verdict,
                kind=node.title if node is not None else None,
            )
            for p, verdict in judged
        ]

    node, products = await _kind_listing(
        mcp, line, slot=slot, branch_id=branch_id, limit=limit
    )
    if products and node is not None:
        return [
            _option(p, same_kind=True, kind=node.title)
            for p in products
            if str(p["externalProductId"]) != article
        ]

    found, _ = await search_products(mcp, [line.intent], slot, branch_id)
    fallback = (found.get(line.intent) or [])[:SEARCH_LIMIT]
    return [_option(p) for p in fallback if str(p["externalProductId"]) != article]


__all__ = ["line_of", "options_for"]
