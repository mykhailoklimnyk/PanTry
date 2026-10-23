from __future__ import annotations

import asyncio
from typing import Any

import pytest

from komora.agent.basket import HistoryItem, Naming
from komora.agent.steps.pantry import Home
from komora.api.schemas import Pantry
from komora.core.said import Said


def _empty() -> Pantry:
    return Pantry(items=[], receipts=0, orders=0, kinds=0, tracked_from=3, hidden=[], unlisted=0)


class _Ground:
    mcp = None
    llm = "модель є"
    cfg = None
    moment = None
    pool = None
    account = "відбиток-акаунта"
    packs = 1

    def __init__(self) -> None:
        self.trace = _Trace()


class _Trace:
    def __init__(self) -> None:
        self.steps: list[tuple[str, dict[str, Any]]] = []

    def add(self, step: str, _tool: str, args: dict[str, Any], *_a: Any, **_kw: Any) -> None:
        self.steps.append((step, args))


HISTORY = [
    HistoryItem(lager_id=str(n), name=name, unit="шт", receipts=5)
    for n, name in enumerate(
        [
            "Молоко Яготинське 2,5%",
            "Хліб Київський нарізний",
            "Сир Комо твердий",
            "Кава Jacobs Monarch",
            "Вода Моршинська негазована",
        ],
        start=1,
    )
]


@pytest.fixture
def asked(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    rounds: list[list[str]] = []

    async def _names(llm: Any, names: list[str], **_kw: Any) -> dict[str, Naming]:
        if llm is not None:
            rounds.append(list(names))
        return {name: Naming(intent=name, subtype=None) for name in names}

    monkeypatch.setattr("komora.agent.steps.pantry.intent_names", _names)
    return rounds


def _home(*, cold: bool) -> Home:
    return Home(
        _Ground(),  # type: ignore[arg-type]
        said=Said(),
        read=object(),  # type: ignore[arg-type]
        drawn=_empty(),
        cold=cold,
    )


def test_a_cold_run_does_not_ask_the_same_names_twice(asked: list[list[str]]) -> None:
    home = _home(cold=True)
    asyncio.run(home.name({"history": HISTORY}))
    asyncio.run(home.name({"history": HISTORY}))

    assert len(asked) == 2, "крок мусить лишитись кроком, а не зникнути"
    assert asked[0], "перший оберт питає все"
    assert asked[1] == [], "другий не питає нічого: ці назви ми самі щойно назвали"


def test_the_second_step_keeps_what_the_first_named(asked: list[list[str]]) -> None:
    home = _home(cold=True)
    asyncio.run(home.name({"history": HISTORY}))
    first = dict(home.names)
    asyncio.run(home.name({"history": HISTORY}))

    assert home.names == first
    assert len(home.names) == len(HISTORY)


def test_the_repeat_names_itself_in_the_trace(asked: list[list[str]]) -> None:
    home = _home(cold=True)
    asyncio.run(home.name({"history": HISTORY}))
    made = asyncio.run(home.name({"history": HISTORY}))

    assert made.args["цим прогоном уже названо"] == len(HISTORY)
    assert made.args["кандидатів"] == len(HISTORY), "число кандидатів описує ВЕСЬ перелік"


def test_the_first_step_says_nothing_about_a_repeat(asked: list[list[str]]) -> None:
    made = asyncio.run(_home(cold=True).name({"history": HISTORY}))

    assert "цим прогоном уже названо" not in made.args


def test_a_warm_run_is_unchanged(asked: list[list[str]]) -> None:
    home = _home(cold=False)
    asyncio.run(home.name({"history": HISTORY}))

    assert len(home.names) == len(HISTORY)
    assert asked[0]
