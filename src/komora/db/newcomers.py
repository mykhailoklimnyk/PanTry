from __future__ import annotations

import hashlib

from komora.db.pool import DictPool

DB_TIMEOUT = 2.0

GREET_LIMIT = 10

_ARRIVE = """
insert into newcomers (account) values (%(account)s)
on conflict (account) do nothing
returning account
"""

_POSITION = """
select count(*) as position
  from newcomers
 where first_seen <= (select first_seen from newcomers where account = %(account)s)
"""

_GREET = """
update newcomers
   set greeted_at = now()
 where account = %(account)s
   and greeted_at is null
returning account
"""


def fingerprint(profile_id: str) -> str:
    return hashlib.sha256(profile_id.encode("utf-8")).hexdigest()


async def arrive(pool: DictPool, *, account: str) -> int | None:
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        inserted = await (await conn.execute(_ARRIVE, {"account": account})).fetchone()
        if inserted is None:
            return None
        row = await (await conn.execute(_POSITION, {"account": account})).fetchone()
    return int(row["position"]) if row else None


async def claim_greeting(pool: DictPool, *, account: str) -> int | None:
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        claimed = await (await conn.execute(_GREET, {"account": account})).fetchone()
        if claimed is None:
            return None
        row = await (await conn.execute(_POSITION, {"account": account})).fetchone()
    if row is None:
        return None
    position = int(row["position"])
    return position if position <= GREET_LIMIT else None


__all__ = ["DB_TIMEOUT", "GREET_LIMIT", "arrive", "claim_greeting", "fingerprint"]
