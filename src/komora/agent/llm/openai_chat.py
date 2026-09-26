from __future__ import annotations

import json
import time
from typing import Any

import httpx

from komora.agent.llm import Decision, ModelError, Truncated, Usage


class OpenAIChatLLM:
    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key: str,
        timeout_s: float = 120.0,
    ) -> None:
        self.model = model
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout_s = timeout_s

    async def decide(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        schema_name: str = "decision",
        max_tokens: int = 2048,
        temperature: float | None = None,
    ) -> Decision:
        schema_note = (
            "\n\nВідповідь — ОДИН JSON-об'єкт за цією JSON-схемою, "
            "без жодного тексту довкола:\n" + json.dumps(schema, ensure_ascii=False)
        )
        token_param = "max_completion_tokens" if self.model.startswith("gpt-5") else "max_tokens"
        payload: dict[str, Any] = {
            "model": self.model,
            token_param: max_tokens,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system + schema_note},
                {"role": "user", "content": user},
            ],
        }
        if self.model.startswith("gpt-5"):
            payload["reasoning_effort"] = "none"

        if temperature is not None:
            payload["temperature"] = temperature

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        if "openai.com" not in self._base_url:
            headers["OpenAI-Project"] = "default"

        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            response = await client.post(
                f"{self._base_url}/v1/chat/completions",
                headers=headers,
                json=payload,
            )
        duration_ms = int((time.perf_counter() - started) * 1000)

        if response.status_code >= 400:
            raise ModelError(
                f"{self.model}: {response.status_code} {response.text[:300]}",
                status=response.status_code,
            )

        body = response.json()
        choice = body["choices"][0]
        text = choice["message"].get("content") or ""
        finish = choice.get("finish_reason")

        usage_raw = body.get("usage") or {}
        details = usage_raw.get("prompt_tokens_details") or {}
        usage = Usage(
            input_tokens=usage_raw.get("prompt_tokens", 0),
            output_tokens=usage_raw.get("completion_tokens", 0),
            cached_tokens=details.get("cached_tokens") or 0,
        )

        if finish == "length":
            raise Truncated(
                f"{self.model}: відповідь урвано на ліміті — max_tokens={max_tokens}, "
                f"згенеровано {usage.output_tokens}. Хвіст: {text[-60:]!r}",
                usage,
            )

        data = coerce_strings(_parse(text, self.model), schema)

        return Decision(
            data=data,
            text=text,
            model=body.get("model", self.model),
            usage=usage,
            duration_ms=duration_ms,
        )


def _parse(text: str, model: str) -> dict[str, Any]:
    trimmed = text.strip()
    if trimmed.startswith("```"):
        trimmed = trimmed.split("\n", 1)[1] if "\n" in trimmed else ""
        trimmed = trimmed.rstrip().removesuffix("```").rstrip()
    try:
        parsed = json.loads(trimmed)
    except json.JSONDecodeError as exc:
        raise ModelError(f"{model}: відповідь не JSON — {text[:200]}") from exc
    if not isinstance(parsed, dict):
        raise ModelError(f"{model}: очікували об'єкт, отримали {type(parsed).__name__}")
    return parsed


def coerce_strings(value: Any, subschema: dict[str, Any]) -> Any:
    stype = subschema.get("type")
    if stype == "string" and isinstance(value, int | float) and not isinstance(value, bool):
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value)
    if stype == "object" and isinstance(value, dict):
        props = subschema.get("properties", {})
        return {
            key: coerce_strings(item, props[key]) if key in props else item
            for key, item in value.items()
        }
    if stype == "array" and isinstance(value, list):
        items_schema = subschema.get("items", {})
        return [coerce_strings(item, items_schema) for item in value]
    return value
