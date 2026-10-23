from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from fastapi import HTTPException

from komora.agent.basket import Assembled, PlanLine
from komora.agent.swaps import apply as apply_swaps
from komora.agent.swaps import remember_options
from komora.api import runs
from komora.api.app import apply_swaps as endpoint
from komora.api.schemas import Basket, RunStats, SwapDecision, SwapOption, SwapsRequest
from komora.auth.session import GuestSession
from komora.core.substitution import Alternative, Source

GUEST = GuestSession(access="токен")
OWNER = GUEST.owner

SLOT = {
    "start": "2026-08-24T08:00:00+00:00",
    "end": "2026-08-24T10:00:00+00:00",
    "deliveryCost": 89,
    "minOrderCost": 599,
    "maxWeight": 50,
}


def _card(article: int, name: str, price: str) -> dict[str, Any]:
    return {
        "id": f"00000000-0000-4000-8000-{article:012d}",
        "companyId": "c",
        "branchId": "b",
        "name": name,
        "price": price,
        "externalProductId": article,
        "stock": 4,
        "available": True,
    }


def _line(article: int, name: str, price: str = "100", **kwargs: Any) -> PlanLine:
    return PlanLine(
        intent=name.lower(),
        product=_card(article, name, price),
        qty=Decimal(1),
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


def _decision(article: int, chain: list[int], policy: str = "substitute") -> SwapDecision:
    return SwapDecision.model_validate(
        {
            "externalProductId": str(article),
            "policy": policy,
            "chain": [str(link) for link in chain],
        }
    )


def test_the_guests_chain_becomes_the_mandate_without_a_rebuild():
    line = _line(101, "Сир Пармезан", considered=(_card(202, "Сир Джюгас", "250"),))
    plan = _plan([line])

    after = apply_swaps(plan, [_decision(101, [202])])

    assert after.lines[0].mandate is not None
    assert "Сир Джюгас" in after.lines[0].mandate
    assert [link.name for link in after.lines[0].chain] == ["Сир Джюгас"]
    assert len(after.lines) == 1
    assert after.slot == plan.slot


def test_a_link_chosen_in_search_still_names_itself():
    plan = _plan([_line(101, "Сир Пармезан")])
    remember_options(
        plan,
        [
            SwapOption.model_validate(
                {
                    "external_product_id": "303",
                    "name": "Сир Грана Падано",
                    "price": "270",
                    "stock": "6",
                    "available": True,
                }
            )
        ],
    )

    after = apply_swaps(plan, [_decision(101, [303])])

    assert "Сир Грана Падано" in (after.lines[0].mandate or "")


def test_the_form_wish_survives_the_cheap_recount():
    line = _line(
        101,
        "Ковбаса Салямі",
        considered=(_card(202, "Ковбаса Мисливська", "180"),),
        wish="нарізана",
    )

    after = apply_swaps(_plan([line]), [_decision(101, [202])])

    assert "нарізана" in (after.lines[0].mandate or "")


def test_the_shelf_life_survives_the_cheap_recount_too():
    line = _line(
        101,
        "Молоко Ферма",
        considered=(_card(202, "Молоко Яготинське", "76"),),
        shelf_life="термін придатності не менше ніж до 30.08",
    )

    after = apply_swaps(_plan([line]), [_decision(101, [202])])

    assert "термін придатності не менше ніж до 30.08" in (after.lines[0].mandate or "")


def test_a_decision_that_dictates_nothing_leaves_the_line_alone():
    line = _line(101, "Молоко", mandate="якщо немає — рівноцінна заміна", risky=True)

    after = apply_swaps(_plan([line]), [_decision(101, [])])

    assert after.lines[0].mandate == "якщо немає — рівноцінна заміна"


def test_do_not_collect_is_a_decision_and_it_says_so():
    line = _line(101, "Молоко", risky=True)

    after = apply_swaps(_plan([line]), [_decision(101, [], policy="skip")])

    assert "заміни не підбирати" in (after.lines[0].mandate or "")
    assert after.lines[0].needs_approval is False


def test_a_call_leaves_the_line_waiting_for_the_guest():
    line = _line(101, "Молоко", risky=True, mandate="старий текст")

    after = apply_swaps(_plan([line]), [_decision(101, [], policy="call")])

    assert after.lines[0].mandate is None
    assert after.lines[0].needs_approval is True


def test_the_trace_says_what_changed_and_that_it_was_cheap():
    line = _line(101, "Сир", considered=(_card(202, "Сир Джюгас", "250"),))

    after = apply_swaps(_plan([line]), [_decision(101, [202])])

    step = after.basket.trace[-1]
    assert step.id == "step-swaps"
    assert "1 з 1" in step.result_summary
    assert "без перезбірки" in (step.decision or "")


def test_an_untouched_line_keeps_its_own_chain():
    kept = Alternative(external_product_id="909", name="Молоко Ферма", source=Source.HISTORY)
    lines = [
        _line(101, "Сир", considered=(_card(202, "Сир Джюгас", "250"),)),
        _line(102, "Молоко", chain=(kept,), mandate="якщо немає — Молоко Ферма"),
    ]

    after = apply_swaps(_plan(lines), [_decision(101, [202])])

    assert after.lines[1].chain == (kept,)
    assert after.lines[1].mandate == "якщо немає — Молоко Ферма"


@pytest.mark.anyio
async def test_a_foreign_run_is_indistinguishable_from_a_forgotten_one():
    runs.forget_all()
    basket = runs.remember(_plan([_line(101, "Сир")]), owner="somebody-else")

    with pytest.raises(HTTPException) as raised:
        await endpoint(basket.run_id, SwapsRequest(swaps=[]), GUEST)

    assert raised.value.status_code == 404
    runs.forget_all()


@pytest.mark.anyio
async def test_the_endpoint_hands_back_a_new_run_id():
    runs.forget_all()
    line = _line(101, "Сир", considered=(_card(202, "Сир Джюгас", "250"),))
    before = runs.remember(_plan([line]), owner=OWNER)

    after = await endpoint(before.run_id, SwapsRequest(swaps=[_decision(101, [202])]), GUEST)

    assert after.run_id != before.run_id
    kept = runs.recall(after.run_id, owner=OWNER)
    assert kept is not None
    assert "Сир Джюгас" in (kept.lines[0].mandate or "")
    runs.forget_all()
