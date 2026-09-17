from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

from komora.agent.prompts import register as register_prompt
from komora.agent.prompts import stamp as prompt_stamp
from komora.core.nextlist import Pick, why
from komora.logging import get_logger

log = get_logger(__name__)

TOKENS_PER_ROW = 60

NEXT_SYSTEM = (
    "Ти ведеш список покупок однієї родини. Тобі дають види, які за їхніми ж "
    "чеками закінчились або закінчаться до наступного походу в магазин, разом "
    "з порахованою підставою. Твоя робота -- ВІДІБРАТИ те, що справді варто "
    "взяти цього разу, і сказати про кожен рядок одне коротке речення. "
    "Порядок: спершу те, що вже закінчилось. "
    "Не додавай нічого, чого немає у списку. Не вигадуй чисел: якщо в "
    "підставі є строк, бери його як є. Рядок з позначкою про акцію лишай з "
    "нею -- без знижки цей вид не беруть. Якщо два види з переліку -- це те "
    "саме призначення, лиши один. Відповідай ключами, які тобі дали."
)

NEXT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "list": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "why": {"type": "string"},
                },
                "required": ["key", "why"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["list"],
    "additionalProperties": False,
}

register_prompt("nextlist", NEXT_SYSTEM)


class Composed:

    __slots__ = ("note", "prompt", "rows", "tokens")

    def __init__(
        self,
        rows: list[tuple[str, str, str]],
        *,
        note: str,
        tokens: int = 0,
        prompt: str | None = None,
    ) -> None:
        self.rows = rows
        self.note = note
        self.tokens = tokens
        self.prompt = prompt


def _by_code(picks: Sequence[Pick]) -> list[tuple[str, str, str]]:
    return [(pick.kind, pick.label, why(pick)) for pick in picks]


async def compose(llm: Any, picks: Sequence[Pick]) -> Composed:
    if not picks:
        return Composed([], note="комора не назвала жодного виду на наступну покупку")
    if llm is None:
        return Composed(_by_code(picks), note="без агента: порядок і підстави з коду")
    asked = {
        "види": [{"key": pick.kind, "назва": pick.label, "підстава": why(pick)} for pick in picks]
    }
    try:
        decision = await llm.decide(
            system=NEXT_SYSTEM,
            user=json.dumps(asked, ensure_ascii=False),
            schema=NEXT_SCHEMA,
            schema_name="nextlist",
            prompt=prompt_stamp("nextlist", NEXT_SYSTEM),
            max_tokens=max(1024, TOKENS_PER_ROW * len(picks)),
        )
    except Exception as exc:
        log.warning("nextlist.model_failed", error=str(exc)[:160])
        return Composed(
            _by_code(picks),
            note=f"модель не відповіла ({str(exc)[:60]}) — список з коду",
        )
    known = {pick.kind: pick for pick in picks}
    rows: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for item in decision.data.get("list") or []:
        key = str(item.get("key") or "")
        pick = known.get(key)
        if pick is None or key in seen:
            continue
        seen.add(key)
        said = str(item.get("why") or "").strip() or why(pick)
        rows.append((pick.kind, pick.label, said))
    if not rows:
        return Composed(
            _by_code(picks),
            note="агент не назвав жодного рядка — список з коду",
            tokens=decision.usage.input_tokens + decision.usage.output_tokens,
            prompt=prompt_stamp("nextlist", NEXT_SYSTEM),
        )
    dropped = len(picks) - len(rows)
    return Composed(
        rows,
        note=f"агент склав список: {len(rows)} з {len(picks)}"
        + (f", зняв {dropped}" if dropped else ""),
        tokens=decision.usage.input_tokens + decision.usage.output_tokens,
        prompt=prompt_stamp("nextlist", NEXT_SYSTEM),
    )


__all__ = ["NEXT_SCHEMA", "NEXT_SYSTEM", "TOKENS_PER_ROW", "Composed", "compose"]
