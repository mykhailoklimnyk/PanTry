from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from komora.agent.basket import (
    STOP_WORDS,
    HistoryItem,
    Naming,
    ask_kind,
    history_matches,
    kind_key,
    name_matches,
    narrow_by_query,
    norm_name,
    related_to,
    same_kind,
    search_products,
    strip_other_processing,
)
from komora.agent.executor import Made
from komora.agent.kinds import Kind, load_tree
from komora.agent.kinds import merge as merge_kinds
from komora.agent.kinds import narrow as narrow_kinds
from komora.agent.steps.ground import Ground
from komora.core.dictionary import Dictionary
from komora.core.queries import dedupe, narrow, one_product
from komora.core.words import plural
from komora.logging import get_logger
from komora.mcp.client import SEARCH_TOOL as _SEARCH_TOOL

log = get_logger(__name__)

KIND_QUERY_TAKE = 3

SEARCH_TOOL = _SEARCH_TOOL
KIND_TOOL = "silpo_get_products"


def _first_query(queries: Mapping[str, str]) -> str:
    return next(iter(dict.fromkeys(queries.values())), "")


@dataclass(slots=True)
class Shelf:

    ground: Ground
    candidates: dict[str, list[dict[str, Any]]]
    auto_intents: dict[str, HistoryItem] = field(default_factory=dict)
    siblings: Mapping[str, Sequence[str]] = field(default_factory=dict)
    tree: Dictionary | None = field(default=None, init=False)
    intents: list[str] = field(default_factory=list, init=False)
    hints: dict[str, HistoryItem] = field(default_factory=dict, init=False)
    hints_all: dict[str, list[HistoryItem]] = field(default_factory=dict, init=False)
    answered: dict[str, Any] = field(default_factory=dict, init=False)
    dropped: set[str] = field(default_factory=set, init=False)
    chosen_nodes: dict[str, str] = field(default_factory=dict, init=False)
    clarified: dict[str, str] = field(default_factory=dict, init=False)
    probed: dict[str, str] = field(default_factory=dict, init=False)
    stray: list[str] = field(default_factory=list, init=False)
    kind_done: bool = field(default=False, init=False)
    read_whole: frozenset[str] = field(default_factory=frozenset)
    fallback_words: dict[str, list[str]] = field(default_factory=dict, init=False)
    narrowed: dict[str, Kind] = field(default_factory=dict, init=False)

    async def by_article(self, bound: Mapping[str, Any]) -> Made:
        by_number = {
            item.lager_id: intent
            for intent, item in self.auto_intents.items()
            if item.lager_id.isdigit()
            and not any(
                str(p.get("externalProductId")) == item.lager_id
                for p in self.candidates.get(intent, [])
            )
        }
        kin = {
            article: intent
            for intent, articles in self.siblings.items()
            for article in articles
            if article not in by_number
            and not any(
                str(p.get("externalProductId")) == article for p in self.candidates.get(intent, [])
            )
        }
        found = 0
        kin_found = 0
        article_ms: int | None = None
        if by_number or kin:
            hits, article_ms = await search_products(
                self.ground.mcp, [*by_number, *kin], bound["slot"], bound["branch"]
            )
            heads: dict[str, int] = {}
            for article, intent in by_number.items():
                own = [
                    p for p in hits.get(article, []) if str(p.get("externalProductId")) == article
                ]
                if own:
                    self.candidates[intent] = own + self.candidates.get(intent, [])
                    heads[intent] = len(own)
                    found += 1
            for article, intent in kin.items():
                mine = [
                    p for p in hits.get(article, []) if str(p.get("externalProductId")) == article
                ]
                if mine:
                    rest = self.candidates.get(intent, [])
                    head = heads.get(intent, 0)
                    self.candidates[intent] = rest[:head] + mine + rest[head:]
                    heads[intent] = head + len(mine)
                    kin_found += 1
        return Made(
            facts={"candidates": self.candidates},
            args={
                "артикулів": len(by_number),
                "на полиці": found,
                "того ж виду": len(kin),
                "того ж виду на полиці": kin_found,
                "мс пошуку": article_ms,
            },
            summary=(
                f"за числовим артикулом з чека: спитав {len(by_number)}, на полиці {found}"
                + (
                    f"; інших своїх того ж виду спитав {len(kin)}, на полиці {kin_found}"
                    if kin
                    else ""
                )
                if by_number or kin
                else "за числовим артикулом: усе своє вже в видачі за назвою — пошуку не було"
            ),
            decision="крок поставив план: опис інструмента називає пошук числом "
            "найнадійнішим збігом",
            tag=f"+{found + kin_found}" if found + kin_found else None,
            tag_tone="good" if found + kin_found else "muted",
        )

    async def search(
        self,
        bound: Mapping[str, Any],
        *,
        heard: Any,
        occasion: Any,
        said: Mapping[str, Any],
        history: list[HistoryItem],
        ripe_names: Mapping[str, Naming],
        spent_ms: int,
    ) -> Made:
        slot = bound["slot"]
        branch_id = bound["branch"] or None
        mcp = self.ground.mcp
        trace = self.ground.trace
        candidates = self.candidates
        intents = bound["intents"]
        search_ms = spent_ms
        await self.ladder(slot=slot, branch_id=branch_id, ripe_names=ripe_names)

        occasion = await heard.wait(occasion, intents)
        answer_intents = heard.intents

        if answer_intents:
            more, more_ms = await search_products(mcp, list(answer_intents), slot, branch_id)
            candidates.update(more)
            search_ms += more_ms

        by_kind = {ask_kind(answer.intent, ripe_names): answer for answer in said.values()}
        answered = {
            intent: answer
            for intent in intents
            if (answer := said.get(kind_key(intent)) or by_kind.get(ask_kind(intent, ripe_names)))
            is not None
        }
        dropped = {intent for intent, answer in answered.items() if answer.skip}
        chosen_nodes = {intent: answer.slug for intent, answer in answered.items() if answer.slug}
        clarified = {
            intent: text
            for intent, answer in answered.items()
            if (text := (answer.text or "").strip()) and not answer.skip
        }
        probed = {
            intent: phrase
            for intent, answer in answered.items()
            if (phrase := (answer.query or "").strip()) and not answer.skip
        }

        refined = {
            intent: f"{intent} {text}" for intent, text in clarified.items() if intent in intents
        }
        await self.by_words(refined, clarified=clarified, slot=slot, branch_id=branch_id)

        intents = await self.split(intents, slot=slot, branch_id=branch_id)

        hints_all = {
            intent: matches for intent in intents if (matches := history_matches(intent, history))
        }
        hints = {intent: matches[0] for intent, matches in hints_all.items()}

        search_ms += await self.exact(intents, hints=hints, slot=slot, branch_id=branch_id)

        self.kind_done = await self.kind(
            intents, slot=slot, branch_id=branch_id, chosen=chosen_nodes
        )

        if probed:
            narrowed_by_query, probe_ms = await narrow_by_query(
                mcp, candidates, probed, slot=slot, branch_id=branch_id
            )
            trace.add(
                "step-answers",
                "silpo_find_products_batch",
                {
                    "звужено": len(narrowed_by_query),
                    "відповідей": len(probed),
                    "варіанти": dict(probed),
                },
                f"гість обрав варіант: {len(probed)} "
                + plural(len(probed), "намір", "наміри", "намірів")
                + (
                    ""
                    if len(narrowed_by_query) == len(probed)
                    else "; на полиці зараз порожньо — лишаю набір, який був"
                ),
                duration_ms=probe_ms,
                decision="відповідь звужує НАБІР, а не лише слово в промпті",
                tag="звужено" if narrowed_by_query else "без змін",
                tag_tone="good" if narrowed_by_query else "warn",
            )

        self.stray = stray = [
            intent
            for intent in intents
            if candidates.get(intent)
            and intent not in hints
            and intent not in probed
            and not (intent in self.narrowed and self.narrowed[intent].products)
            and not any(related_to(intent, p["name"]) for p in candidates[intent])
        ]
        if stray:
            for intent in stray:
                candidates.pop(intent, None)
            trace.add(
                "step-stray",
                "core.brands",
                {"намірів": len(stray), "слова": list(stray)},
                f"у видачі немає нічого, пов'язаного зі словом: {len(stray)}",
                decision="фонетичний сусід не стає вибором: чесніше сказати «немає», "
                "ніж принести не те",
                tag="не знайшлось",
                tag_tone="warn",
            )

        empty_handed = [intent for intent in intents if not candidates.get(intent)]
        self.intents, self.hints, self.hints_all = intents, hints, hints_all
        self.answered, self.dropped, self.chosen_nodes = answered, dropped, chosen_nodes
        self.clarified, self.probed = clarified, probed
        return Made(
            facts={"candidates": candidates, "intents": intents},
            args={"queries": len(intents), "порожніх": len(empty_handed), "мс пошуку": search_ms},
            summary=f"кандидатів: {sum(len(v) for v in candidates.values())} "
            f"на {len(intents)} намірів; "
            f"{len(hints)} намірів упізнано в історії"
            + (f"; без жодного кандидата: {len(empty_handed)}" if empty_handed else ""),
            tag=f"{len(empty_handed)} без товару" if empty_handed else None,
            tag_tone="warn" if empty_handed else "muted",
        )

    async def ladder(
        self,
        *,
        slot: dict[str, Any],
        branch_id: str | None,
        ripe_names: Mapping[str, Naming],
    ) -> None:
        narrowed_hits: dict[str, str] = {}
        narrow_ms = 0
        remaining = [intent for intent in self.auto_intents if not self.candidates.get(intent)]
        for step in range(3):
            if not remaining:
                break
            asked = {intent: narrow(intent) for intent in remaining}
            queries = {
                intent: variants[step] for intent, variants in asked.items() if len(variants) > step
            }
            if not queries:
                break
            more, more_ms = await search_products(
                self.ground.mcp, list(dict.fromkeys(queries.values())), slot, branch_id
            )
            narrow_ms += more_ms
            still: list[str] = []
            for intent in remaining:
                query = queries.get(intent)
                fit = [p for p in more.get(query or "", []) if related_to(query or "", p["name"])]
                if fit:
                    self.candidates[intent] = fit
                    narrowed_hits[intent] = query or ""
                else:
                    still.append(intent)
            remaining = still
        if narrowed_hits:
            self.ground.trace.add(
                "step-narrow",
                "silpo_find_products_batch",
                {
                    "звужено": len(narrowed_hits),
                    "запити": dict(narrowed_hits),
                },
                f"назва з чека нічого не дала — звузив до виду: {len(narrowed_hits)}",
                duration_ms=narrow_ms,
                decision="кандидати звуженого запиту звіряються з ним же: ширший "
                "запит приносить чуже, а не потрібне",
                tag=f"+{len(narrowed_hits)} поз.",
                tag_tone="good",
            )

        kind_queries = {
            intent: naming.intent.strip()
            for intent in self.auto_intents
            if (naming := ripe_names.get(kind_key(intent))) is not None and naming.intent.strip()
        }
        kind_queries = {
            intent: query
            for intent, query in kind_queries.items()
            if query.casefold() != intent.casefold()
        }
        if kind_queries:
            more, more_ms = await search_products(
                self.ground.mcp, list(dict.fromkeys(kind_queries.values())), slot, branch_id
            )
            added_by_kind = 0
            for intent, query in kind_queries.items():
                fit = [p for p in more.get(query, []) if related_to(query, p["name"])]
                if not fit:
                    continue
                known = {str(p["externalProductId"]) for p in self.candidates.get(intent, [])}
                extra = [p for p in fit if str(p["externalProductId"]) not in known][
                    :KIND_QUERY_TAKE
                ]
                if extra:
                    self.candidates[intent] = self.candidates.get(intent, []) + extra
                    added_by_kind += len(extra)
            if kind_queries:
                self.ground.trace.add(
                    "step-kind-query",
                    "silpo_find_products_batch",
                    {
                        "намірів": len(kind_queries),
                        "докинуто": added_by_kind,
                        "фрази": dict(kind_queries),
                        "правило": "назва з чека шукає ТОВАР, видова фраза шукає ВИД: "
                        "«Рулет» дає торти, «рулет м'ясний» — м'ясні рулети",
                    },
                    f"спитав пошук видовою фразою: {added_by_kind} нових кандидатів до "
                    f"{len(kind_queries)} намірів",
                    duration_ms=more_ms,
                    decision="назва з чека шукає товар, а вид шукає окрема фраза — "
                    f"цього разу «{_first_query(kind_queries)}»",
                    tag=f"+{added_by_kind} поз." if added_by_kind else "нічого нового",
                    tag_tone="good" if added_by_kind else "muted",
                )

    async def by_words(
        self,
        refined: Mapping[str, str],
        *,
        clarified: Mapping[str, str],
        slot: dict[str, Any],
        branch_id: str | None,
    ) -> None:
        if not refined:
            return
        more, more_ms = await search_products(
            self.ground.mcp, list(refined.values()), slot, branch_id
        )
        for intent, query in refined.items():
            known = {str(p["externalProductId"]) for p in self.candidates.get(intent, [])}
            extra = [
                product
                for product in more.get(query, [])
                if str(product["externalProductId"]) not in known
            ]
            if extra:
                self.candidates[intent] = self.candidates.get(intent, []) + extra
        self.ground.trace.add(
            "step-answers",
            "silpo_find_products_batch",
            {"уточнень": len(refined), "слова": dict(clarified)},
            f"гість уточнив словами: {len(clarified)} "
            + plural(len(clarified), "намір", "наміри", "намірів"),
            duration_ms=more_ms,
            decision="слова гостя важать більше за наш вибір виду",
            tag="уточнено",
            tag_tone="good",
        )

    async def split(
        self, intents: list[str], *, slot: dict[str, Any], branch_id: str | None
    ) -> list[str]:
        entered = len(intents)
        self.fallback_words = fallback_words = {}
        split_blind: set[str] = set()
        for intent in intents:
            if intent in self.auto_intents:
                continue
            if intent in self.read_whole:
                continue
            if one_product(intent):
                continue
            words = [
                word
                for word in intent.split()
                if len(word) >= 3 and norm_name(word) not in STOP_WORDS
            ]
            found = self.candidates.get(intent) or []
            on_phrase = any(related_to(intent, product["name"]) for product in found)
            if not on_phrase and words and (len(words) > 1 or words[0] != intent):
                fallback_words[intent] = words
                if not found:
                    split_blind.add(intent)
        if fallback_words:
            flat = list(
                dict.fromkeys(
                    word
                    for words in fallback_words.values()
                    for word in words
                    if word not in self.candidates
                )
            )
            more, more_ms = await search_products(self.ground.mcp, flat, slot, branch_id)
            self.candidates.update(more)

            kept: list[str] = []
            for intent, parts in list(fallback_words.items()):
                if intent in split_blind:
                    continue
                if all(
                    any(
                        name_matches(word, product["name"])
                        for product in self.candidates.get(word) or []
                    )
                    for word in parts
                ):
                    continue
                del fallback_words[intent]
                kept.append(intent)

            expanded: list[str] = []
            for intent in intents:
                if intent in fallback_words:
                    expanded.extend(fallback_words[intent])
                else:
                    expanded.append(intent)
            intents = dedupe(expanded)
            blind = len(split_blind)
            astray = len(fallback_words) - blind
            split_note = (
                "намір розкладено на слова: "
                + "; ".join(f"«{k}» → {', '.join(v)}" for k, v in fallback_words.items())
                + f" (без жодного результату {blind}, з результатами не про фразу {astray})"
                if fallback_words
                else "жодного наміру не розклав"
            )
            kept_note = (
                "; лишив цілими, бо видом виявилось не кожне слово: "
                + ", ".join(f"«{intent}»" for intent in kept)
                if kept
                else ""
            )
            self.ground.trace.add(
                "step-split",
                "core.list",
                {
                    "розкладено": len(fallback_words),
                    "не про фразу": astray,
                    "намірів": f"{entered} -> {len(intents)}",
                },
                split_note + kept_note,
                duration_ms=more_ms,
                decision="пошук окремо по кожному слову: нечітка видача під «ром "
                "горілка» приносить лише ром, і другий намір гостя зник би мовчки",
            )

        caught: list[str] = []
        for name in list(self.auto_intents):
            if any(
                intent not in self.auto_intents and same_kind(name, intent)
                for intent in intents
                if intent != name
            ):
                del self.auto_intents[name]
                if name in intents:
                    intents.remove(name)
                caught.append(name)
        if caught:
            self.ground.trace.add(
                "step-split-merge",
                "core.list",
                {"злито": caught, "намірів": len(intents)},
                f"слово гостя накрило автопотребу: {len(caught)} -- один рядок, не два",
                decision="один товар не їде двома рядками (#254)",
            )
        return intents

    async def exact(
        self,
        intents: Sequence[str],
        *,
        hints: Mapping[str, HistoryItem],
        slot: dict[str, Any],
        branch_id: str | None,
    ) -> int:
        spent_ms = 0
        exact_queries: list[str] = []
        for intent in intents:
            hint = hints.get(intent)
            if hint is None or hint.name == intent:
                continue
            known = {str(p["externalProductId"]) for p in self.candidates.get(intent, [])}
            if hint.lager_id not in known:
                exact_queries.append(hint.name)
        if exact_queries:
            more, more_ms = await search_products(
                self.ground.mcp, list(dict.fromkeys(exact_queries)), slot, branch_id
            )
            spent_ms = more_ms
            for intent in intents:
                hint = hints.get(intent)
                if hint is None or hint.name not in more:
                    continue
                known = {str(p["externalProductId"]) for p in self.candidates.get(intent, [])}
                extra = [p for p in more[hint.name] if str(p["externalProductId"]) not in known]
                if extra:
                    self.candidates[intent] = self.candidates.get(intent, []) + extra
        return spent_ms

    async def kind(
        self,
        intents: Sequence[str],
        *,
        slot: dict[str, Any],
        branch_id: str | None,
        chosen: Mapping[str, str],
    ) -> bool:
        if not branch_id:
            return False
        self.tree = await load_tree(self.ground.mcp, branch_id=branch_id)
        if self.tree is None:
            return False
        trace = self.ground.trace
        self.narrowed, kinds_ms = await narrow_kinds(
            self.ground.mcp,
            intents,
            slot=slot,
            branch_id=branch_id,
            tree=self.tree,
            chosen=chosen,
        )
        added, empty_kinds = merge_kinds(self.candidates, self.narrowed)
        emptied = strip_other_processing(self.candidates, self.narrowed)
        if emptied:
            trace.add(
                "step-kind",
                "core.dictionary",
                {"знято": len(emptied), "наміри": list(emptied)},
                f"вид порожній на цей слот, а знайдене — іншої обробки: {len(emptied)}",
                decision="інша обробка не видається за намір: чесніше сказати «не збирають»",
                tag="не збирають",
                tag_tone="warn",
            )
        if self.narrowed:
            trace.add(
                "step-kind",
                KIND_TOOL,
                {
                    "видів": len(self.narrowed),
                    "види": [
                        f"«{word}» → {kind.title}"
                        + (" — на цей слот не збирають" if kind.empty else "")
                        for word, kind in self.narrowed.items()
                    ],
                },
                f"звужено видом: {len(self.narrowed)}; кандидатів з видів: +{added}",
                duration_ms=kinds_ms,
                decision="вид з дерева тримає заміну в межах виду",
                tag=f"+{added}" if added else "порожньо",
                tag_tone="good" if added else "warn",
            )
        for word in empty_kinds:
            log.info("basket.kind_empty", word=word, slot=slot.get("start"))
        return True


__all__ = ["KIND_QUERY_TAKE", "KIND_TOOL", "SEARCH_TOOL", "Shelf"]
