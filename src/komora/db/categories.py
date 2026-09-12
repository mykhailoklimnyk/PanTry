from __future__ import annotations

from collections.abc import Sequence

from komora.core.dictionary import Node
from komora.db.pool import DictPool

_LOAD = """
select id, parent_id, slug, title
  from categories
 where gone_at is null
 order by id
"""

_UPSERT = """
insert into categories (id, parent_id, slug, title)
values (%(id)s, %(parent_id)s, %(slug)s, %(title)s)
on conflict (id) do update
   set parent_id = excluded.parent_id,
       slug      = excluded.slug,
       title     = excluded.title,
       last_seen = now(),
       gone_at   = null
"""

_MARK_GONE = """
update categories
   set gone_at = now()
 where gone_at is null
   and id <> all(%(ids)s)
"""


async def load(pool: DictPool) -> tuple[Node, ...]:
    async with pool.connection() as conn:
        rows = await (await conn.execute(_LOAD)).fetchall()
    return tuple(
        Node(
            id=row["id"],
            title=row["title"],
            parent_id=row["parent_id"],
            slug=row["slug"] or "",
        )
        for row in rows
    )


async def save(pool: DictPool, nodes: Sequence[Node]) -> None:
    if not nodes:
        raise ValueError("порожнє дерево категорій — не пишемо")

    rows = [
        {"id": n.id, "parent_id": n.parent_id, "slug": n.slug, "title": n.title}
        for n in nodes
    ]
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.executemany(_UPSERT, rows)
        await cur.execute(_MARK_GONE, {"ids": [n.id for n in nodes]})


__all__ = ["load", "save"]
