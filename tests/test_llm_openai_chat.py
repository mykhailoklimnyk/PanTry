from typing import Any

import httpx
import pytest

from komora.agent.llm import ModelError
from komora.agent.llm.openai_chat import OpenAIChatLLM, _parse, coerce_strings
from komora.agent.llm.validation import validate

SCHEMA = {
    "type": "object",
    "properties": {
        "chosen_id": {"type": "string"},
        "reason": {"type": "string"},
    },
    "required": ["chosen_id", "reason"],
    "additionalProperties": False,
}


def test_parse_plain_json():
    assert _parse('{"chosen_id": "1", "reason": "ok"}', "m") == {
        "chosen_id": "1",
        "reason": "ok",
    }


def test_parse_strips_markdown_fence():
    fenced = '```json\n{"chosen_id": "1", "reason": "ok"}\n```'
    assert _parse(fenced, "m")["chosen_id"] == "1"


def test_parse_rejects_non_object():
    with pytest.raises(ModelError, match="очікували об'єкт"):
        _parse('["не", "словник"]', "m")


def test_parse_rejects_garbage():
    with pytest.raises(ModelError, match="не JSON"):
        _parse("тут взагалі не JSON", "m")


def test_coerce_turns_number_into_string_where_schema_wants_string():
    data = coerce_strings({"chosen_id": 445120, "reason": "яйця"}, SCHEMA)
    assert data["chosen_id"] == "445120"


def test_coerce_does_not_leave_a_float_tail_on_integral_numbers():
    data = coerce_strings({"chosen_id": 445120.0, "reason": "яйця"}, SCHEMA)
    assert data["chosen_id"] == "445120"


def test_coerce_leaves_booleans_alone():
    schema = {"type": "object", "properties": {"flag": {"type": "string"}}}
    assert coerce_strings({"flag": True}, schema)["flag"] is True


def test_coerce_walks_nested_objects_and_arrays():
    schema = {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"id": {"type": "string"}},
                },
            }
        },
    }
    data = coerce_strings({"items": [{"id": 7}, {"id": "8"}]}, schema)
    assert [item["id"] for item in data["items"]] == ["7", "8"]


def test_validate_passes_a_conforming_answer():
    validate({"chosen_id": "1", "reason": "ok"}, SCHEMA, model="m")


def test_validate_rejects_missing_required_field():
    with pytest.raises(ModelError, match="не за схемою"):
        validate({"chosen_id": "1"}, SCHEMA, model="m")


def test_validate_rejects_wrong_type_after_coercion_had_its_chance():
    with pytest.raises(ModelError, match="не за схемою"):
        validate({"chosen_id": ["1"], "reason": "ok"}, SCHEMA, model="m")


def _stand(monkeypatch: pytest.MonkeyPatch, usage: dict[str, Any]) -> None:

    class _Response:
        status_code = 200
        text = ""

        def json(self) -> dict[str, Any]:
            return {
                "choices": [
                    {
                        "message": {"content": '{"chosen_id": "445120", "reason": "ok"}'},
                        "finish_reason": "stop",
                    }
                ],
                "usage": usage,
            }

    class _Client:
        def __init__(self, *_a: Any, **_kw: Any) -> None: ...

        async def __aenter__(self) -> _Client:
            return self

        async def __aexit__(self, *_exc: object) -> bool:
            return False

        async def post(self, *_a: Any, **_kw: Any) -> _Response:
            return _Response()

    monkeypatch.setattr(httpx, "AsyncClient", _Client)


async def _ask(monkeypatch: pytest.MonkeyPatch, usage: dict[str, Any]) -> Any:
    _stand(monkeypatch, usage)
    llm = OpenAIChatLLM(model="mistral-x", base_url="https://x", api_key="k")
    return await llm.decide(system="s", user="u", schema=SCHEMA, max_tokens=64)


@pytest.mark.anyio
async def test_cached_tokens_are_read_from_the_details_block(monkeypatch):
    decided = await _ask(
        monkeypatch,
        {
            "prompt_tokens": 4766,
            "completion_tokens": 96,
            "prompt_tokens_details": {"cached_tokens": 4704},
        },
    )

    assert decided.usage.cached_tokens == 4704
    assert decided.usage.input_tokens == 4766


@pytest.mark.anyio
async def test_a_miss_is_zero_and_not_a_missing_field(monkeypatch):
    decided = await _ask(monkeypatch, {"prompt_tokens": 4766, "completion_tokens": 96})

    assert decided.usage.cached_tokens == 0


@pytest.mark.anyio
async def test_an_empty_details_block_does_not_crash_the_call(monkeypatch):
    decided = await _ask(
        monkeypatch,
        {"prompt_tokens": 4766, "completion_tokens": 96, "prompt_tokens_details": None},
    )

    assert decided.usage.cached_tokens == 0
