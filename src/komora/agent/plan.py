from __future__ import annotations

import json
import time
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from komora.agent.prompts import register as register_prompt
from komora.agent.prompts import stamp as prompt_stamp
from komora.agent.skills import PANTRY_HEADER
from komora.agent.skills import block as skills_block
from komora.agent.spine import Batch, Ground
from komora.core.instructions import Digest, Verdict, digest
from komora.core.plan import (
    BATCH_SCHEMA,
    CORE_AFTER_PLAN,
    DECIDES,
    PHASES,
    PLAN_SCHEMA,
    STEPS,
    Aim,
    Plan,
    code_plan,
    describe,
    repair_note,
    validate,
)
from komora.core.skills import pantry_skills
from komora.logging import get_logger
from komora.mcp import verdicts as verdict_register
from komora.mcp.client import SilpoMCP

log = get_logger(__name__)

PLAN_TOKENS = 2048

PLAN_SYSTEM = (
    "Ти планувальник агента продуктового кошика «Комора». Твоя робота -- "
    "скласти ПЛАН прогону: упорядкований список кроків зі СЛОВНИКА нижче, "
    "який доведе кошик гостя від «куди веземо» до записаного і перевіреного "
    "кошика. Кожен крок словника кличе один інструмент «Сільпо» (або це "
    "обчислення коду чи рішення моделі), споживає факти з попередніх кроків "
    "і дає нові. Правила: крок можна брати лише зі словника; крок без входів "
    "не виконається; полицю не питають до слота; запис у кошик -- лише після "
    "рішення і лише коли задача просить записати, і після кожного запису "
    "кошик перечитується. Не додавай кроків, яких задача не потребує: кожен "
    "крок коштує секунди й гроші. Читай описи інструментів -- у них "
    "інструкції, наприклад шукати за числовим артикулом там, де він відомий "
    "з чека (крок shelf.by_article). На переплані крок може нести `labels` -- "
    "наміри зі стану, до яких його застосувати; без них decide.pick і "
    "decide.loop беруть наміри, які ще не дійшли до рядка. "
    "Відповідай ВИКЛЮЧНО українською."
)

register_prompt("plan", PLAN_SYSTEM)

PANTRY_SYSTEM = (
    "Ти планувальник агента «Комора». Твоя робота -- скласти ПЛАН прогону, "
    "який доведе СТАН ДОМУ гостя: комора вже намальована з його чеків, і "
    "твоє питання одне -- чого їй бракує, щоб кожен рядок сказав або число "
    "(коли це закінчиться), або речення (чому числа немає). Кроки бери лише "
    "зі словника нижче; крок без входів не виконається; називання йде перед "
    "вироком і стелею зберігання, бо обидва питаються по мітці виду -- але "
    "якщо мітки вже мають усі рядки, називати нема кого. Не додавай кроків, "
    "яких цей дім не потребує: у теплого акаунта названо все і питати нема "
    "чого, і порожній план -- законна відповідь. Крок може нести `labels` -- "
    "мітки виду зі стану, до яких його застосувати; порожній перелік означає "
    "всі. `pantry.shelf` -- єдиний крок, який дізнається щось ПОЗА чеками: "
    "він питає полицю про фасовку свого артикула, і ставити його варто "
    "адресно, на мовчазні рядки, про які збираєшся спитати гостя. "
    "Відповідай ВИКЛЮЧНО українською."
)

register_prompt("plan-pantry", PANTRY_SYSTEM)

_SYSTEMS: dict[Aim, tuple[str, str]] = {
    Aim.BASKET: ("plan", PLAN_SYSTEM),
    Aim.PANTRY: ("plan-pantry", PANTRY_SYSTEM),
}


@dataclass(frozen=True, slots=True)
class Planned:

    plan: Plan
    attempts: int
    tokens: int
    duration_ms: int
    note: str
    """Одне речення для трейсу: звідки план і що з ним робили."""
    tools_note: str = ""
    """Що зробили з чужими описами: скільки інструментів поїхало і скільки
    абзаців знято (#354). Порожньо -- описів не було взагалі.

    Стоїть у трейсі окремим числом, бо знятий абзац і відсутній опис на
    екрані нерозрізненні, а різницю між ними бачить лише реєстр."""
    prompt: str = ""
    """Чим питали: ім'я@хеш промпта планування (#295).

    Порожньо -- виклику не було (моделі немає). Живі описи інструментів і
    словник кроків у стамп не входять: перші пише чужий сервер (їх стереже
    `docs/mcp-tools.json`), другий генерується з даних, а не з рядка."""


def dictionary_text(aim: Aim = Aim.BASKET) -> str:
    allowed = PHASES.get(aim)
    rows = []
    for kind in STEPS:
        if allowed is not None and kind.phase not in allowed:
            continue
        rows.append(
            f"- {kind.name} [{kind.phase}] -> {kind.tool}"
            + (f"; потребує: {', '.join(sorted(kind.needs))}" if kind.needs else "")
            + (f"; дає: {', '.join(sorted(kind.gives))}" if kind.gives else "")
            + ("; ПИШЕ в кошик" if kind.writes else "")
            + ("; можна повторювати" if kind.repeatable else "")
        )
    return "\n".join(rows)


DICT_HEAD = "\n\nСЛОВНИК КРОКІВ:\n"

_DICT_NAMES: dict[Aim, str] = {Aim.BASKET: "plan.dict", Aim.PANTRY: "plan-pantry.dict"}


def dictionary_block(aim: Aim = Aim.BASKET) -> str:
    return register_prompt(_DICT_NAMES[aim], DICT_HEAD + dictionary_text(aim)).text


for _aim in _DICT_NAMES:
    dictionary_block(_aim)


def tools_digest(
    tools: Sequence[Mapping[str, Any]],
    *,
    verdicts: Sequence[Verdict] | None = None,
) -> Digest:
    rows = verdict_register.load() if verdicts is None else verdicts
    return digest(tools, rows, wanted={kind.tool for kind in STEPS})


def tools_text(tools: Sequence[Mapping[str, Any]]) -> str:
    return tools_digest(tools).text()


def describe_tools_note(described: Digest) -> str:
    if not described.rows:
        return "описів не було"
    said = f"{len(described.rows)} інстр., знято не наших {described.dropped}"
    if described.unjudged:
        said += f", БЕЗ ВИРОКУ {described.unjudged}"
    return said


async def describe_tools(mcp: SilpoMCP) -> list[dict[str, Any]]:
    try:
        return await mcp.describe_tools()
    except Exception as exc:
        log.warning("plan.tools_unavailable", error=str(exc)[:160])
        return []


def system_text(
    *,
    aim: Aim = Aim.BASKET,
    tools: Sequence[dict[str, Any]] = (),
    state: Mapping[str, Any] | None = None,
) -> tuple[str, str]:
    stamp, head = _SYSTEMS[aim]
    said = tools_text(tools)
    tail = (
        skills_block(pantry_skills(state or {}).skills, header=PANTRY_HEADER)
        if aim is Aim.PANTRY
        else ""
    )
    core = CORE_AFTER_PLAN.get(aim, ())
    mine = (
        "\n\nЦЕ КОД РОБИТЬ САМ, хоч би що стояло в плані -- не плануй їх:\n" + ", ".join(core)
        if core
        else ""
    )
    return stamp, (
        head
        + dictionary_block(aim)
        + mine
        + ("\n\nОПИСИ ІНСТРУМЕНТІВ:\n" + said if said else "")
        + tail
    )


async def plan_run(
    llm: Any,
    *,
    source: str,
    writes: bool,
    budget: bool,
    known: Sequence[str] = (),
    tools: Sequence[dict[str, Any]] = (),
    goal: str = "",
    aim: Aim = Aim.BASKET,
    state: Mapping[str, Any] | None = None,
) -> Planned:
    fallback = code_plan(source=source, writes=writes, budget=budget)
    if llm is None:
        return Planned(
            fallback, attempts=0, tokens=0, duration_ms=0, note="без моделі: план з коду"
        )

    task = {
        "задача": goal or ("чужий кошик до дверей" if source == "cart" else "кошик з намірів"),
        "джерело": "кошик гостя" if source == "cart" else "наміри (список, чеки, комора)",
        "записати в кошик": writes,
        "є межа суми": budget,
        "уже відомо": list(known),
    }
    if state:
        task["стан"] = dict(state)
    stamp, system = system_text(aim=aim, tools=tools, state=state)
    prompt = prompt_stamp(stamp, system)
    tools_note = describe_tools_note(tools_digest(tools))
    user = json.dumps(task, ensure_ascii=False)
    started = time.perf_counter()
    tokens = 0
    attempts = 0
    plan: Plan | None = None
    last_raw: Any = None
    note = ""
    for attempt in range(2):
        attempts += 1
        try:
            decision = await llm.decide(
                system=system if attempt == 0 else system + "\n\n" + note,
                user=user,
                schema=PLAN_SCHEMA,
                prompt=prompt,
                max_tokens=PLAN_TOKENS,
                temperature=0.0,
            )
        except Exception as exc:
            log.warning("plan.model_failed", error=str(exc)[:160], attempt=attempt)
            return Planned(
                fallback,
                attempts=attempts,
                tokens=tokens,
                duration_ms=int((time.perf_counter() - started) * 1000),
                note=f"модель не відповіла ({str(exc)[:60]}) — план з коду",
                tools_note=tools_note,
                prompt=prompt,
            )
        tokens += decision.usage.input_tokens + decision.usage.output_tokens
        last_raw = decision.data
        plan = validate(decision.data, writes_allowed=writes, known=known, aim=aim)
        if plan.ok and not plan.dropped:
            break
        note = repair_note(plan)
        if plan.ok:
            break
    duration_ms = int((time.perf_counter() - started) * 1000)
    assert plan is not None
    if plan.ok:
        how = "план від моделі" + (" після одного ремонту" if attempts > 1 else "")
        if plan.dropped:
            how += f", знято {len(plan.dropped)}"
        return Planned(
            plan,
            attempts=attempts,
            tokens=tokens,
            duration_ms=duration_ms,
            note=how,
            tools_note=tools_note,
            prompt=prompt,
        )
    mended = _mend_essential(plan, last_raw, writes=writes, known=known, aim=aim)
    if mended is not None:
        return Planned(
            mended,
            attempts=attempts,
            tokens=tokens,
            duration_ms=duration_ms,
            note=f"план від моделі, крок {DECIDES[aim]} дописано кодом",
            tools_note=tools_note,
            prompt=prompt,
        )
    log.info("plan.fallback", reason=plan.fatal, dropped=len(plan.dropped), attempts=attempts)
    return Planned(
        fallback,
        attempts=attempts,
        tokens=tokens,
        duration_ms=duration_ms,
        note=f"план моделі не годиться після {attempts} спроб ({plan.fatal}) — план з коду",
        tools_note=tools_note,
        prompt=prompt,
    )


__all__ = [
    "PANTRY_SYSTEM",
    "PLAN_SYSTEM",
    "PLAN_TOKENS",
    "Planned",
    "describe",
    "describe_tools",
    "describe_tools_note",
    "dictionary_text",
    "plan_run",
    "system_text",
    "tools_digest",
    "tools_text",
]


BATCH_TOKENS = 1024

BREAK = chr(10) * 2

BATCH_HEAD = (
    "Ти віддаєш не весь план, а ПАЧКУ з 1-4 кроків -- те, що варто зробити "
    "ПРЯМО ЗАРАЗ. Після виконання ти побачиш, що з неї вийшло, і віддаси "
    "наступну; кроків, які залежать від ще не здобутих фактів, у пачку не "
    "став. Коли робити більше нема чого -- постав `stop: true` і скажи "
    "причину в `why`."
)


async def plan_batch(
    llm: Any,
    ground: Ground,
    *,
    source: str,
    writes: bool,
    budget: bool,
    tools: Sequence[dict[str, Any]] = (),
    goal: str = "",
    aim: Aim = Aim.BASKET,
    state: Mapping[str, Any] | None = None,
    labels: Iterable[str] | None = None,
) -> Batch:
    if llm is None:
        return Batch(plan=Plan(steps=(), source="code"), stop=True, why="моделі немає")

    known = tuple(ground.facts)
    task: dict[str, Any] = {
        "задача": goal or ("чужий кошик до дверей" if source == "cart" else "кошик з намірів"),
        "джерело": "кошик гостя" if source == "cart" else "наміри (список, чеки, комора)",
        "записати в кошик": writes,
        "є межа суми": budget,
        "ґрунт": ground.told(),
    }
    if state:
        task["стан"] = dict(state)
    stamp, system = system_text(aim=aim, tools=tools, state=state)
    prompt = prompt_stamp(f"{stamp}+batch", BATCH_HEAD + BREAK + system)
    started = time.perf_counter()
    try:
        decision = await llm.decide(
            system=BATCH_HEAD + BREAK + system,
            user=json.dumps(task, ensure_ascii=False),
            schema=BATCH_SCHEMA,
            prompt=prompt,
            max_tokens=BATCH_TOKENS,
            temperature=0.0,
        )
    except Exception as exc:
        log.warning("batch.model_failed", error=str(exc)[:160], turn=ground.turn)
        return Batch(
            plan=Plan(steps=(), fatal=f"модель не відповіла ({str(exc)[:60]})", source="model"),
            stop=False,
            why="",
        )

    plan = validate(
        decision.data, writes_allowed=writes, known=known, aim=aim, whole=False, labels=labels
    )
    tokens = decision.usage.input_tokens + decision.usage.output_tokens
    data = decision.data if isinstance(decision.data, Mapping) else {}
    log.info(
        "batch.planned",
        turn=ground.turn,
        steps=len(plan.steps),
        dropped=len(plan.dropped),
        stop=bool(data.get("stop")),
        tokens=tokens,
        ms=int((time.perf_counter() - started) * 1000),
    )
    return Batch(
        plan=plan,
        stop=bool(data.get("stop")),
        why=str(data.get("why") or ""),
        tokens=tokens,
    )


def _mend_essential(
    plan: Plan, raw: Any, *, writes: bool, known: Sequence[str], aim: Aim
) -> Plan | None:
    essential = DECIDES.get(aim)
    if plan.ok or essential is None or not (plan.fatal or "").startswith("у плані немає рішення"):
        return None
    steps = raw.get("steps") if isinstance(raw, dict) else raw
    if not isinstance(steps, list):
        return None
    extra = {"name": essential, "why": "дописано кодом: без цього кроку плану немає"}
    for at in range(len(steps), -1, -1):
        mended = validate(
            [*steps[:at], extra, *steps[at:]], writes_allowed=writes, known=known, aim=aim
        )
        if mended.ok:
            return mended
    return None
