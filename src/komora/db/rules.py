from __future__ import annotations

from komora.core.rules import Rule
from komora.db.pool import DictPool

DB_TIMEOUT = 2.0

_LOAD = """
select rule_id, label, active
  from guest_rules
 where account = %(account)s
 order by added_at, rule_id
"""

_UPSERT = """
insert into guest_rules (account, rule_id, label, active)
values (%(account)s, %(rule_id)s, %(label)s, %(active)s)
on conflict (account, rule_id) do update
   set label   = excluded.label,
       active  = excluded.active,
       said_at = now()
"""

_TOGGLE = """
update guest_rules
   set active = %(active)s,
       said_at = now()
 where account = %(account)s
   and rule_id = %(rule_id)s
returning rule_id
"""

_DELETE = """
delete from guest_rules
 where account = %(account)s
   and rule_id = %(rule_id)s
returning rule_id
"""


async def load(pool: DictPool, account: str) -> list[Rule]:
    if not account:
        return []
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        rows = await (await conn.execute(_LOAD, {"account": account})).fetchall()
    return [
        Rule(id=row["rule_id"], label=row["label"], permanent=False, active=row["active"])
        for row in rows
    ]


async def save(pool: DictPool, account: str, rule: Rule) -> None:
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        await conn.execute(
            _UPSERT,
            {
                "account": account,
                "rule_id": rule.id,
                "label": rule.label,
                "active": rule.active,
            },
        )


async def toggle(pool: DictPool, account: str, rule_id: str, *, active: bool) -> bool:
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        row = await (
            await conn.execute(
                _TOGGLE, {"account": account, "rule_id": rule_id, "active": active}
            )
        ).fetchone()
    return row is not None


async def remove(pool: DictPool, account: str, rule_id: str) -> bool:
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        row = await (
            await conn.execute(_DELETE, {"account": account, "rule_id": rule_id})
        ).fetchone()
    return row is not None


__all__ = ["DB_TIMEOUT", "load", "remove", "save", "toggle"]
