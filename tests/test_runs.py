from __future__ import annotations

from decimal import Decimal

from komora.agent.basket import Assembled
from komora.api import runs
from komora.api.schemas import Basket, RunStats
from komora.auth.session import GuestSession

ME = GuestSession(access="мій-токен").owner
STRANGER = GuestSession(access="чужий-токен").owner


def _plan() -> Assembled:
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
    return Assembled(basket=basket, lines=[], unresolved=[], slot={})


def setup_function() -> None:
    runs.forget_all()


def teardown_function() -> None:
    runs.forget_all()


def test_a_stranger_cannot_push_my_run_out_of_memory() -> None:
    mine = runs.remember(_plan(), owner=ME)

    for _ in range(runs.MAX_RUNS * 2):
        runs.remember(_plan(), owner=STRANGER)

    assert runs.recall(mine.run_id, owner=ME) is not None, (
        "план витіснили чужі збірки — «Оформити» віддасть 404 на живому демо"
    )


def test_my_own_ceiling_still_holds() -> None:
    ids = [runs.remember(_plan(), owner=ME).run_id for _ in range(runs.MAX_RUNS + 3)]

    alive = [run_id for run_id in ids if runs.recall(run_id, owner=ME) is not None]

    assert alive == ids[-runs.MAX_RUNS :]


def test_the_machine_still_has_a_floor() -> None:
    for number in range(runs.MAX_TOTAL + runs.MAX_RUNS):
        runs.remember(_plan(), owner=f"гість-{number}")

    assert len(runs._RUNS) <= runs.MAX_TOTAL


def test_the_run_i_just_used_outlives_the_one_i_did_not() -> None:
    first = runs.remember(_plan(), owner=ME)
    rest = [runs.remember(_plan(), owner=ME) for _ in range(runs.MAX_RUNS - 1)]

    assert runs.recall(first.run_id, owner=ME) is not None, "передумова: поки всі живі"
    runs.remember(_plan(), owner=ME)

    assert runs.recall(first.run_id, owner=ME) is not None, "вживаний прогін випав першим"
    assert runs.recall(rest[0].run_id, owner=ME) is None, "випасти мав найдавніший невживаний"


def test_a_recalled_plan_does_not_share_row_objects_with_memory() -> None:
    from decimal import Decimal

    from komora.agent.basket import PlanLine

    line = PlanLine(
        intent="молоко",
        product={"id": "u-1", "externalProductId": "1", "name": "Молоко"},
        qty=Decimal(1),
        reason="звичне",
        from_history=None,
    )
    plan = _plan()
    plan.lines.append(line)
    kept = runs.remember(plan, owner=ME)

    borrowed = runs.recall(kept.run_id, owner=ME)
    assert borrowed is not None
    borrowed.lines[0].qty = Decimal(9)

    again = runs.recall(kept.run_id, owner=ME)
    assert again is not None
    assert again.lines[0].qty == Decimal(1), "правка нового прогону дісталась старого"


def test_a_recalled_plan_still_shares_the_cards_the_guest_saw() -> None:
    plan = _plan()
    kept = runs.remember(plan, owner=ME)

    borrowed = runs.recall(kept.run_id, owner=ME)
    assert borrowed is not None
    borrowed.swap_cards["7"] = {"name": "Ланка"}

    again = runs.recall(kept.run_id, owner=ME)
    assert again is not None
    assert again.swap_cards == {"7": {"name": "Ланка"}}


def test_leaving_takes_the_plans_along() -> None:
    mine = runs.remember(_plan(), owner=ME)

    runs.forget(ME)

    assert runs.recall(mine.run_id, owner=ME) is None


def test_leaving_takes_only_my_own_plans() -> None:
    mine = runs.remember(_plan(), owner=ME)
    theirs = runs.remember(_plan(), owner=STRANGER)

    runs.forget(ME)

    assert runs.recall(mine.run_id, owner=ME) is None
    assert runs.recall(theirs.run_id, owner=STRANGER) is not None
