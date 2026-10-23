from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from komora.agent.basket import assemble_list
from komora.api.schemas import BuildRequest
from test_agent_basket import _AskingLLM, mcp  # noqa: F401

MOMENT = datetime(2026, 8, 14, 14, 30, 5, 991538, tzinfo=UTC)

GOLDEN = Path(__file__).parent / "fixtures" / "basket_golden.json"

VOLATILE = frozenset(
    {
        "durationMs",
        "duration_ms",
        "мс виклику",
        "calls",
        "tokens",
        "tokensIn",
        "tokensOut",
        "tokens_in",
        "tokens_out",
        "costUsd",
        "cost_usd",
        "prompt",
        "runLog",
        "run_log",
    }
)

_TIMING = re.compile(r"\d+(?:[.,]\d+)?\s*(мс|с)\b")


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _scrub(item) for key, item in value.items() if key not in VOLATILE}
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    if isinstance(value, str):
        return _TIMING.sub(r"# \1", value)
    return value


CASES: dict[str, dict[str, Any]] = {
    "з межею": {"mode": "week", "shoppingList": ["кава"], "budget": 3000},
    "список і історія": {"mode": "week", "shoppingList": ["молоко", "шафран", "кава"]},
}


AGENT_PICK = [{"intent": "молоко", "chosen_id": "101", "qty": 1, "reason": "звичний"}]


async def _shot(stand: Any, payload: dict[str, Any], *, llm: Any = None) -> dict[str, Any]:
    assembled = await assemble_list(
        stand,
        llm=llm,
        request=BuildRequest.model_validate(payload),
        now=MOMENT,
    )
    return _scrub(
        {
            "unresolved": assembled.unresolved,
            "basket": assembled.basket.model_dump(mode="json", by_alias=True),
        }
    )


def _judge(case: str, shot: dict[str, Any]) -> None:
    if os.environ.get("KOMORA_GOLDEN"):
        known = json.loads(GOLDEN.read_text(encoding="utf-8")) if GOLDEN.exists() else {}
        known[case] = shot
        GOLDEN.write_text(
            json.dumps(known, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        pytest.skip(f"знімок «{case}» перезаписано")

    assert GOLDEN.exists(), "знімка немає: перезняти KOMORA_GOLDEN=1"
    known = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert case in known, f"у знімку немає входу «{case}»: перезняти KOMORA_GOLDEN=1"
    assert shot == known[case]


@pytest.mark.parametrize("case", sorted(CASES))
async def test_basket_answer_matches_the_golden_shot(mcp, case: str) -> None:  # noqa: F811
    _judge(case, await _shot(mcp, CASES[case]))


async def test_the_agent_path_matches_the_golden_shot(mcp) -> None:  # noqa: F811
    _judge(
        "агент обрав один намір із трьох",
        await _shot(mcp, CASES["список і історія"], llm=_AskingLLM(list(AGENT_PICK))),
    )


async def test_the_shot_is_stable_between_runs(mcp) -> None:  # noqa: F811
    first = await _shot(mcp, CASES["список і історія"])
    second = await _shot(mcp, CASES["список і історія"])

    assert first == second
