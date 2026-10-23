from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from komora.agent.basket import AssemblyError, assemble_list
from komora.agent.llm import Decision, ModelError, Usage
from komora.api.schemas import BuildRequest
from komora.config import settings
from komora.core.plan import PLAN_SCHEMA
from komora.mcp.client import SilpoMCP

NOW = datetime(2026, 9, 3, tzinfo=UTC)
SLOT = {
    "start": "2026-09-03T11:30:00+00:00",
    "end": "2026-09-03T13:00:00+00:00",
    "available": True,
    "deliveryType": "DeliveryHome",
    "deliveryCost": 89,
    "deliveryCostMap": [{"cost": 59, "fromOrderCost": 1199}],
    "minOrderCost": 599,
    "maxWeight": 50,
}
MILK = "Молоко Ферма 2,5%"
CHEESE = "Сир Комо Гауда"


def _cfg():
    return settings.model_copy(update={"branch_id": "id:1"})


def _card(pid: int, name: str, price: float) -> dict:
    return {
        "id": f"00000000-0000-4000-8000-{pid:012d}",
        "name": name,
        "slug": f"slug-{pid}",
        "price": price,
        "oldPrice": None,
        "stock": 30,
        "available": True,
        "image": None,
        "weighted": False,
        "step": 1,
        "displayRatio": "1шт",
        "companyId": "00000000-0000-4000-8000-000000000001",
        "branchId": "00000000-0000-4000-8000-000000000002",
        "externalProductId": pid,
    }


def _bought(days_ago: int, lager: int, name: str) -> dict:
    return {
        "createdAt": (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%d"),
        "products": [
            {
                "lagerId": lager,
                "name": name,
                "unit": "шт",
                "quantity": 1,
                "price": 50,
                "catalogProduct": {"price": 50},
            }
        ],
    }


class _PlanningLLM:

    model = "fake-planner"

    def __init__(self, steps: list[str]) -> None:
        self.steps = steps
        self.plans = 0

    async def decide(self, *, system, user, schema, schema_name="decision", max_tokens=2048, **_):
        if schema is not PLAN_SCHEMA:
            raise ModelError("не планування -- мовчу")
        self.plans += 1
        data = {"steps": [{"step": name, "why": "план"} for name in self.steps]}
        return Decision(
            data=data, text=json.dumps(data), model=self.model, usage=Usage(10, 5), duration_ms=1
        )


def _stand(tmp_path, *, shelf: dict[str, list[dict]], extra_orders: list[dict] = ()) -> SilpoMCP:
    (tmp_path / "silpo_get_time_slots.json").write_text(
        json.dumps({"slots": [SLOT]}), encoding="utf-8"
    )
    (tmp_path / "silpo_get_my_offline_orders.json").write_text(
        json.dumps(
            {
                "orders": [_bought(day, 101, MILK) for day in (30, 23, 16, 9)]
                + [_bought(day, 202, CHEESE) for day in (59, 45, 31, 17)]
                + list(extra_orders)
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "silpo_get_my_shopping_cart.json").write_text(
        json.dumps({"shoppingCartId": None}), encoding="utf-8"
    )
    (tmp_path / "silpo_find_products_batch.json").write_text(
        json.dumps(
            {"queries": [{"query": query, "products": cards} for query, cards in shelf.items()]}
        ),
        encoding="utf-8",
    )
    (tmp_path / "tools.json").write_text(
        json.dumps(
            [
                {
                    "name": "silpo_find_products_batch",
                    "description": "SEARCH BY ARTICLE CODE: numeric lagerId is the most reliable",
                    "inputSchema": {},
                }
            ]
        ),
        encoding="utf-8",
    )
    return SilpoMCP(fixtures_dir=tmp_path)


PLAN = [
    "history.receipts",
    "history.orders",
    "history.model",
    "intents.compose",
    "shelf.search",
    "shelf.by_article",
    "decide.pick",
    "decide.chain",
    "economy.settle",
    "cart.slot",
    "cart.write",
    "cart.reread",
]


@pytest.mark.anyio
async def test_the_plan_step_names_the_model_plan_and_the_tools_it_read(tmp_path):
    mcp = _stand(
        tmp_path,
        shelf={
            MILK: [_card(101, MILK, 53.49)],
            CHEESE: [_card(203, "Сир Комо Едам", 99.0)],
            "202": [_card(202, CHEESE, 129.0)],
        },
    )
    llm = _PlanningLLM(PLAN)

    assembled = await assemble_list(
        mcp, llm=llm, request=BuildRequest(mode="week"), now=NOW, settings=_cfg()
    )

    step = next(s for s in assembled.basket.trace if s.id == "step-plan")
    assert step.tag == "план моделі"
    assert step.result_summary == f"план від моделі: {len(PLAN)} кроків"
    assert step.args["план"].startswith("history.receipts -> history.orders")
    assert step.args["джерело"] == "model" and step.args["спроб"] == 1
    assert llm.plans == 1
    assert assembled.plan is not None and assembled.plan.names() == tuple(PLAN)


@pytest.mark.anyio
async def test_the_article_step_brings_the_own_article_the_name_search_missed(tmp_path):
    mcp = _stand(
        tmp_path,
        shelf={
            MILK: [_card(101, MILK, 53.49)],
            CHEESE: [_card(203, "Сир Комо Едам", 99.0)],
            "202": [_card(202, CHEESE, 129.0)],
        },
    )
    assembled = await assemble_list(
        mcp, llm=_PlanningLLM(PLAN), request=BuildRequest(mode="week"), now=NOW, settings=_cfg()
    )

    article = next(s for s in assembled.basket.trace if s.id == "step-article")
    assert article.tag == "+1"
    assert article.args["артикулів"] == 1 and article.args["на полиці"] == 1
    assert article.args["крок"] == "shelf.by_article"
    assert article.args["входи"] == ["branch", "history", "slot"]
    assert article.args["дав"] == {"candidates": "3 (shelf.by_article)"}
    cheese = next(line for line in assembled.basket.lines if line.name == CHEESE)
    assert cheese.external_product_id == "202"
    assert "звичне" in (cheese.explanation_detail or "")


@pytest.mark.anyio
async def test_without_the_step_in_the_plan_the_article_is_not_asked(tmp_path):
    mcp = _stand(
        tmp_path,
        shelf={
            MILK: [_card(101, MILK, 53.49)],
            CHEESE: [_card(203, "Сир Комо Едам", 99.0)],
            "202": [_card(202, CHEESE, 129.0)],
        },
    )
    plan = [name for name in PLAN if name != "shelf.by_article"]
    assembled = await assemble_list(
        mcp, llm=_PlanningLLM(plan), request=BuildRequest(mode="week"), now=NOW, settings=_cfg()
    )

    assert all(s.id != "step-article" for s in assembled.basket.trace)
    cheese = next(line for line in assembled.basket.lines if line.name.startswith("Сир Комо"))
    assert cheese.external_product_id == "203"


@pytest.mark.anyio
async def test_the_done_step_says_what_ran_what_waits_for_checkout_and_what_did_not(tmp_path):
    mcp = _stand(tmp_path, shelf={MILK: [_card(101, MILK, 53.49)], CHEESE: [], "202": []})
    assembled = await assemble_list(
        mcp, llm=_PlanningLLM(PLAN), request=BuildRequest(mode="week"), now=NOW, settings=_cfg()
    )

    done = next(s for s in assembled.basket.trace if s.id == "step-plan-done")
    assert done.args["на оформлення"] == 3
    assert "ще 3 чекають на «Оформити»" in done.result_summary
    assert "1 не вдалось" in done.result_summary
    assert done.args["збій"] == 1
    assert done.args["кроки"]["на оформлення"] == ["cart.slot", "cart.write", "cart.reread"]
    assert done.args["кроки"]["збій"] == [
        "decide.pick — модель недоступна (не планування -- мовчу) — план за історією"
    ]
    assert done.args["кроки"]["не знадобилось"] == []
    assert done.args["нема чого дати"] == 0
    assert done.args["виконано"] == len(PLAN) - 4
    assert done.tag == f"{len(PLAN) - 4}/{len(PLAN)}"


@pytest.mark.anyio
async def test_without_a_model_the_plan_is_from_code_and_the_trace_says_so(tmp_path):
    mcp = _stand(tmp_path, shelf={MILK: [_card(101, MILK, 53.49)], CHEESE: [], "202": []})
    assembled = await assemble_list(
        mcp, llm=None, request=BuildRequest(mode="week"), now=NOW, settings=_cfg()
    )

    step = next(s for s in assembled.basket.trace if s.id == "step-plan")
    assert step.tag == "план з коду"
    assert step.result_summary.startswith("без моделі: план з коду")
    assert assembled.plan is not None and assembled.plan.source == "code"


@pytest.mark.anyio
async def test_a_lost_intent_refuses_the_basket_instead_of_shrinking_it(tmp_path, monkeypatch):
    from komora.core.goal import Duty, Goal

    mcp = _stand(tmp_path, shelf={MILK: [_card(101, MILK, 53.49)], CHEESE: [], "202": []})
    monkeypatch.setattr(
        "komora.agent.basket.basket_goal",
        lambda **_: Goal(
            duties=(Duty(name="кожен намір має адресу", ok=False, why="загублено 1: кава"),)
        ),
    )

    with pytest.raises(AssemblyError, match="загублено 1: кава"):
        await assemble_list(
            mcp, llm=None, request=BuildRequest(mode="week"), now=NOW, settings=_cfg()
        )


@pytest.mark.anyio
async def test_the_article_step_brings_own_articles_of_the_same_kind_for_the_chain(tmp_path):
    from komora.agent.basket import Naming, _cache_names, forget_intents
    from komora.core.substitution import Source

    other = "Молоко Яготинське 2,5%"
    forget_intents()
    _cache_names(
        {
            MILK: Naming(intent="молоко"),
            other: Naming(intent="молоко"),
            CHEESE: Naming(intent="сир"),
        }
    )
    try:
        mcp = _stand(
            tmp_path,
            shelf={
                MILK: [_card(101, MILK, 53.49)],
                CHEESE: [_card(203, "Сир Комо Едам", 99.0)],
                "202": [_card(202, CHEESE, 129.0)],
                "303": [_card(303, other, 49.0)],
            },
            extra_orders=[_bought(day, 303, other) for day in (200, 150, 12)],
        )
        assembled = await assemble_list(
            mcp, llm=_PlanningLLM(PLAN), request=BuildRequest(mode="week"), now=NOW, settings=_cfg()
        )
    finally:
        forget_intents()
    article = next(s for s in assembled.basket.trace if s.id == "step-article")
    assert article.args["того ж виду"] == 1 and article.args["того ж виду на полиці"] == 1
    milk = next(line for line in assembled.lines if str(line.product["externalProductId"]) == "101")
    assert milk.chain and milk.chain[0].external_product_id == "303"
    assert milk.chain[0].source is Source.HISTORY
