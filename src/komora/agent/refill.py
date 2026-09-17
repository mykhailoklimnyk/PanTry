from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from time import monotonic
from typing import Any

from komora.agent import skills as skill_texts
from komora.agent.basket import (
    GUEST_PICK,
    Assembled,
    PlanLine,
    Receipts,
    Tracer,
    _slicing_habit,
    agent_picks,
    build_lines,
    collapse_same_product,
    history_matches,
    load_history,
    narrow_by_query,
    norm_name,
    search_products,
    terms_from_slot,
    to_cart_line,
    weigh,
)
from komora.agent.cart import CartRun, plan_of, with_plan
from komora.agent.economics import ORDER_MIN, settle
from komora.agent.kinds import load_tree
from komora.agent.kinds import merge as merge_kinds
from komora.agent.kinds import narrow as narrow_kinds
from komora.agent.llm import Meter
from komora.api.schemas import Declined, RefillRequest, TraceStep
from komora.core import models, quota
from komora.core import skills as core_skills
from komora.core.slots import day_of, hours_until
from komora.core.words import plural
from komora.db import catalog as catalog_store
from komora.db.pool import DictPool
from komora.logging import get_logger
from komora.mcp.client import SilpoMCP

log = get_logger(__name__)


class RefillError(RuntimeError):
    """Добирати нема чого або нема куди — з людською причиною."""


def wanted_intents(plan: Assembled, request: RefillRequest) -> list[str]:
    said = [answer.intent.strip() for answer in request.answers if answer.intent.strip()]
    asked = [text for part in request.intents if (text := part.strip())]
    if asked or said:
        return list(dict.fromkeys([*asked, *said]))
    return [item.intent for item in plan.basket.postponed if item.refillable]


def missing_from(plan: Assembled, intents: list[str]) -> list[str]:
    have = {norm_name(line.intent) for line in plan.lines}
    have |= {norm_name(str(line.product.get("name") or "")) for line in plan.lines}
    have.discard("")
    return [
        intent
        for intent in intents
        if not any(known in norm_name(intent) or norm_name(intent) in known for known in have)
    ]


async def refill(
    mcp: SilpoMCP,
    llm: Any,
    run: Assembled | CartRun,
    request: RefillRequest,
    *,
    now: datetime | None = None,
    pool: DictPool | None = None,
    account: str = "",
    saved_chains: Mapping[str, tuple[str, ...]] | None = None,
    receipts: Receipts | None = None,
    trim_fill: bool = False,
    label: str | None = None,
    on_step: Callable[[TraceStep], None] | None = None,
) -> Assembled | CartRun:
    plan = plan_of(run)
    intents = missing_from(plan, wanted_intents(plan, request))
    if not intents:
        raise RefillError(
            "добирати нема чого: або стеля нічого не відклала, або назване вже в кошику"
        )

    remembered = receipts is not None and receipts.branch_id == plan.branch_id
    if receipts is not None and remembered:
        history, count, history_ms = receipts.history, receipts.count, 0
    else:
        history, count, history_ms, _, _ = await load_history(
            mcp, plan.slot, plan.branch_id, now=now, pool=pool, account=account
        )
    candidates, search_ms = await search_products(mcp, intents, plan.slot, plan.branch_id)

    said: dict[str, str] = {
        answer.intent: text for answer in request.answers if (text := (answer.text or "").strip())
    }
    chosen = {answer.intent: answer.slug for answer in request.answers if answer.slug}
    probed = {
        answer.intent: phrase
        for answer in request.answers
        if (phrase := (answer.query or "").strip()) and not answer.skip
    }
    kinds_ms: int | None = None
    if chosen and plan.branch_id:
        tree = await load_tree(mcp, branch_id=plan.branch_id)
        if tree is not None:
            narrowed, kinds_ms = await narrow_kinds(
                mcp,
                list(chosen),
                slot=plan.slot,
                branch_id=plan.branch_id,
                tree=tree,
                chosen=chosen,
            )
            merge_kinds(candidates, narrowed)
            said.update({word: kind.title for word, kind in narrowed.items() if word not in said})

    narrowed_by_query: list[str] = []
    probe_ms = 0
    if probed:
        narrowed_by_query, probe_ms = await narrow_by_query(
            mcp, candidates, probed, slot=plan.slot, branch_id=plan.branch_id
        )
        search_ms += probe_ms
        said.update({intent: phrase for intent, phrase in probed.items()})

    hints_all = {
        intent: matches for intent in intents if (matches := history_matches(intent, history))
    }
    kinds_map: dict[str, frozenset[str]] = {}
    catalog_ms: int | None = None
    if pool is not None:
        catalog_started = monotonic()
        wanted = {
            str(product["externalProductId"]) for found in candidates.values() for product in found
        } | {str(hint.lager_id) for found in hints_all.values() for hint in found}
        try:
            kinds_map = await catalog_store.load(pool, sorted(wanted))
        except Exception as exc:
            log.warning("refill.kinds_unreadable", error=str(exc))
        catalog_ms = round((monotonic() - catalog_started) * 1000)
    by_article = {item.lager_id: item for item in history}
    chosen_skills = core_skills.select(
        list(plan.rules),
        occasion_mode=str(plan.occasion.mode) if plan.occasion is not None else "",
        occasion_phrase=(
            plan.occasion.phrase() if plan.occasion is not None and plan.occasion.named else ""
        ),
        intents=intents,
        promo_kinds=sum(1 for item in history if item.promo.mostly),
        promo_on_shelf=any(
            product.get("oldPrice") and str(product["externalProductId"]) in by_article
            for found in candidates.values()
            for product in found
        ),
        shelf={
            intent: [str(product["name"]) for product in found]
            for intent, found in candidates.items()
        },
    )
    picks, model_used, agent_ms, agent_prompt = await _picks(
        llm,
        intents,
        candidates,
        hints_all,
        kinds_map,
        by_article,
        fast=request.fast,
        said=said,
        rules=list(plan.rules),
        skills=skill_texts.block(chosen_skills.skills),
    )

    built, unresolved, declined = build_lines(
        intents,
        candidates,
        {intent: matches[0] for intent, matches in hints_all.items()},
        picks,
        habits={intent: _slicing_habit(matches) for intent, matches in hints_all.items()},
        owned=by_article,
        saved_chains=saved_chains,
        answered=frozenset(chosen) | frozenset(probed),
        **guest_terms(plan, now),
    )
    unresolved = [intent for intent in unresolved if intent not in declined]
    known = {str(line.product["externalProductId"]) for line in plan.lines}
    added = [line for line in built if str(line.product["externalProductId"]) not in known]
    closed_by_answer = bool(built) and bool(request.answers)
    if not added and not closed_by_answer:
        if built:
            raise RefillError(
                "це вже в кошику: " + ", ".join(f"«{line.product['name']}»" for line in built)
            )
        if declined and not unresolved:
            raise RefillError(
                "агент не взяв: "
                + "; ".join(f"«{intent}» — {why}" for intent, why in declined.items())
            )
        log.info("refill.nothing_on_shelf", intents=list(unresolved))

    log.info("refill.added", lines=len(added), unresolved=len(unresolved), model=model_used)
    trace = Tracer(on_step=on_step)
    trace.steps = list(plan.basket.trace)
    trace.add(
        "step-refill-kinds",
        "catalog_nodes",
        {"артикулів": len(kinds_map)},
        f"вузол відомий у {len(kinds_map)} артикулів"
        if kinds_map
        else "карти видів немає: ярус вузла в доборі не спрацював",
        duration_ms=catalog_ms,
        decision="добір мусить судити тим самим, чим судила збірка -- інакше "
        "два кошики розходяться, і видно це лише поклавши їх поруч",
        tag=None if kinds_map else "ярус не спрацював",
        tag_tone="muted",
    )
    trace.add(
        "step-refill-history",
        "api.history" if remembered else "silpo_get_my_offline_orders",
        {"намірів": len(intents), "з пам'яті сесії": remembered},
        (
            f"{count} чеків з пам'яті сесії — правка не перечитує історію"
            if remembered
            else f"{count} чеків перечитано під добір — ціни й залишки з них свіжі"
        ),
        duration_ms=history_ms,
        decision=(
            "історію міняє чек раз на день, а не наш дотик: відкриття читає "
            "наново, правка бере прочитане (#245)"
            if remembered
            else "історія читається наново: план тримає рядки, а не чеки"
        ),
    )
    trace.add(
        "step-refill-search",
        "silpo_find_products_batch",
        {"queries": len(intents)},
        f"кандидатів: {sum(len(v) for v in candidates.values())} на {len(intents)} намірів",
        duration_ms=search_ms,
    )
    if request.answers:
        trace.add(
            "step-refill-answer",
            "silpo_get_products",
            {"відповідей": len(request.answers), "слова": dict(said)},
            (
                f"гість уточнив: {len(said)} " + plural(len(said), "намір", "наміри", "намірів")
                if said
                else "жодну відповідь не вдалось звузити вузлом — лишаюсь при пошуку"
            )
            + (
                f"; набір звужено фразою у {len(narrowed_by_query)} з {len(probed)}"
                if probed
                else ""
            ),
            duration_ms=(kinds_ms or 0) + probe_ms,
            decision="слова гостя важать більше за наш вибір виду, і перезбирати "
            "заради них увесь кошик не треба: бюджет і вагу рахує код",
            tag="уточнено" if said else "без вузла",
            tag_tone="good" if said else "muted",
        )
    if trim_fill and added:
        plan = replace(plan, fill_intents=(*plan.fill_intents, *(line.intent for line in added)))
    return _rebuilt(
        run,
        plan,
        trace,
        added=added,
        attempted=intents,
        trim=trim_fill,
        label=label,
        answered=[answer.intent for answer in request.answers],
        unresolved=unresolved,
        declined=declined,
        duration_ms=history_ms + search_ms + (kinds_ms or 0) + (catalog_ms or 0) + agent_ms,
        agent_ms=agent_ms,
        model=model_used,
        prompt=agent_prompt,
        spent=Meter.of(llm),
    )


async def _picks(
    llm: Any,
    intents: list[str],
    candidates: dict[str, list[dict[str, Any]]],
    hints_all: dict[str, list[Any]],
    kinds: Mapping[str, frozenset[str]] | None = None,
    owned: Mapping[str, Any] | None = None,
    *,
    fast: bool | None = None,
    said: Mapping[str, str] | None = None,
    rules: list[str] | None = None,
    skills: str = "",
) -> tuple[dict[str, dict[str, Any]], str, int, str]:
    decidable = [intent for intent in intents if candidates.get(intent)]
    if llm is None or not decidable:
        return {}, "без агента", 0, ""
    try:
        picks, _queue, model, agent_ms, _tokens, batched = await agent_picks(
            llm,
            decidable,
            candidates,
            hints_all,
            rules or [],
            kinds=kinds,
            owned=owned,
            answers=dict(said) if said else None,
            batches=models.batches_for(getattr(llm, "model", "") or "", fast=fast, fallback=1),
            skills=skills,
        )
    except Exception as exc:
        log.warning("refill.agent_failed", error=str(exc))
        return {}, "без агента", 0, ""
    return picks, model, agent_ms, batched.prompt


def _first_by_intent(items: list[Declined]) -> list[Declined]:
    seen: set[str] = set()
    kept: list[Declined] = []
    for item in items:
        if item.intent in seen:
            continue
        seen.add(item.intent)
        kept.append(item)
    return kept


def _rebuilt(
    run: Assembled | CartRun,
    plan: Assembled,
    trace: Tracer,
    *,
    added: list[PlanLine],
    attempted: list[str],
    unresolved: list[str],
    declined: Mapping[str, str] | None = None,
    answered: list[str] | None = None,
    replaced: frozenset[str] = frozenset(),
    trim: bool = False,
    label: str | None = None,
    duration_ms: int,
    agent_ms: int,
    model: str,
    prompt: str = "",
    spent: Meter,
) -> Assembled | CartRun:
    lines: list[PlanLine] = [
        *(line for line in plan.lines if str(line.product["externalProductId"]) not in replaced),
        *added,
    ]
    merged = collapse_same_product(lines)
    merged_names = [f"{name} ({count})" for name, count in merged]
    terms = terms_from_slot(plan.slot)
    snapshot = run.snapshot if isinstance(run, CartRun) else None
    blockers = [code for code in (snapshot.blockers if snapshot else []) if code != ORDER_MIN]
    money = settle(lines, terms, blockers=blockers)
    trimmed_fill: list[str] = []
    if (answered or trim) and plan.basket.budget is not None:
        high = Decimal(str(plan.basket.budget))
        ours = sorted(
            (line for line in lines if line.intent in plan.fill_intents),
            key=lambda line: plan.fill_intents.index(line.intent),
            reverse=True,
        )
        for line in ours:
            if money.total <= high:
                break
            lines.remove(line)
            trimmed_fill.append(line.intent)
            money = settle(lines, terms, blockers=blockers)
    cost = sum((line.total for line in added), Decimal(0))
    was = sum(
        (line.total for line in plan.lines if str(line.product["externalProductId"]) in replaced),
        Decimal(0),
    )
    saved = was - cost

    trace.add(
        "step-refill" if not replaced else "step-cheaper",
        model,
        (
            {"додано": len(added), "товари": [line.product["name"] for line in added]}
            if not replaced
            else {"замінено": len(replaced), "товари": [line.product["name"] for line in added]}
        )
        | {"не знайшлось": list(unresolved), "знято під межу": trimmed_fill, "злито": merged_names},
        (
            f"{label}: "
            if label
            else "дешевше того ж виду: "
            if replaced
            else "відповідь гостя: "
            if answered
            else "добір: "
        )
        + f"{len(added)} {plural(len(added), 'позиція', 'позиції', 'позицій')}"
        + (f"; не знайшлось: {len(unresolved)}" if unresolved else "")
        + (f"; під межу знято наш добір: {len(trimmed_fill)}" if trimmed_fill else ""),
        duration_ms=agent_ms,
        prompt=prompt,
        decision=(
            (
                f"замінено на дешевше: {was} -> {cost} грн"
                + (f", економія {saved} грн; " if saved > 0 else "; ")
                if replaced
                else f"з відповіді гостя {len(added)} поз. на {cost} грн; "
                + (f"під межу знято наш добір: {', '.join(trimmed_fill)}; " if trimmed_fill else "")
                if answered
                else f"докинуто {len(added)} поз. на {cost} грн; "
                + (f"під межу знято: {', '.join(trimmed_fill)}; " if trimmed_fill else "")
            )
            + f"разом {money.total} грн, доставка {money.cost} грн"
        ),
        tag=f"+{len(added)} поз." if not replaced else f"-{saved} грн" if saved > 0 else "замінено",
        tag_tone="good",
    )

    taken = {norm_name(intent) for intent in attempted}
    basket = plan.basket.model_copy(
        update={
            "lines": [to_cart_line(line) for line in lines],
            "total": money.total,
            "base_total": money.discounted,
            "delivery_cost": money.cost,
            "total_weight_kg": weigh(lines).kg,
            "top_up": money.top_up,
            "blockers": money.blockers,
            "trace": trace.steps,
            "postponed": [
                item
                for item in plan.basket.postponed
                if norm_name(item.intent) not in taken and item.intent not in unresolved
            ],
            "questions": [
                question
                for question in plan.basket.questions
                if norm_name(question.intent) not in {norm_name(i) for i in (answered or [])}
            ],
            "unresolved": list(dict.fromkeys([*plan.basket.unresolved, *unresolved])),
            "declined": _first_by_intent(
                [
                    *plan.basket.declined,
                    *(Declined(intent=intent, why=why) for intent, why in (declined or {}).items()),
                ]
            ),
            "stats": plan.basket.stats.model_copy(
                update={
                    "duration_ms": plan.basket.stats.duration_ms + duration_ms,
                    "tokens_in": plan.basket.stats.tokens_in + spent.input_tokens,
                    "tokens_out": plan.basket.stats.tokens_out + spent.output_tokens,
                    "tokens_cached": plan.basket.stats.tokens_cached + spent.cached_tokens,
                    "cost_usd": plan.basket.stats.cost_usd
                    + (
                        quota.cost_of(spent.model, spent.input_tokens, spent.output_tokens)
                        or Decimal(0)
                    ),
                    "mcp_calls": sum(1 for step in trace.steps if step.tool.startswith("silpo_")),
                }
            ),
        }
    )
    return with_plan(
        run,
        replace(
            plan,
            basket=basket,
            lines=lines,
            unresolved=[*plan.unresolved, *unresolved],
        ),
    )


__all__ = ["RefillError", "guest_terms", "missing_from", "refill", "wanted_intents"]


def guest_terms(plan: Assembled, now: datetime | None = None) -> dict[str, Any]:
    moment = now or datetime.now(UTC)
    return {
        "auto_swap": plan.auto_swap,
        "auto_swap_percent": plan.auto_swap_percent,
        "hours_to_slot": hours_until(plan.slot.get("start"), now=moment),
        "slot_day": day_of(plan.slot.get("start"), now=moment),
    }


def take_cheaper(
    run: Assembled | CartRun, *, article: str, to: str, now: datetime | None = None
) -> Assembled | CartRun:
    started = monotonic()
    plan = plan_of(run)
    line = next(
        (item for item in plan.lines if str(item.product["externalProductId"]) == article),
        None,
    )
    if line is None:
        raise RefillError("цього рядка вже немає в кошику — онови сторінку")
    card = plan.swap_cards.get(to)
    if card is None:
        raise RefillError("цей варіант уже не в пам'яті сервера — збери кошик заново")
    if any(str(item.product["externalProductId"]) == to for item in plan.lines):
        raise RefillError(f"«{card['name']}» уже в кошику")

    built, _, _ = build_lines(
        [line.intent],
        {line.intent: [card]},
        {},
        {line.intent: {"chosen_id": to, "qty": float(line.qty), "why": GUEST_PICK}},
        owned={},
        **guest_terms(plan, now),
    )
    if not built:
        raise RefillError("не вдалось скласти рядок із цього товару")

    trace = Tracer()
    trace.steps = list(plan.basket.trace)
    return _rebuilt(
        run,
        plan,
        trace,
        added=built,
        attempted=[],
        unresolved=[],
        replaced=frozenset({article}),
        duration_ms=int((monotonic() - started) * 1000),
        agent_ms=0,
        model="без агента",
        spent=Meter(),
    )


async def pick_answer(
    run: Assembled | CartRun, *, intent: str, article: str, now: datetime | None = None
) -> Assembled | CartRun:
    started = monotonic()
    plan = plan_of(run)
    card = plan.swap_cards.get(article)
    if card is None:
        raise RefillError("цей варіант уже не в пам'яті сервера — збери кошик заново")
    known = {str(line.product["externalProductId"]) for line in plan.lines}
    if article in known:
        trace = Tracer()
        trace.steps = list(plan.basket.trace)
        return _rebuilt(
            run,
            plan,
            trace,
            added=[],
            attempted=[intent],
            answered=[intent],
            unresolved=[],
            duration_ms=int((monotonic() - started) * 1000),
            agent_ms=0,
            model="без агента",
            spent=Meter(),
        )

    built, _, _ = build_lines(
        [intent],
        {intent: [card]},
        {},
        {intent: {"chosen_id": article, "qty": 1, "why": GUEST_PICK}},
        owned={},
        **guest_terms(plan, now),
    )
    if not built:
        raise RefillError("не вдалось скласти рядок із цього товару")

    trace = Tracer()
    trace.steps = list(plan.basket.trace)
    return _rebuilt(
        run,
        plan,
        trace,
        added=built,
        attempted=[intent],
        answered=[intent],
        unresolved=[],
        duration_ms=int((monotonic() - started) * 1000),
        agent_ms=0,
        model="без агента",
        spent=Meter(),
    )
