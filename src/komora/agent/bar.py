from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime

from komora.agent.basket import (
    MIN_RECEIPTS,
    AssemblyError,
    HistoryItem,
    Naming,
    Receipts,
    history_kinds,
    intent_names,
    is_service_item,
    kind_key,
    load_history,
    manual_key,
    same_kind,
    slots_query,
)
from komora.agent.place import resolve as resolve_place
from komora.api.schemas import Bar, BarItem, ProductPick
from komora.config import Settings
from komora.config import settings as _default_settings
from komora.core import bar as core
from komora.core.location import HOME_DELIVERY, Location
from komora.core.said import SOURCE_MANUAL, SOURCE_RECEIPTS, Said
from komora.db import catalog as catalog_map
from komora.db import categories as categories_store
from komora.db.pool import DictPool
from komora.logging import get_logger
from komora.mcp.client import SilpoMCP

log = get_logger(__name__)


def kinds_of(
    goods: list[HistoryItem],
    names: dict[str, Naming],
    *,
    drinks: Mapping[str, core.DrinkKind] | None = None,
    tree: Mapping[str, core.Shelved] | None = None,
    nodes: Mapping[str, frozenset[str]] | None = None,
) -> tuple[core.Kind, ...]:
    said = drinks or {}
    shelves, where = tree or {}, nodes or {}
    grouped: dict[str, list[tuple[Naming, HistoryItem]]] = {}
    shelf: dict[str, tuple[core.DrinkKind, bool, str]] = {}
    for item in goods:
        naming = names.get(kind_key(item.name))
        if naming is None:
            continue
        from_tree = core.shelved(item.lager_id, where, shelves)
        label = from_tree.label if from_tree is not None else naming.label
        group, by_guest = core.said_group(
            manual_key(label),
            from_tree.group if from_tree is not None else naming.drink,
            said,
        )
        if group is None:
            continue
        key = f"{group}|{label}"
        shelf[key] = (group, by_guest, label)
        grouped.setdefault(key, []).append((naming, item))
    kinds = []
    for key, pairs in grouped.items():
        naming = pairs[0][0]
        group, by_guest, label = shelf[key]
        kinds.append(
            core.Kind(
                key=key,
                label=label,
                group=group,
                group_said=by_guest,
                bottles=tuple(
                    core.Bottle(
                        article=item.lager_id,
                        name=item.name,
                        receipts=item.receipts,
                        price=item.price,
                        last_at=max(item.moments) if item.moments else None,
                        pack=item.unit,
                    )
                    for _, item in pairs
                ),
            )
        )
    return tuple(kinds)


def _line(row: core.Row) -> BarItem:
    usual = (
        ProductPick(
            external_product_id=row.usual.article,
            name=row.usual.name,
            share=row.share,
            price=row.price,
            pack=row.usual.pack,
        )
        if row.usual is not None and row.price is not None
        else None
    )
    return BarItem(
        id=row.id,
        label=row.label,
        kind=row.group,
        times=row.times,
        days_since=row.days_since,
        source=SOURCE_MANUAL if row.said else SOURCE_RECEIPTS,
        kind_said=row.group_said,
        usual=usual,
        price_from=row.fork.low if row.fork else None,
        price_to=row.fork.high if row.fork else None,
        fork_note=row.fork_note,
    )


def report(
    shelf: core.Shelf,
    *,
    receipts: int,
    kinds: int,
    named: int,
    orders: int = 0,
    source: str = SOURCE_RECEIPTS,
    unlisted: int = 0,
) -> Bar:
    return Bar(
        items=[_line(row) for row in shelf.rows],
        receipts=receipts,
        orders=orders,
        kinds=kinds,
        named=named,
        tracked_from=MIN_RECEIPTS,
        dropped=shelf.dropped,
        source=source,
        unlisted=unlisted,
    )


def merge_said(
    shelf: core.Shelf,
    manual: Mapping[str, str],
    *,
    names: dict[str, Naming],
    source: str,
    drinks: Mapping[str, core.DrinkKind] | None = None,
) -> tuple[core.Shelf, int]:
    if not manual and source != SOURCE_MANUAL:
        return shelf, 0
    said: list[core.Row] = []
    covered: set[str] = set()
    for label in manual.values():
        name = label.strip()
        if not name:
            continue
        match = next((row for row in shelf.rows if same_kind(name, row.label)), None)
        if match is not None:
            covered.add(match.id)
            continue
        if any(same_kind(name, row.label) for row in said):
            continue
        naming = names.get(kind_key(name))
        group, by_guest = core.said_group(
            manual_key(name), naming.drink if naming is not None else None, drinks or {}
        )
        said.append(core.said_row(manual_key(name), name, group=group, group_said=by_guest))
    if source != SOURCE_MANUAL:
        return core.Shelf((*shelf.rows, *said), shelf.dropped), 0
    kept = [row for row in shelf.rows if row.id in covered]
    return core.Shelf((*kept, *said), shelf.dropped), len(shelf.rows) - len(kept)


async def bar_live(
    mcp: SilpoMCP,
    *,
    llm: object | None = None,
    settings: Settings | None = None,
    now: datetime | None = None,
    place: Location | None = None,
    pool: DictPool | None = None,
    account: str = "",
    said: Said | None = None,
    receipts: Receipts | None = None,
) -> Bar:
    words = said or Said()
    cfg = settings if settings is not None else _default_settings
    moment = now or datetime.now(UTC)
    if receipts is not None:
        history, counted, orders = receipts.history, receipts.count, receipts.orders
    else:
        where = place if place is not None else await resolve_place(mcp, settings=cfg)
        branch_id = where.branch_for(HOME_DELIVERY) or cfg.branch_id
        outcome = await mcp.call(
            "silpo_get_time_slots",
            slots_query(branch_id, HOME_DELIVERY, 5, since=moment),
        )
        slots = outcome.payload_raw.get("slots") or []
        slot = next((s for s in slots if s.get("available")), slots[0] if slots else None)
        if slot is None:
            raise AssemblyError("немає жодного слота — без нього історія чеків не читається")
        history, counted, _, _, online = await load_history(
            mcp, slot, branch_id, now=moment, pool=pool, account=account
        )
        orders = online.count
    goods = [item for item in history if not is_service_item(item.name)]
    kinds = history_kinds(goods)
    tracked = [kind for kind in kinds if kind.receipts >= MIN_RECEIPTS]
    said_labels = [label.strip() for label in words.listed.values() if label.strip()]
    names = await intent_names(
        llm,
        [kind.name for kind in tracked] + said_labels,
        pool=pool,
        need_drink=True,
    )
    tree, nodes = {}, {}
    if pool is not None:
        try:
            nodes = await catalog_map.load(pool, [item.lager_id for item in goods if item.lager_id])
            tree = core.shelf_map(await categories_store.load(pool))
        except Exception as exc:
            log.warning("bar.tree_unreadable", error=str(exc))
    shelf, unlisted = merge_said(
        core.rows(kinds_of(goods, names, drinks=words.drinks, tree=tree, nodes=nodes), now=moment),
        words.listed,
        names=names,
        source=words.source,
        drinks=words.drinks,
    )
    return report(
        shelf,
        receipts=counted,
        orders=orders,
        kinds=len(kinds),
        named=sum(1 for kind in tracked if kind_key(kind.name) in names),
        source=words.source,
        unlisted=unlisted,
    )


__all__ = ["bar_live", "kinds_of", "merge_said", "report"]
