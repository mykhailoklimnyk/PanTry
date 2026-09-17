from __future__ import annotations

import itertools
from collections import OrderedDict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import HTTPException

from komora.agent.llm import Meter
from komora.auth.session import GuestSession
from komora.config import settings
from komora.core import models, quota
from komora.db import spend
from komora.db.pool import get_pool
from komora.logging import get_logger

log = get_logger(__name__)

MAX_OWNERS = 512

_SESSION: OrderedDict[str, int] = OrderedDict()

_TICKET = itertools.count(1)

_LIVE_SESSION: dict[str, set[int]] = {}
_LIVE_DAY: dict[str, set[int]] = {}


def _day_key(guest: GuestSession) -> str:
    return guest.account or guest.owner


def _take(guest: GuestSession) -> int:
    ticket = next(_TICKET)
    _LIVE_SESSION.setdefault(guest.owner, set()).add(ticket)
    _LIVE_DAY.setdefault(_day_key(guest), set()).add(ticket)
    return ticket


def _drop(guest: GuestSession, ticket: int) -> None:
    for store, key in ((_LIVE_SESSION, guest.owner), (_LIVE_DAY, _day_key(guest))):
        held = store.get(key)
        if held is None:  # pragma: no cover — місце завжди віддає той, хто взяв
            continue
        held.discard(ticket)
        if not held:
            store.pop(key, None)


def flying(guest: GuestSession, *, before: int | None = None) -> tuple[int, int]:

    def held(store: dict[str, set[int]], key: str) -> int:
        taken = store.get(key, frozenset[int]())
        return len(taken) if before is None else sum(1 for one in taken if one < before)

    return (held(_LIVE_SESSION, guest.owner), held(_LIVE_DAY, _day_key(guest)))


def elapsed_ms(started: datetime) -> int:
    return int((datetime.now(UTC) - started).total_seconds() * 1000)


def seen(owner: str) -> int:
    return _SESSION.get(owner, 0)


def bump(owner: str) -> int:
    count = _SESSION.pop(owner, 0) + 1
    _SESSION[owner] = count
    while len(_SESSION) > MAX_OWNERS:
        _SESSION.popitem(last=False)
    return count


def forget(owner: str) -> None:
    _SESSION.pop(owner, None)


def forget_all() -> None:
    _SESSION.clear()
    _LIVE_SESSION.clear()
    _LIVE_DAY.clear()


def priced() -> bool:
    return bool(settings.bedrock_api_key)


def open_verdict() -> quota.Verdict:
    return quota.Verdict(
        scope=None,
        headline="модель не налаштована — прогони нічого не коштують, стеля не рахується",
        action=None,
        left=settings.runs_per_session,
        resets_at=None,
    )


def limits() -> quota.Limits:
    return quota.Limits(
        per_session=settings.runs_per_session,
        per_day=settings.runs_per_day,
        day_usd=settings.budget_day_usd,
        total_usd=settings.budget_total_usd,
    )


async def look(
    guest: GuestSession, *, now: datetime | None = None, before: int | None = None
) -> quota.Verdict:
    moment = now or datetime.now(UTC)
    counted = await spend.counters(
        get_pool(),
        account=guest.account,
        owner=guest.owner,
        since=quota.day_start(moment),
        kinds=sorted(quota.COUNTED_RUNS),
        offbudget=sorted(quota.OFF_DAY_BUDGET),
    )
    session_flying, day_flying = flying(guest, before=before)
    return quota.verdict(
        limits(),
        quota.Spent(
            session_runs=seen(guest.owner),
            day_runs=counted.day_runs,
            day_usd=counted.day_usd,
            day_offbudget_usd=counted.day_offbudget_usd,
            day_guest_usd=counted.day_guest_usd,
            total_usd=counted.total_usd,
            unpriced=counted.unpriced,
            session_flying=session_flying,
            day_flying=day_flying,
            login_runs=counted.login_runs,
            login_usd=counted.login_usd,
            login_tokens_in=counted.login_tokens_in,
            login_tokens_out=counted.login_tokens_out,
            login_unpriced=counted.login_unpriced,
            login_guest_usd=counted.login_guest_usd,
        ),
        now=moment,
        exempt=bool(guest.account) and guest.account in settings.insider_accounts(),
    )


async def guard(
    guest: GuestSession, *, now: datetime | None = None, before: int | None = None
) -> quota.Verdict:
    if not priced():
        return open_verdict()
    try:
        verdict = await look(guest, now=now, before=before)
    except Exception as exc:
        log.error("quota.counter_down", error=str(exc)[:200])
        raise HTTPException(
            status_code=503,
            detail=(
                "Лічильник витрат не відповідає, тому жива збірка вимкнена — "
                "рахувати чужі гроші наосліп ми не будемо. Комора і решта "
                "екранів працюють."
            ),
        ) from exc

    if not verdict.allowed:
        raise HTTPException(
            status_code=429,
            detail=f"{verdict.headline}. {verdict.action}: {settings.contact}",
        )
    return verdict


async def model_gate(guest: GuestSession, llm: object | None) -> object | None:
    if llm is None:
        return None
    try:
        verdict = await look(guest)
    except Exception as exc:
        log.warning("quota.pantry_uncounted", error=str(exc)[:200])
        return llm
    return None if verdict.scope in ("budget-day", "budget-total") else llm


async def record(
    guest: GuestSession,
    *,
    kind: str,
    meter: Meter,
    duration_ms: int,
    started_at: datetime,
    ok: bool = True,
) -> None:
    if not priced():
        return
    if quota.counts_as_run(kind):
        bump(guest.owner)
    cost = quota.run_cost(meter.model, meter.calls, meter.input_tokens, meter.output_tokens)
    if cost is None:
        log.warning("quota.model_without_price", model=meter.model)
    try:
        await spend.record(
            get_pool(),
            account=guest.account,
            owner=guest.owner,
            kind=kind,
            model=meter.model,
            tokens_in=meter.input_tokens,
            tokens_out=meter.output_tokens,
            cost_usd=cost,
            duration_ms=duration_ms,
            started_at=started_at,
            ok=ok,
            payer=models.payer_of(meter.model),
        )
    except Exception as exc:
        log.error("quota.record_failed", kind=kind, error=str(exc)[:200])


@asynccontextmanager
async def counted(guest: GuestSession, *, kind: str, meter: Meter) -> AsyncIterator[quota.Verdict]:
    if not quota.counts_as_run(kind):
        raise RuntimeError(
            f"вид прогону «{kind}» не рахується стелею — додай його в "
            "core.quota.COUNTED_RUNS або пиши витрату через record()"
        )
    if not priced():
        yield open_verdict()
        return

    ticket = _take(guest)
    try:
        verdict = await guard(guest, before=ticket)
    except BaseException:
        _drop(guest, ticket)
        raise

    started = datetime.now(UTC)
    ok = False
    try:
        yield verdict
        ok = True
    finally:
        try:
            await record(
                guest,
                kind=kind,
                meter=meter,
                duration_ms=elapsed_ms(started),
                started_at=started,
                ok=ok,
            )
        finally:
            _drop(guest, ticket)
    if meter.down and meter.payer == "project":
        raise HTTPException(
            status_code=402,
            detail=(
                f"Модель проєкту відмовила ({meter.down}): гроші або ліміт на "
                "AWS скінчились. Додай свій ключ OpenAI -- далі збираємо твоєю "
                "моделлю, а не нашою."
            ),
        )


__all__ = [
    "MAX_OWNERS",
    "bump",
    "counted",
    "elapsed_ms",
    "flying",
    "forget",
    "forget_all",
    "guard",
    "limits",
    "look",
    "model_gate",
    "open_verdict",
    "priced",
    "record",
    "seen",
]
