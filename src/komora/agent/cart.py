from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from time import monotonic
from typing import Any

from komora.agent.basket import (
    CHAIN_TOKENS_PER_ROW,
    MIN_RECEIPTS,
    SLOT_LOOKAHEAD,
    Assembled,
    AssemblyError,
    Naming,
    PlanLine,
    Tracer,
    build_chain,
    chain_from_decision,
    delivery_type_for,
    fork_for,
    intent_names,
    kg_text,
    kind_key,
    load_history,
    mandate_for_decision,
    qty_for_api,
    receipts_phrase,
    record_run,
    run_cost,
    search_products,
    slots_query,
    terms_from_slot,
    to_cart_line,
    weigh,
)
from komora.agent.economics import settle
from komora.agent.llm import Meter, Truncated
from komora.agent.prompts import register as register_prompt
from komora.agent.prompts import stamp as prompt_stamp
from komora.api.schemas import (
    Basket,
    BuildRequest,
    CartState,
    OrderFeedback,
    Reason,
    RunStats,
    SlotWindow,
    SwapDecision,
    TraceStep,
)
from komora.config import Settings
from komora.config import settings as _default_settings
from komora.core import slots as core_slots
from komora.core.cycles import FOREIGN_NOTE
from komora.core.feedback import Changes, Contacts, changes_of, contacts_of
from komora.core.location import Location
from komora.core.mandate import Fork, build_comment, fit_comment, price_fork_comment
from komora.core.occasion import occasion_of
from komora.core.packaging import parse_pack_weight
from komora.core.revalidation import Line, Rewrite, Verdict, plan_rewrites
from komora.core.shelf_life import required_until, shelf_life_phrase
from komora.core.silence import is_mute, mute_note
from komora.core.substitution import (
    DEFAULT_CHAIN_LENGTH,
    SHELF_TURNOVER_HOURS,
    Alternative,
    Source,
    is_risky,
)
from komora.core.words import rows as rows_word
from komora.db import catalog as catalog_store
from komora.db.pool import DictPool
from komora.logging import get_logger
from komora.mcp.client import MCPCallError, SilpoMCP, missing_resource

log = get_logger(__name__)

_SLUG_ARTICLE = re.compile(r"-(\d+)$")

_LINE_LEVELS = frozenset({"error"})

EMPTY_CART_NOTE = (
    "кошик у «Сільпо» порожній — доводити до дверей нема чого. "
    "Наповни його в «Сільпо» або натисни «Зібрати на тиждень»: "
    "зберу кошик із твоїх покупок"
)

UNNAMED_CART_NOTE = (
    "«Сільпо» відповіло про кошик, але не назвало його — це не «кошика немає», "
    "а мовчання магазину: спробуй ще раз"
)

UNSEEN_CART_NOTE = (
    "«Сільпо» назвало кошик, але не показало, що в ньому — писати туди наосліп "
    "не буду: спробуй ще раз"
)

_NOTABLE_WEIGHT_GAP = Decimal("0.1")


class CartMissing(AssemblyError):
    ...


def article_of(slug: str | None) -> str | None:
    if not slug:
        return None
    found = _SLUG_ARTICLE.search(slug)
    return found.group(1) if found else None


def flagged_products(validations: list[dict[str, Any]]) -> dict[str, Decimal | None]:
    flagged: dict[str, Decimal | None] = {}
    for entry in validations:
        if entry.get("type") != "product" or entry.get("level") not in _LINE_LEVELS:
            continue
        context = entry.get("context") or {}
        product_id = context.get("productId")
        if not product_id:
            continue
        stock = context.get("stock")
        flagged[str(product_id)] = Decimal(str(stock)) if stock is not None else None
    return flagged


@dataclass(frozen=True, slots=True)
class CartSnapshot:

    cart_id: str
    branch_id: str | None
    delivery_type: str
    timeslot_start: str | None
    timeslot_end: str | None
    rows: tuple[dict[str, Any], ...]
    validations: tuple[dict[str, Any], ...]
    checkout_web_link: str | None
    checkout_mobile_link: str | None
    address: dict[str, Any]
    shipments: tuple[dict[str, Any], ...]
    weight_kg: Decimal
    products_total: Decimal
    discount: Decimal
    total_after_discounts: Decimal | None
    bonus_available: Decimal
    delivery_cost: Decimal | None
    feedback_changes: Changes | None
    feedback_contacts: Contacts | None
    service_fee: Decimal | None = None
    seen: bool = True

    @property
    def blockers(self) -> list[str]:
        return [
            str(entry.get("message"))
            for entry in self.validations
            if entry.get("level") == "error" and entry.get("message")
        ]


async def read_cart(mcp: SilpoMCP) -> CartSnapshot:
    try:
        payload = (await mcp.call("silpo_get_my_shopping_cart")).payload_raw
    except MCPCallError as exc:
        if not missing_resource(exc):
            raise
        raise CartMissing(EMPTY_CART_NOTE) from exc
    cart_id = payload.get("shoppingCartId")
    if cart_id:
        snapshot = await read_cart_by_id(mcp, str(cart_id))
        if not snapshot.seen:
            raise AssemblyError(UNSEEN_CART_NOTE)
        return snapshot
    if payload.get("exists") is False:
        raise CartMissing(EMPTY_CART_NOTE)
    log.warning("cart.unnamed", fields=sorted(str(key) for key in payload))
    raise AssemblyError(UNNAMED_CART_NOTE)


def state_of(snapshot: CartSnapshot) -> CartState:
    return CartState(
        rows=len(snapshot.rows),
        total=snapshot.products_total,
        slot=SlotWindow(start=snapshot.timeslot_start, end=snapshot.timeslot_end)
        if snapshot.timeslot_start and snapshot.timeslot_end
        else None,
    )


def _fee_of(raw: object) -> Decimal | None:
    if not isinstance(raw, dict) or raw.get("total") is None:
        return None
    return Decimal(str(raw["total"]))


async def read_cart_by_id(mcp: SilpoMCP, cart_id: str) -> CartSnapshot:
    details = (
        await mcp.call("silpo_get_shopping_cart_by_id", {"shoppingCartId": cart_id})
    ).payload_raw
    raw = details.get("cart")
    seen = isinstance(raw, dict) and bool(raw)
    cart = raw if isinstance(raw, dict) else {}
    if not seen:
        log.warning("cart.unseen", cart_id=str(cart_id))
    shipments = cart.get("shipments") or []
    calculation = cart.get("calculation") or {}
    delivery = calculation.get("delivery") or {}
    loyalty = details.get("loyalty") or {}
    return CartSnapshot(
        cart_id=str(cart_id),
        branch_id=shipments[0].get("branchId") if shipments else None,
        delivery_type=str(cart.get("deliveryType") or "DeliveryHome"),
        timeslot_start=(cart.get("timeslot") or {}).get("start"),
        timeslot_end=(cart.get("timeslot") or {}).get("end"),
        rows=tuple(row for shipment in shipments for row in (shipment.get("products") or [])),
        validations=tuple(calculation.get("validations") or []),
        checkout_web_link=details.get("checkoutWebLink") or None,
        checkout_mobile_link=details.get("checkoutMobileLink") or None,
        address=dict(cart.get("address") or {}),
        shipments=tuple(
            {key: value for key, value in shipment.items() if key != "products"}
            for shipment in shipments
        ),
        weight_kg=Decimal(str(delivery.get("totalWeight") or 0)),
        products_total=Decimal(
            str(calculation.get("productsTotal") or calculation.get("totalAfterDiscounts") or 0)
        ),
        discount=Decimal(str(calculation.get("subDiscount") or 0)),
        total_after_discounts=(
            Decimal(str(calculation["totalAfterDiscounts"]))
            if calculation.get("totalAfterDiscounts") is not None
            else None
        ),
        bonus_available=Decimal(str(loyalty.get("bonusAvailable") or 0)),
        delivery_cost=(
            Decimal(str(delivery["total"])) if delivery.get("total") is not None else None
        ),
        service_fee=_fee_of(calculation.get("serviceFee")),
        feedback_changes=changes_of(cart.get("feedbackChanges")),
        feedback_contacts=contacts_of(cart.get("feedbackContacts")),
        seen=seen,
    )


def cart_states(
    rows: Sequence[dict[str, Any]],
    validations: Sequence[dict[str, Any]],
    *,
    vanished: frozenset[str] = frozenset(),
) -> list[Line]:
    flagged = flagged_products(list(validations))
    states: list[Line] = []
    for row in rows:
        product_id = str(row.get("productId") or "")
        explicit = row.get("externalProductId")
        article = str(explicit) if explicit else (article_of(row.get("slug")) or product_id)
        by_api = flagged.get(product_id)
        raw_stock = row.get("stock")
        if by_api is not None:
            stock: Decimal | None = by_api
        elif article in vanished:
            stock = Decimal(0)
        else:
            stock = Decimal(str(raw_stock)) if raw_stock is not None else None
        states.append(
            Line(
                external_product_id=article,
                product_id=product_id,
                name=str(row.get("name") or ""),
                quantity=Decimal(str(row.get("quantity") or 0)),
                stock=stock,
                flagged=product_id in flagged or article in vanished,
            )
        )
    return states


def _product_from_row(row: dict[str, Any], article: str | None) -> dict[str, Any]:
    return {
        "id": row.get("productId"),
        "companyId": row.get("companyId"),
        "branchId": row.get("branchId"),
        "externalProductId": article or str(row.get("productId") or ""),
        "name": row.get("name") or "",
        "price": row.get("price") or 0,
        "oldPrice": row.get("oldPrice"),
        "stock": row.get("stock"),
        "available": True,
        "image": row.get("image"),
        "displayRatio": row.get("ratio"),
        "weighted": row.get("weighted"),
        "step": row.get("addToBasketStep"),
    }


def _kind_query(name: str, mapped: Naming | None) -> str:
    if mapped:
        return f"{mapped.intent} {mapped.subtype}" if mapped.subtype else mapped.intent
    words = name.split()
    return words[0] if words else ""


CHAIN_SCHEMA = {
    "type": "object",
    "properties": {
        "chains": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "article": {"type": "string"},
                    "chain": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                    "swap": {"type": ["string", "null"]},
                },
                "required": ["article", "chain", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["chains"],
    "additionalProperties": False,
}

CHAIN_SYSTEM = (
    "Ти агент кошика «Комора». Для КОЖНОГО рядка кошика гостя склади ланцюжок "
    "замін: від 1 до 3 артикулів з кандидатів, у порядку переваги — перший "
    "поїде, якщо звичного не буде на полиці. Заміна мусить бути ТИМ САМИМ "
    "товаром по суті: чорний ароматизований чай заміняється чорним чаєм, а не "
    "трав'яним; молоко 2,5% — молоком, а не вершками й не йогуртом; свіже не "
    "заміняється сушеним, консервованим чи замороженим. Інша марка — нормально, "
    "інший вид — ні. Ближча фасовка краща за далеку. Якщо гідної заміни серед "
    "кандидатів немає, поверни ПОРОЖНІЙ ланцюжок: краще порожньо, ніж не те — "
    "гість тоді вирішить сам. Причина — одне коротке речення українською. "
    "Поле «swap» — ВІСЬ ЗАМІНИ для збирача, коли конкретного ланцюжка немає: "
    "чим можна закрити позицію, у словах, які людина біля полиці перевірить "
    "очима («інший цільнозерновий пшеничний, 400 г»). НЕ пиши «інша марка»: "
    "для хліба марка ні до чого, важать вид і вага. Ціну не називай. "
    "«article» і артикули в ланцюжку — рівно ті рядки, що в кандидатах. "
    "Правила гостя (поле «правила_гостя») — ОБОВ'ЯЗКОВІ: ланка, яка їх "
    "порушує, не ланка; порожній ланцюжок кращий за заміну всупереч."
)

register_prompt("chain", CHAIN_SYSTEM)


async def agent_chains(
    llm: Any, payload: list[dict[str, Any]], *, rules: Sequence[str] = ()
) -> tuple[dict[str, dict[str, Any]], int]:
    decision = await llm.decide(
        system=CHAIN_SYSTEM,
        user=json.dumps(
            {"рядки": payload, "правила_гостя": list(rules) or None},
            ensure_ascii=False,
        ),
        schema=CHAIN_SCHEMA,
        prompt=prompt_stamp("chain", CHAIN_SYSTEM),
        max_tokens=max(2048, CHAIN_TOKENS_PER_ROW * len(payload)),
    )
    chains = {str(row.get("article", "")): row for row in decision.data.get("chains", []) if row}
    return chains, decision.duration_ms


def _filter_word(name: str, query: str) -> str:
    words = name.split()
    return words[0] if words else query


def _chain_from_agent(
    picked: dict[str, Any], options: list[dict[str, Any]], *, history_id: str
) -> tuple[Alternative, ...]:
    by_article = {str(p["externalProductId"]): p for p in options}
    chain: list[Alternative] = []
    for article in picked.get("chain", [])[:DEFAULT_CHAIN_LENGTH]:
        product = by_article.get(str(article))
        if product is None or not product.get("available"):
            continue
        chain.append(
            Alternative(
                external_product_id=str(article),
                name=product["name"],
                source=Source.HISTORY if str(article) == history_id else Source.SIMILAR,
                price=Decimal(str(product["price"])),
                stock=product.get("stock"),
                available=True,
            )
        )
    return tuple(chain)


def _mandate_for(
    chain: tuple[Alternative, ...],
    product: dict[str, Any],
    request: BuildRequest,
    *,
    kind: str | None = None,
    shelf_life: str | None = None,
) -> tuple[str | None, Fork | None, bool]:
    if chain:
        return build_comment(chain=chain, shelf_life=shelf_life).comment, None, False
    price = Decimal(str(product["price"]))
    if request.auto_swap and price > 0:
        fork = fork_for(product, request.auto_swap_percent)
        return price_fork_comment(fork, kind=kind, shelf_life=shelf_life), fork, False
    return build_comment(chain=(), shelf_life=shelf_life).comment, None, False


@dataclass(slots=True)
class CartRun:

    assembled: Assembled
    snapshot: CartSnapshot
    chains: dict[str, tuple[Alternative, ...]]
    cards: dict[str, dict[str, Any]]
    drops: tuple[str, ...] = ()


def plan_of(run: Assembled | CartRun) -> Assembled:
    return run.assembled if isinstance(run, CartRun) else run


def with_plan(
    run: Assembled | CartRun,
    plan: Assembled,
    *,
    chains: Mapping[str, tuple[Alternative, ...]] | None = None,
) -> Assembled | CartRun:
    if not isinstance(run, CartRun):
        return plan
    return replace(run, assembled=plan, chains={**run.chains, **(chains or {})})


def dropped_rows(plan: Sequence[Rewrite], fresh: Mapping[str, dict[str, Any]]) -> tuple[str, ...]:
    return tuple(
        str(rewrite.line.product_id)
        for rewrite in plan
        if rewrite.replacement is not None
        and rewrite.keep_quantity <= 0
        and rewrite.replacement.external_product_id in fresh
        and rewrite.line.product_id
    )


async def assemble_cart(
    mcp: SilpoMCP,
    llm: Any,
    request: BuildRequest,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
    place: Location | None = None,
    pool: DictPool | None = None,
    account: str = "",
    on_step: Callable[[TraceStep], None] | None = None,
) -> CartRun:
    cfg = settings if settings is not None else _default_settings
    moment = now or datetime.now(UTC)
    trace = Tracer(on_step)

    cart_started = monotonic()
    snapshot = await read_cart(mcp)
    cart_ms = round((monotonic() - cart_started) * 1000)
    if not snapshot.rows:
        raise AssemblyError(EMPTY_CART_NOTE)
    branch_id = (
        snapshot.branch_id
        or (place.address_branch(delivery_type_for(request.delivery)) if place else None)
        or cfg.branch_id
    )
    trace.add(
        "step-cart",
        "silpo_get_shopping_cart_by_id",
        {},
        f"чужий кошик прочитано: {len(snapshot.rows)} рядків, "
        f"{snapshot.products_total} грн, {snapshot.weight_kg} кг",
        duration_ms=cart_ms,
        decision="хто наповнив кошик — не має значення: кошик і є спільна мова продуктів",
        tag="вхід Б",
        tag_tone="good",
    )

    occasion = occasion_of(request.mode, request.occasion_people, request.event_style)
    if occasion.named:
        trace.add(
            "step-occasion",
            "core.occasion",
            {"привід": str(occasion.mode), "людей": occasion.people},
            f"привід «{occasion.phrase()}» склад чужого кошика не міняє: його наповнив хтось інший",
            decision="щоб привід спрацював, збери кошик зі списку або на тиждень",
            tag="не застосовано",
            tag_tone="warn",
        )

    delivery_type = delivery_type_for(request.delivery)
    if delivery_type != snapshot.delivery_type:
        trace.add(
            "step-delivery",
            "core.delivery",
            {"кошик": snapshot.delivery_type, "запит": delivery_type},
            f"кошик оформлений під {snapshot.delivery_type}, гість обрав {delivery_type} — "
            "пороги й ліміт ваги рахуються під вибір гостя",
            tag_tone="warn",
        )
    slots_outcome = await mcp.call(
        "silpo_get_time_slots",
        slots_query(branch_id, delivery_type, SLOT_LOOKAHEAD, since=moment),
    )
    slots = slots_outcome.payload_raw.get("slots") or []
    choice = core_slots.choose(
        [(s.get("start"), bool(s.get("available"))) for s in slots],
        wanted=snapshot.timeslot_start,
    )
    if choice is None:
        raise AssemblyError(
            f"{core_slots.no_free_note(delivery_type, len(slots))} — доводити нема куди"
        )
    slot = slots[choice.index]
    kept_slot = choice.basis is core_slots.Basis.CART
    slot_note = core_slots.basis_note(choice)
    trace.add(
        "step-slots",
        "silpo_get_time_slots",
        {
            "deliveryTypes": [delivery_type],
            "limit": SLOT_LOOKAHEAD,
            "вікно": f"{slot['start']} — {slot['end']}",
        },
        f"слот {core_slots.window_note(slot['start'], slot['end'], now=moment)}"
        f" — вільних {choice.free} з {choice.offered} найближчих",
        duration_ms=slots_outcome.duration_ms,
        decision=slot_note,
        tag=None if kept_slot else "слот протух",
        tag_tone="muted" if kept_slot else "warn",
    )

    hours_to_slot = core_slots.hours_until(slot.get("start"), now=moment)
    slot_day = core_slots.day_of(slot.get("start"), now=moment)

    history, receipts, history_ms, _, _ = await load_history(
        mcp, slot, branch_id, now=moment, pool=pool, account=account
    )
    by_article = {item.lager_id: item for item in history}
    trace.add(
        "step-history",
        "silpo_get_my_offline_orders",
        {},
        f"{receipts} чеків, {len(history)} різних товарів — щоб знати, що тут звичне",
        duration_ms=history_ms,
    )

    row_names = [str(row.get("name") or "") for row in snapshot.rows]
    names = await intent_names(llm, row_names, pool=pool)
    articles = [article_of(row.get("slug")) for row in snapshot.rows]
    queries = [_kind_query(name, names.get(kind_key(name))) for name in row_names]
    categories = [_filter_word(name, query) for name, query in zip(row_names, queries, strict=True)]
    found, search_ms = await search_products(
        mcp,
        list(dict.fromkeys([term for term in [*queries, *categories, *articles] if term])),
        slot,
        branch_id,
    )
    fresh: dict[str, dict[str, Any]] = {}
    for products in found.values():
        for product in products:
            fresh[str(product["externalProductId"])] = product
    trace.add(
        "step-batch",
        "silpo_find_products_batch",
        {"queries": len(queries)},
        f"кандидатів на заміну: {sum(len(v) for v in found.values())} на {len(queries)} видів",
        duration_ms=search_ms,
        decision="вид рядка називає агент" if names else "агент видів не назвав — вид за словами",
    )

    swaps = {str(s.external_product_id): s for s in request.swaps}
    keep = {str(article) for article in request.keep}

    options_by_key: dict[str, list[dict[str, Any]]] = {}
    for row, article, query, category in zip(
        snapshot.rows, articles, queries, categories, strict=True
    ):
        key = article or str(row.get("productId") or "")
        options_by_key[key] = [
            product
            for product in {
                str(p["externalProductId"]): p
                for p in [*found.get(query, []), *found.get(category, [])]
            }.values()
            if str(product["externalProductId"]) != key
        ]
    picked: dict[str, dict[str, Any]] = {}
    if llm is not None and any(options_by_key.values()):
        chain_payload = [
            {
                "артикул": key,
                "товар": str(row.get("name") or ""),
                "кандидати": [
                    {
                        "id": str(p["externalProductId"]),
                        "назва": p["name"],
                        "ціна": p["price"],
                        "залишок": p.get("stock"),
                        "фасовка": p.get("displayRatio"),
                    }
                    for p in options_by_key[key][:10]
                ],
            }
            for row, article in zip(snapshot.rows, articles, strict=True)
            if (key := article or str(row.get("productId") or "")) and options_by_key[key]
        ]
        started = monotonic()
        try:
            picked, chain_ms = await agent_chains(llm, chain_payload, rules=request.rules)
            trace.add(
                "step-chains",
                str(getattr(llm, "model", "агент")),
                {"рядків": len(picked)},
                "агент склав ланцюжки замін на "
                + f"{sum(1 for row in picked.values() if row.get('chain'))} рядків",
                duration_ms=chain_ms,
                prompt=prompt_stamp("chain", CHAIN_SYSTEM),
                decision="яка саме заміна годиться — рішення агента, не збіг слів",
                tag="агент",
                tag_tone="good",
            )
        except Truncated as exc:
            log.warning(
                "cart.chains_truncated",
                rows=len(chain_payload),
                output_tokens=exc.usage.output_tokens,
                error=str(exc),
            )
            trace.add(
                "step-chains",
                str(getattr(llm, "model", "агент")),
                {"рядків": len(chain_payload)},
                f"відповідь не влізла в стелю на {len(chain_payload)} рядків "
                "— ланцюжки за категорією",
                duration_ms=int((monotonic() - started) * 1000),
                decision="модель відповіла і оплачена: урване це не відмова",
                tag="стеля відповіді",
                tag_tone="warn",
            )
        except Exception as exc:
            log.warning("cart.chains_failed", error=str(exc))
            trace.add(
                "step-chains",
                "агент",
                {"помилка": str(exc)[:400]},
                f"модель недоступна ({str(exc)[:60]}) — ланцюжки за категорією",
                duration_ms=int((monotonic() - started) * 1000),
                tag="без агента",
                tag_tone="warn",
            )

    kinds_map: dict[str, frozenset[str]] = {}
    if pool is not None:
        wanted = {
            str(product["externalProductId"])
            for found in options_by_key.values()
            for product in found
        } | {str(hint.lager_id) for hint in by_article.values() if hint}
        try:
            kinds_map = await catalog_store.load(pool, sorted(wanted))
        except Exception:
            kinds_map = {}

    lines: list[PlanLine] = []
    chains: dict[str, tuple[Alternative, ...]] = {}
    for row, article, query, category in zip(
        snapshot.rows, articles, queries, categories, strict=True
    ):
        key = article or str(row.get("productId") or "")
        product = _product_from_row(row, article)
        if article and article in fresh:
            product = {**product, **{k: v for k, v in fresh[article].items() if v is not None}}
        hint = by_article.get(key)
        decision = swaps.get(key)
        options = options_by_key[key]
        chosen_by_agent = picked.get(key)
        if decision is not None and decision.chain:
            chain = chain_from_decision(decision, fresh)
        elif decision is not None and decision.policy != "substitute":
            chain = ()
        elif chosen_by_agent is not None:
            chain = _chain_from_agent(chosen_by_agent, options, history_id=key)
        else:
            chain = build_chain(
                category,
                product,
                options,
                history_id=hint.lager_id if hint else None,
                usual_pack=parse_pack_weight(hint.unit) if hint else None,
                kinds=kinds_map,
            )
        chains[key] = chain
        risky = is_risky(product.get("stock"))
        mandate, needs_approval = (None, False)
        swap_fork: Fork | None = None
        life = shelf_life_phrase(
            required_until(
                slot_day=slot_day,
                cycle_days=hint.cycle_days() if hint is not None else None,
                keeps=hint.keeps if hint is not None else None,
            )
        )
        decided = (
            mandate_for_decision(decision, chain, risky=risky, shelf_life=life)
            if decision is not None
            else None
        )
        if decided is not None:
            mandate, needs_approval = decided
        else:
            mandate, swap_fork, needs_approval = _mandate_for(
                chain,
                product,
                request,
                kind=str((chosen_by_agent or {}).get("swap") or ""),
                shelf_life=life,
            )
        if hint is None:
            explanation = "рядок чужого кошика — Комора його перевіряє"
        elif hint.receipts >= MIN_RECEIPTS:
            explanation = f"звичне — {receipts_phrase(hint.receipts)} в історії"
        else:
            explanation = f"брав раніше — {receipts_phrase(hint.receipts)}"
        lines.append(
            PlanLine(
                intent=query,
                product=product,
                qty=Decimal(str(row.get("quantity") or 1)),
                reason="прийшло з кошика, зібраного не Коморою",
                from_history=hint,
                risky=risky,
                ahead=mandate is not None and not risky,
                decided=decided is not None,
                chain=chain,
                mandate=mandate,
                swap_fork=swap_fork,
                needs_approval=needs_approval,
                history_matched=hint is not None,
                explanation=explanation,
                reason_code=Reason.FREQUENCY,
                shelf_life=life,
            )
        )

    lines, unresolved, rewrites = revalidate(
        lines,
        chains,
        snapshot=snapshot,
        fresh=fresh,
        found_queries=frozenset(found),
        swaps=swaps,
        keep=keep,
        trace=trace,
    )

    terms = terms_from_slot(slot)
    money = settle(
        lines,
        terms,
        actual_delivery_cost=snapshot.delivery_cost,
        blockers=snapshot.blockers,
    )
    ahead_count = sum(1 for line in lines if line.ahead)
    if ahead_count:
        trace.add(
            "step-risk",
            "core.substitution",
            {},
            f"{ahead_count} рядків з мандатом напоготові: "
            f"до слота {hours_to_slot:.0f} год при стелі {SHELF_TURNOVER_HOURS}",
            decision="полиця до збирання встигне змінитись — виміряно на знімках залишків",
            tag="наперед",
            tag_tone="muted",
        )
    trace.add(
        "step-economics",
        "core.delivery",
        {},
        f"після ре-валідації разом {money.total} грн, доставка {money.cost} грн"
        + (
            f" (за порогами слота {money.by_tiers} — діє підписка або промо)"
            if money.subscription_applies
            else ""
        )
        + (f"; бонуси {snapshot.bonus_available}" if snapshot.bonus_available else ""),
    )
    ours = weigh(lines)
    gap = abs(ours.kg - snapshot.weight_kg)
    trace.add(
        "step-weight",
        "core.weight",
        {},
        f"«Сільпо» рахує {kg_text(snapshot.weight_kg)}, моя оцінка з фасовок "
        f"{kg_text(ours.kg)}"
        + (
            f" (без {ours.unknown} рядків — картка фасовки не назвала)" if not ours.complete else ""
        ),
        decision=(
            f"розбіжність {kg_text(gap)} — на ліміт слота дивимось за їхнім числом"
            if gap > _NOTABLE_WEIGHT_GAP
            else "числа зійшлись — на ліміт слота дивимось за їхнім"
        ),
        tag=kg_text(snapshot.weight_kg),
        tag_tone="muted",
    )

    if request.budget is not None:
        limit = Decimal(str(request.budget))
        over = money.total - limit
        trace.add(
            "step-budget",
            "core.delivery",
            {"межа": str(limit)},
            f"кошик {money.total} грн вище межі {limit} грн на {over} грн — різати склад "
            "чужого кошика Комора самовільно не буде"
            if over > 0
            else f"кошик {money.total} грн у межі {limit} грн",
            decision="чужий кошик наповнив хтось інший — межа тут показує, а не ріже",
            tag=f"понад межу на {over} грн" if over > 0 else "у межі",
            tag_tone="warn" if over > 0 else "good",
        )

    spent = Meter.of(llm)
    basket = Basket(
        run_id="live",
        shelf_note=(mute_note(mcp.silence) if is_mute(mcp.silence) else None),
        lines=[to_cart_line(line) for line in lines],
        total=money.total,
        base_total=money.discounted,
        delivery_cost=money.cost,
        total_weight_kg=snapshot.weight_kg,
        top_up=money.top_up,
        blockers=money.blockers,
        slot=SlotWindow(start=slot["start"], end=slot["end"], note=slot_note),
        trace=trace.steps,
        unresolved=unresolved,
        feedback=OrderFeedback(
            changes=snapshot.feedback_changes, contacts=snapshot.feedback_contacts
        ),
        budget=Decimal(str(request.budget)) if request.budget is not None else None,
        cycles_note=FOREIGN_NOTE,
        stats=RunStats(
            receipts=receipts,
            cycled=0,
            mcp_calls=sum(1 for step in trace.steps if step.tool.startswith("silpo_")),
            duration_ms=sum(step.duration_ms or 0 for step in trace.steps),
            cost_usd=run_cost(spent),
            tokens_in=spent.input_tokens,
            tokens_out=spent.output_tokens,
            tokens_cached=spent.cached_tokens,
            model=str(getattr(llm, "model", "")) if names else "без агента",
        ),
    )
    log.info(
        "cart.assembled",
        rows=len(snapshot.rows),
        rewrites=len(rewrites),
        cart_id=snapshot.cart_id,
    )
    return CartRun(
        assembled=Assembled(
            basket=basket,
            lines=lines,
            unresolved=unresolved,
            slot=slot,
            run_log=record_run(basket, request, moment) if cfg.run_log else None,
            branch_id=branch_id,
            rules=tuple(request.rules),
            auto_swap=request.auto_swap,
            auto_swap_percent=request.auto_swap_percent,
        ),
        snapshot=snapshot,
        chains=chains,
        cards=fresh,
        drops=dropped_rows(rewrites, fresh),
    )


def revalidate(
    lines: list[PlanLine],
    chains: dict[str, tuple[Alternative, ...]],
    *,
    snapshot: CartSnapshot,
    fresh: dict[str, dict[str, Any]],
    found_queries: frozenset[str],
    swaps: dict[str, SwapDecision],
    keep: frozenset[str] | set[str],
    trace: Tracer,
) -> tuple[list[PlanLine], list[str], list[Rewrite]]:
    vanished = frozenset(
        article
        for line in lines
        if (article := str(line.product["externalProductId"])) in found_queries
        and article not in fresh
    )
    states = cart_states(
        [
            {
                "productId": line.product.get("id"),
                "externalProductId": line.product["externalProductId"],
                "name": line.product["name"],
                "quantity": line.qty,
                "stock": line.product.get("stock"),
            }
            for line in lines
        ],
        list(snapshot.validations),
        vanished=vanished,
    )

    plan = plan_rewrites(states, chains)
    if not plan:
        trace.add(
            "step-revalidate",
            "core.revalidation",
            {"рядків": len(lines)},
            "усі рядки доступні на момент слота — переписувати нічого",
            decision="ре-валідація перед слотом пройдена",
        )
        return lines, [], []

    unresolved: list[str] = []
    result: list[PlanLine] = []
    for line in lines:
        article = str(line.product["externalProductId"])
        rewrite = next((r for r in plan if r.line.external_product_id == article), None)
        if rewrite is None:
            result.append(line)
            continue
        decision = swaps.get(article)
        if rewrite.replacement is None and decision is not None and decision.policy == "skip":
            unresolved.append(f"{line.product['name']} — {rewrite.note}; знято за правилом гостя")
            continue
        if rewrite.replacement is None:
            result.append(_needs_approval(line, rewrite, kept=article in keep))
            unresolved.append(f"{line.product['name']} — {rewrite.note}")
            continue
        result.extend(_replaced(line, rewrite, fresh))

    swapped = sum(1 for r in plan if r.replacement is not None)
    trace.add(
        "step-revalidate",
        "core.revalidation",
        {
            "рядків": len(lines),
            "проблемних": len(plan),
            "рядки": [r.note for r in plan],
        },
        f"переписую {len(plan)} з {len(lines)} "
        + rows_word(len(lines))
        + f": погоджених замін {swapped}",
        decision=(
            f"застосовано погоджені заміни: {swapped} з {len(plan)} — "
            "рішення прийняте наперед, не питається зараз"
        ),
        tag=f"замін {swapped}" if swapped else "потрібне рішення",
        tag_tone="good" if swapped == len(plan) else "warn",
    )
    return result, unresolved, plan


def _needs_approval(line: PlanLine, rewrite: Rewrite, *, kept: bool) -> PlanLine:
    line.needs_approval = True
    line.mandate = None
    line.swap_fork = None
    line.risky = True
    line.gone = rewrite.verdict is Verdict.GONE
    line.explanation = rewrite.note + (" · твій рядок, не знімаю" if kept else "")
    line.reason_code = Reason.FREQUENCY
    if rewrite.verdict is Verdict.SHORT:
        line.qty = rewrite.keep_quantity
    return line


def _replaced(line: PlanLine, rewrite: Rewrite, fresh: dict[str, dict[str, Any]]) -> list[PlanLine]:
    if rewrite.replacement is None:  # pragma: no cover — відсіяно в revalidate()
        return [line]
    out: list[PlanLine] = []
    if rewrite.keep_quantity > 0:
        line.qty = rewrite.keep_quantity
        line.explanation = rewrite.note
        line.reason_code = Reason.FREQUENCY
        out.append(line)
    product = fresh.get(rewrite.replacement.external_product_id)
    if product is None:
        return [_needs_approval(line, rewrite, kept=False)]
    out.append(
        PlanLine(
            intent=line.intent,
            product=product,
            qty=rewrite.replacement_quantity,
            reason=rewrite.note,
            from_history=line.from_history,
            risky=is_risky(product.get("stock")),
            chain=(),
            mandate=None,
            needs_approval=False,
            history_matched=False,
            explanation=rewrite.note,
            reason_code=Reason.SUBSTITUTED,
        )
    )
    return out


async def commit(mcp: SilpoMCP, run: CartRun) -> dict[str, Any]:
    written = await apply_rewrites(mcp, run.snapshot, run.assembled.lines, drops=run.drops)
    after = await read_cart_by_id(mcp, run.snapshot.cart_id)
    second = plan_rewrites(cart_states(after.rows, after.validations), run.chains)
    fixes = [
        PlanLine(
            intent=rewrite.line.name,
            product=run.cards[rewrite.replacement.external_product_id],
            qty=rewrite.replacement_quantity,
            reason=rewrite.note,
            from_history=None,
            explanation=rewrite.note,
            reason_code=Reason.SUBSTITUTED,
        )
        for rewrite in second
        if rewrite.replacement is not None and rewrite.replacement.external_product_id in run.cards
    ]
    planned = {str(line.product.get("id") or ""): line for line in run.assembled.lines}
    trimmed = [
        replace(planned[rewrite.line.product_id], qty=rewrite.keep_quantity, needs_approval=False)
        for rewrite in second
        if rewrite.verdict is Verdict.SHORT
        and rewrite.keep_quantity > 0
        and rewrite.line.product_id in planned
    ]
    repaired: dict[str, Any] | None = None
    second_drops = dropped_rows(second, run.cards)
    if fixes or trimmed or second_drops:
        repaired = await apply_rewrites(mcp, after, [*trimmed, *fixes], drops=second_drops)
        log.info(
            "cart.revalidated_after_write",
            fixes=len(fixes),
            drops=len(second_drops),
            trimmed=[str(line.product.get("name") or line.intent) for line in trimmed],
        )
    return {
        "written": written,
        "validations": list(after.validations),
        "recheck": [rewrite.note for rewrite in second],
        "repaired": repaired,
    }


async def apply_rewrites(
    mcp: SilpoMCP,
    snapshot: CartSnapshot,
    lines: list[PlanLine],
    *,
    drops: Sequence[str] = (),
) -> dict[str, Any]:
    products = [
        {
            "productId": line.product["id"],
            "companyId": line.product["companyId"],
            "branchId": line.product["branchId"],
            "quantity": qty_for_api(line.qty, line.product),
            "addQuantity": False,
            **({"comment": fit_comment(line.mandate)} if line.mandate else {}),
        }
        for line in lines
        if not line.needs_approval and not line.at_home and line.product.get("id")
    ]
    if not products and not drops:
        return {"success": False, "summary": "нема чого записувати"}
    written: dict[str, Any] = {"success": True}
    if products:
        outcome = await mcp.call(
            "silpo_add_or_update_cart_products",
            {"shoppingCartId": snapshot.cart_id, "products": products},
        )
        written = outcome.payload_raw
    if drops:
        await mcp.call(
            "silpo_remove_cart_products",
            {
                "shoppingCartId": snapshot.cart_id,
                "products": [{"productId": product_id} for product_id in drops],
            },
        )
        log.info("cart.dropped_gone_rows", cart_id=snapshot.cart_id, rows=len(drops))
    return written
