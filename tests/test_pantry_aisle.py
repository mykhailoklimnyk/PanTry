from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any, cast

import pytest

from komora.agent.aisle import forget_aisles
from komora.agent.basket import Naming, Tracer
from komora.agent.llm import Decision, Usage
from komora.agent.steps.ground import Ground
from komora.agent.steps.pantry import Home
from komora.api.schemas import Pantry, PantryItem
from komora.config import Settings
from komora.core.facts import Facts
from komora.core.said import Said

NOW = datetime(2026, 8, 26, 12, tzinfo=UTC)
SHELF = ["Бакалія і консерви", "Напої", "Фрукти, овочі"]


def _ground(llm: Any, pool: Any = None) -> Ground:
    return Ground(
        mcp=cast(Any, None),
        cfg=Settings.model_construct(pantry_batches=1),
        moment=NOW,
        facts=Facts(),
        trace=Tracer(None),
        pool=pool,
        llm=llm,
    )


class _Model:
    model = "fake"

    def __init__(self, kinds: list[dict[str, str]]) -> None:
        self.kinds = kinds
        self.calls = 0

    async def decide(self, **_: Any) -> Decision:
        self.calls += 1
        answer = {"kinds": self.kinds}
        return Decision(
            data=answer,
            text=json.dumps(answer),
            model=self.model,
            usage=Usage(1, 1),
            duration_ms=1,
        )


def _home(llm: Any, *, pool: Any = None) -> Home:
    empty = Pantry(items=[], receipts=0, orders=0, kinds=0, tracked_from=3, unlisted=0)
    return Home(_ground(llm, pool), said=Said(), read=None, drawn=empty)  # type: ignore[arg-type]


@pytest.fixture(autouse=True)
def _clean_cache():
    forget_aisles()
    yield
    forget_aisles()


@pytest.fixture
def shelf(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    async def _known(_pool: Any) -> list[str]:
        return SHELF

    monkeypatch.setattr("komora.agent.steps.pantry.known_aisles", _known)
    return SHELF


@pytest.mark.anyio
async def test_the_step_tags_the_labels_it_was_given(shelf: list[str]) -> None:
    llm = _Model([{"label": "сік · яблучний", "aisle": "Напої"}])
    named = {"сік": Naming(intent="сік", subtype="яблучний")}

    made = await _home(llm).aisle({"named": named})

    assert made.facts["aisles"] == {"сік · яблучний": "Напої"}
    assert made.args["відділів у словнику"] == 3
    assert "відділ виду: 1 з 1" in made.summary


@pytest.mark.anyio
async def test_without_a_tree_the_step_says_so_and_costs_no_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:

    async def _known(_pool: Any) -> list[str]:
        return []

    monkeypatch.setattr("komora.agent.steps.pantry.known_aisles", _known)
    llm = _Model([{"label": "сік · яблучний", "aisle": "Напої"}])

    made = await _home(llm).aisle({"named": {"сік": Naming(intent="сік", subtype="яблучний")}})

    assert made.facts["aisles"] == {}
    assert llm.calls == 0
    assert made.summary == "дерева категорій немає — відділ питати нема з чого"


@pytest.mark.anyio
async def test_the_rail_reads_what_the_step_wrote(monkeypatch: pytest.MonkeyPatch) -> None:
    from komora.agent import basket

    seen: dict[str, Any] = {}

    async def _named(llm: Any, labels: Any, vocabulary: Any, **kw: Any) -> dict[str, str]:
        seen["llm"] = llm
        seen["labels"] = list(labels)
        seen["vocabulary"] = list(vocabulary)
        return {"сік · яблучний": "Напої"}

    def _aisles(pairs: Any, cards: Any, roots: Any, said: Any = None) -> Any:
        seen["said"] = dict(said or {})
        return basket.Aisled(of={}, order=())

    async def _cards(_pool: Any, _articles: Any) -> dict[str, frozenset[str]]:
        return {"111": frozenset({"napoi"})}

    async def _tree(_pool: Any) -> list[Any]:
        return []

    monkeypatch.setattr("komora.agent.basket.intent_aisles", _named)
    monkeypatch.setattr("komora.agent.basket.aisles", _aisles)
    monkeypatch.setattr("komora.agent.basket.catalog_store.load", _cards)
    monkeypatch.setattr("komora.agent.basket.categories_store.load", _tree)
    monkeypatch.setattr(
        "komora.agent.basket.catalog.roots_of", lambda _tree: {"Напої": frozenset()}
    )

    row = PantryItem(
        id="111", label="сік · яблучний", unit="шт", state="оцінка", named=True, source="receipts"
    )
    item = basket.HistoryItem(lager_id="111", name="Сік Садочок", unit="шт")

    await basket._aisles_of([row], [item], object())

    assert seen["labels"] == ["сік · яблучний"]
    assert seen["vocabulary"] == ["Напої"]
    assert seen["llm"] is None
    assert seen["said"] == {"111": "Напої"}
