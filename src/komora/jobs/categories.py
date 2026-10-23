from __future__ import annotations

from typing import Any

from komora.core.dictionary import Node
from komora.logging import get_logger
from komora.mcp.client import SilpoMCP

log = get_logger(__name__)

TOOL = "silpo_get_categories"

PAGE = 1000

MAX_PAGES = 10


def parse_node(raw: dict[str, Any]) -> Node:
    return Node(
        id=raw["id"],
        title=raw["title"],
        parent_id=raw.get("parentId"),
        slug=raw.get("slug") or "",
    )


async def fetch_all(mcp: SilpoMCP, *, branch_id: str) -> tuple[Node, ...]:
    nodes: list[Node] = []
    total = 0
    for page in range(MAX_PAGES):
        outcome = await mcp.call(
            TOOL,
            {"branchId": branch_id, "limit": PAGE, "offset": page * PAGE},
        )
        chunk = outcome.payload_raw.get("categories") or []
        nodes.extend(parse_node(raw) for raw in chunk)
        total = (outcome.payload_raw.get("meta") or {}).get("total") or total
        if not chunk or len(nodes) >= total:
            break

    if total and len(nodes) != total:
        log.warning("categories.partial", got=len(nodes), total=total)
    return tuple(nodes)
