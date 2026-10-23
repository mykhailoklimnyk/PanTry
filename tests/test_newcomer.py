from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from komora.agent.basket import (
    MIN_RECEIPTS,
    AssemblyError,
    assemble_list,
    pantry_live,
)
from komora.agent.cart import EMPTY_CART_NOTE, read_cart
from komora.api.schemas import BuildRequest
from komora.config import Settings
from komora.core.location import HOME_DELIVERY, Location
from komora.mcp.client import MCPCallError, SilpoMCP

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 8, 24, tzinfo=UTC)
BRANCH = "00000000-0000-4000-8000-000000000002"
HERE = Location(branch_id=BRANCH, branches={HOME_DELIVERY: BRANCH})

SLOT = {
    "start": "2026-08-25T11:30:00+00:00",
    "end": "2026-08-25T13:00:00+00:00",
    "available": True,
    "deliveryType": "DeliveryHome",
    "deliveryCost": 89,
    "deliveryCostMap": [{"cost": 59, "fromOrderCost": 1199}],
    "minOrderCost": 599,
    "maxWeight": 50,
}

MILK = {
    "id": "00000000-0000-4000-8000-000000000101",
    "name": "Молоко Ферма 2,5%",
    "slug": "moloko-ferma-101",
    "price": 53.49,
    "oldPrice": None,
    "stock": 20,
    "available": True,
    "image": None,
    "weighted": False,
    "step": 1,
    "displayRatio": "1шт",
    "companyId": "00000000-0000-4000-8000-000000000001",
    "branchId": BRANCH,
    "externalProductId": 101,
}


def _receipt(day: int) -> dict:
    return {
        "createdAt": f"2026-08-{day:02d}T10:00:00",
        "sumReg": 53.49,
        "products": [{"lagerId": "101", "name": "Молоко Ферма 2,5%", "quantity": 1, "unit": "шт"}],
    }


class _Newcomer(SilpoMCP):

    async def call(self, tool: str, arguments: dict | None = None):
        if tool == "silpo_get_my_shopping_cart":
            raise MCPCallError(
                tool, "Error in get-my-shopping-cart: Resource not found.", attempts=4
            )
        return await super().call(tool, arguments)


def _stand(tmp_path, *, orders: list[dict]) -> SilpoMCP:
    (tmp_path / "silpo_get_time_slots.json").write_text(
        json.dumps({"slots": [SLOT]}), encoding="utf-8"
    )
    (tmp_path / "silpo_get_my_offline_orders.json").write_text(
        json.dumps({"orders": orders, "meta": {"limit": 10, "offset": 0, "total": len(orders)}}),
        encoding="utf-8",
    )
    (tmp_path / "silpo_find_products_batch.json").write_text(
        json.dumps({"queries": [{"query": "молоко", "products": [MILK]}]}),
        encoding="utf-8",
    )
    return _Newcomer(settings=Settings.model_construct(), fixtures_dir=tmp_path)


async def test_a_pantry_without_receipts_says_there_are_no_receipts(tmp_path):
    pantry = await pantry_live(_stand(tmp_path, orders=[]), now=NOW, place=HERE)

    assert pantry.items == []
    assert pantry.receipts == 0
    assert pantry.kinds == 0
    assert pantry.tracked_from == MIN_RECEIPTS


async def test_receipts_without_a_cycle_are_not_the_same_as_no_receipts(tmp_path):
    orders = [_receipt(10), _receipt(17)]

    pantry = await pantry_live(_stand(tmp_path, orders=orders), now=NOW, place=HERE)

    assert pantry.items == []
    assert pantry.receipts == 2, "чеки прочитані, і мовчати про них не можна"
    assert pantry.kinds == 1


async def test_week_needs_without_history_name_the_real_reason(tmp_path):
    mcp = _stand(tmp_path, orders=[])
    request = BuildRequest.model_validate({"mode": "week", "shoppingList": []})

    with pytest.raises(AssemblyError) as refusal:
        await assemble_list(mcp, llm=None, request=request, now=NOW, place=HERE)

    said = str(refusal.value)
    assert "не бачу твоїх покупок у «Сільпо»" in said
    assert "нічого не закінчується" not in said
    assert "Напиши, що потрібно" in said, "названа відмова мусить лишати дію"
    assert "наповни кошик" in said


async def test_a_written_list_still_builds_without_any_history(tmp_path):
    mcp = _stand(tmp_path, orders=[])
    request = BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко"]})

    assembled = await assemble_list(mcp, llm=None, request=request, now=NOW, place=HERE)

    assert [line.name for line in assembled.basket.lines] == ["Молоко Ферма 2,5%"]
    assert assembled.basket.stats.receipts == 0


async def test_the_trace_of_a_first_run_reads_as_a_state_not_a_failure(tmp_path):
    mcp = _stand(tmp_path, orders=[])
    request = BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко"]})

    assembled = await assemble_list(mcp, llm=None, request=request, now=NOW, place=HERE)
    steps = {step.id: step for step in assembled.basket.trace}

    assert "кошика в акаунті ще немає" in (steps["step-cart"].result_summary or "")
    assert steps["step-cart"].tag_tone != "warn", "порожнеча нового акаунта — не тривога"
    assert "покупок у «Сільпо» ще не видно" in (steps["step-history"].result_summary or "")
    assert "демо" not in (steps["step-agent"].result_summary or "")


class _NoCart:

    def __init__(self, message: str) -> None:
        self._message = message

    async def call(self, tool: str, args: dict | None = None):
        raise MCPCallError(tool, self._message, attempts=4)


async def test_a_cart_that_never_existed_is_empty_not_broken():
    mcp = _NoCart("Error in get-my-shopping-cart: Resource not found. Verify the parameters")

    with pytest.raises(AssemblyError) as refusal:
        await read_cart(mcp)  # type: ignore[arg-type]

    assert str(refusal.value) == EMPTY_CART_NOTE


async def test_any_other_cart_failure_stays_a_failure():
    mcp = _NoCart("HTTP 500 Internal Server Error")

    with pytest.raises(MCPCallError):
        await read_cart(mcp)  # type: ignore[arg-type]


def test_the_start_screen_sees_an_empty_cart_not_a_failure(monkeypatch):
    from fastapi.testclient import TestClient

    from komora.api.app import app
    from komora.api.auth_routes import require_guest

    class Newcomer:
        def __init__(self, *_args, **_kwargs) -> None: ...

        async def __aenter__(self) -> Newcomer:
            return self

        async def __aexit__(self, *_exc: object) -> bool:
            return False

        async def call(self, tool: str, args: dict | None = None):
            raise MCPCallError(
                tool, "Error in get-my-shopping-cart: Resource not found.", attempts=4
            )

    class Session:
        access = "живий-токен"
        refresh = "живий-refresh"
        owner = "власник-сесії"
        account = "відбиток-акаунта"

    monkeypatch.setattr("komora.api.app.SilpoMCP", Newcomer)
    app.dependency_overrides[require_guest] = lambda: Session()
    try:
        response = TestClient(app).get("/api/cart")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["rows"] == 0


async def test_without_purchases_there_is_nothing_to_top_up_with(tmp_path):
    pantry = await pantry_live(_stand(tmp_path, orders=[]), now=NOW, place=HERE)

    assert pantry.target_pool == 0
    assert pantry.target_estimate is None, "суми немає, а не нуль (#76)"


async def test_receipts_below_the_threshold_are_not_a_pool_either(tmp_path):
    pantry = await pantry_live(
        _stand(tmp_path, orders=[_receipt(10), _receipt(17)]), now=NOW, place=HERE
    )

    assert pantry.receipts == 2
    assert pantry.target_pool == 0
    assert pantry.target_estimate is None


def _many_kinds(count: int) -> list[dict]:
    return [
        {
            "createdAt": f"2026-08-{10 + trip:02d}T10:00:00",
            "sumReg": 10.0 * count,
            "products": [
                {
                    "lagerId": str(200 + one),
                    "name": f"Вид{one:02d} звичайний",
                    "quantity": 1,
                    "unit": "шт",
                }
                for one in range(count)
            ],
        }
        for trip in range(2)
    ]


async def test_the_add_window_gets_every_kind_of_his_not_a_sample_of_four(tmp_path):
    pantry = await pantry_live(_stand(tmp_path, orders=_many_kinds(12)), now=NOW, place=HERE)

    assert pantry.items == [], "жоден вид не набрав порога ведення -- комора порожня"
    assert pantry.unlisted == 12, "числом гість бачить УСІ свої види поза коморою"
    assert len(pantry.outside) == 12, (
        "пул вікна додавання -- усі види гостя, а не вибірка для показу: "
        "вибірка не може сказати «такий вид у тебе вже є» про п'ятий і далі"
    )


async def test_the_pool_of_own_kinds_names_its_own_ceiling(tmp_path):
    pantry = await pantry_live(_stand(tmp_path, orders=_many_kinds(12)), now=NOW, place=HERE)

    ceilings = [step for step in pantry.trace if step.id == "step-pantry-ceilings"]
    assert len(ceilings) == 1, "крок стель безумовний"
    said = ceilings[0].result_summary + json.dumps(ceilings[0].args, ensure_ascii=False)
    assert "12" in said, "число видів поза коморою мусить стояти в кроці"
    assert "стеля пулу" in ceilings[0].args, "клапан пулу називає своє число окремим полем"
