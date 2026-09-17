from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import pytest
from structlog.testing import capture_logs

from komora.agent.basket import Naming, forget_intents, intent_names
from komora.db import intents as store


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
        yield  # pragma: no cover — недосяжно, але робить це генератором


class _NamingLLM:

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
        self.asked_about.append(json.loads(user)["назви"])
        return Decision(
            data={"kinds": self.kinds},
            text="",
            model=self.model,
            usage=Usage(1, 1),
            duration_ms=1,
        )


@pytest.fixture(autouse=True)
def _clean_cache():
    forget_intents()
    yield
    forget_intents()


def test_same_name_written_differently_is_one_entry():
    assert store.fingerprint("Молоко Яготинське") == store.fingerprint("молоко   яготинське")
    assert store.fingerprint("Молоко") != store.fingerprint("Кефір")


def test_fingerprint_does_not_leak_the_name():
    name = "Ліки від тиску"
    assert name.lower() not in store.fingerprint(name)
    assert len(store.fingerprint(name)) == 64


@pytest.mark.asyncio
async def test_known_names_read_back_by_name_not_by_hash():
    pool = _Pool(
        [
            {
                "name_sha": store.fingerprint("Напій Geo"),
                "intent": "вода",
                "subtype": "газована",
                "drink": None,
            }
        ]
    )
    known = await store.load(pool, ["Напій Geo", "Хліб"])  # type: ignore[arg-type]
    assert known == {"Напій Geo": ("вода", "газована", None)}


@pytest.mark.asyncio
async def test_nothing_asked_means_no_query():
    pool = _Pool()
    assert await store.load(pool, []) == {}  # type: ignore[arg-type]
    assert pool.written == []


@pytest.mark.asyncio
async def test_empty_intent_is_not_written():
    pool = _Pool()
    await store.save(pool, {"Хліб": ("", None, None), "   ": ("хліб", None, None)})  # type: ignore[arg-type]
    assert pool.written == []


@pytest.mark.asyncio
async def test_known_name_does_not_reach_the_model():
    llm = _NamingLLM([])
    pool = _Pool(
        [
            {
                "name_sha": store.fingerprint("Напій Geo"),
                "intent": "вода",
                "subtype": "газована",
                "drink": None,
            }
        ]
    )

    names = await intent_names(llm, ["Напій Geo"], pool=pool)  # type: ignore[arg-type]

    assert llm.calls == 0
    assert names["напій geo"] == Naming("вода", "газована")


@pytest.mark.asyncio
async def test_only_the_unknown_names_go_to_the_model_and_come_back_into_the_base():
    llm = _NamingLLM(
        [{"name": "Хліб Київський", "intent": "хліб", "subtype": "житній", "drink": None}]
    )
    pool = _Pool(
        [
            {
                "name_sha": store.fingerprint("Напій Geo"),
                "intent": "вода",
                "subtype": "газована",
                "drink": None,
            }
        ]
    )

    names = await intent_names(llm, ["Напій Geo", "Хліб Київський"], pool=pool)  # type: ignore[arg-type]

    assert llm.asked_about == [["Хліб Київський"]], "про відоме модель не питають"
    assert names["хліб київський"] == Naming("хліб", "житній", drink_known=True)
    written = [rows for kind, rows in pool.written if kind == "many"]
    assert written and written[0][0]["name_sha"] == store.fingerprint("Хліб Київський")


@pytest.mark.asyncio
async def test_second_pantry_in_the_same_process_asks_neither_base_nor_model():
    llm = _NamingLLM([{"name": "Хліб", "intent": "хліб", "subtype": None, "drink": None}])
    pool = _Pool()

    await intent_names(llm, ["Хліб"], pool=pool)  # type: ignore[arg-type]
    pool.written.clear()
    await intent_names(llm, ["Хліб"], pool=pool)  # type: ignore[arg-type]

    assert llm.calls == 1
    assert pool.written == [], "пам'ять процесу лишається першим ярусом"


@pytest.mark.asyncio
async def test_dead_base_costs_time_not_the_pantry():
    llm = _NamingLLM([{"name": "Хліб", "intent": "хліб", "subtype": None, "drink": None}])

    names = await intent_names(llm, ["Хліб"], pool=_DeadPool())  # type: ignore[arg-type]

    assert names["хліб"] == Naming("хліб", None, drink_known=True)
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_unwritable_base_does_not_break_the_answer():

    class _WriteFails(_Pool):
        @asynccontextmanager
        async def connection(self, **_: Any):
            if self.written:
                raise ConnectionError("база відповіла і зникла")
            yield _Conn([], self.written)

    llm = _NamingLLM([{"name": "Хліб", "intent": "хліб", "subtype": None, "drink": None}])
    names = await intent_names(llm, ["Хліб"], pool=_WriteFails())  # type: ignore[arg-type]

    assert names["хліб"] == Naming("хліб", None, drink_known=True)


@pytest.mark.asyncio
async def test_without_the_base_nothing_changes():
    llm = _NamingLLM([{"name": "Хліб", "intent": "хліб", "subtype": None, "drink": None}])
    names = await intent_names(llm, ["Хліб"])
    assert names["хліб"] == Naming("хліб", None, drink_known=True)
    assert llm.calls == 1


@pytest.mark.asyncio
async def test_a_cold_pantry_costs_exactly_one_call(monkeypatch):
    many = [f"Товар {number}" for number in range(45)]
    llm = _NamingLLM(
        [{"name": name, "intent": "щось", "subtype": None, "drink": None} for name in many]
    )

    await intent_names(llm, many, pool=None)  # type: ignore[arg-type]

    assert llm.calls == 1
    assert llm.asked_about == [many], "усі назви їдуть одним запитом"


@pytest.mark.asyncio
async def test_a_mangled_echo_does_not_become_a_key_of_its_own():
    llm = _NamingLLM(
        [{"name": "Сир «Гауда»", "intent": "сир", "subtype": "твердий", "drink": None}]
    )
    pool = _Pool()

    names = await intent_names(llm, ["Сир \"Гауда\""], pool=pool)  # type: ignore[arg-type]

    assert names == {}, "спотворена луна не називає нічого — і не називає ЧУЖОГО"
    written = [rows for kind, rows in pool.written if kind == "many"]
    assert not written, "чужий ключ у вічному кеші дорожчий за зайвий виклик"


@pytest.mark.asyncio
async def test_an_echo_that_only_lost_the_spacing_still_names_the_original():
    llm = _NamingLLM(
        [{"name": "хліб   київський", "intent": "хліб", "subtype": "житній", "drink": None}]
    )
    pool = _Pool()

    names = await intent_names(llm, ["Хліб Київський"], pool=pool)  # type: ignore[arg-type]

    assert names["хліб київський"] == Naming("хліб", "житній", drink_known=True)
    written = [rows for kind, rows in pool.written if kind == "many"]
    assert written[0][0]["name_sha"] == store.fingerprint("Хліб Київський")


@pytest.mark.asyncio
async def test_a_lost_echo_says_so_instead_of_disappearing():
    llm = _NamingLLM(
        [
            {"name": "Сир «Гауда»", "intent": "сир", "subtype": None, "drink": None},
            {"name": "Хліб", "intent": "хліб", "subtype": None, "drink": None},
        ]
    )

    with capture_logs() as written:
        names = await intent_names(llm, ["Сир \"Гауда\"", "Хліб"])

    assert names["хліб"] == Naming("хліб", None, drink_known=True)
    said = [one for one in written if one["event"] == "naming.echo_mismatch"]
    assert said and said[0]["lost"] == 1 and said[0]["asked"] == 2
    assert "гауда" not in str(said).lower()


@pytest.mark.asyncio
async def test_a_name_cached_before_the_drink_column_is_asked_again():
    llm = _NamingLLM(
        [{"name": "Пиво Hike", "intent": "пиво", "subtype": "світле", "drink": "light"}]
    )
    pool = _Pool(
        [
            {
                "name_sha": store.fingerprint("Пиво Hike"),
                "intent": "пиво",
                "subtype": "світле",
                "drink": None,
            }
        ]
    )

    named = await intent_names(llm, ["Пиво Hike"], pool=pool, need_drink=True)  # type: ignore[arg-type]

    assert llm.calls == 1, "про групу напою мусять спитати"
    assert named["пиво hike"].drink == "light"


@pytest.mark.asyncio
async def test_the_pantry_never_pays_for_the_bars_question():
    llm = _NamingLLM([])
    pool = _Pool(
        [
            {
                "name_sha": store.fingerprint("Пиво Hike"),
                "intent": "пиво",
                "subtype": "світле",
                "drink": None,
            }
        ]
    )

    named = await intent_names(llm, ["Пиво Hike"], pool=pool)  # type: ignore[arg-type]

    assert llm.calls == 0
    assert named["пиво hike"].label == "пиво · світле"


@pytest.mark.asyncio
async def test_not_a_drink_is_written_down_as_a_word_not_as_a_hole():
    llm = _NamingLLM(
        [{"name": "Лаваш", "intent": "лаваш", "subtype": None, "drink": None}]
    )
    pool = _Pool()

    await intent_names(llm, ["Лаваш"], pool=pool, need_drink=True)  # type: ignore[arg-type]

    written = [rows for kind, rows in pool.written if kind == "many"]
    assert written and written[0][0]["drink"] == "none"


@pytest.mark.asyncio
async def test_a_word_the_bar_does_not_know_means_not_a_drink():
    llm = _NamingLLM(
        [{"name": "Лаваш", "intent": "лаваш", "subtype": None, "drink": "пиво"}]
    )

    named = await intent_names(llm, ["Лаваш"], need_drink=True)

    assert named["лаваш"].drink is None
    assert named["лаваш"].drink_known is True


@pytest.mark.asyncio
async def test_a_cold_run_asks_again_even_when_the_name_is_cached():
    llm = _NamingLLM([{"name": "Молоко Яготинське", "intent": "молоко"}])
    rows = [
        {
            "name_sha": store.fingerprint("Молоко Яготинське"),
            "intent": "молоко",
            "subtype": None,
            "drink": None,
        }
    ]

    warm = await intent_names(llm, ["Молоко Яготинське"], pool=_Pool(rows))
    assert llm.calls == 0, "тепла назва не має коштувати виклик"

    cold = await intent_names(llm, ["Молоко Яготинське"], pool=_Pool(rows), use_cache=False)
    assert llm.calls == 1
    assert llm.asked_about[-1] == ["Молоко Яготинське"]
    assert set(cold) == set(warm)


@pytest.mark.asyncio
async def test_a_cold_run_never_writes_to_the_eternal_cache():
    llm = _NamingLLM([{"name": "Хліб Київський", "intent": "хліб"}])
    pool = _Pool()

    await intent_names(llm, ["Хліб Київський"], pool=pool, use_cache=False)

    assert llm.calls == 1, "модель мусить бути спитана -- інакше тест ні про що"
    assert [kind for kind, _ in pool.written] == [], f"писало в базу: {pool.written}"


@pytest.mark.asyncio
async def test_a_cold_run_answers_from_what_it_asked_not_from_memory():
    llm = _NamingLLM([{"name": "Кава Jacobs", "intent": "кава"}])
    await intent_names(llm, ["Кава Jacobs"], pool=_Pool())
    assert llm.calls == 1

    cold = await intent_names(None, ["Кава Jacobs"], pool=_Pool(), use_cache=False)
    assert cold == {}, "холодний показ віддав мітку, якої цей виклик не питав"

    warm = await intent_names(None, ["Кава Jacobs"], pool=_Pool())
    assert warm != {}


@pytest.mark.asyncio
async def test_a_continued_cold_round_reads_what_this_process_already_asked():
    llm = _NamingLLM([{"name": "Сир Гауда", "intent": "сир"}])
    first = await intent_names(llm, ["Сир Гауда"], pool=_Pool(), use_cache=False)
    assert llm.calls == 1 and first != {}
    pool = _Pool()
    again = await intent_names(llm, ["Сир Гауда"], pool=pool, use_cache=False, memory=True)
    assert llm.calls == 1, "продовження перепитало те, що процес уже назвав"
    assert again == first
    assert pool.written == [], f"писало в базу: {pool.written}"
    cold = await intent_names(None, ["Сир Гауда"], pool=_Pool(), use_cache=False)
    assert cold == {}
