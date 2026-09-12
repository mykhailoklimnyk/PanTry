from __future__ import annotations

import json
from dataclasses import replace
from decimal import Decimal
from typing import Any

from komora.agent import correction, swaps
from komora.agent.basket import Assembled, PlanLine, Tracer
from komora.agent.cart import (
    CartRun,
    apply_rewrites,
    assemble_cart,
    dropped_rows,
    read_cart_by_id,
    with_plan,
)
from komora.agent.checkout import hand_off
from komora.agent.llm import Meter
from komora.agent.refill import _rebuilt as refill_rebuilt
from komora.api.schemas import (
    Basket,
    BuildRequest,
    CorrectionRequest,
    RunStats,
    SwapDecision,
)
from komora.config import Settings
from komora.core.revalidation import Line, Rewrite, Verdict
from komora.core.substitution import Alternative, Source
from komora.mcp.client import SilpoMCP

CART_ID = "00000000-0000-4000-8000-00000000c0de"

PLAN_SLOT = {
    "start": "2026-08-15T06:00:00+00:00",
    "end": "2026-08-15T08:00:00+00:00",
    "deliveryType": "DeliveryHome",
}

MOVED_SLOT = {"start": "2026-08-16T10:00:00+00:00", "end": "2026-08-16T12:00:00+00:00"}

ADDRESS = {"addressType": "flat", "latitude": "49.22", "longitude": "28.45", "flat": "76"}


def _uuid(n: int) -> str:
    return f"00000000-0000-4000-8000-{n:012d}"


def _row(article: int, name: str, qty: float = 1, stock: int = 20) -> dict[str, Any]:
    return {
        "productId": _uuid(article),
        "companyId": _uuid(1),
        "branchId": _uuid(2),
        "slug": f"tovar-{article}",
        "name": name,
        "quantity": qty,
        "price": 50.0,
        "total": 50.0 * qty,
        "stock": stock,
        "weighted": False,
        "addToBasketStep": 1,
        "comment": None,
    }


class FakeCart:

    def __init__(
        self,
        rows: list[dict[str, Any]] | None = None,
        *,
        slot: dict[str, str] | None = None,
    ) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.rows = rows if rows is not None else []
        self.slot = dict(slot or PLAN_SLOT)

    async def call(self, tool: str, arguments: dict[str, Any] | None = None) -> Any:
        self.calls.append((tool, arguments or {}))
        if tool == "silpo_get_my_shopping_cart":
            payload: dict[str, Any] = {"shoppingCartId": CART_ID}
        elif tool == "silpo_get_shopping_cart_by_id":
            payload = {
                "checkoutWebLink": "https://silpo.ua/checkout-new",
                "cart": {
                    "id": CART_ID,
                    "deliveryType": "DeliveryHome",
                    "timeslot": {"start": self.slot["start"], "end": self.slot["end"]},
                    "address": ADDRESS,
                    "shipments": [
                        {
                            "id": "ship-1",
                            "companyId": _uuid(1),
                            "branchId": _uuid(2),
                            "products": list(self.rows),
                        }
                    ],
                    "calculation": {"validations": [], "delivery": {}},
                },
            }
        else:
            payload = {"success": True}
        return type("Outcome", (), {"payload_raw": payload, "payload": payload})()

    @property
    def tools(self) -> list[str]:
        return [name for name, _ in self.calls]

    def args_of(self, tool: str) -> dict[str, Any] | None:
        return next((args for name, args in self.calls if name == tool), None)


def _line(article: int, name: str, **kwargs: Any) -> PlanLine:
    return PlanLine(
        intent=name.lower(),
        product={
            "id": _uuid(article),
            "companyId": _uuid(1),
            "branchId": _uuid(2),
            "externalProductId": str(article),
            "name": name,
            "price": 50.0,
        },
        qty=Decimal(1),
        reason="звичне",
        from_history=None,
        **kwargs,
    )


def _assembled(lines: list[PlanLine], slot: dict[str, Any] | None = None) -> Assembled:
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
    return Assembled(basket=basket, lines=lines, unresolved=[], slot=dict(slot or PLAN_SLOT))


async def _cart_run(mcp: FakeCart, lines: list[PlanLine], **kwargs: Any) -> CartRun:
    snapshot = await read_cart_by_id(mcp, CART_ID)
    mcp.calls.clear()
    return CartRun(assembled=_assembled(lines), snapshot=snapshot, chains={}, cards={}, **kwargs)


def _rewrite(article: int, *, replacement: str | None, keep: int = 0) -> Rewrite:
    alternative = (
        Alternative(
            external_product_id=replacement,
            name="Заміна",
            source=Source.HISTORY,
            price=Decimal(60),
        )
        if replacement
        else None
    )
    return Rewrite(
        line=Line(
            external_product_id=str(article),
            product_id=_uuid(article),
            name="Оригінал",
            quantity=Decimal(1),
        ),
        verdict=Verdict.GONE if keep == 0 else Verdict.SHORT,
        keep_quantity=Decimal(keep),
        replacement=alternative,
        replacement_quantity=Decimal(1),
        link_index=1 if alternative else 0,
        needs_approval=alternative is None,
        note="немає у філії",
    )


def test_a_gone_original_with_a_replacement_is_dropped():
    plan = [_rewrite(201, replacement="202")]
    assert dropped_rows(plan, {"202": {"id": _uuid(202)}}) == (_uuid(201),)


def test_a_replacement_without_a_card_leaves_the_original_alone():
    assert dropped_rows([_rewrite(201, replacement="202")], {}) == ()


def test_a_row_that_only_shrank_is_kept_not_dropped():
    assert dropped_rows([_rewrite(201, replacement="202", keep=1)], {"202": {}}) == ()


def test_a_row_without_a_plan_b_is_never_dropped():
    assert dropped_rows([_rewrite(201, replacement=None)], {"202": {}}) == ()


async def test_the_dead_original_leaves_only_after_its_replacement_is_written():
    mcp = FakeCart()
    snapshot = await read_cart_by_id(mcp, CART_ID)
    mcp.calls.clear()

    await apply_rewrites(mcp, snapshot, [_line(202, "Заміна")], drops=(_uuid(201),))

    assert mcp.tools == ["silpo_add_or_update_cart_products", "silpo_remove_cart_products"]
    assert mcp.args_of("silpo_remove_cart_products") == {
        "shoppingCartId": CART_ID,
        "products": [{"productId": _uuid(201)}],
    }


async def test_a_drop_alone_is_still_worth_a_call():
    mcp = FakeCart()
    snapshot = await read_cart_by_id(mcp, CART_ID)
    mcp.calls.clear()

    await apply_rewrites(mcp, snapshot, [], drops=(_uuid(201),))

    assert mcp.tools == ["silpo_remove_cart_products"]


async def test_nothing_at_all_still_costs_no_calls():
    mcp = FakeCart()
    snapshot = await read_cart_by_id(mcp, CART_ID)
    mcp.calls.clear()

    written = await apply_rewrites(mcp, snapshot, [], drops=())

    assert mcp.calls == []
    assert written["success"] is False


def _fixture_cart(tmp_path) -> SilpoMCP:
    slot = {
        **PLAN_SLOT,
        "available": True,
        "deliveryCost": 89,
        "deliveryCostMap": [{"cost": 59, "fromOrderCost": 1199}],
        "minOrderCost": 599,
        "maxWeight": 50,
    }

    def product(article: int, name: str, price: float, stock: int) -> dict[str, Any]:
        return {
            "id": _uuid(article),
            "name": name,
            "slug": f"tovar-{article}",
            "price": price,
            "stock": stock,
            "available": True,
            "weighted": False,
            "step": 1,
            "displayRatio": "950г",
            "companyId": _uuid(1),
            "branchId": _uuid(2),
            "externalProductId": article,
        }

    rows = [
        _row(101, "Молоко Ферма 2,5%", qty=2, stock=20),
        _row(201, "Чай Pickwick чорний", stock=0),
        _row(401, "Сир Джюгас 12 міс.", stock=15),
    ]
    (tmp_path / "silpo_get_my_shopping_cart.json").write_text(
        json.dumps({"shoppingCartId": CART_ID}), encoding="utf-8"
    )
    (tmp_path / "silpo_get_shopping_cart_by_id.json").write_text(
        json.dumps(
            {
                "cart": {
                    "id": CART_ID,
                    "deliveryType": "DeliveryHome",
                    "timeslot": {"start": PLAN_SLOT["start"], "end": PLAN_SLOT["end"]},
                    "shipments": [{"companyId": _uuid(1), "branchId": _uuid(2), "products": rows}],
                    "calculation": {
                        "productsTotal": 300,
                        "delivery": {"total": 89, "totalWeight": 2.19},
                        "validations": [],
                    },
                }
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "silpo_get_time_slots.json").write_text(
        json.dumps({"slots": [slot]}), encoding="utf-8"
    )
    (tmp_path / "silpo_get_my_offline_orders.json").write_text(
        json.dumps({"orders": []}), encoding="utf-8"
    )
    (tmp_path / "silpo_find_products_batch.json").write_text(
        json.dumps(
            {
                "queries": [
                    {"query": "Чай", "products": [product(202, "Чай Pickwick зелений", 67.49, 18)]},
                    {"query": "Сир", "products": [product(402, "Сир Grana Padano", 59.0, 12)]},
                    {"query": "101", "products": [product(101, "Молоко Ферма 2,5%", 53.49, 20)]},
                    {"query": "201", "products": []},
                    {"query": "401", "products": []},
                ]
            }
        ),
        encoding="utf-8",
    )
    return SilpoMCP(settings=Settings.model_construct(), fixtures_dir=tmp_path)


async def test_the_run_names_which_rows_have_to_leave_the_cart(tmp_path):
    run = await assemble_cart(
        _fixture_cart(tmp_path),
        llm=None,
        request=BuildRequest.model_validate({"mode": "week", "source": "cart"}),
    )

    assert set(run.drops) == {_uuid(201), _uuid(401)}


async def test_a_swap_decision_keeps_the_run_a_foreign_cart():
    mcp = FakeCart(rows=[_row(101, "Молоко")])
    run = await _cart_run(mcp, [_line(101, "Молоко")])

    after = swaps.apply(run, [])

    assert isinstance(after, CartRun)
    assert after.snapshot is run.snapshot


async def test_a_correction_keeps_the_run_a_foreign_cart():
    mcp = FakeCart(rows=[_row(101, "Молоко"), _row(201, "Чай")])
    run = await _cart_run(mcp, [_line(101, "Молоко"), _line(201, "Чай")])

    after, _ = correction.apply(
        run, CorrectionRequest(externalProductId="201", action="never_again")
    )

    assert isinstance(after, CartRun)
    assert [line.product["name"] for line in after.assembled.lines] == ["Молоко"]


async def test_a_refill_keeps_the_run_a_foreign_cart():
    mcp = FakeCart(rows=[_row(101, "Молоко")])
    run = await _cart_run(mcp, [_line(101, "Молоко")])

    after = refill_rebuilt(
        run,
        run.assembled,
        Tracer(),
        added=[_line(301, "Кава")],
        attempted=["кава"],
        unresolved=[],
        duration_ms=1,
        agent_ms=0,
        model="тест",
        spent=Meter(),
    )

    assert isinstance(after, CartRun)
    assert len(after.assembled.lines) == 2


async def test_the_chain_named_by_the_guest_reaches_the_revalidation():
    mcp = FakeCart(rows=[_row(101, "Молоко")])
    line = _line(101, "Молоко")
    line.considered = [
        {"externalProductId": "102", "name": "Молоко Яготинське", "price": 75.99, "stock": 30}
    ]
    run = await _cart_run(mcp, [line])

    after = swaps.apply(
        run,
        [SwapDecision(externalProductId="101", chain=["102"], policy="substitute")],
    )

    assert isinstance(after, CartRun)
    assert [link.external_product_id for link in after.chains["101"]] == ["102"]


async def test_a_touched_foreign_cart_is_never_asked_about_its_own_rows():
    mcp = FakeCart(rows=[_row(101, "Молоко"), _row(201, "Чай")])
    run = await _cart_run(mcp, [_line(101, "Молоко"), _line(201, "Чай", needs_approval=True)])

    result = await hand_off(mcp, swaps.apply(run, []))

    assert result.carry_over is None, "у чужого кошика спитали про його ж рядки"
    assert result.written == 2
    assert result.unmandated == ["Чай"]
    assert "silpo_add_or_update_cart_products" in mcp.tools


async def test_a_slot_moved_after_the_run_is_aligned_back():
    mcp = FakeCart(rows=[_row(101, "Молоко")])
    run = await _cart_run(mcp, [_line(101, "Молоко")])
    mcp.slot = dict(MOVED_SLOT)

    await hand_off(mcp, run)

    aligned = mcp.args_of("silpo_update_shopping_cart")
    assert aligned is not None, "слот входу Б не вирівнювався жодного разу"
    assert aligned["timeslot"] == {"start": PLAN_SLOT["start"], "end": PLAN_SLOT["end"]}


async def test_an_unmoved_slot_costs_no_write():
    mcp = FakeCart(rows=[_row(101, "Молоко")])
    run = await _cart_run(mcp, [_line(101, "Молоко")])

    await hand_off(mcp, run)

    assert "silpo_update_shopping_cart" not in mcp.tools


async def test_the_slot_is_judged_by_the_cart_not_by_the_snapshot():
    mcp = FakeCart(rows=[_row(101, "Молоко")])
    run = await _cart_run(mcp, [_line(101, "Молоко")])
    assert run.snapshot.timeslot_start == PLAN_SLOT["start"], "знімок і план розійшлись"
    mcp.slot = dict(MOVED_SLOT)

    await hand_off(mcp, run)

    assert "silpo_update_shopping_cart" in mcp.tools


async def test_a_plain_run_stays_plain():
    plan = _assembled([_line(101, "Молоко")])
    assert with_plan(plan, plan) is plan


async def test_chains_are_merged_not_replaced():
    mcp = FakeCart(rows=[_row(101, "Молоко")])
    run = await _cart_run(mcp, [_line(101, "Молоко")])
    old = Alternative("102", "Стара ланка", Source.HISTORY, price=Decimal(60))
    new = Alternative("302", "Нова ланка", Source.HISTORY, price=Decimal(70))
    run = replace(run, chains={"101": (old,), "201": (old,)})

    after = with_plan(run, run.assembled, chains={"101": (new,)})

    assert isinstance(after, CartRun)
    assert after.chains["101"] == (new,), "рішення гостя не перекрило ланцюжок збірки"
    assert after.chains["201"] == (old,), "решта ланцюжків зникла разом з оновленням"
