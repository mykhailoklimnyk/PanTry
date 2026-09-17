from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from functools import partial

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import JSONResponse

from komora.agent import correction, place, swaps
from komora.agent.bar import bar_live
from komora.agent.basket import (
    Assembled,
    AssemblyError,
    Receipts,
    assemble_list,
    delivery_options_live,
    forget_intents,
    forget_keeps,
    kind_key,
    manual_item,
    manual_key,
    mark_pantry,
    name_cycle,
    name_kind,
    name_mandate,
    pantry_live,
    read_receipts,
    same_kind,
)
from komora.agent.cart import CartRun, assemble_cart, read_cart, state_of
from komora.agent.checkout import hand_off, writable
from komora.agent.correction import CorrectionError
from komora.agent.llm import Meter, build_llm
from komora.agent.llm.catalog import SNAPSHOT, arrange, fetch_ids
from komora.agent.llm.validation import Validated
from komora.agent.nextlist import compose as compose_list
from komora.agent.options import options_for
from komora.agent.pantry import forget_loop
from komora.agent.pantry import refine as refine_pantry
from komora.agent.probe import MAX_COVERS as PROBE_COVERS
from komora.agent.probe import MAX_QUESTIONS as PROBE_CEILING
from komora.agent.probe import intent_spread
from komora.agent.refill import RefillError, pick_answer, refill, take_cheaper
from komora.agent.sanity import forget_sense
from komora.agent.spending import WeekSpendError, week_spend
from komora.agent.steps import place as place_step
from komora.agent.table import top_up_table
from komora.api import history, places, progress, quota, runs
from komora.api.auth_routes import Guest, LlmKey, forget
from komora.api.auth_routes import router as auth_router
from komora.api.schemas import (
    AnswerTaken,
    Bar,
    BarGroupChoice,
    Basket,
    BuildRequest,
    CartState,
    CheaperRequest,
    CheckoutRequest,
    CheckoutResult,
    CorrectionRequest,
    DeliveryOption,
    Exclusion,
    Health,
    ModelOption,
    NextList,
    Pantry,
    PantryAdjustment,
    PantryAsk,
    PantryEntry,
    PantryItem,
    PickRequest,
    Place,
    PlaceChoice,
    PlaceOption,
    PlaceQuery,
    Progress,
    ProgressAnswer,
    Quota,
    RefillRequest,
    RefineRequest,
    RuleEntry,
    RuleToggle,
    RunCost,
    SavedSwap,
    SourceChoice,
    SwapDecision,
    SwapOption,
    SwapsRequest,
    Toll,
    WantedEntry,
    WantedRow,
    WeekSpend,
)
from komora.config import settings
from komora.core import models
from komora.core import quota as core_quota
from komora.core import rules as rules_of
from komora.core.bar import DrinkKind
from komora.core.location import Address, Location
from komora.core.marks import bought_now
from komora.core.nextlist import Row as NextRow
from komora.core.nextlist import changes as next_changes
from komora.core.nextlist import choose as choose_next
from komora.core.occasion import BuildMode, occasion_of
from komora.core.pantry import is_manual, manual_id
from komora.core.said import (
    GUEST,
    PURCHASES,
    SOURCE_MANUAL,
    SOURCE_RECEIPTS,
    Said,
    origin_of_list,
)
from komora.core.target import band
from komora.db import pantry as pantry_marks
from komora.db import rules as guest_rules
from komora.db import swaps as saved_swaps
from komora.db import wanted as wanted_store
from komora.db.pool import get_pool, pool_lifespan
from komora.db.wanted import Want as WantedItem
from komora.logging import get_logger
from komora.mcp.client import MCPCallError, SilpoMCP, TokenRejected
from komora.version import deployed_sha

PANTRY_SCOPE = pantry_marks.PANTRY

AGENT = "agent"

NEXT_LIST_RUN = "nextlist"
BAR_SCOPE = pantry_marks.BAR

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    async with pool_lifespan(wait=False):
        log.info("api.started", login_ready=settings.guest_login_ready)
        yield


app = FastAPI(
    title="Комора",
    version="0.1.0",
    summary="Передбачений тижневий кошик з мандатом на заміну",
    lifespan=lifespan,
)


app.include_router(auth_router)


@app.get("/api/health", response_model=Health)
async def health() -> Health:
    pool = get_pool()
    try:
        async with pool.connection(timeout=2) as conn:
            await conn.execute("select 1")
        db_ok = True
    except Exception as exc:
        log.warning("api.health.db_down", error=str(exc))
        db_ok = False

    return Health(
        database=db_ok,
        login_ready=settings.guest_login_ready,
        version=deployed_sha(),
    )


@app.get("/api/quota", response_model=Quota)
async def read_quota(guest: Guest) -> Quota:
    try:
        verdict = await quota.look(guest)
    except Exception as exc:
        log.warning("api.quota.counter_down", error=str(exc))
        return Quota(
            blocked=False,
            headline="лічильник витрат мовчить — скільки лишилось, невідомо",
            left=0,
        )
    spent = verdict.spent
    return Quota(
        blocked=not verdict.allowed,
        scope=verdict.scope,
        headline=verdict.headline,
        action=verdict.action,
        left=verdict.left,
        resets_at=verdict.resets_at,
        contact=settings.contact if not verdict.allowed else None,
        toll=Toll(
            runs=spent.login_runs,
            usd=(
                None
                if not spent.login_runs or spent.login_unpriced >= spent.login_runs
                else spent.login_usd
            ),
            unpriced=spent.login_unpriced,
            tokens_in=spent.login_tokens_in,
            tokens_out=spent.login_tokens_out,
            guest_usd=spent.login_guest_usd or None,
        ),
    )


@app.get("/api/models", response_model=list[ModelOption])
async def list_models() -> list[ModelOption]:
    ids = SNAPSHOT
    if settings.bedrock_api_key:
        try:
            ids = tuple(
                await fetch_ids(
                    base_url=settings.bedrock_base_url,
                    api_key=settings.bedrock_api_key,
                )
            )
        except Exception as exc:
            log.warning("api.models.fetch_failed", error=str(exc))
            ids = SNAPSHOT

    recommended = {row.id for row in models.RECOMMENDED}
    return [
        ModelOption(
            id=entry.id,
            label=entry.label,
            note=entry.note,
            available=entry.available,
            active=entry.id == settings.bedrock_model_id,
            recommended=entry.id in recommended,
            needs_key=models.needs_guest_key(entry.id),
            supports_fast=models.supports_fast(entry.id),
            fast_by_default=models.fast_by_default(entry.id),
        )
        for entry in arrange(ids)
    ]


def _run_llm(model: str | None, *, api_key: str | None, meter: Meter) -> Validated | None:
    chosen = model or settings.bedrock_model_id
    if models.needs_guest_key(chosen):
        if not api_key:
            raise HTTPException(
                status_code=402,
                detail="ця модель працює на твоєму ключі OpenAI — додай ключ і збери ще раз",
            )
        meter.payer = "guest"
        return build_llm(
            model=chosen, base_url=settings.openai_base_url, api_key=api_key, meter=meter
        )
    if not settings.bedrock_api_key:
        return None
    meter.payer = "project"
    return build_llm(
        model=chosen,
        base_url=settings.bedrock_base_url,
        api_key=settings.bedrock_api_key,
        meter=meter,
    )


def silpo_silent(exc: MCPCallError) -> HTTPException:
    return HTTPException(status_code=503, detail=f"«Сільпо» не відповіло: {exc.reason}")


async def cart_branch(mcp: SilpoMCP) -> str | None:
    try:
        cart = await place_step.read_cart(mcp)
    except MCPCallError as exc:
        log.warning("place.cart_branch_failed", error=str(exc)[:120])
        return None
    branch = cart.get("branch")
    return str(branch) if branch else None


async def place_of(mcp: SilpoMCP, guest: Guest) -> Location:
    known = places.recall(guest.owner)
    if known is not None:
        return known.location
    saved = await place.saved_addresses(mcp)
    location = await place.resolve(mcp, saved=saved, ask_cart=partial(cart_branch, mcp))
    places.remember(places.Known(location=location, saved=tuple(saved)), owner=guest.owner)
    return location


@app.get("/api/place", response_model=Place)
async def where_to(guest: Guest) -> Place:
    known = places.recall(guest.owner)
    if known is not None and known.branch is not None:
        return places.to_place(known)
    try:
        async with SilpoMCP(token=guest.access) as mcp:
            if known is None:
                saved = await place.saved_addresses(mcp)
                location = await place.resolve(mcp, saved=saved, ask_cart=partial(cart_branch, mcp))
            else:
                saved, location = list(known.saved), known.location
            branch = await place.branch_label(mcp, location.branch_id)
    except MCPCallError as exc:
        raise silpo_silent(exc) from exc
    history.forget(guest.owner)
    forget_loop(guest.account)
    return places.to_place(
        places.remember(
            places.Known(location=location, saved=tuple(saved), branch=branch),
            owner=guest.owner,
        )
    )


@app.post("/api/place/search", response_model=list[PlaceOption])
async def search_place(query: PlaceQuery, guest: Guest) -> list[PlaceOption]:
    try:
        async with SilpoMCP(token=guest.access) as mcp:
            found = await place.search_addresses(mcp, query.text)
    except MCPCallError as exc:
        raise silpo_silent(exc) from exc
    return [places.option_of(address) for address in found]


@app.post("/api/place", response_model=Place)
async def choose_place(choice: PlaceChoice, guest: Guest) -> Place:
    address = Address(
        label=choice.label,
        latitude=choice.latitude,
        longitude=choice.longitude,
        id=choice.id,
    )
    cached = places.recall(guest.owner)
    try:
        async with SilpoMCP(token=guest.access) as mcp:
            location = await place.resolve(mcp, address=address, ask_cart=partial(cart_branch, mcp))
            saved = cached.saved if cached else tuple(await place.saved_addresses(mcp))
            branch = await place.branch_label(mcp, location.branch_id)
    except MCPCallError as exc:
        raise silpo_silent(exc) from exc
    history.forget(guest.owner)
    forget_loop(guest.account)
    return places.to_place(
        places.remember(
            places.Known(location=location, saved=saved, branch=branch), owner=guest.owner
        )
    )


@app.post("/api/basket", response_model=Basket)
async def build_basket(request: BuildRequest, guest: Guest, api_key: LlmKey) -> Basket:
    request = request.model_copy(update={"cold": _cold_run(guest, request.cold)})
    meter = Meter()
    llm = _run_llm(request.model, api_key=api_key, meter=meter)
    key = request.progress_key
    on_step = None
    answer_of = None
    if key is not None:
        progress.open_channel(key, owner=guest.owner)
        on_step = lambda step: progress.push(key, step)  # noqa: E731
        answer_of = lambda qid, seconds: progress.wait(key, qid, seconds=seconds)  # noqa: E731
    async with quota.counted(guest, kind="basket", meter=meter):
        try:
            async with SilpoMCP(token=guest.access) as mcp:
                where = await place_of(mcp, guest)
                said = Said() if request.source == "cart" else await _said_of(guest, PANTRY_SCOPE)
                run = (
                    await assemble_cart(
                        mcp,
                        llm,
                        request,
                        place=where,
                        pool=get_pool(),
                        account=guest.account,
                        on_step=on_step,
                    )
                    if request.source == "cart"
                    else await assemble_list(
                        mcp,
                        llm,
                        request,
                        place=where,
                        marks=said.marks,
                        cycles=said.cycles,
                        manual=said.written,
                        drinks=said.drinks,
                        wanted=await _wanted_of(guest),
                        saved_chains=await _saved_chains_of(guest),
                        pool=get_pool(),
                        account=guest.account,
                        on_step=on_step,
                        answer_of=answer_of,
                    )
                )
                if request.source != "cart":
                    run = await top_up_table(
                        mcp,
                        llm,
                        run,
                        occasion_of(request.mode, request.occasion_people, request.event_style),
                        pool=get_pool(),
                        account=guest.account,
                        saved_chains=await _saved_chains_of(guest),
                        receipts=_remembered_receipts(guest),
                        on_step=on_step,
                    )
        except AssemblyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except MCPCallError as exc:
            raise silpo_silent(exc) from exc
        finally:
            if key is not None:
                progress.finish(key)

    assembled = run.assembled if isinstance(run, CartRun) else run
    if assembled.unresolved:
        log.info("basket.unresolved", intents=assembled.unresolved)
    return runs.remember(run, owner=guest.owner)


@app.get("/api/progress/{key}", response_model=Progress)
async def build_progress(key: str, guest: Guest) -> Progress:
    if not progress.valid_key(key):
        raise HTTPException(status_code=404, detail="такого прогону немає")
    seen = progress.read(key, owner=guest.owner)
    if seen is None:
        raise HTTPException(status_code=404, detail="такого прогону немає")
    return Progress(steps=list(seen.steps), done=seen.done)


@app.post("/api/progress/{key}/answer", response_model=AnswerTaken)
async def answer_progress(key: str, body: ProgressAnswer, guest: Guest) -> AnswerTaken:
    if not progress.valid_key(key):
        raise HTTPException(status_code=404, detail="такого прогону немає")
    if progress.read(key, owner=guest.owner) is None:
        raise HTTPException(status_code=404, detail="такого прогону немає")
    return AnswerTaken(
        taken=progress.answer(
            key,
            owner=guest.owner,
            question_id=body.question_id,
            option_id=body.option_id,
        )
    )


@app.post("/api/basket/{run_id}/checkout", response_model=CheckoutResult)
async def checkout(
    run_id: str, guest: Guest, api_key: LlmKey, body: CheckoutRequest | None = None
) -> CheckoutResult:
    run = runs.recall(run_id, owner=guest.owner)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail="цей прогін уже не в пам'яті сервера — збери кошик заново, "
            "щоб оформити рівно те, що бачиш",
        )
    try:
        async with SilpoMCP(token=guest.access, writes=True) as mcp:
            asked = body or CheckoutRequest()
            known = places.recall(guest.owner)
            result = await hand_off(
                mcp,
                run,
                existing=asked.existing,
                lines={k: Decimal(str(v)) for k, v in (asked.lines or {}).items()} or None,
                added=asked.extras,
                place=known.location if known is not None else None,
            )
            plan = run.assembled if isinstance(run, CartRun) else run
            rounds = 0
            while (
                rounds < 2
                and result.written
                and result.totals is not None
                and not isinstance(run, CartRun)
                and plan.occasion is not None
                and plan.occasion.mode is BuildMode.EVENT
                and plan.basket.budget is not None
                and Decimal(str(result.totals.to_pay)) < band(Decimal(str(plan.basket.budget))).low
            ):
                rounds += 1
                meter = Meter()
                llm = _run_llm(asked.model, api_key=api_key, meter=meter)
                if llm is None:
                    break
                async with quota.counted(guest, kind="refill", meter=meter):
                    topped = await top_up_table(
                        mcp,
                        llm,
                        run,
                        plan.occasion,
                        paid=Decimal(str(result.totals.to_pay)),
                        pool=get_pool(),
                        account=guest.account,
                        saved_chains=await _saved_chains_of(guest),
                        receipts=_remembered_receipts(guest),
                    )
                topped_plan = topped.assembled if isinstance(topped, CartRun) else topped
                if len(topped_plan.lines) <= len(plan.lines):
                    break
                again = await hand_off(
                    mcp,
                    topped,
                    existing=asked.existing,
                    lines={k: Decimal(str(v)) for k, v in (asked.lines or {}).items()} or None,
                    added=asked.extras,
                    place=known.location if known is not None else None,
                )
                run = topped
                plan = topped_plan
                result = again.model_copy(
                    update={"basket": runs.remember(topped, owner=guest.owner)}
                )
    except AssemblyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except MCPCallError as exc:
        raise silpo_silent(exc) from exc
    if result.written:
        burned = await _burn_wanted(guest, run)
        result = result.model_copy(
            update={"wanted_burned": burned.labels, "wanted_stocked": burned.stocked}
        )
    return result


@app.get("/api/basket/{run_id}/options", response_model=list[SwapOption])
async def swap_options(
    run_id: str, guest: Guest, line: str, q: str | None = None
) -> list[SwapOption]:
    run = runs.recall(run_id, owner=guest.owner)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail="цей прогін уже не в пам'яті сервера — збери кошик заново",
        )
    try:
        async with SilpoMCP(token=guest.access) as mcp:
            found = await options_for(mcp, run, article=line, query=q)
    except MCPCallError as exc:
        raise silpo_silent(exc) from exc
    swaps.remember_options(run, found)
    return found


@app.post("/api/basket/{run_id}/swaps", response_model=Basket)
async def apply_swaps(run_id: str, request: SwapsRequest, guest: Guest) -> Basket:
    run = runs.recall(run_id, owner=guest.owner)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail="цей прогін уже не в пам'яті сервера — збери кошик заново",
        )
    decided = swaps.apply(run, request.swaps)
    if request.remember:
        await _remember_chains(guest, decided, request.swaps)
    return runs.remember(decided, owner=guest.owner)


async def _saved_chains_of(guest: Guest) -> dict[str, tuple[str, ...]]:
    try:
        rows = await saved_swaps.load(get_pool(), guest.account)
    except Exception as exc:
        log.warning("swaps.saved_unavailable", error=str(exc))
        return {}
    return {kind: row.articles for kind, row in rows.items()}


async def _remember_chains(
    guest: Guest, run: Assembled | CartRun, decisions: Sequence[SwapDecision]
) -> None:
    plan = run.assembled if isinstance(run, CartRun) else run
    touched = {str(decision.external_product_id) for decision in decisions}
    rows = {
        kind_key(line.intent): saved_swaps.Saved(
            line.intent,
            tuple(saved_swaps.Link(alt.external_product_id, alt.name) for alt in line.chain),
        )
        for line in plan.lines
        if str(line.product.get("externalProductId")) in touched and line.chain
    }
    if not rows:
        return
    try:
        await saved_swaps.save(get_pool(), guest.account, rows)
    except Exception as exc:
        log.warning("swaps.not_remembered", error=str(exc))


async def _saved_now(guest: Guest) -> list[SavedSwap]:
    try:
        rows = await saved_swaps.load(get_pool(), guest.account)
    except Exception as exc:
        log.warning("swaps.saved_unavailable", error=str(exc))
        return []
    return [
        SavedSwap(
            id=manual_id(kind),
            label=row.label,
            links=[link.name for link in row.links],
        )
        for kind, row in rows.items()
    ]


@app.get("/api/swaps/saved", response_model=list[SavedSwap])
async def list_saved_swaps(guest: Guest) -> list[SavedSwap]:
    return await _saved_now(guest)


@app.delete("/api/swaps/saved/{item_id}", response_model=list[SavedSwap])
async def drop_saved_swap(item_id: str, guest: Guest) -> list[SavedSwap]:
    if not is_manual(item_id):
        raise HTTPException(status_code=404, detail="такого погодження немає")
    try:
        stored = await saved_swaps.load(get_pool(), guest.account)
        kind = next((key for key in stored if manual_id(key) == item_id), None)
        if kind is not None:
            await saved_swaps.drop(get_pool(), guest.account, kind)
    except Exception as exc:
        log.warning("swaps.saved_undeletable", error=str(exc))
        raise HTTPException(
            status_code=503, detail="сховище не відповіло — погодження не знялось"
        ) from exc
    return await _saved_now(guest)


@app.post("/api/basket/{run_id}/correction", response_model=Basket)
async def apply_correction(run_id: str, request: CorrectionRequest, guest: Guest) -> Basket:
    run = runs.recall(run_id, owner=guest.owner)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail="цей прогін уже не в пам'яті сервера — збери кошик заново",
        )
    try:
        corrected, _ = correction.apply(run, request)
    except CorrectionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return runs.remember(corrected, owner=guest.owner)


@app.post("/api/basket/{run_id}/pick", response_model=Basket)
async def pick_for_question(run_id: str, request: PickRequest, guest: Guest) -> Basket:
    run = runs.recall(run_id, owner=guest.owner)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail="цей прогін уже не в пам'яті сервера — збери кошик заново",
        )
    try:
        filled = await pick_answer(run, intent=request.intent, article=request.external_product_id)
    except RefillError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return runs.remember(filled, owner=guest.owner)


@app.post("/api/basket/{run_id}/cheaper", response_model=Basket)
async def take_cheaper_line(run_id: str, request: CheaperRequest, guest: Guest) -> Basket:
    run = runs.recall(run_id, owner=guest.owner)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail="цей прогін уже не в пам'яті сервера — збери кошик заново",
        )
    try:
        swapped = take_cheaper(run, article=request.external_product_id, to=request.to)
    except RefillError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return runs.remember(swapped, owner=guest.owner)


@app.post("/api/basket/{run_id}/refill", response_model=Basket)
async def refill_basket(
    run_id: str, request: RefillRequest, guest: Guest, api_key: LlmKey
) -> Basket:
    run = runs.recall(run_id, owner=guest.owner)
    if run is None:
        raise HTTPException(
            status_code=404,
            detail="цей прогін уже не в пам'яті сервера — збери кошик заново",
        )
    meter = Meter()
    llm = _run_llm(request.model, api_key=api_key, meter=meter)
    async with quota.counted(guest, kind="refill", meter=meter):
        try:
            async with SilpoMCP(token=guest.access) as mcp:
                filled = await refill(
                    mcp,
                    llm,
                    run,
                    request,
                    pool=get_pool(),
                    account=guest.account,
                    saved_chains=await _saved_chains_of(guest),
                    receipts=_remembered_receipts(guest),
                )
        except RefillError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except AssemblyError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except MCPCallError as exc:
            raise silpo_silent(exc) from exc
    return runs.remember(filled, owner=guest.owner)


@app.get("/api/exclusions", response_model=list[Exclusion])
async def list_exclusions(guest: Guest) -> list[Exclusion]:
    try:
        async with SilpoMCP(token=guest.access) as mcp:
            outcome = await mcp.call("silpo_get_my_food_restrictions")
    except MCPCallError as exc:
        raise silpo_silent(exc) from exc
    raw = outcome.payload_raw.get("restrictions")
    rows = [row for row in raw if isinstance(row, dict)] if isinstance(raw, list) else []
    return [_chip(rule) for rule in rules_of.profile_rules(rows)]


def _chip(rule: rules_of.Rule) -> Exclusion:
    return Exclusion(id=rule.id, label=rule.label, permanent=rule.permanent, active=rule.active)


def _rule_account(guest: Guest) -> str:
    if not guest.account:
        raise HTTPException(
            status_code=409,
            detail="не знаю, чий це акаунт — перезайди, і правила повернуться",
        )
    return guest.account


async def _own_rules(account: str) -> list[Exclusion]:
    try:
        return [_chip(rule) for rule in await guest_rules.load(get_pool(), account)]
    except HTTPException:
        raise
    except Exception as exc:
        log.warning("rules.unavailable", error=str(exc))
        raise HTTPException(
            status_code=503, detail="сховище правил не відповідає — правки поки в браузері"
        ) from exc


@app.get("/api/rules", response_model=list[Exclusion])
async def list_rules(guest: Guest) -> list[Exclusion]:
    return await _own_rules(_rule_account(guest))


@app.post("/api/rules", response_model=list[Exclusion])
async def add_rule(entry: RuleEntry, guest: Guest) -> list[Exclusion]:
    account = _rule_account(guest)
    label = rules_of.clean(entry.label)
    if not label:
        raise HTTPException(status_code=422, detail="порожнє правило — нема чого читати")
    if rules_of.too_long(entry.label):
        raise HTTPException(
            status_code=422,
            detail=f"правило довше за {rules_of.MAX_LABEL} символів — воно їде в промпт цілим",
        )
    rule = rules_of.own_rule(label, active=entry.active)
    try:
        await guest_rules.save(get_pool(), account, rule)
    except Exception as exc:
        log.warning("rules.save_failed", error=str(exc))
        raise HTTPException(
            status_code=503, detail="сховище правил не відповідає — правило поки в браузері"
        ) from exc
    return await _own_rules(account)


@app.patch("/api/rules/{rule_id}", response_model=list[Exclusion])
async def switch_rule(rule_id: str, change: RuleToggle, guest: Guest) -> list[Exclusion]:
    account = _rule_account(guest)
    try:
        known = await guest_rules.toggle(get_pool(), account, rule_id, active=change.active)
    except Exception as exc:
        log.warning("rules.toggle_failed", error=str(exc))
        raise HTTPException(
            status_code=503, detail="сховище правил не відповідає — правки поки в браузері"
        ) from exc
    if not known:
        raise HTTPException(status_code=404, detail="такого правила в цього акаунта немає")
    return await _own_rules(account)


@app.delete("/api/rules/{rule_id}", response_model=list[Exclusion])
async def drop_rule(rule_id: str, guest: Guest) -> list[Exclusion]:
    account = _rule_account(guest)
    try:
        await guest_rules.remove(get_pool(), account, rule_id)
    except Exception as exc:
        log.warning("rules.delete_failed", error=str(exc))
        raise HTTPException(
            status_code=503, detail="сховище правил не відповідає — правки поки в браузері"
        ) from exc
    return await _own_rules(account)


async def _seen_receipts(mcp: SilpoMCP, guest: Guest, *, fresh: bool, place: Location) -> Receipts:
    if not fresh:
        seen = history.recall(guest.owner)
        if isinstance(seen, Receipts):
            return seen
    read = await read_receipts(mcp, place=place, pool=get_pool(), account=guest.account)
    history.remember(read, owner=guest.owner)
    return read


def _remembered_receipts(guest: Guest) -> Receipts | None:
    seen = history.recall(guest.owner)
    return seen if isinstance(seen, Receipts) else None


def _cold_run(guest: Guest, asked: bool) -> bool:
    return asked


async def _pantry_now(
    guest: Guest, *, fresh: bool = True, ask: bool = True, cold: bool = False
) -> Pantry:
    meter = Meter()
    llm = (
        build_llm(
            model=settings.bedrock_model_id,
            base_url=settings.bedrock_base_url,
            api_key=settings.bedrock_api_key,
            meter=meter,
        )
        if settings.bedrock_api_key
        else None
    )
    llm = await quota.model_gate(guest, llm)
    started = datetime.now(UTC)
    said = await _said_of(guest, PANTRY_SCOPE)
    try:
        async with SilpoMCP(token=guest.access) as mcp:
            place = await place_of(mcp, guest)
            drawn = await pantry_live(
                mcp,
                llm=llm,
                place=place,
                receipts=await _seen_receipts(mcp, guest, fresh=fresh, place=place),
                pool=get_pool(),
                account=guest.account,
                said=said,
                ask=ask,
                use_cache=not cold,
            )
            return drawn.model_copy(update={"fresh": fresh})
    except AssemblyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except MCPCallError as exc:
        raise silpo_silent(exc) from exc
    finally:
        await _count_named(guest, meter, started, kind="pantry")


async def _with_wanted(guest: Guest, pantry: Pantry) -> Pantry:
    if not guest.account or not pantry.items:
        return pantry
    listed = set(await _wanted_of(guest))
    if not listed:
        return pantry
    return pantry.model_copy(
        update={
            "items": [
                row.model_copy(update={"wanted": True}) if manual_key(row.label) in listed else row
                for row in pantry.items
            ]
        }
    )


@app.get("/api/pantry", response_model=Pantry)
async def list_pantry(guest: Guest, cold: bool = False) -> Pantry:
    try:
        return await _drawn_pantry(guest, cold=cold)
    except AssemblyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


async def _drawn_pantry(guest: Guest, *, cold: bool) -> Pantry:
    if _cold_run(guest, cold):
        forget_intents()
        forget_keeps()
        forget_sense()
        return await _with_wanted(guest, await _pantry_now(guest, ask=False, cold=True))
    return await _with_wanted(guest, await _pantry_now(guest, ask=False))


@app.post("/api/pantry/refine", response_model=Pantry)
async def loop_pantry(guest: Guest, body: RefineRequest | None = None) -> Pantry:
    asked = body or RefineRequest()
    meter = Meter()
    llm = (
        build_llm(
            model=settings.bedrock_model_id,
            base_url=settings.bedrock_base_url,
            api_key=settings.bedrock_api_key,
            meter=meter,
        )
        if settings.bedrock_api_key
        else None
    )
    llm = await quota.model_gate(guest, llm)
    started = datetime.now(UTC)
    if body is not None and body.answers:
        answered: dict[str, tuple[int, list[str]]] = {}
        lost = [label for label in body.answers if label not in body.kinds]
        if lost:
            log.warning("pantry.answer_keyless", labels=lost[:6])
        for label, days in list(body.answers.items())[:PROBE_CEILING]:
            under = body.kinds.get(label)
            if not under:
                continue
            await pantry_marks.save_cycle(get_pool(), guest.account, under, days)
            answered[label] = (days, list(body.covers.get(label, []))[:PROBE_COVERS])
        spread, thrown, _tokens = await intent_spread(llm, answered)
        for label, (days, from_kind) in spread.items():
            under = body.kinds.get(label)
            if not under:
                continue
            await pantry_marks.save_cycle(
                get_pool(), guest.account, under, days, said=False, from_kind=from_kind
            )
        if thrown:
            log.info("pantry.spread_cut", cut=thrown[:6])

    said = await _said_of(guest, PANTRY_SCOPE)
    cold = _cold_run(guest, asked.cold)
    packs = models.pantry_batches_for(
        settings.bedrock_model_id, fast=asked.fast, fallback=settings.pantry_batches
    )
    key = asked.progress_key
    on_step = None
    if key is not None:
        progress.open_channel(key, owner=guest.owner)
        on_step = lambda step: progress.push(key, step)  # noqa: E731
    try:
        async with SilpoMCP(token=guest.access) as mcp:
            place = await place_of(mcp, guest)
            read = await _seen_receipts(mcp, guest, fresh=False, place=place)
            drawn = await pantry_live(
                mcp,
                llm=llm,
                place=place,
                receipts=read,
                pool=get_pool(),
                account=guest.account,
                said=said,
                ask=False,
                use_cache=not cold,
            )
            done = await refine_pantry(
                mcp,
                drawn=drawn,
                read=read,
                said=said,
                llm=llm,
                place=place,
                pool=get_pool(),
                account=guest.account,
                on_step=on_step,
                cold=cold,
                continuing=bool(asked.answers),
                batches=packs,
                answered=(body.answers if body is not None else None),
                more=(body.more if body is not None else False),
                seq_from=asked.seen,
            )
    except AssemblyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except MCPCallError as exc:
        raise silpo_silent(exc) from exc
    finally:
        await _count_named(guest, meter, started, kind="pantry_loop")
        if key is not None:
            progress.finish(key)
    return await _with_wanted(
        guest,
        done.pantry.model_copy(
            update={
                "refined": done.note,
                "fresh": False,
                "spent": _cost_of(meter, started),
                "asked": [
                    PantryAsk(
                        label=probe.label,
                        ask=probe.ask,
                        covers=list(probe.covers),
                        kind=probe.kind,
                        cover_kinds=list(probe.cover_kinds),
                        usual=probe.usual,
                    )
                    for probe in done.probes
                ],
            }
        ),
    )


def _cost_of(meter: Meter, started: datetime) -> RunCost:
    cost = core_quota.run_cost(meter.model, meter.calls, meter.input_tokens, meter.output_tokens)
    return RunCost(
        calls=meter.calls,
        duration_ms=quota.elapsed_ms(started),
        cost_usd=cost,
        tokens_in=meter.input_tokens,
        tokens_out=meter.output_tokens,
    )


@app.put("/api/pantry/source", response_model=Pantry)
async def choose_pantry_source(choice: SourceChoice, guest: Guest) -> Pantry:
    try:
        await pantry_marks.save_source(get_pool(), guest.account, PANTRY_SCOPE, choice.mode)
    except Exception as exc:
        log.warning("pantry.source_unwritable", error=str(exc))
        raise HTTPException(
            status_code=503, detail="сховище не відповіло — вибір не зберігся"
        ) from exc
    return await _pantry_now(guest, fresh=False)


@app.post("/api/pantry/generate", response_model=Pantry)
async def generate_pantry(guest: Guest) -> Pantry:
    counted = await _pantry_now(guest, fresh=False)
    rows = {
        manual_key(item.label): item.label
        for item in counted.items
        if item.source == "receipts" and item.named
    }
    unnamed = sum(1 for item in counted.items if item.source == "receipts" and not item.named)
    try:
        added = await pantry_marks.add_items(
            get_pool(), guest.account, rows, scope=PANTRY_SCOPE, origin=PURCHASES
        )
    except Exception as exc:
        log.warning("pantry.generate_failed", error=str(exc))
        raise HTTPException(
            status_code=503, detail="сховище не відповіло — список не склався"
        ) from exc
    log.info("pantry.generated", rows=added, unnamed=unnamed)
    return (await _pantry_now(guest, fresh=False)).model_copy(update={"changed": added})


@app.post("/api/pantry/next-list", response_model=NextList)
async def compose_next_list(guest: Guest) -> NextList:
    if not guest.account:
        raise HTTPException(
            status_code=409,
            detail="не знаю, чий це акаунт — перезайди, і список запам'ятається",
        )
    meter = Meter()
    llm = (
        build_llm(
            model=settings.bedrock_model_id,
            base_url=settings.bedrock_base_url,
            api_key=settings.bedrock_api_key,
            meter=meter,
        )
        if settings.bedrock_api_key
        else None
    )
    llm = await quota.model_gate(guest, llm)
    started = datetime.now(UTC)
    counted = await _pantry_now(guest)
    picks = choose_next(
        [
            NextRow(
                kind=manual_key(item.label),
                label=item.label,
                running_out=item.running_out,
                days_left=item.days_left,
                promo=item.promo is not None,
                manual=item.source == "manual",
            )
            for item in counted.items
        ],
        gap_days=counted.trip_gap,
        limit=counted.list_limit,
    )
    composed = await compose_list(llm, picks)
    await _count_named(guest, meter, started, kind=NEXT_LIST_RUN)
    try:
        stored = await wanted_store.load(get_pool(), guest.account)
        before = {kind: row.label for kind, row in stored.items() if row.origin == AGENT}
        fresh = {
            kind: WantedItem(label=label, why=said)
            for kind, label, said in composed.rows
            if kind not in stored
        }
        gone = [kind for kind in before if kind not in {row[0] for row in composed.rows}]
        await wanted_store.compose(get_pool(), guest.account, fresh)
        await wanted_store.drop_agent(get_pool(), guest.account, gone)
    except Exception as exc:
        log.warning("wanted.compose_failed", error=str(exc))
        raise HTTPException(
            status_code=503, detail="сховище не відповіло — список не склався"
        ) from exc
    said_changes = next_changes(before, {row[0]: row[1] for row in composed.rows})
    log.info("wanted.composed", rows=len(composed.rows), added=len(fresh), gone=len(gone))
    return NextList(
        rows=await _wanted_now(guest),
        changes=list(said_changes),
        note=composed.note,
    )


@app.delete("/api/pantry/items", response_model=Pantry)
async def wipe_pantry(guest: Guest) -> Pantry:
    try:
        wiped = await pantry_marks.wipe_items(get_pool(), guest.account, scope=PANTRY_SCOPE)
    except Exception as exc:
        log.warning("pantry.wipe_failed", error=str(exc))
        raise HTTPException(
            status_code=503, detail="сховище не відповіло — список не стерся"
        ) from exc
    log.info("pantry.wiped", rows=wiped)
    return (await _pantry_now(guest, fresh=False)).model_copy(update={"changed": wiped})


async def _count_named(guest: Guest, meter: Meter, started: datetime, *, kind: str) -> None:
    if not meter.calls:
        return
    await quota.record(
        guest,
        kind=kind,
        meter=meter,
        duration_ms=quota.elapsed_ms(started),
        started_at=started,
    )


@app.post("/api/pantry/manual", response_model=PantryItem)
async def resolve_manual_item(entry: PantryEntry, guest: Guest) -> PantryItem:
    label = entry.label.strip()
    if not label:
        raise HTTPException(status_code=422, detail="порожня назва — нема чого шукати")
    if not guest.account:
        raise HTTPException(
            status_code=409,
            detail="не знаю, чий це акаунт — перезайди, і комора запам'ятає твій список",
        )
    item = manual_item(label, [])

    try:
        await pantry_marks.add_item(
            get_pool(), guest.account, manual_key(label), label, scope=PANTRY_SCOPE
        )
    except Exception as exc:
        log.warning("pantry.manual_unwritable", error=str(exc))
        raise HTTPException(
            status_code=503,
            detail="сховище не відповіло — рядок покажу, але після оновлення його не буде",
        ) from exc
    return item


@app.delete("/api/pantry/manual/{item_id}", status_code=204)
async def forget_manual_item(item_id: str, guest: Guest) -> Response:
    if not is_manual(item_id):
        raise HTTPException(
            status_code=422,
            detail="прибрати можна лише те, що ти додав руками — решту комора рахує з чеків",
        )
    if not guest.account:
        raise HTTPException(status_code=409, detail="не знаю, чий це акаунт")
    try:
        stored = await pantry_marks.load_items(get_pool(), guest.account, scope=PANTRY_SCOPE)
        kind = next((key for key in stored if manual_id(key) == item_id), None)
        if kind is not None:
            await pantry_marks.drop_item(get_pool(), guest.account, kind, scope=PANTRY_SCOPE)
    except HTTPException:
        raise
    except Exception as exc:
        log.warning("pantry.manual_undeletable", error=str(exc))
        raise HTTPException(
            status_code=503, detail="сховище не відповіло — рядок лишився на місці"
        ) from exc
    return Response(status_code=204)


async def _marks_of(guest: Guest) -> dict[str, datetime]:
    try:
        return await pantry_marks.load(get_pool(), guest.account)
    except Exception as exc:
        log.warning("pantry.marks_unavailable", error=str(exc))
        return {}


async def _cycles_of(guest: Guest) -> dict[str, int]:
    try:
        return await pantry_marks.load_cycles(get_pool(), guest.account)
    except Exception as exc:
        log.warning("pantry.cycles_unavailable", error=str(exc))
        return {}


async def _cycle_sources_of(guest: Guest) -> dict[str, str]:
    try:
        return await pantry_marks.load_cycle_sources(get_pool(), guest.account)
    except Exception as exc:
        log.warning("pantry.cycle_sources_unavailable", error=str(exc))
        return {}


async def _source_of(guest: Guest, scope: str) -> str:
    try:
        return await pantry_marks.load_source(get_pool(), guest.account, scope)
    except Exception as exc:
        log.warning("pantry.source_unavailable", error=str(exc))
        return SOURCE_RECEIPTS


async def _hidden_of(guest: Guest) -> list[str]:
    try:
        return await pantry_marks.load_hidden(get_pool(), guest.account)
    except Exception as exc:
        log.warning("pantry.hidden_unavailable", error=str(exc))
        return []


async def _apart_of(guest: Guest, scope: str) -> list[str]:
    try:
        return await pantry_marks.load_splits(get_pool(), guest.account, scope=scope)
    except Exception as exc:
        log.warning("pantry.splits_unavailable", error=str(exc))
        return []


async def _drinks_of(guest: Guest) -> dict[str, DrinkKind]:
    try:
        return await pantry_marks.load_drinks(get_pool(), guest.account)
    except Exception as exc:
        log.warning("bar.drinks_unavailable", error=str(exc))
        return {}


async def _manual_of(
    guest: Guest, *, scope: str = PANTRY_SCOPE, origin: str | None = None
) -> dict[str, str]:
    try:
        return await pantry_marks.load_items(get_pool(), guest.account, scope=scope, origin=origin)
    except Exception as exc:
        log.warning("pantry.manual_unavailable", error=str(exc), scope=scope)
        return {}


async def _said_of(guest: Guest, scope: str) -> Said:
    mode = await _source_of(guest, scope)
    listed = await _manual_of(guest, scope=scope, origin=origin_of_list(mode))
    return Said(
        scope=scope,
        source=mode,
        marks=await _marks_of(guest),
        cycles=await _cycles_of(guest),
        cycle_sources=await _cycle_sources_of(guest),
        hidden=await _hidden_of(guest),
        drinks=await _drinks_of(guest),
        apart=await _apart_of(guest, scope),
        listed=listed,
        written=listed if mode != SOURCE_MANUAL else await _manual_of(guest, scope=scope),
    )


@app.patch("/api/pantry", response_model=Pantry)
async def adjust_pantry(adjustment: PantryAdjustment, guest: Guest) -> Pantry:
    if not guest.account:
        raise HTTPException(
            status_code=409,
            detail="не знаю, чий це акаунт — перезайди, і комора запам'ятає твої слова",
        )
    meter = Meter()
    llm = (
        build_llm(
            model=settings.bedrock_model_id,
            base_url=settings.bedrock_base_url,
            api_key=settings.bedrock_api_key,
            meter=meter,
        )
        if settings.bedrock_api_key
        else None
    )
    llm = await quota.model_gate(guest, llm)
    now = datetime.now(UTC)
    try:
        async with SilpoMCP(token=guest.access) as mcp:
            where = await place_of(mcp, guest)
            paper = await _seen_receipts(mcp, guest, fresh=False, place=where)
            words = await _said_of(guest, PANTRY_SCOPE)
            marks = words.marks
            cycles = words.cycles
            if adjustment.action in ("split", "unsplit"):
                intent = " ".join(adjustment.group.split())
                if not intent:
                    raise HTTPException(
                        status_code=422,
                        detail="скажи, який саме намір розділити",
                    )
                try:
                    if adjustment.action == "split":
                        await pantry_marks.split(
                            get_pool(), guest.account, intent, scope=PANTRY_SCOPE
                        )
                    else:
                        await pantry_marks.unsplit(
                            get_pool(), guest.account, intent, scope=PANTRY_SCOPE
                        )
                except Exception as exc:
                    log.warning("pantry.split_unwritable", error=str(exc))
                    raise HTTPException(
                        status_code=503,
                        detail="не вдалось запам'ятати — скажи ще раз за мить",
                    ) from exc
                words = words.with_apart(intent, apart=adjustment.action == "split")
                stamped = {}
            elif adjustment.action in ("hide", "unhide"):
                kind = await name_kind(
                    mcp,
                    adjustment,
                    place=where,
                    marks=marks,
                    cycles=cycles,
                    now=now,
                    receipts=paper,
                )
                try:
                    if adjustment.action == "hide":
                        await pantry_marks.hide(get_pool(), guest.account, kind)
                    else:
                        await pantry_marks.unhide(get_pool(), guest.account, kind)
                except Exception as exc:
                    log.warning("pantry.hidden_unwritable", error=str(exc))
                    raise HTTPException(
                        status_code=503,
                        detail="не вдалось запам'ятати — скажи ще раз за мить",
                    ) from exc
                words = words.with_hidden(kind, away=adjustment.action == "hide")
                stamped = {}
            elif adjustment.action in ("mandate", "forget_mandate"):
                if adjustment.action == "mandate":
                    kind, chain = await name_mandate(
                        mcp,
                        adjustment,
                        place=where,
                        marks=marks,
                        cycles=cycles,
                        now=now,
                        receipts=paper,
                    )
                else:
                    kind, chain = (
                        await name_kind(
                            mcp,
                            adjustment,
                            place=where,
                            marks=marks,
                            cycles=cycles,
                            now=now,
                            receipts=paper,
                        ),
                        None,
                    )
                try:
                    if chain is None:
                        await saved_swaps.drop(get_pool(), guest.account, kind)
                    else:
                        await saved_swaps.save(get_pool(), guest.account, {kind: chain})
                except Exception as exc:
                    log.warning("pantry.mandate_unwritable", error=str(exc))
                    raise HTTPException(
                        status_code=503,
                        detail="не вдалось запам'ятати — скажи ще раз за мить",
                    ) from exc
                stamped = {}
            elif adjustment.action in ("cycle", "forget_cycle"):
                kind, days = await name_cycle(
                    mcp,
                    adjustment,
                    place=where,
                    marks=marks,
                    cycles=cycles,
                    now=now,
                    receipts=paper,
                )
                try:
                    if days is None:
                        await pantry_marks.drop_cycle(get_pool(), guest.account, kind)
                        cycles = {k: v for k, v in cycles.items() if k != kind}
                    else:
                        await pantry_marks.save_cycle(get_pool(), guest.account, kind, days)
                        cycles = {**cycles, kind: days}
                except Exception as exc:
                    log.warning("pantry.cycle_unwritable", error=str(exc))
                    raise HTTPException(
                        status_code=503,
                        detail="не вдалось запам'ятати — скажи ще раз за мить",
                    ) from exc
                stamped = {}
            else:
                stamped = await mark_pantry(
                    mcp,
                    adjustment,
                    place=where,
                    marks=marks,
                    cycles=cycles,
                    now=now,
                    receipts=paper,
                )
                await pantry_marks.save(get_pool(), guest.account, stamped)
            return await pantry_live(
                mcp,
                llm=llm,
                place=where,
                pool=get_pool(),
                account=guest.account,
                said=words.with_marks(stamped).with_cycles(cycles),
                receipts=paper,
                ask=False,
            )
    except AssemblyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except MCPCallError as exc:
        raise silpo_silent(exc) from exc
    finally:
        await _count_named(guest, meter, now, kind="pantry")


@app.get("/api/cart", response_model=CartState)
async def read_cart_state(guest: Guest) -> CartState:
    try:
        async with SilpoMCP(token=guest.access) as mcp:
            snapshot = await read_cart(mcp)
    except AssemblyError:
        return CartState(rows=0, total=Decimal(0))
    except MCPCallError as exc:
        raise silpo_silent(exc) from exc

    return state_of(snapshot)


@app.get("/api/week-spend", response_model=WeekSpend)
async def read_week_spend(guest: Guest) -> WeekSpend:
    try:
        async with SilpoMCP(token=guest.access) as mcp:
            return await week_spend(mcp, place=await place_of(mcp, guest))
    except WeekSpendError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except MCPCallError as exc:
        raise silpo_silent(exc) from exc


@app.get("/api/delivery-options", response_model=list[DeliveryOption])
async def list_delivery_options(guest: Guest) -> list[DeliveryOption]:
    try:
        async with SilpoMCP(token=guest.access) as mcp:
            return await delivery_options_live(mcp, place=await place_of(mcp, guest))
    except MCPCallError as exc:
        raise silpo_silent(exc) from exc


async def _bar_now(guest: Guest, *, fresh: bool = True) -> Bar:
    meter = Meter()
    llm = (
        build_llm(
            model=settings.bedrock_model_id,
            base_url=settings.bedrock_base_url,
            api_key=settings.bedrock_api_key,
            meter=meter,
        )
        if settings.bedrock_api_key
        else None
    )
    llm = await quota.model_gate(guest, llm)
    started = datetime.now(UTC)
    said = await _said_of(guest, BAR_SCOPE)
    try:
        async with SilpoMCP(token=guest.access) as mcp:
            place = await place_of(mcp, guest)
            return await bar_live(
                mcp,
                llm=llm,
                place=place,
                receipts=await _seen_receipts(mcp, guest, fresh=fresh, place=place),
                pool=get_pool(),
                account=guest.account,
                said=said,
            )
    except AssemblyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except MCPCallError as exc:
        raise silpo_silent(exc) from exc
    finally:
        await _count_named(guest, meter, started, kind="bar")


@app.get("/api/bar", response_model=Bar)
async def list_bar(guest: Guest) -> Bar:
    return await _bar_now(guest)


@app.put("/api/bar/source", response_model=Bar)
async def choose_bar_source(choice: SourceChoice, guest: Guest) -> Bar:
    try:
        await pantry_marks.save_source(get_pool(), guest.account, BAR_SCOPE, choice.mode)
    except Exception as exc:
        log.warning("bar.source_unwritable", error=str(exc))
        raise HTTPException(
            status_code=503, detail="сховище не відповіло — вибір не зберігся"
        ) from exc
    return await _bar_now(guest, fresh=False)


@app.post("/api/bar/generate", response_model=Bar)
async def generate_bar(guest: Guest) -> Bar:
    counted = await _bar_now(guest, fresh=False)
    rows = {
        manual_key(item.label): item.label
        for item in counted.items
        if item.source == SOURCE_RECEIPTS
    }
    try:
        added = await pantry_marks.add_items(
            get_pool(), guest.account, rows, scope=BAR_SCOPE, origin=PURCHASES
        )
    except Exception as exc:
        log.warning("bar.generate_failed", error=str(exc))
        raise HTTPException(
            status_code=503, detail="сховище не відповіло — список не склався"
        ) from exc
    log.info("bar.generated", rows=added)
    return (await _bar_now(guest, fresh=False)).model_copy(update={"changed": added})


@app.delete("/api/bar/items", response_model=Bar)
async def wipe_bar(guest: Guest) -> Bar:
    try:
        wiped = await pantry_marks.wipe_items(get_pool(), guest.account, scope=BAR_SCOPE)
    except Exception as exc:
        log.warning("bar.wipe_failed", error=str(exc))
        raise HTTPException(
            status_code=503, detail="сховище не відповіло — список не стерся"
        ) from exc
    log.info("bar.wiped", rows=wiped)
    return (await _bar_now(guest, fresh=False)).model_copy(update={"changed": wiped})


@app.put("/api/bar/group", response_model=Bar)
async def choose_bar_group(choice: BarGroupChoice, guest: Guest) -> Bar:
    label = choice.label.strip()
    if not label:
        raise HTTPException(status_code=422, detail="порожня назва — нема про що казати")
    if not guest.account:
        raise HTTPException(
            status_code=409,
            detail="не знаю, чий це акаунт — перезайди, і бар запам'ятає твоє слово",
        )
    try:
        if choice.kind is None:
            await pantry_marks.drop_drink(get_pool(), guest.account, manual_key(label))
        else:
            await pantry_marks.save_drink(
                get_pool(), guest.account, manual_key(label), str(choice.kind)
            )
    except Exception as exc:
        log.warning("bar.group_unwritable", error=str(exc))
        raise HTTPException(
            status_code=503, detail="сховище не відповіло — слово не зберіглось"
        ) from exc
    return await _bar_now(guest, fresh=False)


@app.post("/api/bar/manual", response_model=Bar)
async def add_bar_item(entry: PantryEntry, guest: Guest) -> Bar:
    label = entry.label.strip()
    if not label:
        raise HTTPException(status_code=422, detail="порожня назва — нема чого додавати")
    if not guest.account:
        raise HTTPException(
            status_code=409,
            detail="не знаю, чий це акаунт — перезайди, і бар запам'ятає твій список",
        )
    try:
        await pantry_marks.add_item(
            get_pool(), guest.account, manual_key(label), label, scope=BAR_SCOPE
        )
    except Exception as exc:
        log.warning("bar.manual_unwritable", error=str(exc))
        raise HTTPException(
            status_code=503, detail="сховище не відповіло — рядок не зберігся"
        ) from exc
    return await _bar_now(guest, fresh=False)


@app.delete("/api/bar/manual/{item_id}", response_model=Bar)
async def drop_bar_item(item_id: str, guest: Guest) -> Bar:
    if not is_manual(item_id):
        raise HTTPException(
            status_code=404,
            detail="цей рядок порахований з чеків — прибрати його нема чого",
        )
    try:
        stored = await pantry_marks.load_items(get_pool(), guest.account, scope=BAR_SCOPE)
        for kind in stored:
            if manual_id(kind) == item_id:
                await pantry_marks.drop_item(get_pool(), guest.account, kind, scope=BAR_SCOPE)
                break
    except Exception as exc:
        log.warning("bar.manual_undeletable", error=str(exc))
        raise HTTPException(
            status_code=503, detail="сховище не відповіло — рядок не прибрався"
        ) from exc
    return await _bar_now(guest, fresh=False)


@dataclass(frozen=True, slots=True)
class Burned:

    labels: list[str]
    stocked: list[str]


async def _burn_wanted(guest: Guest, run: Assembled | CartRun) -> Burned:
    plan = run.assembled if isinstance(run, CartRun) else run
    going, _ = writable(plan.lines)
    if not going:
        return Burned([], [])
    try:
        stored = await wanted_store.load(get_pool(), guest.account)
        burned = {
            kind: row
            for kind, row in stored.items()
            if any(same_kind(row.label, line.intent) for line in going)
        }
        if not burned:
            return Burned([], [])
        home = {kind: row.label for kind, row in burned.items() if row.at_home}
        if home:
            await pantry_marks.add_items(
                get_pool(), guest.account, home, scope=PANTRY_SCOPE, origin=GUEST
            )
            await pantry_marks.save(
                get_pool(),
                guest.account,
                dict.fromkeys(home, bought_now(datetime.now(UTC))),
            )
        await wanted_store.drop(get_pool(), guest.account, burned)
    except Exception as exc:
        log.warning("wanted.burn_failed", error=str(exc))
        return Burned([], [])
    return Burned([row.label for row in burned.values()], list(home.values()))


async def _wanted_of(guest: Guest) -> dict[str, str]:
    try:
        rows = await wanted_store.load(get_pool(), guest.account)
    except Exception as exc:
        log.warning("wanted.unavailable", error=str(exc))
        return {}
    return {kind: row.label for kind, row in rows.items()}


async def _wanted_now(guest: Guest) -> list[WantedRow]:
    try:
        rows = await wanted_store.load(get_pool(), guest.account)
    except Exception as exc:
        log.warning("wanted.unavailable", error=str(exc))
        return []
    return [
        WantedRow(id=manual_id(kind), label=row.label, why=row.why, at_home=row.at_home)
        for kind, row in rows.items()
    ]


@app.get("/api/list", response_model=list[WantedRow])
async def list_wanted(guest: Guest) -> list[WantedRow]:
    return await _wanted_now(guest)


@app.post("/api/list", response_model=list[WantedRow])
async def add_wanted(entry: WantedEntry, guest: Guest) -> list[WantedRow]:
    label = entry.label.strip()
    if not label:
        raise HTTPException(status_code=422, detail="порожній рядок — нема чого додавати")
    if not guest.account:
        raise HTTPException(
            status_code=409,
            detail="не знаю, чий це акаунт — перезайди, і список запам'ятається",
        )
    try:
        await wanted_store.add(
            get_pool(), guest.account, manual_key(label), label, at_home=entry.at_home
        )
    except Exception as exc:
        log.warning("wanted.unwritable", error=str(exc))
        raise HTTPException(
            status_code=503, detail="сховище не відповіло — рядок не зберігся"
        ) from exc
    return await _wanted_now(guest)


@app.delete("/api/list/{item_id}", response_model=list[WantedRow])
async def drop_wanted(item_id: str, guest: Guest) -> list[WantedRow]:
    if not is_manual(item_id):
        raise HTTPException(status_code=404, detail="такого рядка в списку немає")
    try:
        stored = await wanted_store.load(get_pool(), guest.account)
        kind = next((key for key in stored if manual_id(key) == item_id), None)
        if kind is not None:
            await wanted_store.drop(get_pool(), guest.account, [kind])
    except Exception as exc:
        log.warning("wanted.undeletable", error=str(exc))
        raise HTTPException(
            status_code=503, detail="сховище не відповіло — рядок не прибрався"
        ) from exc
    return await _wanted_now(guest)


@app.exception_handler(HTTPException)
async def http_error(_, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def unexpected(_, exc: Exception) -> JSONResponse:
    log.exception("api.unhandled", error=type(exc).__name__)
    return JSONResponse(
        status_code=500,
        content={"detail": "Несподівана помилка на нашому боці — спробуй ще раз."},
    )


@app.exception_handler(TokenRejected)
async def token_rejected(_, exc: TokenRejected) -> JSONResponse:
    log.warning("api.token_rejected", tool=exc.tool)
    response = JSONResponse(
        status_code=401,
        content={"detail": "З'єднання із Сільпо розірвано — підключись знову."},
    )
    forget(response, keep_key=True)
    return response
