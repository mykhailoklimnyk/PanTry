from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class Usage:

    input_tokens: int
    output_tokens: int
    cached_tokens: int = 0
    """Скільки з `input_tokens` шлюз віддав зі свого кешу префікса (#291).

    ПІДМНОЖИНА входу, а не доданок: заміряно 03.09 на mantle -- при влучанні
    `prompt_tokens` не міняється жодного разу, тобто кешоване вже пораховане
    в ньому. Складати їх означало б рахувати одні й ті самі токени двічі
    (у Converse навпаки: там `inputTokens` кешованих НЕ містить).

    Ціни в цього числа немає навмисно. Скільки Bedrock бере за читання з
    кешу для Mistral, не сказано ніде, а зі своєї платформи Mistral бере
    10% -- і зашитий сюди чужий відсоток зробив би те, чого #34 забороняє
    прямо: збрехав би в ДЕШЕВШИЙ бік. Тому кешоване коштує повну ціну, і
    помилка лічильника лишається на безпечному боці -- ми рахуємо дорожче,
    ніж заплатили, а не навпаки.
    """


@dataclass(frozen=True, slots=True)
class Decision:

    data: dict[str, Any]
    text: str
    model: str
    usage: Usage
    duration_ms: int


@dataclass(slots=True)
class Meter:

    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    model: str = ""
    payer: str = ""
    down: str = ""

    @classmethod
    def of(cls, llm: object | None) -> Meter:
        meter = getattr(llm, "meter", None)
        return meter if isinstance(meter, cls) else cls()

    def add(self, decision: Decision) -> None:
        self.calls += 1
        self.input_tokens += decision.usage.input_tokens
        self.output_tokens += decision.usage.output_tokens
        self.cached_tokens += decision.usage.cached_tokens
        self.model = decision.model or self.model

    def refused(self, exc: ModelError, model: str) -> None:
        if exc.status in PAYER_STATUSES:
            self.down = f"{model}: {exc.status}"

    def burned(self, usage: Usage, model: str) -> None:
        self.calls += 1
        self.input_tokens += usage.input_tokens
        self.output_tokens += usage.output_tokens
        self.cached_tokens += usage.cached_tokens
        self.model = model or self.model


PAYER_STATUSES = frozenset({401, 402, 403, 429})


class ModelError(RuntimeError):

    def __init__(self, message: str = "", *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class Truncated(ModelError):

    def __init__(self, message: str, usage: Usage) -> None:
        super().__init__(message)
        self.usage = usage


class LLM(Protocol):

    model: str

    async def decide(
        self,
        *,
        system: str,
        user: str,
        schema: dict[str, Any],
        schema_name: str = "decision",
        max_tokens: int = 2048,
        temperature: float | None = None,
    ) -> Decision: ...


from komora.agent.llm.registry import build_llm  # noqa: E402 — уникаємо циклу імпорту

__all__ = ["LLM", "Decision", "Meter", "ModelError", "Usage", "build_llm"]
