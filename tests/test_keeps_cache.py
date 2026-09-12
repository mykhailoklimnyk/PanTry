from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import pytest
from structlog.testing import capture_logs

from komora.agent.basket import (
    HistoryItem,
    Naming,
    apply_keeps,
    forget_keeps,
    intent_keeps,
    kind_key,
)
from komora.core.cycles import Keeps
from komora.db import facts as store


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


class _KeepsLLM:
    model = "fake-model"

    def __init__(self, kinds: list[dict[str, Any]]) -> None:
        self.kinds = kinds
        self.calls = 0
        self.asked_about: list[list[str]] = []

    async def decide(
        self, *, system, user, schema, schema_name="decision", max_tokens=2048, **_
    ):
        import json

        from komora.agent.llm import Decision, Usage

        self.calls += 1
        self.asked_about.append(json.loads(user)["види"])
        return Decision(
            data={"kinds": self.kinds},
            text="",
            model=self.model,
            usage=Usage(1, 1),
            duration_ms=1,
        )


@pytest.fixture(autouse=True)
def _clean_cache():
    forget_keeps()
    yield
    forget_keeps()


async def test_the_model_is_asked_once_and_the_answer_is_reused():
    llm = _KeepsLLM([{"label": "хліб", "keeps": "дні"}])

    first = await intent_keeps(llm, ["хліб"])
    second = await intent_keeps(llm, ["хліб"])

    assert first == {"хліб": Keeps.DAYS}
    assert second == first
    assert llm.calls == 1


async def test_what_the_database_already_knows_is_not_asked_again():
    pool = _Pool(
        [
            {
                "label_sha": store.fingerprint("хліб"),
                "keeps": "дні",
                "sanity": None,
                "rhythm_lies": None,
                "per_day": None,
                "per_day_unit": None,
                "aisle": None,
            }
        ]
    )
    llm = _KeepsLLM([])

    got = await intent_keeps(llm, ["хліб"], pool=pool)

    assert got == {"хліб": Keeps.DAYS}
    assert llm.calls == 0


async def test_an_echo_that_does_not_match_the_question_is_thrown_away():
    llm = _KeepsLLM([{"label": "хлібчик", "keeps": "дні"}])

    with capture_logs() as logs:
        got = await intent_keeps(llm, ["хліб"])

    assert got == {}
    assert any(entry["event"] == "keeps.echo_mismatch" for entry in logs)


async def test_an_echo_that_lost_the_separator_still_lands_on_the_asked_label():
    llm = _KeepsLLM([{"label": "йогурт фруктовий", "keeps": "дні"}])

    with capture_logs() as logs:
        got = await intent_keeps(llm, ["йогурт · фруктовий"])

    assert got == {"йогурт · фруктовий": Keeps.DAYS}
    assert any(entry["event"] == "keeps.echo_drifted" for entry in logs)
    assert not any(entry["event"] == "keeps.echo_mismatch" for entry in logs)


async def test_a_dead_database_leaves_the_pantry_working():
    llm = _KeepsLLM([{"label": "хліб", "keeps": "дні"}])

    with capture_logs() as logs:
        got = await intent_keeps(llm, ["хліб"], pool=_DeadPool())

    assert got == {"хліб": Keeps.DAYS}
    assert any(entry["event"] == "pantry.keeps.cache_unreadable" for entry in logs)


async def test_a_model_that_refuses_takes_nothing_down_with_it():
    class _Broken:
        model = "fake"

        async def decide(self, **_):
            raise RuntimeError("модель мовчить")

    with capture_logs() as logs:
        assert await intent_keeps(_Broken(), ["хліб"]) == {}

    assert any(entry["event"] == "pantry.keeps.failed" for entry in logs)


async def test_one_broken_batch_does_not_take_the_others_down_with_it():

    class _HalfBroken:
        model = "fake"

        def __init__(self) -> None:
            self.calls = 0

        async def decide(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise RuntimeError("перша пачка мовчить")
            from komora.agent.llm import Decision, Usage

            return Decision(
                data={"kinds": [{"label": "молоко", "keeps": "дні"}]},
                text="",
                model=self.model,
                usage=Usage(1, 1),
                duration_ms=1,
            )

    llm = _HalfBroken()
    with capture_logs() as logs:
        got = await intent_keeps(llm, ["хліб", "молоко"], batches=2)

    assert llm.calls == 2, "пачок було не дві -- тест міряє не те"
    assert got == {"молоко": Keeps.DAYS}, "жива пачка мусить долетіти"
    assert any(entry["event"] == "pantry.keeps.batch_failed" for entry in logs)
    assert not any(entry["event"] == "pantry.keeps.failed" for entry in logs)


async def test_a_word_outside_the_tiers_means_no_ceiling_and_not_a_short_one():
    llm = _KeepsLLM([{"label": "хліб", "keeps": "інколи"}])

    assert await intent_keeps(llm, ["хліб"]) == {}


def _item(name: str) -> HistoryItem:
    return HistoryItem(
        lager_id=name,
        name=name,
        unit="шт",
        receipts=3,
        qty_total=3,
        recent_receipts=1,
        qty_recent=1,
        moments=[],
    )


def test_the_ceiling_lands_on_the_sku_through_the_label_of_its_kind():
    bread = _item("Хліб Рум'янець цільнозерновий")
    other = _item("Сіль кам'яна")
    names = {
        kind_key(bread.name): Naming(intent="хліб", subtype="цільнозерновий"),
        kind_key(other.name): Naming(intent="сіль"),
    }

    apply_keeps(
        [bread, other],
        names,
        {"хліб · цільнозерновий": Keeps.DAYS, "сіль": Keeps.YEARS},
    )

    assert bread.keeps is Keeps.DAYS
    assert other.keeps is Keeps.YEARS


def test_a_ceiling_taken_away_disappears_from_the_row_that_was_already_read():
    bread = _item("Хліб Рум'янець цільнозерновий")
    bread.keeps = Keeps.DAYS

    apply_keeps([bread], {}, {})

    assert bread.keeps is None


async def test_an_echo_never_crosses_from_one_batch_into_another():

    class _Crossing:
        model = "fake"

        def __init__(self) -> None:
            self.calls = 0
            self.asked_about: list[list[str]] = []

        async def decide(self, *, user, **_):
            import json

            from komora.agent.llm import Decision, Usage

            self.calls += 1
            self.asked_about.append(json.loads(user)["види"])
            kinds = (
                []
                if self.calls == 1
                else [{"label": "йогурт фруктовий", "keeps": "дні"}]
            )
            return Decision(
                data={"kinds": kinds}, text="", model=self.model, usage=Usage(1, 1), duration_ms=1
            )

    llm = _Crossing()
    with capture_logs() as logs:
        got = await intent_keeps(llm, ["йогурт · фруктовий", "ковбаса · салямі"], batches=2)

    assert llm.calls == 2, "пачок було не дві -- тест міряє не те"
    assert llm.asked_about[0] == ["йогурт · фруктовий"]
    assert got == {}, "луна другої пачки лягла під мітку першої"
    assert any(entry["event"] == "keeps.echo_mismatch" for entry in logs)
