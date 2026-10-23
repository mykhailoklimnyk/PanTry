from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, cast

import pytest

from komora.agent.loop import Loop
from komora.agent.steps.decide import Decide


@dataclass
class _Line:
    intent: str
    chain: list[str] = field(default_factory=list)
    risky: bool = False


def _deciding() -> Decide:
    return Decide(ground=cast(Any, None), shelf=cast(Any, None))


@pytest.mark.asyncio
async def test_what_the_loop_found_survives_the_next_rebuild_of_the_lines(
    monkeypatch: pytest.MonkeyPatch,
):
    import komora.agent.steps.decide as module

    deciding = _deciding()
    deciding.llm = object()
    deciding.picks["хліб"] = {"chosen_id": "111", "qty": 1, "why": "вибір першого проходу"}
    deciding.unresolved = ["рулет"]

    async def _resolve_one(_llm: Any, intent: str, **_kwargs: Any) -> Loop:
        return Loop(intent=intent, chosen={"externalProductId": "222"}, candidates=[])

    def _build(found: list[str], _seen: Any, _picks: Any) -> list[_Line]:
        return [_Line(intent=intent) for intent in found]

    monkeypatch.setattr(module, "resolve_one", _resolve_one)
    await deciding.loop(
        {"candidates": {}},
        listed=[],
        hints={},
        history={},
        tools=[],
        search=None,
        similar=None,
        build=_build,
        why="дошукано петлею",
    )

    assert deciding.picks.get("рулет", {}).get("chosen_id") == "222", (
        "знайдене петлею мусить лежати там, звідки рядки будує `decide.chain`"
    )
    assert deciding.picks["хліб"]["chosen_id"] == "111", "перший прохід не затирається"

    async def _rebuild() -> tuple[list[_Line], list[str], dict[str, str]]:
        return [_Line(intent=intent) for intent in deciding.picks], [], {}

    await deciding.chain({}, build=_rebuild)

    assert [line.intent for line in deciding.lines] == ["хліб", "рулет"]
