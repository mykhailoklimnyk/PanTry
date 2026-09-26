from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from komora.db.pool import DictPool

DB_TIMEOUT = 2.0

_LOAD = """
select kind, label, at_home, origin, why
  from wanted_items
 where account = %(account)s
 order by added_at
"""

_ADD = """
insert into wanted_items (account, kind, label, at_home, origin, why)
values (%(account)s, %(kind)s, %(label)s, %(at_home)s, %(origin)s, %(why)s)
on conflict (account, kind) do update
   set label = excluded.label, at_home = excluded.at_home
"""

_COMPOSE = """
insert into wanted_items (account, kind, label, at_home, origin, why)
values (%(account)s, %(kind)s, %(label)s, true, 'agent', %(why)s)
on conflict (account, kind) do nothing
"""

_DROP = """
delete from wanted_items
 where account = %(account)s and kind = any(%(kinds)s)
"""

_DROP_AGENT = """
delete from wanted_items
 where account = %(account)s and origin = 'agent' and kind = any(%(kinds)s)
"""


@dataclass(frozen=True, slots=True)
class Want:

    label: str
    at_home: bool = True
    origin: str = "guest"
    why: str | None = None


async def load(pool: DictPool, account: str) -> dict[str, Want]:
    if not account:
        return {}
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        rows = await (await conn.execute(_LOAD, {"account": account})).fetchall()
    return {
        row["kind"]: Want(
            row["label"], bool(row["at_home"]), row["origin"] or "guest", row["why"]
        )
        for row in rows
    }


async def add(pool: DictPool, account: str, kind: str, label: str, *, at_home: bool) -> None:
    if not account or not kind.strip() or not label.strip():
        return
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        await conn.execute(
            _ADD,
            {
                "account": account,
                "kind": kind,
                "label": label,
                "at_home": at_home,
                "origin": "guest",
                "why": None,
            },
        )


async def drop(pool: DictPool, account: str, kinds: Iterable[str]) -> int:
    keys = [kind for kind in kinds if kind.strip()]
    if not account or not keys:
        return 0
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        cursor = await conn.execute(_DROP, {"account": account, "kinds": keys})
        return cursor.rowcount


async def fill(pool: DictPool, account: str, rows: Mapping[str, Want]) -> int:
    payload = [
        {
            "account": account,
            "kind": kind,
            "label": row.label,
            "at_home": row.at_home,
            "origin": row.origin,
            "why": row.why,
        }
        for kind, row in rows.items()
        if kind.strip() and row.label.strip()
    ]
    if not account or not payload:
        return 0
    async with pool.connection(timeout=DB_TIMEOUT) as conn, conn.cursor() as cur:
        await cur.executemany(_ADD, payload)
    return len(payload)


async def compose(pool: DictPool, account: str, rows: Mapping[str, Want]) -> int:
    payload = [
        {"account": account, "kind": kind, "label": row.label, "why": row.why}
        for kind, row in rows.items()
        if kind.strip() and row.label.strip()
    ]
    if not account or not payload:
        return 0
    async with pool.connection(timeout=DB_TIMEOUT) as conn, conn.cursor() as cur:
        await cur.executemany(_COMPOSE, payload)
    return len(payload)


async def drop_agent(pool: DictPool, account: str, kinds: Iterable[str]) -> int:
    keys = [kind for kind in kinds if kind.strip()]
    if not account or not keys:
        return 0
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        cursor = await conn.execute(_DROP_AGENT, {"account": account, "kinds": keys})
        return cursor.rowcount


__all__ = ["Want", "add", "compose", "drop", "drop_agent", "fill", "load"]
