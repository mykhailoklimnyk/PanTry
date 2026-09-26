from __future__ import annotations

from dataclasses import replace

from komora.agent.basket import (
    Assembled,
    PlanLine,
    Tracer,
    terms_from_slot,
    to_cart_line,
    weigh,
)
from komora.agent.cart import CartRun, plan_of, with_plan
from komora.agent.economics import ORDER_MIN, settle
from komora.api.schemas import CorrectionRequest, Reason
from komora.logging import get_logger

log = get_logger(__name__)


class CorrectionError(RuntimeError):
    ...


PHRASES = {
    "still_have": "ти сказав, що ще є вдома — не купую",
    "ran_out_earlier": "закінчилось раніше, ніж я рахував — беру",
    "never_again": "більше не потрібне — прибрав зі списку",
}


def apply(
    run: Assembled | CartRun, request: CorrectionRequest
) -> tuple[Assembled | CartRun, str]:
    plan = plan_of(run)
    article = str(request.external_product_id)
    target = next(
        (line for line in plan.lines if str(line.product.get("externalProductId")) == article),
        None,
    )
    if target is None:
        raise CorrectionError(
            f"рядка {article} у цьому прогоні немає — можливо, кошик уже перезібрано"
        )

    name = str(target.product.get("name") or target.intent)
    phrase = PHRASES[request.action]
    lines = [
        corrected
        for line in plan.lines
        if (
            corrected := (
                _corrected(line, request.action, phrase)
                if str(line.product.get("externalProductId")) == article
                else line
            )
        )
        is not None
    ]

    return _rebuilt(run, plan, lines, note=f"{name}: {phrase}"), f"{name} — {phrase}"


def _corrected(line: PlanLine, action: str, phrase: str) -> PlanLine | None:
    if action == "never_again":
        return None
    if action == "still_have":
        return replace(
            line,
            at_home=True,
            mandate=None,
            swap_fork=None,
            needs_approval=False,
            risky=False,
            explanation=phrase,
            reason_code=Reason.AT_HOME,
        )
    return replace(
        line,
        at_home=False,
        explanation=phrase,
        reason_code=Reason.CYCLE,
    )


def _rebuilt(
    run: Assembled | CartRun,
    plan: Assembled,
    lines: list[PlanLine],
    *,
    note: str,
) -> Assembled | CartRun:
    terms = terms_from_slot(plan.slot)
    snapshot = run.snapshot if isinstance(run, CartRun) else None
    money = settle(
        lines,
        terms,
        actual_delivery_cost=snapshot.delivery_cost if snapshot else None,
        blockers=[code for code in (snapshot.blockers if snapshot else []) if code != ORDER_MIN],
    )

    trace = Tracer()
    trace.steps = list(plan.basket.trace)
    trace.add(
        "step-correction",
        "agent.correction",
        {},
        note,
        decision=(
            f"перерахував кошик: разом {money.total} грн, доставка {money.cost} грн"
            + (
                f"; до мінімуму {terms.min_order_cost} бракує"
                if ORDER_MIN in money.blockers
                else ""
            )
        ),
        tag="правка гостя",
        tag_tone="good",
    )

    basket = plan.basket.model_copy(
        update={
            "lines": [to_cart_line(line) for line in lines],
            "total": money.total,
            "base_total": money.discounted,
            "delivery_cost": money.cost,
            "total_weight_kg": weigh(lines).kg,
            "top_up": money.top_up,
            "blockers": money.blockers,
            "trace": trace.steps,
        }
    )
    log.info("correction.applied", lines=len(lines), total=str(money.total))
    return with_plan(run, replace(plan, basket=basket, lines=lines))


__all__ = ["PHRASES", "CorrectionError", "apply", "plan_of"]
