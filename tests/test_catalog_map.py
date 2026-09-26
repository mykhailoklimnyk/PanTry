from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import pytest

from komora.db import catalog as store


class _Conn:
    def __init__(self, rows: list[dict[str, Any]], written: list[Any]) -> None:
        self._rows = rows
        self.written = written

    async def execute(self, sql: str, args: Any = None) -> Any:
        self.written.append(("query", args))
        return self

    async def fetchall(self) -> list[dict[str, Any]]:
        return self._rows

    async def fetchone(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    @asynccontextmanager
    async def cursor(self):
        yield self

    async def executemany(self, sql: str, rows: Any) -> None:
        self.written.append(("many", rows))


class _Pool:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.written: list[Any] = []
        self._rows = rows or []

    @asynccontextmanager
    async def connection(self, **_: Any):
        yield _Conn(self._rows, self.written)


async def test_the_map_answers_with_frozen_sets_of_nodes():
    pool = _Pool([{"article": "1", "nodes": ["m-iasni-rulety-4747"]}])
    got = await store.load(pool, ["1"])
    assert got == {"1": frozenset({"m-iasni-rulety-4747"})}


async def test_an_article_with_no_nodes_is_still_an_answer():
    pool = _Pool([{"article": "1", "nodes": []}])
    assert await store.load(pool, ["1"]) == {"1": frozenset()}


async def test_a_null_nodes_column_does_not_raise():
    pool = _Pool([{"article": "1", "nodes": None}])
    assert await store.load(pool, ["1"]) == {"1": frozenset()}


async def test_nothing_to_ask_about_does_not_touch_the_database():
    pool = _Pool()
    assert await store.load(pool, []) == {}
    assert pool.written == []


async def test_an_empty_sweep_is_a_refusal_not_an_empty_catalog():
    pool = _Pool()
    with pytest.raises(ValueError):
        await store.save(pool, {}, since="коли завгодно")
    assert pool.written == []


async def test_a_sweep_writes_every_article_and_marks_the_rest_gone():
    pool = _Pool()
    written = await store.save(
        pool, {"1": frozenset({"b", "a"}), "2": frozenset({"c"})}, since="мить"
    )
    assert written == 2
    kinds = [kind for kind, _ in pool.written]
    assert kinds == ["many", "query"], "спершу запис, і лише потім позначка зниклих"


async def test_the_nodes_go_to_the_database_sorted():
    pool = _Pool()
    await store.save(pool, {"1": frozenset({"я", "а"})}, since="мить")
    rows = next(rows for kind, rows in pool.written if kind == "many")
    assert rows[0]["nodes"] == ["а", "я"]


async def test_a_cold_map_reports_zero_and_a_warm_one_reports_its_size():
    assert await store.size(_Pool([{"n": 0}])) == 0
    assert await store.size(_Pool([{"n": 49414}])) == 49414


async def test_a_missing_row_is_not_a_crash():
    assert await store.size(_Pool()) == 0


def test_a_card_is_one_row_and_not_four_aggregates():
    sql = store._BY_PRODUCT.lower()
    assert "distinct on (product_id)" in sql, (
        "картка мусить братись цілим рядком: `distinct on` з детермінованим "
        "порядком, а не агрегатами по полях"
    )
    for mixer in ("min(", "max(", "bool_or(", "bool_and("):
        assert mixer not in sql, (
            f"{mixer} у запиті картки збирає товар з різних рядків — "
            "інформація про товар береться з тієї філії, де його знайшли"
        )
