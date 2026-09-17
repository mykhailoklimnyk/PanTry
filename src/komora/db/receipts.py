from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from komora.core.quota import KYIV
from komora.db.pool import DictPool

DB_TIMEOUT = 2.0

OFFLINE = "offline"
ONLINE = "online"
SOURCES = (OFFLINE, ONLINE)

OVERLAP_DAYS = 3


@dataclass(frozen=True, slots=True)
class Mark:

    last_at: datetime | None
    read_at: datetime


_LOAD = """
select payload
  from receipts
 where account = %(account)s
   and source  = %(source)s
   and active
 order by bought_at desc
"""

_LOAD_SLOT_HOURS = """
select payload -> 'delivery' -> 'timeSlot' ->> 'from' as start
  from receipts
 where account = %(account)s
   and source  = 'online'
   and active
   and payload -> 'delivery' -> 'timeSlot' ->> 'from' is not null
"""

_SAVE = """
insert into receipts (account, source, ident, bought_at, payload)
values (%(account)s, %(source)s, %(ident)s, %(bought_at)s, %(payload)s)
on conflict (account, source, ident) do update
   set payload   = excluded.payload,
       bought_at = excluded.bought_at,
       active    = true,
       seen_at   = now()
"""

_MARK = """
select last_at, read_at
  from receipt_reads
 where account = %(account)s
   and source  = %(source)s
"""

_TOUCH = """
insert into receipt_reads (account, source, last_at)
values (%(account)s, %(source)s, %(last_at)s)
on conflict (account, source) do update
   set last_at = greatest(
           coalesce(receipt_reads.last_at, excluded.last_at),
           coalesce(excluded.last_at, receipt_reads.last_at)
       ),
       read_at = now()
"""


async def load(pool: DictPool, account: str, source: str) -> list[dict[str, Any]]:
    if not account or source not in SOURCES:
        return []
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        rows = await (await conn.execute(_LOAD, {"account": account, "source": source})).fetchall()
    return [row["payload"] for row in rows]


async def slot_hours(pool: DictPool, account: str) -> dict[int, int]:
    if not account:
        return {}
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        rows = await (await conn.execute(_LOAD_SLOT_HOURS, {"account": account})).fetchall()
    hours: dict[int, int] = {}
    for row in rows:
        start = row["start"]
        if not start:
            continue
        try:
            moment = datetime.fromisoformat(str(start))
        except ValueError:
            continue
        hour = moment.astimezone(KYIV).hour
        hours[hour] = hours.get(hour, 0) + 1
    return hours


async def save(
    pool: DictPool,
    account: str,
    source: str,
    orders: Iterable[tuple[str, datetime, dict[str, Any]]],
) -> int:
    if not account or source not in SOURCES:
        return 0
    rows = [
        {
            "account": account,
            "source": source,
            "ident": ident,
            "bought_at": bought_at,
            "payload": json.dumps(payload, ensure_ascii=False),
        }
        for ident, bought_at, payload in orders
        if ident
    ]
    if not rows:
        return 0
    async with pool.connection(timeout=DB_TIMEOUT) as conn, conn.cursor() as cur:
        await cur.executemany(_SAVE, rows)
    return len(rows)


async def mark(pool: DictPool, account: str, source: str) -> Mark | None:
    if not account or source not in SOURCES:
        return None
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        row = await (await conn.execute(_MARK, {"account": account, "source": source})).fetchone()
    if row is None:
        return None
    return Mark(last_at=row["last_at"], read_at=row["read_at"])


async def touch(pool: DictPool, account: str, source: str, *, last_at: datetime | None) -> None:
    if not account or source not in SOURCES:
        return
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        await conn.execute(_TOUCH, {"account": account, "source": source, "last_at": last_at})


async def forget(pool: DictPool, account: str) -> None:
    return None


__all__ = [
    "DB_TIMEOUT",
    "OFFLINE",
    "ONLINE",
    "OVERLAP_DAYS",
    "SOURCES",
    "Mark",
    "forget",
    "load",
    "mark",
    "save",
    "slot_hours",
    "touch",
]
