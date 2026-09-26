from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace
from typing import Any

from komora.agent.basket import (
    Assembled,
    PlanLine,
    Tracer,
    chain_from_decision,
    mandate_for_decision,
    to_cart_line,
)
from komora.agent.cart import CartRun, plan_of, with_plan
from komora.api.schemas import SwapDecision, SwapOption
from komora.logging import get_logger

log = get_logger(__name__)


def remember_options(run: Assembled | CartRun, options: Sequence[SwapOption]) -> None:
    plan = plan_of(run)
    for option in options:
        plan.swap_cards[str(option.external_product_id)] = {
            "externalProductId": str(option.external_product_id),
            "name": option.name,
            "price": option.price,
            "stock": None if option.stock is None else int(option.stock),
            "available": option.available,
        }


def _cards(plan: Assembled, line: PlanLine) -> dict[str, dict[str, Any]]:
    cards: dict[str, dict[str, Any]] = {
        str(card.get("externalProductId")): card for card in line.considered
    }
    cards[str(line.product.get("externalProductId"))] = line.product
    for alternative in line.chain:
        cards[alternative.external_product_id] = {
            "externalProductId": alternative.external_product_id,
            "name": alternative.name,
            "price": alternative.price,
            "stock": alternative.stock,
            "available": alternative.available,
        }
    cards.update(plan.swap_cards)
    return cards


def apply(run: Assembled | CartRun, decisions: Sequence[SwapDecision]) -> Assembled | CartRun:
    plan = plan_of(run)
    by_article: Mapping[str, SwapDecision] = {
        str(decision.external_product_id): decision for decision in decisions
    }
    lines = [_decided(plan, line, by_article) for line in plan.lines]
    changed = sum(
        1
        for before, after in zip(plan.lines, lines, strict=True)
        if before.mandate != after.mandate or before.chain != after.chain
    )

    trace = Tracer()
    trace.steps = list(plan.basket.trace)
    trace.add(
        "step-swaps",
        "agent.swaps",
        {},
        f"погоджені заміни: {changed} з {len(lines)} рядків",
        decision=(
            "мандат перерахований без перезбірки: ланцюжок не міняє ні складу, "
            "ні цін, ні слота"
        ),
        tag="рішення гостя",
        tag_tone="good",
    )

    basket = plan.basket.model_copy(
        update={"lines": [to_cart_line(line) for line in lines], "trace": trace.steps}
    )
    log.info("swaps.applied", changed=changed, lines=len(lines))
    decided = {
        article: line.chain
        for line in lines
        if (article := str(line.product.get("externalProductId"))) in by_article and line.chain
    }
    return with_plan(run, replace(plan, basket=basket, lines=lines), chains=decided)


def _decided(
    plan: Assembled, line: PlanLine, by_article: Mapping[str, SwapDecision]
) -> PlanLine:
    decision = by_article.get(str(line.product.get("externalProductId")))
    if decision is None:
        return line
    chain = chain_from_decision(decision, _cards(plan, line)) if decision.chain else ()
    decided = mandate_for_decision(
        decision, chain, risky=line.risky, shelf_life=line.shelf_life, wish=line.wish
    )
    if decided is None:
        return line
    mandate, needs_approval = decided
    return replace(
        line,
        chain=chain,
        mandate=mandate,
        needs_approval=needs_approval,
        swap_fork=None,
        ahead=False,
    )


__all__ = ["apply", "plan_of", "remember_options"]
