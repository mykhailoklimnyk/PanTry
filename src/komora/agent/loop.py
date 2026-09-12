from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from komora.agent.prompts import register as register_prompt
from komora.agent.prompts import stamp as prompt_stamp
from komora.core.instructions import Verdict, digest
from komora.core.queries import norm_query
from komora.logging import get_logger
from komora.mcp import verdicts as verdict_register

log = get_logger(__name__)

LOOP_INTENTS = 3

LOOP_STEPS = 3

LOOP_TOKENS = 512

LOOP_SHOWN = 12

LOOP_TOOLS: tuple[str, ...] = ("silpo_find_products_batch", "silpo_get_similar_products")

LOOP_QUERIES = 4

LOOP_FIRST_NAMES = 3

LOOP_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "tool": {"type": ["string", "null"], "enum": [*LOOP_TOOLS, None]},
        "arguments": {"type": ["object", "null"]},
        "finish": {"type": ["string", "null"], "enum": ["pick", "give_up", None]},
        "chosen_id": {"type": ["string", "null"]},
        "why": {"type": ["string", "null"]},
        "give_up": {"type": ["string", "null"]},
    },
}

LOOP_SYSTEM = (
    "Ти агент продуктового кошика «Комора». Під намір гостя нічого підхожого не "
    "знайшлось звичайним пошуком. Твоя робота -- за КІЛЬКА кроків або знайти "
    "правильний товар, або чесно відмовитись. На кожному кроці роби рівно ОДНЕ: "
    "(а) поклич один інструмент з переліку і дай його аргументи -- поле «tool» і "
    "«arguments»; (б) закінчи вибором -- «finish» = «pick», «chosen_id» з артикулом "
    "кандидата, якого ти БАЧИШ у полі «кандидати», і «why» одним реченням; "
    "(в) закінчи відмовою -- «finish» = «give_up» і «give_up» з причиною. "
    "Закінчити можна ЛИШЕ полем «finish»: артикул без «finish» = «pick» вибором не "
    "вважається, причина без «finish» = «give_up» -- відмовою. Артикул, якого немає "
    "серед кандидатів, не називай. Філію, спосіб доставки і слот не пиши -- їх "
    "підставить код. Якщо в гостя є свій артикул (поле «свої артикули»), спершу "
    "шукай за його ЧИСЛОМ: описи інструментів кажуть, що це найнадійніший збіг. "
    "Знайдений за числом артикул -- це ТОЙ САМИЙ товар гостя, навіть якщо назва "
    "на полиці інша. Поле «фідбек» -- відповідь полиці на твої попередні кроки; "
    "читай його і не повторюй запит, який уже пробували. На ОСТАННЬОМУ кроці "
    "(поле «крок» каже, котрий він) інструментів більше не клич -- закінчи "
    "полем «finish». Відповідай ВИКЛЮЧНО українською."
)

register_prompt("loop", LOOP_SYSTEM)

TOOLS_NOTE = (
    "Інструменти:\n"
    "- silpo_find_products_batch: пошук на полиці за назвами або числовими артикулами\n"
    "- silpo_get_similar_products: схожі товари до кандидата"
)

ARGUMENTS_NOTE = (
    "З аргументів ти пишеш ЛИШЕ це:\n"
    '- silpo_find_products_batch: {"products": [до чотирьох рядків -- назви або '
    "числові артикули]}\n"
    '- silpo_get_similar_products: {"slug": slug кандидата з поля «кандидати»}\n'
    "Решту (філія, спосіб доставки, слот, ліміт) підставляє код."
)

FALLBACK_NOTE = TOOLS_NOTE + "\n" + ARGUMENTS_NOTE

REPEAT_WARNING = "ти повторюєшся: зміни підхід або відмовся"


def tools_note(
    tools: Sequence[Mapping[str, Any]],
    *,
    verdicts: Sequence[Verdict] | None = None,
) -> tuple[str, str]:
    rows = verdict_register.load() if verdicts is None else verdicts
    said = digest(tools, rows, wanted=LOOP_TOOLS)
    if not said.rows:
        return FALLBACK_NOTE, "запасний текст"
    return "Інструменти:\n" + said.text() + "\n" + ARGUMENTS_NOTE, "живі описи"


@dataclass(slots=True)
class Loop:

    intent: str
    steps: int = 0
    tokens: int = 0
    duration_ms: int = 0
    chosen: dict[str, Any] | None = None
    why: str = ""
    gave_up: str | None = None
    prompt: str = ""
    calls: list[str] = field(default_factory=list)
    candidates: list[dict[str, Any]] = field(default_factory=list)
    turns: list[str] = field(default_factory=list)
    """Діалог: по рядку на крок, «запит → фідбек → рішення» (#290).

    Журі питає не «скільки кроків», а «як він дійшов»: без цих рядків
    петля, яка виправилась після порожньої видачі, і петля, яка вгадала
    з першого разу, на екрані виглядають однаково."""

    @property
    def found(self) -> bool:
        return self.chosen is not None

    def _head(self) -> str:
        if self.chosen is not None:
            return (
                f"«{self.intent}» → {self.chosen.get('name')} за {self.steps} "
                f"{_steps_word(self.steps)}"
            )
        return f"«{self.intent}» → відмова: {self.gave_up or 'без причини'}"

    def phrase(self) -> str:
        return self._head() + (f" ({', '.join(self.calls)})" if self.calls else "")

    def dialog(self) -> str:
        return " · ".join(f"{n}) {turn}" for n, turn in enumerate(self.turns, 1))

    def summary(self) -> str:
        return f"{self._head()}: {self.dialog()}" if self.turns else self._head()


def _steps_word(n: int) -> str:
    if n == 1:
        return "крок"
    if 2 <= n <= 4:
        return "кроки"
    return "кроків"


def _card(product: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(product.get("externalProductId") or ""),
        "назва": product.get("name"),
        "ціна": product.get("price"),
        "фасовка": product.get("displayRatio"),
        "slug": product.get("slug"),
    }


def _merge(into: list[dict[str, Any]], more: Sequence[Mapping[str, Any]]) -> int:
    known = {str(p.get("externalProductId")) for p in into}
    added = 0
    for product in more:
        key = str(product.get("externalProductId") or "")
        if not key or key in known or not product.get("available", True):
            continue
        into.append(dict(product))
        known.add(key)
        added += 1
    return added


def _names(cards: Sequence[Mapping[str, Any]]) -> str:
    return ", ".join(str(card.get("name")) for card in cards[:LOOP_FIRST_NAMES] if card.get("name"))


def _found_text(added: int, cards: Sequence[Mapping[str, Any]]) -> str:
    names = _names(cards)
    if not added:
        return "0 товарів" + (f" (усе вже серед кандидатів: {names})" if names else "")
    return f"+{added}, перші: {names}" if names else f"+{added}"


Searcher = Callable[[list[str]], Awaitable[dict[str, list[dict[str, Any]]]]]
Similar = Callable[[str], Awaitable[list[dict[str, Any]]]]


async def resolve_one(
    llm: Any,
    intent: str,
    *,
    seen: Sequence[Mapping[str, Any]],
    own: Sequence[Mapping[str, Any]],
    tried: Sequence[str],
    search: Searcher,
    similar: Similar,
    max_steps: int = LOOP_STEPS,
    skills: str = "",
    note: str = FALLBACK_NOTE,
) -> Loop:
    loop = Loop(intent=intent, candidates=[dict(p) for p in seen])
    started = time.perf_counter()
    queries_tried = list(tried)
    tried_keys = {norm_query(q) for q in queries_tried}
    slugs_asked: set[str] = set()
    feedback: list[str] = []
    repeats = 0

    def burn(ask: str, result: str) -> None:
        feedback.append(f"{ask}: {result}")
        loop.turns.append(f"{ask} → {result} → далі")

    system = LOOP_SYSTEM + "\n\n" + note + skills
    prompt = prompt_stamp("loop", system)
    loop.prompt = prompt

    for _ in range(max_steps):
        loop.steps += 1
        context: dict[str, Any] = {
            "намір": intent,
            "свої артикули": list(own),
            "пробували": queries_tried,
            "фідбек": feedback,
            "кандидати": [_card(p) for p in loop.candidates[:LOOP_SHOWN]],
            "крок": f"{loop.steps} з {max_steps}",
        }
        if repeats:
            context["попередження"] = REPEAT_WARNING
        try:
            decision = await llm.decide(
                system=system,
                user=json.dumps(context, ensure_ascii=False),
                schema=LOOP_SCHEMA,
                prompt=prompt,
                max_tokens=LOOP_TOKENS,
                temperature=0.0,
            )
        except Exception as exc:
            loop.gave_up = f"модель не відповіла ({str(exc)[:80]})"
            break
        loop.tokens += decision.usage.input_tokens + decision.usage.output_tokens
        data = decision.data or {}
        finish = str(data.get("finish") or "").strip()
        chosen_id = str(data.get("chosen_id") or "").strip()
        give_up = str(data.get("give_up") or "").strip()

        if finish == "pick":
            if not chosen_id:
                burn("вибір", "finish=pick без chosen_id: назви артикул кандидата")
                continue
            match = next(
                (p for p in loop.candidates if str(p.get("externalProductId")) == chosen_id),
                None,
            )
            if match is None:
                burn(
                    f"вибір {chosen_id}",
                    "цього артикула немає серед кандидатів; обирай лише з поля «кандидати»",
                )
                continue
            loop.chosen = match
            loop.why = str(data.get("why") or "")
            loop.turns.append(f"вибір {chosen_id} → {match.get('name')} → обрано")
            break
        if finish == "give_up":
            loop.gave_up = give_up or "без причини"
            loop.turns.append(f"відмова → {loop.gave_up} → стоп")
            break
        if chosen_id:
            burn(f"вибір {chosen_id}", "щоб обрати, постав finish=pick")
            continue
        if give_up:
            burn("відмова", "щоб відмовитись, постав finish=give_up")
            continue

        tool = str(data.get("tool") or "")
        raw_args = data.get("arguments")
        arguments: Mapping[str, Any] = raw_args if isinstance(raw_args, Mapping) else {}
        if tool == "silpo_find_products_batch":
            raw = arguments.get("products")
            queries = [str(q).strip() for q in (raw or []) if str(q).strip()][:LOOP_QUERIES]
            fresh = [q for q in queries if norm_query(q) not in tried_keys]
            if not fresh:
                asked = ", ".join(f"«{q}»" for q in queries) or "порожній запит"
                repeats += 1
                if repeats > 1:
                    loop.gave_up = "повтор запиту"
                    loop.turns.append(f"пошук {asked} → уже пробували, і це вдруге → стоп")
                    break
                burn(f"пошук {asked}", f"це вже пробували. {REPEAT_WARNING}")
                continue
            queries_tried.extend(fresh)
            tried_keys |= {norm_query(q) for q in fresh}
            found = await search(fresh)
            answered: set[str] = set()
            parts: list[str] = []
            total = 0
            for query, cards in found.items():
                answered.add(norm_query(str(query)))
                added = _merge(loop.candidates, cards)
                total += added
                parts.append(f"«{query}»: {_found_text(added, cards)}")
            parts += [f"«{q}»: 0 товарів" for q in fresh if norm_query(q) not in answered]
            loop.calls.append(f"пошук {', '.join(fresh)}: +{total}")
            burn("пошук", "; ".join(parts))
            continue
        if tool == "silpo_get_similar_products":
            slug = str(arguments.get("slug") or "")
            if not any(str(p.get("slug")) == slug for p in loop.candidates):
                burn(
                    f"схожі до {slug or 'порожньо'}",
                    "такого кандидата не було; slug бери з поля «кандидати»",
                )
                continue
            if slug in slugs_asked:
                repeats += 1
                if repeats > 1:
                    loop.gave_up = "повтор запиту"
                    loop.turns.append(f"схожі до {slug} → уже пробували, і це вдруге → стоп")
                    break
                burn(f"схожі до {slug}", f"це вже пробували. {REPEAT_WARNING}")
                continue
            slugs_asked.add(slug)
            cards = await similar(slug)
            added = _merge(loop.candidates, cards)
            loop.calls.append(f"схожі до {slug}: +{added}")
            burn(f"схожі до {slug}", _found_text(added, cards))
            continue
        burn(
            f"інструмент {tool or 'порожньо'}",
            f"не з переліку; можна лише {', '.join(LOOP_TOOLS)}, або закінчити полем finish",
        )
    else:
        loop.gave_up = f"стеля {max_steps} кроків"
    loop.duration_ms = int((time.perf_counter() - started) * 1000)
    log.info(
        "loop.done",
        intent=intent,
        steps=loop.steps,
        found=loop.found,
        gave_up=loop.gave_up,
        calls=len(loop.calls),
        repeats=repeats,
    )
    return loop


__all__ = [
    "ARGUMENTS_NOTE",
    "FALLBACK_NOTE",
    "LOOP_FIRST_NAMES",
    "LOOP_INTENTS",
    "LOOP_QUERIES",
    "LOOP_SCHEMA",
    "LOOP_SHOWN",
    "LOOP_STEPS",
    "LOOP_SYSTEM",
    "LOOP_TOKENS",
    "LOOP_TOOLS",
    "REPEAT_WARNING",
    "TOOLS_NOTE",
    "Loop",
    "resolve_one",
    "tools_note",
]
