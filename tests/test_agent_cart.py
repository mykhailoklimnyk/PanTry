import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from komora.agent.basket import (
    CHAIN_TOKENS_PER_ROW,
    KIND_SCHEMA,
    NAMING_TOKENS_PER_NAME,
    SLOT_LOOKAHEAD,
    AssemblyError,
    PlanLine,
    to_cart_line,
)
from komora.agent.cart import (
    CHAIN_SCHEMA,
    _product_from_row,
    article_of,
    assemble_cart,
    flagged_products,
)
from komora.api.schemas import BuildRequest, Reason
from komora.config import Settings
from komora.core.feedback import Changes, Contacts, collector_swaps
from komora.mcp.client import SilpoMCP

CART_ID = "00000000-0000-4000-8000-00000000c0de"

SLOT = {
    "start": "2026-08-15T06:00:00+00:00",
    "end": "2026-08-15T08:00:00+00:00",
    "available": True,
    "deliveryType": "DeliveryHome",
    "deliveryCost": 89,
    "deliveryCostMap": [
        {"cost": 59, "fromOrderCost": 1199},
        {"cost": 1, "fromOrderCost": 1699},
    ],
    "minOrderCost": 599,
    "maxWeight": 50,
}


def _row(article: int, name: str, price: float, stock: int, qty: float = 1) -> dict:
    return {
        "productId": f"00000000-0000-4000-8000-{article:012d}",
        "companyId": "00000000-0000-4000-8000-000000000001",
        "branchId": "00000000-0000-4000-8000-000000000002",
        "slug": f"tovar-{article}",
        "name": name,
        "image": None,
        "ratio": "950г",
        "quantity": qty,
        "price": price,
        "oldPrice": None,
        "subTotal": price * qty,
        "subDiscount": 0,
        "total": price * qty,
        "stock": stock,
        "weighted": False,
        "addToBasketStep": 1,
        "comment": None,
    }


def _product(article: int, name: str, price: float, stock: int) -> dict:
    return {
        "id": f"00000000-0000-4000-8000-{article:012d}",
        "name": name,
        "slug": f"tovar-{article}",
        "price": price,
        "oldPrice": None,
        "stock": stock,
        "available": True,
        "image": None,
        "weighted": False,
        "step": 1,
        "displayRatio": "950г",
        "companyId": "00000000-0000-4000-8000-000000000001",
        "branchId": "00000000-0000-4000-8000-000000000002",
        "externalProductId": article,
    }


def _cart(
    rows: list[dict],
    validations: list[dict] | None = None,
    *,
    feedback: dict | None = None,
) -> dict:
    return {
        "cart": {
            "id": CART_ID,
            "deliveryType": "DeliveryHome",
            "timeslot": {"start": SLOT["start"], "end": SLOT["end"]},
            **(feedback if feedback is not None else {}),
            "shipments": [
                {
                    "companyId": "00000000-0000-4000-8000-000000000001",
                    "branchId": "00000000-0000-4000-8000-000000000002",
                    "products": rows,
                }
            ],
            "calculation": {
                "total": 0,
                "totalAfterDiscounts": 0,
                "productsTotal": sum(row["price"] * row["quantity"] for row in rows),
                "delivery": {"total": 89, "totalWeight": 2.19},
                "validations": validations or [],
            },
        },
        "loyalty": {"bonusAvailable": 36.37, "bonusTotal": 151.65},
    }


ROWS = [
    _row(101, "Молоко Ферма 2,5%", 53.49, stock=20, qty=2),
    _row(201, "Чай Pickwick чорний", 49.99, stock=0),
    _row(301, "Кава Lavazza мелена", 245.0, stock=3),
    _row(401, "Сир Джюгас 12 міс.", 164.5, stock=15),
]


def _write_fixtures(tmp_path, cart: dict) -> None:
    (tmp_path / "silpo_get_my_shopping_cart.json").write_text(
        json.dumps({"shoppingCartId": CART_ID}), encoding="utf-8"
    )
    (tmp_path / "silpo_get_shopping_cart_by_id.json").write_text(json.dumps(cart), encoding="utf-8")
    (tmp_path / "silpo_get_time_slots.json").write_text(
        json.dumps({"slots": [SLOT]}), encoding="utf-8"
    )
    (tmp_path / "silpo_get_my_offline_orders.json").write_text(
        json.dumps(
            {
                "orders": [
                    {
                        "createdAt": f"2026-0{month}-01",
                        "products": [
                            {
                                "lagerId": 101,
                                "name": "Молоко Ферма 2,5%",
                                "unit": "шт",
                                "quantity": 2,
                            }
                        ],
                    }
                    for month in (6, 7, 8)
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "silpo_find_products_batch.json").write_text(
        json.dumps(
            {
                "queries": [
                    {
                        "query": "Молоко",
                        "products": [
                            _product(101, "Молоко Ферма 2,5%", 53.49, 20),
                            _product(102, "Молоко Яготинське 2,6%", 75.99, 30),
                        ],
                    },
                    {
                        "query": "Чай",
                        "products": [_product(202, "Чай Pickwick зелений", 67.49, 18)],
                    },
                    {"query": "Кава", "products": [_product(301, "Кава Lavazza мелена", 245.0, 3)]},
                    {"query": "Сир", "products": [_product(402, "Сир Grana Padano", 189.0, 12)]},
                    {"query": "101", "products": [_product(101, "Молоко Ферма 2,5%", 53.49, 20)]},
                    {"query": "201", "products": []},
                    {"query": "301", "products": [_product(301, "Кава Lavazza мелена", 245.0, 3)]},
                    {"query": "401", "products": []},
                ]
            }
        ),
        encoding="utf-8",
    )


class _Recording(SilpoMCP):

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.calls: list[tuple[str, dict]] = []

    async def call(self, tool: str, arguments: dict | None = None):
        self.calls.append((tool, arguments or {}))
        return await super().call(tool, arguments)

    def args_of(self, tool: str) -> dict:
        return next(args for name, args in self.calls if name == tool)


@pytest.fixture
def mcp(tmp_path) -> _Recording:
    _write_fixtures(tmp_path, _cart(ROWS))
    return _Recording(settings=Settings.model_construct(), fixtures_dir=tmp_path)


@pytest.fixture
def empty_mcp(tmp_path) -> SilpoMCP:
    _write_fixtures(tmp_path, _cart([]))
    return SilpoMCP(settings=Settings.model_construct(), fixtures_dir=tmp_path)


def test_article_lives_in_the_slug_tail():
    assert article_of("moloko-galychyna-ultrapasteryzovane-2-5-815590") == "815590"
    assert article_of("bez-hvosta") is None
    assert article_of(None) is None


def test_only_line_level_errors_are_flagged():
    validations = [
        {
            "level": "error",
            "type": "product",
            "message": "product.offer.stock.max",
            "context": {"productId": "uuid-1", "stock": 9},
        },
        {
            "level": "error",
            "type": "order",
            "message": "order.cost.min",
            "context": {"orderCostMin": 599},
        },
        {
            "level": "info",
            "type": "product",
            "message": "product.adult",
            "context": {"productId": "uuid-2"},
        },
    ]
    assert flagged_products(validations) == {"uuid-1": Decimal(9)}


async def test_someone_elses_cart_becomes_a_checked_basket(mcp):
    request = BuildRequest.model_validate({"mode": "week", "source": "cart"})
    run = await assemble_cart(mcp, llm=None, request=request)
    basket = run.assembled.basket

    names = [line.name for line in basket.lines]
    assert "Молоко Ферма 2,5%" in names
    assert "Чай Pickwick зелений" in names
    assert "Сир Grana Padano" in names
    assert "Чай Pickwick чорний" not in names
    assert "Сир Джюгас 12 міс." not in names


async def test_replacement_explains_itself_in_the_line(mcp):
    run = await assemble_cart(
        mcp, llm=None, request=BuildRequest.model_validate({"mode": "week", "source": "cart"})
    )
    swapped = next(
        line for line in run.assembled.basket.lines if line.name == "Чай Pickwick зелений"
    )

    assert swapped.reason is Reason.SUBSTITUTED
    assert swapped.explanation == (
        "звичного не було — поклав погоджену заміну №1: Чай Pickwick зелений"
    )


async def test_row_present_in_cart_but_missing_in_branch_is_replaced(mcp):
    run = await assemble_cart(
        mcp, llm=None, request=BuildRequest.model_validate({"mode": "week", "source": "cart"})
    )
    swapped = next(line for line in run.assembled.basket.lines if line.name == "Сир Grana Padano")
    assert swapped.reason is Reason.SUBSTITUTED


async def test_history_line_keeps_its_quantity_and_says_it_is_usual(mcp):
    run = await assemble_cart(
        mcp, llm=None, request=BuildRequest.model_validate({"mode": "week", "source": "cart"})
    )
    milk = next(line for line in run.assembled.basket.lines if line.name == "Молоко Ферма 2,5%")

    assert milk.qty == Decimal(2)
    assert milk.explanation == "звичне — 3 чеки в історії"


def test_a_weighed_row_of_a_foreign_cart_stays_a_weight():
    row = _row(815590, "Рулет курячий «Алан» домашній в/г", 719.0, 5, qty=0.3) | {
        "ratio": "100г",
        "weighted": True,
        "addToBasketStep": 0.1,
    }

    line = to_cart_line(
        PlanLine(
            intent="рулет",
            product=_product_from_row(row, "815590"),
            qty=Decimal("0.3"),
            reason="прийшло з кошика, зібраного не Коморою",
            from_history=None,
        )
    )

    assert (line.unit, line.step) == ("кг", Decimal("0.1"))
    assert line.qty * line.price == Decimal("215.7")


def test_a_piece_row_of_a_foreign_cart_is_not_dragged_into_kilograms():
    line = to_cart_line(
        PlanLine(
            intent="молоко",
            product=_product_from_row(_row(101, "Молоко Ферма 2,5%", 53.49, 20, qty=2), "101"),
            qty=Decimal(2),
            reason="прийшло з кошика",
            from_history=None,
        )
    )

    assert (line.unit, line.step) == ("шт", None)


async def test_low_stock_without_a_chain_rides_with_a_do_not_substitute_mandate(mcp):
    run = await assemble_cart(
        mcp, llm=None, request=BuildRequest.model_validate({"mode": "week", "source": "cart"})
    )
    coffee = next(line for line in run.assembled.lines if line.intent == "Кава")

    assert coffee.risky
    assert coffee.needs_approval is False
    assert coffee.mandate is not None and "не підбирати" in coffee.mandate


async def test_auto_swap_turns_the_lonely_line_into_a_price_fork(mcp):
    run = await assemble_cart(
        mcp,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week", "source": "cart", "autoSwap": True}),
    )
    coffee = next(line for line in run.assembled.lines if line.intent == "Кава")

    assert not coffee.needs_approval
    assert coffee.mandate is not None
    assert "марки" not in coffee.mandate
    assert "того самого виду" in coffee.mandate


async def test_the_foreign_cart_fork_says_what_the_price_is_for():
    from komora.agent.cart import _mandate_for

    roll = {
        "price": 719.0,
        "weighted": True,
        "displayRatio": "100г",
        "step": 0.1,
        "addToBasketStep": 0.1,
    }
    mandate, fork, needs_approval = _mandate_for(
        (), roll, BuildRequest.model_validate({"mode": "week", "source": "cart", "autoSwap": True})
    )

    assert needs_approval is False
    assert fork is not None and fork.per == "кг"
    assert mandate is not None and "у межах 669–769 грн/кг" in mandate


async def test_a_row_without_a_plan_b_loses_the_fork_together_with_the_mandate(tmp_path):
    _write_fixtures(tmp_path, _cart([_row(501, "Печиво Марія", 32.0, stock=0)]))
    run = await assemble_cart(
        SilpoMCP(settings=Settings.model_construct(), fixtures_dir=tmp_path),
        llm=None,
        request=BuildRequest.model_validate({"mode": "week", "source": "cart", "autoSwap": True}),
    )

    [line] = run.assembled.lines
    assert line.needs_approval
    assert line.mandate is None
    assert line.swap_fork is None
    assert run.assembled.basket.lines[0].swap_fork is None


async def test_revalidation_is_visible_in_the_trace(mcp):
    run = await assemble_cart(
        mcp, llm=None, request=BuildRequest.model_validate({"mode": "week", "source": "cart"})
    )
    steps = {step.id: step for step in run.assembled.basket.trace}

    assert "step-cart" in steps
    revalidate = steps["step-revalidate"]
    assert revalidate.tag == "замін 2"
    assert "погоджених замін 2" in revalidate.result_summary
    assert any("поклав погоджену заміну №1" in note for note in revalidate.args["рядки"])
    assert revalidate.decision is not None
    assert "не питається зараз" in revalidate.decision


async def test_guest_rule_do_not_deliver_removes_the_row_out_loud(mcp):
    request = BuildRequest.model_validate(
        {
            "mode": "week",
            "source": "cart",
            "swaps": [{"externalProductId": "201", "policy": "skip", "chain": []}],
        }
    )
    run = await assemble_cart(mcp, llm=None, request=request)

    assert all("Pickwick" not in line.name for line in run.assembled.basket.lines)
    assert any("знято за правилом гостя" in text for text in run.assembled.basket.unresolved)


async def test_guest_chain_wins_over_the_computed_one(mcp):
    request = BuildRequest.model_validate(
        {
            "mode": "week",
            "source": "cart",
            "swaps": [{"externalProductId": "401", "policy": "substitute", "chain": ["102"]}],
        }
    )
    run = await assemble_cart(mcp, llm=None, request=request)

    assert any(line.name == "Молоко Яготинське 2,6%" for line in run.assembled.basket.lines)


async def test_gone_row_without_a_plan_b_stays_and_asks(tmp_path):
    _write_fixtures(tmp_path, _cart([_row(501, "Печиво Марія", 32.0, stock=0)]))
    request = BuildRequest.model_validate({"mode": "week", "source": "cart"})
    run = await assemble_cart(
        SilpoMCP(settings=Settings.model_construct(), fixtures_dir=tmp_path),
        llm=None,
        request=request,
    )

    [line] = run.assembled.lines
    assert line.needs_approval
    assert any("потрібне рішення гостя" in text for text in run.assembled.basket.unresolved)


async def test_empty_cart_is_a_loud_refusal_not_an_empty_basket(empty_mcp):
    with pytest.raises(AssemblyError, match="порожній"):
        await assemble_cart(
            empty_mcp,
            llm=None,
            request=BuildRequest.model_validate({"mode": "week", "source": "cart"}),
        )


async def test_refusal_speaks_to_the_guest_not_to_us(empty_mcp):
    from komora.agent.cart import EMPTY_CART_NOTE

    with pytest.raises(AssemblyError) as refusal:
        await assemble_cart(
            empty_mcp,
            llm=None,
            request=BuildRequest.model_validate({"mode": "week", "source": "cart"}),
        )

    said = str(refusal.value)
    assert said == EMPTY_CART_NOTE
    assert "вхід" not in said.lower(), "класифікація конвеєра гостю нічого не каже"
    assert "Зібрати на тиждень" in said, "відмова мусить називати наступний крок"


async def test_no_cart_at_all_refuses_with_the_same_words(tmp_path):
    from komora.agent.cart import EMPTY_CART_NOTE

    _write_fixtures(tmp_path, _cart([]))
    (tmp_path / "silpo_get_my_shopping_cart.json").write_text("{}", encoding="utf-8")
    mcp = SilpoMCP(settings=Settings.model_construct(), fixtures_dir=tmp_path)

    with pytest.raises(AssemblyError) as refusal:
        await assemble_cart(
            mcp, llm=None, request=BuildRequest.model_validate({"mode": "week", "source": "cart"})
        )

    assert str(refusal.value) == EMPTY_CART_NOTE


async def test_cart_numbers_come_from_the_api_not_from_the_code(mcp):
    run = await assemble_cart(
        mcp, llm=None, request=BuildRequest.model_validate({"mode": "week", "source": "cart"})
    )
    basket = run.assembled.basket

    assert basket.total_weight_kg == Decimal("2.19")
    assert basket.delivery_cost == Decimal(89)
    assert basket.slot is not None


async def test_both_weights_stand_together_and_the_gap_is_named(mcp):
    run = await assemble_cart(
        mcp, llm=None, request=BuildRequest.model_validate({"mode": "week", "source": "cart"})
    )

    step = next(s for s in run.assembled.basket.trace if s.id == "step-weight")
    assert step.result_summary.startswith("«Сільпо» рахує 2,19 кг, моя оцінка з фасовок")
    assert step.decision is not None and step.decision.startswith("розбіжність")
    assert step.tag == "2,19 кг"


class _FakeLLM:

    model = "fake-model"

    def __init__(self, chains: list[dict]) -> None:
        self.chains = chains
        self.calls: list[str] = []
        self.limits: list[tuple[dict, int]] = []
        self.asked: list[str] = []

    async def decide(self, *, system, user, schema, schema_name="decision", max_tokens=2048, **_):
        from komora.agent.llm import Decision, Usage

        self.calls.append(system)
        self.asked.append(user)
        self.limits.append((schema, max_tokens))
        data = {"kinds": []} if "комору" in system else {"chains": self.chains}
        return Decision(data=data, text="", model=self.model, usage=Usage(1, 1), duration_ms=1)

    @property
    def chain_tokens(self) -> int:
        return next(limit for schema, limit in self.limits if schema is CHAIN_SCHEMA)

    @property
    def naming_tokens(self) -> int:
        return next(limit for schema, limit in self.limits if schema is KIND_SCHEMA)


def _live(tmp_path) -> tuple[SilpoMCP, Settings]:
    cfg = Settings.model_construct()
    return SilpoMCP(settings=cfg, fixtures_dir=tmp_path), cfg


async def test_agent_builds_the_chain_and_its_order_is_kept(tmp_path):
    _write_fixtures(tmp_path, _cart([_row(101, "Молоко Ферма 2,5%", 53.49, stock=20)]))
    mcp, settings = _live(tmp_path)
    llm = _FakeLLM([{"article": "101", "chain": ["102"], "reason": "те саме молоко іншої марки"}])

    run = await assemble_cart(
        mcp, llm, BuildRequest.model_validate({"mode": "week", "source": "cart"}), settings=settings
    )

    [line] = run.assembled.lines
    assert [alt.name for alt in line.chain] == ["Молоко Яготинське 2,6%"]
    assert any(step.id == "step-chains" for step in run.assembled.basket.trace)


async def test_agent_articles_outside_the_candidates_are_dropped(tmp_path):
    _write_fixtures(tmp_path, _cart([_row(101, "Молоко Ферма 2,5%", 53.49, stock=20)]))
    mcp, settings = _live(tmp_path)
    llm = _FakeLLM([{"article": "101", "chain": ["999999", "102"], "reason": "…"}])

    run = await assemble_cart(
        mcp, llm, BuildRequest.model_validate({"mode": "week", "source": "cart"}), settings=settings
    )

    [line] = run.assembled.lines
    assert [alt.external_product_id for alt in line.chain] == ["102"]


def _bulk_fixtures(tmp_path, rows: int) -> SilpoMCP:
    tmp_path.mkdir(parents=True, exist_ok=True)
    _write_fixtures(
        tmp_path,
        _cart([_row(1000 + i, f"Товар{i:03d} марка", 50.0, stock=20) for i in range(rows)]),
    )
    (tmp_path / "silpo_find_products_batch.json").write_text(
        json.dumps(
            {
                "queries": [
                    {
                        "query": f"Товар{i:03d}",
                        "products": [_product(5000 + i, f"Товар{i:03d} інша марка", 55.0, 20)],
                    }
                    for i in range(rows)
                ]
            }
        ),
        encoding="utf-8",
    )
    return SilpoMCP(settings=Settings.model_construct(), fixtures_dir=tmp_path)


async def test_chain_ceiling_grows_with_the_cart_and_holds_the_floor(tmp_path):
    big = _bulk_fixtures(tmp_path / "big", 30)
    llm = _FakeLLM([])
    await assemble_cart(
        big,
        llm,
        BuildRequest.model_validate({"mode": "week", "source": "cart"}),
        settings=Settings.model_construct(),
    )
    assert llm.chain_tokens > 2048
    assert llm.chain_tokens == CHAIN_TOKENS_PER_ROW * 30

    small = _bulk_fixtures(tmp_path / "small", 3)
    tight = _FakeLLM([])
    await assemble_cart(
        small,
        tight,
        BuildRequest.model_validate({"mode": "week", "source": "cart"}),
        settings=Settings.model_construct(),
    )
    assert tight.chain_tokens == 2048


async def test_truncation_names_itself_and_not_the_model_being_unavailable(tmp_path):

    class _Cut(_FakeLLM):
        async def decide(self, **kwargs):
            from komora.agent.llm import Truncated, Usage

            if "комору" in kwargs["system"]:
                return await super().decide(**kwargs)
            raise Truncated("fake-model: відповідь урвано на ліміті", Usage(500, 2048))

    _write_fixtures(tmp_path, _cart([_row(101, "Молоко Ферма 2,5%", 53.49, stock=20)]))
    mcp, settings = _live(tmp_path)

    run = await assemble_cart(
        mcp,
        _Cut([]),
        BuildRequest.model_validate({"mode": "week", "source": "cart"}),
        settings=settings,
    )

    step = next(s for s in run.assembled.basket.trace if s.id == "step-chains")
    assert step.tag == "стеля відповіді"
    assert "модель недоступна" not in step.result_summary
    [line] = run.assembled.lines
    assert [alt.external_product_id for alt in line.chain] == ["102"]


async def test_naming_ceiling_grows_with_the_foreign_cart_too(tmp_path):
    wide = _bulk_fixtures(tmp_path / "wide", 60)
    llm = _FakeLLM([])
    await assemble_cart(
        wide,
        llm,
        BuildRequest.model_validate({"mode": "week", "source": "cart"}),
        settings=Settings.model_construct(),
    )
    assert llm.naming_tokens > 4096
    assert llm.naming_tokens == NAMING_TOKENS_PER_NAME * 60

    narrow = _bulk_fixtures(tmp_path / "narrow", 3)
    tight = _FakeLLM([])
    await assemble_cart(
        narrow,
        tight,
        BuildRequest.model_validate({"mode": "week", "source": "cart"}),
        settings=Settings.model_construct(),
    )
    assert tight.naming_tokens == 4096


async def test_model_failure_falls_back_to_words_not_to_a_crash(tmp_path):

    class _Broken(_FakeLLM):
        async def decide(self, **kwargs):
            if "комору" in kwargs["system"]:
                return await super().decide(**kwargs)
            raise RuntimeError("bedrock 503")

    _write_fixtures(tmp_path, _cart([_row(101, "Молоко Ферма 2,5%", 53.49, stock=20)]))
    mcp, settings = _live(tmp_path)

    run = await assemble_cart(
        mcp,
        _Broken([]),
        BuildRequest.model_validate({"mode": "week", "source": "cart"}),
        settings=settings,
    )

    [line] = run.assembled.lines
    assert [alt.external_product_id for alt in line.chain] == ["102"]
    step = next(s for s in run.assembled.basket.trace if s.id == "step-chains")
    assert step.tag == "без агента"


def test_cart_states_read_the_same_way_in_every_moment():
    from komora.agent.cart import cart_states

    rows = [
        _row(101, "Молоко Ферма", 53.49, stock=20, qty=2),
        _row(201, "Чай Pickwick", 49.99, stock=0),
        _row(301, "Кава Lavazza", 245.0, stock=15),
    ]
    validations = [
        {
            "level": "error",
            "type": "product",
            "message": "product.offer.stock.max",
            "context": {"productId": rows[2]["productId"], "stock": 3},
        },
    ]
    states = cart_states(rows, validations, vanished=frozenset({"201"}))

    assert [s.external_product_id for s in states] == ["101", "201", "301"]
    assert [s.stock for s in states] == [Decimal(20), Decimal(0), Decimal(3)]
    assert [s.flagged for s in states] == [False, True, True]


def test_cart_states_prefer_the_article_we_already_resolved():
    from komora.agent.cart import cart_states

    [state] = cart_states(
        [{"productId": "uuid", "externalProductId": 815590, "name": "Молоко", "quantity": 1}],
        [],
    )
    assert state.external_product_id == "815590"
    assert state.stock is None


async def test_snapshot_keeps_both_ends_of_the_slot(mcp):
    from komora.agent.cart import read_cart

    snapshot = await read_cart(mcp)
    assert snapshot.timeslot_start == SLOT["start"]
    assert snapshot.timeslot_end == SLOT["end"]


async def test_the_foreign_cart_asks_slots_from_now_not_from_dawn(mcp):
    moment = datetime(2026, 8, 14, 14, 30, 5, 991538, tzinfo=UTC)
    await assemble_cart(
        mcp,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week", "source": "cart"}),
        now=moment,
    )

    args = mcp.args_of("silpo_get_time_slots")
    assert args["start"] == "2026-08-14T14:30:05+00:00"
    assert args["limit"] == SLOT_LOOKAHEAD, "стеля з константи, а не літералом на місці"
    assert args["branchId"] == ROWS[0]["branchId"], "слоти питаються з філії кошика"


async def test_the_foreign_cart_slot_window_starts_at_the_run_not_at_the_cart(mcp):
    moment = datetime(2026, 8, 14, 14, 30, tzinfo=UTC)
    await assemble_cart(
        mcp,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week", "source": "cart"}),
        now=moment,
    )

    assert mcp.args_of("silpo_get_time_slots")["start"] != SLOT["start"]
    assert mcp.args_of("silpo_get_time_slots")["start"].startswith("2026-08-14T14:30")


async def test_the_foreign_cart_slot_step_names_the_ceiling_it_looked_through(mcp):
    run = await assemble_cart(
        mcp, llm=None, request=BuildRequest.model_validate({"mode": "week", "source": "cart"})
    )

    step = next(s for s in run.assembled.basket.trace if s.id == "step-slots")
    assert "найближчих" in step.result_summary
    assert step.args["limit"] == SLOT_LOOKAHEAD


async def test_no_free_slot_blames_our_window_not_the_shop(tmp_path):
    _write_fixtures(tmp_path, _cart(ROWS))
    (tmp_path / "silpo_get_time_slots.json").write_text(
        json.dumps({"slots": [{**SLOT, "available": False}] * 3}), encoding="utf-8"
    )
    mcp = SilpoMCP(settings=Settings.model_construct(), fixtures_dir=tmp_path)

    with pytest.raises(AssemblyError) as refusal:
        await assemble_cart(
            mcp, llm=None, request=BuildRequest.model_validate({"mode": "week", "source": "cart"})
        )

    assert str(refusal.value) == (
        "серед 3 найближчих слотів DeliveryHome немає жодного вільного — доводити нема куди"
    )
    assert str(SLOT_LOOKAHEAD) not in str(refusal.value), "стеля запиту тут не при чому"


async def test_an_empty_slot_list_does_not_pretend_the_shelf_was_busy(tmp_path):
    _write_fixtures(tmp_path, _cart(ROWS))
    (tmp_path / "silpo_get_time_slots.json").write_text(json.dumps({"slots": []}), encoding="utf-8")
    mcp = SilpoMCP(settings=Settings.model_construct(), fixtures_dir=tmp_path)

    with pytest.raises(AssemblyError) as refusal:
        await assemble_cart(
            mcp, llm=None, request=BuildRequest.model_validate({"mode": "week", "source": "cart"})
        )

    assert str(refusal.value) == "на DeliveryHome не прийшло жодного слота — доводити нема куди"


async def test_delivery_cost_comes_from_the_cart_not_from_our_tiers(tmp_path):
    cart = _cart([_row(101, "Молоко Ферма 2,5%", 53.49, stock=20)])
    cart["cart"]["calculation"]["delivery"]["total"] = 1
    _write_fixtures(tmp_path, cart)
    run = await assemble_cart(
        SilpoMCP(settings=Settings.model_construct(), fixtures_dir=tmp_path),
        llm=None,
        request=BuildRequest.model_validate({"mode": "week", "source": "cart"}),
    )
    basket = run.assembled.basket

    assert basket.delivery_cost == Decimal(1)
    assert basket.top_up is None
    economics = next(s for s in basket.trace if s.id == "step-economics")
    assert "за порогами слота 89" in economics.result_summary


async def test_someone_elses_cart_over_the_limit_says_the_difference(mcp):
    run = await assemble_cart(
        mcp,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week", "source": "cart", "budget": 100}),
    )
    basket = run.assembled.basket

    assert basket.budget == Decimal(100)
    step = next(s for s in basket.trace if s.id == "step-budget")
    assert f"на {basket.total - Decimal(100)} грн" in step.result_summary
    assert step.tag_tone == "warn"
    assert basket.trimmed == [], "склад чужого кошика під межу не ріжеться"


async def test_cart_state_says_how_much_is_there_before_the_run(mcp):
    from komora.agent.cart import read_cart, state_of

    state = state_of(await read_cart(mcp))

    assert state.rows == len((await read_cart(mcp)).rows)
    assert state.rows > 0
    assert state.total > 0, "сума самих рядків, а не «до оплати»"
    assert state.slot is not None, "слот кошика видно на кнопці, бо збирати будуть під нього"


async def test_cart_state_of_an_empty_cart_is_zero_not_a_refusal(empty_mcp):
    from komora.agent.cart import read_cart, state_of

    state = state_of(await read_cart(empty_mcp))

    assert state.rows == 0
    assert state.total == 0


async def test_the_button_and_the_run_say_the_same_about_one_cart(empty_mcp):
    from komora.agent.cart import read_cart, state_of

    state = state_of(await read_cart(empty_mcp))
    with pytest.raises(AssemblyError):
        await assemble_cart(
            empty_mcp,
            llm=None,
            request=BuildRequest.model_validate({"mode": "week", "source": "cart"}),
        )

    assert state.rows == 0, "кнопка гасне рівно там, де збірка відмовляє"


async def test_the_order_switches_travel_from_the_cart_to_the_basket(tmp_path):
    _write_fixtures(
        tmp_path,
        _cart(
            ROWS,
            feedback={
                "feedbackChanges": "disapprovedChanges",
                "feedbackContacts": "doNotCall",
            },
        ),
    )
    mcp = SilpoMCP(settings=Settings.model_construct(), fixtures_dir=tmp_path)
    run = await assemble_cart(
        mcp, llm=None, request=BuildRequest.model_validate({"mode": "week", "source": "cart"})
    )
    assert run.assembled.basket.feedback.changes is Changes.DISAPPROVED
    assert run.assembled.basket.feedback.contacts is Contacts.DO_NOT_CALL
    assert collector_swaps(run.assembled.basket.feedback.changes) is False


async def test_a_cart_that_never_named_the_switches_grants_nothing(mcp):
    run = await assemble_cart(
        mcp, llm=None, request=BuildRequest.model_validate({"mode": "week", "source": "cart"})
    )
    assert run.assembled.basket.feedback.changes is None
    assert run.assembled.basket.feedback.contacts is None


async def test_a_far_slot_prepares_the_whole_foreign_cart_not_only_its_thin_rows(mcp):
    from datetime import UTC, datetime

    run = await assemble_cart(
        mcp,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week", "source": "cart"}),
        now=datetime(2026, 8, 14, tzinfo=UTC),
    )
    milk = next(line for line in run.assembled.lines if line.intent == "Молоко")

    assert milk.risky is False
    assert milk.ahead is True
    assert milk.mandate is not None and "Яготинське" in milk.mandate
    assert milk.needs_approval is False

    step = next(s for s in run.assembled.basket.trace if s.id == "step-risk")
    assert "до слота 30 год" in step.result_summary
    assert "при стелі 18" in step.result_summary


async def test_a_near_slot_still_sends_the_chain_of_the_foreign_cart(mcp):
    from datetime import UTC, datetime

    run = await assemble_cart(
        mcp,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week", "source": "cart"}),
        now=datetime(2026, 8, 15, 4, tzinfo=UTC),
    )
    milk = next(line for line in run.assembled.lines if line.intent == "Молоко")

    assert milk.mandate is not None and "Яготинське" in milk.mandate
    assert milk.ahead is True and milk.risky is False
    step = next(s for s in run.assembled.basket.trace if s.id == "step-risk")
    assert "з мандатом напоготові" in step.result_summary


async def test_the_occasion_of_a_foreign_cart_says_it_changes_nothing(mcp):
    request = BuildRequest.model_validate({"source": "cart", "mode": "event", "occasionPeople": 6})
    run = await assemble_cart(mcp, llm=None, request=request)

    step = next(s for s in run.assembled.basket.trace if s.id == "step-occasion")
    assert "подія, 6 людей" in step.result_summary
    assert step.tag == "не застосовано" and step.tag_tone == "warn"
    assert step.decision and "зі списку" in step.decision


async def test_an_ordinary_week_leaves_the_foreign_cart_trace_alone(mcp):
    run = await assemble_cart(
        mcp, llm=None, request=BuildRequest.model_validate({"mode": "week", "source": "cart"})
    )

    assert not [s for s in run.assembled.basket.trace if s.id == "step-occasion"]


async def test_a_foreign_cart_explains_the_headroom_with_its_own_words(mcp):
    run = await assemble_cart(
        mcp, llm=None, request=BuildRequest.model_validate({"mode": "week", "source": "cart"})
    )

    note = run.assembled.basket.cycles_note
    assert note is not None and "хтось інший" in note
    assert "закінчується" not in note


class _CountingPool:

    def __init__(self) -> None:
        self.reads = 0

    @asynccontextmanager
    async def connection(self, **_):
        self.reads += 1
        yield _CacheConn()


class _CacheConn:
    async def execute(self, sql, args=None):
        return self

    async def fetchall(self):
        return []

    @asynccontextmanager
    async def cursor(self):
        yield self

    async def executemany(self, sql, rows):
        return None


async def test_the_foreign_cart_reaches_the_shared_name_cache(mcp):
    pool = _CountingPool()
    await assemble_cart(
        mcp,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week", "source": "cart"}),
        pool=pool,
    )
    assert pool.reads > 0


async def test_the_chain_the_agent_builds_knows_the_guests_rules(tmp_path):
    _write_fixtures(tmp_path, _cart([_row(101, "Молоко Ферма 2,5%", 53.49, stock=20)]))
    mcp, settings = _live(tmp_path)
    llm = _FakeLLM([{"article": "101", "chain": ["102"], "reason": "те саме молоко"}])

    await assemble_cart(
        mcp,
        llm,
        BuildRequest.model_validate({"mode": "week", "source": "cart", "rules": ["без свинини"]}),
        settings=settings,
    )

    chain_call = next(
        body for system, body in zip(llm.calls, llm.asked, strict=True) if "комору" not in system
    )
    assert "без свинини" in chain_call
    assert "правила_гостя" in chain_call


async def test_no_rules_is_a_lawful_state_and_says_nothing(tmp_path):
    _write_fixtures(tmp_path, _cart([_row(101, "Молоко Ферма 2,5%", 53.49, stock=20)]))
    mcp, settings = _live(tmp_path)
    llm = _FakeLLM([{"article": "101", "chain": ["102"], "reason": "те саме молоко"}])

    await assemble_cart(
        mcp, llm, BuildRequest.model_validate({"mode": "week", "source": "cart"}), settings=settings
    )

    chain_call = next(
        body for system, body in zip(llm.calls, llm.asked, strict=True) if "комору" not in system
    )
    assert '"правила_гостя": null' in chain_call


async def test_the_foreign_cart_fork_carries_the_shelf_life_too():
    from komora.agent.cart import _mandate_for

    milk = {"price": 53.49, "weighted": False, "displayRatio": "1шт", "step": 1}
    mandate, _fork, _needs = _mandate_for(
        (),
        milk,
        BuildRequest.model_validate({"mode": "week", "source": "cart", "autoSwap": True}),
        shelf_life="термін придатності не менше ніж до 30.08",
    )

    assert mandate is not None
    assert "термін придатності не менше ніж до 30.08" in mandate
