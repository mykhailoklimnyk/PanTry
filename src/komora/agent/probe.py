from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from komora.agent.prompts import register as register_prompt
from komora.agent.prompts import stamp as prompt_stamp
from komora.logging import get_logger

log = get_logger(__name__)

MAX_QUESTIONS = 3

MAX_COVERS = 12

TOKENS_PER_LABEL = 24

PROBE_SYSTEM = (
    "Тобі дають ЗАКРИТИЙ перелік видів товарів з домашньої комори гостя. Про "
    "ці види відомо, ЩО він їх купує, і невідомо, ЯК ШВИДКО вони в нього "
    "закінчуються: чеки показують покупки, а не споживання. "
    f"Обери НЕ БІЛЬШЕ {MAX_QUESTIONS} видів, про які варто спитати гостя, щоб "
    "дізнатись найбільше про решту. Питай про той вид, відповідь на який "
    "пояснює СУСІДНІ: хліб пояснює булку і батон, пральний порошок -- гель для "
    "прання, але хліб не пояснює порошок. "
    "На кожне питання назви `covers` -- мітки з переліку, які ця сама "
    f"відповідь пояснює (до {MAX_COVERS}). Мітки бери з переліку ДОСЛІВНО і "
    "своїх не вигадуй. "
    "`ask` -- саме питання гостю, одне коротке речення українською, і вісь у "
    "ньому РІВНО ОДНА: на скільки ЧАСУ гостю вистачає його звичної покупки "
    "цього виду. Питати «як часто ти це купуєш» не можна: на це вже відповіли "
    "чеки, а відповідь ляже в те саме число і зіпсує його. "
    "Питати нема про що -- віддай порожній перелік: це законна відповідь."
)

PROBE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "ask": {"type": "string"},
                    "covers": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["label", "ask", "covers"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["questions"],
    "additionalProperties": False,
}

register_prompt("probe", PROBE_SYSTEM)


@dataclass(frozen=True, slots=True)
class Probe:

    label: str
    ask: str
    covers: tuple[str, ...]
    kind: str = ""
    cover_kinds: tuple[str, ...] = ()
    usual: str = ""


def _intent(label: str) -> str:
    return label.split(" · ", 1)[0].strip()


def _clean(
    rows: Sequence[Mapping[str, Any]], known: Sequence[str]
) -> tuple[list[Probe], list[str]]:
    allowed = set(known)
    taken: set[str] = set()
    probes: list[Probe] = []
    thrown: list[str] = []
    for row in rows:
        label = str(row.get("label") or "").strip()
        ask = str(row.get("ask") or "").strip()
        if label not in allowed:
            thrown.append(f"«{label[:40] or 'порожньо'}»: мітки немає в переліку")
            continue
        if not ask:
            thrown.append(f"«{label}»: питання без тексту")
            continue
        if label in taken:
            thrown.append(f"«{label}»: про це вже питає сусіднє питання")
            continue
        covers: list[str] = []
        for name in row.get("covers") or ():
            other = str(name).strip()
            if other == label or other in taken or other in covers:
                continue
            if other not in allowed:
                thrown.append(f"«{label}» пояснює «{other[:30]}»: мітки немає в переліку")
                continue
            if _intent(other) != _intent(label):
                thrown.append(f"«{label}» пояснює «{other[:30]}»: інший вид, а не підвид")
                continue
            covers.append(other)
        covers = covers[:MAX_COVERS]
        taken.add(label)
        taken.update(covers)
        probes.append(Probe(label=label, ask=ask, covers=tuple(covers)))
        if len(probes) >= MAX_QUESTIONS:
            break
    return probes, thrown


async def intent_probe(llm: Any, labels: Sequence[str]) -> tuple[list[Probe], list[str], int]:
    known = [label for label in dict.fromkeys(labels) if label.strip()]
    if llm is None or not known:
        return [], [], 0
    decision = await llm.decide(
        system=PROBE_SYSTEM,
        user=json.dumps({"види": known}, ensure_ascii=False),
        schema=PROBE_SCHEMA,
        schema_name="probe",
        prompt=prompt_stamp("probe", PROBE_SYSTEM),
        max_tokens=max(1024, TOKENS_PER_LABEL * len(known)),
        temperature=0.0,
    )
    rows = decision.data.get("questions") or []
    probes, thrown = _clean(rows if isinstance(rows, list) else [], known)
    log.info(
        "probe.asked",
        offered=len(rows) if isinstance(rows, list) else 0,
        kept=len(probes),
        thrown=len(thrown),
        covers=sum(len(probe.covers) for probe in probes),
    )
    return probes, thrown, decision.usage.input_tokens + decision.usage.output_tokens


SPREAD_SYSTEM = (
    "Гість сказав, як швидко в його домі закінчуються кілька видів товару. "
    "Постав число днів СУСІДНІМ видам -- тим, які тобі назвали поруч із кожною "
    "відповіддю. "
    "Це не переписування відповіді: сусід може закінчуватись швидше або "
    "повільніше за той вид, про який спитали. Батон при хлібі раз на 3 дні "
    "може йти раз на 5; крупа при макаронах раз на 7 -- раз на 20. "
    "Мітки бери ДОСЛІВНО з тих, які дали під кожною відповіддю, і своїх не "
    "вигадуй. Про що сказати нема чого -- пропусти: неповна відповідь краща за "
    "вигадане число."
)

SPREAD_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "kinds": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "days": {"type": "integer"},
                },
                "required": ["label", "days"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["kinds"],
    "additionalProperties": False,
}

register_prompt("spread", SPREAD_SYSTEM)

SPREAD_MIN = 1
SPREAD_MAX = 180


async def intent_spread(
    llm: Any, answered: Mapping[str, tuple[int, Sequence[str]]]
) -> tuple[dict[str, tuple[int, str]], list[str], int]:
    allowed = {cover: kind for kind, (_days, covers) in answered.items() for cover in covers}
    if llm is None or not allowed:
        return {}, [], 0
    task = {
        "відповіді": [
            {"вид": kind, "днів": days, "сусіди": list(covers)}
            for kind, (days, covers) in answered.items()
        ]
    }
    decision = await llm.decide(
        system=SPREAD_SYSTEM,
        user=json.dumps(task, ensure_ascii=False),
        schema=SPREAD_SCHEMA,
        schema_name="spread",
        prompt=prompt_stamp("spread", SPREAD_SYSTEM),
        max_tokens=max(1024, TOKENS_PER_LABEL * len(allowed)),
        temperature=0.0,
    )
    spread: dict[str, tuple[int, str]] = {}
    thrown: list[str] = []
    for row in decision.data.get("kinds") or []:
        label = str(row.get("label") or "").strip()
        if label not in allowed:
            thrown.append(f"«{label[:40] or 'порожньо'}»: цього виду не було серед сусідів")
            continue
        if label in answered:
            thrown.append(f"«{label}»: про це гість сказав сам")
            continue
        try:
            days = int(row.get("days") or 0)
        except TypeError, ValueError:
            days = 0
        if not SPREAD_MIN <= days <= SPREAD_MAX:
            thrown.append(f"«{label}»: {days} дн поза межами {SPREAD_MIN}-{SPREAD_MAX}")
            continue
        spread[label] = (days, allowed[label])
    log.info("probe.spread", asked=len(answered), covers=len(allowed), set=len(spread))
    return spread, thrown, decision.usage.input_tokens + decision.usage.output_tokens


__all__ = [
    "MAX_COVERS",
    "MAX_QUESTIONS",
    "PROBE_SCHEMA",
    "PROBE_SYSTEM",
    "SPREAD_MAX",
    "SPREAD_MIN",
    "SPREAD_SCHEMA",
    "SPREAD_SYSTEM",
    "Probe",
    "intent_probe",
    "intent_spread",
]
