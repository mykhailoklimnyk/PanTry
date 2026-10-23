from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from time import monotonic
from typing import Any

from komora.agent.basket import _sale_of as sale_of
from komora.agent.basket import collapse_same_product, collapse_split
from komora.agent.executor import Made
from komora.agent.loop import LOOP_INTENTS, LOOP_STEPS, Loop, resolve_one, tools_note
from komora.agent.steps.ground import Ground
from komora.agent.steps.shelf import Shelf
from komora.core.plan import Refusal
from komora.core.queries import narrow
from komora.core.twins import Drop as TwinDrop
from komora.core.twins import Row as TwinRow
from komora.core.twins import groups as group_twins
from komora.core.twins import judge as judge_twins
from komora.core.words import plural
from komora.logging import get_logger

TOOL = "агент"

log = get_logger(__name__)


def _unit_price(line: Any) -> str:
    price = line.product.get("price")
    if price is None:
        return ""
    unit, _step = sale_of(line.product)
    return f"{price} грн/{unit}"


def _promo_note(line: Any) -> str:
    was = line.product.get("oldPrice")
    now = line.product.get("price")
    if not was or now is None or float(was) <= float(now):
        return ""
    return f"було {was}, стало {now}"


@dataclass(slots=True)
class Decide:

    ground: Ground
    shelf: Shelf
    llm: Any = None
    picks: dict[str, dict[str, Any]] = field(default_factory=dict, init=False)
    expendable: list[tuple[str, str]] = field(default_factory=list, init=False)
    model_used: str = field(default="без агента", init=False)
    tokens: int = field(default=0, init=False)
    decidable: list[str] = field(default_factory=list, init=False)
    lines: list[Any] = field(default_factory=list, init=False)
    unresolved: list[str] = field(default_factory=list, init=False)
    declined: dict[str, str] = field(default_factory=dict, init=False)
    twins_dropped: tuple[TwinDrop, ...] = field(default=(), init=False)

    async def pick(self, bound: Mapping[str, Any], *, ask: Any, labels: Sequence[str] = ()) -> Made:
        intents: Sequence[str] = bound["intents"]
        wanted = tuple(labels)
        rowed = {line.intent for line in self.lines}
        scope = [
            intent for intent in intents if (intent in wanted if wanted else intent not in rowed)
        ]
        address: dict[str, Any] = {
            **({"адресно": len(wanted)} if wanted else {}),
            **({"без рядка": len(scope)} if rowed and not wanted else {}),
            **({"наміри": list(scope)} if wanted or rowed else {}),
        }
        self.decidable = [intent for intent in scope if self.shelf.candidates.get(intent)]
        if self.llm is None:
            return Made(absent="без моделі: план зібрано кодом за історією", tag_tone="muted")
        if not self.decidable:
            return Made(
                args={"intents": len(intents), **address},
                absent="нема з чого обирати: жоден намір не дав кандидатів",
            )

        started = monotonic()
        try:
            picks, expendable, model, agent_ms, tokens, batched = await ask(self.decidable)
        except Exception as exc:
            return Made(
                args={"помилка": str(exc)[:400], "мс": round((monotonic() - started) * 1000)},
                absent=f"модель недоступна ({str(exc)[:70]}) — план за історією",
                absent_kind=Refusal.BROKE,
                tag_tone="warn",
            )
        for intent in self.decidable:
            self.picks.pop(intent, None)
        self.picks.update(picks)
        asked = set(self.decidable)
        self.expendable[:] = [
            *(entry for entry in self.expendable if entry[0] not in asked),
            *expendable,
        ]
        self.model_used, self.tokens = model, tokens
        note = f"агент обрав товари під {len(picks)} намірів"
        return Made(
            facts={"picks": picks},
            args={
                "intents": len(intents),
                **address,
                "пачок": batched.sent,
                "мс виклику": agent_ms,
            },
            summary=f"{note} · {batched.note}" if batched.note else note,
            decision="вибір товару і кількості — рішення агента",
            tag=f"-{len(batched.lost)} поз." if batched.lost else "агент",
            tag_tone="warn" if batched.lost else "good",
            prompt=batched.prompt,
            tool=model,
        )

    async def chain(self, bound: Mapping[str, Any], *, build: Any) -> Made:
        lines, unresolved, declined = await build()
        self.lines, self.unresolved, self.declined = lines, unresolved, declined
        chains = {line.intent: line.chain for line in lines if line.chain}
        risky = sum(1 for line in lines if line.chain and line.risky)
        return Made(
            facts={"lines": lines, "chains": chains},
            args={
                "рядків": len(lines),
                "з ланцюжком": len(chains),
                "не знайшлось": len(unresolved),
                "агент не взяв": len(declined),
            },
            summary=f"рядків кошика {len(lines)}, із ланцюжком замін {len(chains)}"
            + (f", з них {risky} просять уваги" if risky else ""),
            decision="ланцюжок узгоджується наперед: після оформлення змінити замовлення "
            "вже не можна, і замінює збирач",
            tag=f"{len(chains)} із заміною" if chains else "без замін",
            tag_tone="good" if chains else "muted",
        )

    def collapse(self) -> set[str]:
        merged: set[str] = set()
        if self.shelf.fallback_words:
            was = {line.intent for line in self.lines}
            doubled = collapse_split(self.lines, self.shelf.fallback_words)
            merged |= was - {line.intent for line in self.lines}
            if doubled:
                self.ground.trace.add(
                    "step-split",
                    "core.list",
                    {"знято": len(doubled), "види": list(doubled)},
                    f"той самий вид приїхав двома словами однієї фрази: {len(doubled)}",
                    decision="гість просив це один раз — лишаю один рядок",
                    tag="-дубль",
                    tag_tone="muted",
                )

        was = {line.intent for line in self.lines}
        doubled_products = collapse_same_product(self.lines)
        merged |= was - {line.intent for line in self.lines}
        if doubled_products:
            self.ground.trace.add(
                "step-merge",
                "core.list",
                {
                    "злито": sum(count for _, count in doubled_products),
                    "товари": [f"{name} ({count})" for name, count in doubled_products],
                },
                f"під різні наміри полиця дала той самий товар: {len(doubled_products)}",
                decision="один артикул — один рядок; кількість найбільша з намірів, "
                "а не сума: полиця сьогодні одна, а не апетит утричі більший",
                tag=f"-{sum(count - 1 for _, count in doubled_products)} дубль",
                tag_tone="muted",
            )
        return merged

    async def twins(
        self,
        bound: Mapping[str, Any],
        *,
        ask: Any,
        phrases: Mapping[str, str] | None = None,
        kinds: Mapping[str, str] | None = None,
        sections: Mapping[str, frozenset[str]] | None = None,
    ) -> Made:
        said = dict(phrases or {})
        by_kind = dict(kinds or {})
        shelf = dict(sections or {})
        rows = [
            TwinRow(
                intent=line.intent,
                article=str(line.product.get("externalProductId") or ""),
                name=str(line.product.get("name") or line.intent),
                phrase=said.get(line.intent, ""),
                kind_key=by_kind.get(line.intent, line.intent),
                guest_word=not line.auto_need,
                own_article=bool(line.history_matched),
                price=line.total,
                receipts=hint.receipts if (hint := line.from_history) is not None else 0,
                recent_receipts=hint.recent_receipts if hint is not None else 0,
                unit_price=_unit_price(line),
                promo=_promo_note(line),
                came_from=str(line.reason or ""),
                sections=shelf.get(str(line.product.get("externalProductId") or ""), frozenset()),
                bought=frozenset(
                    moment.date().isoformat()
                    for moment in (line.from_history.moments if line.from_history else ())
                ),
            )
            for line in self.lines
            if not line.at_home
        ]
        pairs = group_twins(rows)
        if not pairs:
            return Made(
                facts={"lines": self.lines},
                args={"рядків": len(rows)},
                summary="пар одного виду немає — згортати нема чого",
                tag="без близнюків",
                tag_tone="muted",
            )
        if self.llm is None:
            return Made(
                args={"пар": len(pairs), "види": [group.key for group in pairs]},
                absent="без моделі: чи це одна потреба вдома, код не вирішує",
                tag_tone="muted",
            )
        try:
            plan = await ask(pairs)
        except Exception as exc:
            return Made(
                args={"пар": len(pairs), "помилка": str(exc)[:400]},
                absent=f"модель недоступна ({str(exc)[:70]}) — лишаю обидва рядки",
                absent_kind=Refusal.BROKE,
                tag_tone="warn",
            )
        judged = judge_twins(pairs, plan.verdicts)
        self.twins_dropped = judged.dropped
        gone = {drop.intent for drop in judged.dropped}
        if gone:
            self.lines[:] = [line for line in self.lines if line.intent not in gone]
        return Made(
            facts={"lines": self.lines},
            args={
                "пар": len(pairs),
                "знято": [
                    f"«{drop.name}» → «{drop.kept_name}»: {drop.why}" for drop in judged.dropped
                ],
                "лишено": dict(judged.left),
                **({"лишив слово гостя": list(judged.guest_kept)} if judged.guest_kept else {}),
                **(
                    {"свій артикул замість заміни": list(judged.own_kept)}
                    if judged.own_kept
                    else {}
                ),
                **({"ключі повз перелік": list(plan.stray)} if plan.stray else {}),
                "токенів": plan.tokens,
            },
            summary=(
                f"пар одного виду {len(pairs)}, згорнуто {len(judged.dropped)}"
                if judged.dropped
                else f"пар одного виду {len(pairs)}, і всі вони — різні потреби"
            ),
            decision="чи два рядки одного виду це одна потреба вдома — рішення агента; "
            "слово гостя і свій артикул з чеків лишає код",
            prompt=plan.prompt,
            tool=plan.model or TOOL,
            tag=f"-{len(judged.dropped)} дубль" if judged.dropped else "різні потреби",
            tag_tone="muted" if judged.dropped else "good",
        )

    def refusals(self, unresolved: Sequence[str], declined: Mapping[str, str]) -> list[str]:
        left = [intent for intent in unresolved if intent not in declined]
        if self.picks:
            self.ground.trace.add(
                "step-declined",
                TOOL,
                {
                    "відмов": len(declined),
                    "виборів": len(self.picks),
                    "чому": dict(declined),
                },
                (
                    f"кандидати були під {len(self.picks)} "
                    f"{plural(len(self.picks), 'намір', 'наміри', 'намірів')}; "
                    + (
                        f"під {len(declined)} агент сказав «жоден не той»"
                        if declined
                        else "під кожен агент щось обрав"
                    )
                ),
                decision="порожній вибір при наявних кандидатах — це відповідь "
                "«жоден не той», а не «не знайшлось»: порада мусить пасувати причині",
                tag=f"-{len(declined)} поз." if declined else "жодної",
                tag_tone="warn" if declined else "muted",
            )
        return left

    async def loop(
        self,
        bound: Mapping[str, Any],
        *,
        listed: Sequence[str],
        hints: Mapping[str, Any],
        history: Mapping[str, Sequence[Any]],
        tools: Sequence[Mapping[str, Any]],
        search: Any,
        similar: Any,
        build: Any,
        why: str,
        skills: str = "",
        labels: Sequence[str] = (),
    ) -> Made:
        seen: dict[str, list[dict[str, Any]]] = bound["candidates"]
        queue = [i for i in self.unresolved if i in listed] + [
            i for i in self.unresolved if i not in listed
        ]
        wanted = tuple(labels)
        if wanted:
            queue = [i for i in queue if i in wanted]
        note, described = tools_note(tools)
        assert self.llm is not None
        loops: list[Loop] = []
        for intent in queue[:LOOP_INTENTS]:
            own = [
                {"lagerId": item.lager_id, "назва": item.name, "чеків": item.receipts}
                for item in history.get(intent, [])[:3]
                if item.lager_id.isdigit()
            ]
            try:
                loops.append(
                    await resolve_one(
                        self.llm,
                        intent,
                        seen=seen.get(intent, []),
                        own=own,
                        tried=[intent, *narrow(intent)[:3]],
                        search=search,
                        similar=similar,
                        skills=skills,
                        note=note,
                    )
                )
            except Exception as exc:
                log.warning("basket.loop_failed", intent=intent, error=str(exc)[:120])
                loops.append(Loop(intent=intent, gave_up=f"збій ({str(exc)[:60]})"))
        found = [loop for loop in loops if loop.chosen is not None]
        if found:
            for loop in found:
                seen[loop.intent] = loop.candidates
            picks = {
                loop.intent: {
                    "chosen_id": str(loop.chosen["externalProductId"]),
                    "qty": (hints[loop.intent].typical_qty if loop.intent in hints else 1),
                    "why": why,
                }
                for loop in found
                if loop.chosen is not None
            }
            self.picks.update(picks)
            more = build([loop.intent for loop in found], seen, picks)
            self.lines.extend(more)
            done = {line.intent for line in more}
            self.unresolved = [i for i in self.unresolved if i not in done]
            self.declined = {i: text for i, text in self.declined.items() if i not in done}
        beyond = max(0, len(queue) - LOOP_INTENTS)
        steps = sum(loop.steps for loop in loops)
        return Made(
            facts={"lines": self.lines},
            args={
                "намірів": min(len(queue), LOOP_INTENTS),
                **({"адресно": len(wanted), "наміри": queue[:LOOP_INTENTS]} if wanted else {}),
                "кроків": steps,
                "стеля": f"{LOOP_INTENTS} намірів × {LOOP_STEPS} кроки",
                "токенів": sum(loop.tokens for loop in loops),
                "описи": described,
                "діалог": [loop.summary() for loop in loops],
            },
            summary=f"дошукав {len(found)} з {len(loops)} "
            + plural(len(loops), "наміру", "намірів", "намірів")
            + f" за {steps} "
            + plural(steps, "крок", "кроки", "кроків")
            + (f"; ще {beyond} поза стелею намірів" if beyond else ""),
            prompt=next((loop.prompt for loop in loops if loop.prompt), None),
            decision="чим шукати далі — рішення агента; філію, слот і перелік "
            "інструментів сталий, артикул береться лише з побаченого",
            tag=f"+{len(found)}" if found else "не знайшлось",
            tag_tone="good" if found else "muted",
        )


__all__ = ["TOOL", "Decide"]
