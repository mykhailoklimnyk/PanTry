from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from komora.db.pool import DictPool

DB_TIMEOUT = 2.0

_RECORD = """
insert into agent_runs (
    started_at, finished_at, account, owner, kind,
    model, tokens_in, tokens_out, cost_usd, duration_ms, ok, payer
)
values (
    %(started_at)s, now(), %(account)s, %(owner)s, %(kind)s,
    %(model)s, %(tokens_in)s, %(tokens_out)s, %(cost_usd)s, %(duration_ms)s, %(ok)s,
    %(payer)s
)
"""

_COUNTERS = """
select
    count(*) filter (
        where started_at >= %(since)s
          and kind = any(%(kinds)s)
          and (
              (%(account)s <> '' and account = %(account)s)
              or (%(account)s = '' and owner = %(owner)s)
          )
    )                                                          as day_runs,
    coalesce(sum(cost_usd) filter (
        where started_at >= %(since)s and kind <> all(%(offbudget)s)
          and payer = 'project'
    ), 0)                                                      as day_usd,
    coalesce(sum(cost_usd) filter (
        where started_at >= %(since)s and kind = any(%(offbudget)s)
          and payer = 'project'
    ), 0)                                                      as day_offbudget_usd,
    coalesce(sum(cost_usd) filter (
        where started_at >= %(since)s and payer = 'guest'
    ), 0)                                                      as day_guest_usd,
    coalesce(sum(cost_usd) filter (where payer = 'project'), 0) as total_usd,
    count(*) filter (where cost_usd is null)                   as unpriced,
    count(*) filter (where owner = %(owner)s)                  as login_runs,
    coalesce(sum(cost_usd) filter (where owner = %(owner)s), 0) as login_usd,
    coalesce(sum(tokens_in) filter (where owner = %(owner)s), 0) as login_tokens_in,
    coalesce(sum(tokens_out) filter (where owner = %(owner)s), 0) as login_tokens_out,
    count(*) filter (where owner = %(owner)s and cost_usd is null) as login_unpriced,
    coalesce(sum(cost_usd) filter (
        where owner = %(owner)s and payer = 'guest'
    ), 0)                                                      as login_guest_usd
  from agent_runs
"""


@dataclass(frozen=True, slots=True)
class Counters:

    day_runs: int
    day_usd: Decimal
    day_offbudget_usd: Decimal
    day_guest_usd: Decimal
    total_usd: Decimal
    unpriced: int
    login_runs: int = 0
    login_usd: Decimal = Decimal(0)
    login_tokens_in: int = 0
    login_tokens_out: int = 0
    login_unpriced: int = 0
    login_guest_usd: Decimal = Decimal(0)


async def record(
    pool: DictPool,
    *,
    account: str,
    owner: str,
    kind: str,
    model: str,
    tokens_in: int,
    tokens_out: int,
    cost_usd: Decimal | None,
    duration_ms: int,
    started_at: datetime,
    ok: bool = True,
    payer: str = "project",
) -> None:
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        await conn.execute(
            _RECORD,
            {
                "started_at": started_at,
                "account": account,
                "owner": owner,
                "kind": kind,
                "model": model,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cost_usd": cost_usd,
                "duration_ms": duration_ms,
                "ok": ok,
                "payer": payer,
            },
        )


async def counters(
    pool: DictPool,
    *,
    account: str,
    owner: str,
    since: datetime,
    kinds: Sequence[str],
    offbudget: Sequence[str],
) -> Counters:
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        row = await (
            await conn.execute(
                _COUNTERS,
                {
                    "account": account,
                    "owner": owner,
                    "since": since,
                    "kinds": list(kinds),
                    "offbudget": list(offbudget),
                },
            )
        ).fetchone()
    if row is None:  # pragma: no cover — агрегат завжди віддає рядок
        return Counters(
            day_runs=0,
            day_usd=Decimal(0),
            day_offbudget_usd=Decimal(0),
            day_guest_usd=Decimal(0),
            total_usd=Decimal(0),
            unpriced=0,
        )
    return Counters(
        day_runs=int(row["day_runs"]),
        day_usd=Decimal(row["day_usd"]),
        day_offbudget_usd=Decimal(row["day_offbudget_usd"]),
        day_guest_usd=Decimal(row["day_guest_usd"]),
        total_usd=Decimal(row["total_usd"]),
        unpriced=int(row["unpriced"]),
        login_runs=int(row["login_runs"]),
        login_usd=Decimal(row["login_usd"]),
        login_tokens_in=int(row["login_tokens_in"]),
        login_tokens_out=int(row["login_tokens_out"]),
        login_unpriced=int(row["login_unpriced"]),
        login_guest_usd=Decimal(row["login_guest_usd"]),
    )


__all__ = ["DB_TIMEOUT", "Counters", "counters", "record"]
