from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from fastapi import HTTPException

from komora.agent import kinds
from komora.agent.basket import Assembled, PlanLine
from komora.agent.options import options_for
from komora.api import app as api
from komora.api import runs
from komora.api.schemas import Basket
from komora.auth.session import GuestSession
from komora.core.dictionary import Dictionary, Node
from komora.core.silence import Silence
from komora.mcp.client import SEARCH_TOOL, MCPCallError, counted_silence

GUEST = GuestSession(access="токен-гостя")
OTHER = GuestSession(access="токен-сусіда")

SLOT = {
    "start": "2026-08-19T07:00:00+00:00",
    "end": "2026-08-19T08:30:00+00:00",
    "deliveryType": "DeliveryHome",
}

TREE = Dictionary(
    [
        Node("water", "Вода мінеральна", None, "mineralna-voda-5091"),
    ]
)

LISTING = [
    {
        "externalProductId": 501,
        "name": "Поляна Квасова 0,5 л",
        "price": 39.9,
        "stock": 12,
        "available": True,
        "displayRatio": "0,5л",
        "image": "https://cdn.silpo.ua/501.png",
        "slug": "voda-polyana-kvasova-0-5-l-501",
    },
    {
        "externalProductId": 502,
        "name": "Моршинська сильногазована 1,5 л",
        "price": 27.5,
        "stock": 40,
        "available": True,
        "displayRatio": "1,5л",
    },
    {
        "externalProductId": 500,
        "name": "Вода Карпатська 1,5 л",
        "price": 28.9,
        "stock": 3,
        "available": True,
    },
]


class _Outcome:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload_raw = payload
        self.duration_ms = 5


SHELF = [
    *LISTING,
    {
        "externalProductId": 900,
        "name": "Вермішель Мівіна з куркою 59,2 г",
        "price": 21.9,
        "stock": 60,
        "available": True,
    },
    {
        "externalProductId": 901,
        "name": "Вода мінеральна Боржомі 0,33 л",
        "price": 59.9,
        "stock": 8,
        "available": True,
    },
]


class _MCP:

    def __init__(
        self,
        *,
        listing: list[dict[str, Any]] | None = None,
        shelf: list[dict[str, Any]] | None = None,
        tree: bool = True,
    ) -> None:
        self._listing = LISTING if listing is None else listing
        self._shelf = SHELF if shelf is None else shelf
        self._tree = tree
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.silence = Silence()

    def _seen(self, raw: dict[str, Any]) -> _Outcome:
        self.silence = counted_silence(self.silence, SEARCH_TOOL, raw)
        return _Outcome(raw)

    async def call(self, tool: str, arguments: dict[str, Any] | None = None) -> _Outcome:
        args = arguments or {}
        self.calls.append((tool, args))
        if tool == "silpo_get_categories":
            if not self._tree:
                raise MCPCallError(tool, "дерево недоступне", attempts=1)
            return _Outcome({"categories": [], "meta": {"total": 0}})
        if tool == "silpo_get_products":
            return _Outcome({"products": self._listing})
        if tool == SEARCH_TOOL:
            wanted = (args.get("products") or [""])[0]
            return self._seen(
                {
                    "queries": [
                        {
                            "query": wanted,
                            "products": [
                                p for p in self._shelf if wanted.lower() in p["name"].lower()
                            ],
                        }
                    ]
                }
            )
        raise AssertionError(f"зайвий виклик: {tool}")

    async def __aenter__(self) -> _MCP:
        return self

    async def __aexit__(self, *exc: object) -> None:
        return None


def _run() -> Assembled:
    line = PlanLine(
        intent="вода мінеральна",
        product={
            "externalProductId": "500",
            "name": "Вода Карпатська 1,5 л",
            "price": 28.9,
            "branchId": "branch-1",
            "companyId": "company-1",
            "id": "product-1",
        },
        qty=Decimal(6),
        reason="звичне",
        from_history=None,
    )
    return Assembled(
        basket=Basket.model_construct(lines=[], trace=[]), lines=[line], unresolved=[], slot=SLOT
    )


@pytest.fixture(autouse=True)
def tree(monkeypatch):
    monkeypatch.setattr(kinds, "_TREE", TREE)
    yield
    kinds.forget_tree()


async def test_options_are_the_kind_on_the_runs_slot():
    mcp = _MCP()
    options = await options_for(mcp, _run(), article="500")

    assert [o.name for o in options] == [
        "Поляна Квасова 0,5 л",
        "Моршинська сильногазована 1,5 л",
    ], "сам рядок зі списку прибирається"
    tool, args = mcp.calls[0]
    assert tool == "silpo_get_products"
    assert args["timeslotStart"] == SLOT["start"], "перелік — на слот ПРОГОНУ"
    assert args["branchId"] == "branch-1", "і на філію, з якої зібраний рядок"
    assert options[0].ratio == "0,5л"
    assert options[0].stock == 12
    assert options[0].image_url and options[1].image_url is None


async def test_the_card_link_is_built_here_and_only_from_a_slug():
    options = await options_for(_MCP(), _run(), article="500")

    assert options[0].card_url == "https://silpo.ua/product/voda-polyana-kvasova-0-5-l-501"
    assert options[1].card_url is None, "слага немає -- посилання теж"


async def test_search_by_words_is_the_second_path():
    mcp = _MCP()
    options = await options_for(mcp, _run(), article="500", query="Моршинська")

    assert [o.name for o in options] == ["Моршинська сильногазована 1,5 л"]
    assert mcp.calls[0][0] == "silpo_find_products_batch"


async def test_the_kind_listing_proves_the_kind_by_construction():
    options = await options_for(_MCP(), _run(), article="500")

    assert all(o.same_kind is True for o in options)
    assert {o.kind for o in options} == {"Вода мінеральна"}, "вісь названа, її видно"


async def test_a_search_hit_from_another_kind_is_named_as_one():
    mcp = _MCP()
    options = await options_for(mcp, _run(), article="500", query="Мівіна")

    assert [o.name for o in options] == ["Вермішель Мівіна з куркою 59,2 г"]
    assert options[0].same_kind is False
    assert options[0].kind == "Вода мінеральна"
    assert "silpo_get_products" in [tool for tool, _ in mcp.calls], (
        "звірка виду коштує перелік вузла — і платиться лише коли є що судити"
    )


async def test_the_shelf_beyond_the_listing_is_not_an_accusation():
    options = await options_for(_MCP(), _run(), article="500", query="Боржомі")

    assert [o.name for o in options] == ["Вода мінеральна Боржомі 0,33 л"]
    assert options[0].same_kind is True


async def test_without_the_tree_nothing_is_judged():
    kinds.forget_tree()
    options = await options_for(_MCP(tree=False), _run(), article="500", query="Мівіна")

    assert [o.same_kind for o in options] == [None]
    assert options[0].kind is None


async def test_an_empty_kind_is_an_answer_not_an_error():
    mcp = _MCP(listing=[], shelf=[])
    assert await options_for(mcp, _run(), article="500") == []


async def test_a_line_that_is_not_in_the_plan_gives_nothing():
    assert await options_for(_MCP(), _run(), article="999") == []


async def test_someone_elses_run_is_the_same_404_as_a_forgotten_one(monkeypatch):
    monkeypatch.setattr(api, "SilpoMCP", lambda **kwargs: _MCP())
    basket = runs.remember(_run(), owner=GUEST.owner)

    with pytest.raises(HTTPException) as theirs:
        await api.swap_options(basket.run_id, OTHER, line="500")
    with pytest.raises(HTTPException) as forgotten:
        await api.swap_options("немає-такого", GUEST, line="500")

    assert theirs.value.status_code == forgotten.value.status_code == 404
    assert theirs.value.detail == forgotten.value.detail

    mine = await api.swap_options(basket.run_id, GUEST, line="500")
    assert [o.external_product_id for o in mine] == ["501", "502"]
