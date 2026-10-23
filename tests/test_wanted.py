from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from komora.agent.basket import assemble_list
from komora.api.schemas import BuildRequest
from komora.mcp.client import SilpoMCP

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 8, 25, tzinfo=UTC)

SLOT = {
    "start": "2026-08-26T11:30:00+00:00",
    "end": "2026-08-26T13:00:00+00:00",
    "available": True,
    "deliveryType": "DeliveryHome",
    "deliveryCost": 89,
    "minOrderCost": 599,
    "maxWeight": 50,
}


def _card(article: int, name: str) -> dict:
    return {
        "id": f"uuid-{article}",
        "externalProductId": article,
        "name": name,
        "price": 30,
        "stock": 10,
        "available": True,
        "step": 1,
        "displayRatio": "1шт",
        "weighted": False,
        "companyId": "company",
        "branchId": "branch",
        "slug": f"slug-{article}",
    }


BREAD_ORDERS = [
    {
        "createdAt": (NOW - timedelta(days=day)).isoformat(),
        "products": [
            {"lagerId": 101, "name": "Хліб Київський", "unit": "шт", "quantity": 1, "price": 30}
        ],
    }
    for day in (2, 9, 16)
]


def _stand(tmp_path) -> SilpoMCP:
    (tmp_path / "silpo_get_time_slots.json").write_text(
        json.dumps({"slots": [SLOT]}), encoding="utf-8"
    )
    (tmp_path / "silpo_get_my_offline_orders.json").write_text(
        json.dumps({"orders": BREAD_ORDERS}), encoding="utf-8"
    )
    (tmp_path / "silpo_get_my_shopping_cart.json").write_text(
        json.dumps({"shoppingCartId": None}), encoding="utf-8"
    )
    (tmp_path / "silpo_find_products_batch.json").write_text(
        json.dumps(
            {
                "queries": [
                    {"query": "батарейки", "products": [_card(301, "Батарейки AA Varta")]},
                    {"query": "Хліб Київський", "products": [_card(101, "Хліб Київський")]},
                ]
            }
        ),
        encoding="utf-8",
    )
    return SilpoMCP(fixtures_dir=tmp_path)


async def test_a_row_from_the_list_reaches_the_basket(tmp_path):
    built = await assemble_list(
        _stand(tmp_path),
        llm=None,
        request=BuildRequest.model_validate({"mode": "week"}),
        now=NOW,
        wanted={"батарейки": "батарейки"},
    )

    assert "батарейки" in {line.intent for line in built.lines}


async def test_the_row_explains_itself_with_the_guests_own_word(tmp_path):
    built = await assemble_list(
        _stand(tmp_path),
        llm=None,
        request=BuildRequest.model_validate({"mode": "week"}),
        now=NOW,
        wanted={"батарейки": "батарейки"},
    )
    row = next(line for line in built.basket.lines if line.name.startswith("Батарейки"))

    assert row.explanation == "ти поклав це в список на цю покупку"


async def test_a_kind_the_pantry_tracks_is_taken_anyway(tmp_path):
    built = await assemble_list(
        _stand(tmp_path),
        llm=None,
        request=BuildRequest.model_validate({"mode": "week"}),
        now=NOW,
        wanted={"хліб київський": "Хліб Київський"},
    )

    assert "Хліб Київський" in {line.intent for line in built.lines}


async def test_a_word_the_guest_typed_now_does_not_double_the_list_row(tmp_path):
    built = await assemble_list(
        _stand(tmp_path),
        llm=None,
        request=BuildRequest.model_validate({"mode": "week", "shoppingList": ["батарейки AA"]}),
        now=NOW,
        wanted={"батарейки": "батарейки"},
    )

    assert sum(1 for line in built.lines if "атарейки" in line.intent) == 1


async def test_the_step_stands_in_the_trace_even_when_nothing_is_new(tmp_path):
    built = await assemble_list(
        _stand(tmp_path),
        llm=None,
        request=BuildRequest.model_validate({"mode": "week", "shoppingList": ["батарейки"]}),
        now=NOW,
        wanted={"батарейки": "батарейки"},
    )
    step = next(s for s in built.basket.trace if s.id == "step-wanted")

    assert step.result_summary.startswith("нового немає")


async def test_an_empty_list_says_nothing_at_all(tmp_path):
    built = await assemble_list(
        _stand(tmp_path),
        llm=None,
        request=BuildRequest.model_validate({"mode": "week", "shoppingList": ["батарейки"]}),
        now=NOW,
    )

    assert not [s for s in built.basket.trace if s.id == "step-wanted"]
