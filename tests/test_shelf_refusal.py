from __future__ import annotations

from typing import Any

import pytest

from komora.agent.basket import search_products, shelf_recognises
from komora.core.silence import Silence
from komora.mcp.client import MCPCallError

SLOT = {
    "deliveryType": "DeliveryHome",
    "start": "2026-09-12T06:00:00+00:00",
    "end": "2026-09-12T08:00:00+00:00",
}


class _Shelf:

    def __init__(self, poison: str) -> None:
        self.poison = poison
        self.batches: list[list[str]] = []
        self.silence = Silence()

    async def call(self, tool: str, arguments: dict[str, Any]) -> Any:
        queries = list(arguments["products"])
        self.batches.append(queries)
        if self.poison in queries:
            raise MCPCallError(tool, "Server returned an error response", attempts=4)
        payload = {
            "queries": [
                {"query": q, "products": [{"externalProductId": q, "name": q, "available": True}]}
                for q in queries
            ]
        }
        return type("Outcome", (), {"payload_raw": payload, "payload": payload, "duration_ms": 1})()


@pytest.mark.anyio
async def test_a_poisoned_article_costs_one_query_not_the_batch() -> None:
    shelf = _Shelf(poison="45823")
    queries = ["1020221", "904546", "838137", "45823", "914280", "32571", "830986", "892644"]

    found, _ms = await search_products(shelf, queries, SLOT, "id:1")

    assert found["45823"] == []
    assert all(found[q] and found[q][0]["externalProductId"] == q for q in queries if q != "45823")
    assert shelf.batches[0] == queries, "здорова пачка спершу питається цілком"
    assert all(len(batch) < 8 for batch in shelf.batches[1:])


@pytest.mark.anyio
async def test_a_healthy_batch_costs_one_call() -> None:
    shelf = _Shelf(poison="нема")
    found, _ms = await search_products(shelf, ["а", "б"], SLOT, "id:1")
    assert len(shelf.batches) == 1 and set(found) == {"а", "б"}


def test_the_shelf_recognises_a_typed_catalogue_name_but_not_a_greeting() -> None:
    hit = {"name": "Напій на основі рому Oakheart Original 35%"}
    assert shelf_recognises("Напій на основі рому Oakheart Original 35%", [hit])
    assert shelf_recognises("ром Oakheart", [hit])
    assert not shelf_recognises("привіт як справи", [hit])
    assert not shelf_recognises("+380671234567", [hit])
    assert not shelf_recognises("ром Oakheart", [])
