from __future__ import annotations

import asyncio
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from komora.agent import steps
from komora.agent.basket import (
    NEEDS_APPROVAL_NOTE,
    Assembled,
    AssemblyError,
    PlanLine,
    Tracer,
    qty_for_api,
    search_products,
)
from komora.agent.cart import (
    CartMissing,
    CartRun,
    CartSnapshot,
    article_of,
    commit,
    read_cart,
    read_cart_by_id,
)
from komora.agent.executor import Executor
from komora.agent.steps.ground import Ground
from komora.api.schemas import (
    CarryOverLine,
    CarryOverState,
    CartCarryOver,
    CartTotals,
    CheckoutExtra,
    CheckoutResult,
    CheckoutSkip,
)
from komora.config import settings as _settings
from komora.core import words
from komora.core.blockers import BRANCH_MISMATCH, explain, explain_warnings, worth_retrying
from komora.core.carryover import CarryOver, carried_over
from komora.core.facts import Facts
from komora.core.goal import handover_goal
from komora.core.location import Location
from komora.core.mandate import fit_comment
from komora.core.plan import ESSENTIAL_BEFORE_WRITE, Carried, validate
from komora.core.promo import on_sale
from komora.core.slots import same_moment
from komora.logging import get_logger
from komora.mcp.client import MCPCallError, SilpoMCP, TokenRejected, is_throttled

log = get_logger(__name__)

CHECKOUT_URL = "https://silpo.ua/checkout-new"

SKIP_NEEDS_APPROVAL = f"{NEEDS_APPROVAL_NOTE} — заміну не погоджено, не везу"
SKIP_AT_HOME = "схоже, ще є вдома — не купую вдруге"
SKIP_GONE = "на полиці вже немає, а заміни не погоджено — не везу"
SKIP_NO_PRODUCT = "немає картки товару — записати неможливо"
SKIP_REMOVED = "прибрано тобою на екрані — не везу"
SKIP_OFF_SHELF = "докинуте на екрані, а на полиці цього слота вже немає — не везу"
SKIP_NO_STOCK = "на полиці вже нуль («очікується») — зняв з кошика, щоб оформлення пройшло"
STOCK_MAX = "product.offer.stock.max"
ADDED_ON_SCREEN = "докинуто тобою на екрані"
SKIP_REJECTED = "«Сільпо» не прийняло цей рядок: {why}"

QTY_RESET_NOTE = "кількість у {rows} рядк. поставив свою — у «Сільпо» там було інше число"

WRITE_NOT_MADE = (
    "крок запису в кошик не виконався, тож у «Сільпо» не поїхало нічого — "
    "причина в трейсі, спробуй ще раз"
)

UNSEEN_NOTE = (
    "«Сільпо» не показало кошик після запису, тож про блокери я не знаю нічого — "
    "відкрий кошик у застосунку"
)

SKIP_THROTTLED = "«Сільпо» попросило зачекати -- рядок не встиг записатись"

THROTTLE_PAUSE_S = 2.0
THROTTLE_PAUSES = (THROTTLE_PAUSE_S, THROTTLE_PAUSE_S * 2.5)


def edited(
    lines: list[PlanLine], edits: Mapping[str, Decimal] | None
) -> tuple[list[PlanLine], list[CheckoutSkip]]:
    if not edits:
        return list(lines), []
    kept: list[PlanLine] = []
    removed: list[CheckoutSkip] = []
    for line in lines:
        key = str(line.product.get("externalProductId") or "")
        if key not in edits:
            kept.append(line)
            continue
        qty = Decimal(str(edits[key]))
        if qty <= 0:
            name = str(line.product.get("name") or line.intent)
            removed.append(CheckoutSkip(name=name, reason=SKIP_REMOVED))
            continue
        kept.append(replace(line, qty=qty))
    return kept, removed


async def added_on_screen(
    mcp: SilpoMCP, plan: Assembled, extras: Sequence[CheckoutExtra]
) -> tuple[list[PlanLine], list[CheckoutSkip]]:
    if not extras:
        return [], []
    wanted = [str(extra.external_product_id) for extra in extras]
    found, _ms = await search_products(mcp, wanted, plan.slot, plan.branch_id)
    lines: list[PlanLine] = []
    skipped: list[CheckoutSkip] = []
    for extra in extras:
        article = str(extra.external_product_id)
        card = next(
            (
                product
                for product in found.get(article, [])
                if str(product.get("externalProductId")) == article
            ),
            None,
        )
        qty = Decimal(str(extra.qty))
        if qty <= 0:
            continue
        if card is None or not card.get("id"):
            skipped.append(CheckoutSkip(name=extra.name or article, reason=SKIP_OFF_SHELF))
            continue
        lines.append(
            PlanLine(
                intent=str(card.get("name") or extra.name or article),
                product=card,
                qty=qty,
                reason=ADDED_ON_SCREEN,
                from_history=None,
                decided=True,
            )
        )
    return lines, skipped


async def fit_stock(
    mcp: SilpoMCP, cart_id: str, going: list[PlanLine], after: CartSnapshot
) -> tuple[set[str], list[CheckoutSkip], list[str]]:
    by_id = {str(line.product.get("id")): line for line in going}
    drops: list[tuple[str, PlanLine]] = []
    cuts: list[tuple[PlanLine, Decimal]] = []
    for entry in after.validations:
        if entry.get("message") != STOCK_MAX:
            continue
        context = entry.get("context") or {}
        product_id = str(context.get("productId") or "")
        line = by_id.get(product_id)
        stock = context.get("stock")
        if line is None or stock is None:
            continue
        have = Decimal(str(stock))
        if have <= 0:
            drops.append((product_id, line))
        elif have < line.qty:
            cuts.append((line, have))
    removed: list[CheckoutSkip] = []
    if drops:
        await mcp.call(
            "silpo_remove_cart_products",
            {
                "shoppingCartId": cart_id,
                "products": [{"productId": product_id} for product_id, _ in drops],
            },
        )
        removed = [CheckoutSkip(name=row_name(line), reason=SKIP_NO_STOCK) for _, line in drops]
    notes: list[str] = []
    if cuts:
        await mcp.call(
            "silpo_add_or_update_cart_products",
            {
                "shoppingCartId": cart_id,
                "products": [
                    {
                        "productId": line.product["id"],
                        "companyId": line.product["companyId"],
                        "branchId": line.product["branchId"],
                        "quantity": qty_for_api(have, line.product),
                        "addQuantity": False,
                        **({"comment": fit_comment(line.mandate)} if line.mandate else {}),
                    }
                    for line, have in cuts
                ],
            },
        )
        notes = [
            f"{row_name(line)}: на полиці лише {have.normalize():f}, стільки й узяв"
            for line, have in cuts
        ]
    return {product_id for product_id, _ in drops}, removed, notes


CREATED_NOTE = "кошика в акаунті ще не було — створив під твою адресу і слот."

NO_HOUSE_NOTE = (
    "кошика в акаунті ще немає, а в адресі немає номера будинку — "
    "«Сільпо» не підтвердило будинок; обери адресу з номером"
)


async def create_cart(mcp: SilpoMCP, place: Location, plan: Assembled) -> CartSnapshot:
    address = place.address
    if address is None:
        raise AssemblyError("кошика в акаунті ще немає, а створити його нема під що: назви адресу")
    if address.id is None and not address.house:
        raise AssemblyError(NO_HOUSE_NOTE)
    branch = plan_branch_of(plan, plan) or place.branch_for(str(plan.slot.get("deliveryType")))
    if not branch:
        raise AssemblyError("кошика в акаунті ще немає, а філії під адресу не знайшлось")
    arguments: dict[str, Any] = {
        "addressType": address.kind or "house",
        "latitude": address.latitude,
        "longitude": address.longitude,
        "deliveryType": plan.slot.get("deliveryType"),
        "branchId": branch,
        "timeslot": {"start": plan.slot.get("start"), "end": plan.slot.get("end")},
    }
    for key, value in (
        ("city", address.city),
        ("street", address.street),
        ("house", address.house),
    ):
        if value:
            arguments[key] = value
    payload = (await mcp.call("silpo_create_shopping_cart", arguments)).payload_raw
    cart_id = payload.get("shoppingCartId") or payload.get("id")
    if not cart_id:
        raise AssemblyError("«Сільпо» не віддало id створеного кошика — спробуй ще раз")
    log.info("checkout.cart_created", cart_id=str(cart_id), branch=branch)
    return await read_cart_by_id(mcp, str(cart_id))


def promo_lost(lines: Sequence[PlanLine], rows: Sequence[Mapping[str, Any]]) -> list[str]:
    by_key: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        article = article_of(row.get("slug"))
        if article:
            by_key[article] = row
        product_id = str(row.get("productId") or "")
        if product_id:
            by_key[product_id] = row
    gone: list[str] = []
    for line in lines:
        if not line.promo:
            continue
        row = by_key.get(str(line.product.get("externalProductId") or "")) or by_key.get(
            str(line.product.get("id") or "")
        )
        if row is None or on_sale(row):
            continue
        gone.append(str(row.get("name") or line.product.get("name") or line.intent))
    return gone


def row_name(line: PlanLine) -> str:
    return str(line.product.get("name") or line.intent)


def writable(lines: list[PlanLine]) -> tuple[list[PlanLine], list[CheckoutSkip]]:
    going: list[PlanLine] = []
    skipped: list[CheckoutSkip] = []
    for line in lines:
        name = row_name(line)
        if line.gone:
            skipped.append(CheckoutSkip(name=name, reason=SKIP_GONE))
        elif line.at_home:
            skipped.append(CheckoutSkip(name=name, reason=SKIP_AT_HOME))
        elif not line.product.get("id"):
            skipped.append(CheckoutSkip(name=name, reason=SKIP_NO_PRODUCT))
        else:
            going.append(line)
    return going, skipped


def mandates_lost(going: Sequence[PlanLine], rows: Sequence[Mapping[str, Any]]) -> list[str]:
    by_id = {str(row.get("productId") or ""): row for row in rows}
    lost: list[str] = []
    for line in going:
        if not line.mandate:
            continue
        row = by_id.get(str(line.product["id"]))
        if row is None:
            continue
        if str(row.get("comment") or "").strip() != fit_comment(line.mandate):
            lost.append(row_name(line))
    return lost


def qty_overwritten(rows: Sequence[Mapping[str, Any]], lines: Sequence[PlanLine]) -> list[str]:
    have = {
        str(row.get("productId") or ""): Decimal(str(row.get("quantity") or 0))
        for row in rows
        if row.get("productId")
    }
    said: list[str] = []
    for line in lines:
        was = have.get(str(line.product.get("id") or ""))
        now = Decimal(str(qty_for_api(line.qty, line.product)))
        if was is None or was == now:
            continue
        said.append(f"{row_name(line)}: у кошику було {was.normalize():f}, поставив {now:f}")
    return said


def cart_payload(lines: list[PlanLine]) -> list[dict[str, Any]]:
    return [
        {
            "productId": line.product["id"],
            "companyId": line.product["companyId"],
            "branchId": line.product["branchId"],
            "quantity": qty_for_api(line.qty, line.product),
            "addQuantity": False,
            **({"comment": fit_comment(line.mandate)} if line.mandate else {}),
        }
        for line in lines
    ]


async def _write_one(mcp: SilpoMCP, cart_id: str, line: PlanLine) -> None:
    payload = {"shoppingCartId": cart_id, "products": cart_payload([line])}
    for pause in (None, *THROTTLE_PAUSES):
        if pause is not None:
            await asyncio.sleep(pause)
        try:
            await mcp.call("silpo_add_or_update_cart_products", payload)
            return
        except MCPCallError as exc:
            if not is_throttled(exc) or pause == THROTTLE_PAUSES[-1]:
                raise


async def already_in_cart(mcp: SilpoMCP, cart_id: str) -> dict[str, Decimal]:
    try:
        after = await read_cart_by_id(mcp, cart_id)
    except (MCPCallError, AssemblyError) as exc:
        log.warning("checkout.landed_unknown", cart_id=cart_id, error=str(exc)[:160])
        return {}
    if not after.seen:
        return {}
    return {
        str(row.get("productId") or ""): Decimal(str(row.get("quantity") or 0))
        for row in after.rows
        if row.get("productId")
    }


async def write_rows(
    mcp: SilpoMCP, cart_id: str, going: list[PlanLine]
) -> tuple[list[PlanLine], list[CheckoutSkip]]:
    if not going:
        return going, []
    try:
        await mcp.call(
            "silpo_add_or_update_cart_products",
            {"shoppingCartId": cart_id, "products": cart_payload(going)},
        )
        return going, []
    except MCPCallError as exc:
        batch_error = exc
        log.warning(
            "checkout.batch_rejected",
            cart_id=cart_id,
            rows=len(going),
            error=str(exc)[:200],
        )

    landed = await already_in_cart(mcp, cart_id)
    if landed:
        log.info("checkout.batch_landed", cart_id=cart_id, rows=len(landed))

    written: list[PlanLine] = []
    rejected: list[CheckoutSkip] = []
    for line in going:
        want = Decimal(str(qty_for_api(line.qty, line.product)))
        if landed.get(str(line.product.get("id") or "")) == want:
            written.append(line)
            continue
        try:
            await _write_one(mcp, cart_id, line)
        except MCPCallError as exc:
            reason = SKIP_THROTTLED if is_throttled(exc) else SKIP_REJECTED.format(why=exc.reason)
            rejected.append(CheckoutSkip(name=row_name(line), reason=reason))
            log.warning(
                "checkout.row_rejected",
                cart_id=cart_id,
                name=row_name(line),
                qty=str(line.qty),
                product_id=str(line.product.get("id") or ""),
                error=str(exc)[:200],
            )
        else:
            written.append(line)

    if not written:
        raise batch_error
    log.info(
        "checkout.rows_salvaged", cart_id=cart_id, written=len(written), rejected=len(rejected)
    )
    return written, rejected


async def align_slot(mcp: SilpoMCP, snapshot: CartSnapshot, slot: dict[str, Any]) -> bool:
    start, end = slot.get("start"), slot.get("end")
    if not start or not end:
        return False
    if same_moment(snapshot.timeslot_start, start) and same_moment(snapshot.timeslot_end, end):
        return False
    await mcp.call(
        "silpo_update_shopping_cart",
        {
            "shoppingCartId": snapshot.cart_id,
            "deliveryType": str(slot.get("deliveryType") or snapshot.delivery_type),
            "timeslot": {"start": start, "end": end},
            "address": snapshot.address,
            "shipments": [dict(shipment) for shipment in snapshot.shipments],
        },
    )
    log.info("checkout.slot_aligned", cart_id=snapshot.cart_id, start=start, end=end)
    return True


def blocker_codes(validations: list[dict[str, Any]]) -> list[str]:
    counts: dict[str, int] = {}
    for entry in validations:
        if entry.get("level") != "error" or not entry.get("message"):
            continue
        code = str(entry["message"])
        counts[code] = counts.get(code, 0) + 1
    return [code if n == 1 else f"{code} ×{n}" for code, n in counts.items()]


def warning_codes(validations: list[dict[str, Any]]) -> list[str]:
    counts: dict[str, int] = {}
    for entry in validations:
        if entry.get("level") != "warning" or not entry.get("message"):
            continue
        code = str(entry["message"])
        counts[code] = counts.get(code, 0) + 1
    return [code if n == 1 else f"{code} ×{n}" for code, n in counts.items()]


def extras_of(snapshot: CartSnapshot, going: list[PlanLine]) -> CarryOver:
    return carried_over(snapshot.rows, writing={str(line.product["id"]) for line in going})


def carry_over_of(extras: CarryOver, state: CarryOverState) -> CartCarryOver:
    return CartCarryOver(
        state=state,
        total=extras.total,
        lines=[
            CarryOverLine(name=row.name, qty=row.quantity, total=row.total) for row in extras.rows
        ],
    )


def drop_payload(extras: CarryOver) -> list[dict[str, Any]]:
    return [{"productId": row.product_id} for row in extras.rows]


async def hand_off(
    mcp: SilpoMCP,
    run: Assembled | CartRun,
    *,
    existing: CarryOverState = CarryOverState.ASKING,
    lines: Mapping[str, Decimal] | None = None,
    added: Sequence[CheckoutExtra] | None = None,
    place: Location | None = None,
) -> CheckoutResult:
    plan = run.assembled if isinstance(run, CartRun) else run
    if (lines or added) and isinstance(run, CartRun):
        raise AssemblyError(
            "правки складу чужого кошика поки їдуть перезбіркою — перезбери, "
            "щоб поїхало саме те, що бачиш"
        )
    kept, removed = edited(plan.lines, lines)
    on_screen, off_shelf = await added_on_screen(mcp, plan, added or ())
    going, skipped = writable([*kept, *on_screen])
    skipped = [*removed, *off_shelf, *skipped]
    if not going:
        return CheckoutResult(
            written=0,
            skipped=skipped,
            summary="у кошик нічого не поїхало: жоден рядок не має плану, який можна записати",
        )

    trace = Tracer()
    done_before = Carried(seen=frozenset(ESSENTIAL_BEFORE_WRITE))
    facts = Facts(
        {
            "cart": {"id": ""},
            "lines": list(going),
            "economics": plan.basket.total,
            "slot": dict(plan.slot or {}),
        }
    )
    runner = Executor(
        facts,
        plan=validate(
            ["cart.write", "cart.reread"],
            writes_allowed=True,
            known=facts.names(),
            carried=done_before,
        ),
        trace=trace,
        writes_allowed=True,
        carried=done_before,
        fatal=(MCPCallError, AssemblyError, TokenRejected),
    )
    ground = Ground(mcp=mcp, cfg=_settings, moment=datetime.now(UTC), facts=facts, trace=trace)
    writing = steps.Cart(ground)

    carry: CartCarryOver | None = None
    created = False
    reset: list[str] = []
    if isinstance(run, CartRun):
        await align_slot(mcp, await read_cart_by_id(mcp, run.snapshot.cart_id), plan.slot)
        await commit(mcp, run)
        cart_id = run.snapshot.cart_id
    else:
        try:
            snapshot = await read_cart(mcp)
        except CartMissing:
            if place is None or place.address is None:
                raise
            snapshot = await create_cart(mcp, place, plan)
            created = True
        cart_id = snapshot.cart_id
        astray = branch_astray(snapshot, plan_branch_of(run, plan))
        if astray is not None:
            log.warning(
                "checkout.branch_mismatch",
                cart_id=cart_id,
                cart_branch=snapshot.branch_id,
                plan_branch=astray,
            )
            return CheckoutResult(
                written=0,
                skipped=skipped,
                blockers=[BRANCH_MISMATCH],
                blocker_notes=explain([BRANCH_MISMATCH]),
                retry_helps=False,
                summary=(
                    "кошик у «Сільпо» стоїть на іншому магазині, ніж той, для якого я "
                    "збирав за твоєю адресою — записувати туди товари з іншої полиці "
                    "означало б замовлення, яке не збереться"
                ),
            )
        extras = extras_of(snapshot, going)
        carry = carry_over_of(extras, existing) if extras else None
        if carry is not None and existing is CarryOverState.ASKING:
            log.info("checkout.carry_over_asked", cart_id=cart_id, rows=len(carry.lines))
            return CheckoutResult(
                written=0, skipped=skipped, carry_over=carry, summary=asking_summary(carry)
            )
        await align_slot(mcp, snapshot, plan.slot)
        made = await runner.run(
            "cart.write",
            lambda bound: writing.write(bound, put=lambda: write_rows(mcp, cart_id, going)),
            step_id="step-write",
            tool=steps.cart.WRITE_TOOL,
        )
        if made is None:
            raise AssemblyError(WRITE_NOT_MADE)
        going, rejected = writing.going, writing.rejected
        skipped.extend(rejected)
        reset = qty_overwritten(snapshot.rows, going)
        if reset:
            trace.add(
                "step-qty-reset",
                "code",
                {"переписано": reset},
                f"кількість у кошику переписав своєю: {len(reset)} {_plural(len(reset))}",
                decision="`addQuantity: false` -- рядок каже «стільки ВСЬОГО»: інакше "
                "повторне «Оформити» подвоювало б кошик. Але число, поставлене руками "
                "в «Сільпо», воно затирає, і мовчати про це не можна",
                tag=f"{len(reset)} переписано",
                tag_tone="warn",
            )
        if carry is not None and existing is CarryOverState.REMOVED:
            await mcp.call(
                "silpo_remove_cart_products",
                {"shoppingCartId": cart_id, "products": drop_payload(extras)},
            )

    reread = lambda bound: writing.reread(  # noqa: E731
        bound, read=lambda: read_cart_by_id(mcp, cart_id)
    )
    await runner.settle(reread, step_id="step-reread", tool=steps.cart.REREAD_TOOL)
    if writing.after is None:
        await runner.run("cart.reread", reread, step_id="step-reread", tool=steps.cart.REREAD_TOOL)
    after = writing.after if writing.after is not None else await read_cart_by_id(mcp, cart_id)
    stock_cut: list[str] = []
    if not isinstance(run, CartRun):
        dropped_ids, no_stock, stock_cut = await fit_stock(mcp, cart_id, going, after)
        if dropped_ids or stock_cut:
            trace.add(
                "step-stock-fit",
                "silpo_add_or_update_cart_products",
                {"знято": [skip.name for skip in no_stock], "урізано": stock_cut},
                f"«Сільпо» не прийняло кількість: знято {len(no_stock)}, урізано "
                f"{len(stock_cut)} -- перечитую кошик",
                decision="нуль на полиці -- рядок знімається і називає себе; менше, ніж "
                "просили, -- беру, скільки є: «зменш у застосунку» не робота агента",
                tag=f"-{len(no_stock)} без залишку" if no_stock else f"{len(stock_cut)} урізано",
                tag_tone="warn",
            )
            going = [line for line in going if str(line.product.get("id")) not in dropped_ids]
            skipped = [*skipped, *no_stock]
            after = await read_cart_by_id(mcp, cart_id)
    blockers = blocker_codes(list(after.validations))
    warnings = explain_warnings(warning_codes(list(after.validations)))
    unseen = not after.seen
    money = totals_of(after, estimate=plan.basket.total)
    gone = promo_lost(going, after.rows)
    with_mandate = [line for line in going if line.mandate]
    lost_mandates = mandates_lost(going, after.rows)
    unmandated = [row_name(line) for line in going if line.needs_approval and not line.mandate]
    if with_mandate:
        shown_lost = ", ".join(lost_mandates[:3])
        trace.add(
            "step-mandates",
            "code",
            {"з мандатом": len(with_mandate), "не записався": lost_mandates},
            f"мандат у полі коментаря: записався {len(with_mandate) - len(lost_mandates)} "
            f"з {len(with_mandate)}" + (f" — не записався: {shown_lost}" if lost_mandates else ""),
            tag=f"{len(lost_mandates)} без мандата" if lost_mandates else None,
            tag_tone="warn" if lost_mandates else "muted",
        )

    in_cart = {str(row.get("productId") or "") for row in after.rows}
    goal = handover_goal(
        written=sorted(in_cart - {""}),
        planned=[str(line.product["id"]) for line in going],
        cart_id=cart_id,
        slot_written=after.timeslot_start,
        slot_planned=plan.slot.get("start") if plan.slot else None,
        reread=True,
    )
    if goal.broken:
        log.warning(
            "checkout.goal_unmet",
            cart_id=cart_id,
            unmet=[duty.name for duty in goal.broken],
        )

    log.info(
        "checkout.handed_off",
        cart_id=cart_id,
        written=len(going),
        skipped=len(skipped),
        blockers=blockers,
        carry_over=0 if carry is None else len(carry.lines),
        promo_gone=len(gone),
    )
    return CheckoutResult(
        written=len(going),
        skipped=skipped,
        trace=trace.steps,
        blockers=blockers,
        blocker_notes=explain(blockers),
        warnings=warnings,
        retry_helps=worth_retrying(blockers),
        carry_over=carry,
        promo_gone=gone,
        mandate_lost=lost_mandates,
        unmandated=unmandated,
        stock_cut=stock_cut,
        checkout_web_link=None if blockers or unseen else (after.checkout_web_link or CHECKOUT_URL),
        cart_web_link=CHECKOUT_URL if going else None,
        totals=money,
        bonus_available=after.bonus_available or None,
        summary=(f"{CREATED_NOTE} " if created else "")
        + summarize(len(going), skipped, blockers, money, carry)
        + (f" · {UNSEEN_NOTE}" if unseen else "")
        + (f" · {QTY_RESET_NOTE.format(rows=len(reset))}" if reset else "")
        + ("" if goal.ok else " · " + goal.note())
        + (f" · коментар збирачу не зберігся: {len(lost_mandates)}" if lost_mandates else "")
        + (f" · без мандата: {len(unmandated)} (заміну не погоджено)" if unmandated else ""),
    )


NOTABLE_GAP = Decimal(1)


def totals_of(after: CartSnapshot, *, estimate: Decimal | None = None) -> CartTotals | None:
    if after.total_after_discounts is None:
        return None
    gap = None if estimate is None else abs(estimate - after.total_after_discounts)
    return CartTotals(
        products=after.products_total,
        discount=after.discount,
        delivery=after.delivery_cost or Decimal(0),
        service_fee=after.service_fee,
        to_pay=after.total_after_discounts,
        estimate=estimate if gap is not None and gap >= NOTABLE_GAP else None,
    )


def asking_summary(carry: CartCarryOver) -> str:
    count = len(carry.lines)
    return (
        f"у кошику «Сільпо» вже лежить {count} {_plural(count)} "
        f"на {_money(carry.total)} грн, яких немає в цьому плані — "
        "скажи, доповнити чи почати заново"
    )


def summarize(
    written: int,
    skipped: list[CheckoutSkip],
    blockers: list[str],
    totals: CartTotals | None = None,
    carry_over: CartCarryOver | None = None,
) -> str:
    parts = [f"у кошик «Сільпо» поїхало {written} " + _plural(written)]
    if totals is not None:
        parts.append(f"до оплати {_money(totals.to_pay)} грн")
    if carry_over is not None:
        count = len(carry_over.lines)
        parts.append(
            f"{count} {_plural(count)} поза планом на {_money(carry_over.total)} грн я зняв"
            if carry_over.state is CarryOverState.REMOVED
            else f"у кошику лишилось ще {count} {_plural(count)} поза планом "
            f"на {_money(carry_over.total)} грн — вони теж у сумі"
        )
    if skipped:
        parts.append(f"{len(skipped)} лишилось тут — причина в кожного своя")
    if blockers:
        parts.append("оформлення поки блокує сам кошик: " + ", ".join(blockers))
    return "; ".join(parts) + "."


def _money(value: Decimal) -> str:
    normalized = Decimal(value).normalize()
    return f"{normalized:f}"


def _plural(count: int) -> str:
    return words.rows(count)


def plan_branch_of(run: Assembled | CartRun, plan: Assembled) -> str | None:
    if isinstance(run, CartRun):
        return run.snapshot.branch_id
    return next(
        (str(line.product["branchId"]) for line in plan.lines if line.product.get("branchId")),
        None,
    )


def branch_astray(snapshot: CartSnapshot, plan_branch: str | None) -> str | None:
    if not snapshot.branch_id or not plan_branch:
        return None
    return plan_branch if snapshot.branch_id != plan_branch else None


__all__ = [
    "CHECKOUT_URL",
    "NOTABLE_GAP",
    "CheckoutResult",
    "MCPCallError",
    "align_slot",
    "asking_summary",
    "blocker_codes",
    "branch_astray",
    "carry_over_of",
    "cart_payload",
    "drop_payload",
    "extras_of",
    "hand_off",
    "plan_branch_of",
    "summarize",
    "totals_of",
    "writable",
]
