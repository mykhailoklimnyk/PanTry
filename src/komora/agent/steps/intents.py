from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from time import monotonic
from typing import Any

from komora.agent.aisle import aisles_known
from komora.agent.basket import (
    MIN_RECEIPTS,
    NO_HISTORY_NOTE,
    PANTRY_MANUAL_WHY,
    POOL_WINDOW_DAYS,
    AssemblyError,
    HistoryItem,
    Naming,
    Tally,
    _kind_axis,
    _occasion_tag,
    apply_keeps,
    apply_sense,
    fill_pool,
    intent_keeps,
    intent_names,
    is_service_item,
    kind_key,
    manual_item,
    manual_key,
    norm_name,
    same_kind,
    stocked_manual,
    tracked_kinds,
)
from komora.agent.executor import Made
from komora.agent.occasion import OccasionPlan
from komora.agent.occasion import rework as rework_occasion
from komora.agent.sanity import intent_sense
from komora.agent.steps.ground import Ground
from komora.api.schemas import BuildRequest, Postponed
from komora.core import catalog
from komora.core.aisles import by_word_only
from komora.core.bar import DrinkKind, alcohol_word, said_group
from komora.core.ceilings import trip_gap, usual_basket_stats
from komora.core.cycles import Rhythm, Trust
from komora.core.occasion import BuildMode, Occasion
from komora.core.postponed import Remedy
from komora.core.promo import Habit
from komora.core.target import Stretched, stretch
from komora.core.target import band as budget_band
from komora.core.target import fill as fill_to_band
from komora.core.words import plural
from komora.db import catalog as catalog_store
from komora.logging import get_logger

log = get_logger(__name__)


class Compose:

    def __init__(
        self,
        ground: Ground,
        *,
        request: BuildRequest,
        occasion: Occasion,
        said: list[str],
        sizes: Sequence[int],
        marks: Mapping[str, datetime] | None = None,
        manual: Mapping[str, str] | None = None,
        wanted: Mapping[str, str] | None = None,
        usual: Decimal | None = None,
        drinks: Mapping[str, DrinkKind] | None = None,
    ) -> None:
        self.ground = ground
        self.request = request
        self.occasion = occasion
        self.said = said
        self.sizes = sizes
        self.marks = marks or {}
        self.manual = manual or {}
        self.wanted = wanted or {}
        self.usual = usual
        self.drinks: Mapping[str, DrinkKind] = drinks or {}
        self.budget: Decimal | None = (
            Decimal(str(request.budget)) if request.budget is not None else None
        )
        self.stretched: Stretched | None = None
        self.auto_intents: dict[str, HistoryItem] = {}
        self.beats: dict[str, Rhythm] = {}
        self.by_article: dict[str, HistoryItem] = {}
        self.fill_intents: dict[str, str] = {}
        self.fill_note: str | None = None
        self.intents: list[str] = []
        self.kept_articles: dict[str, str] = {}
        self.kinds: int = 0
        self.manual_intents: dict[str, str] = {}
        self.occasion_intents: dict[str, str] = {}
        self.bar_items: list[HistoryItem] = []
        self.postponed: list[tuple[Remedy, Postponed]] = []
        self.promo_due: dict[str, HistoryItem] = {}
        self.promo_intents: dict[str, Habit] = {}
        self.promo_kinds: int = 0
        self.rare: int = 0
        self.judged_rest: int = 0
        self.unjudged_rest: int = 0
        self.ripe_names: dict[str, Naming] = {}
        self.named_all: dict[str, Naming] = {}
        self.silent_intents: dict[str, str] = {}
        self.wanted_intents: dict[str, str] = {}

    async def compose(self, bound: Mapping[str, Any]) -> Made:
        llm, pool, moment, trace = (
            self.ground.llm,
            self.ground.pool,
            self.ground.moment,
            self.ground.trace,
        )
        request, occasion = self.request, self.occasion
        marks, manual, wanted = self.marks, self.manual, self.wanted
        sizes = self.sizes
        list_intents = self.said
        history: list[HistoryItem] = bound["history"]

        from_field = len(list_intents)
        by_article = {item.lager_id: item for item in history}
        kept_articles: dict[str, str] = {}
        unknown_keep: list[str] = []
        for article in dict.fromkeys(str(a) for a in request.keep):
            item = by_article.get(article)
            if item is None:
                unknown_keep.append(article)
                continue
            if any(norm_name(item.name) == norm_name(intent) for intent in list_intents):
                continue
            list_intents.append(item.name)
            kept_articles[item.name] = article

        ripe = [
            item
            for item in history
            if occasion.takes_cycles
            and item.receipts >= MIN_RECEIPTS
            and not is_service_item(item.name)
            and (beat := item.rhythm(moment)).cycle_days is not None
            and beat.days_since is not None
            and beat.days_since >= beat.cycle_days
        ]
        ripe_names: dict[str, Naming] = {}
        if llm is not None and ripe:
            warm = not self.request.cold
            probe = Tally()
            ripe_labels = [item.name for item in ripe]
            await intent_names(None, ripe_labels, pool=pool, tally=probe, use_cache=warm)
            to_ask = len(ripe_labels) - probe.named_cached
            if to_ask > 0:
                self.ground.trace.add(
                    "step-naming-ahead",
                    "model",
                    {"спитаю": to_ask, "з кешу": probe.named_cached},
                    f"називаю {to_ask} {plural(to_ask, 'вид', 'види', 'видів')} з чеків — "
                    "найдовший крок холодного акаунта",
                    tag_tone="muted",
                )
            ripe_names = await intent_names(llm, ripe_labels, pool=pool, use_cache=warm)
            labels = sorted({naming.label for naming in ripe_names.values()})
            keeps = await intent_keeps(llm, labels, pool=pool, use_cache=warm)
            apply_keeps(ripe, ripe_names, keeps)
            apply_sense(
                ripe, ripe_names, await intent_sense(llm, labels, pool=pool, use_cache=warm)
            )

        ripe_ids = {id(item) for item in ripe}
        rest = [
            item
            for item in history
            if id(item) not in ripe_ids
            and item.receipts >= MIN_RECEIPTS
            and not is_service_item(item.name)
        ]
        self.judged_rest = 0
        self.unjudged_rest = len(rest)
        if rest:
            known = await intent_names(None, [item.name for item in rest], pool=pool)
            self.judged_rest = len(known)
            self.unjudged_rest = len(rest) - len(known)
            if known:
                more = sorted({naming.label for naming in known.values()})
                apply_keeps(rest, known, await intent_keeps(None, more, pool=pool))
                apply_sense(rest, known, await intent_sense(None, more, pool=pool))

        manual_intents: dict[str, str] = {}
        if manual and occasion.takes_pantry:
            tracked_manual = 0
            stocked_manual_kinds = 0
            for label in manual.values():
                row = manual_item(label, history, now=moment, names=ripe_names, marks=marks or {})
                if row.source != "manual":
                    tracked_manual += 1
                    continue
                if stocked_manual(label, marks) is not None:
                    stocked_manual_kinds += 1
                    continue
                name = label.strip()
                if not norm_name(name) or any(same_kind(name, i) for i in list_intents):
                    continue
                list_intents.append(name)
                manual_intents[name] = PANTRY_MANUAL_WHY
            already_said = len(manual) - tracked_manual - stocked_manual_kinds - len(manual_intents)
            trace.add(
                "step-manual",
                "agent.pantry",
                {"дописано в комору": len(manual), "щойно куплено": stocked_manual_kinds},
                (
                    f"беру наміром {len(manual_intents)}"
                    + (f", комора вже веде {tracked_manual}" if tracked_manual else "")
                    + (f", щойно куплено {stocked_manual_kinds}" if stocked_manual_kinds else "")
                    + (f", уже в списку {already_said}" if already_said else "")
                    if manual_intents
                    else "нового немає: усе дописане комора вже веде з чеків"
                    if tracked_manual == len(manual)
                    else f"нового немає: {stocked_manual_kinds} щойно куплено зі списку"
                    if stocked_manual_kinds
                    else "нового немає: усе дописане вже назване в списку"
                ),
                decision="дописане руками — слово гостя, і воно не знімається під межу",
                tag=None if manual_intents else "нічого нового",
                tag_tone="muted",
            )

        wanted_intents: dict[str, str] = {}
        if wanted:
            for label in wanted.values():
                name = label.strip()
                if not norm_name(name) or any(same_kind(name, i) for i in list_intents):
                    continue
                list_intents.append(name)
                wanted_intents[name] = "ти поклав це в список на цю покупку"
            trace.add(
                "step-wanted",
                "agent.wanted",
                {"у списку на покупку": len(wanted)},
                (
                    f"беру наміром {len(wanted_intents)}"
                    + (
                        f", уже названо гостем {len(wanted) - len(wanted_intents)}"
                        if len(wanted) - len(wanted_intents)
                        else ""
                    )
                    if wanted_intents
                    else "нового немає: усе зі списку гість уже назвав сам"
                ),
                decision="список -- рішення гостя: під межу і під цикл він не знімається",
                tag=None if wanted_intents else "нічого нового",
                tag_tone="muted",
            )

        promo_intents: dict[str, Habit] = {}
        promo_due: dict[str, HistoryItem] = {}
        at_bar_kinds = 0
        promo_kinds = 0
        rest = [item.name for item in history if kind_key(item.name) not in ripe_names]
        known = (
            await intent_names(None, rest, pool=pool, use_cache=not self.request.cold)
            if rest
            else {}
        )
        named_all = {**known, **ripe_names}
        aisle_of = await aisles_known(
            sorted({naming.label for naming in named_all.values()}),
            pool=pool,
            use_cache=not self.request.cold,
        )
        spice_names = {
            item.name
            for item in history
            if (told := named_all.get(kind_key(item.name))) is not None
            and by_word_only(aisle_of.get(told.label))
        }
        spice_kinds = 0
        bar_names = {} if self.request.bar_in_week else named_all
        for item in history if occasion.takes_cycles else ():
            if item.receipts < MIN_RECEIPTS or is_service_item(item.name):
                continue
            if at_bar(bar_names, item.name, self.drinks, by_word=not self.request.bar_in_week):
                continue
            if item.name in spice_names:
                continue
            promo = item.promo
            if not promo.mostly:
                continue
            promo_kinds += 1
            beat = item.rhythm(moment)
            due_after = beat.cycle_days if beat.cycle_days is not None else beat.receipts_days
            if beat.days_since is None or due_after is None or beat.days_since < due_after:
                continue
            if any(same_kind(item.name, i) for i in list_intents):
                continue
            promo_due[item.name] = item
            promo_intents[item.name] = promo

        beats: dict[str, Rhythm] = {}
        needs: list[HistoryItem] = []
        rare = 0
        kinds = 0
        for item in history if occasion.takes_cycles else ():
            if item.receipts < MIN_RECEIPTS or is_service_item(item.name) or item.promo.mostly:
                continue
            if at_bar(bar_names, item.name, self.drinks, by_word=not self.request.bar_in_week):
                at_bar_kinds += 1
                continue
            if item.name in spice_names:
                spice_kinds += 1
                continue
            kinds += 1
            beat = item.rhythm(moment)
            if beat.cycle_days is None or beat.days_since is None:
                rare += 1
                continue
            if beat.days_since < beat.cycle_days:
                continue
            beats[item.lager_id] = beat
            needs.append(item)
        tracked_for_kinds = tracked_kinds(history)
        own_nodes: Mapping[str, frozenset[str]] | None = None
        if pool is not None:
            try:
                own_nodes = await catalog_store.load(
                    pool, sorted({item.lager_id for item in tracked_for_kinds})
                )
            except Exception as exc:
                log.warning("target.kinds_unavailable", error=str(exc)[:200])
        proven_kinds = (
            catalog.kind_keys(
                ((item.name, item.lager_id) for item in tracked_for_kinds),
                own_nodes,
                unknown_merges=False,
            )
            if own_nodes is not None
            else None
        )
        folded = 0
        folded_names: set[str] = set()
        seen_labels: set[str] = set()
        kept: list[HistoryItem] = []
        for item in sorted(needs, key=lambda i: (-i.recent_receipts, -i.receipts)):
            told = named_all.get(kind_key(item.name))
            label = (
                told.label.strip().lower()
                if told is not None
                else (proven_kinds.of.get(item.name) if proven_kinds is not None else None)
            )
            if label:
                if label in seen_labels:
                    folded += 1
                    folded_names.add(item.name)
                    continue
                seen_labels.add(label)
            kept.append(item)
        needs = kept
        needs.sort(
            key=lambda item: (
                beats[item.lager_id].trust is Trust.SILENT,
                beats[item.lager_id].trust is not Trust.SAID,
                -item.recent_receipts,
                -item.receipts,
            )
        )
        usual = usual_basket_stats(sizes)
        needs_limit = usual.limit
        auto_intents: dict[str, HistoryItem] = {}
        silent_intents: dict[str, str] = {}
        for item in needs[:needs_limit]:
            if any(same_kind(item.name, i) for i in list_intents):
                continue
            auto_intents[item.name] = item
            if beats[item.lager_id].trust is Trust.SILENT:
                silent_intents[item.name] = beats[item.lager_id].phrase()
        for name, item in promo_due.items():
            auto_intents[name] = item
        intents = list_intents + list(auto_intents)
        sources = "; ".join(
            part
            for part in (
                f"з поля: {from_field}" if from_field else "",
                f"зі списку на потім: {len(wanted_intents)}" if wanted_intents else "",
                f"дописане в комору: {len(manual_intents)}" if manual_intents else "",
                f"докинуте гостем: {len(kept_articles)}" if kept_articles else "",
                f"за циклами: {len(auto_intents)}"
                if occasion.takes_cycles
                else "цикли вимкнено: комора під цей режим не читається",
            )
            if part
        )
        trace.add(
            "step-mode",
            "core.occasion",
            {
                "режим": str(occasion.mode),
                "людей": occasion.people,
                "стиль": str(occasion.style) if occasion.style is not None else None,
            },
            f"{occasion.phrase()}: {sources}",
            decision=(
                occasion.task()
                or (
                    "тиждень: наміри з комори, циклів і списку, добір під суму"
                    if occasion.mode is BuildMode.WEEK
                    else "список: беру рівно те, що гість записав — ні циклів, ні добору"
                )
            ),
            tag=f"{len(intents)} намірів",
            tag_tone="muted",
        )
        beyond_ceiling = max(0, len(needs) - needs_limit)
        postponed = [
            (
                Remedy.REFILL,
                Postponed(
                    intent=item.name,
                    reason=(
                        "давно не брав"
                        if beats[item.lager_id].trust is Trust.SILENT
                        else "закінчилось"
                    )
                    + f", але не влізло в звичний розмір кошика ({needs_limit} поз.)",
                    estimate=item.typical_cost,
                    refillable=True,
                ),
            )
            for item in (needs[needs_limit:] if occasion.mode is not BuildMode.EVENT else ())
        ]
        postponed.extend(
            (
                Remedy.MANUAL,
                Postponed(
                    intent=article,
                    reason="докинуте не знайшлось у твоїй історії покупок — "
                    "додай його в кошик «Сільпо» руками",
                ),
            )
            for article in unknown_keep
        )
        said_kinds = sum(1 for item in history if item.guest_said)
        if auto_intents:
            by_cycle = len(auto_intents) - len(silent_intents) - len(promo_due)
            groups = ", ".join(
                part
                for part in (
                    f"{by_cycle} за циклом" if by_cycle > 0 else "",
                    f"{len(silent_intents)} давно не брав" if silent_intents else "",
                    f"{len(promo_due)} по акції поза стелею" if promo_due else "",
                )
                if part
            )
            held = {
                "ритм нерівний": rare,
                "у барі": at_bar_kinds,
                "лише за твоїм словом (спеції)": spice_kinds,
                "згорнуто в один рядок": folded,
                "не влізло в звичний кошик": beyond_ceiling,
                "ти сказав, що вже купив": said_kinds,
            }
            held_total = sum(held.values())
            trace.add(
                "step-needs",
                "core.cycles",
                {
                    "limit": needs_limit,
                    "due": len(needs),
                    "rare": rare,
                    "беру": list(auto_intents),
                    "не беру": {name: n for name, n in held.items() if n},
                    "як порахована стеля": usual.phrase(),
                },
                f"беру {len(auto_intents)} {plural(len(auto_intents), 'вид', 'види', 'видів')}"
                + (f": {groups}" if groups else "")
                + (
                    f"; ще {held_total} {plural(held_total, 'вид', 'види', 'видів')} не беру"
                    if held_total
                    else ""
                ),
                decision=f"скільки брати за раз — {needs_limit} "
                f"{plural(needs_limit, 'вид', 'види', 'видів')}: це твій звичний кошик "
                "з чеків, а не число з коду"
                + ("; акційне йде поза цією стелею" if promo_due else ""),
                tag=f"+{len(auto_intents)}" + (f" зі {len(needs)}" if beyond_ceiling else ""),
                tag_tone="warn" if beyond_ceiling else "good",
            )

        occasion_intents: dict[str, str] = {}
        plan = OccasionPlan()
        if occasion.named:
            habits = sorted(
                (
                    (item.name, item.receipts)
                    for item in history
                    if item.receipts >= MIN_RECEIPTS and not is_service_item(item.name)
                ),
                key=lambda pair: -pair[1],
            )
            self.bar_items = sorted(
                (item for item in history if at_bar(named_all, item.name, self.drinks)),
                key=lambda item: -item.receipts,
            )
            bar = sorted(
                (
                    (
                        named.label
                        if (named := named_all.get(kind_key(item.name))) is not None
                        else item.name,
                        item.receipts,
                    )
                    for item in history
                    if at_bar(named_all, item.name, self.drinks)
                ),
                key=lambda pair: -pair[1],
            )
            occasion_started = monotonic()
            failure = "модель не підключена" if llm is None else ""
            if llm is not None:
                try:
                    plan = await rework_occasion(
                        llm,
                        occasion,
                        intents=intents,
                        protected=list_intents,
                        habits=habits,
                        budget=self.budget,
                        usual=self.usual,
                        bar=bar,
                    )
                except Exception as exc:
                    log.warning("basket.occasion_failed", error=str(exc))
                    failure = str(exc)[:120]
            occasion_ms = round((monotonic() - occasion_started) * 1000)
            stretched = (
                stretch(self.budget, plan.target, why=plan.target_why, said=request.budget_said)
                if self.budget is not None
                else None
            )
            self.stretched = stretched
            if stretched is not None and stretched.refused is None:
                self.budget = stretched.target
            for change in plan.skipped:
                auto_intents.pop(change.intent, None)
            for change in plan.added:
                occasion_intents[change.intent] = change.why
            intents = [
                intent
                for intent in list_intents + list(auto_intents)
                if intent not in {change.intent for change in plan.skipped}
            ] + list(occasion_intents)
            trace.add(
                "step-occasion",
                "agent.occasion",
                {
                    "привід": str(occasion.mode),
                    "людей": occasion.people,
                    "бар гостя": [name for name, _ in bar],
                    **_stretch_args(stretched),
                },
                f"{occasion.phrase()}: "
                + (
                    f"привід не застосувався ({failure})"
                    if failure
                    else plan.note()
                    + (
                        f"; ще {plan.beyond_limit} назвав агент, але це вже другий кошик"
                        if plan.beyond_limit
                        else ""
                    )
                    + _stretch_note(stretched)
                ),
                duration_ms=occasion_ms,
                prompt=plan.prompt,
                decision=occasion.task() or None,
                tag=_occasion_tag(plan, failed=bool(failure)),
                tag_tone="warn" if failure else ("good" if plan.touched else "muted"),
            )

        fill_intents: dict[str, str] = {}
        fill_note: str | None = None
        if self.budget is not None and occasion.fills_target:
            edges = budget_band(self.budget)
            by_name = {item.name: item for item in tracked_kinds(history)}
            soon = trip_gap([moment.date() for item in history for moment in item.moments])
            have = sum(
                (
                    item.typical_cost or Decimal(0)
                    for name, item in auto_intents.items()
                    if name not in promo_intents
                ),
                Decimal(0),
            )
            own_kind_keys: catalog.KindKeys | None = (
                catalog.kind_keys(
                    ((item.name, item.lager_id) for item in tracked_for_kinds), own_nodes
                )
                if own_nodes is not None
                else None
            )
            reserve = fill_pool(
                history,
                moment=moment,
                soon=soon,
                skip={item.name for item in needs}
                | set(auto_intents)
                | set(occasion_intents)
                | {
                    item.name
                    for item in history
                    if at_bar(
                        bar_names, item.name, self.drinks, by_word=not self.request.bar_in_week
                    )
                }
                | spice_names
                | folded_names,
                said=list_intents,
                kinds=own_kind_keys,
            )
            bag = list(reserve.pool)
            promo_held = reserve.promo_held
            covered: set[str] = set()
            for intent in list(auto_intents) + list_intents + list(occasion_intents):
                covered |= (
                    own_kind_keys.covering(intent) if own_kind_keys else {catalog.kind_word(intent)}
                )
            filled = fill_to_band(have=have, band=edges, pool=bag, covered=covered)
            picked, added = filled.taken, filled.spent
            for candidate in picked:
                auto_intents[candidate.key] = by_name[candidate.key]
                fill_intents[candidate.key] = candidate.why
            if picked:
                intents = [
                    intent
                    for intent in list_intents + list(auto_intents)
                    if intent not in {change.intent for change in plan.skipped}
                ] + list(occasion_intents)
            short = edges.short_by(have + added)
            fill_note = filled.note() if short else None
            trace.add(
                "step-target",
                "core.target",
                {
                    "ціль": str(edges.target),
                    "пул": len(bag),
                    "поза вікном": reserve.stale,
                    "вікно, дн": POOL_WINDOW_DAYS,
                    "ключ виду": _kind_axis(own_kind_keys),
                    "наступний похід, дн": soon,
                    "решта пулу": filled.note() or None,
                    "суджено поза потребами": self.judged_rest,
                    "не питали (холодний кеш)": self.unjudged_rest,
                    "докинуто": [candidate.key for candidate in picked],
                },
                f"{edges.phrase()}; за циклом ~{have:.0f} грн"
                + (
                    f", докинув {len(picked)} поз. на ~{added:.0f}"
                    if picked
                    else ", коридор закривають самі потреби"
                    if not short
                    else ", докидати нема з чого"
                )
                + (f", бракує ~{short:.0f} грн" if short else "")
                + (f"; по акції не добираю {promo_held}" if promo_held else ""),
                decision="що саме брати наперед — рішення агента; підстава кожного "
                "рядка інша, і «закінчилось» на них не пишеться",
                tag=f"+{len(picked)} поз." if picked else ("недобір" if short else "у коридорі"),
                tag_tone="warn" if short else "good",
            )

        if not intents:
            raise AssemblyError(
                "у списку порожньо — напиши, що взяти, або перемкни режим на «на тиждень»"
                if not occasion.takes_cycles
                else f"під привід «{occasion.label}» з потреб тижня не лишилось нічого — "
                "напиши списком, що поставити на стіл"
                if occasion.named and plan.skipped
                else NO_HISTORY_NOTE
                if not history
                else "за циклами зараз нічого не закінчується"
                + (
                    f", а добрати під {self.budget:.0f} грн нема з чого"
                    if self.budget is not None and occasion.fills_target
                    else ""
                )
                + " — напиши, що потрібно, і я зберу"
            )

        self.auto_intents = auto_intents
        self.beats = beats
        self.by_article = by_article
        self.fill_intents = fill_intents
        self.fill_note = fill_note
        self.intents = intents
        self.kept_articles = kept_articles
        self.kinds = kinds
        self.manual_intents = manual_intents
        self.occasion_intents = occasion_intents
        self.postponed = postponed
        self.promo_due = promo_due
        self.promo_intents = promo_intents
        self.promo_kinds = promo_kinds
        self.rare = rare
        self.ripe_names = ripe_names
        self.named_all = named_all
        self.silent_intents = silent_intents
        self.wanted_intents = wanted_intents
        return Made(
            facts={"intents": intents},
            args={
                "з поля": from_field,
                "докинуте гостем": len(kept_articles),
                "дописане в комору": len(manual_intents),
                "зі списку на потім": len(wanted_intents),
                "за циклами": len(auto_intents),
                "під подію": len(occasion_intents),
                "добір під суму": len(fill_intents),
                "чекають акції": len(promo_intents),
                "відкладено стелею": len(postponed),
            },
            summary=f"список намірів закрито: {len(intents)}"
            + (f", з них {len(promo_intents)} чекають акції" if promo_intents else "")
            + (f", відкладено стелею {len(postponed)}" if postponed else ""),
            decision="джерела намірів вирішує РЕЖИМ, а не план: половина джерел "
            "означала б кошик, у якому мовчки немає сказаного гостем",
            tag=(
                f"{len(promo_intents)} чекають акції"
                if promo_intents
                else f"відкладено {len(postponed)}"
                if postponed
                else None
            ),
            tag_tone="muted",
        )


__all__ = ["Compose"]


def _stretch_args(stretched: Stretched | None) -> dict[str, Any]:
    if stretched is None:
        return {}
    said: dict[str, Any] = {
        "межа, грн": f"{stretched.named:.0f}",
        "агент пропонує, грн": f"{stretched.proposed:.0f}",
        "чому": stretched.why,
    }
    if stretched.refused:
        said["відмова"] = stretched.refused
    return said


def _stretch_note(stretched: Stretched | None) -> str:
    if stretched is None:
        return ""
    if stretched.refused:
        return f"; межу {stretched.proposed:.0f} грн від агента не взято"
    return f"; межа {stretched.named:.0f} -> {stretched.target:.0f} грн"


def at_bar(
    names: Mapping[str, Naming],
    name: str,
    drinks: Mapping[str, DrinkKind],
    *,
    by_word: bool = True,
) -> bool:
    told = names.get(kind_key(name))
    if told is None:
        return by_word and alcohol_word(name)
    return said_group(manual_key(told.label), told.drink, drinks)[0] is not None
