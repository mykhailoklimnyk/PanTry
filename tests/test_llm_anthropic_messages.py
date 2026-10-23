from __future__ import annotations

from typing import Any

import httpx
import pytest

from komora.agent.llm import ModelError, Truncated
from komora.agent.llm.anthropic_messages import AnthropicMessagesLLM

pytestmark = pytest.mark.anyio

SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"chosen_id": {"type": "string"}},
    "required": ["chosen_id"],
    "additionalProperties": False,
}


def _stand(monkeypatch: pytest.MonkeyPatch, body: dict[str, Any]) -> None:

    class _Response:
        status_code = 200
        text = ""

        def json(self) -> dict[str, Any]:
            return body

    class _Client:
        def __init__(self, *_a: Any, **_kw: Any) -> None: ...

        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *_exc: object) -> bool:
            return False

        async def post(self, *_a: Any, **_kw: Any) -> _Response:
            return _Response()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)


async def _ask(llm: AnthropicMessagesLLM) -> Any:
    return await llm.decide(system="s", user="u", schema=SCHEMA, max_tokens=64)


async def test_a_truncated_answer_is_its_own_diagnosis(monkeypatch):
    _stand(
        monkeypatch,
        {
            "stop_reason": "max_tokens",
            "content": [{"type": "text", "text": '{"chosen_id": "4451'}],
            "usage": {"input_tokens": 500, "output_tokens": 64},
        },
    )
    llm = AnthropicMessagesLLM(model="claude-x", base_url="https://x", api_key="k")

    with pytest.raises(Truncated) as failure:
        await _ask(llm)

    assert failure.value.usage.output_tokens == 64
    assert "урвано на ліміті" in str(failure.value)


async def test_a_refusal_stays_a_refusal(monkeypatch):
    _stand(monkeypatch, {"stop_reason": "refusal", "content": []})
    llm = AnthropicMessagesLLM(model="claude-x", base_url="https://x", api_key="k")

    with pytest.raises(ModelError, match="відмовилась"):
        await _ask(llm)


async def test_a_whole_answer_goes_through(monkeypatch):
    _stand(
        monkeypatch,
        {
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": '{"chosen_id": "445120"}'}],
            "usage": {"input_tokens": 500, "output_tokens": 12},
        },
    )
    llm = AnthropicMessagesLLM(model="claude-x", base_url="https://x", api_key="k")

    decided = await _ask(llm)

    assert decided.data == {"chosen_id": "445120"}


async def test_cache_read_is_added_back_into_the_input(monkeypatch):
    _stand(
        monkeypatch,
        {
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": '{"chosen_id": "445120"}'}],
            "usage": {
                "input_tokens": 62,
                "output_tokens": 12,
                "cache_read_input_tokens": 4704,
            },
        },
    )
    llm = AnthropicMessagesLLM(model="claude-x", base_url="https://x", api_key="k")

    decided = await _ask(llm)

    assert decided.usage.cached_tokens == 4704
    assert decided.usage.input_tokens == 4766


async def test_without_a_cache_field_the_input_is_not_inflated(monkeypatch):
    _stand(
        monkeypatch,
        {
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": '{"chosen_id": "445120"}'}],
            "usage": {"input_tokens": 4766, "output_tokens": 12},
        },
    )
    llm = AnthropicMessagesLLM(model="claude-x", base_url="https://x", api_key="k")

    decided = await _ask(llm)

    assert decided.usage.cached_tokens == 0
    assert decided.usage.input_tokens == 4766
