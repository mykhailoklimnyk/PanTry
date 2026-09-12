from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

import httpx

from komora.agent.llm.registry import openai_base_url
from komora.core import models

PINNED = (
    "mistral.mistral-large-3-675b-instruct",
    "mistral.devstral-2-123b",
)

UNAVAILABLE = frozenset(
    {
        "anthropic.claude-fable-5",
        "anthropic.claude-haiku-4-5",
        "anthropic.claude-opus-4-7",
        "anthropic.claude-opus-4-8",
        "anthropic.claude-opus-5",
        "anthropic.claude-sonnet-5",
        "google.gemma-4-26b-a4b",
        "google.gemma-4-31b",
        "google.gemma-4-e2b",
        "openai.gpt-5.4",
        "openai.gpt-5.4-2026-03-05",
        "openai.gpt-5.5",
        "openai.gpt-5.5-2026-04-23",
        "openai.gpt-5.6-luna",
        "openai.gpt-5.6-sol",
        "openai.gpt-5.6-terra",
        "writer.palmyra-vision-7b",
        "xai.grok-4.3",
    }
)

UNAVAILABLE_NOTE = "не підтримується цим маршрутом (виміряно 14.08)"

LABELS = {
    "mistral.mistral-large-3-675b-instruct": "Mistral Large 3",
    "mistral.devstral-2-123b": "Devstral 2",
    "anthropic.claude-opus-5": "Claude Opus 5",
    "anthropic.claude-sonnet-5": "Claude Sonnet 5",
    "anthropic.claude-haiku-4-5": "Claude Haiku 4.5",
    "anthropic.claude-opus-4-8": "Claude Opus 4.8",
    "anthropic.claude-opus-4-7": "Claude Opus 4.7",
    "anthropic.claude-fable-5": "Claude Fable 5",
}

NOTES = {
    "mistral.mistral-large-3-675b-instruct": "основна — 12/12 на сценаріях 14.08",
    "mistral.devstral-2-123b": "не тримає pass^5: 15 з 22 (03.09)",
    "anthropic.claude-opus-5": "доступ на акаунті ще не виданий",
    "anthropic.claude-sonnet-5": "доступ на акаунті ще не виданий",
    "anthropic.claude-haiku-4-5": "доступ на акаунті ще не виданий",
    "anthropic.claude-opus-4-8": "доступ на акаунті ще не виданий",
    "anthropic.claude-opus-4-7": "доступ на акаунті ще не виданий",
    "anthropic.claude-fable-5": "доступ на акаунті ще не виданий",
    "openai.gpt-oss-120b": "замість рішення переписує схему — не JSON (×2, 14.08)",
    "openai.gpt-oss-20b": "замість рішення переписує схему — не JSON (×2, 14.08)",
    "qwen.qwen3-coder-next": "плаває: то тримає схему, то губить поля (14.08)",
    "moonshotai.kimi-k2-thinking": "reasoning з'їдає весь ліміт — відповідь урвана (×2, 14.08)",
    "mistral.ministral-3-3b-instruct": "плаває на схемі: губить обов'язкові поля (14.08)",
    "nvidia.nemotron-nano-9b-v2": "плаває на схемі: луна зі схеми замість рішення (14.08)",
    "mistral.voxtral-mini-3b-2507": "аудіомодель — у заміні молока обрала воду (14.08)",
    "mistral.voxtral-small-24b-2507": "аудіомодель — обрала корм для котів (14.08)",
    "zai.glm-4.7": "плутає значення полів з їхніми назвами (13.08)",
    "zai.glm-5": "ієрогліфи посеред українського речення (13.08)",
    "google.gemma-4-26b-a4b": "живе на /v1/responses, але той не відповідає (14.08)",
    "google.gemma-4-31b": "живе на /v1/responses, але той не відповідає (14.08)",
    "google.gemma-4-e2b": "живе на /v1/responses, але той не відповідає (14.08)",
    "xai.grok-4.3": "живе на /v1/responses, але той не відповідає (14.08)",
    "openai.gpt-5.4": "не підтримує ні chat-, ні responses-шлях (14.08)",
    "openai.gpt-5.4-2026-03-05": "не підтримує ні chat-, ні responses-шлях (14.08)",
    "openai.gpt-5.5": "не підтримує ні chat-, ні responses-шлях (14.08)",
    "openai.gpt-5.5-2026-04-23": "не підтримує ні chat-, ні responses-шлях (14.08)",
    "openai.gpt-5.6-luna": "не підтримує ні chat-, ні responses-шлях (14.08)",
    "openai.gpt-5.6-sol": "не підтримує ні chat-, ні responses-шлях (14.08)",
    "openai.gpt-5.6-terra": "не підтримує ні chat-, ні responses-шлях (14.08)",
    "writer.palmyra-vision-7b": "vision-модель — текстовий виклик відбиває 400 (14.08)",
}

SNAPSHOT = (
    "anthropic.claude-fable-5",
    "anthropic.claude-haiku-4-5",
    "anthropic.claude-opus-4-7",
    "anthropic.claude-opus-4-8",
    "anthropic.claude-opus-5",
    "anthropic.claude-sonnet-5",
    "deepseek.v3.1",
    "deepseek.v3.2",
    "google.gemma-3-12b-it",
    "google.gemma-3-27b-it",
    "google.gemma-3-4b-it",
    "google.gemma-4-26b-a4b",
    "google.gemma-4-31b",
    "google.gemma-4-e2b",
    "minimax.minimax-m2",
    "minimax.minimax-m2.1",
    "minimax.minimax-m2.5",
    "mistral.devstral-2-123b",
    "mistral.magistral-small-2509",
    "mistral.ministral-3-14b-instruct",
    "mistral.ministral-3-3b-instruct",
    "mistral.ministral-3-8b-instruct",
    "mistral.mistral-large-3-675b-instruct",
    "mistral.voxtral-mini-3b-2507",
    "mistral.voxtral-small-24b-2507",
    "moonshotai.kimi-k2-thinking",
    "moonshotai.kimi-k2.5",
    "nvidia.nemotron-nano-12b-v2",
    "nvidia.nemotron-nano-3-30b",
    "nvidia.nemotron-nano-9b-v2",
    "nvidia.nemotron-super-3-120b",
    "openai.gpt-5.4",
    "openai.gpt-5.4-2026-03-05",
    "openai.gpt-5.5",
    "openai.gpt-5.5-2026-04-23",
    "openai.gpt-5.6-luna",
    "openai.gpt-5.6-sol",
    "openai.gpt-5.6-terra",
    "openai.gpt-oss-120b",
    "openai.gpt-oss-20b",
    "openai.gpt-oss-safeguard-120b",
    "openai.gpt-oss-safeguard-20b",
    "qwen.qwen3-235b-a22b-2507",
    "qwen.qwen3-32b",
    "qwen.qwen3-coder-30b-a3b-instruct",
    "qwen.qwen3-coder-480b-a35b-instruct",
    "qwen.qwen3-coder-next",
    "qwen.qwen3-next-80b-a3b-instruct",
    "qwen.qwen3-vl-235b-a22b-instruct",
    "writer.palmyra-vision-7b",
    "xai.grok-4.3",
    "zai.glm-4.6",
    "zai.glm-4.7",
    "zai.glm-4.7-flash",
    "zai.glm-5",
)


@dataclass(frozen=True, slots=True)
class CatalogModel:
    id: str
    label: str
    note: str | None
    available: bool


def label_for(model_id: str) -> str:
    return LABELS.get(model_id, model_id.split(".", 1)[-1])


def _available(model_id: str) -> bool:
    return model_id not in UNAVAILABLE


def arrange(ids: Iterable[str]) -> list[CatalogModel]:
    unique = list(dict.fromkeys(ids))
    top = [row.id for row in models.RECOMMENDED]
    rest = sorted(m for m in unique if m not in top)
    ordered = top + [m for m in rest if _available(m)] + [m for m in rest if not _available(m)]
    return [
        CatalogModel(
            id=m,
            label=_label_of(m),
            note=_note_of(m),
            available=True if m in top else _available(m),
        )
        for m in ordered
    ]


def _label_of(model: str) -> str:
    for row in models.RECOMMENDED:
        if row.id == model:
            return row.label
    return label_for(model)


def _note_of(model: str) -> str | None:
    for row in models.RECOMMENDED:
        if row.id == model:
            return row.note
    return NOTES.get(model, None if _available(model) else UNAVAILABLE_NOTE)


async def fetch_ids(*, base_url: str, api_key: str, timeout_s: float = 15.0) -> list[str]:
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        response = await client.get(
            f"{openai_base_url(base_url)}/v1/models",
            headers={"Authorization": f"Bearer {api_key}"},
        )
    response.raise_for_status()
    data = response.json().get("data", [])
    return [item["id"] for item in data if item.get("id")]
