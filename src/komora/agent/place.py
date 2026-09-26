from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from komora.config import Settings
from komora.config import settings as _default_settings
from komora.core.location import (
    HOME_DELIVERY,
    Address,
    Location,
    choose_address,
    decide,
    label_of,
)
from komora.logging import get_logger
from komora.mcp.client import MCPCallError, SilpoMCP, TokenRejected

log = get_logger(__name__)

ADDRESSES_TOOL = "silpo_get_my_delivery_addresses"
SEARCH_TOOL = "silpo_find_address"
TYPES_TOOL = "silpo_get_available_delivery_types"
BRANCHES_TOOL = "silpo_list_branches"

CartBranch = Callable[[], Awaitable[str | None]]


def _coordinates(row: dict[str, Any]) -> tuple[float, float] | None:
    lat, lon = row.get("latitude"), row.get("longitude")
    if lat is None or lon is None:
        return None
    try:
        return float(lat), float(lon)
    except TypeError, ValueError:
        return None


def address_from_saved(row: dict[str, Any]) -> Address | None:
    point = _coordinates(row)
    if point is None:
        return None
    label = label_of(
        city=row.get("city"),
        street=row.get("street"),
        building=row.get("building"),
        apartment=row.get("apartment"),
    )
    return Address(
        label=label or "адреса без назви",
        latitude=point[0],
        longitude=point[1],
        id=str(row["id"]) if row.get("id") else None,
        tag=str(row["tag"]) if row.get("tag") else None,
        kind="flat" if row.get("apartment") else "house",
        city=str(row["city"]) if row.get("city") else None,
        street=str(row["street"]) if row.get("street") else None,
        house=str(row["building"]) if row.get("building") else None,
    )


def address_from_found(row: dict[str, Any]) -> Address | None:
    point = _coordinates(row)
    if point is None:
        return None
    ready = str(row.get("address") or "").strip()
    label = ready or label_of(
        city=row.get("city"),
        street=row.get("street"),
        building=row.get("houseNumber"),
    )
    if not label:
        return None
    return Address(
        label=label,
        latitude=point[0],
        longitude=point[1],
        kind=str(row["addressType"]) if row.get("addressType") else None,
        city=str(row["city"]) if row.get("city") else None,
        street=str(row["street"]) if row.get("street") else None,
        house=str(row["houseNumber"]) if row.get("houseNumber") else None,
        confirmed=bool(row.get("houseNumber")),
    )


async def saved_addresses(mcp: SilpoMCP) -> list[Address]:
    try:
        outcome = await mcp.call(ADDRESSES_TOOL)
    except TokenRejected:
        raise
    except MCPCallError as exc:
        log.warning("place.saved_failed", error=str(exc)[:120])
        return []
    rows = outcome.payload_raw.get("addresses") or []
    found = [address_from_saved(row) for row in rows if isinstance(row, dict)]
    return [address for address in found if address is not None]


async def search_addresses(mcp: SilpoMCP, text: str) -> list[Address]:
    query = text.strip()
    if not query:
        return []
    outcome = await mcp.call(SEARCH_TOOL, {"address": query})
    rows = outcome.payload_raw.get("addresses") or []
    found = [address_from_found(row) for row in rows if isinstance(row, dict)]
    return [address for address in found if address is not None]


async def branches_at(
    mcp: SilpoMCP, address: Address
) -> tuple[dict[str, str], frozenset[str] | None]:
    try:
        outcome = await mcp.call(
            TYPES_TOOL,
            {"latitude": address.latitude, "longitude": address.longitude},
        )
    except TokenRejected:
        raise
    except MCPCallError as exc:
        log.warning("place.types_failed", error=str(exc)[:120])
        return {}, None

    branches: dict[str, str] = {}
    offered: set[str] = set()
    for option in outcome.payload_raw.get("options") or []:
        if not isinstance(option, dict):
            continue
        type_id = option.get("deliveryType")
        if not type_id:
            continue
        offered.add(str(type_id))
        if option.get("branchId"):
            branches[str(type_id)] = str(option["branchId"])
    return branches, frozenset(offered)


async def resolve(
    mcp: SilpoMCP,
    *,
    settings: Settings | None = None,
    address: Address | None = None,
    saved: Sequence[Address] | None = None,
    preferred_id: str | None = None,
    cart_branch: str | None = None,
    ask_cart: CartBranch | None = None,
) -> Location:
    cfg = settings if settings is not None else _default_settings

    chosen = address
    if chosen is None:
        rows = saved if saved is not None else await saved_addresses(mcp)
        chosen = choose_address(rows, preferred_id=preferred_id)

    branches: dict[str, str] = {}
    offered: frozenset[str] | None = None
    if chosen is not None:
        branches, offered = await branches_at(mcp, chosen)

    from_address = branches.get(HOME_DELIVERY)
    if not from_address and cart_branch is None and ask_cart is not None:
        cart_branch = await ask_cart()

    branch_id, source = decide(
        from_address=from_address,
        from_cart=cart_branch,
        from_config=cfg.branch_id,
    )
    location = Location(
        branch_id=branch_id,
        source=source,
        address=chosen,
        branches=branches,
        offered=offered,
    )
    log.info("place.resolved", source=source.value, has_address=chosen is not None)
    return location


BRANCH_PAGE = 500

MAX_BRANCH_PAGES = 10


async def all_branches(mcp: SilpoMCP) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen = 0
    total = 0
    for _ in range(MAX_BRANCH_PAGES):
        outcome = await mcp.call(BRANCHES_TOOL, {"limit": BRANCH_PAGE, "offset": seen})
        got = outcome.payload_raw.get("branches") or []
        seen += len(got)
        rows.extend(row for row in got if isinstance(row, dict))
        total = (outcome.payload_raw.get("meta") or {}).get("total") or total
        if not got or seen >= total:
            break
    if total and seen < total:
        log.warning("place.branches_capped", got=seen, total=total)
    return rows


_DIRECTORY: dict[str, str] | None = None


async def branch_label(mcp: SilpoMCP, branch_id: str | None) -> str | None:
    global _DIRECTORY
    if not branch_id:
        return None
    if _DIRECTORY is None:
        try:
            rows = await all_branches(mcp)
        except TokenRejected:
            raise
        except MCPCallError as exc:
            log.warning("place.branches_failed", error=str(exc)[:120])
            return None
        directory: dict[str, str] = {}
        for row in rows:
            if not row.get("branchId"):
                continue
            label = ", ".join(
                part
                for part in (str(row.get("city") or ""), str(row.get("address") or ""))
                if part.strip()
            )
            if label:
                directory[str(row["branchId"])] = label
        _DIRECTORY = directory
    return _DIRECTORY.get(branch_id)


def forget_directory() -> None:
    global _DIRECTORY
    _DIRECTORY = None


__all__ = [
    "ADDRESSES_TOOL",
    "BRANCHES_TOOL",
    "BRANCH_PAGE",
    "SEARCH_TOOL",
    "TYPES_TOOL",
    "CartBranch",
    "address_from_found",
    "address_from_saved",
    "all_branches",
    "branch_label",
    "branches_at",
    "forget_directory",
    "resolve",
    "saved_addresses",
    "search_addresses",
]
