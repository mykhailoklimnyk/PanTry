from __future__ import annotations

import asyncio
import json
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Collection, Iterable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from functools import partial
from hashlib import sha256
from pathlib import Path
from time import monotonic
from typing import Any, Literal
from zoneinfo import ZoneInfo

from komora.agent import skills as skill_texts
from komora.agent.aisle import intent_aisles
from komora.agent.clarify import Asked
from komora.agent.clarify import options_for as clarify_options
from komora.agent.economics import settle
from komora.agent.executor import Executor
from komora.agent.kinds import Kind
from komora.agent.llm import Decision, Meter
from komora.agent.occasion import OccasionPlan
from komora.agent.place import resolve as resolve_place
from komora.agent.plan import describe_tools, plan_batch, plan_run
from komora.agent.prompts import register as register_prompt
from komora.agent.prompts import stamp as prompt_stamp
from komora.agent.sanity import NORM_UNITS, intent_sense
from komora.agent.spine import Turn, spin
from komora.agent.twins import ask_twins
from komora.agent.understand import understand as understand_task
from komora.api.schemas import (
    AgentTarget,
    Basket,
    BuildRequest,
    CartLine,
    Cheaper,
    Clarification,
    ClarifyOption,
    ClarifyPick,
    Declined,
    DeliveryOption,
    Pantry,
    PantryAdjustment,
    PantryAisle,
    PantryItem,
    PantryLink,
    PantryMandate,
    PantryPart,
    Postponed,
    PriceFork,
    Reason,
    RunStats,
    SlotWindow,
    SpendTarget,
    Substitute,
    SwapDecision,
    SwapOption,
    TraceOption,
    TraceQuestion,
    TraceStep,
    Trimmed,
    TwinsDropped,
)
from komora.config import Settings
from komora.config import settings as _default_settings
from komora.core import batching, brands, catalog, homoglyphs, labels, quota, slicing
from komora.core import labels as label_bones
from komora.core import models as core_models
from komora.core import skills as core_skills
from komora.core.aisles import Aisled, aisles
from komora.core.ambiguity import MAX_OPTIONS, MAX_QUESTIONS, Option
from komora.core.bar import DrinkKind, said_group
from komora.core.brands import carried_by
from komora.core.brands import words as brand_words
from komora.core.ceilings import (
    DEFAULT_NEEDS,
    Usual,
    max_qty,
    trip_gap,
    usual_basket_stats,
    usual_order,
)
from komora.core.cheaper import better as better_price
from komora.core.cycles import Keeps, Rhythm, Trust, coverage_note, intervals_days, rhythm
from komora.core.cycles import median as cycles_median
from komora.core.delivery import CostTier, DeliveryTerms
from komora.core.facts import Facts
from komora.core.feedback import collector_swaps, reach_note
from komora.core.goal import basket_goal, resolution_goal
from komora.core.leftover import WHOLE, leftover
from komora.core.levels import Folded, Level, Seen, fold, fresh_links, own_chain, parts
from komora.core.links import product_url
from komora.core.location import HOME_DELIVERY, Location, source_note
from komora.core.location import Source as BranchSource
from komora.core.mandate import Fork, build_comment, price_fork, price_fork_comment
from komora.core.marks import bought_now, stocked_at
from komora.core.occasion import BuildMode, Occasion, occasion_of
from komora.core.orders import Stage, stage_of
from komora.core.packaging import (
    RECEIPT_GRAM_UNITS,
    is_sold_by_weight,
    parse_pack_weight,
    price_per_100g,
    quantize_to_step,
    receipt_unit,
    sale_step,
    sale_unit,
)
from komora.core.pantry import manual_id, regrouped
from komora.core.plan import CORE_AFTER_PLAN, Aim, Plan, facts_of, validate
from komora.core.plan import describe as describe_plan
from komora.core.plan import report as plan_report
from komora.core.postponed import Remedy, in_fix_order
from komora.core.promo import Habit, Purchase, on_sale, purchase_of, regular_of, sale_phrase
from komora.core.promo import habit as promo_habit
from komora.core.prompt import prune
from komora.core.queries import bound_at, dedupe, head, kind_words
from komora.core.said import BAR, SOURCE_MANUAL, Said
from komora.core.shelf_life import required_until, shelf_life_phrase
from komora.core.shortlist import cheapest as shortlist_cheapest
from komora.core.shortlist import shortlist
from komora.core.silence import Silence, is_mute, mute_note
from komora.core.slots import REASON_WEIGHT_MAX, day_of, hours_until, window_note
from komora.core.spine import Halt
from komora.core.substitution import (
    SHELF_TURNOVER_HOURS,
    Alternative,
    Source,
    covers,
    is_risky,
    price_within,
    rank_chain,
)
from komora.core.target import Candidate, Reach, Stretched
from komora.core.target import band as budget_band
from komora.core.target import next_cut as next_budget_cut
from komora.core.target import overshoot as overshoot_ways
from komora.core.target import reach as reach_of_pool
from komora.core.target import spare_cut as spare_budget_cut
from komora.core.target import supply_rank as supply_rank_of
from komora.core.trace import SUMMARY_CHARS, fits
from komora.core.traits import sees_a_fraction
from komora.core.understanding import (
    ANSWER_WAIT_S,
    PLAN_GATED,
    Understanding,
)
from komora.core.weight import (
    GRAMS_IN_KG,
    Estimate,
    WeighedLine,
    cart_weight,
    over_limit,
    split_by_weight,
    unit_weight_kg,
)
from komora.core.words import plural
from komora.db import catalog as catalog_store
from komora.db import categories as categories_store
from komora.db import facts as facts_store
from komora.db import intents as intents_store
from komora.db import receipts as receipts_store
from komora.db import swaps as saved_swaps
from komora.db.pool import DictPool
from komora.logging import get_logger
from komora.mcp.client import SEARCH_TOOL, MCPCallError, SilpoMCP, TokenRejected

log = get_logger(__name__)

BEFORE_PLAN = (
    "place.address",
    "place.delivery_types",
    "place.cart",
    "place.decide",
    "slot.list",
    "slot.pick",
    "history.receipts",
    "history.orders",
    "history.model",
)

MAX_HISTORY_PAGES = 20

HISTORY_PAGE = 10

RECENT_DAYS = 90
BAR_ASK_INTENT = "напої до столу"
BAR_ASK_TAKE = 4

NEEDS_APPROVAL_NOTE = "потребує погодження заміни"

PANTRY_STILL_HAVE_RATIO = 0.6

_HISTORY_EPOCH = "2015-01-01T00:00:00+00:00"

REASON_CODES = (
    "звичне",
    "акція",
    "дешевше",
    "під_намір",
    "правило",
    "строк",
    "єдине",
)

AGENT_PICK = "агент"
PRICE_PICK = "ціна"
HEAD_PICK = "видача"
GUEST_PICK = "обрав ти"
OWN_PICK = "своє_свіже"
OWN_DECLINE = "своє_замість_відмови"
OWN_PROMO = "своє_замість_акції"
LOOP_PICK = "петля"

BASKET_TURNS = 2

ADDRESSED_LOOP = frozenset({"decide.pick", "decide.loop"})

NO_DECLINE_WHY = "агент не назвав причини"

_PICK_PICKS = {
    "type": "array",
    "salvage": True,
    "items": {
        "type": "object",
        "properties": {
            "intent": {"type": "string"},
            "chosen_id": {"type": "string"},
            "qty": {"type": "number"},
            "why": {
                "type": ["string", "null"],
                "enum": [*REASON_CODES, None],
            },
            "swap": {"type": ["string", "null"]},
            "ask": {"type": ["string", "null"]},
            "ask_options": {
                "type": ["array", "null"],
                "items": {"type": "string"},
            },
        },
        "required": ["intent", "chosen_id", "qty"],
        "additionalProperties": False,
    },
}

_PICK_QUEUE = {
    "type": ["array", "null"],
    "items": {
        "type": "object",
        "properties": {
            "intent": {"type": "string"},
            "why": {"type": "string"},
        },
        "required": ["intent", "why"],
        "additionalProperties": False,
    },
}


def pick_schema(*, with_queue: bool) -> dict[str, Any]:
    properties: dict[str, Any] = {"picks": _PICK_PICKS}
    if with_queue:
        properties["expendable"] = _PICK_QUEUE
    return {
        "type": "object",
        "properties": properties,
        "required": ["picks"],
        "additionalProperties": False,
    }


QUEUE_RULE = (
    "Поле «межа_кошика» — скільки гривень гість дав на ЦЕЙ кошик. "
    "Суму рахувати НЕ треба і зайвого не знімай: "
    "скільки саме зняти, порахує код. Від тебе — «expendable»: ЧЕРГА на "
    "зняття, від найлегшої втрати до найважчої, кожен запис {intent, why}. "
    "У черзі лише позиції, у яких «джерело» — «потреби з циклів» або "
    "«привід»: назване гостем не знімається ніколи, навіть коли кошик через "
    "це виходить за межу. Черга не має йти хвостом списку: попереду те, без чого тиждень "
    "працює, — рідке й разове раніше за звичне щотижневе. "
)

LABEL_RULE = (
    " Поле «intent» у відповіді — це РІВНО «ключ» наміру, скопійований "
    "дослівно, а не його назва словами. Ключ не вигадуй і не скорочуй: "
    "якого немає в запиті, того немає."
)

_PICK_HEAD = (
    "Ти агент продуктового кошика «Комора». Гість назвав наміри (види товарів), "
    "а ти обираєш під кожен намір КОНКРЕТНИЙ товар з кандидатів. Правила гостя "
    "(поле «правила_гостя») — ОБОВ'ЯЗКОВІ обмеження вибору, вони важать більше "
    "за історію і ціну. Далі: звичне з історії гостя важить більше за ціну; "
    "без історії — найдоречніший під намір товар з наявних (не найдешевший і "
    "не випадковий; розчинна кава під намір «кава» — лише якщо гість так "
    "купує). Історичний збіг, ШИРШИЙ за намір, — не звичне: якщо гість сказав "
    "«огірки», то «огірки солоні» чи «огірки мариновані» з історії — інший "
    "товар; без уточнення гостя обирай базовий/свіжий варіант. Поле "
    "«оброблене» називає ознаки обробки: слова з назви і НАЗВИ ІНШИХ ВИДІВ, у "
    "яких товар теж лежить («М'ясо для шашлику та барбекю» — смажити вдома, "
    "«Другі страви» — уже готове). Якщо намір не просить такого виду, бери "
    "кандидата БЕЗ поля «оброблене»: «свинина» це сире м'ясо, а не шашлик. "
    "А коли «уточнення_гостя» називає сире чи необроблене, кандидат з полем "
    "«оброблене» не підходить узагалі: краще лиши chosen_id порожнім, ніж "
    "поклади сало під «свинина». "
    "Якщо жоден кандидат не того ВИДУ, що намір (курячий рулет проти "
    "рибного), лиши chosen_id порожнім і не питай: спільне перше слово "
    "видом не робить. "
    "ПОРОЖНІХ ПОЛІВ У ЗАПИТІ НЕМАЄ: поля з порожнім значенням просто немає в "
    "об'єкті — немає поля, немає ознаки. При РІВНІЙ "
    "відповідності наміру перевага акційному (є «стара_ціна») — і постав "
    "код «акція»; але акція НЕ перебиває звичний бренд гостя. Ціни "
    "порівнюй полем «за_100г» — воно вже зведене до спільної одиниці; «ціна» "
    "у різних фасовках непорівнянна. Поле «прочитання» показує ІНШІ види, на "
    "які лягає те саме слово («сир» — і «Сири», і «Сир кисломолочний»). Якщо "
    "прочитання справді різні наміри, історії гостя немає і його правила "
    "мовчать — постав питання: «ask» — одне коротке речення гостю, і тоді "
    "chosen_id лиши порожнім рядком. «ask_options» — 2-4 короткі фрази, "
    "якими можна ШУКАТИ товар і які відповідають саме на це питання "
    "(«свинина лопатка», «сир твердий»), а не повторюють слово гостя. "
    "Не питай, коли вибір очевидний, коли є "
    "звичне з історії або коли намір гостя ВЖЕ називає вид («шашлик», «сир "
    "кисломолочний»): прочитання уточнює лише те, чого гість не сказав. "
    "Питання — це пауза в збірці. Поле «уточнення_гостя» "
    "означає, що він УЖЕ відповів: це рішення, не підказка — не питай удруге "
    "і не бери всупереч. Кількість — звична з історії, інакше 1; більше 24 не "
    "буває. Поле «привід» (порожньо — звичайний тиждень) міняє саме "
    "кількість і доречність: «що_означає_привід» каже, чого від тебе чекає "
    "гість. Механічно множити на кількість людей не треба — хліба до гостей "
    "треба більше, а пральний порошок не змінюється взагалі. "
)

_PICK_TAIL = (
    "Слово гостя буває ВУЖЧИМ за вид — бренд, сорт або смак («Спрайт», "
    "«Пепсі Макс», «фісташкове»). Впізнаєш його по кандидатах: таке слово "
    "стоїть УСЕРЕДИНІ назви, а не її головою («Напій Sprite» — вид «напій», "
    "звуження «Sprite»). Тоді бери саме назване: інший бренд чи інший смак — "
    "це ІНШИЙ товар, а не заміна, і економніша альтернатива тут теж не "
    "потрібна, бо гість уже вирішив. Вісь «swap» для такого рядка пише, "
    "наскільки відходити МОЖНА і що заміною НЕ є: «інший лимон-лайм "
    "газований 0,5 л, колу не брати». "
    "Причина — одне коротке речення. "
    "Поле «swap» заповнюй ЗАВЖДИ, для КОЖНОЇ позиції. Це ВІСЬ ЗАМІНИ для "
    "збирача: чим можна закрити цю позицію, "
    "якщо її не буде на полиці. Пиши те, що людина біля полиці може "
    "перевірити очима: «інший цільнозерновий пшеничний, 400 г», «інша "
    "негазована вода 1,5 л», «інший сухий корм для котів з кроликом, 85 г». "
    "НЕ пиши «інша марка» і «той самий товар іншого виробника»: для хліба "
    "марка ні до чого, важать вид і вага. Ціну не називай — вилку додасть "
    "код. Причину НЕ пиши словами: постав у поле «why» рівно один код з "
    "переліку (звичне, акція, дешевше, під_намір, правило, строк, єдине). "
    "Речення про причину складе код із власних чисел. Якщо ставиш питання "
    "гостю — «why» лишай порожнім. "
    "Відповідай ВИКЛЮЧНО українською. "
    "chosen_id — САМЕ артикул кандидата, без префіксів."
)

register_prompt("pick.head", _PICK_HEAD)
register_prompt("pick.label", LABEL_RULE)
register_prompt("pick.queue", QUEUE_RULE)
register_prompt("pick.tail", _PICK_TAIL)


def pick_system(*, with_queue: bool, skills: str = "") -> str:
    return _PICK_HEAD + LABEL_RULE + (QUEUE_RULE if with_queue else "") + _PICK_TAIL + skills


KIND_SCHEMA = {
    "type": "object",
    "properties": {
        "kinds": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "intent": {"type": "string"},
                    "subtype": {"type": ["string", "null"]},
                    "drink": {
                        "type": ["string", "null"],
                        "enum": [*[str(group) for group in DrinkKind], None],
                    },
                },
                "required": ["name", "intent", "subtype", "drink"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["kinds"],
    "additionalProperties": False,
}

KIND_SYSTEM = (
    "Ти ведеш домашню комору. Для кожної назви товару з чека («name» лишай "
    "як прийшла) назви ВИД — те, як про нього думає гість, а не етикетку. "
    "«intent»: коротка загальна назва українською, без бренду, фасовки і "
    "сорту: «вода газована», «філе куряче», «морозиво», «томати», «яблука». "
    "Той самий продукт різних брендів чи з іншим порядком слів мусить "
    "отримати ОДНАКОВИЙ intent. «subtype»: уточнення, яке реально міняє "
    "вибір (солодка, безлактозне, житній, дитячий) — або null. Бренд і "
    "розмір упаковки — НЕ підтип. «drink»: якщо це АЛКОГОЛЬНИЙ напій — "
    "«strong» (горілка, віскі, коньяк, ром, джин, текіла, лікер, настоянка), "
    "«wine» (вино, шампанське, ігристе, вермут) або «light» (пиво, сидр, "
    "слабоалкогольні коктейлі). Усе інше, зокрема безалкогольне пиво й вино, "
    "— null."
)

register_prompt("naming", KIND_SYSTEM)


class AssemblyError(RuntimeError):
    ...


DELIVERY_TYPES: tuple[tuple[str, str, str], ...] = (
    ("DeliveryHome", "кур'єр", "слот 2 години"),
    ("SelfPickup", "самовивіз", "своя або будь-яка філія"),
    ("DeliveryExpressByPromise", "експрес", "близько години"),
    ("LongDelivery", "без поспіху", "слот 3–4 години"),
    ("NovaPoshta", "Нова пошта", "1–3 дні · без швидкопсувного · тариф НП"),
)

_HACKATHON_DISABLED = {
    "NovaPoshta": "потрібен вибір відділення НП — цього в продукті ще немає",
}

_LOKO_OPTION = DeliveryOption(
    id="loko",
    label="LOKO",
    note="15–30 хвилин · доставка за циклом",
    cost=Decimal(0),
    available=False,
    unavailable_reason="LOKO в офіційному API ще немає — ідея в роадмапі",
)

_DEMO_DELIVERY_IDS = {
    "courier": "DeliveryHome",
    "pickup": "SelfPickup",
    "novaposhta": "NovaPoshta",
    "express": "DeliveryHome",
}


def delivery_type_for(request_delivery: str) -> str:
    return _DEMO_DELIVERY_IDS.get(request_delivery, request_delivery or "DeliveryHome")


SLOT_LOOKAHEAD = 20


def slots_query(
    branch_id: str | None, delivery_type: str, limit: int, *, since: datetime
) -> dict[str, Any]:
    if since.tzinfo is None:
        raise ValueError(
            "slots_query: `since` без часового поясу — вікно слотів мусить "
            "бути в абсолютному часі, інакше воно з'їде мовчки"
        )
    return {
        "branchId": branch_id,
        "deliveryTypes": [delivery_type],
        "limit": limit,
        "start": since.replace(microsecond=0).isoformat(),
    }


def slots_note(fallback: str, slots: list[dict[str, Any]], *, now: datetime) -> str:
    free = [one for one in slots if one.get("available")]
    if not free:
        return fallback
    first = window_note(free[0].get("start"), free[0].get("end"), now=now)
    count = plural(len(free), "вільний слот", "вільні слоти", "вільних слотів")
    return f"{len(free)} {count} · найближчий {first}"


def option_from_slots(
    type_id: str, label: str, note: str, slots: list[dict[str, Any]], *, now: datetime
) -> DeliveryOption:
    note = slots_note(note, slots, now=now)
    available = next((s for s in slots if s.get("available")), None)
    sample = available or (slots[0] if slots else None)
    if sample is None:
        return DeliveryOption(
            id=type_id,
            label=label,
            note=note,
            cost=Decimal(0),
            available=False,
            unavailable_reason="слотів немає взагалі",
        )
    tiers = sample.get("deliveryCostMap") or []
    top_tier = max(
        (Decimal(str(t["fromOrderCost"])) for t in tiers),
        default=None,
    )
    return DeliveryOption(
        id=type_id,
        label=label,
        note=note,
        cost=Decimal(str(sample.get("deliveryCost") or 0)),
        min_order=(Decimal(str(sample["minOrderCost"])) if sample.get("minOrderCost") else None),
        threshold=top_tier,
        max_weight_kg=(Decimal(str(sample["maxWeight"])) if sample.get("maxWeight") else None),
        service_fee=(Decimal(str(sample["serviceFee"])) if sample.get("serviceFee") else None),
        available=available is not None,
        unavailable_reason=None if available is not None else "немає вільних слотів",
    )


def kind_key(name: str) -> str:
    parts = norm_name(name).split()
    if len(parts) < 3:
        return " ".join(parts[:2])
    taken, i = [parts[0]], 1
    while (step := bound_at(parts, i)) and i + step < len(parts):
        taken.extend(parts[i : i + step])
        i += step
    taken.append(parts[i])
    return " ".join(taken)


def kind_label(name: str, names: Mapping[str, Naming] | None) -> str:
    mapped = names.get(kind_key(name)) if names else None
    return mapped.label if mapped else name


def ask_kind(intent: str, names: Mapping[str, Naming] | None) -> str:
    naming = (names or {}).get(kind_key(intent))
    return naming.intent if naming is not None else kind_key(intent)


@dataclass(frozen=True, slots=True)
class Naming:

    intent: str
    subtype: str | None = None
    drink: DrinkKind | None = None
    drink_known: bool = False

    @property
    def label(self) -> str:
        return f"{self.intent}{LABEL_MARK}{self.subtype}" if self.subtype else self.intent


INTENT_CACHE_MAX = 4096

_INTENT_CACHE: OrderedDict[str, Naming] = OrderedDict()


def _cache_names(named: Mapping[str, Naming]) -> None:
    for name, naming in named.items():
        _INTENT_CACHE[name] = naming
        _INTENT_CACHE.move_to_end(name)
    while len(_INTENT_CACHE) > INTENT_CACHE_MAX:
        _INTENT_CACHE.popitem(last=False)


def _cached_name(name: str) -> Naming | None:
    naming = _INTENT_CACHE.get(name)
    if naming is not None:
        _INTENT_CACHE.move_to_end(name)
    return naming


def forget_intents() -> None:
    _INTENT_CACHE.clear()


async def _ask_names(llm: Any, part: list[str]) -> list[dict[str, Any]]:
    decision = await llm.decide(
        system=KIND_SYSTEM,
        user=json.dumps({"назви": part}, ensure_ascii=False),
        schema=KIND_SCHEMA,
        prompt=prompt_stamp("naming", KIND_SYSTEM),
        max_tokens=max(4096, NAMING_TOKENS_PER_NAME * len(part)),
        temperature=0.0,
    )
    return list(decision.data.get("kinds", []))


async def intent_names(
    llm: Any,
    names: list[str],
    *,
    pool: DictPool | None = None,
    need_drink: bool = False,
    tally: Tally | None = None,
    use_cache: bool = True,
    memory: bool | None = None,
    batches: int = 1,
) -> dict[str, Naming]:
    read_memory = use_cache if memory is None else memory
    fresh = [name for name in names if _unnamed(name, need_drink)] if read_memory else list(names)
    asked_now: dict[str, Naming] = {}
    stored: dict[str, Naming] = {}
    if fresh and pool is not None and use_cache:
        try:
            known = await intents_store.load(pool, fresh)
        except Exception as exc:
            log.warning("pantry.intents.cache_unreadable", error=str(exc))
        else:
            stored = {name: _from_row(row) for name, row in known.items()}
            _cache_names(stored)
            fresh = [name for name in fresh if _unnamed(name, need_drink)]
    if tally is not None:
        tally.named_cached = len(names) - len(fresh)
        tally.named_asked = len(fresh) if llm is not None else 0
    if fresh and llm is not None:
        try:
            parts = [[fresh[index] for index in group] for group in batching.split(fresh, batches)]
            answers = await asyncio.gather(
                *(_ask_names(llm, part) for part in parts), return_exceptions=True
            )
            named: dict[str, Naming] = {}
            lost: list[str] = []
            relabeled: list[str] = []
            broke: list[BaseException] = []
            rows: list[tuple[dict[str, str], dict[str, Any]]] = []
            for part, answer in zip(parts, answers, strict=True):
                if isinstance(answer, BaseException):
                    broke.append(answer)
                    continue
                asked = {intents_store.fingerprint(name): name for name in part}
                rows.extend((asked, row) for row in answer)
            if broke and not rows:
                raise broke[0]
            for one in broke:
                log.warning("pantry.intents.batch_failed", error=str(one))
            for asked, row in rows:
                intent = " ".join(str(row.get("intent", "")).split())
                if not intent:
                    continue
                echo = str(row.get("name", ""))
                original = asked.get(intents_store.fingerprint(echo))
                if original is None:
                    lost.append(intents_store.fingerprint(echo)[:12])
                    continue
                subtype_raw = row.get("subtype")
                subtype = " ".join(str(subtype_raw).split()) if subtype_raw else None
                kept = stored.get(original)
                if kept is not None and kept.intent:
                    if kept.intent != intent or kept.subtype != subtype:
                        relabeled.append(intents_store.fingerprint(original)[:12])
                    intent, subtype = kept.intent, kept.subtype
                named[original] = Naming(
                    intent=intent,
                    subtype=subtype,
                    drink=_drink_group(row.get("drink")),
                    drink_known=True,
                )
            if relabeled:
                log.info(
                    "naming.label_kept",
                    kept=len(relabeled),
                    asked=len(fresh),
                    names=relabeled[:5],
                )
            if lost:
                log.warning(
                    "naming.echo_mismatch",
                    lost=len(lost),
                    asked=len(fresh),
                    batches=len(parts),
                    echoes=lost[:5],
                )
            asked_now = named
            _cache_names(named)
            if pool is not None and named and use_cache:
                try:
                    await intents_store.save(
                        pool,
                        {
                            name: (naming.intent, naming.subtype, _drink_word(naming))
                            for name, naming in named.items()
                        },
                    )
                except Exception as exc:
                    log.warning("pantry.intents.cache_unwritable", error=str(exc))
        except Exception as exc:
            log.warning("pantry.intents.failed", error=str(exc))
    if not use_cache:
        if read_memory:
            return {
                kind_key(name): naming
                for name in names
                if (naming := asked_now.get(name) or _cached_name(name)) is not None
            }
        return {kind_key(name): naming for name, naming in asked_now.items()}
    return {kind_key(name): naming for name in names if (naming := _cached_name(name)) is not None}


NOT_A_DRINK = "none"


def _unnamed(name: str, need_drink: bool) -> bool:
    naming = _cached_name(name)
    if naming is None:
        return True
    return need_drink and not naming.drink_known


def _from_row(row: tuple[str, str | None, str | None]) -> Naming:
    intent, subtype, drink = row
    return Naming(
        intent=intent,
        subtype=subtype,
        drink=_drink_group(drink),
        drink_known=drink is not None,
    )


def _drink_word(naming: Naming) -> str | None:
    return str(naming.drink) if naming.drink else NOT_A_DRINK


def _drink_group(raw: Any) -> DrinkKind | None:
    try:
        return DrinkKind(str(raw))
    except ValueError:
        return None


KEEPS_SCHEMA = {
    "type": "object",
    "properties": {
        "kinds": {
            "type": "array",
            "salvage": True,
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "keeps": {
                        "type": "string",
                        "enum": [str(tier) for tier in Keeps],
                    },
                },
                "required": ["label", "keeps"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["kinds"],
    "additionalProperties": False,
}

KEEPS_SYSTEM = (
    "Ти ведеш домашню комору. Для кожної мітки виду («label» лишай як "
    "прийшла) скажи, скільки ОДНА покупка може пролежати вдома, поки не "
    "зіпсується. Це властивість самого продукту, а не того, як швидко його "
    "з'їдають: «keeps» — «дні» (псується за кілька днів: хліб, молоко, "
    "зелень, свіже м'ясо, готова їжа), «тижні» (лежить до місяця: тверді "
    "сири, яйця, коренеплоди, йогурти), «місяці» (лежить до року: крупи, "
    "консерви, заморожене, побутова хімія, косметика), «роки» (практично не "
    "псується: сіль, цукор, спеції, приправи, засоби для прибирання). Якщо "
    "вагаєшся між двома ярусами — бери ДОВШИЙ: це стеля, і зайве вето гірше "
    "за пропущене."
)

register_prompt("keeps", KEEPS_SYSTEM)

KEEPS_TOKENS_PER_LABEL = 40

_KEEPS_CACHE: dict[str, Keeps] = {}


def forget_keeps() -> None:
    _KEEPS_CACHE.clear()


def naming_candidates(kinds: Sequence[HistoryItem], listed: Iterable[str]) -> list[str]:
    return [kind.name for kind in kinds if kind.receipts >= MIN_RECEIPTS] + [
        label.strip() for label in listed if label.strip()
    ]


def naming_labels(names: Mapping[str, Naming]) -> list[str]:
    return sorted({naming.label for naming in names.values()})


async def _ask_keeps(llm: Any, part: Sequence[str]) -> list[dict[str, Any]]:
    decision = await llm.decide(
        system=KEEPS_SYSTEM,
        user=json.dumps({"види": list(part)}, ensure_ascii=False),
        schema=KEEPS_SCHEMA,
        schema_name="keeps",
        prompt=prompt_stamp("keeps", KEEPS_SYSTEM),
        max_tokens=max(2048, KEEPS_TOKENS_PER_LABEL * len(part)),
        temperature=0.0,
    )
    return list(decision.data.get("kinds", []))


async def intent_keeps(
    llm: Any,
    labels: Sequence[str],
    *,
    pool: DictPool | None = None,
    use_cache: bool = True,
    memory: bool | None = None,
    batches: int = 1,
) -> dict[str, Keeps]:
    read_memory = use_cache if memory is None else memory
    fresh = [label for label in labels if label and (not read_memory or label not in _KEEPS_CACHE)]
    asked_now: dict[str, Keeps] = {}
    if fresh and pool is not None and use_cache:
        try:
            known = await facts_store.load(pool, fresh)
        except Exception as exc:
            log.warning("pantry.keeps.cache_unreadable", error=str(exc))
        else:
            _KEEPS_CACHE.update(
                {label: tier for label, row in known.items() if (tier := _keeps_tier(row.keeps))}
            )
            fresh = [label for label in fresh if label not in _KEEPS_CACHE]
    if fresh and llm is not None:
        try:
            parts = [[fresh[index] for index in group] for group in batching.split(fresh, batches)]
            answers = await asyncio.gather(
                *(_ask_keeps(llm, part) for part in parts), return_exceptions=True
            )
            rows: list[tuple[str, dict[str, Any]]] = []
            broke: list[BaseException] = []
            for part, answer in zip(parts, answers, strict=True):
                if isinstance(answer, BaseException):
                    broke.append(answer)
                    continue
                bones = label_bones.by_skeleton(part)
                rows.extend(
                    (label_bones.echoed(str(row.get("label", "")), bones) or "", row)
                    for row in answer
                )
            if broke and not rows:
                raise broke[0]
            for one in broke:
                log.warning("pantry.keeps.batch_failed", error=str(one))
            asked = {facts_store.fingerprint(label): label for label in fresh}
            got: dict[str, Keeps] = {}
            lost: list[str] = []
            drifted = 0
            for by_bones, row in rows:
                tier = _keeps_tier(row.get("keeps"))
                if tier is None:
                    continue
                echo = str(row.get("label", ""))
                original = asked.get(facts_store.fingerprint(echo))
                if original is None:
                    original = by_bones or None
                    if original is not None:
                        drifted += 1
                if original is None:
                    lost.append(facts_store.fingerprint(echo)[:12])
                    continue
                got[original] = tier
            if drifted:
                log.info("keeps.echo_drifted", drifted=drifted, asked=len(fresh))
            if lost:
                log.warning("keeps.echo_mismatch", lost=len(lost), asked=len(fresh))
            asked_now = got
            _KEEPS_CACHE.update(got)
            if pool is not None and got and use_cache:
                try:
                    await facts_store.save(
                        pool,
                        {label: facts_store.Facts(keeps=str(tier)) for label, tier in got.items()},
                    )
                except Exception as exc:
                    log.warning("pantry.keeps.cache_unwritable", error=str(exc))
        except Exception as exc:
            log.warning("pantry.keeps.failed", error=str(exc))
    if not use_cache:
        if read_memory:
            return {
                label: tier
                for label in labels
                if (tier := asked_now.get(label) or _KEEPS_CACHE.get(label)) is not None
            }
        return dict(asked_now)
    return {label: _KEEPS_CACHE[label] for label in labels if label in _KEEPS_CACHE}


def _keeps_tier(raw: Any) -> Keeps | None:
    try:
        return Keeps(str(raw))
    except ValueError:
        return None


def apply_keeps(
    history: list[HistoryItem],
    names: Mapping[str, Naming],
    keeps: Mapping[str, Keeps],
) -> list[HistoryItem]:
    for item in history:
        naming = names.get(kind_key(item.name))
        item.keeps = keeps.get(naming.label) if naming is not None else None
    return history


def apply_sense(
    history: list[HistoryItem],
    names: Mapping[str, Naming],
    sense: Mapping[str, Any],
) -> list[HistoryItem]:
    for item in history:
        naming = names.get(kind_key(item.name))
        judged = sense.get(naming.label) if naming is not None else None
        if judged is None:
            item.rhythm_lies = False
            continue
        item.rhythm_lies = bool(judged.rhythm_lies) or sees_a_fraction(
            judged.per_day,
            bought_per_day=_bought_per_day(item, unit=judged.per_day_unit),
        )
    return history


def _bought_per_day(item: HistoryItem, *, unit: str | None) -> Decimal | None:
    if unit not in NORM_UNITS:
        return None
    gaps = intervals_days(sorted({moment.date() for moment in item.moments}))
    if not gaps:
        return None
    middle = cycles_median(gaps)
    usual = item.usual_amount[0]
    if middle <= 0 or usual <= 0:
        return None
    amount = Decimal(str(usual))
    if unit == "г":
        pack = parse_pack_weight(item.unit) or parse_pack_weight(item.name)
        if pack is None or pack <= 0:
            return None
        amount *= pack
    return amount / Decimal(str(middle))


def _seen(item: HistoryItem, now: datetime) -> Seen:
    last = max(item.moments) if item.moments else None
    return Seen(
        label=item.name,
        unit=receipt_unit(item.unit),
        receipts=item.receipts,
        days_since=(now - last).days if last is not None else None,
        article=item.lager_id,
    )


def history_kinds(
    history: list[HistoryItem],
    aliases: dict[str, str] | None = None,
    *,
    now: datetime | None = None,
) -> list[HistoryItem]:
    merged: dict[str, HistoryItem] = {}
    moment = now or datetime.now(UTC)
    for item in history:
        key = kind_key(item.name)
        if aliases:
            key = aliases.get(key, key)
        target = merged.get(key)
        if target is None:
            merged[key] = HistoryItem(
                lager_id=item.lager_id,
                name=item.name,
                unit=item.unit,
                receipts=item.receipts,
                qty_total=item.qty_total,
                recent_receipts=item.recent_receipts,
                qty_recent=item.qty_recent,
                moments=list(item.moments),
                image=item.image,
                marked_at=item.marked_at,
                said_cycle=item.said_cycle,
                said_from=item.said_from,
                online_last=item.online_last,
                online_qtys=list(item.online_qtys),
                price=item.price,
                price_at=item.price_at,
                keeps=item.keeps,
                rhythm_lies=item.rhythm_lies,
                purchases=list(item.purchases),
                sources=[_seen(item, moment)],
            )
            continue
        if item.moments and (not target.moments or max(item.moments) > max(target.moments)):
            target.name = item.name
            target.unit = item.unit
            target.lager_id = item.lager_id
            if item.image:
                target.image = item.image
        target.receipts += item.receipts
        target.qty_total += item.qty_total
        target.recent_receipts += item.recent_receipts
        target.qty_recent += item.qty_recent
        target.moments.extend(item.moments)
        target.purchases.extend(item.purchases)
        target.sources.append(_seen(item, moment))
        target.online_qtys.extend(item.online_qtys)
        if item.online_last is not None and (
            target.online_last is None or item.online_last > target.online_last
        ):
            target.online_last = item.online_last
        if item.price is not None and (
            target.price is None
            or target.price_at is None
            or (item.price_at is not None and item.price_at >= target.price_at)
        ):
            target.price = item.price
            target.price_at = item.price_at
        if item.marked_at is not None and (
            target.marked_at is None or item.marked_at > target.marked_at
        ):
            target.marked_at = item.marked_at
        if item.said_cycle is not None:
            shorter = target.said_cycle is None or item.said_cycle < target.said_cycle
            own = target.said_cycle == item.said_cycle and item.said_from is None
            if shorter or own:
                target.said_cycle = item.said_cycle
                target.said_from = item.said_from
    return list(merged.values())


def apply_marks(history: list[HistoryItem], marks: Mapping[str, datetime]) -> list[HistoryItem]:
    if not marks and not any(item.marked_at is not None for item in history):
        return history
    for item in history:
        item.marked_at = marks.get(kind_key(item.name))
    return history


def apply_cycles(
    history: list[HistoryItem],
    cycles: Mapping[str, int],
    sources: Mapping[str, str] | None = None,
) -> list[HistoryItem]:
    if not cycles and not any(item.said_cycle is not None for item in history):
        return history
    said_from = sources or {}
    for item in history:
        item.said_cycle = cycles.get(kind_key(item.name))
        item.said_from = said_from.get(kind_key(item.name))
    return history


def receipts_pantry(
    history: list[HistoryItem],
    *,
    now: datetime | None = None,
    limit: int | None = None,
    names: dict[str, Naming] | None = None,
    sense: Mapping[str, Any] | None = None,
) -> list[PantryItem]:
    moment = now or datetime.now(UTC)
    aliases = {key: naming.label for key, naming in names.items()} if names else None
    kinds = history_kinds(
        [item for item in history if not is_service_item(item.name)],
        aliases=aliases,
        now=moment,
    )
    scored: list[tuple[bool, int, PantryItem]] = []
    for item in kinds:
        row = kind_row(item, moment=moment, names=names, sense=sense)
        if row is None:
            continue
        scored.append((row.running_out, item.recent_receipts * 100 + item.receipts, row))
    scored.sort(key=lambda row: (not row[0], -row[1]))
    rows = [row[2] for row in scored]
    return rows[:limit] if limit is not None else rows


def _sense_of(
    item: HistoryItem,
    beat: Rhythm,
    names: dict[str, Naming] | None,
    sense: Mapping[str, Any] | None,
) -> tuple[str | None, bool]:
    mapped = names.get(kind_key(item.name)) if names else None
    judged = sense.get(mapped.label) if (sense and mapped is not None) else None
    said = getattr(judged, "sanity", None) if judged is not None else None
    ask = beat.trust is Trust.NOT_RHYTHM and not beat.beyond_keeps
    return (said or None), ask


LONG_SILENCE = 10


ONLINE_HABIT_MIN = 2


ARRIVED_DAYS = 2


def arrived_note(item: HistoryItem, since: int | None) -> str | None:
    if since is None or since > ARRIVED_DAYS or item.online_last is None or not item.moments:
        return None
    if max(item.moments) != item.online_last:
        return None
    if since == 0:
        return "приїхало сьогодні"
    if since == 1:
        return "приїхало вчора"
    return f"приїхало {since} дн тому"


def kind_row(
    item: HistoryItem,
    *,
    moment: datetime,
    names: dict[str, Naming] | None = None,
    sense: Mapping[str, Any] | None = None,
) -> PantryItem | None:
    if item.receipts < MIN_RECEIPTS:
        return None
    beat = item.rhythm(moment)
    since = beat.days_since
    arrived = arrived_note(item, since)
    if since is None:
        return None
    unit = receipt_unit(item.unit)
    sanity, ask = _sense_of(item, beat, names, sense)
    if beat.cycle_days is None:
        mapped = names.get(kind_key(item.name)) if names else None
        return PantryItem(
            id=item.lager_id,
            label=kind_label(item.name, names),
            named=mapped is not None,
            group=mapped.intent if mapped else None,
            image_url=item.image,
            qty=None,
            usual_qty=item.usual_amount[0],
            unit=unit,
            state=(
                beat.phrase()
                if beat.trust in (Trust.ELSEWHERE, Trust.NOT_RHYTHM)
                else f"оцінка: {beat.phrase()}"
            ),
            sanity=sanity,
            keeps=str(item.keeps) if item.keeps else None,
            trust=beat.trust,
            ask=ask,
            left_ratio=None,
            days_left=None,
            cycle_days=None,
            cycle_said=False,
            running_out=False,
            promo=item.promo.phrase() or None,
            arrived=arrived,
            usual=None,
            source="receipts",
            parts=_row_parts(item),
        )
    cycle = beat.cycle_days
    usual, step = item.usual_amount
    left = leftover(cycle_days=cycle, days_since=since, typical_qty=usual, smallest=step)
    running_out = left.running_out
    named = beat.trust is Trust.SAID
    if item.guest_said:
        if since == 0:
            said = "взято сьогодні"
        elif left.qty is not None:
            said = f"удома ~{_amount_text(left.qty)} {unit}".rstrip()
        else:
            said = "це вже є"
        cycle_text = "запас понад цикл" if left.days_left > cycle else "цикл"
        state = f"{said} · {cycle_text} ~{cycle} дн"
    elif named:
        state = (
            f"~{cycle} дн · як у «{item.said_from}» · брав {since} дн тому"
            if item.said_from
            else f"вистачає на ~{cycle} дн · брав {since} дн тому"
        )
    elif beat.trust is Trust.SILENT:
        state = f"оцінка: {beat.phrase()}"
    else:
        state = f"оцінка: брав {since} дн тому · цикл ~{cycle} дн"
    if running_out and beat.trust is not Trust.SILENT:
        stale = (
            since is not None and cycle is not None and cycle > 0 and since > LONG_SILENCE * cycle
        )
        state += " — закінчилось" if stale else " — мабуть, закінчилось"
    mapped = names.get(kind_key(item.name)) if names else None
    return PantryItem(
        id=item.lager_id,
        label=kind_label(item.name, names),
        named=mapped is not None,
        group=mapped.intent if mapped else None,
        image_url=item.image,
        qty=left.qty,
        usual_qty=usual,
        unit=unit,
        state=state,
        sanity=sanity,
        keeps=str(item.keeps) if item.keeps else None,
        trust=beat.trust,
        ask=ask,
        left_ratio=left.left_ratio,
        days_left=left.days_left,
        cycle_days=cycle,
        cycle_said=named,
        running_out=running_out,
        promo=item.promo.phrase() or None,
        arrived=arrived,
        usual=None,
        source="receipts",
        parts=_row_parts(item),
    )


def _row_parts(item: HistoryItem) -> list[PantryPart]:
    return [
        PantryPart(
            label=part.label,
            unit=part.unit,
            receipts=part.receipts,
            days_since=part.days_since,
            fresh=part.fresh,
        )
        for part in parts(item.sources, recent_days=RECENT_DAYS)
    ]


def _bought_phrase(stocked: datetime, now: datetime | None) -> str:
    days = ((now or datetime.now(UTC)) - stocked).days
    return "купив сьогодні зі списку" if days <= 0 else f"купив {days} дн тому зі списку"


def stocked_manual(label: str, marks: Mapping[str, datetime] | None) -> datetime | None:
    return (marks or {}).get(manual_key(label))


def manual_item(
    label: str,
    history: list[HistoryItem],
    *,
    now: datetime | None = None,
    names: dict[str, Naming] | None = None,
    marks: Mapping[str, datetime] | None = None,
) -> PantryItem:
    name = label.strip()
    stocked = stocked_manual(name, marks)
    aliases = {key: naming.label for key, naming in names.items()} if names else None
    kinds = history_kinds(
        [item for item in history if not is_service_item(item.name)],
        aliases=aliases,
        now=now,
    )
    match = _alias_match(name, kinds, aliases) or (_history_match(name, kinds) if name else None)
    if match is None:
        return PantryItem(
            id=manual_id(kind_key(name)),
            label=name,
            unit="",
            state=(
                f"{_bought_phrase(stocked, now)} · у чеках «Сільпо» такого ще немає "
                f"— цикл рахується з {MIN_RECEIPTS} покупок"
                if stocked is not None
                else "додано вручну · у чеках «Сільпо» такого немає — беру в наступний кошик"
            ),
            source="manual",
        )
    row = kind_row(match, moment=now or datetime.now(UTC), names=names)
    if row is not None:
        return row
    return PantryItem(
        id=manual_id(kind_key(name)),
        label=name,
        unit=receipt_unit(match.unit),
        image_url=match.image,
        state=(
            f"{_bought_phrase(stocked, now)} · у чеках це {match.name}, "
            f"брав {match.receipts} — цикл рахується з {MIN_RECEIPTS}"
            if stocked is not None
            else (
                f"додано вручну · у чеках це {match.name}, "
                f"брав {match.receipts} — цикл рахується з {MIN_RECEIPTS}, "
                "беру в наступний кошик"
            )
        ),
        source="manual",
    )


def same_kind(one: str, other: str) -> bool:
    left, right = norm_name(one), norm_name(other)
    if not left or not right:
        return False
    return left in right or right in left


LABEL_MARK = " · "


def manual_key(label: str) -> str:
    return kind_key(label.replace(LABEL_MARK, " ").strip())


@dataclass(slots=True)
class Tally:

    stored_papers: int = 0

    named_cached: int = 0

    named_asked: int = 0


@dataclass(slots=True)
class Receipts:

    slot: dict[str, Any]
    branch_id: str | None
    history: list[HistoryItem]
    count: int
    sizes: tuple[int, ...] = ()
    online: Online = field(default_factory=lambda: Online(0))

    @property
    def orders(self) -> int:
        return self.online.count

    def detached(self) -> Receipts:
        return replace(self, history=[replace(item) for item in self.history])


@dataclass(frozen=True, slots=True)
class Online:

    count: int
    paid: tuple[Decimal, ...] = ()


async def read_receipts(
    mcp: SilpoMCP,
    *,
    settings: Settings | None = None,
    place: Location | None = None,
    now: datetime | None = None,
    pool: DictPool | None = None,
    account: str = "",
    tally: Tally | None = None,
) -> Receipts:
    cfg = settings if settings is not None else _default_settings
    moment = now or datetime.now(UTC)
    where = place if place is not None else await resolve_place(mcp, settings=cfg)
    branch_id = where.branch_for(HOME_DELIVERY) or cfg.branch_id
    outcome = await mcp.call(
        "silpo_get_time_slots",
        slots_query(branch_id, HOME_DELIVERY, 5, since=moment),
    )
    slots = outcome.payload_raw.get("slots") or []
    slot = next((s for s in slots if s.get("available")), slots[0] if slots else None)
    if slot is None:
        raise AssemblyError("немає жодного слота — без нього історія чеків не читається")
    history, count, _, sizes, online = await load_history(
        mcp, slot, branch_id, now=moment, pool=pool, account=account, tally=tally
    )
    return Receipts(
        slot=slot,
        branch_id=branch_id,
        history=history,
        count=count,
        sizes=tuple(sizes),
        online=online,
    )


async def resolve_kind(
    mcp: SilpoMCP,
    ident: str,
    *,
    settings: Settings | None = None,
    place: Location | None = None,
    marks: Mapping[str, datetime] | None = None,
    cycles: Mapping[str, int] | None = None,
    now: datetime | None = None,
    receipts: Receipts | None = None,
    pool: DictPool | None = None,
    account: str = "",
) -> HistoryItem:
    moment = now or datetime.now(UTC)
    read = receipts or await read_receipts(
        mcp, settings=settings, place=place, now=moment, pool=pool, account=account
    )
    history = read.history
    apply_marks(history, marks or {})
    apply_cycles(history, cycles or {})
    kinds = history_kinds([item for item in history if not is_service_item(item.name)])
    row = next((item for item in kinds if item.lager_id == str(ident)), None)
    if row is None:
        raise AssemblyError("цього виду немає в твоїх чеках — тут нема чого поправляти")
    return row


async def name_cycle(
    mcp: SilpoMCP,
    adjustment: PantryAdjustment,
    *,
    settings: Settings | None = None,
    place: Location | None = None,
    marks: Mapping[str, datetime] | None = None,
    cycles: Mapping[str, int] | None = None,
    now: datetime | None = None,
    receipts: Receipts | None = None,
) -> tuple[str, int | None]:
    row = await resolve_kind(
        mcp,
        str(adjustment.id),
        settings=settings,
        place=place,
        marks=marks,
        cycles=cycles,
        now=now,
        receipts=receipts,
    )
    if adjustment.action == "forget_cycle":
        return kind_key(row.name), None
    if adjustment.days < 1:
        raise AssemblyError("скажи, на скільки днів вистачає — числом від одного")
    return kind_key(row.name), adjustment.days


async def name_kind(
    mcp: SilpoMCP,
    adjustment: PantryAdjustment,
    *,
    settings: Settings | None = None,
    place: Location | None = None,
    marks: Mapping[str, datetime] | None = None,
    cycles: Mapping[str, int] | None = None,
    now: datetime | None = None,
    receipts: Receipts | None = None,
) -> str:
    row = await resolve_kind(
        mcp,
        str(adjustment.id),
        settings=settings,
        place=place,
        marks=marks,
        cycles=cycles,
        now=now,
        receipts=receipts,
    )
    return kind_key(row.name)


async def name_mandate(
    mcp: SilpoMCP,
    adjustment: PantryAdjustment,
    *,
    settings: Settings | None = None,
    place: Location | None = None,
    marks: Mapping[str, datetime] | None = None,
    cycles: Mapping[str, int] | None = None,
    now: datetime | None = None,
    receipts: Receipts | None = None,
) -> tuple[str, saved_swaps.Saved]:
    row = await resolve_kind(
        mcp,
        str(adjustment.id),
        settings=settings,
        place=place,
        marks=marks,
        cycles=cycles,
        now=now,
        receipts=receipts,
    )
    own = {
        one.article: one
        for one in own_chain(row.sources, head=row.lager_id, recent_days=RECENT_DAYS)
    }
    picked = [own[article] for article in adjustment.chain if article in own]
    if not picked or len(picked) != len(adjustment.chain):
        raise AssemblyError(
            "у цьому мандаті є товар, якого немає серед твоїх свіжих покупок цього виду"
        )
    return kind_key(row.name), saved_swaps.Saved(
        row.name, tuple(saved_swaps.Link(one.article, one.label) for one in picked)
    )


async def mark_pantry(
    mcp: SilpoMCP,
    adjustment: PantryAdjustment,
    *,
    settings: Settings | None = None,
    place: Location | None = None,
    marks: Mapping[str, datetime] | None = None,
    cycles: Mapping[str, int] | None = None,
    now: datetime | None = None,
    receipts: Receipts | None = None,
) -> dict[str, datetime]:
    moment = now or datetime.now(UTC)
    row = await resolve_kind(
        mcp,
        str(adjustment.id),
        settings=settings,
        place=place,
        marks=marks,
        cycles=cycles,
        now=moment,
        receipts=receipts,
    )
    cycle = row.cycle_days()
    if cycle is None:
        raise AssemblyError(
            "цей вид ти береш нерівно — циклу для нього ще немає. "
            "Скажи, на скільки тобі його вистачає, і я почну рахувати"
        )
    if adjustment.action == "bought":
        return {kind_key(row.name): bought_now(moment)}
    usual, _ = row.usual_amount
    return {
        kind_key(row.name): stocked_at(
            now=moment,
            cycle_days=cycle,
            typical_qty=float(usual),
            qty=float(adjustment.qty),
        )
    }


async def _sections_of(
    pool: DictPool | None, lines: Sequence[PlanLine], kinds_map: Mapping[str, frozenset[str]]
) -> dict[str, frozenset[str]]:
    if pool is None or not lines:
        return {}
    try:
        tree = await categories_store.load(pool)
    except Exception as exc:
        log.warning("twins.sections_failed", error=str(exc))
        return {}
    parent = catalog.sections_of(tree)
    out: dict[str, frozenset[str]] = {}
    for line in lines:
        article = str(line.product.get("externalProductId") or "")
        found = frozenset(parent[slug] for slug in kinds_map.get(article, ()) if slug in parent)
        if found:
            out[article] = found
    return out


async def _aisles_of(
    rows: list[PantryItem], kinds: list[HistoryItem], pool: DictPool | None
) -> Aisled:
    if pool is None:
        return Aisled(of={}, order=())
    by_id = {item.lager_id: item for item in kinds}
    pairs: list[tuple[str, list[str]]] = []
    for row in rows:
        item = by_id.get(row.id)
        found = [seen.article for seen in item.sources if seen.article] if item else []
        pairs.append((row.id, found or ([row.id] if row.source == "receipts" else [])))
    articles = sorted({article for _, found in pairs for article in found})
    if not articles:
        return Aisled(of={}, order=())
    try:
        catalog_map = await catalog_store.load(pool, articles)
        tree = await categories_store.load(pool)
    except Exception as exc:
        log.warning("pantry.aisles_failed", error=str(exc))
        return Aisled(of={}, order=())
    roots = catalog.roots_of(tree)
    named = await intent_aisles(
        None, [row.label for row in rows if row.named], sorted(roots), pool=pool
    )
    by_row = {row.id: named.get(row.label, "") for row in rows if row.named}
    return aisles(pairs, catalog_map, roots, by_row)


async def _mandates_of(
    rows: list[PantryItem], kinds: list[HistoryItem], pool: DictPool | None, account: str
) -> dict[str, PantryMandate]:
    if pool is None or not account or not rows:
        return {}
    try:
        stored = await saved_swaps.load(pool, account)
    except Exception as exc:
        log.warning("pantry.mandate_unavailable", error=str(exc))
        return {}
    by_id = {item.lager_id: item for item in kinds}
    found: dict[str, PantryMandate] = {}
    for row in rows:
        item = by_id.get(row.id)
        if item is None:
            continue
        agreed = stored.get(kind_key(item.name))
        if agreed is not None and agreed.links:
            keep, gone = fresh_links(
                [link.article for link in agreed.links], item.sources, recent_days=RECENT_DAYS
            )
            if gone:
                log.info("swaps.saved_link_stale", kind=kind_key(item.name), dropped=len(gone))
            links = [link for link in agreed.links if link.article in set(keep)]
            if links:
                found[row.id] = PantryMandate(
                    links=[PantryLink(article=link.article, name=link.name) for link in links],
                    agreed=True,
                )
                continue
        own = own_chain(item.sources, head=item.lager_id, recent_days=RECENT_DAYS)
        if own:
            found[row.id] = PantryMandate(
                links=[PantryLink(article=one.article, name=one.label) for one in own],
                agreed=False,
            )
    return found


async def pantry_live(
    mcp: SilpoMCP,
    *,
    llm: Any = None,
    settings: Settings | None = None,
    now: datetime | None = None,
    place: Location | None = None,
    pool: DictPool | None = None,
    account: str = "",
    said: Said | None = None,
    receipts: Receipts | None = None,
    ask: bool = True,
    use_cache: bool = True,
    memory: bool | None = None,
    batches: int | None = None,
) -> Pantry:
    words = said or Said()
    voice = llm if ask else None
    cfg = settings or Settings()
    packs = cfg.pantry_batches if batches is None else batches
    tally = Tally()
    read = receipts or await read_receipts(
        mcp, settings=settings, place=place, now=now, pool=pool, account=account, tally=tally
    )
    history = read.history
    apply_marks(history, words.marks)
    apply_cycles(history, words.cycles, words.cycle_sources)
    kinds = history_kinds([item for item in history if not is_service_item(item.name)])
    names: dict[str, Naming] = {}
    if llm is not None:
        names = await intent_names(
            voice,
            naming_candidates(kinds, words.listed.values()),
            pool=pool,
            tally=tally,
            use_cache=use_cache,
            memory=memory,
            batches=packs,
        )
        apply_keeps(
            history,
            names,
            await intent_keeps(
                voice,
                naming_labels(names),
                pool=pool,
                use_cache=use_cache,
                memory=memory,
                batches=packs,
            ),
        )
    sense = await intent_sense(
        voice, naming_labels(names), pool=pool, use_cache=use_cache, memory=memory, batches=packs
    )
    apply_sense(history, names, sense)
    counted = receipts_pantry(history, now=now, names=names, sense=sense)
    if words.source == SOURCE_MANUAL:
        items, outside = only_manual(
            counted, words.listed, history=history, now=now, names=names, marks=words.marks
        )
    else:
        items, outside = (
            with_manual(
                counted, words.listed, history=history, now=now, names=names, marks=words.marks
            ),
            untracked(kinds, names=names),
        )
    away = {key for key in words.hidden if key}
    away_labels = {
        told.label
        for item in kinds
        if kind_key(item.name) in away
        and (told := names.get(kind_key(item.name))) is not None
        and told.label
    }
    hidden_ids = {
        item.lager_id
        for item in kinds
        if kind_key(item.name) in away
        or ((told := names.get(kind_key(item.name))) is not None and told.label in away_labels)
    }
    bar_ids = {
        item.lager_id
        for item in kinds
        if (told := names.get(kind_key(item.name))) is not None
        and said_group(manual_key(told.label), told.drink, words.drinks)[0] is not None
    }
    shown = [
        row
        for row in items
        if row.source == "manual" or (row.id not in hidden_ids and row.id not in bar_ids)
    ]
    folded = fold(
        [Level(id=row.id, intent=row.group or "", urgent=row.running_out) for row in shown],
        apart=words.apart,
    )
    by_id = {row.id: row for row in shown}
    shown = [
        by_id[row].model_copy(update={"group": folded.group_of.get(row)}) for row in folded.order
    ]
    rail = await _aisles_of(shown, kinds, pool)
    if rail.of:
        shown = [row.model_copy(update={"aisle": rail.of.get(row.id)}) for row in shown]

    hand = await _mandates_of(shown, kinds, pool, account)
    if hand:
        shown = [row.model_copy(update={"mandate": hand.get(row.id)}) for row in shown]

    got = target_reach(history, now=now)
    basket_size = usual_basket_stats(read.sizes)
    live = {row.id for row in shown}
    took_away = sorted({row.label for row in items if row.id not in live and row.id not in bar_ids})
    at_bar = sorted({row.label for row in items if row.source != "manual" and row.id in bar_ids})
    return Pantry(
        items=shown,
        hidden=took_away,
        at_bar=at_bar,
        receipts=read.count,
        orders=read.orders,
        kinds=len(kinds),
        tracked_from=MIN_RECEIPTS,
        spend=spend_target(read.online.paid),
        target_pool=got.kinds,
        target_estimate=got.estimate,
        trip_gap=trip_gap([moment.date() for item in history for moment in item.moments]),
        list_limit=basket_size.limit,
        aisles=[PantryAisle(title=one.title, rows=one.rows) for one in rail.order],
        source=words.source,
        apart=[name for name in words.apart if name],
        unlisted=len(outside),
        outside=outside[:PANTRY_POOL],
        trace=_pantry_trace(
            read,
            tally,
            place=place,
            kinds=kinds,
            names=names,
            rows=shown,
            words=words,
            llm=llm,
            folded=folded,
            outside=outside,
            basket_size=basket_size,
        ).steps,
    )


def _pantry_trace(
    read: Receipts,
    tally: Tally,
    *,
    place: Location | None = None,
    kinds: list[HistoryItem],
    names: dict[str, Naming],
    rows: list[PantryItem],
    words: Said,
    llm: Any,
    folded: Folded,
    outside: Sequence[str],
    basket_size: Usual,
) -> Tracer:
    trace = Tracer()
    source = place.source if place is not None else None
    trace.add(
        "step-pantry-place",
        "code",
        {
            "магазин": read.branch_id or "—",
            "джерело": source.value if source is not None else "не питали",
        },
        source_note(source) if source is not None else "магазин той, за слотом якого читались чеки",
        decision="асортимент, ціни й залишки в кожній філії свої",
        tag=None if source is BranchSource.ADDRESS else "не за адресою",
        tag_tone="muted" if source is BranchSource.ADDRESS else "warn",
    )
    live = max(0, read.count - tally.stored_papers)
    trace.add(
        "step-pantry-read",
        "silpo_get_my_offline_orders",
        {
            "чеків": read.count,
            "зі сховища": tally.stored_papers,
            "дочитано наживо": live,
            "замовлень": read.orders,
        },
        f"{read.count} чеків і {read.orders} замовлень; "
        f"зі сховища {tally.stored_papers}, дочитано {live}",
        decision="історія зберігається, тож щоразу дочитується лише хвіст",
    )
    unnamed = [item.name for item in kinds if kind_key(item.name) not in names]
    trace.add(
        "step-pantry-names",
        "агент" if tally.named_asked else "кеш назв",
        {
            "видів": len(kinds),
            "з кешу": tally.named_cached,
            "спитано": tally.named_asked,
            "без назви": len(unnamed),
        },
        f"видів {len(kinds)}: з кешу {tally.named_cached}, спитано "
        f"{tally.named_asked}, без назви {len(unnamed)} з усіх видів, не з рядків",
        decision=(
            "назва -- властивість ТОВАРУ, не гостя: кеш вічний і спільний"
            if llm is not None
            else "без моделі рядки лишаються з назвами за словами -- це відкат, не поломка"
        ),
    )
    banded = sum(1 for row in rows if row.cycle_days is not None)
    heard = len(words.marks) + len(words.cycles) + len(words.hidden) + len(words.listed)
    trace.add(
        "step-pantry-rows",
        "core.cycles",
        {
            "режим": "список гостя" if words.source == SOURCE_MANUAL else "чеки",
            "область": "бар" if words.scope == BAR else "комора",
            "рядків": len(rows),
            "зі смугою": banded,
            "без циклу": len(rows) - banded,
            "позначок": len(words.marks),
            "названих циклів": len(words.cycles),
            "сховано": len(words.hidden),
            "дописано": len(words.listed),
        },
        f"рядків {len(rows)}: зі смугою {banded}, без циклу {len(rows) - banded}; "
        f"слів гостя накладено {heard}",
        decision=(
            "режим списку: рядки лише з нього, числа далі з чеків"
            if words.source == SOURCE_MANUAL
            else "рядок без доведеного циклу лишається, але без смуги і без «закінчилось»"
        ),
    )
    trace.add(
        "step-pantry-levels",
        "core.levels",
        {
            "рядків": len(rows),
            "згорнуто": folded.rows,
            "груп": folded.groups,
            "розділено гостем": len(words.apart),
        },
        f"груп {folded.groups}: у них {folded.rows} рядків з {len(rows)}; "
        f"розділено гостем {len(words.apart)}",
        decision=("група -- це ПОКАЗ: злиття по наміру дало нуль нових циклів і один відібрало"),
    )
    pooled = min(len(outside), PANTRY_POOL)
    trace.add(
        "step-pantry-ceilings",
        "core.ceilings",
        {
            "видів": len(kinds),
            "рядків": len(rows),
            "поза коморою": len(outside),
            "у пулі вікна": pooled,
            "стеля пулу": PANTRY_POOL,
            "список на похід": basket_size.limit,
        },
        f"поріг ведення {MIN_RECEIPTS}: з {len(kinds)} видів рядками {len(rows)}; "
        f"у пулі вікна {pooled} з {len(outside)} при стелі {PANTRY_POOL}",
        decision=f"стеля списку на похід -- з його ж чеків: {basket_size.phrase()}",
    )
    return trace


def untracked(kinds: list[HistoryItem], *, names: dict[str, Naming] | None = None) -> list[str]:
    rare = [kind for kind in kinds if kind.receipts < MIN_RECEIPTS]
    rare.sort(key=lambda kind: kind.last_moment() or datetime.min.replace(tzinfo=UTC), reverse=True)
    seen: dict[str, None] = {}
    for kind in rare:
        seen.setdefault(kind_label(kind.name, names), None)
    return list(seen)


def tracked_kinds(history: Sequence[HistoryItem]) -> list[HistoryItem]:
    return [
        item for item in history if item.receipts >= MIN_RECEIPTS and not is_service_item(item.name)
    ]


@dataclass(frozen=True, slots=True)
class Reserve:

    pool: tuple[Candidate, ...] = ()
    promo_held: int = 0
    stale: int = 0


SILENT_RANK = 500

POOL_WINDOW_DAYS = 180


def fill_pool(
    history: Sequence[HistoryItem],
    *,
    moment: datetime,
    soon: int,
    skip: Collection[str] = (),
    said: Sequence[str] = (),
    kinds: catalog.KindKeys | None = None,
) -> Reserve:
    away = set(skip)
    spoken = {norm_name(name) for name in said}
    pool: list[Candidate] = []
    promo_held = 0
    stale = 0
    for item in tracked_kinds(history):
        kind = kinds.key(item.name) if kinds else catalog.kind_word(item.name)
        if item.name in away or norm_name(item.name) in spoken:
            continue
        if item.promo.mostly:
            promo_held += 1
            continue
        beat = item.rhythm(moment)
        if beat.days_since is None:
            continue
        if beat.cycle_days is None and beat.days_since > POOL_WINDOW_DAYS:
            stale += 1
            continue
        if beat.cycle_days is not None:
            left = beat.cycle_days - beat.days_since
            if beat.trust is Trust.SILENT:
                silence = beat.silence
                assert silence is not None
                pool.append(
                    Candidate(
                        key=item.name,
                        rank=SILENT_RANK + round(silence),
                        cost=item.typical_cost,
                        why=(f"давно не брав: {beat.days_since} дн при звичних ~{beat.cycle_days}"),
                        kind=kind,
                    )
                )
            elif left <= 0:
                pool.append(
                    Candidate(
                        key=item.name,
                        rank=left,
                        cost=item.typical_cost,
                        why="закінчилось за циклом",
                        kind=kind,
                    )
                )
            elif left <= soon:
                pool.append(
                    Candidate(
                        key=item.name,
                        rank=100 + left,
                        cost=item.typical_cost,
                        why=f"закінчиться за {left} дн — беру наперед",
                        kind=kind,
                    )
                )
            else:
                pool.append(
                    Candidate(
                        key=item.name,
                        rank=supply_rank_of(left),
                        cost=item.typical_cost,
                        why=(
                            f"докинуто до суми: береш раз на ~{beat.cycle_days} дн, "
                            f"вдома ще ~{left} дн"
                        ),
                        kind=kind,
                    )
                )
        elif beat.longest is not None and beat.days_since > beat.longest:
            pool.append(
                Candidate(
                    key=item.name,
                    rank=200,
                    cost=item.typical_cost,
                    why=(
                        f"береш нерівно: не брав {beat.days_since} дн при звичних до {beat.longest}"
                    ),
                    kind=kind,
                )
            )
        else:
            pool.append(
                Candidate(
                    key=item.name,
                    rank=supply_rank_of(
                        None if beat.longest is None else beat.longest - beat.days_since
                    ),
                    cost=item.typical_cost,
                    why=f"докинуто до суми: береш нерівно, останній раз {beat.days_since} дн тому",
                    kind=kind,
                )
            )
    return Reserve(pool=tuple(pool), promo_held=promo_held, stale=stale)


def _kind_axis(keys: catalog.KindKeys | None) -> str:
    if keys is None:
        return "перше слово назви: карти видів не було"
    split = sum(1 for group in keys.by_word.values() if len(group) > 1)
    return (
        f"перше слово, різане вузлами дерева: розділено слів {split}"
        if split
        else "перше слово: вузли нікого не розділили"
    )


def spend_target(paid: Sequence[Decimal]) -> SpendTarget:
    spend = usual_order([float(value) for value in paid])
    return SpendTarget(
        target=Decimal(spend.target),
        orders=spend.orders,
        presets=[Decimal(step) for step in spend.presets],
        note=spend.phrase(),
    )


def target_reach(history: Sequence[HistoryItem], *, now: datetime | None = None) -> Reach:
    moment = now or datetime.now(UTC)
    soon = trip_gap([stamp.date() for item in history for stamp in item.moments])
    return reach_of_pool(fill_pool(history, moment=moment, soon=soon).pool)


def _listed(
    manual: Mapping[str, str],
    known: set[str],
    *,
    history: list[HistoryItem],
    now: datetime | None,
    names: dict[str, Naming] | None,
    marks: Mapping[str, datetime] | None,
) -> tuple[list[PantryItem], dict[str, list[str]]]:
    added: list[PantryItem] = []
    said: dict[str, list[str]] = {}
    for label in manual.values():
        item = manual_item(label, history, now=now, names=names, marks=marks)
        word = label.strip()
        if word and regrouped(word, item.label):
            words = said.setdefault(item.id, [])
            if word not in words:
                words.append(word)
        if item.id in known:
            continue
        known.add(item.id)
        added.append(item)
    return added, said


def _speak_up(rows: list[PantryItem], said: Mapping[str, list[str]]) -> list[PantryItem]:
    if not said:
        return rows
    return [
        row.model_copy(update={"written_as": said[row.id]}) if row.id in said else row
        for row in rows
    ]


def with_manual(
    rows: list[PantryItem],
    manual: Mapping[str, str],
    *,
    history: list[HistoryItem],
    now: datetime | None = None,
    names: dict[str, Naming] | None = None,
    marks: Mapping[str, datetime] | None = None,
) -> list[PantryItem]:
    if not manual:
        return rows
    added, said = _listed(
        manual, {row.id for row in rows}, history=history, now=now, names=names, marks=marks
    )
    if not added:
        return _speak_up(rows, said)
    running_out = [row for row in rows if row.running_out]
    calm = [row for row in rows if not row.running_out]
    return _speak_up([*running_out, *added, *calm], said)


def only_manual(
    rows: list[PantryItem],
    manual: Mapping[str, str],
    *,
    history: list[HistoryItem],
    now: datetime | None = None,
    names: dict[str, Naming] | None = None,
    marks: Mapping[str, datetime] | None = None,
) -> tuple[list[PantryItem], list[str]]:
    seen: set[str] = set()
    items, said = _listed(manual, seen, history=history, now=now, names=names, marks=marks)
    running_out = [row for row in items if row.running_out]
    calm = [row for row in items if not row.running_out]
    outside = [row.label for row in rows if row.id not in seen]
    return _speak_up([*running_out, *calm], said), outside


async def delivery_options_live(
    mcp: SilpoMCP,
    *,
    settings: Settings | None = None,
    place: Location | None = None,
    now: datetime | None = None,
) -> list[DeliveryOption]:
    cfg = settings if settings is not None else _default_settings
    since = now or datetime.now(UTC)
    where = place if place is not None else await resolve_place(mcp, settings=cfg)
    offered = where.offered

    options: list[DeliveryOption] = []
    for type_id, label, note in DELIVERY_TYPES:
        if type_id in _HACKATHON_DISABLED:
            options.append(
                DeliveryOption(
                    id=type_id,
                    label=label,
                    note=note,
                    cost=Decimal(0),
                    available=False,
                    unavailable_reason=_HACKATHON_DISABLED[type_id],
                )
            )
            continue
        if offered is not None and type_id not in offered:
            options.append(
                DeliveryOption(
                    id=type_id,
                    label=label,
                    note=note,
                    cost=Decimal(0),
                    available=False,
                    unavailable_reason="за твоєю адресою так не возять",
                )
            )
            continue
        branch = where.branch_for(type_id) or cfg.branch_id
        outcome = await mcp.call(
            "silpo_get_time_slots",
            slots_query(branch, type_id, SLOT_LOOKAHEAD, since=since),
        )
        option = option_from_slots(
            type_id, label, note, outcome.payload_raw.get("slots") or [], now=since
        )
        if offered is not None and type_id in offered and not option.available:
            option = option.model_copy(update={"available": True, "unavailable_reason": None})
        options.append(option)
    options.append(_LOKO_OPTION)
    return options


MAX_LINE_QTY = 24

_SALE_UNITS_IN_RECEIPT = frozenset({"кг", "kg", "л", "l"})

_WEIGHED_ROW_UNITS = frozenset({"кг", "л"})

PANTRY_WEIGHT_STEP = Decimal("0.1")

STOP_WORDS = frozenset(
    {
        "і",
        "й",
        "та",
        "або",
        "чи",
        "ще",
        "плюс",
        "також",
        "потім",
        "може",
        "давай",
        "якщо",
        "треба",
        "потрібно",
        "надо",
        "необхідно",
        "купити",
        "купить",
        "купи",
        "купімо",
        "закупити",
        "взяти",
        "візьми",
        "візьмемо",
        "брати",
        "замовити",
        "замов",
        "замовимо",
        "додати",
        "додай",
        "докупити",
        "докупи",
        "щось",
        "шось",
        "нам",
        "мені",
        "собі",
        "би",
        "б",
        "же",
        "ж",
        "сьогодні",
        "завтра",
        "зараз",
        "вже",
        "уже",
        "скоро",
        "терміново",
        "тиждень",
        "зібрати",
        "зібери",
    }
)

AUTO_NEEDS_LIMIT = DEFAULT_NEEDS

OVER_QUESTION = "over"

OVER_RAISE = "raise"

MIN_RECEIPTS = 3

PANTRY_POOL = 1000

PICK_TOKENS_PER_INTENT = 240

CHAIN_TOKENS_PER_ROW = 120

NAMING_TOKENS_PER_NAME = 80

NO_HISTORY_NOTE = (
    "поки не бачу твоїх покупок у «Сільпо», тому не знаю, що в тебе закінчується. "
    "Напиши, що потрібно («молоко, хліб»), або наповни кошик у «Сільпо» — "
    "зберу і доведу до дверей. А комора наповниться сама: купуй як завжди, з "
    f"карткою, і за {MIN_RECEIPTS} покупки виду я знатиму його цикл"
)

_SERVICE_FIRST_WORDS = frozenset({"пакет", "пакети", "послуга", "послуги"})

_SERVICE_PHRASES = frozenset({"в скарбничку"})


def is_service_item(name: str) -> bool:
    normalized = norm_name(name)
    words = normalized.split()
    return bool(words) and (words[0] in _SERVICE_FIRST_WORDS or normalized in _SERVICE_PHRASES)


@dataclass(slots=True)
class HistoryItem:
    lager_id: str
    name: str
    unit: str
    receipts: int = 0
    qty_total: Decimal = Decimal(0)
    recent_receipts: int = 0
    qty_recent: Decimal = Decimal(0)
    moments: list[datetime] = field(default_factory=list)
    online_last: datetime | None = None
    online_qtys: list[Decimal] = field(default_factory=list)
    image: str | None = None
    price: Decimal | None = None
    price_at: datetime | None = None
    marked_at: datetime | None = None
    said_cycle: int | None = None
    said_from: str | None = None
    keeps: Keeps | None = None
    rhythm_lies: bool = False
    purchases: list[Purchase] = field(default_factory=list)
    sources: list[Seen] = field(default_factory=list)

    @property
    def promo(self) -> Habit:
        return self.promo_at(None)

    def promo_at(self, shelf: Decimal | None) -> Habit:
        return promo_habit(
            self.purchases,
            weighed=receipt_unit(self.unit) in _WEIGHED_ROW_UNITS,
            shelf=shelf,
        )

    def _per_receipt(self) -> Decimal | None:
        if len(self.online_qtys) >= ONLINE_HABIT_MIN:
            ordered = sorted(self.online_qtys)
            return ordered[len(ordered) // 2]
        if self.recent_receipts > 0:
            return self.qty_recent / self.recent_receipts
        if self.receipts > 0:
            return self.qty_total / self.receipts
        return None

    @property
    def typical_weight(self) -> Decimal | None:
        raw = self._per_receipt()
        if raw is None:
            return None
        unit = self.unit.strip().lower()
        if unit in RECEIPT_GRAM_UNITS:
            return raw / 1000
        if unit in _SALE_UNITS_IN_RECEIPT:
            return raw
        return None

    @property
    def typical_qty(self) -> int:
        raw = self._per_receipt()
        if raw is None:
            return 1
        weight = self.typical_weight
        if weight is not None:
            raw = weight
        return min(MAX_LINE_QTY, max(1, round(raw)))

    @property
    def typical_cost(self) -> Decimal | None:
        if self.price is None:
            return None
        weight = self.typical_weight
        amount = weight if weight is not None else Decimal(self.typical_qty)
        return (self.price * amount).quantize(Decimal("0.01"))

    def rhythm(self, now: datetime) -> Rhythm:
        return rhythm(
            [moment.date() for moment in self.moments],
            days_since=self.days_since_last(now),
            said_days=self.said_cycle,
            keeps=self.keeps,
            rhythm_lies=self.rhythm_lies,
        )

    def cycle_days(self) -> int | None:
        return rhythm(
            [moment.date() for moment in self.moments],
            days_since=None,
            said_days=self.said_cycle,
            keeps=self.keeps,
            rhythm_lies=self.rhythm_lies,
        ).cycle_days

    def last_moment(self) -> datetime | None:
        latest = max(self.moments) if self.moments else None
        if self.marked_at is not None and (latest is None or self.marked_at > latest):
            return self.marked_at
        return latest

    @property
    def guest_said(self) -> bool:
        return self.marked_at is not None and self.marked_at == self.last_moment()

    @property
    def usual_amount(self) -> tuple[Decimal, Decimal]:
        weight = self.typical_weight
        if weight is not None and receipt_unit(self.unit) in _WEIGHED_ROW_UNITS:
            return weight, PANTRY_WEIGHT_STEP
        return Decimal(self.typical_qty), WHOLE

    def days_since_last(self, now: datetime) -> int | None:
        latest = self.last_moment()
        if latest is None:
            return None
        days = (now - latest).days
        return days if self.guest_said else max(0, days)


@dataclass(slots=True)
class PlanLine:

    intent: str
    product: dict[str, Any]
    qty: Decimal
    reason: str
    from_history: HistoryItem | None
    risky: bool = False
    chain: tuple[Alternative, ...] = ()
    mandate: str | None = None
    swap_fork: Fork | None = None
    needs_approval: bool = False
    gone: bool = False
    at_home: bool = False
    ahead: bool = False
    decided: bool = False
    auto_need: bool = False
    history_matched: bool = False
    explanation: str | None = None
    reason_code: Reason | None = None
    considered: tuple[dict[str, Any], ...] = ()
    considered_total: int = 0
    slicing_note: str | None = None
    wish: str | None = None
    shelf_life: str | None = None
    cheaper: dict[str, Any] | None = None
    promo: bool = False

    @property
    def price(self) -> Decimal:
        return Decimal(str(self.product["price"]))

    @property
    def total(self) -> Decimal:
        return self.price * self.qty


@dataclass(slots=True)
class Assembled:

    basket: Basket
    lines: list[PlanLine]
    unresolved: list[str]
    slot: dict[str, Any]
    run_log: Path | None = None
    branch_id: str | None = None
    swap_cards: dict[str, dict[str, Any]] = field(default_factory=dict)
    rules: tuple[str, ...] = ()
    auto_swap: bool = False
    auto_swap_percent: int = 10
    plan: Plan | None = None
    fill_intents: tuple[str, ...] = ()
    occasion: Occasion | None = None


def run_cost(spent: Meter) -> Decimal:
    return quota.cost_of(spent.model, spent.input_tokens, spent.output_tokens) or Decimal(0)


def norm_name(text: str) -> str:
    return " ".join(text.lower().split())


RUNS_DIR = Path(__file__).resolve().parents[3] / "runs"


def record_run(basket: Basket, request: BuildRequest, moment: datetime) -> Path | None:
    try:
        RUNS_DIR.mkdir(exist_ok=True)
        stamp = moment.strftime("%Y-%m-%dT%H-%M-%S") + f"-{moment.microsecond // 1000:03d}"
        path = RUNS_DIR / f"{stamp}_basket.json"
        path.write_text(
            json.dumps(
                {
                    "recorded_at": moment.isoformat(),
                    "request": request.model_dump(mode="json", by_alias=True),
                    "basket": basket.model_dump(mode="json", by_alias=True),
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )
    except OSError as exc:
        log.warning("basket.run_log_failed", error=str(exc))
        return None
    log.info("basket.run_recorded", path=str(path))
    return path


class Tracer:

    def __init__(
        self,
        on_step: Callable[[TraceStep], None] | None = None,
        *,
        start: int = 0,
    ) -> None:
        self.steps: list[TraceStep] = []
        self._start = start
        self._on_step = on_step

    def add(
        self,
        step_id: str,
        tool: str,
        args: dict[str, Any],
        summary: str,
        *,
        duration_ms: int | None = None,
        calls: int | None = None,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
        decision: str | None = None,
        tag: str | None = None,
        tag_tone: Literal["good", "warn", "muted"] = "muted",
        prompt: str | None = None,
        question: TraceQuestion | None = None,
    ) -> None:
        step = TraceStep(
            id=step_id,
            seq=self._start + len(self.steps) + 1,
            tool=tool,
            args=args,
            duration_ms=duration_ms,
            calls=calls,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            result_summary=summary,
            decision=decision,
            tag=tag,
            tag_tone=tag_tone,
            prompt=prompt or None,
            question=question,
        )
        if not fits(summary):
            log.warning("trace.long_summary", step=step_id, chars=len(summary))
        self.steps.append(step)
        if self._on_step is not None:
            self._on_step(step)


def stitch(*groups: Sequence[TraceStep], start: int = 1) -> list[TraceStep]:
    joined: list[TraceStep] = []
    for group in groups:
        for step in group:
            joined.append(step.model_copy(update={"seq": start + len(joined)}))
    return joined


def _named_within(names: Sequence[str], *, budget: int) -> str:
    shown: list[str] = []
    left = budget
    for name in names:
        need = len(name) + (2 if shown else 0)
        if need > left:
            break
        left -= need
        shown.append(name)
    if not shown:
        return ""
    rest = len(names) - len(shown)
    return ", ".join(shown) + (f" і ще {rest}" if rest else "")


def _agent_target(stretched: Stretched | None) -> AgentTarget | None:
    if stretched is None:
        return None
    return AgentTarget(
        named=stretched.named,
        proposed=stretched.proposed,
        target=stretched.target,
        why=stretched.why,
        refused=stretched.refused,
    )


def _occasion_tag(plan: OccasionPlan, *, failed: bool) -> str:
    if failed:
        return "не спрацював"
    if not plan.touched:
        return "без змін"
    parts = []
    if plan.added:
        parts.append(f"+{len(plan.added)}")
    if plan.skipped:
        parts.append(f"-{len(plan.skipped)}")
    return " ".join(parts)


_RECEIPT_TZ = ZoneInfo("Europe/Kyiv")


def _order_moment(order: dict[str, Any]) -> datetime | None:
    raw = order.get("createdAt")
    if not raw:
        return None
    try:
        moment = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=_RECEIPT_TZ)


MAX_ONLINE_PAGES = 8
ONLINE_PAGE = 50

_CANCELLED = frozenset({"canceled", "cancelled"})

_FINAL_STAGES = frozenset({Stage.RECEIVED, Stage.CANCELED})


def _order_stamp(order: dict[str, Any], field: str) -> tuple[str, str]:
    when = str(order.get("createdAt") or "")[:10]
    raw = order.get(field)
    try:
        total = f"{float(str(raw or 0)):.2f}"
    except TypeError, ValueError:
        total = "?"
    return when, total


async def load_history(
    mcp: SilpoMCP,
    slot: dict[str, Any],
    branch_id: str | None,
    *,
    now: datetime | None = None,
    pool: DictPool | None = None,
    account: str = "",
    tally: Tally | None = None,
) -> tuple[list[HistoryItem], int, int, list[int], Online]:
    cutoff = (now or datetime.now(UTC)) - timedelta(days=RECENT_DAYS)
    by_lager: dict[str, HistoryItem] = {}
    sizes: list[int] = []
    paper: set[tuple[str, str]] = set()

    papers, spent_ms, from_store = await _offline_history(
        mcp, slot, branch_id, pool=pool, account=account
    )
    if tally is not None:
        tally.stored_papers = from_store
    receipts = len(papers)
    for order in papers:
        paper.add(_order_stamp(order, "sumReg"))
        moment = _order_moment(order)
        fresh = moment is not None and moment >= cutoff
        products = order.get("products") or []
        sizes.append(sum(1 for p in products if not is_service_item(p.get("name") or "")))
        for product in products:
            lager = str(product.get("lagerId") or "")
            if not lager:
                continue
            item = by_lager.setdefault(
                lager,
                HistoryItem(
                    lager_id=lager,
                    name=product.get("name") or "",
                    unit=product.get("unit") or "шт",
                ),
            )
            qty = Decimal(str(product.get("quantity") or 1))
            item.receipts += 1
            item.qty_total += qty
            if product.get("image"):
                item.image = product["image"]
            _remember_price(item, product, moment)
            _remember_purchase(item, product, qty)
            if moment is not None:
                item.moments.append(moment)
            if fresh:
                item.recent_receipts += 1
                item.qty_recent += qty

    online, online_ms, online_total, paid = await _online_orders(
        mcp, paper=paper, pool=pool, account=account
    )
    spent_ms += online_ms
    if online_total > MAX_ONLINE_PAGES * ONLINE_PAGE:
        log.warning(
            "history.online_capped", total=online_total, read=MAX_ONLINE_PAGES * ONLINE_PAGE
        )
    _merge_online(
        by_lager,
        online,
        cutoff=cutoff,
        sizes=sizes,
        articles=await _articles_of(pool, online),
    )
    return list(by_lager.values()), receipts, spent_ms, sizes, Online(len(online), tuple(paid))


_STORED_ORDER = frozenset(
    {
        "orderId",
        "number",
        "status",
        "createdAt",
        "amount",
        "discount",
        "delivery",
        "sumReg",
        "sumDiscount",
        "accruedBalaBonusesSum",
        "rewards",
        "products",
    }
)
_STORED_PRODUCT = frozenset(
    {
        "id",
        "lagerId",
        "name",
        "unit",
        "quantity",
        "price",
        "subtotal",
        "removed",
        "image",
        "companyId",
        "catalogProduct",
    }
)


def _paper_ident(order: dict[str, Any]) -> str:
    when = str(order.get("createdAt") or "")
    total = str(order.get("sumReg") or "")
    if not when:
        return sha256(repr(sorted(order.items())).encode()).hexdigest()
    return f"{when}|{total}"


def _stored_row(order: dict[str, Any]) -> dict[str, Any]:
    dropped: set[str] = set(order) - _STORED_ORDER
    row = {key: value for key, value in order.items() if key in _STORED_ORDER}
    products = []
    for product in order.get("products") or []:
        dropped |= set(product) - _STORED_PRODUCT
        clean = {key: value for key, value in product.items() if key in _STORED_PRODUCT}
        card = clean.pop("catalogProduct", None) or {}
        price = card.get("price")
        if price is not None:
            clean["priceSeen"] = price
        products.append(clean)
    if "products" in row:
        row["products"] = products
    if dropped - _KNOWN_DROPPED:
        log.info("history.stored_dropped", keys=sorted(dropped - _KNOWN_DROPPED))
    return row


_KNOWN_DROPPED = frozenset(
    {
        "address",
        "branchId",
        "filId",
        "filialName",
        "cityName",
        "receiptUrl",
        "chequeMagicName",
        "chequePrediction",
    }
)


async def _offline_history(
    mcp: SilpoMCP,
    slot: dict[str, Any],
    branch_id: str | None,
    *,
    pool: DictPool | None = None,
    account: str = "",
) -> tuple[list[dict[str, Any]], int, int]:
    if pool is None or not account:
        papers, spent = await _offline_pages(mcp, slot, branch_id, since=_HISTORY_EPOCH)
        return papers, spent, 0

    known: dict[str, dict[str, Any]] = {}
    since = _HISTORY_EPOCH
    store = True
    try:
        for order in await receipts_store.load(pool, account, receipts_store.OFFLINE):
            known[_paper_ident(order)] = order
        seen = await receipts_store.mark(pool, account, receipts_store.OFFLINE)
    except Exception as exc:
        log.warning("history.store_failed", error=str(exc)[:200])
        known, seen, store = {}, None, False
    else:
        if seen is not None and seen.last_at is not None:
            since = (seen.last_at - timedelta(days=receipts_store.OVERLAP_DAYS)).isoformat()

    fresh, spent_ms = await _offline_pages(mcp, slot, branch_id, since=since)
    if store:
        await _remember_papers(pool, account, fresh)

    merged = dict(known)
    for order in fresh:
        merged[_paper_ident(order)] = order
    return list(merged.values()), spent_ms, len(known)


async def _offline_pages(
    mcp: SilpoMCP,
    slot: dict[str, Any],
    branch_id: str | None,
    *,
    since: str,
) -> tuple[list[dict[str, Any]], int]:

    async def page(offset: int) -> tuple[list[dict[str, Any]], int | None, int]:
        outcome = await mcp.call(
            "silpo_get_my_offline_orders",
            {
                "branchId": branch_id,
                "deliveryType": slot["deliveryType"],
                "timeslotStart": slot["start"],
                "timeslotEnd": slot["end"],
                "limit": HISTORY_PAGE,
                "offset": offset,
                "dateStart": since,
            },
        )
        total = (outcome.payload_raw.get("meta") or {}).get("total")
        return (
            list(outcome.payload_raw.get("orders") or []),
            None if total is None else int(total),
            outcome.duration_ms,
        )

    orders: list[dict[str, Any]] = []
    spent_ms = 0
    taken = 0
    for number in range(MAX_HISTORY_PAGES):
        chunk, total, spent = await page(taken)
        spent_ms += spent
        if number == 0 and not chunk:
            again, total, spent = await page(taken)
            spent_ms += spent
            log.info("history.empty_retry", healed=bool(again), orders=len(again))
            chunk = again
        orders.extend(chunk)
        taken += len(chunk)
        if total is not None and taken >= total:
            break
        if not chunk or len(chunk) < HISTORY_PAGE:
            break
    return orders, spent_ms


async def _remember_papers(pool: DictPool, account: str, orders: list[dict[str, Any]]) -> None:
    rows = []
    last: datetime | None = None
    for order in orders:
        moment = _order_moment(order)
        if moment is None:
            continue
        rows.append((_paper_ident(order), moment, _stored_row(order)))
        last = moment if last is None else max(last, moment)
    try:
        if rows:
            await receipts_store.save(pool, account, receipts_store.OFFLINE, rows)
        await receipts_store.touch(pool, account, receipts_store.OFFLINE, last_at=last)
    except Exception as exc:
        log.warning("history.store_write_failed", error=str(exc)[:200])


async def _online_orders(
    mcp: SilpoMCP,
    *,
    paper: set[tuple[str, str]],
    pool: DictPool | None = None,
    account: str = "",
) -> tuple[list[dict[str, Any]], int, int, list[Decimal]]:
    stored, head_only = await _stored_orders(pool, account)
    fetched, spent_ms, total = await _online_pages(mcp, head_only=head_only)
    if pool is not None and account:
        await _remember_orders(pool, account, fetched)

    merged: dict[str, dict[str, Any]] = {_order_ident(o): o for o in stored}
    for order in fetched:
        merged[_order_ident(order)] = order

    orders: list[dict[str, Any]] = []
    paid: list[Decimal] = []
    for order in merged.values():
        if str(order.get("status") or "") in _CANCELLED:
            continue
        amount = order.get("amount")
        if amount is not None:
            paid.append(Decimal(str(amount)))
        if _order_stamp(order, "amount") in paper:
            continue
        orders.append(order)
    return orders, spent_ms, max(total, len(merged)), paid


def _order_ident(order: dict[str, Any]) -> str:
    return str(order.get("orderId") or order.get("id") or "")


async def _stored_orders(pool: DictPool | None, account: str) -> tuple[list[dict[str, Any]], bool]:
    if pool is None or not account:
        return [], False
    try:
        stored = await receipts_store.load(pool, account, receipts_store.ONLINE)
        seen = await receipts_store.mark(pool, account, receipts_store.ONLINE)
    except Exception as exc:
        log.warning("history.store_failed", error=str(exc)[:200])
        return [], False
    return stored, seen is not None


async def _online_pages(mcp: SilpoMCP, *, head_only: bool) -> tuple[list[dict[str, Any]], int, int]:
    orders: list[dict[str, Any]] = []
    spent_ms = 0
    total = 0
    pages = 1 if head_only else MAX_ONLINE_PAGES
    for page in range(pages):
        try:
            outcome = await mcp.call(
                "silpo_get_my_online_orders",
                {"limit": ONLINE_PAGE, "offset": page * ONLINE_PAGE},
            )
        except MCPCallError as exc:
            log.warning("history.online_failed", error=str(exc)[:200])
            break
        spent_ms += outcome.duration_ms
        chunk = outcome.payload_raw.get("orders") or []
        orders.extend(chunk)
        total = (outcome.payload_raw.get("meta") or {}).get("total") or total
        if len(chunk) < ONLINE_PAGE or (page + 1) * ONLINE_PAGE >= total:
            break
    return orders, spent_ms, total


async def _remember_orders(pool: DictPool, account: str, orders: list[dict[str, Any]]) -> None:
    rows = []
    last: datetime | None = None
    for order in orders:
        stage = stage_of(str(order.get("status") or ""))
        if stage not in _FINAL_STAGES:
            continue
        ident = _order_ident(order)
        moment = _order_moment(order)
        if not ident or moment is None:
            continue
        rows.append((ident, moment, _stored_row(order)))
        last = moment if last is None else max(last, moment)
    if not rows:
        return
    try:
        await receipts_store.save(pool, account, receipts_store.ONLINE, rows)
        await receipts_store.touch(pool, account, receipts_store.ONLINE, last_at=last)
    except Exception as exc:
        log.warning("history.store_write_failed", error=str(exc)[:200])


@dataclass(slots=True)
class OnlineCards:

    by_product: dict[str, dict[str, Any]]
    by_name: dict[str, str]

    def article(self, row: dict[str, Any]) -> str | None:
        found = self.by_product.get(str(row.get("id") or ""))
        if found is not None:
            return str(found["article"])
        return self.by_name.get(norm_name(str(row.get("name") or "")))

    def unit(self, row: dict[str, Any]) -> str:
        found = self.by_product.get(str(row.get("id") or ""))
        if found is None:
            return ""
        step = found.get("step")
        named = sale_unit(
            weighted=found.get("weighted"),
            ratio=found.get("ratio"),
            step=Decimal(str(step)) if step is not None else None,
        )
        return named or "шт"


def web_article(name: str) -> str:
    return f"web:{norm_name(name)}"


async def _articles_of(pool: DictPool | None, orders: list[dict[str, Any]]) -> OnlineCards:
    empty = OnlineCards(by_product={}, by_name={})
    if pool is None or not orders:
        return empty
    rows = [
        row
        for order in orders
        for row in (order.get("products") or [])
        if row.get("name") and not row.get("removed")
    ]
    ids = sorted({str(row.get("id")) for row in rows if row.get("id")})
    keys = sorted({norm_name(str(row.get("name") or "")) for row in rows} - {""})
    try:
        return OnlineCards(
            by_product=await catalog_store.cards_by_product(pool, ids),
            by_name=await catalog_store.articles_by_name(pool, keys),
        )
    except Exception as exc:
        log.warning("history.articles_unavailable", error=str(exc)[:200])
        return empty


def _merge_online(
    by_lager: dict[str, HistoryItem],
    orders: list[dict[str, Any]],
    *,
    cutoff: datetime,
    sizes: list[int],
    articles: OnlineCards,
) -> None:
    for order in orders:
        moment = _order_moment(order)
        fresh = moment is not None and moment >= cutoff
        rows = [
            row
            for row in (order.get("products") or [])
            if not row.get("removed") and not is_service_item(str(row.get("name") or ""))
        ]
        sizes.append(len(rows))
        for row in rows:
            name = str(row.get("name") or "")
            if not name:
                continue
            lager = articles.article(row) or web_article(name)
            item = by_lager.setdefault(
                lager, HistoryItem(lager_id=lager, name=name, unit=articles.unit(row))
            )
            qty = Decimal(str(row.get("quantity") or 1))
            item.receipts += 1
            item.qty_total += qty
            if row.get("image"):
                item.image = row["image"]
            _remember_price(item, row, moment)
            _remember_purchase(item, row, qty)
            if moment is not None:
                item.moments.append(moment)
                if item.online_last is None or moment > item.online_last:
                    item.online_last = moment
            item.online_qtys.append(qty)
            if fresh:
                item.recent_receipts += 1
                item.qty_recent += qty


def _remember_price(item: HistoryItem, product: dict[str, Any], moment: datetime | None) -> None:
    card = product.get("catalogProduct") or {}
    raw = card.get("price")
    if raw is None:
        raw = product.get("priceSeen")
    if raw is None:
        raw = product.get("price")
    if raw is None:
        return
    fresher = item.price_at is None or (moment is not None and moment >= item.price_at)
    if item.price is not None and not fresher:
        return
    item.price = Decimal(str(raw))
    item.price_at = moment


def _remember_purchase(item: HistoryItem, product: dict[str, Any], qty: Decimal) -> None:
    purchase = purchase_of(product, qty)
    if purchase is not None:
        item.purchases.append(purchase)


_PROCESSED_MARKERS = frozenset(
    {
        "сушений",
        "сушена",
        "сушені",
        "сушен",
        "чіпси",
        "смажений",
        "смажені",
        "в'ялений",
        "в'ялені",
        "вялений",
        "цукати",
        "снек",
        "снеки",
        "консервований",
        "консервовані",
        "маринований",
        "мариновані",
        "солоний",
        "солоні",
        "солона",
        "квашений",
        "квашені",
        "копчений",
        "копчені",
        "заморожений",
        "заморожені",
        "маринад",
        "маринаді",
        "шашлик",
        "шашлику",
        "шашлика",
        "в'ялена",
        "в'яленої",
        "томлений",
        "томлена",
        "томлені",
        "рвана",
        "рваний",
        "ковбаса",
        "ковбаски",
        "ковбасок",
        "напівфабрикат",
        "напівфабрикати",
        "напівфабрикату",
        "гриль",
        "смалець",
    }
)


def _processing_of(name: str) -> frozenset[str]:
    return frozenset(word for word in norm_name(name).split() if word in _PROCESSED_MARKERS)


def strip_other_processing(
    candidates: dict[str, list[dict[str, Any]]], narrowed: dict[str, Kind]
) -> list[str]:
    emptied: list[str] = []
    for intent, kind in narrowed.items():
        if not kind.empty:
            continue
        wanted = _processing_of(intent)
        rest = [
            product
            for product in candidates.get(intent, [])
            if _processing_of(product.get("name", "")) <= wanted
        ]
        if rest:
            candidates[intent] = rest
        elif intent in candidates:
            del candidates[intent]
            emptied.append(intent)
    return emptied


def _word_match(a: str, b: str) -> bool:
    a = homoglyphs.bare(homoglyphs.fold_names(a).text)
    b = homoglyphs.bare(homoglyphs.fold_names(b).text)
    if a == b:
        return True
    shorter = min(len(a), len(b))
    if shorter < 5:
        return False
    shared = 0
    for x, y in zip(a, b, strict=False):
        if x != y:
            break
        shared += 1
    return shared >= 4 and len(a) - shared <= 2 and len(b) - shared <= 2


def name_matches(intent: str, name: str) -> bool:
    intent_words = [w for w in norm_name(intent).split() if w not in STOP_WORDS]
    name_words = norm_name(name).split()
    if not intent_words or not name_words:
        return False
    if not any(_word_match(word, name_words[0]) for word in intent_words):
        return False
    return all(
        any(_word_match(word, candidate) for candidate in name_words) for word in intent_words
    )


def related_to(intent: str, name: str, *, kind_proven: bool = False) -> bool:
    return name_matches(intent, name) or (not kind_proven and brands.carried_by(intent, name))


def kind_word_proven(intent: str, names: Iterable[str]) -> bool:
    intent_words = [w for w in norm_name(intent).split() if w not in STOP_WORDS]
    heads = {words[0] for words in (norm_name(n).split() for n in names) if words}
    return any(_word_match(word, head) for word in intent_words for head in heads)


def _ask_picks(intent: str, cards: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    proven = kind_word_proven(intent, (p["name"] for p in cards))
    kin = [p for p in cards if related_by_kind(intent, p["name"], kind_proven=proven)]
    return list(kin or cards)[:PICKS_ON_ASK]


def _considered(
    intent: str, options: Sequence[dict[str, Any]], chosen: Mapping[str, Any]
) -> tuple[dict[str, Any], ...]:
    rest = [p for p in options if p is not chosen]
    proven = kind_word_proven(intent, (p["name"] for p in options))
    kin = [p for p in rest if related_by_kind(intent, p["name"], kind_proven=proven)]
    seen = {id(p) for p in kin}
    return tuple(kin + [p for p in rest if id(p) not in seen])[:MAX_CONSIDERED]


def fresh_own(
    intent: str,
    options: Sequence[dict[str, Any]],
    owned: Mapping[str, HistoryItem],
) -> dict[str, Any] | None:
    if not options or not owned:
        return None
    kind_proven = kind_word_proven(intent, (p["name"] for p in options))
    mine = [
        p
        for p in options
        if (item := owned.get(str(p["externalProductId"]))) is not None
        and item.recent_receipts > 0
        and related_by_kind(intent, p["name"], kind_proven=kind_proven)
    ]
    if not mine:
        return None
    return max(
        mine,
        key=lambda p: (
            owned[str(p["externalProductId"])].recent_receipts,
            owned[str(p["externalProductId"])].receipts,
        ),
    )


def own_over_promo(
    intent: str,
    chosen: Mapping[str, Any],
    options: Sequence[dict[str, Any]],
    *,
    hint: HistoryItem | None,
    owned: Mapping[str, HistoryItem],
    why: str = "",
    auto: bool = False,
    rules_given: bool = False,
) -> dict[str, Any] | None:
    if not auto or rules_given:
        return None
    if hint is not None and hint.promo.mostly:
        return None
    if str(chosen["externalProductId"]) in owned:
        return None
    if not on_sale(chosen) and why != "акція":
        return None
    return fresh_own(intent, options, owned)


SIBLING_TAKE = 3


def siblings_of(
    auto_intents: Mapping[str, HistoryItem],
    history: Sequence[HistoryItem],
    names: Mapping[str, Naming],
    *,
    take: int = SIBLING_TAKE,
) -> dict[str, list[str]]:
    label_of = {key: naming.intent for key, naming in names.items()}
    out: dict[str, list[str]] = {}
    for intent, own in auto_intents.items():
        label = label_of.get(kind_key(own.name))
        if not label:
            continue
        kin = [
            item
            for item in history
            if item.lager_id != own.lager_id
            and item.lager_id.isdigit()
            and item.recent_receipts > 0
            and label_of.get(kind_key(item.name)) == label
        ]
        kin.sort(key=lambda item: (-item.recent_receipts, -item.receipts, item.lager_id))
        if kin:
            out[intent] = [item.lager_id for item in kin[:take]]
    return out


def related_by_kind(intent: str, name: str, *, kind_proven: bool = False) -> bool:
    return related_to(head(intent, 1) or intent, name, kind_proven=kind_proven)


def narrowing_word(intent: str, name: str) -> bool:
    return brands.carried_by(intent, name) and not name_matches(intent, name)


def name_proves_kind(intent: str, name: str, *, like: str = "") -> bool:
    return name_matches(intent, name) and _processing_of(name) <= (
        _processing_of(intent) | _processing_of(like)
    )


def habit_reason(hint: HistoryItem) -> str:
    if hint.recent_receipts == 0 or hint.receipts < MIN_RECEIPTS:
        return "брав це раніше, але не останнім часом"
    return f"звичне з історії — {receipts_phrase(hint.receipts)}"


def history_matches(
    intent: str, history: list[HistoryItem], *, limit: int = 3
) -> list[HistoryItem]:
    proven = kind_word_proven(intent, (item.name for item in history))
    matches = [item for item in history if related_to(intent, item.name, kind_proven=proven)]
    matches.sort(
        key=lambda item: (item.recent_receipts, item.receipts, item.qty_total),
        reverse=True,
    )
    return matches[:limit]


def _alias_match(
    label: str, kinds: list[HistoryItem], aliases: dict[str, str] | None
) -> HistoryItem | None:
    if not aliases or not label:
        return None
    want = norm_name(label)
    for kind in kinds:
        if norm_name(aliases.get(kind_key(kind.name), "")) == want:
            return kind
    return None


def _history_match(intent: str, history: list[HistoryItem]) -> HistoryItem | None:
    top = history_matches(intent, history, limit=1)
    return top[0] if top else None


SEARCH_LIMIT = 20

MAX_CONSIDERED = 5

CANDIDATES_IN_PROMPT = 10

PICKS_ON_ASK = MAX_OPTIONS


async def _ask_shelf(
    mcp: SilpoMCP, queries: list[str], slot: dict[str, Any], branch_id: str | None
) -> tuple[dict[str, list[dict[str, Any]]], int]:
    found: dict[str, list[dict[str, Any]]] = {}
    spent_ms = 0
    for start in range(0, len(queries), 30):
        part, part_ms = await _ask_shelf_part(mcp, queries[start : start + 30], slot, branch_id)
        found.update(part)
        spent_ms += part_ms
    return found, spent_ms


async def _ask_shelf_part(
    mcp: SilpoMCP, queries: list[str], slot: dict[str, Any], branch_id: str | None
) -> tuple[dict[str, list[dict[str, Any]]], int]:
    try:
        outcome = await mcp.call(
            SEARCH_TOOL,
            {
                "branchId": branch_id,
                "deliveryType": slot["deliveryType"],
                "timeslotStart": slot["start"],
                "timeslotEnd": slot["end"],
                "products": queries,
                "limit": SEARCH_LIMIT,
            },
        )
    except MCPCallError as exc:
        if len(queries) <= 1:
            log.warning("shelf.query_refused", query=queries[0] if queries else "", error=str(exc))
            return ({queries[0]: []} if queries else {}), 0
        half = len(queries) // 2
        left, left_ms = await _ask_shelf_part(mcp, queries[:half], slot, branch_id)
        right, right_ms = await _ask_shelf_part(mcp, queries[half:], slot, branch_id)
        return {**left, **right}, left_ms + right_ms
    found: dict[str, list[dict[str, Any]]] = {}
    for query in outcome.payload_raw.get("queries") or []:
        found[query.get("query") or ""] = [
            product for product in query.get("products") or [] if product.get("available")
        ]
    return found, outcome.duration_ms


async def search_products(
    mcp: SilpoMCP, queries: list[str], slot: dict[str, Any], branch_id: str | None
) -> tuple[dict[str, list[dict[str, Any]]], int]:
    before = mcp.silence
    found, spent_ms = await _ask_shelf(mcp, queries, slot, branch_id)
    said = Silence(
        asked=mcp.silence.asked - before.asked,
        empty=mcp.silence.empty - before.empty,
    )
    if not is_mute(said):
        return found, spent_ms

    log.warning("shelf.mute", asked=said.asked, empty=said.empty, share=round(said.share, 2))
    again, more_ms = await _ask_shelf(mcp, queries, slot, branch_id)
    healed = 0
    for query, products in again.items():
        if products and not found.get(query):
            found[query] = products
            healed += 1
    if healed:
        mcp.silence = mcp.silence.healed(healed)
        log.info("shelf.recovered", healed=healed, of=said.empty)
    return found, spent_ms + more_ms


async def narrow_by_query(
    mcp: SilpoMCP,
    candidates: dict[str, list[dict[str, Any]]],
    probes: Mapping[str, str],
    *,
    slot: dict[str, Any],
    branch_id: str | None,
) -> tuple[list[str], int]:
    wanted = sorted({phrase for phrase in probes.values() if phrase})
    if not wanted:
        return [], 0
    found, spent_ms = await search_products(mcp, wanted, slot, branch_id)
    narrowed: list[str] = []
    for intent, phrase in probes.items():
        products = found.get(phrase) or []
        if products:
            candidates[intent] = products
            narrowed.append(intent)
    return narrowed, spent_ms


def _prepared_mark(
    product: dict[str, Any], also_in: dict[str, tuple[str, ...]]
) -> list[str] | None:
    marks = set(_processing_of(product["name"]))
    marks |= set(also_in.get(str(product.get("externalProductId")), ()))
    return sorted(marks) or None


PANTRY_MANUAL_WHY = "ти сам додав це в комору"

PROMO_WAIT_WHY = "береш це по акції, а зараз її немає — чекаю акції"


def reason_text(
    code: str | None,
    *,
    chosen: dict[str, Any],
    options: Sequence[dict[str, Any]],
    hint: HistoryItem | None,
    matched: bool,
    picked_by: str = HEAD_PICK,
    subject: str = "намір",
) -> str:
    if code == "звичне" and matched and hint is not None:
        return habit_reason(hint)
    if code == "акція":
        old = chosen.get("oldPrice")
        if old:
            return f"акційна ціна: було {old}, стало {chosen.get('price')}"
    if code == "дешевше":
        mine = _per_100g(chosen)
        others = [v for v in (_per_100g(p) for p in options) if v is not None]
        if mine is not None and others and mine <= min(others):
            return "найнижча ціна за спільну одиницю серед кандидатів"
        return f"під {subject} відповідає точніше за решту"
    if code == GUEST_PICK:
        return f"ти обрав це сам під {subject}"
    if code == OWN_PICK and hint is not None:
        return (
            f"своє замість питання: береш це останнім часом — "
            f"{hint.recent_receipts} свіжих чеків із {hint.receipts}"
        )
    if code == OWN_DECLINE and hint is not None:
        return (
            f"своє замість відмови: береш це останнім часом — "
            f"{hint.recent_receipts} свіжих чеків із {hint.receipts}"
        )
    if code == OWN_PROMO and hint is not None:
        return (
            f"своє замість чужої акції: береш це останнім часом — "
            f"{hint.recent_receipts} свіжих чеків із {hint.receipts}"
        )
    if code == LOOP_PICK:
        return f"звичайний пошук не дав нічого — агент дошукав за кілька кроків під {subject}"
    if code == "правило":
        return "так вимагає твоє правило збору"
    if code == "строк":
        return "вирішив термін придатності"
    if code == "єдине":
        return f"інших кандидатів під {'цей намір' if subject == 'намір' else subject} не знайшлось"
    if code == "під_намір":
        return f"під {subject} відповідає точніше за решту"
    if matched and hint is not None:
        return habit_reason(hint)
    return {
        AGENT_PICK: f"обрав агент під {subject}",
        PRICE_PICK: f"найдешевший за спільну одиницю під {subject}",
        HEAD_PICK: f"перший доступний під {subject}",
    }.get(picked_by, f"перший доступний під {subject}")


def _slicing_habit(hints: Sequence[HistoryItem]) -> slicing.Habit:
    return slicing.habit((hint.name, hint.receipts) for hint in hints)


def _per_100g(product: dict[str, Any]) -> float | None:
    step = product.get("step")
    price = product.get("price")
    unit = price_per_100g(
        Decimal(str(price)) if price is not None else None,
        weighted=product.get("weighted"),
        ratio=product.get("displayRatio"),
        step=Decimal(str(step)) if step is not None else None,
    )
    return round(float(unit), 2) if unit is not None else None


def _source_of(intent: str, *, auto: frozenset[str], occasion: Mapping[str, str]) -> str:
    if intent in occasion:
        return "привід"
    if intent in auto:
        return "потреби з циклів"
    return "список гостя"


@dataclass(frozen=True, slots=True)
class Batches:

    sent: int
    failures: list[BaseException] = field(default_factory=list)
    lost: tuple[str, ...] = ()
    stray: tuple[str, ...] = ()
    prompt: str = ""

    @property
    def note(self) -> str:
        parts = [] if self.sent < 2 else [f"пачок паралельно: {self.sent}"]
        if self.failures:
            parts.append(
                f"не долетіло {len(self.failures)} з {self.sent} "
                f"({str(self.failures[0])[:80]}) — без вибору лишились "
                f"{len(self.lost)} намірів, план за історією"
            )
        if self.stray:
            parts.append(
                f"мітка не з цього запиту: {len(self.stray)} "
                f"({', '.join(self.stray[:3])}) — ці рядки відкинуто"
            )
        return " · ".join(parts)


async def agent_picks(
    llm: Any,
    intents: list[str],
    candidates: dict[str, list[dict[str, Any]]],
    hints_all: dict[str, list[HistoryItem]],
    rules: list[str],
    also_in: dict[str, tuple[str, ...]] | None = None,
    readings: dict[str, tuple[str, ...]] | None = None,
    answers: dict[str, str] | None = None,
    budget: Decimal | None = None,
    auto_intents: frozenset[str] = frozenset(),
    occasion: Occasion | None = None,
    occasion_intents: Mapping[str, str] | None = None,
    batches: int = 1,
    kinds: Mapping[str, frozenset[str]] | None = None,
    owned: Mapping[str, HistoryItem] | None = None,
    on_batch: Callable[[int, int, list[str]], None] | None = None,
    skills: str = "",
) -> tuple[dict[str, dict[str, Any]], list[tuple[str, str]], str, int, int, Batches]:
    payload = []
    marks = labels.labels(intents)
    by_mark = {mark: name for name, mark in marks.items()}
    with_queue = budget is not None
    for intent in intents:
        guest_form = _slicing_habit(hints_all.get(intent, ()))
        mine = {hint.lager_id for hint in hints_all.get(intent, [])}
        kind = kind_words(intent) or intent
        own_kinds = catalog.kinds_of(mine, kinds or {})
        shown = shortlist(
            candidates.get(intent, []),
            own=lambda product, ids=mine: str(product["externalProductId"]) in ids,
            bought=(lambda product, ids=owned: str(product["externalProductId"]) in ids)
            if owned
            else None,
            same_kind=(
                lambda product, ks=own_kinds: catalog.same_kind(
                    str(product["externalProductId"]), ks, kinds or {}
                )
            )
            if own_kinds
            else None,
            related=lambda product, word=kind: related_to(word, product["name"]),
            cap=CANDIDATES_IN_PROMPT,
        )
        payload.append(
            {
                "намір": intent,
                "ключ": marks[intent],
                "джерело": _source_of(intent, auto=auto_intents, occasion=occasion_intents or {}),
                "прочитання": list((readings or {}).get(intent, ())) or None,
                "уточнення_гостя": (answers or {}).get(intent),
                "кандидати": [
                    {
                        "id": str(p["externalProductId"]),
                        "назва": p["name"],
                        "ціна": p["price"],
                        "стара_ціна": p.get("oldPrice"),
                        "залишок": p["stock"],
                        "фасовка": p.get("displayRatio"),
                        "за_100г": _per_100g(p),
                        "оброблене": _prepared_mark(p, also_in or {}),
                        "нарізка": slicing.is_sliced(p["name"]) or None,
                    }
                    for p in shown
                ],
                "з_історії": [
                    {
                        "назва": hint.name,
                        "артикул": hint.lager_id,
                        "чеків_усього": hint.receipts,
                        "чеків_за_90_днів": hint.recent_receipts,
                        "звична_кількість": hint.typical_qty,
                        "акційна_звичка": hint.promo.phrase() or None,
                    }
                    for hint in hints_all.get(intent, [])
                ]
                or None,
                "нарізка_в_чеках": (guest_form.says() if guest_form.sliced is not None else None),
            }
        )
    common = {
        "правила_гостя": rules or None,
        "привід": occasion.phrase() if occasion and occasion.named else None,
        "що_означає_привід": (occasion.task() if occasion and occasion.named else None),
        "межа_кошика": float(budget) if budget is not None else None,
    }
    groups = batching.split(intents, batches)

    system = pick_system(with_queue=with_queue, skills=skills)
    prompt = prompt_stamp("pick", system)

    async def one(part: list[dict[str, Any]]) -> Decision:
        return await llm.decide(
            system=system,
            user=json.dumps({**prune(common), "наміри": part}, ensure_ascii=False),
            schema=pick_schema(with_queue=with_queue),
            prompt=prompt,
            max_tokens=max(2048, PICK_TOKENS_PER_INTENT * len(part)),
        )

    parts = [[prune(payload[index]) for index in group] for group in groups]
    started = monotonic()

    async def told(index: int, part: list[dict[str, Any]]) -> Decision:
        result = await one(part)
        if on_batch is not None:
            names: list[str] = []
            for pick in result.data.get("picks", []):
                intent = labels.resolve(str(pick.get("intent", "")), by_mark)
                chosen = str(pick.get("chosen_id") or "").strip()
                if intent is None or not chosen:
                    continue
                card = next(
                    (
                        c
                        for c in candidates.get(intent, ())
                        if str(c.get("externalProductId")) == chosen
                    ),
                    None,
                )
                names.append(str(card.get("name") or intent) if card else intent)
            on_batch(index + 1, len(parts), names)
        return result

    results = await asyncio.gather(
        *(told(index, part) for index, part in enumerate(parts)), return_exceptions=True
    )
    duration_ms = int((monotonic() - started) * 1000)

    picks: dict[str, dict[str, Any]] = {}
    queues: list[list[tuple[str, str]]] = []
    lost: list[str] = []
    stray: list[str] = []
    tokens = 0
    model = ""
    failures: list[BaseException] = []
    for group, result in zip(groups, results, strict=True):
        if isinstance(result, BaseException):
            failures.append(result)
            lost.extend(intents[index] for index in group)
            continue
        mine = {intents[index] for index in group}
        for pick in result.data.get("picks", []):
            name = labels.resolve(str(pick.get("intent", "")), by_mark)
            if name is None:
                stray.append(str(pick.get("intent", ""))[:24])
                continue
            if name in mine:
                picks.setdefault(name, pick)
        queues.append(
            [
                (queued, str(item["why"]))
                for item in result.data.get("expendable") or []
                if (queued := labels.resolve(str(item["intent"]), by_mark)) is not None
            ]
        )
        tokens += result.usage.input_tokens + result.usage.output_tokens
        model = model or result.model
    if failures and len(failures) == len(groups):
        raise failures[0]
    queue = list(batching.interleave(queues))
    return (
        picks,
        queue,
        model,
        duration_ms,
        tokens,
        Batches(len(groups), failures, tuple(lost), tuple(stray), prompt),
    )


def tell_turn(
    trace: Tracer,
    turn: Turn,
    *,
    step_id: str = "step-batch",
    owed: Sequence[str] = (),
) -> None:
    args: dict[str, Any] = {
        "планувала": list(turn.planned),
        "виконано": list(turn.executed),
        "не влізло": list(turn.cut),
        "зрізав валідатор": list(turn.dropped),
        "нові факти": list(turn.learned),
        "сказала «досить»": turn.said_stop,
        "чому": turn.why,
        "токенів": turn.tokens,
    }
    summary = (
        f"оберт {turn.number}: планувала {len(turn.planned)}, "
        f"виконала {len(turn.executed)}, нового дізналась {len(turn.learned)}"
    )
    if owed:
        args["ще винні"] = list(owed)
        summary += f"; ще винні {len(owed)}"
    trace.add(
        step_id,
        "model",
        args,
        summary,
        decision=turn.why or None,
        tag=f"+{len(turn.learned)}" if turn.learned else None,
        tag_tone="good" if turn.learned else "muted",
    )


def build_chain(
    intent: str,
    chosen: dict[str, Any],
    options: Sequence[dict[str, Any]],
    *,
    history_id: str | None = None,
    proven: frozenset[str] | None = None,
    usual_pack: Decimal | None = None,
    kinds: Mapping[str, frozenset[str]] | None = None,
    kin: frozenset[str] = frozenset(),
    taken: frozenset[str] = frozenset(),
) -> tuple[Alternative, ...]:
    chosen_id = str(chosen["externalProductId"])
    narrowed_by_guest = narrowing_word(intent, chosen["name"])
    kind_axis = brands.head_word(chosen["name"]) if narrowed_by_guest else intent
    own_kinds = catalog.kinds_of({chosen_id, *([history_id] if history_id else [])}, kinds or {})
    alternatives = [
        Alternative(
            external_product_id=str(p["externalProductId"]),
            name=p["name"],
            source=Source.HISTORY
            if (history_id and str(p["externalProductId"]) == history_id)
            or str(p["externalProductId"]) in kin
            else Source.SIMILAR,
            price=Decimal(str(p["price"])),
            stock=p.get("stock"),
            available=bool(p.get("available")),
            pack=_pack_of(p),
            per_unit=_unit_price(p),
            ratio=_card_pack(p)[0],
            by_weight=is_sold_by_weight(
                weighted=p.get("weighted"), ratio=_card_pack(p)[0], step=_card_pack(p)[1]
            ),
        )
        for p in options
        if str(p["externalProductId"]) != chosen_id
        and (
            name_proves_kind(kind_axis, p["name"], like=chosen["name"])
            or catalog.same_kind(str(p["externalProductId"]), own_kinds, kinds or {})
            or str(p["externalProductId"]) in kin
        )
        and (
            not narrowed_by_guest
            or brands.carried_by(intent, p["name"])
            or str(p["externalProductId"]) in kin
        )
        and (
            proven is None
            or str(p["externalProductId"]) in proven
            or str(p["externalProductId"]) == history_id
            or str(p["externalProductId"]) in kin
        )
        and (
            str(p["externalProductId"]) == history_id
            or str(p["externalProductId"]) in kin
            or price_within(chosen.get("price"), p.get("price"))
        )
        and (
            str(p.get("name", "")).strip().casefold()
            != str(chosen.get("name", "")).strip().casefold()
            or (p.get("displayRatio") or "") != (chosen.get("displayRatio") or "")
        )
    ]
    return rank_chain(
        alternatives,
        excluded_ids=taken - {str(chosen.get("externalProductId"))},
        want=_pack_of(chosen),
        usual=usual_pack,
        like=str(chosen.get("name") or ""),
    )


def _chain_of(
    articles: Sequence[str], candidates: Mapping[str, dict[str, Any]]
) -> tuple[tuple[Alternative, ...], list[str]]:
    chain: list[Alternative] = []
    lost: list[str] = []
    for article in articles:
        product = candidates.get(str(article))
        if product is None:
            lost.append(str(article))
            continue
        chain.append(
            Alternative(
                external_product_id=str(article),
                name=product["name"],
                source=Source.MANUAL,
                price=Decimal(str(product["price"])),
                stock=product.get("stock"),
                available=bool(product.get("available")),
            )
        )
    return tuple(chain), lost


@dataclass(frozen=True, slots=True)
class Agreed:

    chain: tuple[str, ...] = ()
    from_row: bool = False


def saved_for(
    intent: str, hint: HistoryItem | None, saved: Mapping[str, tuple[str, ...]] | None
) -> Agreed:
    if not saved:
        return Agreed()
    found = saved.get(kind_key(intent))
    if found:
        return Agreed(found)
    if hint is None:
        return Agreed()
    return Agreed(saved.get(kind_key(hint.name)) or (), from_row=True)


def _kept_chain(
    articles: tuple[str, ...] | None,
    cards: Mapping[str, dict[str, Any]],
    seen: Sequence[Seen] = (),
) -> tuple[Alternative, ...]:
    if not articles:
        return ()
    fresh, stale = fresh_links(articles, seen, recent_days=RECENT_DAYS)
    if stale:
        log.info("swaps.saved_link_stale", dropped=len(stale))
    chain, lost = _chain_of(fresh, cards)
    if lost:
        log.info("swaps.saved_link_not_on_slot", lost=len(lost))
    return chain


def chain_from_decision(
    decision: SwapDecision, candidates: Mapping[str, dict[str, Any]]
) -> tuple[Alternative, ...]:
    chain, lost = _chain_of(decision.chain, candidates)
    if lost:
        log.info("swaps.link_not_on_slot", article=decision.external_product_id, lost=len(lost))
    return chain


def mandate_for_decision(
    decision: SwapDecision,
    chain: tuple[Alternative, ...],
    *,
    risky: bool = False,
    shelf_life: str | None = None,
    wish: str | None = None,
) -> tuple[str | None, bool] | None:
    if decision.policy == "call":
        return None, True
    if decision.policy == "skip":
        return build_comment(chain=(), shelf_life=shelf_life, wishes=wish).comment, False
    if chain:
        return build_comment(chain=chain, shelf_life=shelf_life, wishes=wish).comment, False
    if decision.chain and risky:
        return None, True
    return None


def _pack_of(product: dict[str, Any]) -> Decimal | None:
    ratio, step = _card_pack(product)
    if is_sold_by_weight(weighted=product.get("weighted"), ratio=ratio, step=step):
        return None
    return parse_pack_weight(ratio)


def _unit_price(product: dict[str, Any]) -> Decimal | None:
    ratio, step = _card_pack(product)
    price = product.get("price")
    return price_per_100g(
        Decimal(str(price)) if price is not None else None,
        weighted=product.get("weighted"),
        ratio=ratio,
        step=step,
    )


def _card_pack(product: dict[str, Any]) -> tuple[str | None, Decimal | None]:
    raw_ratio = product.get("displayRatio")
    raw_step = product.get("step")
    return (
        None if raw_ratio is None else str(raw_ratio),
        Decimal(str(raw_step)) if raw_step is not None else None,
    )


def line_weight(product: dict[str, Any]) -> Decimal | None:
    ratio, step = _card_pack(product)
    return unit_weight_kg(weighted=product.get("weighted"), ratio=ratio, step=step)


def _sale_of(product: dict[str, Any]) -> tuple[str, Decimal | None]:
    ratio, step = _card_pack(product)
    unit = sale_unit(weighted=product.get("weighted"), ratio=ratio, step=step)
    if unit is None:
        return "шт", None
    return unit, sale_step(ratio=ratio, step=step)


def fork_for(product: dict[str, Any], percent: int) -> Fork:
    sale, _step = _sale_of(product)
    return price_fork(Decimal(str(product["price"])), percent=percent, per=sale)


def _amount_text(value: Decimal) -> str:
    if isinstance(exponent := value.as_tuple().exponent, int) and exponent < -2:
        value = value.quantize(Decimal("0.01"))
    return format(value.normalize(), "f").replace(".", ",")


def kg_text(value: Decimal) -> str:
    return f"{_amount_text(round(value, 2))} кг"


def line_quantity(
    chosen: dict[str, Any],
    *,
    pick: dict[str, Any] | None = None,
    hint: HistoryItem | None = None,
    auto_need: bool = False,
) -> tuple[Decimal, str, str | None]:
    unit, step = _sale_of(chosen)
    if step is not None:
        usual = hint.typical_weight if hint is not None else None
        if usual is not None and usual > 0:
            qty = quantize_to_step(usual, step)
            return qty, unit, f"вагове: звична вага з чеків — {_amount_text(qty)} {unit}"
        note = f"вагове: ваги в чеках немає, беру найменшу фасовку {_amount_text(step)} {unit}"
        return step, unit, note

    qty = int(pick["qty"]) if pick else (hint.typical_qty if hint else 1)
    ceiling = max_qty(float(hint.typical_qty) if hint else None) if auto_need else MAX_LINE_QTY
    return Decimal(min(ceiling, max(1, qty))), unit, None


def build_lines(
    intents: list[str],
    candidates: dict[str, list[dict[str, Any]]],
    hints: dict[str, HistoryItem],
    picks: dict[str, dict[str, Any]],
    *,
    auto_swap: bool = False,
    auto_swap_percent: int = 10,
    auto_intents: frozenset[str] = frozenset(),
    occasion_intents: Mapping[str, str] | None = None,
    refusals_stand: bool = False,
    rules_given: bool = False,
    silent_intents: Mapping[str, str] | None = None,
    fill_intents: Mapping[str, str] | None = None,
    manual_intents: Mapping[str, str] | None = None,
    swaps: Mapping[str, SwapDecision] | None = None,
    saved_chains: Mapping[str, tuple[str, ...]] | None = None,
    must_match: Mapping[str, str] | None = None,
    proven: Mapping[str, frozenset[str]] | None = None,
    kinds: Mapping[str, frozenset[str]] | None = None,
    habits: Mapping[str, slicing.Habit] | None = None,
    owned: Mapping[str, HistoryItem] | None = None,
    siblings: Mapping[str, Sequence[str]] | None = None,
    answered: frozenset[str] = frozenset(),
    hours_to_slot: float = 0.0,
    slot_day: date | None = None,
    trace: Tracer | None = None,
) -> tuple[list[PlanLine], list[str], dict[str, str]]:
    plan: list[PlanLine] = []
    kept_used = 0
    kept_from_row = 0
    kept_gone = 0
    dated = 0
    unresolved: list[str] = []
    declined: dict[str, str] = {}
    refused = 0
    rescued: list[tuple[str, dict[str, Any], HistoryItem]] = []
    over_promo: list[tuple[str, dict[str, Any], dict[str, Any], HistoryItem]] = []

    taken = frozenset(
        str(pick.get("chosen_id") or "").strip() for pick in picks.values()
    ) | frozenset(item.lager_id for item in hints.values() if item.lager_id)
    taken -= {""}
    for intent in intents:
        options = candidates.get(intent, [])
        if not options:
            unresolved.append(intent)
            continue

        required = (must_match or {}).get(intent)
        if required is not None:
            exact = next((p for p in options if str(p["externalProductId"]) == required), None)
            if exact is None:
                unresolved.append(intent)
                continue
            options = [exact]

        hint = hints.get(intent)
        pick = picks.get(intent)
        if pick is not None and not str(pick.get("chosen_id") or "").strip():
            if intent not in answered:
                on_shelf = hint is not None and any(
                    str(product["externalProductId"]) == hint.lager_id for product in options
                )
                own = None
                if intent in auto_intents and not on_shelf and not refusals_stand:
                    refused += 1
                    own = fresh_own(intent, options, owned or {})
                if own is None:
                    unresolved.append(intent)
                    declined[intent] = str(pick.get("swap") or "").strip() or NO_DECLINE_WHY
                    continue
                mine = (owned or {})[str(own["externalProductId"])]
                rescue: dict[str, Any] = {
                    **pick,
                    "chosen_id": str(own["externalProductId"]),
                    "qty": mine.typical_qty,
                    "why": OWN_DECLINE,
                }
                pick = rescue
                rescued.append((intent, own, mine))
            else:
                pick = None
        chosen = None
        dropped: str | None = None
        if pick:
            chosen = next(
                (p for p in options if str(p["externalProductId"]) == str(pick["chosen_id"])),
                None,
            )
            if chosen is not None and (
                own := own_over_promo(
                    intent,
                    chosen,
                    options,
                    hint=hint,
                    owned=owned or {},
                    why=str(pick.get("why") or ""),
                    auto=intent in auto_intents,
                    rules_given=rules_given,
                )
            ):
                mine = (owned or {})[str(own["externalProductId"])]
                over_promo.append((intent, chosen, own, mine))
                dropped = str(chosen["externalProductId"])
                instead: dict[str, Any] = {
                    **pick,
                    "chosen_id": str(own["externalProductId"]),
                    "qty": mine.typical_qty,
                    "why": OWN_PROMO,
                }
                pick = instead
                chosen = own
        if chosen is None and hint is not None:
            chosen = next(
                (p for p in options if str(p["externalProductId"]) == hint.lager_id), None
            )
        picked_by = AGENT_PICK if pick else HEAD_PICK
        if chosen is None:
            named = [p for p in options if narrowing_word(intent, p["name"])]
            pool = named or options
            kind_proven = kind_word_proven(intent, (p["name"] for p in pool))
            bought_here = [
                p
                for p in pool
                if str(p["externalProductId"]) in (owned or {})
                and related_by_kind(intent, p["name"], kind_proven=kind_proven)
            ]
            if bought_here:
                chosen = max(
                    bought_here,
                    key=lambda p: (
                        (owned or {})[str(p["externalProductId"])].recent_receipts,
                        (owned or {})[str(p["externalProductId"])].receipts,
                    ),
                )
            else:
                own_kinds = catalog.kinds_of(
                    {hint.lager_id} if hint is not None else set(), kinds or {}
                )
                kin = [
                    p
                    for p in pool
                    if catalog.same_kind(str(p["externalProductId"]), own_kinds, kinds or {})
                ]
                inside = kin or pool
                cheap = shortlist_cheapest(inside, unit_price=_per_100g)
                picked_by = PRICE_PICK if cheap is not None else HEAD_PICK
                chosen = cheap if cheap is not None else inside[0]

        occasion_why = (occasion_intents or {}).get(intent)
        silent_why = (silent_intents or {}).get(intent)
        fill_why = (fill_intents or {}).get(intent)
        manual_why = (manual_intents or {}).get(intent)
        qty, _unit, weight_note = line_quantity(
            chosen,
            pick=pick,
            hint=hint,
            auto_need=intent in auto_intents or occasion_why is not None,
        )
        bought = (owned or {}).get(str(chosen["externalProductId"]))
        known_item = bought if bought is not None else hint
        matched = bought is not None or (
            hint is not None and str(chosen["externalProductId"]) == hint.lager_id
        )
        reason = reason_text(
            pick.get("why") if pick else None,
            chosen=chosen,
            options=options,
            hint=bought or hint,
            matched=matched,
            picked_by=picked_by,
            subject="вид з комори" if manual_why == PANTRY_MANUAL_WHY else "намір",
        )
        if weight_note is not None:
            reason = f"{reason}. {weight_note}"

        chosen_kinds = catalog.kinds_of({str(chosen["externalProductId"])}, kinds or {})
        cheaper = (
            better_price(
                chosen,
                [
                    p
                    for p in options
                    if str(p["externalProductId"]) != str(chosen["externalProductId"])
                    and p.get("available")
                    and catalog.same_kind(str(p["externalProductId"]), chosen_kinds, kinds or {})
                    and covers(str(p.get("name") or ""), str(chosen.get("name") or ""))
                ],
                unit_price=_per_100g,
                price=lambda p: Decimal(str(p["price"])) if p.get("price") else None,
            )
            if chosen_kinds
            else None
        )

        form_wish = slicing.wish(chosen["name"], (str(p["name"]) for p in options))

        life = shelf_life_phrase(
            required_until(
                slot_day=slot_day,
                cycle_days=hint.cycle_days() if hint is not None else None,
                keeps=hint.keeps if hint is not None else None,
            )
        )
        if life:
            dated += 1

        decision = (swaps or {}).get(str(chosen["externalProductId"]))
        agreed = saved_for(intent, hint, saved_chains)
        kept_chain = _kept_chain(
            agreed.chain,
            {str(p["externalProductId"]): p for p in options},
            hint.sources if hint is not None else (),
        )
        if decision is not None and decision.chain:
            chain = chain_from_decision(decision, {str(p["externalProductId"]): p for p in options})
        elif decision is not None and decision.policy != "substitute":
            chain = ()
        elif kept_chain:
            chain = kept_chain
            kept_used += 1
            if agreed.from_row:
                kept_from_row += 1
        else:
            if agreed.chain:
                kept_gone += 1
            chain = build_chain(
                intent,
                chosen,
                options,
                history_id=known_item.lager_id if known_item is not None else None,
                proven=(proven or {}).get(intent),
                usual_pack=parse_pack_weight(hint.unit) if hint else None,
                kinds=kinds,
                kin=frozenset((siblings or {}).get(intent, ())),
                taken=(
                    taken - {dropped}
                    if dropped is not None
                    and not any(
                        str(other.get("chosen_id") or "").strip() == dropped
                        for other_intent, other in picks.items()
                        if other_intent != intent
                    )
                    else taken
                ),
            )
        risky = is_risky(chosen.get("stock"))
        mandate: str | None = None
        swap_fork: Fork | None = None
        needs_approval = False
        decided = (
            mandate_for_decision(decision, chain, risky=risky, shelf_life=life, wish=form_wish)
            if decision is not None
            else None
        )
        if decided is not None:
            mandate, needs_approval = decided
        elif chain:
            mandate = build_comment(chain=chain, shelf_life=life, wishes=form_wish).comment
        elif auto_swap:
            swap_fork = fork_for(chosen, auto_swap_percent)
            mandate = price_fork_comment(
                swap_fork,
                kind=str(pick.get("swap") or "") if pick else None,
                shelf_life=life,
                wish=form_wish,
            )
        else:
            mandate = build_comment(chain=(), shelf_life=life, wishes=form_wish).comment
        plan.append(
            PlanLine(
                intent=intent,
                product=chosen,
                qty=qty,
                reason=reason,
                from_history=hint,
                risky=risky,
                ahead=mandate is not None and not risky,
                decided=decided is not None,
                chain=chain,
                mandate=mandate,
                swap_fork=swap_fork,
                needs_approval=needs_approval,
                auto_need=intent in auto_intents or occasion_why is not None,
                explanation=occasion_why or silent_why or fill_why or manual_why or None,
                reason_code=(
                    Reason.OCCASION
                    if occasion_why
                    else Reason.CYCLE
                    if silent_why
                    else Reason.FREQUENCY
                    if fill_why or manual_why
                    else None
                ),
                history_matched=matched,
                wish=form_wish,
                shelf_life=life,
                considered=_considered(intent, options, chosen),
                considered_total=len(options),
                slicing_note=slicing.note(
                    chosen["name"], (habits or {}).get(intent) or slicing.Habit(None, 0, 0)
                ),
                cheaper=cheaper,
            )
        )
    carried = sum(1 for line in plan if line.shelf_life and line.mandate)
    if trace is not None and slot_day is not None:
        trace.add(
            "step-shelf-life",
            "core.shelf_life",
            {"рядків": len(plan), "день слота": slot_day.strftime("%d.%m")},
            (
                f"вимога до терміну на {carried} рядках"
                + (f", ще {dated - carried} нема на чому везти" if dated > carried else "")
                if carried
                else f"порахована на {dated}, а мандата під неї немає на жодному"
                if dated
                else "жоден вид не дав доведеного циклу і швидкопсувного ярусу"
            ),
            decision=(
                "дата рахується з доведеного циклу і дня слота, а не питається; "
                "ярус зберігання вирішує, чи є сенс просити"
            ),
            tag="термін" if carried else "нічого не змінилось",
            tag_tone="good" if carried else "muted",
        )
    if trace is not None and saved_chains:
        trace.add(
            "step-saved-swaps",
            "agent.swaps",
            {"погоджено раніше": len(saved_chains)},
            (
                f"беру погоджене: {kept_used}"
                + (f", з рядка комори: {kept_from_row}" if kept_from_row else "")
                + (f", на слоті не лишилось: {kept_gone}" if kept_gone else "")
                if kept_used
                else f"жодне не лишилось на слоті: {kept_gone}"
                if kept_gone
                else "жоден намір цього кошика не збігся зі збереженим"
            ),
            decision=(
                "погоджене гостем сильніше за пораховане, але ланка, якої на "
                "слоті немає, у мандат не їде"
            ),
            tag="рішення гостя" if kept_used else "нічого нового",
            tag_tone="good" if kept_used else "muted",
        )
    if trace is not None and refused:
        trace.add(
            "step-own-declined",
            "core.history",
            {
                "відмов на потребах з чеків": refused,
                "знято": [
                    f"«{intent}» → {own['name']} ({mine.recent_receipts} свіжих чеків)"
                    for intent, own, mine in rescued
                ],
            },
            (
                f"замість відмови беру свій свіжий артикул того ж виду: {len(rescued)} з {refused}"
                if rescued
                else f"жодну з {refused} не зняв: свого свіжого того ж виду серед кандидатів немає"
            ),
            decision="агент порівнює кандидатів з НАЗВОЮ наміру, а намір автопотреби "
            "-- це назва з чека; те, що гість бере останнім часом під іншою "
            "назвою того ж виду, сильніше за відмову",
            tag=f"-{len(rescued)} відмов" if rescued else "нічого не знято",
            tag_tone="good" if rescued else "muted",
        )
    if trace is not None:
        trace.add(
            "step-own-promo",
            "core.history",
            {
                "підмінено": len(over_promo),
                "взято": [
                    f"«{intent}»: агент обрав {gave['name']} → беру {own['name']} "
                    f"({mine.recent_receipts} свіжих чеків)"
                    for intent, gave, own, mine in over_promo
                ],
            },
            (
                f"замість чужої акції беру своє з чеків: {len(over_promo)} "
                + plural(len(over_promo), "рядок", "рядки", "рядків")
                if over_promo
                else "агент ніде не взяв чужу акцію замість свого"
            ),
            decision="знижка на чужому товарі не перебиває того, що ти береш "
            "останнім часом: там, де ти цей вид і без акції купуєш, дешева чужа "
            "марка -- це чужа ціна, а не твій вибір",
            tag=f"-{len(over_promo)} чужих акцій" if over_promo else "нічого не знято",
            tag_tone="good" if over_promo else "muted",
        )
    return plan, unresolved, declined


def collapse_split(lines: list[PlanLine], phrases: Mapping[str, Sequence[str]]) -> list[str]:
    dropped: list[str] = []
    for phrase, words in phrases.items():
        same = [
            line
            for line in lines
            if line.intent in words and name_matches(phrase, line.product["name"])
        ]
        same.sort(key=lambda line: not line.history_matched)
        for extra in same[1:]:
            lines.remove(extra)
            dropped.append(str(extra.product["name"]))
    return dropped


def shelf_recognises(phrase: str, hits: list[dict[str, Any]]) -> bool:
    wanted = [word for word in brand_words(phrase) if len(word) >= 4]
    if not wanted:
        return False
    need = max(1, (len(wanted) + 1) // 2)
    return any(
        sum(carried_by(word, str(hit.get("name") or "")) for word in wanted) >= need for hit in hits
    )


def collapse_same_product(lines: list[PlanLine]) -> list[tuple[str, int]]:
    groups: dict[str, list[PlanLine]] = {}
    for line in lines:
        groups.setdefault(str(line.product["externalProductId"]), []).append(line)
    merged: list[tuple[str, int]] = []
    dropped: set[int] = set()
    for group in groups.values():
        if len(group) == 1:
            continue
        keeper = next((line for line in group if not line.at_home), group[0])
        keeper.qty = max(line.qty for line in group)
        dropped.update(id(line) for line in group if line is not keeper)
        merged.append((str(keeper.product["name"]), len(group)))
    if dropped:
        lines[:] = [line for line in lines if id(line) not in dropped]
    return merged


def terms_from_slot(slot: dict[str, Any]) -> DeliveryTerms:
    return DeliveryTerms(
        base_cost=Decimal(str(slot.get("deliveryCost") or 0)),
        tiers=tuple(
            CostTier(
                cost=Decimal(str(tier["cost"])),
                from_order_cost=Decimal(str(tier["fromOrderCost"])),
            )
            for tier in slot.get("deliveryCostMap") or []
        ),
        min_order_cost=Decimal(str(slot.get("minOrderCost") or 0)),
        max_weight_kg=Decimal(str(slot.get("maxWeight") or 0)),
    )


def receipts_phrase(count: int) -> str:
    tail = count % 100
    if 11 <= tail <= 14:
        word = "чеків"
    elif count % 10 == 1:
        word = "чек"
    elif 2 <= count % 10 <= 4:
        word = "чеки"
    else:
        word = "чеків"
    return f"{count} {word}"


def qty_for_api(qty: Decimal, product: dict[str, Any]) -> float | int:
    if is_sold_by_weight(
        weighted=product.get("weighted"),
        ratio=str(product.get("displayRatio") or "") or None,
        step=_card_pack(product)[1],
    ):
        return int(qty) if qty == qty.to_integral_value() else float(qty)
    whole = max(1, int(qty.to_integral_value(rounding=ROUND_DOWN)))
    return whole


def _confidence(line: PlanLine) -> float:
    if line.from_history is None:
        return 0.5
    return 0.9 if line.from_history.receipts >= 3 else 0.7


def to_cart_line(line: PlanLine) -> CartLine:
    product = line.product
    old_price = product.get("oldPrice")
    hint = line.from_history
    unit, step = _sale_of(product)
    if line.explanation is not None:
        explanation = line.explanation
        reason = line.reason_code or Reason.FREQUENCY
    elif line.at_home:
        explanation = "схоже, ще є вдома"
        reason = Reason.AT_HOME
    elif line.auto_need:
        cycle = hint.cycle_days() if hint else None
        explanation = "закінчується за циклом" + (f" ~{cycle} дн" if cycle else "")
        reason = Reason.CYCLE
    elif line.history_matched and hint is not None:
        explanation = habit_reason(hint)
        reason = Reason.FREQUENCY
    else:
        explanation = "підібрано під намір зі списку"
        reason = Reason.FREQUENCY
    detail = line.reason
    if line.needs_approval:
        detail = (
            f"{explanation}. Погодь заміну або увімкни авто-заміну — інакше поїде "
            "без мандата, і збирач вирішить сам"
        )
        explanation = NEEDS_APPROVAL_NOTE
    return CartLine(
        external_product_id=str(product["externalProductId"]),
        name=product["name"],
        qty=Decimal(line.qty),
        unit=unit,
        step=step,
        price=line.price,
        base_price=Decimal(str(old_price)) if old_price else None,
        weight_kg=line_weight(product),
        image_url=product.get("image"),
        card_url=product_url(product.get("slug")),
        reason=reason,
        explanation=explanation,
        explanation_detail=detail,
        confidence=_confidence(line),
        at_risk=line.risky,
        needs_approval=line.needs_approval,
        chain=[
            Substitute(
                external_product_id=alt.external_product_id,
                name=alt.name,
                source=alt.source.value,
                price=alt.price,
                ratio=alt.ratio,
                by_weight=alt.by_weight,
            )
            for alt in line.chain
        ],
        mandate=line.mandate,
        mandate_ahead=line.ahead,
        decided=line.decided,
        swap_fork=(
            None
            if line.swap_fork is None
            else PriceFork(low=line.swap_fork.low, high=line.swap_fork.high, per=line.swap_fork.per)
        ),
        considered=considered_options(line),
        considered_total=line.considered_total,
        sliced=slicing.is_sliced(product["name"]),
        slicing_note=line.slicing_note,
        cheaper=(
            None
            if line.cheaper is None
            else Cheaper(
                external_product_id=str(line.cheaper["externalProductId"]),
                name=str(line.cheaper["name"]),
                price=Decimal(str(line.cheaper["price"])),
                saving=line.price - Decimal(str(line.cheaper["price"])),
            )
        ),
    )


def swap_option(
    product: dict[str, Any], *, same_kind: bool | None = None, kind: str | None = None
) -> SwapOption:
    ratio, step = _card_pack(product)
    return SwapOption(
        external_product_id=str(product["externalProductId"]),
        name=str(product["name"]),
        price=product.get("price") or 0,
        ratio=ratio,
        by_weight=is_sold_by_weight(weighted=product.get("weighted"), ratio=ratio, step=step),
        stock=product.get("stock"),
        available=bool(product.get("available")),
        image_url=product.get("image"),
        card_url=product_url(product.get("slug")),
        same_kind=same_kind,
        kind=kind,
        sliced=slicing.is_sliced(str(product["name"])),
    )


def considered_options(line: PlanLine) -> list[SwapOption]:
    options: list[SwapOption] = []
    for product in line.considered:
        try:
            options.append(swap_option(product))
        except (KeyError, TypeError, ValueError) as exc:
            log.warning("basket.considered_skipped", intent=line.intent, error=str(exc)[:120])
    return options


def weigh(lines: Sequence[PlanLine]) -> Estimate:
    return cart_weight((line.qty, line_weight(line.product)) for line in lines if not line.at_home)


def _split_note(lines: Sequence[PlanLine], max_weight_kg: Decimal) -> str:
    weighed: list[WeighedLine] = []
    unknown = 0
    for line in lines:
        if line.at_home:
            continue
        unit = line_weight(line.product)
        if unit is None:
            unknown += 1
            continue
        weighed.append(
            WeighedLine(
                external_product_id=str(line.product.get("externalProductId") or ""),
                qty=line.qty,
                unit_weight_g=int(unit * GRAMS_IN_KG),
            )
        )
    if unknown:
        return "одним замовленням це не поїде — зніми щось або бери два вікна"
    try:
        shipments = split_by_weight(weighed, max_weight_kg)
    except ValueError as exc:
        log.warning("basket.split_failed", error=str(exc)[:120])
        return "одним замовленням це не поїде — зніми щось або бери два вікна"
    return f"одним замовленням це не поїде: рейсів за вагою — {len(shipments)}"


def _norm_all(names: Sequence[str]) -> list[str]:
    return [norm_name(name) for name in names]


def _replace_pieces(intents: Sequence[str], *, was: Sequence[str], now: Sequence[str]) -> list[str]:
    gone = set(_norm_all(was))
    out: list[str] = []
    placed = False
    for intent in intents:
        if norm_name(intent) in gone:
            if not placed:
                out.extend(now)
                placed = True
            continue
        out.append(intent)
    if not placed:
        out = list(now) + out
    return dedupe(out)


async def assemble_list(
    mcp: SilpoMCP,
    llm: Any,
    request: BuildRequest,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
    place: Location | None = None,
    marks: Mapping[str, datetime] | None = None,
    cycles: Mapping[str, int] | None = None,
    manual: Mapping[str, str] | None = None,
    wanted: Mapping[str, str] | None = None,
    saved_chains: Mapping[str, tuple[str, ...]] | None = None,
    pool: DictPool | None = None,
    account: str = "",
    on_step: Callable[[TraceStep], None] | None = None,
    answer_of: Callable[[str, float], Awaitable[str | None]] | None = None,
    drinks: Mapping[str, DrinkKind] | None = None,
) -> Assembled:
    cfg = settings if settings is not None else _default_settings
    moment = now or datetime.now(UTC)
    list_intents = [
        intent
        for part in request.shopping_list
        if (intent := part.strip()) and norm_name(intent) not in STOP_WORDS
    ]
    said = {kind_key(answer.intent): answer for answer in request.answers}
    skipped_kinds = {key for key, answer in said.items() if answer.skip}
    list_intents = [intent for intent in list_intents if kind_key(intent) not in skipped_kinds]

    trace = Tracer(on_step)

    occasion = occasion_of(request.mode, request.occasion_people, request.event_style)

    delivery_type = delivery_type_for(request.delivery)

    from komora.agent import steps

    facts = Facts({"address": place, "delivery_types": place.branches} if place is not None else {})
    ground = steps.Ground(
        mcp=mcp,
        cfg=cfg,
        moment=moment,
        facts=facts,
        trace=trace,
        pool=pool,
        account=account,
        delivery_type=delivery_type,
        llm=llm,
    )
    runner = Executor(
        facts,
        plan=validate(
            [
                name
                for name in (*BEFORE_PLAN, *CORE_AFTER_PLAN[Aim.BASKET])
                if place is None or name not in {"place.address", "place.delivery_types"}
            ],
            writes_allowed=False,
        ),
        trace=trace,
        writes_allowed=False,
        fatal=(TokenRejected, AssemblyError),
        meter=Meter.of(llm),
    )
    placing = steps.Place(ground, known=place)
    await runner.run_all(
        ["place.address", "place.delivery_types"],
        placing.address,
        step_id="step-address",
        tool=steps.place.ADDRESSES_TOOL,
    )
    await runner.run("place.cart", placing.read, step_id="step-cart", tool=steps.place.CART_TOOL)
    await runner.run(
        "place.decide", placing.settle, step_id="step-place", tool=steps.place.TYPES_TOOL
    )
    branch_id = placing.branch_id
    feedback = placing.feedback

    slotting = steps.Slots(ground)
    await runner.run_all(
        ["slot.list", "slot.pick"],
        slotting.choose,
        step_id="step-slots",
        tool=steps.slot.SLOTS_TOOL,
    )
    slot = facts.get("slot")
    slot_note = slotting.note

    hours_to_slot = hours_until(slot.get("start"), now=moment)
    slot_day = day_of(slot.get("start"), now=moment)

    executed: set[str] = set()

    tools_live: list[dict[str, Any]] = []

    async def _plan():
        nonlocal tools_live
        tools_live = await describe_tools(mcp)
        return await plan_run(
            llm,
            source="list",
            writes=True,
            budget=request.budget is not None,
            known=facts_of(BEFORE_PLAN),
            tools=tools_live,
            goal=(
                f"кошик {occasion.label}"
                + (f" на {request.budget} грн" if request.budget is not None else "")
                + (
                    " з потреб за чеками і списку гостя"
                    if occasion.takes_cycles
                    else " рівно зі списку гостя, без потреб за чеками"
                )
            ),
        )

    reading = steps.History(ground, marks=marks, cycles=cycles)
    _, planned = await asyncio.gather(
        runner.run_all(
            ["history.receipts", "history.orders", "history.model"],
            reading.read,
            step_id="step-history",
            tool=steps.history.RECEIPTS_TOOL,
        ),
        _plan(),
    )
    runner.adopt(planned.plan)
    history, receipts, sizes, web = reading.items, reading.receipts, reading.sizes, reading.web
    if "history" not in facts or web is None:
        raise AssemblyError("історію покупок не прочитано — збирати нема з чого")

    trace.add(
        "step-plan",
        "agent.plan",
        {
            "кроків": len(planned.plan.steps),
            "джерело": planned.plan.source,
            "спроб": planned.attempts,
            "токенів": planned.tokens,
            "описи": planned.tools_note,
            "план": describe_plan(planned.plan),
        },
        f"{planned.note}: {len(planned.plan.steps)} "
        f"{plural(len(planned.plan.steps), 'крок', 'кроки', 'кроків')}",
        duration_ms=planned.duration_ms,
        prompt=planned.prompt,
        decision="який крок і в якому порядку — рішення моделі; інваріанти (слот "
        "від «зараз», перечитування після запису, дозвіл на запис) — сталі правила",
        tag="план моделі" if planned.plan.source == "model" else "план з коду",
        tag_tone="good" if planned.plan.source == "model" else "muted",
    )

    composing = steps.Compose(
        ground,
        request=request,
        occasion=occasion,
        said=list_intents,
        sizes=sizes,
        marks=marks,
        manual=manual,
        wanted=wanted,
        drinks=drinks or {},
        usual=(
            Decimal(str(spend_target(web.paid).target)) if web is not None and web.paid else None
        ),
    )
    await runner.run(
        "intents.compose", composing.compose, step_id="step-intents", tool="core.intents"
    )
    if composing.stretched is not None and composing.stretched.refused is None:
        request = request.model_copy(update={"budget": composing.stretched.target})
    if "intents" not in facts:
        raise AssemblyError("наміри не склались — збирати нема чого")
    auto_intents = composing.auto_intents
    beats = composing.beats
    by_article = composing.by_article
    siblings = siblings_of(auto_intents, list(by_article.values()), composing.named_all)
    fill_intents = composing.fill_intents
    fill_note = composing.fill_note
    intents = composing.intents
    kept_articles = composing.kept_articles
    kinds = composing.kinds
    manual_intents = composing.manual_intents
    occasion_intents = composing.occasion_intents
    postponed = composing.postponed
    promo_due = composing.promo_due
    promo_intents = composing.promo_intents
    promo_kinds = composing.promo_kinds
    rare = composing.rare
    ripe_names = composing.ripe_names
    silent_intents = composing.silent_intents
    wanted_intents = composing.wanted_intents

    insight = Understanding(failure="модель не підключена")
    if llm is not None:
        thinking = asyncio.ensure_future(
            understand_task(
                llm,
                occasion,
                intents=intents,
                said=list_intents,
                typed=request.list_text,
                rules=list(request.rules),
                known=list(auto_intents),
                tracked=kinds,
                wanted=list(wanted_intents),
                steps=sorted(PLAN_GATED),
            )
        )
        candidates, search_ms = await search_products(mcp, intents, slot, branch_id)
        insight = await thinking
    else:
        candidates, search_ms = await search_products(mcp, intents, slot, branch_id)
    executed.add("shelf.search")
    facts.put("candidates", candidates, step="shelf.search")

    recut: list[str] = []
    if insight.cut and _norm_all(insight.cut) != _norm_all(list_intents):
        recut = [name for name in insight.cut if name not in intents]
        intents = _replace_pieces(intents, was=list_intents, now=list(insight.cut))
        list_intents = list(insight.cut)
    if recut:
        more, more_ms = await search_products(mcp, recut, slot, branch_id)
        candidates.update(more)
        search_ms += more_ms

    understand_intents: dict[str, str] = {}
    for change in insight.dropped:
        auto_intents.pop(change.intent, None)
        occasion_intents.pop(change.intent, None)
        fill_intents.pop(change.intent, None)
        if change.intent in intents:
            intents.remove(change.intent)
    for change in insight.added:
        if any(same_kind(change.intent, known) for known in intents):
            continue
        intents.append(change.intent)
        understand_intents[change.intent] = change.why or "агент докинув під цю задачу"
    rescued: list[str] = []
    if insight.ignored:
        found, found_ms = await search_products(mcp, list(insight.ignored), slot, branch_id)
        search_ms += found_ms
        for phrase in insight.ignored:
            hits = found.get(phrase, [])
            if not shelf_recognises(phrase, hits):
                continue
            if any(same_kind(phrase, known) for known in intents):
                continue
            intents.append(phrase)
            candidates[phrase] = hits
            rescued.append(phrase)
            understand_intents[phrase] = "набране тобою: модель не впізнала товар, полиця впізнала"
    for item in insight.plan:
        runner.move(item.change, item.step)
    facts.put("intents", intents, step="agent.understand")
    trace.add(
        "step-understand",
        insight.model or "agent.understand",
        {
            "питань": len(insight.questions),
            "переріз тексту": len(insight.cut),
            "не взяв із тексту": list(insight.ignored),
            "полиця впізнала": rescued,
            "докинув": len(insight.added),
            "зняв": len(insight.dropped),
            "токенів": insight.tokens,
            "питання": [question.ask for question in insight.questions],
            "наміри": {
                "докинув": [change.intent for change in insight.added],
                "зняв": [
                    f"{change.intent}: {change.why}" if change.why else change.intent
                    for change in insight.dropped
                ],
            },
            "правки плану": [f"{item.change} {item.step}" for item in insight.plan],
            "відкинуто": list(insight.thrown),
        },
        insight.note() + (f"; відкинуто {len(insight.thrown)}" if insight.thrown else ""),
        duration_ms=insight.duration_ms or None,
        decision="що спитати і що докинути — рішення агента; стелі, різ і час очікування — сталі",
        tag=(
            "не спрацював"
            if insight.failure
            else f"+{len(insight.added)}"
            if insight.added
            else "питаю"
            if insight.questions
            else "без змін"
        ),
        tag_tone="warn" if insight.failure else ("good" if insight.touched else "muted"),
    )
    if understand_intents:
        more, more_ms = await search_products(mcp, list(understand_intents), slot, branch_id)
        candidates.update(more)
        search_ms += more_ms

    asked_questions = insight.questions if answer_of is not None else ()
    for question in asked_questions:
        trace.add(
            "step-ask",
            "agent.understand",
            {"питання": question.ask, "варіантів": len(question.options)},
            f"питаю гостя: {question.ask}" + (f" — {question.why}" if question.why else ""),
            decision="збірка тим часом іде далі: відповідь ще встигне змінити вибір",
            tag="питання",
            tag_tone="warn",
            question=TraceQuestion(
                id=question.id,
                ask=question.ask,
                why=question.why or None,
                options=[
                    TraceOption(id=option.id, label=option.label, style=option.style)
                    for option in question.options
                ],
                wait_s=int(ANSWER_WAIT_S),
            ),
        )
    if insight.questions and answer_of is None:
        trace.add(
            "step-ask",
            "agent.understand",
            {"питань": len(insight.questions)},
            f"агент хотів спитати {len(insight.questions)}, але каналу для "
            "відповіді немає — збираю без діалогу",
            tag="без діалогу",
            tag_tone="muted",
        )

    shelf = steps.Shelf(
        ground,
        candidates=candidates,
        auto_intents=auto_intents,
        siblings=siblings,
        read_whole=frozenset(insight.cut),
    )
    await runner.run(
        "shelf.by_article",
        shelf.by_article,
        step_id="step-article",
        tool=steps.shelf.SEARCH_TOOL,
    )

    heard = steps.Heard(ground, answer_of=answer_of, questions=asked_questions)
    await runner.run(
        "shelf.search",
        lambda bound: shelf.search(
            bound,
            heard=heard,
            occasion=occasion,
            said=said,
            history=history,
            ripe_names=ripe_names,
            spent_ms=search_ms,
        ),
        step_id="step-batch",
        tool=steps.shelf.SEARCH_TOOL,
    )
    occasion = heard.occasion or occasion
    guest_answers = heard.said
    intents = facts.get("intents")
    hints, hints_all = shelf.hints, shelf.hints_all
    answered, dropped = shelf.answered, shelf.dropped
    chosen_nodes, clarified, probed = shelf.chosen_nodes, shelf.clarified, shelf.probed
    narrowed, tree, stray = shelf.narrowed, shelf.tree, shelf.stray
    if shelf.kind_done:
        executed.add("shelf.kind")

    kinds_map: dict[str, frozenset[str]] = {}
    kinds_why = "карти видів немає: без бази ярус вимкнено — читання не було"
    catalog_ms: int | None = None
    if pool is not None:
        catalog_started = monotonic()
        asked = {
            str(product["externalProductId"]) for found in candidates.values() for product in found
        } | {str(hint.lager_id) for found in hints_all.values() for hint in found}
        try:
            kinds_map = await catalog_store.load(pool, sorted(asked))
            known = len(kinds_map)
            kinds_why = (
                f"артикулів спитано {len(asked)}, вузол відомий у {known}"
                if known
                else f"артикулів спитано {len(asked)}, у карті НЕМАЄ жодного "
                "(крон ще не ходив або каталог змінився)"
            )
        except Exception as exc:
            kinds_why = f"карта видів не прочиталась: {str(exc)[:80]}"
        catalog_ms = round((monotonic() - catalog_started) * 1000)
    trace.add(
        "step-kinds",
        "catalog_nodes",
        {"артикулів": len(kinds_map)},
        kinds_why,
        duration_ms=catalog_ms,
        decision="вузол дерева -- ярус, а не вето: перетин буває порожнім і на "
        "правильному наборі, тож порядок він міняє, а кандидатів не знімає",
        tag=None if kinds_map else "ярус не спрацював",
        tag_tone="muted",
    )

    guest_rules = list(request.rules) + guest_answers
    chosen_skills = core_skills.select(
        guest_rules,
        occasion_mode=str(occasion.mode) if occasion is not None else "",
        occasion_phrase=occasion.phrase() if occasion is not None and occasion.named else "",
        intents=intents,
        promo_kinds=promo_kinds,
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
    skills_text = skill_texts.block(chosen_skills.skills)
    skill_fields = {skill.name: skill_texts.fields(skill.name) for skill in chosen_skills.skills}
    trace.add(
        "step-skills",
        "core.skills",
        {
            "скілів": len(chosen_skills.skills),
            "правил": len(request.rules),
            "поля": {name: list(named) for name, named in skill_fields.items()},
            "чому": chosen_skills.phrase(skill_fields),
        },
        chosen_skills.note(),
        decision="інструкція за тригером: кошик без правил і без приводу дістає "
        "рівно той промпт, що й до скілів",
        tag=f"+{len(chosen_skills.skills)}" if chosen_skills.skills else "жодного",
        tag_tone="good" if chosen_skills.skills else "muted",
    )

    async def _ask(decidable: list[str]):
        return await agent_picks(
            llm,
            decidable,
            candidates,
            hints_all,
            guest_rules,
            also_in={
                pid: titles for kind in narrowed.values() for pid, titles in kind.also_in.items()
            },
            readings={word: kind.readings for word, kind in narrowed.items() if kind.readings},
            answers={
                intent: clarified.get(intent)
                or probed.get(intent)
                or (narrowed[intent].title if intent in narrowed else "")
                for intent in answered
                if intent not in dropped
            },
            budget=Decimal(str(request.budget)) if request.budget is not None else None,
            auto_intents=frozenset(auto_intents),
            kinds=kinds_map,
            occasion=occasion,
            occasion_intents=occasion_intents,
            owned=by_article,
            batches=core_models.batches_for(
                getattr(llm, "model", "") or "",
                fast=request.fast,
                fallback=cfg.pick_batches,
            ),
            skills=skills_text,
            on_batch=_tell_batch,
        )

    def _tell_batch(number: int, of: int, names: list[str]) -> None:
        if of < 2:
            return
        shown = ", ".join(names[:3]) + ("…" if len(names) > 3 else "")
        trace.add(
            "step-pick-batch",
            "model",
            {"пачка": f"{number} з {of}", "обрано": names},
            f"пачка {number} з {of} відповіла: обрано {len(names)}"
            + (f" — {shown}" if shown else ""),
            tag_tone="muted",
        )

    deciding = steps.Decide(ground, shelf=shelf, llm=llm)
    await runner.run(
        "decide.pick",
        lambda bound: deciding.pick(bound, ask=_ask),
        step_id="step-agent",
        tool=steps.decide.TOOL,
    )
    picks, expendable = deciding.picks, deciding.expendable
    model_used = deciding.model_used

    questions: list[Clarification] = []
    pending: set[str] = set()
    deferred: list[str] = []
    clarify_ms: int | None = None
    ask_report: list[tuple[str, Asked]] = []
    asked_cards: dict[str, dict[str, Any]] = {}
    taken_own: list[tuple[str, dict[str, Any]]] = []
    asked_kinds: dict[str, str] = {}
    merged_asks: list[tuple[str, str]] = []
    for intent, pick in picks.items():
        ask = str(pick.get("ask") or "").strip()
        if not ask or intent in answered:
            continue
        own = fresh_own(intent, candidates.get(intent, []), by_article)
        if own is not None:
            item = by_article[str(own["externalProductId"])]
            pick["ask"] = ""
            pick["chosen_id"] = str(own["externalProductId"])
            pick["qty"] = item.typical_qty
            pick["why"] = OWN_PICK
            taken_own.append((intent, own))
            continue
        kind = ask_kind(intent, ripe_names)
        if (owner := asked_kinds.get(kind)) is not None:
            pending.add(intent)
            merged_asks.append((intent, owner))
            continue
        if len(questions) >= MAX_QUESTIONS:
            pending.add(intent)
            deferred.append(intent)
            postponed.append(
                (
                    Remedy.NEXT_RUN,
                    Postponed(
                        intent=intent,
                        reason=f"двоякий намір понад стелю {MAX_QUESTIONS} питань — "
                        "спитаю наступним прогоном",
                    ),
                )
            )
            continue
        asked = Asked()
        if tree is not None:
            asked = await clarify_options(
                mcp,
                intent,
                ask=ask,
                tree=tree,
                slot=slot,
                branch_id=branch_id,
                wanted=[str(item) for item in (pick.get("ask_options") or [])],
                search=search_products,
            )
            clarify_ms = (clarify_ms or 0) + asked.spent_ms
        taken_names = [
            product["name"]
            for other, other_pick in picks.items()
            if other != intent
            for product in candidates.get(other, [])
            if str(product.get("externalProductId")) == str(other_pick.get("chosen_id") or "")
        ]
        options: tuple[Option, ...] = tuple(
            option
            for option in asked.options
            if not any(same_kind(option.title, name) for name in taken_names)
        )
        ask_report.append((intent, asked))
        pending.add(intent)
        shown_picks = (
            [
                ClarifyPick(
                    external_product_id=str(product["externalProductId"]),
                    name=product["name"],
                    price=product["price"],
                    ratio=product.get("displayRatio"),
                    by_weight=is_sold_by_weight(
                        weighted=product.get("weighted"),
                        ratio=product.get("ratio"),
                        step=_card_pack(product)[1],
                    ),
                )
                for product in _ask_picks(intent, candidates.get(intent, []))
            ]
            if not options
            else []
        )
        asked_cards.update(
            {
                str(product["externalProductId"]): product
                for product in _ask_picks(intent, candidates.get(intent, []))
            }
            if not options
            else {}
        )
        questions.append(
            Clarification(
                intent=intent,
                question=ask,
                options=[
                    ClarifyOption(
                        title=item.title,
                        slug=item.slug,
                        query=item.query or None,
                        count=item.count,
                        price_from=item.price_from,
                        by_weight=item.by_weight,
                    )
                    for item in options
                ],
                picks=shown_picks,
            )
        )
        asked_kinds[kind] = intent
    if taken_own:
        trace.add(
            "step-own",
            "core.history",
            {
                "знято питань": len(taken_own),
                "взято": [
                    f"«{intent}» → {own['name']} "
                    f"({by_article[str(own['externalProductId'])].recent_receipts} свіжих чеків)"
                    for intent, own in taken_own
                ],
            },
            f"замість питання беру свій свіжий артикул того ж виду: "
            f"{len(taken_own)} {plural(len(taken_own), 'намір', 'наміри', 'намірів')}",
            decision="свіжість чеків важить: те, що ти береш останнім часом під "
            "іншою назвою того ж виду, сильніше за питання",
            tag=f"-{len(taken_own)} питань",
            tag_tone="good",
        )
    if occasion.mode is BuildMode.EVENT and composing.bar_items:
        bar_items = composing.bar_items[:BAR_ASK_TAKE]
        found, _bar_ms = await search_products(
            mcp, [str(item.lager_id) for item in bar_items], slot, branch_id
        )
        bar_picks: list[ClarifyPick] = []
        for item in bar_items:
            for product in found.get(str(item.lager_id), []):
                if str(product.get("externalProductId")) != str(item.lager_id):
                    continue
                asked_cards[str(product["externalProductId"])] = product
                bar_picks.append(
                    ClarifyPick(
                        external_product_id=str(product["externalProductId"]),
                        name=product["name"],
                        price=product["price"],
                        ratio=product.get("displayRatio"),
                        by_weight=is_sold_by_weight(
                            weighted=product.get("weighted"),
                            ratio=product.get("ratio"),
                            step=_card_pack(product)[1],
                        ),
                    )
                )
                break
        if bar_picks:
            questions.append(
                Clarification(
                    intent=BAR_ASK_INTENT,
                    question="Що з бару поставити на стіл?",
                    options=[],
                    picks=bar_picks,
                )
            )
        trace.add(
            "step-bar-ask",
            "core.bar",
            {"з бару": len(bar_items), "на полиці": len(bar_picks)},
            f"питаю про бар: на полиці {len(bar_picks)} з {len(bar_items)} твоїх напоїв"
            if bar_picks
            else f"про бар не питаю: жодного з {len(bar_items)} твоїх напоїв на полиці немає",
            decision="напої під подію обирає гість зі свого бару, а не модель здогадом",
            tag="бар" if bar_picks else "бар: нема",
            tag_tone="good" if bar_picks else "muted",
        )
    if questions:
        executed.add("decide.clarify")
        trace.add(
            "step-ask",
            "агент",
            {
                "питань": len(questions),
                "відкладено": len(deferred),
                "варіантів": sum(len(q.options) for q in questions),
                "знято повторів слова": sum(item.tautology for _, item in ask_report),
                "знято не на осі питання": sum(item.off_axis for _, item in ask_report),
                "відпало порожніх": sum(item.empty for _, item in ask_report),
                "питання": [f"«{q.intent}» — {q.question}" for q in questions],
                "поза стелею": list(deferred),
                "злито в сусіднє": [f"«{intent}» -> «{owner}»" for intent, owner in merged_asks],
                "звідки варіанти": [f"«{intent}» — {item.note}" for intent, item in ask_report],
            },
            f"чекає на уточнення: {len(questions)} "
            + plural(len(questions), "питання", "питання", "питань")
            + f", {sum(len(q.options) for q in questions)} "
            + plural(sum(len(q.options) for q in questions), "варіант", "варіанти", "варіантів")
            + (
                f"; ще {len(deferred)} поза стелею {MAX_QUESTIONS} — наступним прогоном"
                if deferred
                else ""
            )
            + (f"; злито в сусіднє питання: {len(merged_asks)}" if merged_asks else ""),
            duration_ms=clarify_ms,
            decision="варіанти називає той, хто ставить питання, а полицею їх "
            "перевіряє код: чип, який повторює слово гостя або відповідає не "
            "на ту вісь, відповіддю не є",
            tag=f"{len(questions)} питань" + (f" +{len(deferred)}" if deferred else ""),
            tag_tone="warn",
        )

    merged_intents: set[str] = set()

    async def _build():
        return build_lines(
            [intent for intent in intents if intent not in pending],
            candidates,
            hints,
            picks,
            proven={
                word: frozenset(str(product["externalProductId"]) for product in kind.products)
                for word, kind in narrowed.items()
                if kind.products
            },
            kinds=kinds_map,
            answered=frozenset(chosen_nodes) | frozenset(probed),
            auto_swap=request.auto_swap,
            auto_swap_percent=request.auto_swap_percent,
            auto_intents=frozenset(auto_intents),
            habits={intent: _slicing_habit(matches) for intent, matches in hints_all.items()},
            owned=by_article,
            siblings=siblings,
            swaps={str(s.external_product_id): s for s in request.swaps},
            must_match=kept_articles,
            occasion_intents=occasion_intents,
            refusals_stand=occasion.mode is BuildMode.EVENT,
            rules_given=bool(guest_rules),
            silent_intents=silent_intents,
            fill_intents=fill_intents,
            manual_intents={**manual_intents, **wanted_intents},
            saved_chains=saved_chains,
            hours_to_slot=hours_to_slot,
            slot_day=slot_day,
            trace=trace,
        )

    await runner.run(
        "decide.chain",
        lambda bound: deciding.chain(bound, build=_build),
        step_id="step-lines",
        tool="core.list",
    )
    lines, unresolved, declined = deciding.lines, deciding.unresolved, deciding.declined

    merged_intents |= deciding.collapse()

    executed.add("decide.chain")
    facts.put("lines", lines, step="decide.chain")

    before_twins = {line.intent for line in lines}
    sections = await _sections_of(pool, lines, kinds_map)
    await runner.run(
        "decide.twins",
        lambda bound: deciding.twins(
            bound,
            ask=lambda pairs: ask_twins(llm, pairs),
            phrases=shelf.kind_phrases,
            kinds={intent: kind_key(intent) for intent in intents},
            sections=sections,
        ),
        step_id="step-twins",
        tool="агент",
    )
    executed.add("decide.twins")
    twins_gone = sorted(before_twins - {line.intent for line in lines})
    merged_intents |= set(twins_gone)

    async def _loop_search(queries: list[str]) -> dict[str, list[dict[str, Any]]]:
        found, _ms = await search_products(mcp, queries, slot, branch_id)
        return found

    async def _loop_similar(slug: str) -> list[dict[str, Any]]:
        outcome = await mcp.call(
            "silpo_get_similar_products",
            {
                "branchId": branch_id,
                "deliveryType": slot["deliveryType"],
                "timeslotStart": slot["start"],
                "timeslotEnd": slot["end"],
                "slug": slug,
                "limit": 10,
            },
        )
        payload = outcome.payload_raw
        rows = payload.get("products") or payload.get("items") or []
        return [row for row in rows if isinstance(row, dict)]

    def _loop_lines(
        found: list[str],
        seen: dict[str, list[dict[str, Any]]],
        picks: dict[str, dict[str, Any]],
    ) -> list[PlanLine]:
        more, _still, _declined_again = build_lines(
            found,
            seen,
            hints,
            picks,
            kinds=kinds_map,
            auto_swap=request.auto_swap,
            auto_swap_percent=request.auto_swap_percent,
            auto_intents=frozenset(auto_intents),
            owned=by_article,
            siblings=siblings,
            swaps={str(s.external_product_id): s for s in request.swaps},
            occasion_intents=occasion_intents,
            refusals_stand=occasion.mode is BuildMode.EVENT,
            rules_given=bool(guest_rules),
            silent_intents=silent_intents,
            fill_intents=fill_intents,
            manual_intents={**manual_intents, **wanted_intents},
            saved_chains=saved_chains,
            hours_to_slot=hours_to_slot,
            slot_day=slot_day,
        )
        return more

    if llm is not None and unresolved:
        deciding.unresolved, deciding.declined = unresolved, declined
        await runner.run(
            "decide.loop",
            lambda bound: deciding.loop(
                bound,
                listed=list_intents,
                hints=hints,
                history=hints_all,
                tools=tools_live,
                search=_loop_search,
                similar=_loop_similar,
                build=_loop_lines,
                why=LOOP_PICK,
                skills=skills_text,
            ),
            step_id="step-loop",
            tool="агент",
        )
        unresolved, declined = deciding.unresolved, deciding.declined

    if llm is not None:
        loop_works: dict[str, tuple[Any, str, str]] = {
            "decide.pick": (
                lambda bound, labels=(): deciding.pick(bound, ask=_ask, labels=labels),
                "step-agent",
                "агент",
            ),
            "decide.chain": (
                lambda bound: deciding.chain(bound, build=_build),
                "step-lines",
                "core.list",
            ),
            "decide.loop": (
                lambda bound, labels=(): deciding.loop(
                    bound,
                    listed=list_intents,
                    hints=hints,
                    history=hints_all,
                    tools=tools_live,
                    search=_loop_search,
                    similar=_loop_similar,
                    build=_loop_lines,
                    why=LOOP_PICK,
                    skills=skills_text,
                    labels=labels,
                ),
                "step-loop",
                "агент",
            ),
        }
        outside: list[str] = []

        async def _resolve(batch: Plan):
            nonlocal lines, unresolved, declined, merged_intents
            for step in batch.steps:
                entry = loop_works.get(step.name)
                if entry is None:
                    outside.append(step.name)
                    continue
                work, step_id, tool = entry
                if step.name in ADDRESSED_LOOP:
                    work = partial(work, labels=step.labels)
                await runner.run(step.name, work, step_id=step_id, tool=tool)
            merged_intents |= deciding.collapse()
            lines, unresolved, declined = deciding.lines, deciding.unresolved, deciding.declined
            return runner.carried

        def _left() -> tuple[str, ...]:
            judged = resolution_goal(
                intents,
                addressed={
                    "рядок кошика": [line.intent for line in lines],
                    "питання гостю": [question.intent for question in questions],
                    "злито в сусідній рядок": sorted(merged_intents),
                },
            )
            return tuple(duty.why or duty.name for duty in judged.unmet)

        def _state() -> dict[str, Any]:
            total = sum((line.total for line in lines), Decimal(0))
            said: dict[str, Any] = {
                "кроки оберту": ", ".join(sorted(loop_works)),
                "намірів": len(facts.get("intents") or ()),
                "рядків кошика": len(lines),
                "зібрано, грн": f"{total:.0f}",
                "питань гостю": len(questions),
                "привід": occasion.phrase(),
            }
            if unresolved:
                said["не знайшлось"] = list(unresolved)
            if declined:
                said["агент не взяв"] = list(declined)
            if request.budget is not None:
                named = Decimal(str(request.budget))
                edges = budget_band(named)
                said["межа, грн"] = f"{named:.0f}"
                said["коридор, грн"] = f"{edges.low:.0f}-{edges.high:.0f}"
                said["до межі різу, грн"] = f"{named - total:.0f}"
            return said

        spun = await spin(
            plan=lambda soil: plan_batch(
                llm,
                soil,
                source="list",
                writes=False,
                budget=request.budget is not None,
                tools=tools_live,
                goal="довести решту намірів до рядка кошика або до питання гостю",
                aim=Aim.BASKET,
                state=_state(),
                labels=list(facts.get("intents") or ()),
            ),
            run=_resolve,
            facts=facts,
            duties=_left,
            verdict=lambda _carried: None,
            refused=lambda: tuple(f"{item.name}: {item.why}" for item in runner.refused),
            ceiling=BASKET_TURNS,
            obey_stop=True,
            on_turn=lambda turn: tell_turn(trace, turn, step_id="step-turn", owed=_left()),
        )
        trace.add(
            "step-spin",
            "code",
            {
                "причина": spun.reason.name.lower(),
                "обертів": len(spun.turns),
                "викликів моделі": spun.calls,
                "токенів": spun.tokens,
                "кроки обертів": [", ".join(turn.executed) or "нічого" for turn in spun.turns],
                **({"поза набором": outside} if outside else {}),
            },
            f"петля добору спинилась: {spun.reason.value} ({len(spun.turns)} "
            f"{plural(len(spun.turns), 'оберт', 'оберти', 'обертів')}, "
            f"{spun.duration_ms / 1000:.1f} с)",
            decision="що робити з рештою намірів -- рішення моделі: вона бачить "
            "невиконане і сама каже, коли досить; набір кроків і стеля сталі",
            tag="мета" if spun.reason is Halt.DONE else spun.reason.name.lower(),
            tag_tone="good" if spun.reason is Halt.DONE else "warn",
        )

    shelf_promo: list[str] = []
    for intent, item in auto_intents.items():
        if intent in promo_intents:
            continue
        own = next(
            (
                product
                for product in candidates.get(intent, ())
                if str(product.get("externalProductId") or "") == item.lager_id
                or web_article(str(product.get("name") or "")) == item.lager_id
            ),
            None,
        )
        if own is None:
            continue
        proven = item.promo_at(regular_of(own))
        if not proven.mostly:
            continue
        promo_intents[intent] = proven
        promo_due[intent] = item
        promo_kinds += 1
        shelf_promo.append(intent)

    riding_promo: list[str] = []
    waiting_promo: list[str] = []
    if promo_intents:
        kept_promo: list[PlanLine] = []
        for line in lines:
            promo = promo_intents.get(line.intent)
            if promo is None:
                kept_promo.append(line)
                continue
            if on_sale(line.product):
                if promo.usual_qty is not None and _sale_of(line.product)[1] is None:
                    line.qty = Decimal(min(MAX_LINE_QTY, int(promo.usual_qty)))
                line.explanation = (
                    f"береш по акції ({promo.discounted} з {promo.purchases}) — "
                    f"зараз акція: {sale_phrase(line.product)}"
                )
                line.promo = True
                riding_promo.append(str(line.product["name"]))
                kept_promo.append(line)
                continue
            waiting_promo.append(line.intent)
            postponed.append(
                (
                    Remedy.PROMO,
                    Postponed(
                        intent=line.intent,
                        reason=PROMO_WAIT_WHY,
                        estimate=line.from_history.typical_cost if line.from_history else None,
                        refillable=False,
                    ),
                )
            )
        lines[:] = kept_promo
        held = [
            intent
            for intent in unresolved
            if intent in promo_intents
            and any(
                str(product["externalProductId"]) == promo_due[intent].lager_id
                and not on_sale(product)
                for product in candidates.get(intent, [])
            )
        ]
        if held:
            unresolved = [intent for intent in unresolved if intent not in held]
            declined = {i: why for i, why in declined.items() if i not in held}
            waiting_promo.extend(held)
            postponed.extend(
                (
                    Remedy.PROMO,
                    Postponed(
                        intent=intent,
                        reason=PROMO_WAIT_WHY,
                        estimate=promo_due[intent].typical_cost,
                        refillable=False,
                    ),
                )
                for intent in held
            )
    if promo_kinds:
        trace.add(
            "step-promo",
            "core.promo",
            {
                "по акції": promo_kinds,
                "час": len(promo_intents),
                "акція на полиці": len(riding_promo),
                "види": list(promo_intents),
                "доведено полицею": shelf_promo,
            },
            f"по акції береш {promo_kinds} {plural(promo_kinds, 'вид', 'види', 'видів')}"
            + (
                f"; час брати {len(promo_intents)}"
                if promo_intents
                else "; жодному ще не час — брав нещодавно"
            )
            + (f"; {len(shelf_promo)} довела полиця, не чек" if shelf_promo else "")
            + (
                f"; акція є на {len(riding_promo)} — беру акційною кількістю"
                if riding_promo
                else ""
            )
            + (f"; без акції {len(waiting_promo)} — чекають" if waiting_promo else ""),
            decision="без акції ти цього не береш — за повну ціну не кладу "
            "і в «не знайшлось» не пишу",
            tag=(
                f"+{len(riding_promo)}"
                if riding_promo
                else ("чекає акції" if waiting_promo else "не час")
            ),
            tag_tone="good" if riding_promo else "muted",
        )

    unresolved = deciding.refusals(unresolved, declined)

    missing = [
        intent for intent in unresolved if intent in auto_intents or intent in occasion_intents
    ]
    unresolved = [intent for intent in unresolved if intent not in missing]
    for intent in missing:
        item = auto_intents.get(intent)
        beat = beats.get(item.lager_id) if item is not None else None
        postponed.append(
            (
                Remedy.SHELF,
                Postponed(
                    intent=intent,
                    reason=(
                        "до приводу"
                        if item is None
                        else "береш по акції"
                        if intent in promo_intents
                        else "давно не брав"
                        if beat is not None and beat.trust is Trust.SILENT
                        else "закінчилось"
                    )
                    + ", але на цей слот у «Сільпо» його не знайшлось",
                    estimate=item.typical_cost if item is not None else None,
                    refillable=False,
                ),
            )
        )
    if missing:
        trace.add(
            "step-missing",
            "core.cycles",
            {"намірів": len(intents), "без товару": len(missing), "види": list(missing)},
            f"закінчилось, але на полиці цього слота не знайшлось: {len(missing)}",
            decision="мовчазна втрата потреби нерозрізненна з «більше нічого "
            "не закінчилось» — тому вона на екрані",
            tag=f"-{len(missing)} поз.",
            tag_tone="warn",
        )
    not_collected = [
        intent
        for intent in unresolved
        if (intent in narrowed and narrowed[intent].empty) or intent in stray
    ]
    unresolved = [intent for intent in unresolved if intent not in not_collected]
    if not lines and not questions:
        if not unresolved and declined:
            raise AssemblyError(
                "агент не взяв жодної позиції: "
                + "; ".join(f"«{intent}» — {why}" for intent, why in declined.items())
                + " — зніми правило або назви іншу фасовку"
            )
        raise AssemblyError(
            "нічого не знайшлось за списком: "
            + ", ".join(f"«{intent}»" for intent in unresolved)
            + " — спробуй назвати конкретніше"
            if unresolved
            else "звичне з чеків зараз не знайшлось на полиці — спробуй назвати словами"
        )

    still_have: list[str] = []
    for line in lines:
        hint = line.from_history
        if hint is None:
            continue
        if (
            line.intent in fill_intents
            or line.intent in occasion_intents
            or line.intent in understand_intents
        ):
            continue
        cycle = hint.cycle_days()
        since = hint.days_since_last(moment)
        if cycle is not None and since is not None and since < cycle * PANTRY_STILL_HAVE_RATIO:
            line.at_home = True
            line.mandate = None
            line.needs_approval = False
            line.ahead = False
            line.reason = (
                f"з твоїх слів це ще є вдома, цикл ~{cycle} дн"
                if hint.guest_said
                else f"брав {since} дн тому, цикл ~{cycle} дн — швидше за все, ще стоїть"
            )
            still_have.append(line.product["name"])
    if still_have:
        trace.add(
            "step-pantry",
            "core.cycles",
            {"види": list(still_have)},
            f"за циклом ще не мало закінчитись: {len(still_have)} "
            + plural(len(still_have), "вид", "види", "видів"),
            decision=f"не додав: {len(still_have)} поз. — «схоже, ще є вдома»",
            tag=f"мінус {len(still_have)}",
            tag_tone="muted",
        )

    terms = terms_from_slot(slot)
    money = settle(lines, terms)

    trimmed: list[Trimmed] = []
    by_intent = {line.intent: line for line in lines if not line.at_home}
    ours = [
        (intent, "добране під ціль — знімаю першим")
        for intent in reversed(list(fill_intents))
        if intent in by_intent
    ]
    kept_home = [
        (intent, "дописано в комору без циклу — знімаю під межу після добору")
        for intent, line in by_intent.items()
        if line.explanation == PANTRY_MANUAL_WHY
    ]
    cuttable = {
        intent
        for intent, line in by_intent.items()
        if line.auto_need or line.explanation == PANTRY_MANUAL_WHY
    }
    queue = list(
        {
            intent: why for intent, why in [*ours, *kept_home, *expendable] if intent in cuttable
        }.items()
    )
    refused = [intent for intent, _ in expendable if intent in by_intent and intent not in cuttable]
    if refused:
        log.info("basket.trim_refused", intents=refused)

    fill_cut = 0
    fill_cut_names: list[str] = []
    fill_cut_heavy: list[str] = []
    fill_trimmed: list[Trimmed] = []

    def cut(intent: str, why: str, *, heavy: bool = False) -> None:
        nonlocal fill_cut
        line = by_intent[intent]
        lines.remove(line)
        item = Trimmed(intent=intent, name=line.product["name"], price=line.total, reason=why)
        if intent in fill_intents:
            (fill_cut_heavy if heavy else fill_cut_names).append(intent)
            if not heavy:
                fill_cut += 1
            fill_trimmed.append(item)
            return
        trimmed.append(item)

    budget_now = Decimal(str(request.budget)) if request.budget is not None else None
    if request.budget is not None and budget_now is not None:
        edges_final = budget_band(budget_now)
        limit = budget_now.quantize(Decimal("0.01"))
        cuts_budget = 0
        budget_skipped: list[str] = []
        while True:
            step_cut = next_budget_cut(
                money.total,
                limit=limit,
                low=edges_final.low,
                queue=[(intent, by_intent[intent].total) for intent, _why in queue],
            )
            if step_cut is None:
                break
            budget_skipped.extend(
                intent for intent in step_cut.skipped if intent not in budget_skipped
            )
            cut(*queue.pop(step_cut.index))
            money = settle(lines, terms)
            cuts_budget += 1
        keep_hand = {str(article) for article in request.keep}
        spare = sorted(
            (
                line
                for line in lines
                if not line.at_home
                and str(line.product.get("externalProductId")) not in keep_hand
                and (
                    line.intent in cuttable
                    or line.intent in occasion_intents
                    or line.intent in understand_intents
                )
            ),
            key=lambda line: -line.total,
        )
        while spare:
            spare_step = spare_budget_cut(
                money.total,
                limit=limit,
                rows=[(line.intent, line.total) for line in spare],
            )
            if spare_step is None:
                break
            victim = spare.pop(spare_step.index)
            cut(
                victim.intent,
                "понад межу після черги агента — знімаю найдешевше з докинутого, що вміщає в межу"
                if spare_step.saves
                else "понад межу після черги агента — жодне докинуте не вміщає, знімаю найдорожче",
            )
            money = settle(lines, terms)
            cuts_budget += 1

        over_high = money.total - limit
        if over_high > 0 and answer_of is not None and len(lines) > 1:
            by_hand = {str(article) for article in request.keep}
            ways = overshoot_ways(
                money.total,
                limit=limit,
                rows=[
                    (line.intent, str(line.product["name"]), line.total)
                    for line in lines
                    if line.intent not in cuttable
                    and not line.at_home
                    and str(line.product.get("externalProductId")) not in by_hand
                ],
            )
            if ways.asks():
                articles = {
                    line.intent: str(line.product.get("externalProductId")) for line in lines
                }
                by_option = {f"cut:{articles[drop.intent]}": drop for drop in ways.drops}
                trace.add(
                    "step-over",
                    "агент",
                    {
                        "над межею, грн": f"{over_high:.2f}",
                        "варіантів": len(by_option) + 1,
                        "рядки": [f"{drop.name}: -{drop.price:.0f} грн" for drop in ways.drops],
                    },
                    f"кошик вище межі на {over_high:.0f} грн, а різати лишилось "
                    f"лише назване тобою — питаю, що робити",
                    decision="назване гостем агент не знімає сам, але й мовчати про "
                    "перебір не має права: рішення за гостем, арифметика за кодом",
                    tag="питання",
                    tag_tone="warn",
                    question=TraceQuestion(
                        id=OVER_QUESTION,
                        ask=f"Кошик на {money.total:.0f} грн — це на {over_high:.0f} "
                        f"вище твоєї межі {limit:.0f}. Що робимо?",
                        why="назване тобою я не знімаю без твого слова",
                        options=[
                            *(
                                TraceOption(
                                    id=option,
                                    label=f"зняти {drop.name} — лишиться {drop.left:.0f} грн",
                                )
                                for option, drop in by_option.items()
                            ),
                            TraceOption(
                                id=OVER_RAISE,
                                label=f"підняти ціль до {ways.target:.0f} грн",
                                target=ways.target,
                            ),
                        ],
                        wait_s=int(ANSWER_WAIT_S),
                    ),
                )
                picked = await answer_of(OVER_QUESTION, ANSWER_WAIT_S)
                drop = by_option.get(picked or "")
                if drop is not None:
                    cut(drop.intent, "ти обрав зняти це під межу")
                    money = settle(lines, terms)
                    cuts_budget += 1
                elif picked == OVER_RAISE:
                    budget_now = ways.target
                    edges_final = budget_band(budget_now)
                    limit = budget_now.quantize(Decimal("0.01"))
                trace.add(
                    "step-over",
                    "агент",
                    {"відповідь": picked or ""},
                    f"знімаю з кошика: {drop.name}"
                    if drop is not None
                    else f"ціль піднято до {ways.target:.0f} грн — кошик у коридорі"
                    if picked == OVER_RAISE
                    else f"не дочекався за {ANSWER_WAIT_S:.0f} с — лишаю як є, рішення за тобою",
                    tag="відповідь" if picked else "без відповіді",
                    tag_tone="good" if picked else "muted",
                )
        if cuts_budget:
            runner.credit("economy.settle", f"різ під межу гостя: {cuts_budget} поз.")
        if not lines and not questions:
            raise AssemblyError(
                f"усе, що закінчується, не влізло в межу {limit} грн — підійми межу"
            )

    weight = weigh(lines)
    heavy_cuts = 0
    while over_limit(weight.kg, terms.max_weight_kg) > 0 and queue:
        intent, why = queue.pop(0)
        cut(intent, f"{why}. Разом кошик важчий за ліміт слота", heavy=True)
        heavy_cuts += 1
        money = settle(lines, terms)
        weight = weigh(lines)
    keep_hand_weight = {str(article) for article in request.keep}
    heavy_spare = sorted(
        (
            line
            for line in lines
            if not line.at_home
            and str(line.product.get("externalProductId")) not in keep_hand_weight
            and (
                line.intent in cuttable
                or line.intent in occasion_intents
                or line.intent in understand_intents
            )
            and line_weight(line.product) is not None
        ),
        key=lambda line: -(line.qty * (line_weight(line.product) or Decimal(0))),
    )
    while over_limit(weight.kg, terms.max_weight_kg) > 0 and heavy_spare:
        victim = heavy_spare.pop(0)
        cut(
            victim.intent,
            "кошик важчий за ліміт слота, а черга агента вичерпана — знімаю найважче з докинутого",
            heavy=True,
        )
        heavy_cuts += 1
        money = settle(lines, terms)
        weight = weigh(lines)
    if heavy_cuts:
        runner.credit("economy.settle", f"різ під вагу слота: {heavy_cuts} поз.")
    if heavy_cuts and not lines and not questions:
        raise AssemblyError(
            f"навіть без добраного кошик важчий за ліміт слота "
            f"{kg_text(terms.max_weight_kg)} — це два замовлення, а не одне"
        )
    over_kg = over_limit(weight.kg, terms.max_weight_kg)
    trace.add(
        "step-weight",
        "core.weight",
        {"наш добір, знятий вагою": fill_cut_heavy} if fill_cut_heavy else {},
        f"вага кошика {kg_text(weight.kg)}"
        + (
            f" при ліміті слота {kg_text(terms.max_weight_kg)}"
            if terms.max_weight_kg > 0
            else " — ліміту слот не назвав"
        )
        + (
            f"; без {weight.unknown} рядків — картка фасовки не назвала"
            if not weight.complete
            else ""
        )
        + (f"; наш добір не вліз за вагою: {len(fill_cut_heavy)} поз." if fill_cut_heavy else ""),
        decision=(
            _split_note(lines, terms.max_weight_kg)
            if over_kg > 0
            else "вага рахована з фасовок: у картці товару її немає"
        ),
        tag=f"понад ліміт на {kg_text(over_kg)}" if over_kg > 0 else kg_text(weight.kg),
        tag_tone="warn" if over_kg > 0 else "muted",
    )

    risky_count = sum(1 for line in lines if line.risky and not line.at_home)
    ahead_count = sum(1 for line in lines if line.ahead and not line.at_home)
    if risky_count or ahead_count:
        swaps_allowed = collector_swaps(feedback.changes)
        summary = []
        if risky_count:
            summary.append(f"ризикових рядків {risky_count} — ланцюжки готові наперед")
        if ahead_count:
            summary.append(
                ("ще " if risky_count else "")
                + f"{ahead_count} з мандатом напоготові: до слота "
                + f"{hours_to_slot:.0f} год при стелі {SHELF_TURNOVER_HOURS}"
            )
        trace.add(
            "step-risk",
            "core.substitution",
            {},
            "; ".join(summary),
            decision=reach_note(swaps_allowed),
            tag=("ризик" if risky_count else "наперед")
            if swaps_allowed is not False
            else "заміни заборонені",
            tag_tone="warn",
        )

    await runner.run(
        "economy.settle",
        steps.Economy(ground).report,
        step_id="step-economics",
        tool=steps.economy.TOOL,
    )
    money = facts.get("economics")

    if request.budget is not None:
        over = money.total - limit
        if over > 0:
            summary = f"кошик {money.total} грн вище межі {limit} грн на {over} грн"
        else:
            summary = f"кошик {money.total} грн у межі {limit} грн"
        if fill_cut:
            summary += f"; добір не вліз за цінами: {fill_cut} поз."
        if budget_skipped:
            summary += (
                f"; пропустив {len(budget_skipped)} поз. — різ кинув би нижче "
                f"коридору {edges_final.low:.0f}-{edges_final.high:.0f}"
            )
        short = edges_final.short_by(money.total)
        if short > 0 and over <= 0:
            summary += (
                f"; це НИЖЧЕ коридору {edges_final.low:.0f}-{edges_final.high:.0f}"
                f" на {short:.0f} грн"
            )
        if trimmed:
            names = _named_within(
                [item.name or item.intent for item in trimmed],
                budget=SUMMARY_CHARS - len(summary) - len(f"; зняв {len(trimmed)}: "),
            )
            summary += f"; зняв {len(trimmed)}: {names}" if names else f"; зняв {len(trimmed)} поз."
        if over > 0:
            tag = f"понад межу на {over} грн"
        elif short > 0:
            tag = f"нижче цілі на {short} грн"
        elif trimmed:
            tag = f"-{len(trimmed)} поз."
        else:
            tag = "у межі"
        trace.add(
            "step-budget",
            "агент" if trimmed else "core.delivery",
            {
                "межа": str(limit),
                "зняв": [item.name or item.intent for item in trimmed],
                **({"пропустив під коридор": budget_skipped} if budget_skipped else {}),
            },
            summary,
            decision="що саме зняти під межу — рішення агента; назване гостем не ріжеться",
            tag=tag,
            tag_tone="warn" if over > 0 else ("muted" if short > 0 else "good"),
        )

    plan_done = plan_report(
        planned.plan.names(),
        done=runner.done,
        also=executed,
        refused=runner.refused,
        did=runner.did,
    )
    done_note = f"з плану агента виконано {len(plan_done.done)} з {plan_done.total} кроків"
    if plan_done.later:
        done_note += f"; ще {len(plan_done.later)} чекають на «Оформити»"
    if plan_done.refused:
        done_note += f"; {len(plan_done.refused)} не вдалось"
    trace.add(
        "step-plan-done",
        "agent.plan",
        plan_done.args(),
        done_note,
        decision="план керує необов'язковими кроками; головні кроки і запобіжники йдуть завжди",
        tag=plan_done.tag,
        tag_tone=plan_done.tone,
    )

    ordered_postponed = in_fix_order(postponed)

    goal = basket_goal(
        intents=intents,
        addresses={
            "рядок кошика": [line.intent for line in lines],
            "питання гостю": [question.intent for question in questions],
            "не знайшлось": unresolved,
            "не збирають на слот": not_collected,
            "агент не взяв": list(declined),
            "відкладено": [item.intent for item in ordered_postponed],
            "зняте під межу": [item.intent for item in trimmed] + fill_cut_names,
            "зняте під вагу слота": fill_cut_heavy,
            "злито в сусідній рядок": sorted(merged_intents),
            "спитано разом із сусіднім": [intent for intent, _ in merged_asks],
            "чекає акції": waiting_promo,
        },
        decided=bool(picks),
        model=llm is not None,
    )
    trace.add(
        "step-goal",
        "core.goal",
        {"зобов'язань": len(goal.duties), **goal.told()},
        goal.note(),
        decision="мету перевіряють один раз і без моделі: рішення про кроки -- агент, "
        "вирок про результат -- сталі правила",
        tag="мета" if goal.ok else f"не збулось {len(goal.unmet)}",
        tag_tone="good" if goal.ok else "warn",
    )

    if goal.broken:
        raise AssemblyError(goal.refusal())

    spent = Meter.of(llm)
    basket = Basket(
        run_id="live",
        lines=[to_cart_line(line) for line in lines],
        total=money.total,
        base_total=money.discounted,
        delivery_cost=money.cost,
        total_weight_kg=weight.kg,
        top_up=money.top_up,
        blockers=[*money.blockers, *([REASON_WEIGHT_MAX] if over_kg > 0 else [])],
        slot=SlotWindow(start=slot["start"], end=slot["end"], note=slot_note),
        trace=trace.steps,
        unresolved=unresolved,
        declined=[Declined(intent=intent, why=why) for intent, why in declined.items()],
        feedback=feedback,
        questions=questions,
        not_collected=not_collected,
        text_ignored=list(insight.ignored),
        postponed=ordered_postponed,
        budget=budget_now,
        fill_note=fill_note,
        cycles_note=coverage_note(
            takes_cycles=occasion.takes_cycles,
            receipts=receipts,
            orders=web.count,
            kinds=kinds,
            uneven=rare,
            tracked_from=MIN_RECEIPTS,
        ),
        trimmed=trimmed,
        fill_cut=fill_trimmed,
        twins_dropped=[
            TwinsDropped(name=drop.name, kept_name=drop.kept_name, why=drop.why)
            for drop in deciding.twins_dropped
        ],
        plan_note=(planned.note if llm is not None and planned.plan.source == "code" else None),
        agent_target=_agent_target(composing.stretched),
        shelf_note=(mute_note(mcp.silence) if is_mute(mcp.silence) else None),
        stats=RunStats(
            receipts=receipts,
            orders=web.count,
            cycled=sum(1 for item in history if item.cycle_days() is not None),
            mcp_calls=sum(1 for _ in trace.steps if _.tool.startswith("silpo_")),
            duration_ms=sum(step.duration_ms or 0 for step in trace.steps),
            cost_usd=run_cost(spent),
            tokens_in=spent.input_tokens,
            tokens_out=spent.output_tokens,
            tokens_cached=spent.cached_tokens,
            model=model_used,
        ),
    )
    run_log = record_run(basket, request, moment) if cfg.run_log else None
    return Assembled(
        basket=basket,
        lines=lines,
        unresolved=unresolved,
        slot=slot,
        run_log=run_log,
        branch_id=branch_id,
        rules=tuple(guest_rules),
        auto_swap=request.auto_swap,
        auto_swap_percent=request.auto_swap_percent,
        plan=planned.plan,
        fill_intents=tuple(fill_intents),
        occasion=occasion,
        swap_cards=asked_cards
        | {
            str(line.cheaper["externalProductId"]): line.cheaper
            for line in lines
            if line.cheaper is not None
        },
    )
