from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from fastapi import HTTPException

from komora.agent.basket import Assembled, PlanLine
from komora.agent.correction import CorrectionError
from komora.agent.correction import apply as apply_correction
from komora.agent.economics import ORDER_MIN
from komora.api import runs
from komora.api.app import apply_correction as endpoint
from komora.api.schemas import Basket, CorrectionRequest, Reason, RunStats
from komora.auth.session import GuestSession

SLOT = {
    "start": "2026-08-16T08:00:00+00:00",
    "end": "2026-08-16T10:00:00+00:00",
    "deliveryCost": 89,
    "deliveryCostMap": [
        {"cost": 59, "fromOrderCost": 1199},
        {"cost": 1, "fromOrderCost": 1699},
    ],
    "minOrderCost": 599,
    "maxWeight": 50,
}


GUEST = GuestSession(access="токен")
OWNER = GUEST.owner


def _line(
    article: int,
    name: str,
    price: str,
    qty: int = 1,
    *,
    ratio: str | None = None,
    **kwargs: Any,
) -> PlanLine:
    return PlanLine(
        intent=name.lower(),
        product={
            "id": f"00000000-0000-4000-8000-{article:012d}",
            "companyId": "c",
            "branchId": "b",
            "name": name,
            "price": price,
            "externalProductId": article,
            "displayRatio": ratio,
        },
        qty=Decimal(qty),
        reason="звичне",
        from_history=None,
        **kwargs,
    )


def _plan(lines: list[PlanLine]) -> Assembled:
    basket = Basket(
        run_id="test",
        lines=[],
        total=Decimal(0),
        delivery_cost=Decimal(0),
        total_weight_kg=Decimal(0),
        stats=RunStats(
            receipts=0, cycled=0, mcp_calls=0, duration_ms=0, cost_usd=Decimal(0), model="тест"
        ),
    )
    return Assembled(basket=basket, lines=lines, unresolved=[], slot=dict(SLOT))


def _ask(article: int, action: str) -> CorrectionRequest:
    return CorrectionRequest.model_validate(
        {"externalProductId": str(article), "action": action}
    )


def test_removed_line_takes_the_money_with_it():
    plan = _plan([_line(101, "Молоко", "700"), _line(102, "Кава", "600")])
    corrected, _ = apply_correction(plan, _ask(102, "never_again"))

    assert [line.name for line in corrected.basket.lines] == ["Молоко"]
    assert corrected.basket.total == Decimal(700)
    assert corrected.basket.top_up is not None
    assert corrected.basket.top_up.threshold == Decimal(1199)


def test_the_weight_is_recounted_with_the_composition():
    plan = _plan(
        [
            _line(101, "Молоко", "700", ratio="900г"),
            _line(102, "Кава", "600", ratio="250г"),
        ]
    )
    corrected, _ = apply_correction(plan, _ask(102, "never_again"))

    assert corrected.basket.total_weight_kg == Decimal("0.9")


def test_a_line_without_packaging_does_not_pretend_to_weigh_nothing():
    plan = _plan([_line(101, "Молоко", "700"), _line(102, "Кава", "600", ratio="250г")])
    corrected, _ = apply_correction(plan, _ask(101, "still_have"))

    lines = {line.name: line for line in corrected.basket.lines}
    assert lines["Молоко"].weight_kg is None
    assert corrected.basket.total_weight_kg == Decimal("0.25")


def test_dropping_below_the_minimum_raises_the_blocker():
    plan = _plan([_line(101, "Молоко", "500"), _line(102, "Кава", "300")])
    corrected, _ = apply_correction(plan, _ask(102, "never_again"))

    assert corrected.basket.total == Decimal(500)
    assert ORDER_MIN in corrected.basket.blockers


def test_still_have_mutes_the_line_instead_of_hiding_it():
    plan = _plan([_line(101, "Молоко", "700"), _line(102, "Рис", "300")])
    corrected, said = apply_correction(plan, _ask(102, "still_have"))

    kept = {line.name: line for line in corrected.basket.lines}
    assert "Рис" in kept, "рядок лишається видимим — зникає лише з суми"
    assert kept["Рис"].reason is Reason.AT_HOME
    assert "ще є вдома" in kept["Рис"].explanation
    assert corrected.basket.total == Decimal(700)
    assert "Рис" in said


def test_ran_out_earlier_brings_the_line_back_into_the_sum():
    plan = _plan([_line(101, "Молоко", "700"), _line(102, "Рис", "300", at_home=True)])
    assert apply_correction(plan, _ask(102, "still_have"))[0].basket.total == Decimal(700)

    corrected, _ = apply_correction(plan, _ask(102, "ran_out_earlier"))
    assert corrected.basket.total == Decimal(1000)
    kept = {line.name: line for line in corrected.basket.lines}
    assert kept["Рис"].reason is Reason.CYCLE


def test_mandate_goes_away_with_the_line_that_is_not_bought():
    line = _line(102, "Кава", "300")
    line.mandate = "якщо немає — Lavazza"
    line.risky = True
    plan = _plan([_line(101, "Молоко", "700"), line])

    corrected, _ = apply_correction(plan, _ask(102, "still_have"))
    kept = {row.name: row for row in corrected.basket.lines}
    assert kept["Кава"].mandate is None
    assert kept["Кава"].at_risk is False


def test_the_fork_goes_away_with_the_mandate_it_was():
    from komora.core.mandate import price_fork

    line = _line(102, "Кава", "300")
    line.mandate = "якщо немає — рівноцінна заміна того самого виду"
    line.swap_fork = price_fork(Decimal("300"))
    line.risky = True
    plan = _plan([_line(101, "Молоко", "700"), line])

    corrected, _ = apply_correction(plan, _ask(102, "still_have"))

    kept = {row.name: row for row in corrected.basket.lines}
    assert kept["Кава"].swap_fork is None


def test_previous_run_survives_the_correction():
    plan = _plan([_line(101, "Молоко", "700"), _line(102, "Кава", "600")])
    before = [line.product["name"] for line in plan.lines]

    apply_correction(plan, _ask(102, "never_again"))

    assert [line.product["name"] for line in plan.lines] == before


def test_correction_is_written_into_the_trace():
    plan = _plan([_line(101, "Молоко", "700")])
    corrected, _ = apply_correction(plan, _ask(101, "still_have"))

    [step] = [s for s in corrected.basket.trace if s.id == "step-correction"]
    assert "Молоко" in step.result_summary
    assert step.decision is not None and "перерахував кошик" in step.decision


def test_unknown_line_says_so_instead_of_silently_doing_nothing():
    plan = _plan([_line(101, "Молоко", "700")])
    with pytest.raises(CorrectionError, match="немає"):
        apply_correction(plan, _ask(999, "never_again"))


async def test_forgotten_run_is_a_404_not_a_guess():
    runs.forget_all()
    with pytest.raises(HTTPException) as exc:
        await endpoint("будь-що", _ask(101, "still_have"), GUEST)

    assert exc.value.status_code == 404


async def test_correction_hands_back_a_new_run_id():
    runs.forget_all()
    plan = _plan([_line(101, "Молоко", "700"), _line(102, "Кава", "600")])
    first = runs.remember(plan, owner=OWNER)

    result = await endpoint(first.run_id, _ask(102, "never_again"), GUEST)

    assert result.run_id != first.run_id
    assert runs.recall(result.run_id, owner=OWNER) is not None, "новий прогін лишився оформлюваним"
    assert runs.recall(result.run_id, owner=GuestSession(access="чужий").owner) is None
    assert result.total == Decimal(700)
