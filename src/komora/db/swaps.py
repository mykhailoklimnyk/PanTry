from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass

from komora.db.pool import DictPool

DB_TIMEOUT = 2.0

_LOAD = """
select kind, label, chain
  from saved_swaps
 where account = %(account)s
 order by saved_at
"""

_UPSERT = """
insert into saved_swaps (account, kind, label, chain)
values (%(account)s, %(kind)s, %(label)s, %(chain)s)
on conflict (account, kind) do update
   set label = excluded.label,
       chain = excluded.chain,
       saved_at = now()
"""

_DROP = """
delete from saved_swaps
 where account = %(account)s and kind = %(kind)s
"""


@dataclass(frozen=True, slots=True)
class Link:

    article: str
    name: str


@dataclass(frozen=True, slots=True)
class Saved:

    label: str
    links: tuple[Link, ...]

    @property
    def articles(self) -> tuple[str, ...]:
        return tuple(link.article for link in self.links)


def _links(raw: object) -> tuple[Link, ...]:
    data = json.loads(raw) if isinstance(raw, str | bytes) else raw
    if not isinstance(data, list):
        return ()
    return tuple(
        Link(str(item["id"]), str(item.get("name") or ""))
        for item in data
        if isinstance(item, dict) and item.get("id")
    )


async def load(pool: DictPool, account: str) -> dict[str, Saved]:
    if not account:
        return {}
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        rows = await (await conn.execute(_LOAD, {"account": account})).fetchall()
    return {row["kind"]: Saved(row["label"], _links(row["chain"])) for row in rows}


async def save(pool: DictPool, account: str, rows: Mapping[str, Saved]) -> int:
    payload = [
        {
            "account": account,
            "kind": kind,
            "label": row.label,
            "chain": json.dumps(
                [{"id": link.article, "name": link.name} for link in row.links],
                ensure_ascii=False,
            ),
        }
        for kind, row in rows.items()
        if kind.strip() and row.links
    ]
    if not account or not payload:
        return 0
    async with pool.connection(timeout=DB_TIMEOUT) as conn, conn.cursor() as cur:
        await cur.executemany(_UPSERT, payload)
    return len(payload)


async def drop(pool: DictPool, account: str, kind: str) -> int:
    if not account or not kind.strip():
        return 0
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        cursor = await conn.execute(_DROP, {"account": account, "kind": kind})
        return cursor.rowcount


__all__ = ["Link", "Saved", "drop", "load", "save"]
