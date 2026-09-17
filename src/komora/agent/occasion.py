from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

from komora.agent.prompts import register as register_prompt
from komora.agent.prompts import stamp as prompt_stamp
from komora.core.occasion import OCCASION_LIMIT, Occasion

HISTORY_LIMIT = 80

_CHANGE_ITEM = {
    "type": "object",
    "properties": {
        "intent": {"type": "string"},
        "why": {"type": "string"},
    },
    "required": ["intent", "why"],
    "additionalProperties": False,
}

OCCASION_SCHEMA = {
    "type": "object",
    "properties": {
        "add": {"type": "array", "items": _CHANGE_ITEM},
        "skip": {"type": "array", "items": _CHANGE_ITEM},
        "target": {"type": ["number", "null"]},
        "target_why": {"type": "string"},
    },
    "required": ["add", "skip"],
    "additionalProperties": False,
}

OCCASION_SYSTEM = (
    "Ти агент продуктового кошика «Комора». Гість назвав ПРИВІД — подію, "
    "під яку збирається кошик, — і твоя задача виправити під нього список "
    "намірів: що докинути і що не брати. Поле «що_це_означає» каже, що саме "
    "змінилось. "
    "«add» — види, яких у списку немає, а привід їх просить. Бери насамперед "
    "із поля «купує_сам»: це те, що гість справді бере, з числом покупок. "
    "Назвати щось поза цим списком можна, але лише коли привід без нього не "
    "виконується і схожого в його покупках немає (лід до вечірки). Не "
    "докидай того, що вже є в «наміри»: це буде другий такий самий рядок. "
    "Один намір — це ВИД («сир твердий», «чипси»), а не бренд і не артикул: "
    "конкретний товар під нього оберуть далі. "
    "«skip» — наміри З ПОЛЯ «наміри», які під цим приводом зайві або "
    "зіпсуються. Беруться ЛИШЕ звідти і лише коли привід прямо цього просить: "
    "зайвий рядок гість зніме сам, а зникле мовчки він шукатиме очима. "
    "Подія — не регулярна покупка: те, що гість бере за своїм розкладом "
    "незалежно від гостей (корм для тварин, гігієна, побутова хімія, засоби "
    "для прання, папір), під подію не йде — став це в «skip». "
    "Наміри, названі самим гостем, не чіпай узагалі — там його слова. "
    "Обидва списки можуть бути порожні, і це нормальна відповідь: привід не "
    "зобов'язаний міняти кошик, і докидати заради кількості не треба. "
    "«why» — одне коротке речення, чому саме цей вид під цей привід; його "
    "прочитає гість. "
    "«target» -- скільки гривень цей кошик коштуватиме під привід, коли названа "
    "межа з ним не збігається: гості на шістьох за межу на одного не зберуться. "
    "Відштовхуйся від «межа_грн» і «звичне_замовлення_грн»; коли межа приводу "
    "пасує або її не названо -- лиши «target» порожнім. «target_why» -- одне "
    "речення гостю, чому саме стільки. «бар_гостя» -- напої, які гість справді "
    "бере: під привід бери їх, а не чужі. Відповідай ВИКЛЮЧНО українською."
)

register_prompt("occasion", OCCASION_SYSTEM)


@dataclass(frozen=True, slots=True)
class Change:

    intent: str
    why: str


@dataclass(frozen=True, slots=True)
class OccasionPlan:

    added: tuple[Change, ...] = ()
    skipped: tuple[Change, ...] = ()
    beyond_limit: int = 0
    target: Decimal | None = None
    target_why: str = ""
    model: str = ""
    duration_ms: int = 0
    tokens: int = 0
    prompt: str = ""

    @property
    def touched(self) -> bool:
        return bool(self.added or self.skipped)

    def note(self) -> str:
        parts = []
        if self.added:
            shown = ", ".join(change.intent for change in self.added[:5])
            tail = "…" if len(self.added) > 5 else ""
            parts.append(f"докинув {len(self.added)} — {shown}{tail}")
        if self.skipped:
            shown = ", ".join(change.intent for change in self.skipped[:5])
            tail = "…" if len(self.skipped) > 5 else ""
            parts.append(f"зняв {len(self.skipped)} — {shown}{tail}")
        if not parts:
            return "склад кошика під цей привід не змінився"
        return "; ".join(parts)


def _norm(text: str) -> str:
    return " ".join(text.split()).casefold()


def plan_of(
    data: dict[str, Any],
    *,
    intents: Sequence[str],
    protected: Sequence[str],
) -> tuple[tuple[Change, ...], tuple[Change, ...], int]:
    known = {_norm(intent): intent for intent in intents}
    untouchable = {_norm(intent) for intent in protected}

    added: list[Change] = []
    seen = set(known)
    for item in data.get("add") or []:
        intent = str(item.get("intent") or "").strip()
        key = _norm(intent)
        if not intent or key in seen:
            continue
        seen.add(key)
        added.append(Change(intent=intent, why=str(item.get("why") or "").strip()))

    skipped: list[Change] = []
    dropped: set[str] = set()
    for item in data.get("skip") or []:
        key = _norm(str(item.get("intent") or ""))
        if key not in known or key in untouchable or key in dropped:
            continue
        dropped.add(key)
        skipped.append(Change(intent=known[key], why=str(item.get("why") or "").strip()))

    beyond = max(0, len(added) - OCCASION_LIMIT)
    return tuple(added[:OCCASION_LIMIT]), tuple(skipped), beyond


def target_of(data: dict[str, Any]) -> tuple[Decimal | None, str]:
    raw = data.get("target")
    if raw is None or raw == "":
        return None, ""
    try:
        target = Decimal(str(raw))
    except InvalidOperation:
        return None, ""
    if not target.is_finite() or target <= 0:
        return None, ""
    return target, str(data.get("target_why") or "").strip()


def payload(
    occasion: Occasion,
    *,
    intents: Sequence[str],
    habits: Sequence[tuple[str, int]],
    budget: Decimal | None = None,
    usual: Decimal | None = None,
    bar: Sequence[tuple[str, int]] = (),
) -> str:
    return json.dumps(
        {
            "привід": occasion.phrase(),
            "що_це_означає": occasion.task(),
            "наміри": list(intents),
            "купує_сам": [{"вид": name, "чеків": count} for name, count in habits[:HISTORY_LIMIT]]
            or None,
            "стеля_докидання": OCCASION_LIMIT,
            **({"межа_грн": f"{budget:.0f}"} if budget is not None else {}),
            **({"звичне_замовлення_грн": f"{usual:.0f}"} if usual is not None else {}),
            **(
                {"бар_гостя": [{"напій": name, "чеків": count} for name, count in bar]}
                if bar
                else {}
            ),
        },
        ensure_ascii=False,
    )


async def rework(
    llm: Any,
    occasion: Occasion,
    *,
    intents: Sequence[str],
    protected: Sequence[str],
    habits: Sequence[tuple[str, int]],
    budget: Decimal | None = None,
    usual: Decimal | None = None,
    bar: Sequence[tuple[str, int]] = (),
) -> OccasionPlan:
    if not occasion.named:
        return OccasionPlan()
    prompt = prompt_stamp("occasion", OCCASION_SYSTEM)
    decision = await llm.decide(
        system=OCCASION_SYSTEM,
        user=payload(occasion, intents=intents, habits=habits, budget=budget, usual=usual, bar=bar),
        schema=OCCASION_SCHEMA,
        prompt=prompt,
        max_tokens=1024,
    )
    added, skipped, beyond = plan_of(decision.data, intents=intents, protected=protected)
    target, target_why = target_of(decision.data)
    return OccasionPlan(
        added=added,
        skipped=skipped,
        beyond_limit=beyond,
        target=target,
        target_why=target_why,
        model=decision.model,
        prompt=prompt,
        duration_ms=decision.duration_ms,
        tokens=decision.usage.input_tokens + decision.usage.output_tokens,
    )


TABLE_LIMIT = OCCASION_LIMIT

TABLE_SYSTEM = (
    "Ти агент продуктового кошика «Комора». Гість збирає стіл під ПРИВІД на "
    "названу суму. Кошик уже зібрано з полиці за справжніми цінами, і до "
    "названої суми ще бракує грошей. Твоя задача -- назвати, чим ще накрити "
    "стіл. «add» -- види, яких у кошику немає і які пасують приводу. Один "
    "намір -- це ВИД («сир твердий», «оливки»), не бренд і не артикул: товар "
    "під нього оберуть далі. Не повторюй того, що є в «у_кошику»: це буде "
    "другий такий самий рядок. Бери насамперед із «купує_сам» -- це те, що "
    "гість справді бере, з числом покупок. Орієнтуйся на «бракує_грн»: назви "
    "стільки видів, щоб приблизно закрити цю суму: не менше за «потрібно_видів» "
    "(порахованих від звичної ціни рядка в цьому кошику) і не більше за «стеля»; "
    "коли бракує багато, бери дорожчі види: сир, м'ясо, риба, напої. "
    "Порожній «add» -- нормальна відповідь, коли столу вже досить. «why» -- "
    "одне коротке речення гостю, чому цей вид до столу. Відповідай ВИКЛЮЧНО "
    "українською."
)
register_prompt("table", TABLE_SYSTEM)

TABLE_SCHEMA = {
    "type": "object",
    "properties": {"add": {"type": "array", "items": _CHANGE_ITEM}},
    "required": ["add"],
    "additionalProperties": False,
}


@dataclass(frozen=True, slots=True)
class TablePlan:

    added: tuple[Change, ...] = ()
    model: str = ""
    duration_ms: int = 0
    tokens: int = 0
    prompt: str = ""


def table_payload(
    occasion: Occasion,
    *,
    have: Sequence[str],
    shortfall: Decimal,
    habits: Sequence[tuple[str, int]] = (),
    need_kinds: int | None = None,
) -> str:
    return json.dumps(
        {
            "привід": occasion.phrase(),
            "що_це_означає": occasion.task(),
            "у_кошику": list(have),
            "бракує_грн": f"{shortfall:.0f}",
            "стеля": TABLE_LIMIT,
            **({"потрібно_видів": need_kinds} if need_kinds is not None else {}),
            "купує_сам": [{"вид": name, "чеків": count} for name, count in habits[:HISTORY_LIMIT]]
            or None,
        },
        ensure_ascii=False,
    )


async def more_for_table(
    llm: Any,
    occasion: Occasion,
    *,
    have: Sequence[str],
    shortfall: Decimal,
    habits: Sequence[tuple[str, int]] = (),
    need_kinds: int | None = None,
) -> TablePlan:
    prompt = prompt_stamp("table", TABLE_SYSTEM)
    decision = await llm.decide(
        system=TABLE_SYSTEM,
        user=table_payload(
            occasion, have=have, shortfall=shortfall, habits=habits, need_kinds=need_kinds
        ),
        schema=TABLE_SCHEMA,
        prompt=prompt,
        max_tokens=768,
    )
    added, _skipped, _beyond = plan_of(decision.data, intents=have, protected=())
    return TablePlan(
        added=added[:TABLE_LIMIT],
        model=decision.model,
        prompt=prompt,
        duration_ms=decision.duration_ms,
        tokens=decision.usage.input_tokens + decision.usage.output_tokens,
    )


__all__ = [
    "HISTORY_LIMIT",
    "OCCASION_SCHEMA",
    "OCCASION_SYSTEM",
    "TABLE_SCHEMA",
    "TABLE_SYSTEM",
    "Change",
    "OccasionPlan",
    "TablePlan",
    "more_for_table",
    "payload",
    "plan_of",
    "rework",
    "table_payload",
    "target_of",
]
