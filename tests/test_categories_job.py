from __future__ import annotations

import json
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

import pytest

from komora.core.dictionary import Dictionary, Level, Node
from komora.db import categories as store
from komora.jobs.categories import PAGE, fetch_all, parse_node

FIXTURE = Path(__file__).parent / "fixtures" / "categories_response.json"
BRANCH = "test-branch"


@pytest.fixture(scope="module")
def raw() -> dict[str, Any]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.fixture
def tree(raw: dict[str, Any]) -> Dictionary:
    return Dictionary(parse_node(item) for item in raw["categories"])


def test_fixture_matches_the_shape_we_rely_on(raw: dict[str, Any]) -> None:
    assert raw["categories"]
    assert raw["meta"]["total"] == len(raw["categories"])
    for item in raw["categories"]:
        assert {"id", "title", "slug"} <= set(item)


def test_every_node_parses(raw: dict[str, Any]) -> None:
    nodes = [parse_node(item) for item in raw["categories"]]
    assert len(nodes) == len(raw["categories"])
    assert all(node.id and node.title for node in nodes)
    assert any(node.parent_id for node in nodes)


def test_root_has_no_parent(raw: dict[str, Any]) -> None:
    node = parse_node({"id": "x", "title": "Риба", "slug": "ryba-1"})
    assert node.parent_id is None
    assert node.slug == "ryba-1"


def test_milk_resolves_to_its_node(tree: Dictionary) -> None:
    match = tree.best("молоко")
    assert match is not None
    assert match.node.title == "Молоко"
    assert match.level is Level.TITLE


def test_word_inside_a_longer_title_is_a_weaker_match(tree: Dictionary) -> None:
    levels = {m.node.title: m.level for m in tree.lookup("риба")}
    assert levels["Риба"] is Level.TITLE
    assert levels["Свіжа риба"] is Level.WORD


def test_receipt_singular_reaches_the_plural_node(tree: Dictionary) -> None:
    match = tree.best("огірок")
    assert match is not None
    assert match.node.title == "Огірки"


def test_strawberry_is_missing_and_that_is_the_limit(tree: Dictionary) -> None:
    assert tree.lookup("полуниця") == ()
    assert tree.lookup("сьомга") == ()
    assert tree.best("риба") is not None


def test_fish_is_broad_and_the_tree_says_by_what(tree: Dictionary) -> None:
    narrowing = tree.narrowing("риба")
    assert "Свіжа риба" in narrowing
    assert len(narrowing) > 5


def test_roots_are_the_top_level(tree: Dictionary) -> None:
    titles = {node.title for node in tree.roots()}
    assert {"Риба", "Фрукти, овочі", "Молочні продукти та яйця"} <= titles
    assert "Овочі" not in titles


class _Outcome:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload_raw = payload


class _MCP:

    def __init__(self, pages: list[dict[str, Any]]) -> None:
        self.pages = pages
        self.calls: list[dict[str, Any]] = []

    async def call(self, tool: str, args: dict[str, Any]) -> _Outcome:
        self.calls.append(args)
        index = args["offset"] // PAGE
        return _Outcome(self.pages[index] if index < len(self.pages) else {"categories": []})


def _page(nodes: list[dict[str, Any]], total: int) -> dict[str, Any]:
    return {"categories": nodes, "meta": {"total": total}}


@pytest.mark.asyncio
async def test_pagination_walks_until_everything_is_read() -> None:
    first = [{"id": f"a{i}", "title": f"Вузол {i}", "slug": "s"} for i in range(PAGE)]
    second = [{"id": "b1", "title": "Останній", "slug": "s"}]
    mcp = _MCP([_page(first, PAGE + 1), _page(second, PAGE + 1)])

    nodes = await fetch_all(mcp, branch_id=BRANCH)  # type: ignore[arg-type]

    assert len(nodes) == PAGE + 1
    assert [call["offset"] for call in mcp.calls] == [0, PAGE]
    assert all(call["branchId"] == BRANCH for call in mcp.calls)


@pytest.mark.asyncio
async def test_one_page_is_one_call() -> None:
    mcp = _MCP([_page([{"id": "a", "title": "Риба", "slug": "s"}], 1)])
    nodes = await fetch_all(mcp, branch_id=BRANCH)  # type: ignore[arg-type]
    assert len(nodes) == 1
    assert len(mcp.calls) == 1


@pytest.mark.asyncio
async def test_empty_answer_does_not_loop() -> None:
    mcp = _MCP([_page([], 1010)])
    assert await fetch_all(mcp, branch_id=BRANCH) == ()  # type: ignore[arg-type]
    assert len(mcp.calls) == 1


class _Result:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    async def fetchall(self) -> list[dict[str, Any]]:
        return self._rows


class _Cursor:
    def __init__(self, sink: list[tuple[str, Any]]) -> None:
        self._sink = sink

    async def __aenter__(self) -> _Cursor:
        return self

    async def __aexit__(self, *exc: object) -> bool:
        return False

    async def executemany(self, query: str, rows: Any) -> None:
        self._sink.append(("many", list(rows)))

    async def execute(self, query: str, params: Any = None) -> None:
        self._sink.append(("gone", params))


class _Conn:
    def __init__(self, rows: list[dict[str, Any]], sink: list[tuple[str, Any]]) -> None:
        self._rows = rows
        self._sink = sink

    async def execute(self, query: str, params: Any = None) -> _Result:
        return _Result(self._rows)

    def cursor(self) -> _Cursor:
        return _Cursor(self._sink)


class _Pool:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.written: list[tuple[str, Any]] = []
        self._rows = rows or []

    @asynccontextmanager
    async def connection(self):
        yield _Conn(self._rows, self.written)


@pytest.mark.asyncio
async def test_known_tree_reads_back_as_nodes() -> None:
    pool = _Pool([{"id": "a", "parent_id": None, "slug": "s", "title": "Риба"}])
    assert await store.load(pool) == (Node("a", "Риба", None, "s"),)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_empty_tree_is_refused_not_written() -> None:
    pool = _Pool()
    with pytest.raises(ValueError):
        await store.save(pool, [])  # type: ignore[arg-type]
    assert pool.written == []


@pytest.mark.asyncio
async def test_save_marks_the_missing_ones_gone() -> None:
    pool = _Pool()
    await store.save(pool, [Node("a", "Риба")])  # type: ignore[arg-type]
    kinds = [kind for kind, _ in pool.written]
    assert kinds == ["many", "gone"]
    assert pool.written[1][1] == {"ids": ["a"]}
