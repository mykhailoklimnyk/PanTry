from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from komora.core.bar import DrinkKind
from komora.core.said import BAR, GUEST, PANTRY, SOURCE_MANUAL, SOURCE_RECEIPTS
from komora.db.pool import DictPool

DB_TIMEOUT = 2.0

_LOAD = """
select kind, stocked_at
  from pantry_marks
 where account = %(account)s
"""

_LOAD_ITEMS = """
select kind, label
  from pantry_items
 where account = %(account)s and scope = %(scope)s
   and (%(origin)s::text is null or origin = %(origin)s)
 order by added_at
"""

_LOAD_CYCLES = """
select kind, days, said, from_kind
  from pantry_cycles
 where account = %(account)s
"""

_UPSERT_CYCLE = """
insert into pantry_cycles (account, kind, days, said, from_kind)
values (%(account)s, %(kind)s, %(days)s, %(said)s, %(from_kind)s)
on conflict (account, kind) do update
   set days      = excluded.days,
       said      = excluded.said,
       from_kind = excluded.from_kind,
       said_at   = now()
 where excluded.said or not pantry_cycles.said
"""

_DROP_CYCLE = """
delete from pantry_cycles
 where account = %(account)s and kind = %(kind)s
"""

_ADD_ITEM = """
insert into pantry_items (account, scope, kind, label, origin)
values (%(account)s, %(scope)s, %(kind)s, %(label)s, %(origin)s)
on conflict (account, scope, kind) do update
   set label  = excluded.label,
       origin = excluded.origin
"""

_DROP_ITEM = """
delete from pantry_items
 where account = %(account)s and scope = %(scope)s and kind = %(kind)s
"""

_LOAD_HIDDEN = """
select kind
  from pantry_hidden
 where account = %(account)s
 order by said_at
"""

_HIDE = """
insert into pantry_hidden (account, kind)
values (%(account)s, %(kind)s)
on conflict (account, kind) do nothing
"""

_UNHIDE = """
delete from pantry_hidden
 where account = %(account)s and kind = %(kind)s
"""

_LOAD_DRINKS = """
select kind, grp
  from pantry_drinks
 where account = %(account)s
"""

_UPSERT_DRINK = """
insert into pantry_drinks (account, kind, grp)
values (%(account)s, %(kind)s, %(grp)s)
on conflict (account, kind) do update
   set grp     = excluded.grp,
       said_at = now()
"""

_DROP_DRINK = """
delete from pantry_drinks
 where account = %(account)s and kind = %(kind)s
"""

_LOAD_SPLITS = """
select intent
  from pantry_splits
 where account = %(account)s and scope = %(scope)s
 order by said_at
"""

_SPLIT = """
insert into pantry_splits (account, scope, intent)
values (%(account)s, %(scope)s, %(intent)s)
on conflict (account, scope, intent) do nothing
"""

_UNSPLIT = """
delete from pantry_splits
 where account = %(account)s and scope = %(scope)s and intent = %(intent)s
"""

_LOAD_SOURCE = """
select mode
  from pantry_sources
 where account = %(account)s and scope = %(scope)s
"""

_UPSERT_SOURCE = """
insert into pantry_sources (account, scope, mode)
values (%(account)s, %(scope)s, %(mode)s)
on conflict (account, scope) do update
   set mode    = excluded.mode,
       said_at = now()
"""

_WIPE_ITEMS = """
delete from pantry_items
 where account = %(account)s and scope = %(scope)s
"""

_UPSERT = """
insert into pantry_marks (account, kind, stocked_at)
values (%(account)s, %(kind)s, %(stocked_at)s)
on conflict (account, kind) do update
   set stocked_at = excluded.stocked_at,
       said_at    = now()
"""


async def load(pool: DictPool, account: str) -> dict[str, datetime]:
    if not account:
        return {}
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        rows = await (await conn.execute(_LOAD, {"account": account})).fetchall()
    return {row["kind"]: row["stocked_at"] for row in rows}


async def save(pool: DictPool, account: str, marks: Mapping[str, datetime]) -> None:
    if not account or not marks:
        return
    rows = [
        {"account": account, "kind": kind, "stocked_at": stocked_at}
        for kind, stocked_at in marks.items()
        if kind.strip()
    ]
    if not rows:
        return
    async with pool.connection(timeout=DB_TIMEOUT) as conn, conn.cursor() as cur:
        await cur.executemany(_UPSERT, rows)


async def load_cycles(pool: DictPool, account: str) -> dict[str, int]:
    if not account:
        return {}
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        rows = await (await conn.execute(_LOAD_CYCLES, {"account": account})).fetchall()
    return {row["kind"]: row["days"] for row in rows}


async def load_cycle_sources(pool: DictPool, account: str) -> dict[str, str]:
    if not account:
        return {}
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        rows = await (await conn.execute(_LOAD_CYCLES, {"account": account})).fetchall()
    return {row["kind"]: row["from_kind"] for row in rows if not row["said"] and row["from_kind"]}


async def save_cycle(
    pool: DictPool,
    account: str,
    kind: str,
    days: int,
    *,
    said: bool = True,
    from_kind: str = "",
) -> None:
    if not account or not kind.strip() or days < 1:
        return
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        await conn.execute(
            _UPSERT_CYCLE,
            {
                "account": account,
                "kind": kind,
                "days": days,
                "said": said,
                "from_kind": from_kind or None,
            },
        )


async def drop_cycle(pool: DictPool, account: str, kind: str) -> None:
    if not account or not kind.strip():
        return
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        await conn.execute(_DROP_CYCLE, {"account": account, "kind": kind})


async def load_items(
    pool: DictPool, account: str, *, scope: str, origin: str | None = None
) -> dict[str, str]:
    if not account:
        return {}
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        rows = await (
            await conn.execute(_LOAD_ITEMS, {"account": account, "scope": scope, "origin": origin})
        ).fetchall()
    return {row["kind"]: row["label"] for row in rows}


async def add_item(
    pool: DictPool, account: str, kind: str, label: str, *, scope: str, origin: str = GUEST
) -> None:
    if not account or not kind.strip() or not label.strip():
        return
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        await conn.execute(
            _ADD_ITEM,
            {"account": account, "scope": scope, "kind": kind, "label": label, "origin": origin},
        )


async def add_items(
    pool: DictPool, account: str, rows: Mapping[str, str], *, scope: str, origin: str
) -> int:
    if not account or not rows:
        return 0
    payload = [
        {"account": account, "scope": scope, "kind": kind, "label": label, "origin": origin}
        for kind, label in rows.items()
        if kind.strip() and label.strip()
    ]
    if not payload:
        return 0
    async with pool.connection(timeout=DB_TIMEOUT) as conn, conn.cursor() as cur:
        await cur.executemany(_ADD_ITEM, payload)
    return len(payload)


async def drop_item(pool: DictPool, account: str, kind: str, *, scope: str) -> None:
    if not account or not kind.strip():
        return
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        await conn.execute(_DROP_ITEM, {"account": account, "scope": scope, "kind": kind})


async def load_source(pool: DictPool, account: str, scope: str) -> str:
    if not account:
        return SOURCE_RECEIPTS
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        row = await (
            await conn.execute(_LOAD_SOURCE, {"account": account, "scope": scope})
        ).fetchone()
    return SOURCE_MANUAL if row and row["mode"] == SOURCE_MANUAL else SOURCE_RECEIPTS


async def save_source(pool: DictPool, account: str, scope: str, mode: str) -> None:
    if not account or mode not in (SOURCE_RECEIPTS, SOURCE_MANUAL):
        return
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        await conn.execute(_UPSERT_SOURCE, {"account": account, "scope": scope, "mode": mode})


async def wipe_items(pool: DictPool, account: str, *, scope: str) -> int:
    if not account:
        return 0
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        cursor = await conn.execute(_WIPE_ITEMS, {"account": account, "scope": scope})
        return cursor.rowcount


async def load_hidden(pool: DictPool, account: str) -> list[str]:
    if not account:
        return []
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        rows = await (await conn.execute(_LOAD_HIDDEN, {"account": account})).fetchall()
    return [row["kind"] for row in rows]


async def hide(pool: DictPool, account: str, kind: str) -> None:
    if not account or not kind.strip():
        return
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        await conn.execute(_HIDE, {"account": account, "kind": kind})


async def unhide(pool: DictPool, account: str, kind: str) -> None:
    if not account or not kind.strip():
        return
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        await conn.execute(_UNHIDE, {"account": account, "kind": kind})


async def load_drinks(pool: DictPool, account: str) -> dict[str, DrinkKind]:
    if not account:
        return {}
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        rows = await (await conn.execute(_LOAD_DRINKS, {"account": account})).fetchall()
    known = {str(group) for group in DrinkKind}
    return {row["kind"]: DrinkKind(row["grp"]) for row in rows if row["grp"] in known}


async def save_drink(pool: DictPool, account: str, kind: str, group: str) -> None:
    if not account or not kind.strip() or group not in {str(known) for known in DrinkKind}:
        return
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        await conn.execute(_UPSERT_DRINK, {"account": account, "kind": kind, "grp": group})


async def drop_drink(pool: DictPool, account: str, kind: str) -> None:
    if not account or not kind.strip():
        return
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        await conn.execute(_DROP_DRINK, {"account": account, "kind": kind})


async def load_splits(pool: DictPool, account: str, *, scope: str) -> list[str]:
    if not account:
        return []
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        rows = await (
            await conn.execute(_LOAD_SPLITS, {"account": account, "scope": scope})
        ).fetchall()
    return [row["intent"] for row in rows]


async def split(pool: DictPool, account: str, intent: str, *, scope: str) -> None:
    if not account or not intent.strip():
        return
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        await conn.execute(_SPLIT, {"account": account, "scope": scope, "intent": intent})


async def unsplit(pool: DictPool, account: str, intent: str, *, scope: str) -> None:
    if not account or not intent.strip():
        return
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        await conn.execute(_UNSPLIT, {"account": account, "scope": scope, "intent": intent})


__all__ = [
    "BAR",
    "DB_TIMEOUT",
    "PANTRY",
    "add_item",
    "add_items",
    "drop_cycle",
    "drop_drink",
    "drop_item",
    "hide",
    "load",
    "load_cycle_sources",
    "load_cycles",
    "load_drinks",
    "load_hidden",
    "load_items",
    "load_source",
    "load_splits",
    "save",
    "save_cycle",
    "save_drink",
    "save_source",
    "split",
    "unhide",
    "unsplit",
    "wipe_items",
]
