from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from komora.agent.basket import (
    HistoryItem,
    assemble_list,
    build_chain,
    build_lines,
    history_matches,
)
from komora.api.schemas import BuildRequest
from komora.config import Settings
from komora.mcp.client import SilpoMCP

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 8, 21, tzinfo=UTC)
BRANCH = "00000000-0000-4000-8000-000000000002"

SLOT = {
    "start": "2026-08-21T11:30:00+00:00",
    "end": "2026-08-21T13:00:00+00:00",
    "available": True,
    "deliveryType": "DeliveryHome",
    "deliveryCost": 89,
    "deliveryCostMap": [{"cost": 59, "fromOrderCost": 1199}],
    "minOrderCost": 599,
    "maxWeight": 50,
}


def _product(pid: int, name: str, price: float, stock: int = 20) -> dict:
    return {
        "id": f"00000000-0000-4000-8000-{pid:012d}",
        "name": name,
        "slug": f"slug-{pid}",
        "price": price,
        "oldPrice": None,
        "stock": stock,
        "available": True,
        "image": None,
        "weighted": False,
        "step": 1,
        "displayRatio": "1шт",
        "companyId": "00000000-0000-4000-8000-000000000001",
        "branchId": BRANCH,
        "externalProductId": pid,
    }


TOOTHPASTE = [
    _product(901, "Паста зубна Splat Perfect Care «Досконалий догляд»", 129.0),
    _product(902, "Паста зубна Splat «Біокальцій»", 119.0),
]

MILK = [_product(101, "Молоко Ферма 2,5%", 53.49)]


def _stand(tmp_path, queries: dict[str, list[dict]]) -> SilpoMCP:
    (tmp_path / "silpo_get_time_slots.json").write_text(
        json.dumps({"slots": [SLOT]}), encoding="utf-8"
    )
    (tmp_path / "silpo_get_my_offline_orders.json").write_text(
        json.dumps({"orders": []}), encoding="utf-8"
    )
    (tmp_path / "silpo_find_products_batch.json").write_text(
        json.dumps(
            {
                "queries": [
                    {"query": query, "products": products} for query, products in queries.items()
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "silpo_get_available_delivery_types.json").write_text(
        json.dumps({"options": [{"deliveryType": "DeliveryHome", "branchId": BRANCH}]}),
        encoding="utf-8",
    )
    return SilpoMCP(settings=Settings.model_construct(), fixtures_dir=tmp_path)


async def test_a_phonetic_neighbour_does_not_become_a_line(tmp_path):
    mcp = _stand(tmp_path, {"Спрайт": TOOTHPASTE, "молоко": MILK})
    request = BuildRequest.model_validate({"mode": "week", "shoppingList": ["Спрайт", "молоко"]})

    assembled = await assemble_list(mcp, llm=None, request=request, now=NOW)

    names = [line.name for line in assembled.basket.lines]
    assert not any("Splat" in name for name in names), "зубна паста поїхала як напій"
    assert [line.intent for line in assembled.lines] == ["молоко"]


async def test_the_word_that_found_nothing_is_not_told_to_be_more_specific(tmp_path):
    mcp = _stand(tmp_path, {"Спрайт": TOOTHPASTE, "молоко": MILK})
    request = BuildRequest.model_validate({"mode": "week", "shoppingList": ["Спрайт", "молоко"]})

    assembled = await assemble_list(mcp, llm=None, request=request, now=NOW)

    assert assembled.basket.not_collected == ["Спрайт"]
    assert assembled.unresolved == []


async def test_the_trace_names_what_it_dropped_and_why(tmp_path):
    mcp = _stand(tmp_path, {"Спрайт": TOOTHPASTE, "молоко": MILK})
    request = BuildRequest.model_validate({"mode": "week", "shoppingList": ["Спрайт", "молоко"]})

    assembled = await assemble_list(mcp, llm=None, request=request, now=NOW)

    step = next(s for s in assembled.basket.trace if s.id == "step-stray")
    assert "зі словом: 1" in step.result_summary
    assert step.args["слова"] == ["Спрайт"]
    assert "фонетичний сусід" in (step.decision or "")


async def test_the_named_brand_survives_a_foreign_alphabet(tmp_path):
    mcp = _stand(
        tmp_path,
        {
            "Спрайт": [
                _product(801, "Напій Coca-Cola Classic з/б", 34.99),
                _product(802, "Напій Sprite 0,5 л", 32.99),
            ]
        },
    )
    request = BuildRequest.model_validate({"mode": "week", "shoppingList": ["Спрайт"]})

    assembled = await assemble_list(mcp, llm=None, request=request, now=NOW)

    assert [line.name for line in assembled.basket.lines] == ["Напій Sprite 0,5 л"]


def test_own_purchase_is_found_by_the_word_the_guest_said():
    receipts = [
        HistoryItem(
            lager_id="802",
            name="Напій Sprite 0,5 л",
            unit="шт",
            receipts=4,
            qty_total=Decimal(4),
            recent_receipts=2,
            qty_recent=Decimal(2),
            moments=[NOW],
        )
    ]

    assert [item.lager_id for item in history_matches("Спрайт", receipts)] == ["802"]


def _item(lager_id: str, name: str, *, receipts: int = 3) -> HistoryItem:
    return HistoryItem(
        lager_id=lager_id,
        name=name,
        unit="шт",
        receipts=receipts,
        qty_total=Decimal(receipts),
        recent_receipts=receipts,
        qty_recent=Decimal(receipts),
        moments=[NOW],
    )


def test_a_kind_word_does_not_reach_a_brand_through_the_skeleton() -> None:
    receipts = [
        _item("1", "Йогурт Lekker натуральний 3,4-4,5%", receipts=9),
        _item("2", "Лікер Morandini Limoncello", receipts=2),
        _item("3", "Лікер Molly's Irish Cream", receipts=1),
    ]

    assert [item.lager_id for item in history_matches("лікер", receipts)] == ["2", "3"]


def test_a_brand_word_still_crosses_the_alphabet() -> None:
    receipts = [
        _item("1", "Напій Sprite 0,5 л"),
        _item("2", "Йогурт Lekker натуральний"),
    ]

    assert [item.lager_id for item in history_matches("Спрайт", receipts)] == ["1"]


def test_the_proof_is_taken_from_the_corpus_and_not_from_the_word() -> None:
    from komora.agent.basket import kind_word_proven

    assert kind_word_proven("лікер", ["Лікер Morandini Limoncello", "Йогурт Lekker"])
    assert not kind_word_proven("лікер", ["Йогурт Lekker натуральний"])
    assert not kind_word_proven("спрайт", ["Напій Sprite 0,5 л"])
    assert not kind_word_proven("", ["Лікер Morandini"])


def test_the_chain_of_a_named_brand_stays_inside_the_name():
    sprite = _product(802, "Напій Sprite 0,5 л", 32.99)
    options = [
        sprite,
        _product(803, "Напій Sprite 2 л", 54.99),
        _product(801, "Напій Coca-Cola Classic з/б", 34.99),
    ]

    chain = build_chain("Спрайт", sprite, options)

    assert [link.name for link in chain] == ["Напій Sprite 2 л"]


def test_a_named_brand_without_a_second_package_gets_an_empty_chain():
    sprite = _product(802, "Напій Sprite 0,5 л", 32.99, stock=2)
    options = [sprite, _product(801, "Напій Coca-Cola Classic з/б", 34.99)]

    lines, _, _ = build_lines(["Спрайт"], {"Спрайт": options}, {}, {})

    assert lines[0].chain == ()
    assert lines[0].needs_approval is False
    assert "не підбирати" in (lines[0].mandate or ""), "порожній ланцюжок мовчить"


def test_a_kind_word_keeps_the_whole_shelf_in_its_chain():
    ferma = _product(101, "Молоко Ферма 2,5%", 53.49)
    options = [ferma, _product(102, "Молоко Яготинське 2,6%", 75.99)]

    chain = build_chain("молоко", ferma, options)

    assert [link.name for link in chain] == ["Молоко Яготинське 2,6%"]
