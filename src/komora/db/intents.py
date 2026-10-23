from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence

from komora.db.pool import DictPool

DB_TIMEOUT = 2.0

_LOAD = """
select name_sha, intent, subtype, drink
  from intent_names
 where name_sha = any(%(shas)s)
"""

_UPSERT = """
insert into intent_names (name_sha, intent, subtype, drink)
values (%(name_sha)s, %(intent)s, %(subtype)s, %(drink)s)
on conflict (name_sha) do update
   set intent    = excluded.intent,
       subtype   = excluded.subtype,
       drink     = excluded.drink,
       last_seen = now()
"""


def fingerprint(name: str) -> str:
    return hashlib.sha256(" ".join(name.split()).casefold().encode()).hexdigest()


async def load(
    pool: DictPool, names: Sequence[str]
) -> dict[str, tuple[str, str | None, str | None]]:
    if not names:
        return {}
    by_sha = {fingerprint(name): name for name in names}
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        rows = await (await conn.execute(_LOAD, {"shas": list(by_sha)})).fetchall()
    return {
        by_sha[row["name_sha"]]: (row["intent"], row["subtype"], row["drink"])
        for row in rows
        if row["name_sha"] in by_sha
    }


async def save(
    pool: DictPool, named: Mapping[str, tuple[str, str | None, str | None]]
) -> None:
    rows = [
        {"name_sha": fingerprint(name), "intent": intent, "subtype": subtype, "drink": drink}
        for name, (intent, subtype, drink) in named.items()
        if name.strip() and intent.strip()
    ]
    if not rows:
        return
    async with pool.connection(timeout=DB_TIMEOUT) as conn, conn.cursor() as cur:
        await cur.executemany(_UPSERT, rows)


__all__ = ["fingerprint", "load", "save"]
