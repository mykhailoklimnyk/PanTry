from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import datetime
from decimal import Decimal
from typing import Any

from komora.agent.basket import Assembled, Receipts, Tracer, norm_name
from komora.agent.cart import CartRun, plan_of, with_plan
from komora.agent.occasion import HISTORY_LIMIT, TABLE_LIMIT, more_for_table
from komora.agent.refill import RefillError, refill
from komora.api.schemas import RefillRequest, TraceStep
from komora.core.occasion import BuildMode, Occasion
from komora.core.target import band
from komora.core.words import plural
from komora.db.pool import DictPool
from komora.logging import get_logger
from komora.mcp.client import SilpoMCP

log = get_logger(__name__)

TABLE_STEP = "step-table"

TABLE_PASSES = 3


async def top_up_table(
    mcp: SilpoMCP,
    llm: Any,
    run: Assembled | CartRun,
    occasion: Occasion,
    *,
    now: datetime | None = None,
    pool: DictPool | None = None,
    account: str = "",
    saved_chains: Mapping[str, tuple[str, ...]] | None = None,
    receipts: Receipts | None = None,
    on_step: Callable[[TraceStep], None] | None = None,
    paid: Decimal | None = None,
) -> Assembled | CartRun:
    if isinstance(run, CartRun) or llm is None or occasion.mode is not BuildMode.EVENT:
        return run
    ratio: Decimal | None = None
    for _pass in range(TABLE_PASSES):
        plan = plan_of(run)
        if plan.basket.budget is None:
            return run
        named = Decimal(str(plan.basket.budget))
        edges = band(named)
        total = Decimal(str(plan.basket.total))
        if paid is not None and ratio is None and total > 0:
            ratio = min(Decimal(1), paid / total)
        measured = (total * ratio).quantize(Decimal("0.01")) if ratio is not None else total
        if measured >= edges.low:
            return run
        ceiling = named
        if ratio is not None and ratio < 1:
            ceiling = (named / ratio).quantize(Decimal("0.01"))
        pass_plan = (
            plan
            if ceiling == named
            else replace(plan, basket=plan.basket.model_copy(update={"budget": ceiling}))
        )
        lines_before = len(plan.lines)
        run = await _one_pass(
            mcp,
            llm,
            with_plan(run, pass_plan) if ceiling != named else run,
            pass_plan,
            occasion,
            total=total,
            shortfall=ceiling - total,
            edges=(edges.low, edges.high),
            now=now,
            pool=pool,
            account=account,
            saved_chains=saved_chains,
            receipts=receipts,
            on_step=on_step,
        )
        if ceiling != named:
            after = plan_of(run)
            run = with_plan(
                run, replace(after, basket=after.basket.model_copy(update={"budget": named}))
            )
        if len(plan_of(run).lines) <= lines_before:
            return run
    return run


async def _one_pass(
    mcp: SilpoMCP,
    llm: Any,
    run: Assembled | CartRun,
    plan: Assembled,
    occasion: Occasion,
    *,
    total: Decimal,
    shortfall: Decimal,
    edges: tuple[Decimal, Decimal],
    now: datetime | None,
    pool: DictPool | None,
    account: str,
    saved_chains: Mapping[str, tuple[str, ...]] | None,
    receipts: Receipts | None,
    on_step: Callable[[TraceStep], None] | None,
) -> Assembled | CartRun:
    have = [str(line.product.get("name") or line.intent) for line in plan.lines if not line.at_home]
    usual_line = (total / len(plan.lines)) if plan.lines and total > 0 else Decimal(100)
    need_kinds = max(
        3,
        min(
            TABLE_LIMIT,
            int((shortfall / usual_line).to_integral_value(rounding="ROUND_CEILING")),
        ),
    )
    habits: tuple[tuple[str, int], ...] = ()
    if receipts is not None and receipts.branch_id == plan.branch_id:
        habits = tuple(
            (item.name, item.receipts)
            for item in sorted(receipts.history, key=lambda item: -item.receipts)
        )[:HISTORY_LIMIT]
    trace = Tracer(on_step=on_step)
    trace.steps = list(plan.basket.trace)
    try:
        more = await more_for_table(
            llm, occasion, have=have, shortfall=shortfall, habits=habits, need_kinds=need_kinds
        )
    except Exception as exc:
        log.warning("table.model_failed", error=str(exc)[:160])
        trace.add(
            TABLE_STEP,
            "agent.occasion",
            {"бракує_грн": f"{shortfall:.0f}", "помилка": str(exc)[:120]},
            f"кошик {total:.0f} грн нижчий за коридор, а модель про стіл не відповіла -- "
            "лишаю як зібрано",
            tag="стіл: нема",
            tag_tone="warn",
        )
        return with_plan(
            run, replace(plan, basket=plan.basket.model_copy(update={"trace": trace.steps}))
        )
    settled = {
        norm_name(name)
        for name in (*plan.basket.unresolved, *(item.intent for item in plan.basket.declined))
    }
    names = [change.intent for change in more.added if norm_name(change.intent) not in settled]
    trace.add(
        TABLE_STEP,
        "agent.occasion",
        {
            "бракує_грн": f"{shortfall:.0f}",
            "коридор": f"{edges[0]:.0f}-{edges[1]:.0f}",
            "докинути": names,
            "чому": {change.intent: change.why for change in more.added},
            "токенів": more.tokens,
        },
        f"кошик {total:.0f} грн нижчий за коридор -- до столу докидаю {len(names)} "
        f"{plural(len(names), 'вид', 'види', 'видів')}"
        if names
        else f"кошик {total:.0f} грн нижчий за коридор, а модель не назвала, чим ще накрити стіл",
        duration_ms=more.duration_ms,
        prompt=more.prompt,
        decision="чим накрити стіл під суму -- рішення агента; межа, коридор і різ під "
        "неї -- сталі правила",
        tag=f"+{len(names)} до столу" if names else "стіл: досить",
        tag_tone="good" if names else "muted",
    )
    run = with_plan(
        run, replace(plan, basket=plan.basket.model_copy(update={"trace": trace.steps}))
    )
    if not names:
        return run
    try:
        filled = await refill(
            mcp,
            llm,
            run,
            RefillRequest(intents=names),
            now=now,
            pool=pool,
            account=account,
            saved_chains=saved_chains,
            receipts=receipts,
            trim_fill=True,
            label="до столу",
            on_step=on_step,
        )
    except RefillError as exc:
        log.info("table.refill_refused", error=str(exc))
        return run
    log.info(
        "table.topped_up",
        before=str(total),
        after=str(plan_of(filled).basket.total),
        named=str(plan.basket.budget),
        asked=len(names),
    )
    return filled


__all__ = ["TABLE_PASSES", "TABLE_STEP", "top_up_table"]
