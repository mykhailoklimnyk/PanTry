from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from komora.agent.prompts import register as register_prompt
from komora.agent.prompts import stamp as prompt_stamp
from komora.core.twins import Group, Verdict, together

TWINS_LIMIT = 10

TWINS_SCHEMA = {
    "type": "object",
    "properties": {
        "pairs": {
            "type": "array",
            "salvage": True,
            "items": {
                "type": "object",
                "properties": {
                    "key": {"type": "string"},
                    "same": {"type": "boolean"},
                    "keep": {"type": "string"},
                    "drop": {"type": "array", "items": {"type": "string"}},
                    "why": {"type": "string"},
                },
                "required": ["key", "same"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["pairs"],
    "additionalProperties": False,
}

TWINS_SYSTEM = (
    "Ти агент продуктового кошика «Комора». У кошику є групи рядків ОДНОГО "
    "виду, і треба сказати, чи це одна потреба вдома. «same» = true, коли "
    "рядки групи закривають ту саму потребу і одного з них вистачить; тоді "
    "«keep» -- артикул того рядка, який лишити (бери той, що гість справді "
    "бере: поле «своє_з_чеків»). «same» = false, коли рядки групи потрібні "
    "ОБИДВА: різні люди в домі, різне призначення, різний смак чи міцність "
    "(дитяча вода і мінеральна -- дві потреби, бо дитячу п'є інша людина). "
    "Рядки групи -- уже ОДИН вид за нашим розбором, тож «різні потреби» "
    "треба обґрунтувати такою причиною; інша марка, сорт чи фасовка того "
    "самого виду причиною не є. Відповідай на КОЖНУ групу з «групи» і не "
    "вигадуй ключів поза ними. «why» -- одне коротке речення гостю, чому "
    "саме так. Відповідай ВИКЛЮЧНО українською."
)

register_prompt("twins", TWINS_SYSTEM)


@dataclass(frozen=True, slots=True)
class TwinsPlan:

    verdicts: dict[str, Verdict]
    model: str = ""
    duration_ms: int = 0
    tokens: int = 0
    prompt: str = ""
    stray: tuple[str, ...] = ()


def payload(pairs: Sequence[Group]) -> str:
    return json.dumps(
        {
            "групи": [
                {
                    "ключ": group.key,
                    **(
                        {"як_беруть": list(pairs)}
                        if group.by_section and (pairs := together(group))
                        else {}
                    ),
                    "рядки": [
                        {
                            "артикул": row.article,
                            "товар": row.name,
                            "намір": row.intent,
                            **({"ціна": row.unit_price} if row.unit_price else {}),
                            **(
                                {
                                    "своє_з_чеків": {
                                        "чеків": row.receipts,
                                        "свіжих": row.recent_receipts,
                                    }
                                }
                                if row.own_article or row.receipts
                                else {"у_чеках_гостя": False}
                            ),
                            **({"як_потрапив": row.came_from} if row.came_from else {}),
                            **({"акція": row.promo} if row.promo else {}),
                            **({"назвав_гість": True} if row.guest_word else {}),
                        }
                        for row in group.rows
                    ],
                }
                for group in pairs
            ]
        },
        ensure_ascii=False,
    )


def verdicts_of(
    data: dict[str, Any], pairs: Sequence[Group]
) -> tuple[dict[str, Verdict], dict[str, Verdict]]:
    known = {group.key for group in pairs}
    verdicts: dict[str, Verdict] = {}
    stray: dict[str, Verdict] = {}
    for item in data.get("pairs") or []:
        key = str(item.get("key") or "").strip()
        if not key:
            continue
        verdict = Verdict(
            key=key,
            same=bool(item.get("same")),
            keep=str(item.get("keep") or "").strip(),
            why=str(item.get("why") or "").strip(),
            drop=tuple(str(one).strip() for one in item.get("drop") or () if str(one).strip()),
        )
        (verdicts if key in known else stray)[key] = verdict
    return verdicts, stray


async def ask_twins(llm: Any, pairs: Sequence[Group]) -> TwinsPlan:
    if not pairs:
        return TwinsPlan(verdicts={})
    asked = list(pairs)[:TWINS_LIMIT]
    prompt = prompt_stamp("twins", TWINS_SYSTEM)
    decision = await llm.decide(
        system=TWINS_SYSTEM,
        user=payload(asked),
        schema=TWINS_SCHEMA,
        prompt=prompt,
        max_tokens=768,
    )
    verdicts, stray = verdicts_of(decision.data, asked)
    return TwinsPlan(
        verdicts=verdicts,
        model=decision.model,
        prompt=prompt,
        duration_ms=decision.duration_ms,
        tokens=decision.usage.input_tokens + decision.usage.output_tokens,
        stray=tuple(stray),
    )


__all__ = [
    "TWINS_LIMIT",
    "TWINS_SCHEMA",
    "TWINS_SYSTEM",
    "TwinsPlan",
    "ask_twins",
    "payload",
    "verdicts_of",
]
