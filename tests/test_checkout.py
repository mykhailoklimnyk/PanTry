from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from fastapi import HTTPException

from komora.agent.basket import Assembled, PlanLine
from komora.agent.cart import CartRun, read_cart_by_id
from komora.agent.checkout import (
    CHECKOUT_URL,
    SKIP_AT_HOME,
    SKIP_GONE,
    SKIP_NO_STOCK,
    SKIP_OFF_SHELF,
    SKIP_REMOVED,
    blocker_codes,
    cart_payload,
    edited,
    hand_off,
    promo_lost,
    totals_of,
    warning_codes,
    writable,
)
from komora.agent.executor import BEYOND
from komora.api import runs
from komora.api.app import checkout
from komora.api.schemas import (
    Basket,
    CarryOverState,
    CheckoutExtra,
    CheckoutRequest,
    CheckoutResult,
    RunStats,
)
from komora.auth.session import GuestSession
from komora.core.blockers import BRANCH_MISMATCH
from komora.core.location import Address, Location
from komora.core.silence import Silence
from komora.mcp.client import MCPCallError

CART_ID = "00000000-0000-4000-8000-00000000c0de"
OWNER = GuestSession(access="токен-гостя").owner
SLOT = {"start": "2026-08-16T08:00:00+00:00", "end": "2026-08-16T10:00:00+00:00"}


BRANCH = "00000000-0000-4000-8000-000000000002"


def _product(article: int, name: str, price: float = 50.0) -> dict[str, Any]:
    return {
        "id": f"00000000-0000-4000-8000-{article:012d}",
        "companyId": "00000000-0000-4000-8000-000000000001",
        "branchId": BRANCH,
        "name": name,
        "price": price,
        "externalProductId": article,
    }


def _line(article: int, name: str, **kwargs: Any) -> PlanLine:
    return PlanLine(
        intent=name.lower(),
        product=_product(article, name),
        qty=Decimal(kwargs.pop("qty", 1)),
        reason="звичне",
        from_history=None,
        **kwargs,
    )


async def _snapshot(calculation: dict[str, Any]):
    return await read_cart_by_id(_FakeMCP(calculation=calculation), CART_ID)


def _assembled(lines: list[PlanLine]) -> Assembled:
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


STALE_SLOT = {"start": "2026-08-15T08:00:00+00:00", "end": "2026-08-15T10:00:00+00:00"}

ADDRESS = {"addressType": "flat", "latitude": "49.22", "longitude": "28.45", "flat": "76"}


class _FakeMCP:

    def __init__(
        self,
        validations: list[dict[str, Any]] | None = None,
        cart_slot: dict[str, str] | None = None,
        link: str | None = None,
        calculation: dict[str, Any] | None = None,
        loyalty: dict[str, Any] | None = None,
        rows: list[dict[str, Any]] | None = None,
        shipment_branch: str | None = BRANCH,
        missing_cart: bool = False,
        cart_payload: dict[str, Any] | None = None,
        blind_from: int | None = None,
        batch_lands_then_fails: bool = False,
        shelf: dict[str, list[dict[str, Any]]] | None = None,
    ) -> None:
        self.batch_lands_then_fails = batch_lands_then_fails
        self.blind_from = blind_from
        self.detail_reads = 0
        self.shelf = shelf or {}
        self.silence = Silence()
        self.missing_cart = missing_cart
        self.cart_payload = cart_payload
        self.created = False
        self.shipment_branch = shipment_branch
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.validations = validations or []
        self.cart_slot = cart_slot if cart_slot is not None else STALE_SLOT
        self.link = link
        self.calculation = calculation or {}
        self.loyalty = loyalty
        self.rows = rows if rows is not None else []

    async def call(self, tool: str, arguments: dict[str, Any] | None = None) -> Any:
        self.calls.append((tool, arguments or {}))
        if tool in ("silpo_remove_cart_products", "silpo_add_or_update_cart_products"):
            touched = {
                str(row.get("productId")): row.get("quantity")
                for row in (arguments or {}).get("products") or []
            }
            self.validations = [
                entry
                for entry in self.validations
                if str((entry.get("context") or {}).get("productId")) not in touched
                or (
                    tool == "silpo_add_or_update_cart_products"
                    and (touched[str(entry["context"]["productId"])] or 0)
                    > (entry["context"].get("stock") or 0)
                )
            ]
            if tool == "silpo_remove_cart_products":
                self.rows = [row for row in self.rows if str(row.get("productId")) not in touched]
        if (
            tool == "silpo_add_or_update_cart_products"
            and self.batch_lands_then_fails
            and len(((arguments or {}).get("products")) or []) > 1
        ):
            self.rows.extend(
                {"productId": row["productId"], "quantity": row.get("quantity")}
                for row in (arguments or {})["products"]
            )
            raise MCPCallError(tool, "timeout", attempts=1)
        if tool == "silpo_get_my_shopping_cart":
            if self.missing_cart and not self.created:
                raise MCPCallError(
                    tool, "Error in get-my-shopping-cart: Resource not found", attempts=1
                )
            payload = (
                {"shoppingCartId": CART_ID}
                if self.cart_payload is None
                else dict(self.cart_payload)
            )
        elif tool == "silpo_create_shopping_cart":
            self.created = True
            payload = {"shoppingCartId": CART_ID}
        elif tool == "silpo_find_products_batch":
            payload = {
                "queries": [
                    {"query": q, "products": self.shelf.get(q, [])}
                    for q in (arguments or {}).get("products", [])
                ]
            }
        elif tool == "silpo_get_shopping_cart_by_id":
            self.detail_reads += 1
            if self.blind_from is not None and self.detail_reads >= self.blind_from:
                return type("Outcome", (), {"payload_raw": {}, "payload": {}, "duration_ms": 0})()
            payload = {
                **({"checkoutWebLink": self.link} if self.link else {}),
                **({"loyalty": self.loyalty} if self.loyalty is not None else {}),
                "cart": {
                    "id": CART_ID,
                    "deliveryType": "DeliveryHome",
                    "timeslot": self.cart_slot,
                    "address": ADDRESS,
                    "shipments": [
                        {
                            "id": "ship-1",
                            "companyId": "c",
                            "branchId": self.shipment_branch,
                            "products": list(self.rows),
                        }
                    ],
                    "calculation": {
                        "validations": self.validations,
                        "delivery": {},
                        **self.calculation,
                    },
                },
            }
        else:
            if tool == "silpo_add_or_update_cart_products":
                self.rows.extend(
                    {"productId": row["productId"], "quantity": row.get("quantity")}
                    for row in (arguments or {}).get("products", [])
                )
            payload = {"success": True}
        return type("Outcome", (), {"payload_raw": payload, "payload": payload, "duration_ms": 0})()

    def args_of(self, tool: str) -> dict[str, Any] | None:
        return next((args for name, args in self.calls if name == tool), None)

    @property
    def tools(self) -> list[str]:
        return [name for name, _ in self.calls]

    @property
    def written(self) -> list[dict[str, Any]]:
        for tool, args in self.calls:
            if tool == "silpo_add_or_update_cart_products":
                return list(args["products"])
        return []


def test_lines_without_a_plan_b_go_without_a_mandate():
    lines = [
        _line(101, "Молоко"),
        _line(201, "Кава", needs_approval=True),
        _line(301, "Рис", at_home=True),
        _line(401, "Чай", needs_approval=True, gone=True),
    ]
    going, skipped = writable(lines)
    assert [line.product["name"] for line in going] == ["Молоко", "Кава"]
    assert {skip.name: skip.reason for skip in skipped} == {
        "Рис": SKIP_AT_HOME,
        "Чай": SKIP_GONE,
    }


def test_the_cart_names_the_waiting_line_before_checkout_not_after():
    from komora.agent.basket import NEEDS_APPROVAL_NOTE, to_cart_line

    waiting = to_cart_line(_line(201, "Кава", needs_approval=True))
    assert waiting.needs_approval is True
    assert waiting.explanation == NEEDS_APPROVAL_NOTE
    assert "поїде без мандата" in (waiting.explanation_detail or "")
    assert waiting.explanation_detail and NEEDS_APPROVAL_NOTE not in waiting.explanation_detail

    calm = to_cart_line(_line(101, "Молоко"))
    assert calm.needs_approval is False
    assert calm.explanation != NEEDS_APPROVAL_NOTE


def test_payload_writes_uuids_not_articles():
    [row] = cart_payload([_line(101, "Молоко", qty=2)])

    assert row["productId"] == "00000000-0000-4000-8000-000000000101"
    assert row["companyId"] and row["branchId"]
    assert row["quantity"] == 2
    assert row["addQuantity"] is False


def test_mandate_travels_in_the_comment():
    line = _line(101, "Молоко")
    line.mandate = "якщо немає — Яготинське 2,6%"
    [row] = cart_payload([line])

    assert row["comment"] == "якщо немає — Яготинське 2,6%"


async def test_cart_moves_to_the_slot_it_was_built_for():
    mcp = _FakeMCP()
    await hand_off(mcp, _assembled([_line(101, "Молоко")]))

    args = mcp.args_of("silpo_update_shopping_cart")
    assert args is not None, "слот кошика розійшовся зі слотом збірки — мали виправити"
    assert args["timeslot"] == {"start": SLOT["start"], "end": SLOT["end"]}
    assert args["address"] == ADDRESS
    assert "products" not in args["shipments"][0]
    assert args["shipments"][0]["companyId"] == "c"

    assert mcp.tools.index("silpo_update_shopping_cart") < mcp.tools.index(
        "silpo_add_or_update_cart_products"
    )


class _PickyMCP(_FakeMCP):

    def __init__(self, bad: set[int] | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.bad = {_product(article, "")["id"] for article in (bad or set())}

    async def call(self, tool: str, arguments: dict[str, Any] | None = None) -> Any:
        if tool == "silpo_add_or_update_cart_products":
            products = (arguments or {}).get("products") or []
            if any(str(row.get("productId")) in self.bad for row in products):
                self.calls.append((tool, arguments or {}))
                raise MCPCallError(
                    tool,
                    "Error in add-or-update-cart-products: API returned 400 Bad Request",
                    attempts=1,
                )
        return await super().call(tool, arguments)


async def test_one_rejected_row_does_not_cost_the_whole_cart():
    mcp = _PickyMCP(bad={102})
    result = await hand_off(
        mcp, _assembled([_line(101, "Молоко"), _line(102, "Хліб"), _line(103, "Сир")])
    )

    assert result.written == 2, "решта кошика доїхала"
    rejected = [row for row in result.skipped if "не прийняло" in row.reason]
    assert [row.name for row in rejected] == ["Хліб"], "винний названий поіменно"
    assert "400 Bad Request" in rejected[0].reason, "чужа відповідь їде як є"
    assert mcp.tools.count("silpo_add_or_update_cart_products") == 4


async def test_when_no_row_gets_through_it_is_not_the_rows_fault():
    mcp = _PickyMCP(bad={101, 102})

    with pytest.raises(MCPCallError):
        await hand_off(mcp, _assembled([_line(101, "Молоко"), _line(102, "Хліб")]))


async def test_a_rejected_row_is_not_written_twice():
    mcp = _PickyMCP(bad={102})
    await hand_off(mcp, _assembled([_line(101, "Молоко"), _line(102, "Хліб")]))

    singles = [
        args
        for tool, args in mcp.calls
        if tool == "silpo_add_or_update_cart_products" and len(args["products"]) == 1
    ]
    assert all(row["addQuantity"] is False for args in singles for row in args["products"])


async def test_matching_slot_is_left_alone():
    mcp = _FakeMCP(cart_slot={"start": SLOT["start"], "end": SLOT["end"]})
    await hand_off(mcp, _assembled([_line(101, "Молоко")]))

    assert "silpo_update_shopping_cart" not in mcp.tools


async def test_link_comes_from_the_cart_when_it_gives_one():
    mcp = _FakeMCP(link="https://silpo.ua/checkout-new")
    result = await hand_off(mcp, _assembled([_line(101, "Молоко")]))

    assert result.checkout_web_link == "https://silpo.ua/checkout-new"


async def test_clean_cart_gets_the_checkout_link():
    mcp = _FakeMCP()
    result = await hand_off(mcp, _assembled([_line(101, "Молоко"), _line(102, "Хліб")]))

    assert result.written == 2
    assert result.checkout_web_link == CHECKOUT_URL
    assert not result.blockers
    assert len(mcp.written) == 2


async def test_blocked_cart_gets_no_link():
    mcp = _FakeMCP(
        validations=[
            {"level": "error", "type": "timeslot", "message": "timeslot.not_available"},
            {"level": "info", "type": "order", "message": "order.payment_types.disabled"},
        ]
    )
    result = await hand_off(mcp, _assembled([_line(101, "Молоко")]))

    assert result.checkout_web_link is None
    assert result.blockers == ["timeslot.not_available"]
    assert "timeslot.not_available" in result.summary


def test_repeated_row_errors_collapse_into_one_line():
    codes = blocker_codes(
        [
            {"level": "error", "type": "timeslot", "message": "timeslot.not_found"},
            *(
                {
                    "level": "error",
                    "type": "product",
                    "message": "product.offer.stock.max",
                    "context": {"productId": f"uuid-{n}", "stock": 0},
                }
                for n in range(13)
            ),
            {"level": "info", "type": "order", "message": "order.payment_types.disabled"},
        ]
    )

    assert codes == ["timeslot.not_found", "product.offer.stock.max ×13"]


async def test_nothing_writable_writes_nothing():
    mcp = _FakeMCP()
    result = await hand_off(mcp, _assembled([_line(201, "Кава", at_home=True)]))

    assert result.written == 0
    assert result.checkout_web_link is None
    assert mcp.calls == [], "у кошик не пішло жодного виклику"
    assert len(result.skipped) == 1


async def test_summary_speaks_ukrainian_numerals():
    mcp = _FakeMCP()
    one = await hand_off(mcp, _assembled([_line(101, "Молоко")]))
    assert "1 рядок" in one.summary

    many = await hand_off(_FakeMCP(), _assembled([_line(100 + n, f"Товар {n}") for n in range(5)]))
    assert "5 рядків" in many.summary


CALCULATION = {
    "total": 1392.04,
    "totalAfterDiscounts": 1104.04,
    "certificatesTotal": 0,
    "subTotal": 1153.04,
    "subDiscount": 288.0,
    "productsTotal": 1153.04,
    "delivery": {"total": 89, "totalWeight": 12.5},
}


async def test_totals_come_from_the_cart_not_from_the_plan():
    snapshot = await _snapshot(CALCULATION)
    money = totals_of(snapshot, estimate=Decimal("1253"))

    assert money is not None
    assert money.to_pay == Decimal("1104.04"), "до оплати — totalAfterDiscounts"
    assert money.products == Decimal("1153.04")
    assert money.discount == Decimal("288.0")
    assert money.delivery == Decimal(89)


async def test_estimate_is_shown_only_when_it_disagrees():
    exact = totals_of(await _snapshot(CALCULATION), estimate=Decimal("1104.04"))
    assert exact is not None and exact.estimate is None

    off = totals_of(await _snapshot(CALCULATION), estimate=Decimal("1253"))
    assert off is not None and off.estimate == Decimal("1253")


async def test_rounding_noise_is_not_a_discrepancy():
    close = totals_of(await _snapshot(CALCULATION), estimate=Decimal("1104.50"))
    assert close is not None and close.estimate is None


async def test_pickup_service_fee_is_its_own_row():
    pickup = {
        **CALCULATION,
        "delivery": {**CALCULATION["delivery"], "total": 0},
        "serviceFee": {"total": 9, "subTotal": 9, "subDiscount": 0},
    }
    money = totals_of(await _snapshot(pickup))
    assert money is not None
    assert money.service_fee == Decimal(9)
    assert money.delivery == Decimal(0)


async def test_zero_fee_and_missing_fee_are_different_answers():
    courier = {**CALCULATION, "serviceFee": {"total": 0, "subTotal": 0, "subDiscount": 0}}
    zero = totals_of(await _snapshot(courier))
    assert zero is not None and zero.service_fee == Decimal(0)
    silent = totals_of(await _snapshot(CALCULATION))
    assert silent is not None and silent.service_fee is None


async def test_cart_without_a_calculation_gives_no_numbers():
    assert totals_of(await _snapshot({})) is None


async def test_checkout_reports_the_sum_silpo_will_charge():
    mcp = _FakeMCP(calculation=CALCULATION)
    result = await hand_off(mcp, _assembled([_line(101, "Молоко")]))

    assert result.totals is not None
    assert result.totals.to_pay == Decimal("1104.04")
    assert "до оплати 1104.04 грн" in result.summary


async def test_checkout_without_numbers_says_nothing_about_money():
    mcp = _FakeMCP()
    result = await hand_off(mcp, _assembled([_line(101, "Молоко")]))

    assert result.totals is None
    assert "до оплати" not in result.summary


def test_run_id_leads_back_to_the_plan():
    runs.forget_all()
    plan = _assembled([_line(101, "Молоко")])
    basket = runs.remember(plan, owner=OWNER)

    assert basket.run_id != "test", "id роздає API, а не збірка"
    found = runs.recall(basket.run_id, owner=OWNER)
    assert found is not None
    assert found.basket is plan.basket
    assert [line.product["id"] for line in found.lines] == [
        line.product["id"] for line in plan.lines
    ]


def test_someone_elses_run_looks_exactly_like_a_forgotten_one():
    runs.forget_all()
    mine = runs.remember(_assembled([_line(101, "Молоко")]), owner=OWNER)
    stranger = GuestSession(access="інший-токен").owner

    assert runs.recall(mine.run_id, owner=stranger) is None
    assert runs.recall("такого-немає", owner=stranger) is None
    assert runs.recall(mine.run_id, owner=OWNER) is not None, "свій прогін лишився своїм"


async def test_checkout_of_a_stranger_run_is_a_404_with_the_same_words():
    runs.forget_all()
    mine = runs.remember(_assembled([_line(101, "Молоко")]), owner=OWNER)

    with pytest.raises(HTTPException) as exc:
        await checkout(mine.run_id, GuestSession(access="інший-токен"), api_key=None)

    assert exc.value.status_code == 404
    assert "збери кошик заново" in str(exc.value.detail)


def test_old_runs_fall_out_of_memory():
    runs.forget_all()
    ids = [
        runs.remember(_assembled([_line(100 + n, f"Товар {n}")]), owner=OWNER).run_id
        for n in range(runs.MAX_RUNS + 2)
    ]

    alive = [run_id for run_id in ids if runs.recall(run_id, owner=OWNER) is not None]

    assert len(alive) == runs.MAX_RUNS, f"у пам'яті {len(alive)}, а стеля {runs.MAX_RUNS}"
    assert alive == ids[-runs.MAX_RUNS :], "лишитись мали САМІ ОСТАННІ прогони"


async def test_forgotten_run_says_so_instead_of_writing_something_else():
    runs.forget_all()
    with pytest.raises(HTTPException) as exc:
        await checkout("немає-такого", GuestSession(access="токен-гостя"), api_key=None)

    assert exc.value.status_code == 404
    assert "збери кошик заново" in str(exc.value.detail)


def _cart_row(article: int, name: str, total: str = "119.98") -> dict[str, Any]:
    return {
        "productId": f"00000000-0000-4000-8000-{article:012d}",
        "name": name,
        "quantity": 2,
        "total": total,
    }


async def test_a_cart_with_leftovers_asks_before_touching_anything():
    mcp = _FakeMCP(rows=[_cart_row(909, "Кава з минулого разу")])

    result = await hand_off(mcp, _assembled([_line(101, "Молоко")]))

    assert result.carry_over is not None
    assert result.carry_over.state.value == "asking"
    assert [line.name for line in result.carry_over.lines] == ["Кава з минулого разу"]
    assert result.written == 0
    assert result.checkout_web_link is None
    assert mcp.written == []
    assert "silpo_update_shopping_cart" not in mcp.tools


async def test_the_question_carries_the_number_and_the_money():
    mcp = _FakeMCP(
        rows=[_cart_row(909, "Кава", total="180.00"), _cart_row(910, "Печиво", total="42.50")]
    )

    result = await hand_off(mcp, _assembled([_line(101, "Молоко")]))

    assert result.carry_over is not None
    assert result.carry_over.total == Decimal("222.50")
    assert "2 рядки" in result.summary
    assert "222.5 грн" in result.summary


async def test_a_row_already_in_the_plan_raises_no_question():
    mcp = _FakeMCP(rows=[_cart_row(101, "Молоко")])

    result = await hand_off(mcp, _assembled([_line(101, "Молоко")]))

    assert result.carry_over is None
    assert result.written == 1


async def test_keeping_them_writes_the_plan_and_says_they_are_in_the_sum():
    mcp = _FakeMCP(rows=[_cart_row(909, "Кава", total="180.00")])

    result = await hand_off(mcp, _assembled([_line(101, "Молоко")]), existing=CarryOverState.KEPT)

    assert result.written == 1
    assert "silpo_remove_cart_products" not in mcp.tools
    assert result.carry_over is not None
    assert result.carry_over.state is CarryOverState.KEPT
    assert "лишилось ще 1 рядок поза планом" in result.summary


async def test_starting_over_leaves_the_cart_holding_exactly_the_plan():
    mcp = _FakeMCP(rows=[_cart_row(909, "Кава"), _cart_row(910, "Печиво")])

    result = await hand_off(
        mcp, _assembled([_line(101, "Молоко")]), existing=CarryOverState.REMOVED
    )

    dropped = mcp.args_of("silpo_remove_cart_products")
    assert dropped is not None
    assert [row["productId"] for row in dropped["products"]] == [
        "00000000-0000-4000-8000-000000000909",
        "00000000-0000-4000-8000-000000000910",
    ]
    assert result.carry_over is not None
    assert result.carry_over.state is CarryOverState.REMOVED
    assert "я зняв" in result.summary


async def test_removal_comes_after_the_write_and_never_before():
    mcp = _FakeMCP(rows=[_cart_row(909, "Кава")])

    await hand_off(mcp, _assembled([_line(101, "Молоко")]), existing=CarryOverState.REMOVED)

    assert mcp.tools.index("silpo_add_or_update_cart_products") < mcp.tools.index(
        "silpo_remove_cart_products"
    )


async def test_a_clean_cart_never_asks():
    mcp = _FakeMCP()

    result = await hand_off(mcp, _assembled([_line(101, "Молоко")]))

    assert result.carry_over is None
    assert result.written == 1
    assert "поза планом" not in result.summary


async def test_the_foreign_cart_is_never_asked_about_itself():
    mcp = _FakeMCP(rows=[_cart_row(909, "Кава")])
    plan = _assembled([_line(101, "Молоко")])
    run = CartRun(
        assembled=plan,
        snapshot=await read_cart_by_id(mcp, CART_ID),
        chains={},
        cards={},
    )

    result = await hand_off(mcp, run)

    assert result.carry_over is None
    assert result.written == 1


async def test_the_endpoint_hands_the_guests_answer_down_to_the_write(monkeypatch):
    runs.forget_all()
    guest = GuestSession(access="токен-гостя")
    mine = runs.remember(_assembled([_line(101, "Молоко")]), owner=guest.owner)
    seen: list[CarryOverState] = []

    async def _spy(
        mcp, run, *, grant=None, existing=CarryOverState.ASKING, lines=None, added=None, place=None
    ):
        seen.append(existing)
        return CheckoutResult(written=0, summary="тест")

    monkeypatch.setattr("komora.api.app.hand_off", _spy)
    monkeypatch.setattr("komora.api.app.SilpoMCP", _FakeSilpo)

    await checkout(
        mine.run_id, guest, api_key=None, body=CheckoutRequest(existing=CarryOverState.REMOVED)
    )
    await checkout(mine.run_id, guest, api_key=None)

    assert seen == [CarryOverState.REMOVED, CarryOverState.ASKING]
    runs.forget_all()


class _FakeSilpo:

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs

    async def __aenter__(self) -> _FakeSilpo:
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False


async def test_a_cart_on_another_branch_is_refused_before_a_single_row_is_written():
    mcp = _FakeMCP(shipment_branch="інша-філія")
    result = await hand_off(mcp, _assembled([_line(101, "Молоко")]))

    assert result.written == 0
    assert result.blockers == [BRANCH_MISMATCH]
    assert result.blocker_notes and "магазин" in result.blocker_notes[0]
    assert result.retry_helps is False
    assert "silpo_add_or_update_cart_products" not in mcp.tools, (
        "у чужу філію не поїхало жодного рядка"
    )


async def test_an_unknown_branch_on_either_side_does_not_stop_the_checkout():
    mcp = _FakeMCP(shipment_branch=None)
    result = await hand_off(mcp, _assembled([_line(101, "Молоко")]))
    assert result.written > 0
    assert BRANCH_MISMATCH not in result.blockers


def test_a_quantity_set_on_the_screen_rides_into_the_write_without_a_rebuild():
    lines = [_line(1, "Молоко", qty=2), _line(2, "Хліб", qty=3), _line(3, "Кава")]

    kept, removed = edited(lines, {"1": Decimal(1), "2": Decimal(0), "9": Decimal(5)})

    assert [(line.product["name"], line.qty) for line in kept] == [("Молоко", 1), ("Кава", 1)]
    assert [skip.name for skip in removed] == ["Хліб"]
    assert removed[0].reason == SKIP_REMOVED
    same, none = edited(lines, None)
    assert [line.qty for line in same] == [2, 3, 1] and none == []


async def test_the_write_carries_the_edited_quantity_and_names_the_removed_row():
    mcp = _FakeMCP(link=CHECKOUT_URL)
    plan = _assembled([_line(1, "Молоко", qty=2), _line(2, "Хліб")])

    result = await hand_off(mcp, plan, lines={"1": Decimal(1), "2": Decimal(0)})

    written = next(a for t, a in mcp.calls if t == "silpo_add_or_update_cart_products")
    assert [(p["productId"][-1], p["quantity"]) for p in written["products"]] == [("1", 1)]
    assert result.written == 1
    assert [(s.name, s.reason) for s in result.skipped] == [("Хліб", SKIP_REMOVED)]


async def test_a_line_added_on_the_screen_rides_into_the_write_without_a_rebuild():
    mcp = _FakeMCP(
        link=CHECKOUT_URL,
        shelf={"7": [{**_product(7, "Гречка"), "available": True}], "8": []},
    )
    plan = _assembled([_line(1, "Молоко")])
    plan.slot["deliveryType"] = "DeliveryHome"

    result = await hand_off(
        mcp,
        plan,
        added=[
            CheckoutExtra(externalProductId="7", qty=2, name="Гречка"),
            CheckoutExtra(externalProductId="8", qty=1, name="Кава"),
        ],
    )

    written = next(a for t, a in mcp.calls if t == "silpo_add_or_update_cart_products")
    assert [(p["productId"][-1], p["quantity"]) for p in written["products"]] == [
        ("1", 1),
        ("7", 2),
    ]
    assert result.written == 2
    assert [(s.name, s.reason) for s in result.skipped] == [("Кава", SKIP_OFF_SHELF)]


def _stock_max(article: int, stock: int) -> dict[str, Any]:
    return {
        "level": "error",
        "type": "product",
        "message": "product.offer.stock.max",
        "context": {"productId": _product(article, "x")["id"], "stock": stock},
    }


async def test_a_row_with_zero_stock_is_removed_after_the_write_instead_of_blocking_the_cart():
    mcp = _FakeMCP(link=CHECKOUT_URL, validations=[_stock_max(2, 0)])
    plan = _assembled([_line(1, "Молоко"), _line(2, "Салат")])

    result = await hand_off(mcp, plan)

    removed = next(a for t, a in mcp.calls if t == "silpo_remove_cart_products")
    assert [p["productId"][-1] for p in removed["products"]] == ["2"]
    assert result.blockers == [] and result.written == 1
    assert [(s.name, s.reason) for s in result.skipped] == [("Салат", SKIP_NO_STOCK)]
    assert any(step.id == "step-stock-fit" for step in result.trace)
    assert result.checkout_web_link is not None, "блокер знято -- дорога до оформлення є"


async def test_a_quantity_above_the_stock_is_cut_to_the_shelf_after_the_write():
    mcp = _FakeMCP(link=CHECKOUT_URL, validations=[_stock_max(1, 2)])
    plan = _assembled([_line(1, "Молоко", qty=5)])

    result = await hand_off(mcp, plan)

    writes = [a for t, a in mcp.calls if t == "silpo_add_or_update_cart_products"]
    assert writes[-1]["products"][0]["quantity"] == 2
    assert result.stock_cut == ["Молоко: на полиці лише 2, стільки й узяв"]
    assert result.written == 1 and result.blockers == []


async def test_the_re_written_row_carries_a_mandate_that_fits_the_field():
    from komora.core.mandate import COMMENT_MAX

    long = "якщо немає — " + "; ".join(
        f"ланка {n} з дуже довгою назвою товару {n}" for n in range(12)
    )
    assert len(long) > COMMENT_MAX, "інакше тест не міряє нічого"
    mcp = _FakeMCP(link=CHECKOUT_URL, validations=[_stock_max(1, 2)])

    await hand_off(mcp, _assembled([_line(1, "Молоко", qty=5, mandate=long)]))

    writes = [a for t, a in mcp.calls if t == "silpo_add_or_update_cart_products"]
    assert len(writes[-1]["products"][0]["comment"]) <= COMMENT_MAX


def _sale_row(article: int, name: str, *, price: str, old: str | None) -> dict[str, Any]:
    return {**_cart_row(article, name), "price": price, "oldPrice": old}


def test_a_sale_line_names_itself_when_the_reread_cart_shows_no_sale():
    beer = _line(501, "Пиво Hike", promo=True)
    milk = _line(101, "Молоко")
    rows = [
        _sale_row(501, "Пиво Hike", price="50.99", old=None),
        _sale_row(101, "Молоко", price="53.49", old=None),
    ]
    assert promo_lost([beer, milk], rows) == ["Пиво Hike"]


def test_a_sale_line_stays_quiet_while_the_sale_holds():
    beer = _line(501, "Пиво Hike", promo=True)
    rows = [_sale_row(501, "Пиво Hike", price="29.99", old="50.99")]
    assert promo_lost([beer], rows) == []


def test_a_sale_line_missing_from_the_cart_is_a_blocker_not_a_lost_sale():
    beer = _line(501, "Пиво Hike", promo=True)
    assert promo_lost([beer], []) == []


def test_the_row_is_found_by_the_article_in_its_slug_too():
    beer = _line(501, "Пиво Hike", promo=True)
    row = {
        "productId": "інший-uuid",
        "slug": "pyvo-hike-501",
        "name": "Пиво Hike",
        "price": "50.99",
    }
    assert promo_lost([beer], [row]) == ["Пиво Hike"]


async def test_the_hand_off_reports_the_sale_that_vanished_while_writing():
    mcp = _FakeMCP(
        link=CHECKOUT_URL,
        rows=[_sale_row(501, "Пиво Hike", price="50.99", old=None)],
    )
    plan = _assembled([_line(501, "Пиво Hike", promo=True)])

    result = await hand_off(mcp, plan, existing=CarryOverState.KEPT)

    assert result.written == 1
    assert result.promo_gone == ["Пиво Hike"]
    assert result.checkout_web_link == CHECKOUT_URL


PLACE = Location(
    branch_id=BRANCH,
    address=Address(
        label="Вінниця, вул. Соборна, 1, кв. 2",
        latitude=49.22,
        longitude=28.45,
        kind="flat",
        city="Вінниця",
        street="вулиця Соборна",
        house="1",
    ),
)


async def test_a_missing_cart_is_created_under_the_address_and_the_plan_slot():
    mcp = _FakeMCP(link=CHECKOUT_URL, missing_cart=True)
    plan = _assembled([_line(101, "Молоко")])
    plan.branch_id = BRANCH
    plan.slot = {**SLOT, "deliveryType": "DeliveryHome"}

    result = await hand_off(mcp, plan, existing=CarryOverState.KEPT, place=PLACE)

    created = mcp.args_of("silpo_create_shopping_cart")
    assert created is not None
    assert created["addressType"] == "flat"
    assert (created["latitude"], created["longitude"]) == (49.22, 28.45)
    assert created["branchId"] == BRANCH and created["deliveryType"] == "DeliveryHome"
    assert created["timeslot"] == {"start": SLOT["start"], "end": SLOT["end"]}
    assert created["city"] == "Вінниця" and created["house"] == "1"
    assert mcp.tools.index("silpo_create_shopping_cart") < mcp.tools.index(
        "silpo_add_or_update_cart_products"
    )
    assert result.written == 1
    assert result.summary.startswith(
        "кошика в акаунті ще не було — створив під твою адресу і слот."
    )


async def test_without_an_address_the_missing_cart_stays_the_same_refusal():
    mcp = _FakeMCP(link=CHECKOUT_URL, missing_cart=True)
    with pytest.raises(Exception, match="кошик у «Сільпо» порожній"):
        await hand_off(mcp, _assembled([_line(101, "Молоко")]), place=None)
    assert "silpo_create_shopping_cart" not in mcp.tools
    bare = Location(branch_id=BRANCH, address=None)
    with pytest.raises(Exception, match="кошик у «Сільпо» порожній"):
        await hand_off(mcp, _assembled([_line(101, "Молоко")]), place=bare)


async def test_a_found_address_without_a_house_does_not_create_a_cart():
    street = Location(
        branch_id=BRANCH,
        address=Address(label="Київ, вулиця Хрещатик", latitude=50.44, longitude=30.52),
    )
    mcp = _FakeMCP(link=CHECKOUT_URL, missing_cart=True)
    plan = _assembled([_line(101, "Молоко")])
    plan.branch_id = BRANCH
    plan.slot = {**SLOT, "deliveryType": "DeliveryHome"}
    with pytest.raises(Exception, match="немає номера будинку"):
        await hand_off(mcp, plan, existing=CarryOverState.KEPT, place=street)
    assert "silpo_create_shopping_cart" not in mcp.tools


async def test_a_saved_address_without_a_house_still_creates_the_cart():
    saved = Location(
        branch_id=BRANCH,
        address=Address(label="Дім", latitude=49.22, longitude=28.45, id="saved-1"),
    )
    mcp = _FakeMCP(link=CHECKOUT_URL, missing_cart=True)
    plan = _assembled([_line(101, "Молоко")])
    plan.branch_id = BRANCH
    plan.slot = {**SLOT, "deliveryType": "DeliveryHome"}
    await hand_off(mcp, plan, existing=CarryOverState.KEPT, place=saved)
    assert "silpo_create_shopping_cart" in mcp.tools


async def test_a_silent_cart_answer_is_not_a_missing_cart():
    mcp = _FakeMCP(link=CHECKOUT_URL, cart_payload={})
    with pytest.raises(Exception, match="мовчання магазину"):
        await hand_off(mcp, _assembled([_line(101, "Молоко")]), place=PLACE)
    assert "silpo_create_shopping_cart" not in mcp.tools


async def test_exists_false_is_still_a_missing_cart():
    mcp = _FakeMCP(link=CHECKOUT_URL, cart_payload={"exists": False})
    plan = _assembled([_line(101, "Молоко")])
    plan.branch_id = BRANCH
    plan.slot = {**SLOT, "deliveryType": "DeliveryHome"}

    result = await hand_off(mcp, plan, existing=CarryOverState.KEPT, place=PLACE)

    assert "silpo_create_shopping_cart" in mcp.tools
    assert result.written == 1


def test_the_quantity_we_overwrite_names_itself():
    from komora.agent.checkout import qty_overwritten

    rows = [
        {"productId": _product(101, "Молоко")["id"], "quantity": 3},
        {"productId": _product(102, "Хліб")["id"], "quantity": 1},
    ]
    said = qty_overwritten(rows, [_line(101, "Молоко"), _line(102, "Хліб")])

    assert said == ["Молоко: у кошику було 3, поставив 1"]


async def test_the_overwritten_quantity_reaches_the_guest():
    mcp = _FakeMCP(
        link=CHECKOUT_URL, rows=[{"productId": _product(101, "Молоко")["id"], "quantity": 3}]
    )

    result = await hand_off(
        mcp, _assembled([_line(101, "Молоко")]), existing=CarryOverState.KEPT, place=PLACE
    )

    assert result.written == 1
    assert "у «Сільпо» там було інше число" in result.summary
    assert any(step.id == "step-qty-reset" for step in result.trace)


async def test_a_batch_that_landed_before_it_failed_is_not_written_again():
    mcp = _FakeMCP(link=CHECKOUT_URL, batch_lands_then_fails=True)

    result = await hand_off(
        mcp,
        _assembled([_line(101, "Молоко"), _line(102, "Хліб")]),
        existing=CarryOverState.KEPT,
        place=PLACE,
    )

    writes = [args for tool, args in mcp.calls if tool == "silpo_add_or_update_cart_products"]
    assert len(writes) == 1, "поштучний прохід переписував те, що вже лежить у кошику"
    assert result.written == 2
    assert result.skipped == []


async def test_the_same_slot_written_two_ways_is_not_a_mismatch():
    mcp = _FakeMCP(
        link=CHECKOUT_URL,
        cart_slot={
            "start": SLOT["start"].replace("+00:00", "Z"),
            "end": SLOT["end"].replace("+00:00", "Z"),
        },
    )

    result = await hand_off(
        mcp, _assembled([_line(101, "Молоко")]), existing=CarryOverState.KEPT, place=PLACE
    )

    assert "silpo_update_shopping_cart" not in mcp.tools, "зайвий запис у чужий кошик"
    assert "план збирався на" not in result.summary


async def test_a_write_step_that_never_happened_is_not_written_zero(monkeypatch):
    from komora.agent import checkout as checkout_module

    def _broken(*_args: Any, **_kwargs: Any):
        raise ValueError("порт зламався всередині кроку")

    monkeypatch.setattr(checkout_module, "write_rows", _broken)
    mcp = _FakeMCP(link=CHECKOUT_URL)

    with pytest.raises(Exception, match="крок запису в кошик не виконався"):
        await hand_off(
            mcp, _assembled([_line(101, "Молоко")]), existing=CarryOverState.KEPT, place=PLACE
        )


async def test_a_dead_token_is_fatal_for_the_handover_too(monkeypatch):
    from komora.agent import checkout as checkout_module
    from komora.mcp.client import TokenRejected as _TokenRejected

    def _dead(*_args: Any, **_kwargs: Any):
        raise _TokenRejected("silpo_add_or_update_cart_products", "HTTP 401", attempts=1)

    monkeypatch.setattr(checkout_module, "write_rows", _dead)
    mcp = _FakeMCP(link=CHECKOUT_URL)

    with pytest.raises(_TokenRejected):
        await hand_off(
            mcp, _assembled([_line(101, "Молоко")]), existing=CarryOverState.KEPT, place=PLACE
        )


async def test_a_cart_answer_without_contents_stops_the_write():
    mcp = _FakeMCP(link=CHECKOUT_URL, blind_from=1)
    with pytest.raises(Exception, match="наосліп"):
        await hand_off(mcp, _assembled([_line(101, "Молоко")]), place=PLACE)
    assert "silpo_add_or_update_cart_products" not in mcp.tools


async def test_a_silent_reread_holds_back_the_checkout_link():
    from komora.agent.checkout import UNSEEN_NOTE

    mcp = _FakeMCP(link=CHECKOUT_URL, blind_from=2)

    result = await hand_off(
        mcp, _assembled([_line(101, "Молоко")]), existing=CarryOverState.KEPT, place=PLACE
    )

    assert result.written == 1, "запис відбувся, і звіт мусить це сказати"
    assert result.checkout_web_link is None
    assert UNSEEN_NOTE in result.summary


async def test_an_existing_cart_is_never_recreated():
    mcp = _FakeMCP(link=CHECKOUT_URL)
    result = await hand_off(mcp, _assembled([_line(101, "Молоко")]), place=PLACE)
    assert "silpo_create_shopping_cart" not in mcp.tools
    assert not result.summary.startswith("кошика в акаунті ще не було")


def test_warning_codes_take_only_warnings_and_count_repeats():
    validations = [
        {"level": "warning", "type": "product", "message": "product.offer.price.changed"},
        {"level": "warning", "type": "product", "message": "product.offer.price.changed"},
        {"level": "error", "type": "product", "message": "product.offer.stock.max"},
        {"level": "warning", "type": "order", "message": "order.something.new"},
        {"level": "warning", "type": "order"},
    ]
    assert warning_codes(validations) == ["product.offer.price.changed ×2", "order.something.new"]
    assert blocker_codes(validations) == ["product.offer.stock.max"]


async def test_the_hand_off_reports_warnings_and_still_hands_the_link():
    mcp = _FakeMCP(
        link=CHECKOUT_URL,
        validations=[
            {"level": "warning", "type": "product", "message": "product.offer.price.changed"},
            {"level": "warning", "type": "order", "message": "order.delivery.late"},
        ],
    )
    result = await hand_off(mcp, _assembled([_line(101, "Молоко")]), existing=CarryOverState.KEPT)
    assert result.blockers == [] and result.checkout_web_link == CHECKOUT_URL
    assert result.warnings == [
        "ціна змінилась між збіркою і записом",
        "«Сільпо» попереджає: order.delivery.late",
    ]


async def test_a_row_that_did_not_reach_the_cart_is_named_in_the_summary():

    class _Losing(_FakeMCP):
        async def call(self, tool, arguments=None):
            outcome = await super().call(tool, arguments)
            if tool == "silpo_add_or_update_cart_products":
                self.rows.pop()
            return outcome

    mcp = _Losing()
    result = await hand_off(mcp, _assembled([_line(101, "Молоко"), _line(202, "Сир")]))

    assert "мета НЕ досягнута" in result.summary
    assert "не доїхало 1" in result.summary
    assert result.written == 2


async def test_the_reread_after_a_write_is_the_executors_own_step_and_signs_itself():
    mcp = _FakeMCP()
    result = await hand_off(mcp, _assembled([_line(101, "Молоко")]))

    ids = [step.id for step in result.trace]
    assert ids == ["step-write", "step-reread"], "передача звітує обома кроками"

    write = result.trace[0]
    assert "у кошик поїхало 1" in write.result_summary

    reread = result.trace[1]
    assert reread.result_summary.startswith(BEYOND), (
        "перечитування -- крок ВИКОНАВЦЯ, а не плану, і підпис це єдине, "
        "чим воно від планового відрізняється"
    )
    assert "блокерів немає" in reread.result_summary


async def test_an_early_refusal_carries_no_trace_because_nothing_was_handed_over():
    result = await hand_off(_FakeMCP(), _assembled([]))

    assert result.written == 0
    assert result.trace == []


async def test_the_bonus_balance_is_reported_as_a_number_and_never_written():
    mcp = _FakeMCP(loyalty={"bonusAvailable": 340, "bonusTotal": 340, "isEnabled": True})

    result = await hand_off(mcp, _assembled([_line(101, "Молоко")]), existing=CarryOverState.KEPT)

    assert result.bonus_available == Decimal(340)
    assert not any("bonusRequested" in args for _tool, args in mcp.calls)


async def test_no_bonuses_is_not_a_zero():
    mcp = _FakeMCP(loyalty={"bonusAvailable": 0, "bonusTotal": 0.65, "isEnabled": True})

    result = await hand_off(mcp, _assembled([_line(101, "Молоко")]), existing=CarryOverState.KEPT)

    assert result.bonus_available is None


def test_a_mandate_longer_than_the_comment_field_is_cut_on_a_separator():
    from komora.core.mandate import COMMENT_MAX, fit_comment

    short = "якщо немає — Морозиво PREMIA вершкове"
    assert fit_comment(short) == short
    long = "якщо немає — " + "; ".join(
        f"ланка {n} з дуже довгою назвою товару {n}" for n in range(12)
    )
    cut = fit_comment(long)
    assert len(cut) <= COMMENT_MAX
    assert cut.startswith("якщо немає — ланка 0")
    assert not cut.endswith(";") and not cut.endswith(" ")


def test_a_mandate_missing_from_the_reread_cart_is_named_by_row() -> None:
    from komora.agent.checkout import mandates_lost
    from komora.core.mandate import fit_comment

    long = "якщо немає — " + ", потім ".join(
        f"Вода мінеральна №{n} газована сильно" for n in range(9)
    )
    milk = _line(1, "Молоко", mandate="якщо немає — інше 2,5%")
    water = _line(2, "Вода", mandate=long)
    bare = _line(3, "Лимон", mandate=None)
    rows = [
        {"productId": milk.product["id"], "comment": "якщо немає — інше 2,5%"},
        {"productId": water.product["id"], "comment": ""},
        {"productId": bare.product["id"]},
    ]
    assert mandates_lost([milk, water, bare], rows) == ["Вода"]
    rows[1]["comment"] = fit_comment(long)
    assert mandates_lost([milk, water, bare], rows) == []
    assert mandates_lost([milk, water], rows[:1]) == []


async def test_a_line_without_an_agreed_swap_is_written_and_named():
    mcp = _FakeMCP()
    result = await hand_off(
        mcp,
        _assembled([_line(101, "Молоко"), _line(201, "Кава", needs_approval=True)]),
    )
    assert result.written == 2
    assert result.unmandated == ["Кава"]
    assert "без мандата: 1 (заміну не погоджено)" in result.summary
    assert result.skipped == []
