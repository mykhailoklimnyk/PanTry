from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal

from komora.db.pool import DictPool


@dataclass(frozen=True, slots=True)
class Card:

    name: str
    name_key: str
    product_id: str
    slug: str
    company_id: str
    weighted: bool | None = None
    step: Decimal | None = None
    ratio: str | None = None

_LOAD = """
select article, nodes
  from catalog_nodes
 where article = any(%(articles)s)
"""

_UPSERT = """
insert into catalog_nodes (
    article, nodes, name, name_key,
    product_id, slug, company_id, weighted, sale_step, display_ratio
)
values (
    %(article)s, %(nodes)s, %(name)s, %(name_key)s,
    %(product_id)s, %(slug)s, %(company_id)s, %(weighted)s, %(step)s, %(ratio)s
)
-- Свіжий обхід перезаписує картку, а `coalesce` береже вже записане від
-- дірки в сторінці: філія, яка не віддала назви, не має права стерти ту, що
-- вже лежить. Що філії не сперечаються між собою -- виміряно (31.08, сім
-- полів на 391 001 рядку, розбіжність нуль), тож «останній обхід виграє»
-- тут не тай-брейк, а просто свіжість.
on conflict (article) do update
   set nodes         = excluded.nodes,
       name          = coalesce(excluded.name, catalog_nodes.name),
       name_key      = coalesce(excluded.name_key, catalog_nodes.name_key),
       product_id    = coalesce(excluded.product_id, catalog_nodes.product_id),
       slug          = coalesce(excluded.slug, catalog_nodes.slug),
       company_id    = coalesce(excluded.company_id, catalog_nodes.company_id),
       weighted      = coalesce(excluded.weighted, catalog_nodes.weighted),
       sale_step     = coalesce(excluded.sale_step, catalog_nodes.sale_step),
       display_ratio = coalesce(excluded.display_ratio, catalog_nodes.display_ratio),
       last_seen     = now(),
       gone_at       = null
"""

_BY_NAME = """
select name_key, min(article) as article
  from catalog_nodes
 where name_key = any(%(keys)s)
 group by name_key
"""

_BY_PRODUCT = """
select distinct on (product_id)
       product_id, article, display_ratio as ratio, weighted, sale_step as step
  from catalog_nodes
 where product_id = any(%(ids)s)
 order by product_id, article
"""

_MARK_GONE = """
update catalog_nodes
   set gone_at = now()
 where gone_at is null
   and last_seen < %(since)s
"""

_SIZE = "select count(*) as n from catalog_nodes"


DB_TIMEOUT = 2.0


async def load(pool: DictPool, articles: list[str]) -> dict[str, frozenset[str]]:
    if not articles:
        return {}
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        rows = await (await conn.execute(_LOAD, {"articles": articles})).fetchall()
    return {row["article"]: frozenset(row["nodes"] or ()) for row in rows}


async def articles_by_name(pool: DictPool, keys: list[str]) -> dict[str, str]:
    if not keys:
        return {}
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        rows = await (await conn.execute(_BY_NAME, {"keys": keys})).fetchall()
    return {row["name_key"]: row["article"] for row in rows}


async def cards_by_product(pool: DictPool, ids: list[str]) -> dict[str, dict[str, object]]:
    if not ids:
        return {}
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        rows = await (await conn.execute(_BY_PRODUCT, {"ids": ids})).fetchall()
    return {
        row["product_id"]: {
            "article": row["article"],
            "ratio": row["ratio"],
            "weighted": row["weighted"],
            "step": row["step"],
        }
        for row in rows
    }


async def size(pool: DictPool) -> int:
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        row = await (await conn.execute(_SIZE)).fetchone()
    return int(row["n"]) if row else 0


async def save(
    pool: DictPool,
    found: Mapping[str, frozenset[str]],
    *,
    since: object,
    names: Mapping[str, Card] | None = None,
) -> int:
    if not found:
        raise ValueError("порожній обхід каталогу -- не пишемо")

    def row(article: str, nodes: frozenset[str]) -> dict[str, object]:
        card = (names or {}).get(article)
        return {
            "article": article,
            "nodes": sorted(nodes),
            "name": card.name if card else None,
            "name_key": card.name_key if card else None,
            "product_id": card.product_id if card else None,
            "slug": card.slug if card else None,
            "company_id": card.company_id if card else None,
            "weighted": card.weighted if card else None,
            "step": card.step if card else None,
            "ratio": card.ratio if card else None,
        }

    rows = [row(a, n) for a, n in found.items()]
    async with pool.connection() as conn, conn.cursor() as cur:
        await cur.executemany(_UPSERT, rows)
        await cur.execute(_MARK_GONE, {"since": since})
        return len(rows)


__all__ = ["Card", "articles_by_name", "cards_by_product", "load", "save", "size"]
