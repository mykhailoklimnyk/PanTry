from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, PlainSerializer

from komora.core.bar import DrinkKind
from komora.core.feedback import Changes, Contacts

JsonNumber = Annotated[Decimal, PlainSerializer(float, return_type=float, when_used="json")]


class Schema(BaseModel):

    model_config = ConfigDict(use_attribute_docstrings=True)


class Reason(StrEnum):

    CYCLE = "cycle"
    FREQUENCY = "frequency"
    UNDELIVERED = "undelivered"
    DISH = "dish"
    TOPUP = "topup"
    AT_HOME = "at_home"
    OCCASION = "occasion"
    SUBSTITUTED = "substituted"


class Health(Schema):
    database: bool
    login_ready: bool = Field(serialization_alias="loginReady")
    version: str | None = None


class GuestLink(Schema):

    connected: bool
    expires_at: datetime | None = Field(default=None, serialization_alias="expiresAt")
    reason: str | None = None
    greet: int | None = None
    llm_key: bool = Field(default=False, serialization_alias="llmKey")


class LlmKeyRequest(Schema):

    key: str


class SwapDecision(Schema):

    external_product_id: str = Field(alias="externalProductId")
    policy: Literal["substitute", "skip", "call"] = "substitute"
    chain: list[str] = Field(default_factory=list)


class ClarifyAnswer(Schema):

    intent: str
    slug: str | None = None
    query: str | None = None
    text: str | None = None
    skip: bool = False


class BuildRequest(Schema):

    source: Literal["list", "cart"] = "list"
    delivery: str = "courier"
    mode: Literal["list", "week", "event"] = "list"
    progress_key: str | None = Field(
        default=None, alias="progressKey", min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$"
    )
    occasion_people: int | None = Field(default=None, alias="occasionPeople", ge=1, le=99)
    cold: bool = False
    event_style: Literal["cooking", "ready"] | None = Field(default=None, alias="eventStyle")
    shopping_list: list[str] = Field(default_factory=list, alias="shoppingList")
    list_text: str = Field(default="", alias="listText")
    bar_in_week: bool = Field(default=False, alias="barInWeek")
    budget_said: bool = Field(default=False, alias="budgetSaid")
    budget: JsonNumber | None = None
    keep: list[str] = Field(default_factory=list)
    swaps: list[SwapDecision] = Field(default_factory=list)
    exclusions: list[str] = Field(default_factory=list)
    rules: list[str] = Field(default_factory=list)
    model: str | None = None
    fast: bool | None = None
    auto_swap: bool = Field(default=False, alias="autoSwap")
    auto_swap_percent: int = Field(default=10, alias="autoSwapPercent", ge=5, le=50)
    answers: list[ClarifyAnswer] = Field(default_factory=list)


class ModelOption(Schema):

    id: str
    label: str
    note: str | None = None
    available: bool = True
    active: bool = False
    recommended: bool = False
    needs_key: bool = Field(default=False, serialization_alias="needsKey")
    supports_fast: bool = Field(default=False, serialization_alias="supportsFast")
    fast_by_default: bool = Field(default=False, serialization_alias="fastByDefault")


class CorrectionRequest(Schema):
    external_product_id: str = Field(alias="externalProductId")
    action: Literal["still_have", "ran_out_earlier", "never_again"]


class SwapsRequest(Schema):

    swaps: list[SwapDecision] = Field(default_factory=list)
    remember: bool = False


class SavedSwap(Schema):

    id: str
    label: str
    links: list[str]


class CheaperRequest(Schema):

    external_product_id: str = Field(validation_alias="externalProductId")
    to: str


class PickRequest(Schema):

    intent: str
    external_product_id: str = Field(validation_alias="externalProductId")


class RefillRequest(Schema):

    intents: list[str] = Field(default_factory=list)
    answers: list[ClarifyAnswer] = Field(default_factory=list)
    model: str | None = None
    fast: bool | None = None


class Substitute(Schema):
    external_product_id: str = Field(serialization_alias="externalProductId")
    name: str
    source: str
    price: JsonNumber | None = None
    ratio: str | None = None
    by_weight: bool = Field(default=False, serialization_alias="byWeight")


class SwapOption(Schema):

    external_product_id: str = Field(serialization_alias="externalProductId")
    name: str
    price: JsonNumber
    ratio: str | None = None
    by_weight: bool = Field(default=False, serialization_alias="byWeight")
    stock: JsonNumber | None = None
    available: bool = True
    image_url: str | None = Field(default=None, serialization_alias="imageUrl")
    card_url: str | None = Field(default=None, serialization_alias="cardUrl")
    same_kind: bool | None = Field(default=None, serialization_alias="sameKind")
    kind: str | None = None
    sliced: bool = False


class PriceFork(Schema):

    low: JsonNumber
    high: JsonNumber
    per: str = ""


class Cheaper(Schema):

    external_product_id: str = Field(serialization_alias="externalProductId")
    name: str
    price: JsonNumber
    saving: JsonNumber


class CartLine(Schema):
    external_product_id: str = Field(serialization_alias="externalProductId")
    name: str
    qty: JsonNumber
    unit: str = "шт"
    step: JsonNumber | None = None
    price: JsonNumber
    base_price: JsonNumber | None = Field(default=None, serialization_alias="basePrice")
    sale_note: str | None = Field(default=None, serialization_alias="saleNote")
    weight_kg: JsonNumber | None = Field(default=None, serialization_alias="weightKg")
    image_url: str | None = Field(default=None, serialization_alias="imageUrl")
    card_url: str | None = Field(default=None, serialization_alias="cardUrl")
    reason: Reason
    explanation: str
    explanation_detail: str | None = Field(default=None, serialization_alias="explanationDetail")
    confidence: float
    at_risk: bool = Field(serialization_alias="atRisk")
    needs_approval: bool = Field(default=False, serialization_alias="needsApproval")
    chain: list[Substitute] = Field(default_factory=list)
    mandate: str | None = None
    mandate_ahead: bool = Field(default=False, serialization_alias="mandateAhead")
    decided: bool = False
    swap_fork: PriceFork | None = Field(default=None, serialization_alias="swapFork")
    considered: list[SwapOption] = Field(default_factory=list)
    sliced: bool = False
    slicing_note: str | None = Field(default=None, serialization_alias="slicingNote")
    cheaper: Cheaper | None = None
    considered_total: int = Field(default=0, serialization_alias="consideredTotal")


class TopUp(Schema):

    threshold: JsonNumber
    saving: JsonNumber
    items: list[CartLine]


class TraceOption(Schema):

    id: str
    label: str
    style: Literal["cooking", "ready"] | None = None
    target: JsonNumber | None = None


class TraceQuestion(Schema):

    id: str
    ask: str
    why: str | None = None
    options: list[TraceOption]
    wait_s: int = Field(serialization_alias="waitS")


class ProgressAnswer(Schema):

    question_id: str = Field(alias="questionId", max_length=32)
    option_id: str = Field(alias="optionId", max_length=32)


class AnswerTaken(Schema):

    taken: bool


class TraceStep(Schema):
    id: str
    seq: int
    tool: str
    args: dict[str, Any]
    duration_ms: int | None = Field(default=None, serialization_alias="durationMs")
    calls: int | None = None
    tokens_in: int | None = Field(default=None, serialization_alias="tokensIn")
    tokens_out: int | None = Field(default=None, serialization_alias="tokensOut")
    result_summary: str = Field(serialization_alias="resultSummary")
    decision: str | None = None
    tag: str | None = None
    tag_tone: Literal["good", "warn", "muted"] = Field(
        default="muted", serialization_alias="tagTone"
    )
    external_product_id: str | None = Field(default=None, serialization_alias="externalProductId")
    prompt: str | None = None
    question: TraceQuestion | None = None


class Progress(Schema):

    steps: list[TraceStep]
    done: bool


class RunStats(Schema):

    receipts: int
    orders: int = 0
    cycled: int
    mcp_calls: int = Field(serialization_alias="mcpCalls")
    duration_ms: int = Field(serialization_alias="durationMs")
    cost_usd: JsonNumber = Field(serialization_alias="costUsd")
    tokens_in: int = Field(default=0, serialization_alias="tokensIn")
    tokens_out: int = Field(default=0, serialization_alias="tokensOut")
    tokens_cached: int = Field(default=0, serialization_alias="tokensCached")
    model: str


class Toll(Schema):

    runs: int
    usd: JsonNumber | None = None
    unpriced: int = 0
    tokens_in: int = Field(default=0, serialization_alias="tokensIn")
    tokens_out: int = Field(default=0, serialization_alias="tokensOut")
    guest_usd: JsonNumber | None = Field(default=None, serialization_alias="guestUsd")


class Quota(Schema):

    blocked: bool
    scope: Literal["session", "day", "budget-day", "budget-total"] | None = None
    headline: str
    action: str | None = None
    left: int
    resets_at: datetime | None = Field(default=None, serialization_alias="resetsAt")
    contact: str | None = None
    toll: Toll | None = None


class PlaceOption(Schema):

    id: str | None = None
    label: str
    tag: str | None = None
    latitude: float
    longitude: float
    city: str | None = None
    street: str | None = None
    house: str | None = None
    confirmed: bool = True


class Place(Schema):

    address: str | None = None
    tag: str | None = None
    branch: str | None = None
    branch_id: str | None = Field(default=None, serialization_alias="branchId")
    source: Literal["address", "cart", "config", "none"]
    note: str
    delivery_types: list[str] = Field(default_factory=list, serialization_alias="deliveryTypes")
    saved: list[PlaceOption] = Field(default_factory=list)


class PlaceQuery(Schema):

    text: str


class PlaceChoice(Schema):

    label: str
    latitude: float
    longitude: float
    id: str | None = None
    city: str | None = None
    street: str | None = None
    house: str | None = None


class DeliveryOption(Schema):

    id: str
    label: str
    note: str
    cost: JsonNumber
    min_order: JsonNumber | None = Field(default=None, serialization_alias="minOrder")
    threshold: JsonNumber | None = None
    max_weight_kg: JsonNumber | None = Field(default=None, serialization_alias="maxWeightKg")
    service_fee: JsonNumber | None = Field(default=None, serialization_alias="serviceFee")
    available: bool = True
    unavailable_reason: str | None = Field(default=None, serialization_alias="unavailableReason")


class SlotWindow(Schema):
    start: datetime
    end: datetime
    note: str | None = None


class ClarifyOption(Schema):

    title: str
    slug: str = ""
    query: str | None = None
    count: int
    price_from: JsonNumber | None = Field(default=None, serialization_alias="priceFrom")
    by_weight: bool = Field(default=False, serialization_alias="byWeight")


class ClarifyPick(Schema):

    external_product_id: str = Field(serialization_alias="externalProductId")
    name: str
    price: JsonNumber
    ratio: str | None = None
    by_weight: bool = Field(default=False, serialization_alias="byWeight")


class Clarification(Schema):

    intent: str
    question: str
    options: list[ClarifyOption] = Field(default_factory=list)
    picks: list[ClarifyPick] = Field(default_factory=list)


class Trimmed(Schema):

    intent: str
    name: str | None = None
    price: JsonNumber | None = None
    reason: str


class TwinsDropped(Schema):

    name: str
    kept_name: str = Field(serialization_alias="keptName")
    why: str


class Declined(Schema):

    intent: str
    why: str


class Postponed(Schema):

    intent: str
    reason: str
    estimate: JsonNumber | None = None
    refillable: bool = False


class OrderFeedback(Schema):

    changes: Changes | None = None
    contacts: Contacts | None = None


class Basket(Schema):
    run_id: str = Field(serialization_alias="runId")
    lines: list[CartLine]
    total: JsonNumber
    base_total: JsonNumber | None = Field(default=None, serialization_alias="baseTotal")
    delivery_cost: JsonNumber = Field(serialization_alias="deliveryCost")
    total_weight_kg: JsonNumber = Field(serialization_alias="totalWeightKg")
    top_up: TopUp | None = Field(default=None, serialization_alias="topUp")
    blockers: list[str] = Field(default_factory=list)
    slot: SlotWindow | None = None
    checkout_web_link: str | None = Field(default=None, serialization_alias="checkoutWebLink")
    trace: list[TraceStep] = Field(default_factory=list)
    stats: RunStats
    feedback: OrderFeedback = Field(default_factory=OrderFeedback)
    unresolved: list[str] = Field(default_factory=list)
    declined: list[Declined] = Field(default_factory=list)
    questions: list[Clarification] = Field(default_factory=list)
    postponed: list[Postponed] = Field(default_factory=list)
    budget: JsonNumber | None = None
    text_ignored: list[str] = Field(default_factory=list, serialization_alias="textIgnored")
    shelf_note: str | None = Field(default=None, serialization_alias="shelfNote")
    plan_note: str | None = Field(default=None, serialization_alias="planNote")
    agent_target: AgentTarget | None = Field(default=None, serialization_alias="agentTarget")
    trimmed: list[Trimmed] = Field(default_factory=list)
    fill_cut: list[Trimmed] = Field(default_factory=list, serialization_alias="fillCut")
    twins_dropped: list[TwinsDropped] = Field(
        default_factory=list, serialization_alias="twinsDropped"
    )
    fill_note: str | None = Field(default=None, serialization_alias="fillNote")
    cycles_note: str | None = Field(default=None, serialization_alias="cyclesNote")
    not_collected: list[str] = Field(default_factory=list, serialization_alias="notCollected")


class CheckoutSkip(Schema):

    name: str
    reason: str


class CartTotals(Schema):

    products: JsonNumber
    discount: JsonNumber
    delivery: JsonNumber
    service_fee: JsonNumber | None = Field(default=None, serialization_alias="serviceFee")
    to_pay: JsonNumber = Field(serialization_alias="toPay")
    estimate: JsonNumber | None = None


class CarryOverState(StrEnum):

    ASKING = "asking"
    KEPT = "kept"
    REMOVED = "removed"


class CarryOverLine(Schema):

    name: str
    qty: JsonNumber
    total: JsonNumber


class CartCarryOver(Schema):

    state: CarryOverState
    total: JsonNumber
    lines: list[CarryOverLine]


class CheckoutResult(Schema):

    written: int
    skipped: list[CheckoutSkip] = Field(default_factory=list)
    blockers: list[str] = Field(default_factory=list)
    blocker_notes: list[str] = Field(default_factory=list, serialization_alias="blockerNotes")
    warnings: list[str] = Field(default_factory=list)
    retry_helps: bool = Field(default=False, serialization_alias="retryHelps")
    mandate_lost: list[str] = Field(default_factory=list, serialization_alias="mandateLost")
    unmandated: list[str] = Field(default_factory=list)
    stock_cut: list[str] = Field(default_factory=list, serialization_alias="stockCut")
    basket: Basket | None = None
    checkout_web_link: str | None = Field(default=None, serialization_alias="checkoutWebLink")
    cart_web_link: str | None = Field(default=None, serialization_alias="cartWebLink")
    totals: CartTotals | None = None
    bonus_available: JsonNumber | None = Field(default=None, serialization_alias="bonusAvailable")
    wanted_burned: list[str] = Field(default_factory=list, serialization_alias="wantedBurned")
    wanted_stocked: list[str] = Field(default_factory=list, serialization_alias="wantedStocked")
    promo_gone: list[str] = Field(default_factory=list, serialization_alias="promoGone")
    carry_over: CartCarryOver | None = Field(default=None, serialization_alias="carryOver")
    trace: list[TraceStep] = Field(default_factory=list)
    summary: str


class CheckoutExtra(Schema):

    external_product_id: str = Field(alias="externalProductId")
    qty: JsonNumber
    name: str = ""


class CheckoutRequest(Schema):

    existing: CarryOverState = CarryOverState.ASKING
    lines: dict[str, JsonNumber] | None = None
    extras: list[CheckoutExtra] | None = None
    model: str | None = None
    fast: bool | None = None


class CartState(Schema):

    rows: int
    total: JsonNumber
    slot: SlotWindow | None = None


class WeekSpend(Schema):

    spent: JsonNumber
    receipts: int
    since: datetime


class Exclusion(Schema):

    id: str
    label: str
    permanent: bool
    active: bool


class RuleEntry(Schema):

    label: str
    active: bool = True


class RuleToggle(Schema):

    active: bool


class PantryPart(Schema):

    label: str
    unit: str = ""
    receipts: int = 0
    days_since: int | None = Field(default=None, serialization_alias="daysSince")
    fresh: bool = False


class PantryLink(Schema):

    article: str
    name: str


class PantryMandate(Schema):

    links: list[PantryLink]
    agreed: bool


class PantryItem(Schema):

    id: str
    label: str
    qty: JsonNumber | None = None
    usual_qty: JsonNumber | None = Field(default=None, serialization_alias="usualQty")
    unit: str = "шт"
    named: bool = False
    left_ratio: float | None = Field(default=None, serialization_alias="leftRatio")
    days_left: int | None = Field(default=None, serialization_alias="daysLeft")
    cycle_days: int | None = Field(default=None, serialization_alias="cycleDays")
    sanity: str | None = None
    keeps: str | None = None
    ask: bool = False

    cycle_said: bool = Field(default=False, serialization_alias="cycleSaid")
    state: str
    running_out: bool = Field(default=False, serialization_alias="runningOut")
    promo: str | None = None
    arrived: str | None = None
    usual: ProductPick | None = None
    trust: str = ""
    source: Literal["receipts", "manual"] = "receipts"
    aisle: str | None = None
    group: str | None = None
    image_url: str | None = Field(default=None, serialization_alias="imageUrl")
    wanted: bool = False
    written_as: list[str] = Field(default_factory=list, serialization_alias="writtenAs")
    mandate: PantryMandate | None = None
    parts: list[PantryPart] = Field(default_factory=list)


class PantryAisle(Schema):

    title: str
    rows: int


class AgentTarget(Schema):

    named: JsonNumber
    proposed: JsonNumber
    target: JsonNumber
    why: str
    refused: str | None = None


class SpendTarget(Schema):

    target: JsonNumber
    orders: int = 0
    presets: list[JsonNumber] = Field(default_factory=list)
    note: str


class PantryAsk(Schema):

    label: str
    ask: str
    covers: list[str] = Field(default_factory=list)
    kind: str = ""
    cover_kinds: list[str] = Field(default_factory=list, serialization_alias="coverKinds")
    usual: str = ""


class Pantry(Schema):

    items: list[PantryItem]
    fresh: bool = True
    refined: str | None = None
    asked: list[PantryAsk] = Field(default_factory=list)
    spent: RunCost | None = None
    changed: int | None = None
    receipts: int
    orders: int = 0
    kinds: int
    tracked_from: int = Field(serialization_alias="trackedFrom")
    hidden: list[str] = Field(default_factory=list)
    at_bar: list[str] = Field(default_factory=list, serialization_alias="atBar")
    apart: list[str] = Field(default_factory=list)
    outside: list[str] = Field(default_factory=list)
    spend: SpendTarget | None = None
    trace: list[TraceStep] = Field(default_factory=list)
    aisles: list[PantryAisle] = Field(default_factory=list)
    source: str = "receipts"
    unlisted: int = 0
    trip_gap: int = Field(default=0, serialization_alias="tripGap")
    list_limit: int = Field(default=0, serialization_alias="listLimit")
    target_pool: int = Field(default=0, serialization_alias="targetPool")
    target_estimate: JsonNumber | None = Field(default=None, serialization_alias="targetEstimate")


class ProductPick(Schema):

    external_product_id: str = Field(serialization_alias="externalProductId")
    name: str
    share: str
    price: JsonNumber
    unit: str = "шт"
    pack: str = ""


class BarItem(Schema):

    id: str
    label: str
    kind: DrinkKind | None = None
    kind_said: bool = Field(default=False, serialization_alias="kindSaid")
    times: int = 0
    days_since: int | None = Field(default=None, serialization_alias="daysSince")
    source: Literal["receipts", "manual"] = "receipts"
    usual: ProductPick | None = None
    price_from: JsonNumber | None = Field(default=None, serialization_alias="priceFrom")
    price_to: JsonNumber | None = Field(default=None, serialization_alias="priceTo")
    fork_note: str = Field(default="", serialization_alias="forkNote")


class Bar(Schema):

    changed: int | None = None
    items: list[BarItem]
    receipts: int
    orders: int = 0
    kinds: int
    named: int
    tracked_from: int = Field(serialization_alias="trackedFrom")
    source: str = "receipts"
    unlisted: int = 0
    dropped: int = 0


class PantryAdjustment(Schema):

    id: str
    action: Literal[
        "bought",
        "qty",
        "cycle",
        "forget_cycle",
        "hide",
        "unhide",
        "split",
        "unsplit",
        "mandate",
        "forget_mandate",
    ] = "qty"
    qty: JsonNumber = Decimal(0)
    group: str = ""
    days: int = 0

    chain: list[str] = Field(default_factory=list)


class RunCost(Schema):

    calls: int
    duration_ms: int = Field(serialization_alias="durationMs")
    cost_usd: JsonNumber | None = Field(default=None, serialization_alias="costUsd")
    tokens_in: int = Field(default=0, serialization_alias="tokensIn")
    tokens_out: int = Field(default=0, serialization_alias="tokensOut")


class RefineRequest(Schema):

    covers: dict[str, list[str]] = Field(default_factory=dict)

    seen: int = 0

    kinds: dict[str, str] = Field(default_factory=dict)

    more: bool = False

    answers: dict[str, int] = Field(default_factory=dict)

    progress_key: str | None = Field(
        default=None, alias="progressKey", min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$"
    )
    cold: bool = False
    fast: bool | None = None


class SourceChoice(Schema):

    mode: Literal["receipts", "manual"]


class BarGroupChoice(Schema):

    label: str
    kind: DrinkKind | None = None


class WantedRow(Schema):

    id: str
    label: str
    why: str | None = None
    at_home: bool = Field(default=True, serialization_alias="atHome")


class NextList(Schema):

    rows: list[WantedRow]
    changes: list[str] = Field(default_factory=list)
    note: str


class WantedEntry(Schema):

    label: str
    at_home: bool = Field(default=True, alias="atHome")


class PantryEntry(Schema):

    label: str
