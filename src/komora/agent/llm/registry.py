from __future__ import annotations

from typing import TYPE_CHECKING

from komora.agent.llm.anthropic_messages import AnthropicMessagesLLM
from komora.agent.llm.openai_chat import OpenAIChatLLM
from komora.agent.llm.validation import Validated

if TYPE_CHECKING:
    from komora.agent.llm import Meter

ANTHROPIC_PREFIX = "anthropic."

CLAUDE_PREFIX = "claude-"

ANTHROPIC_PATH_SUFFIX = "/anthropic"


def is_anthropic(model: str) -> bool:
    return model.startswith((ANTHROPIC_PREFIX, CLAUDE_PREFIX))


def openai_base_url(anthropic_base_url: str) -> str:
    trimmed = anthropic_base_url.rstrip("/")
    if trimmed.endswith(ANTHROPIC_PATH_SUFFIX):
        return trimmed[: -len(ANTHROPIC_PATH_SUFFIX)]
    return trimmed


def build_llm(
    *,
    model: str,
    base_url: str,
    api_key: str,
    timeout_s: float = 120.0,
    meter: Meter | None = None,
) -> Validated:
    inner: AnthropicMessagesLLM | OpenAIChatLLM
    if is_anthropic(model):
        inner = AnthropicMessagesLLM(
            model=model, base_url=base_url, api_key=api_key, timeout_s=timeout_s
        )
    else:
        inner = OpenAIChatLLM(
            model=model,
            base_url=openai_base_url(base_url),
            api_key=api_key,
            timeout_s=timeout_s,
        )
    return Validated(inner, meter=meter)
