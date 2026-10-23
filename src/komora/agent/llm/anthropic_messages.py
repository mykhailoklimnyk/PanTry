from __future__ import annotations

import json
import time
from typing import Any

import httpx

from komora.agent.llm import Decision, ModelError, Truncated, Usage


class AnthropicMessagesLLM:
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

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

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
        payload = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": user}],
            "output_config": {"format": {"type": "json_schema", "schema": schema}},
        }
        if temperature is not None:
            payload["temperature"] = temperature

        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=self._timeout_s) as client:
            response = await client.post(
                f"{self._base_url}/v1/messages",
                headers=self._headers(),
                json=payload,
            )

            if response.status_code == 400 and "Invalid schema" in response.text:
                del payload["output_config"]
                payload["system"] = system + (
                    "\n\nВідповідь — ОДИН JSON-об'єкт за цією JSON-схемою, "
                    "без жодного тексту довкола:\n" + json.dumps(schema, ensure_ascii=False)
                )
                response = await client.post(
                    f"{self._base_url}/v1/messages",
                    headers=self._headers(),
                    json=payload,
                )
        duration_ms = int((time.perf_counter() - started) * 1000)

        if response.status_code >= 400:
            raise ModelError(
                f"{self.model}: {response.status_code} {response.text[:300]}",
                status=response.status_code,
            )

        body = response.json()

        if body.get("stop_reason") == "refusal":
            raise ModelError(f"{self.model}: модель відмовилась відповідати")

        blocks = body.get("content", [])
        text = next(
            (b.get("text", "") for b in blocks if b.get("type") == "text"),
            "",
        )

        usage_raw = body.get("usage") or {}
        cached = usage_raw.get("cache_read_input_tokens") or 0
        usage = Usage(
            input_tokens=usage_raw.get("input_tokens", 0) + cached,
            output_tokens=usage_raw.get("output_tokens", 0),
            cached_tokens=cached,
        )

        if body.get("stop_reason") == "max_tokens":
            raise Truncated(
                f"{self.model}: відповідь урвано на ліміті — max_tokens={max_tokens}, "
                f"згенеровано {usage.output_tokens}. Хвіст: {text[-60:]!r}",
                usage,
            )

        return Decision(
            data=_parse(text, self.model),
            text=text,
            model=body.get("model", self.model),
            usage=usage,
            duration_ms=duration_ms,
        )


def _parse(text: str, model: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else ""
        if cleaned.rstrip().endswith("```"):
            cleaned = cleaned.rstrip()[: -len("```")]
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ModelError(f"{model}: відповідь не JSON — {text[:200]}") from exc
    if not isinstance(parsed, dict):
        raise ModelError(f"{model}: очікували об'єкт, отримали {type(parsed).__name__}")
    return parsed
