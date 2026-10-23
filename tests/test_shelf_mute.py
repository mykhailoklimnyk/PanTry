from __future__ import annotations

from typing import Any

import pytest

from komora.agent.basket import search_products
from komora.core.silence import Silence, is_mute
from komora.mcp.client import SEARCH_TOOL, counted_silence

SLOT = {
    "deliveryType": "DeliveryHome",
    "start": "2026-09-06T09:00:00+00:00",
    "end": "2026-09-06T11:00:00+00:00",
}


class _Outcome:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload_raw = payload
        self.duration_ms = 7


class _Shelf:

    def __init__(self, *, answers: dict[str, list[dict[str, Any]]], mute_passes: int) -> None:
        self._answers = answers
        self._left = mute_passes
        self.silence = Silence()
        self.passes = 0

    async def call(self, tool: str, arguments: dict[str, Any] | None = None) -> _Outcome:
        assert tool == SEARCH_TOOL
        self.passes += 1
        wanted = (arguments or {}).get("products") or []
        mute = self._left > 0
        self._left -= 1
        raw = {
            "queries": [
                {"query": query, "products": [] if mute else self._answers.get(query, [])}
                for query in wanted
            ]
        }
        self.silence = counted_silence(self.silence, tool, raw)
        return _Outcome(raw)


def _card(name: str) -> dict[str, Any]:
    return {"name": name, "available": True, "externalProductId": 1}


def _shelf_of(*names: str) -> dict[str, list[dict[str, Any]]]:
    return {name: [_card(name)] for name in names}


WHOLE = tuple(f"вид {index}" for index in range(12))


@pytest.mark.anyio
async def test_a_mute_shelf_is_asked_a_second_time():
    shelf = _Shelf(answers=_shelf_of(*WHOLE), mute_passes=1)

    found, _ = await search_products(shelf, list(WHOLE), SLOT, "філія")

    assert shelf.passes == 2, "мовчазна полиця мусить бути перепитана"
    assert [name for name in WHOLE if found.get(name)] == list(WHOLE)


@pytest.mark.anyio
async def test_a_healed_run_stops_calling_itself_mute():
    shelf = _Shelf(answers=_shelf_of(*WHOLE), mute_passes=1)

    await search_products(shelf, list(WHOLE), SLOT, "філія")

    assert not is_mute(shelf.silence)


@pytest.mark.anyio
async def test_a_shelf_that_stays_mute_keeps_saying_so():
    shelf = _Shelf(answers=_shelf_of(*WHOLE), mute_passes=2)

    found, _ = await search_products(shelf, list(WHOLE), SLOT, "філія")

    assert shelf.passes == 2, "повтор рівно один: другий коштував би вдвічі за нуль"
    assert not any(found.values())
    assert is_mute(shelf.silence)


@pytest.mark.anyio
async def test_a_guest_with_rare_kinds_is_not_asked_twice():
    shelf = _Shelf(answers=_shelf_of(*WHOLE[:8]), mute_passes=0)

    found, _ = await search_products(shelf, list(WHOLE), SLOT, "філія")

    assert shelf.passes == 1
    assert len([name for name in WHOLE if found.get(name)]) == 8


@pytest.mark.anyio
async def test_a_short_search_is_never_judged():
    shelf = _Shelf(answers={}, mute_passes=1)

    await search_products(shelf, ["рідкісний вид", "ще рідкісніший"], SLOT, "філія")

    assert shelf.passes == 1


@pytest.mark.anyio
async def test_the_time_of_the_retry_is_counted_in():
    shelf = _Shelf(answers=_shelf_of(*WHOLE), mute_passes=1)

    _, spent_ms = await search_products(shelf, list(WHOLE), SLOT, "філія")

    assert spent_ms == 14, "два походи по 7 мс"
