from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import pytest

from komora.core.bar import DrinkKind
from komora.db import pantry as store

pytestmark = pytest.mark.anyio


class _Conn:
    def __init__(self, rows: list[dict[str, Any]], written: list[Any]) -> None:
        self._rows = rows
        self.written = written

    async def execute(self, sql: str, args: Any = None) -> Any:
        self.written.append((sql.split()[0], args))
        return self

    async def fetchall(self) -> list[dict[str, Any]]:
        return self._rows


class _Pool:

    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.written: list[Any] = []
        self._rows = rows or []

    @asynccontextmanager
    async def connection(self, **_: Any):
        yield _Conn(self._rows, self.written)


async def test_the_shelf_comes_back_as_a_shelf_and_not_as_a_string():
    pool = _Pool([{"kind": "лікер", "grp": "strong"}])

    assert await store.load_drinks(pool, "акаунт") == {"лікер": DrinkKind.STRONG}


async def test_a_shelf_nobody_knows_is_skipped_and_not_defaulted():
    pool = _Pool([{"kind": "лікер", "grp": "ром"}, {"kind": "віскі", "grp": "strong"}])

    assert await store.load_drinks(pool, "акаунт") == {"віскі": DrinkKind.STRONG}


async def test_an_account_we_do_not_know_asks_the_base_for_nothing():
    pool = _Pool([{"kind": "лікер", "grp": "strong"}])

    assert await store.load_drinks(pool, "") == {}
    assert pool.written == []


async def test_a_shelf_that_is_not_ours_never_reaches_the_base():
    pool = _Pool()

    await store.save_drink(pool, "акаунт", "лікер", "ром")

    assert pool.written == []


async def test_a_shelf_of_ours_does_reach_the_base():
    pool = _Pool()

    await store.save_drink(pool, "акаунт", "лікер", "strong")

    assert pool.written == [("insert", {"account": "акаунт", "kind": "лікер", "grp": "strong"})]


async def test_a_word_without_a_kind_is_not_written():
    pool = _Pool()

    await store.save_drink(pool, "акаунт", "   ", "strong")
    await store.save_drink(pool, "", "лікер", "strong")

    assert pool.written == []


async def test_taking_the_word_back_deletes_the_row():
    pool = _Pool()

    await store.drop_drink(pool, "акаунт", "лікер")

    assert pool.written == [("delete", {"account": "акаунт", "kind": "лікер"})]


async def test_taking_back_nothing_touches_nothing():
    pool = _Pool()

    await store.drop_drink(pool, "акаунт", "  ")
    await store.drop_drink(pool, "", "лікер")

    assert pool.written == []
