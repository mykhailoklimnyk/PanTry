from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from komora.agent import basket
from komora.agent.basket import Naming, assemble_list
from komora.agent.llm import Decision, Usage
from komora.api.schemas import BuildRequest, ClarifyAnswer
from komora.core.ambiguity import MAX_QUESTIONS
from komora.mcp.client import SilpoMCP

NOW = datetime(2026, 9, 5, tzinfo=UTC)
SLOT = {
    "start": "2026-09-05T11:30:00+00:00",
    "end": "2026-09-05T13:00:00+00:00",
    "available": True,
    "deliveryType": "DeliveryHome",
    "deliveryCost": 89,
    "deliveryCostMap": [{"cost": 59, "fromOrderCost": 1199}],
    "minOrderCost": 599,
    "maxWeight": 50,
}

RONIK = "Фініки Ронік Деглет Нур сушені"
TUNIS = "Фініки Туніс"
FRESH = "Фініки Eat4fit свіжі"
ASK = "Вас цікавлять фініки сушені чи свіжі?"


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
        "displayRatio": "200г",
        "companyId": "00000000-0000-4000-8000-000000000001",
        "branchId": "00000000-0000-4000-8000-000000000002",
        "externalProductId": pid,
    }


def _bought(days_ago: int, lager: int, name: str) -> dict:
    return {
        "createdAt": (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%d"),
        "products": [{"lagerId": lager, "name": name, "unit": "200г", "quantity": 1, "price": 99}],
    }


class _AskingLLM:

    model = "fake-model"

    def __init__(self, picks: list[dict]) -> None:
        self.picks = picks

    async def decide(self, *, system, user, schema, schema_name="decision", max_tokens=2048, **_):
        return Decision(
            data={"picks": self.picks},
            text="",
            model=self.model,
            usage=Usage(1, 1),
            duration_ms=1,
        )


def _stand(tmp_path, *, orders: list[dict], shelf: dict[str, list[dict]]) -> SilpoMCP:
    (tmp_path / "silpo_get_time_slots.json").write_text(
        json.dumps({"slots": [SLOT]}), encoding="utf-8"
    )
    (tmp_path / "silpo_get_my_offline_orders.json").write_text(
        json.dumps({"orders": orders}), encoding="utf-8"
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
    return SilpoMCP(fixtures_dir=tmp_path)


@pytest.fixture
def named() -> None:
    basket._cache_names(
        {
            RONIK: Naming(intent="фініки", subtype="сушені"),
            TUNIS: Naming(intent="фініки", subtype="туніські"),
        }
    )


def _due(lager: int, name: str) -> list[dict]:
    return [_bought(day, lager, name) for day in (50, 40, 30, 20)]


@pytest.mark.anyio
async def test_two_intents_of_one_kind_ask_only_once(tmp_path, named) -> None:
    mcp = _stand(
        tmp_path,
        orders=_due(901, RONIK) + _due(902, TUNIS),
        shelf={RONIK: [_card(903, FRESH, 199.0)], TUNIS: [_card(903, FRESH, 199.0)]},
    )
    llm = _AskingLLM(
        [
            {"intent": RONIK, "chosen_id": "", "qty": 1, "ask": ASK},
            {"intent": TUNIS, "chosen_id": "", "qty": 1, "ask": ASK},
        ]
    )

    assembled = await assemble_list(mcp, llm=llm, request=BuildRequest(mode="week"), now=NOW)

    assert len(assembled.basket.questions) == 1


@pytest.mark.anyio
async def test_the_merged_intent_names_itself_in_the_trace(tmp_path, named) -> None:
    mcp = _stand(
        tmp_path,
        orders=_due(901, RONIK) + _due(902, TUNIS),
        shelf={RONIK: [_card(903, FRESH, 199.0)], TUNIS: [_card(903, FRESH, 199.0)]},
    )
    llm = _AskingLLM(
        [
            {"intent": RONIK, "chosen_id": "", "qty": 1, "ask": ASK},
            {"intent": TUNIS, "chosen_id": "", "qty": 1, "ask": ASK},
        ]
    )

    assembled = await assemble_list(mcp, llm=llm, request=BuildRequest(mode="week"), now=NOW)

    step = next(s for s in assembled.basket.trace if s.id == "step-ask")
    assert len(step.args["злито в сусіднє"]) == 1
    assert "злито в сусіднє питання: 1" in step.result_summary


@pytest.mark.anyio
async def test_the_merged_intent_does_not_go_into_the_basket_unasked(tmp_path, named) -> None:
    mcp = _stand(
        tmp_path,
        orders=_due(901, RONIK) + _due(902, TUNIS),
        shelf={RONIK: [_card(903, FRESH, 199.0)], TUNIS: [_card(903, FRESH, 199.0)]},
    )
    llm = _AskingLLM(
        [
            {"intent": RONIK, "chosen_id": "903", "qty": 1, "ask": ASK},
            {"intent": TUNIS, "chosen_id": "903", "qty": 1, "ask": ASK},
        ]
    )

    assembled = await assemble_list(mcp, llm=llm, request=BuildRequest(mode="week"), now=NOW)

    assert assembled.basket.lines == []


@pytest.mark.anyio
async def test_the_duplicate_does_not_eat_a_slot_under_the_question_ceiling(tmp_path) -> None:
    other = ("Сир Комо гауда", "Кава Лавацца зерно")
    basket._cache_names(
        {
            RONIK: Naming(intent="фініки", subtype="сушені"),
            TUNIS: Naming(intent="фініки", subtype="туніські"),
            other[0]: Naming(intent="сир", subtype="твердий"),
            other[1]: Naming(intent="кава", subtype="зернова"),
        }
    )
    mcp = _stand(
        tmp_path,
        orders=(_due(901, RONIK) + _due(904, other[0]) + _due(905, other[1]) + _due(902, TUNIS)),
        shelf={
            RONIK: [_card(903, FRESH, 199.0)],
            TUNIS: [_card(903, FRESH, 199.0)],
            other[0]: [_card(906, "Сир Комо гауда шматок", 149.0)],
            other[1]: [_card(907, "Кава Лавацца зерно 1кг", 599.0)],
        },
    )
    llm = _AskingLLM(
        [
            {"intent": RONIK, "chosen_id": "", "qty": 1, "ask": ASK},
            {"intent": other[0], "chosen_id": "", "qty": 1, "ask": "Який саме сир?"},
            {"intent": other[1], "chosen_id": "", "qty": 1, "ask": "Яка саме кава?"},
            {"intent": TUNIS, "chosen_id": "", "qty": 1, "ask": ASK},
        ]
    )

    assembled = await assemble_list(mcp, llm=llm, request=BuildRequest(mode="week"), now=NOW)

    assert len(assembled.basket.questions) == MAX_QUESTIONS
    step = next(s for s in assembled.basket.trace if s.id == "step-ask")
    assert step.args["злито в сусіднє"] == [f"«{TUNIS}» -> «{RONIK}»"]
    assert not any(
        item.intent == TUNIS and "понад стелю" in item.reason for item in assembled.basket.postponed
    )


@pytest.mark.anyio
async def test_one_answer_closes_both_intents(tmp_path, named) -> None:
    mcp = _stand(
        tmp_path,
        orders=_due(901, RONIK) + _due(902, TUNIS),
        shelf={
            RONIK: [_card(903, FRESH, 199.0)],
            TUNIS: [_card(903, FRESH, 199.0)],
            "фініки свіжі": [_card(903, FRESH, 199.0)],
        },
    )
    llm = _AskingLLM(
        [
            {"intent": RONIK, "chosen_id": "903", "qty": 1},
            {"intent": TUNIS, "chosen_id": "", "qty": 1, "ask": ASK},
        ]
    )

    assembled = await assemble_list(
        mcp,
        llm=llm,
        request=BuildRequest(
            mode="week",
            answers=[ClarifyAnswer(intent=RONIK, query="фініки свіжі")],
        ),
        now=NOW,
    )

    assert assembled.basket.questions == []
    assert [line.name for line in assembled.basket.lines] == [FRESH]
