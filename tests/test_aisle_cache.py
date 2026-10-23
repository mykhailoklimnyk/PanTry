from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any

import pytest

from komora.agent.aisle import forget_aisles, intent_aisles, known_aisles
from komora.core.aisles import CATCH_ALL
from komora.db import facts as store

SHELF = ["Бакалія і консерви", "Напої", "Фрукти, овочі", CATCH_ALL]


class _Conn:
    def __init__(self, rows: list[dict[str, Any]], written: list[Any]) -> None:
        self._rows = rows
        self.written = written

    async def execute(self, sql: str, args: Any = None) -> Any:
        self.written.append(("query", args))
        return self

    async def fetchall(self) -> list[dict[str, Any]]:
        return self._rows

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


class _DeadPool:

    @asynccontextmanager
    async def connection(self, **_: Any):
        raise ConnectionError("база не відповідає")
        yield  # pragma: no cover -- недосяжно, але робить це генератором


class _AisleLLM:
    model = "fake-model"

    def __init__(self, kinds: list[dict[str, Any]]) -> None:
        self.kinds = kinds
        self.calls = 0
        self.asked_about: list[list[str]] = []
        self.saw_shelf: list[list[str]] = []

    async def decide(self, *, system, user, schema, schema_name="decision", **_):
        from komora.agent.llm import Decision, Usage

        self.calls += 1
        said = json.loads(user)
        self.asked_about.append(said["види"])
        self.saw_shelf.append(said["відділи"])
        return Decision(
            data={"kinds": self.kinds},
            text="",
            model=self.model,
            usage=Usage(1, 1),
            duration_ms=1,
        )


def row(label_sha: str, aisle: str | None) -> dict[str, Any]:
    return {
        "label_sha": label_sha,
        "keeps": None,
        "sanity": None,
        "rhythm_lies": None,
        "per_day": None,
        "per_day_unit": None,
        "aisle": aisle,
    }


@pytest.fixture(autouse=True)
def _clean_cache():
    forget_aisles()
    yield
    forget_aisles()


async def test_the_model_is_asked_once_and_the_answer_is_reused():
    llm = _AisleLLM([{"label": "сік", "aisle": "Напої"}])

    first = await intent_aisles(llm, ["сік"], SHELF)
    second = await intent_aisles(llm, ["сік"], SHELF)

    assert first == second == {"сік": "Напої"}
    assert llm.calls == 1


async def test_the_closed_list_travels_with_the_question():
    llm = _AisleLLM([])

    await intent_aisles(llm, ["сік"], SHELF)

    assert llm.saw_shelf == [SHELF]


async def test_a_tag_outside_the_list_is_not_taken():
    llm = _AisleLLM([{"label": "сік", "aisle": "Свіжовичавлені соки"}])

    assert await intent_aisles(llm, ["сік"], SHELF) == {}


async def test_an_empty_vocabulary_costs_no_call():
    llm = _AisleLLM([{"label": "сік", "aisle": "Напої"}])

    assert await intent_aisles(llm, ["сік"], []) == {}
    assert llm.calls == 0


async def test_what_the_database_already_knows_is_not_asked_again():
    pool = _Pool([row(store.fingerprint("сік"), "Напої")])
    llm = _AisleLLM([])

    got = await intent_aisles(llm, ["сік"], SHELF, pool=pool)

    assert got == {"сік": "Напої"}
    assert llm.calls == 0


async def test_a_stored_tag_outside_todays_vocabulary_is_asked_again():
    pool = _Pool([row(store.fingerprint("сік"), "Свіжовичавлені соки")])
    llm = _AisleLLM([{"label": "сік", "aisle": "Напої"}])

    got = await intent_aisles(llm, ["сік"], SHELF, pool=pool)

    assert got == {"сік": "Напої"}
    assert llm.calls == 1


async def test_a_row_without_our_column_is_not_an_answer():
    pool = _Pool([row(store.fingerprint("сік"), None)])
    llm = _AisleLLM([{"label": "сік", "aisle": "Напої"}])

    got = await intent_aisles(llm, ["сік"], SHELF, pool=pool)

    assert got == {"сік": "Напої"}
    assert llm.calls == 1


async def test_the_answer_is_written_back():
    pool = _Pool([])
    llm = _AisleLLM([{"label": "сік", "aisle": "Напої"}])

    await intent_aisles(llm, ["сік"], SHELF, pool=pool)

    written = [args for kind, args in pool.written if kind == "many"]
    assert written and written[0][0]["aisle"] == "Напої"


async def test_a_dead_database_leaves_the_call_working():
    llm = _AisleLLM([{"label": "сік", "aisle": "Напої"}])

    assert await intent_aisles(llm, ["сік"], SHELF, pool=_DeadPool()) == {"сік": "Напої"}


async def test_the_echo_is_matched_against_what_this_batch_asked():
    llm = _AisleLLM([{"label": "сік  яблучний", "aisle": "Напої"}])

    assert await intent_aisles(llm, ["сік · яблучний"], SHELF) == {"сік · яблучний": "Напої"}


async def test_an_echo_past_the_list_is_dropped_piecewise():
    llm = _AisleLLM(
        [{"label": "кава", "aisle": "Напої"}, {"label": "сік", "aisle": "Напої"}]
    )

    assert await intent_aisles(llm, ["сік"], SHELF) == {"сік": "Напої"}


async def test_a_silent_model_leaves_the_pantry_working():

    class _Boom:
        model = "fake"

        async def decide(self, **_: Any):
            raise RuntimeError("модель мовчить")

    assert await intent_aisles(_Boom(), ["сік"], SHELF) == {}


async def test_the_cold_flag_asks_without_touching_the_database():
    pool = _Pool([row(store.fingerprint("сік"), "Фрукти, овочі")])
    llm = _AisleLLM([{"label": "сік", "aisle": "Напої"}])

    got = await intent_aisles(llm, ["сік"], SHELF, pool=pool, use_cache=False)

    assert got == {"сік": "Напої"}
    assert [kind for kind, _ in pool.written] == []


async def test_without_a_pool_there_is_no_vocabulary():
    assert await known_aisles(None) == []


async def test_a_dead_database_gives_no_vocabulary_and_says_so():
    from structlog.testing import capture_logs

    with capture_logs() as logs:
        assert await known_aisles(_DeadPool()) == []

    assert any(one["event"] == "pantry.aisle.tree_unreadable" for one in logs)
