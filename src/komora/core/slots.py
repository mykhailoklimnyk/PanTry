from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import StrEnum

from komora.core.delivery import DeliveryTerms
from komora.core.quota import KYIV
from komora.core.weight import over_limit


class Restricted(StrEnum):

    ALCOHOL = "alcohol"
    TOBACCO = "tobacco"
    COOKED_FOOD = "cooked_food"
    OWN_COOKING = "own_cooking"


@dataclass(frozen=True, slots=True)
class SlotConstraints:
    alcohol: bool = False
    tobacco: bool = False
    cooked_food: bool = False
    own_cooking: bool = False

    def limited(self) -> frozenset[Restricted]:
        limits = set()
        if self.alcohol:
            limits.add(Restricted.ALCOHOL)
        if self.tobacco:
            limits.add(Restricted.TOBACCO)
        if self.cooked_food:
            limits.add(Restricted.COOKED_FOOD)
        if self.own_cooking:
            limits.add(Restricted.OWN_COOKING)
        return frozenset(limits)


@dataclass(frozen=True, slots=True)
class Slot:
    start: datetime
    end: datetime
    available: bool
    delivery_type: str
    terms: DeliveryTerms
    constraints: SlotConstraints = field(default_factory=SlotConstraints)


REASON_NOT_AVAILABLE = "timeslot.not_available"
REASON_ORDER_MIN = "order.cost.min"
REASON_WEIGHT_MAX = "order.weight.max"


def restriction_reason(category: Restricted) -> str:
    return f"timeslot.limited.{category.value}"


def slot_blockers(
    slot: Slot,
    *,
    cart_categories: Iterable[Restricted] = (),
    order_total: Decimal | None = None,
    total_weight_kg: Decimal | None = None,
) -> tuple[str, ...]:
    reasons: list[str] = []

    if not slot.available:
        reasons.append(REASON_NOT_AVAILABLE)

    limited = slot.constraints.limited()
    for category in sorted(set(cart_categories), key=lambda c: c.value):
        if category in limited:
            reasons.append(restriction_reason(category))

    if order_total is not None and order_total < slot.terms.min_order_cost:
        reasons.append(REASON_ORDER_MIN)

    if total_weight_kg is not None and over_limit(total_weight_kg, slot.terms.max_weight_kg) > 0:
        reasons.append(REASON_WEIGHT_MAX)

    return tuple(reasons)


def is_usable(
    slot: Slot,
    *,
    cart_categories: Iterable[Restricted] = (),
    order_total: Decimal | None = None,
    total_weight_kg: Decimal | None = None,
) -> bool:
    return not slot_blockers(
        slot,
        cart_categories=cart_categories,
        order_total=order_total,
        total_weight_kg=total_weight_kg,
    )


def first_usable(
    slots: Iterable[Slot],
    *,
    cart_categories: Iterable[Restricted] = (),
    order_total: Decimal | None = None,
    total_weight_kg: Decimal | None = None,
) -> Slot | None:
    categories = tuple(cart_categories)
    for slot in sorted(slots, key=lambda s: s.start):
        if is_usable(
            slot,
            cart_categories=categories,
            order_total=order_total,
            total_weight_kg=total_weight_kg,
        ):
            return slot
    return None


class Basis(StrEnum):

    CART = "cart"
    FIRST = "first"
    ONLY = "only"
    HABIT = "habit"


@dataclass(frozen=True, slots=True)
class Choice:
    index: int
    basis: Basis
    free: int
    offered: int
    hour: int | None = None
    hour_orders: int = 0
    orders: int = 0
    over_cart: bool = False


MIN_ORDERS_FOR_HABIT = 3


def choose(
    windows: Sequence[tuple[str | None, bool]],
    *,
    wanted: str | None,
    habit: Mapping[int, int] | None = None,
    now: datetime | None = None,
) -> Choice | None:
    free = [i for i, (_, available) in enumerate(windows) if available]
    if not free:
        return None
    kept = next((i for i in free if windows[i][0] == wanted), None) if wanted is not None else None
    liked = _by_habit(windows, free, habit or {}, now)
    if liked is not None and liked[0] != kept and (kept is not None or liked[0] != free[0]):
        index, hour, seen = liked
        return Choice(
            index=index,
            basis=Basis.HABIT,
            free=len(free),
            offered=len(windows),
            hour=hour,
            hour_orders=seen,
            orders=sum((habit or {}).values()),
            over_cart=kept is not None,
        )
    if kept is not None:
        return Choice(index=kept, basis=Basis.CART, free=len(free), offered=len(windows))
    if len(free) == 1:
        return Choice(index=free[0], basis=Basis.ONLY, free=len(free), offered=len(windows))
    return Choice(index=free[0], basis=Basis.FIRST, free=len(free), offered=len(windows))


def _by_habit(
    windows: Sequence[tuple[str | None, bool]],
    free: Sequence[int],
    habit: Mapping[int, int],
    now: datetime | None,
) -> tuple[int, int, int] | None:
    if sum(habit.values()) < MIN_ORDERS_FOR_HABIT or now is None:
        return None
    best: tuple[int, int, int] | None = None
    for index in free:
        moment = moment_of(windows[index][0], now=now)
        if moment is None:
            continue
        hour = moment.astimezone(KYIV).hour
        seen = habit.get(hour, 0)
        if seen <= 0:
            continue
        if best is None or seen > best[2]:
            best = (index, hour, seen)
    return best


def basis_note(choice: Choice) -> str:
    if choice.basis is Basis.CART:
        return "слот уже стояв у кошику і досі вільний — не міняли"
    window = f"{choice.offered} найближчих"
    if choice.basis is Basis.ONLY:
        return f"єдиний вільний з {window} — вибору не було"
    if choice.basis is Basis.HABIT:
        note = (
            f"ти приймаєш доставку переважно о {choice.hour:02d}:00 — "
            f"{choice.hour_orders} з {choice.orders} замовлень; "
            f"беру найближче таке з {choice.free} вільних"
        )
        if choice.over_cart:
            note += " — слот, що стояв у кошику, не брали"
        return note
    return f"перший вільний із {choice.free} у {window}"


def no_free_note(delivery_type: str, offered: int) -> str:
    if offered <= 0:
        return f"на {delivery_type} не прийшло жодного слота"
    return f"серед {offered} найближчих слотів {delivery_type} немає жодного вільного"


def moment_of(text: str | None, *, now: datetime) -> datetime | None:
    if not text:
        return None
    try:
        moment = datetime.fromisoformat(str(text))
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=now.tzinfo)


def same_moment(left: str | None, right: str | None) -> bool:
    if left == right:
        return True
    if not left or not right:
        return False
    first, second = _instant(left), _instant(right)
    return first is not None and first == second


def _instant(text: str) -> datetime | None:
    try:
        moment = datetime.fromisoformat(str(text))
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def day_of(start: str | None, *, now: datetime) -> date | None:
    moment = moment_of(start, now=now)
    return None if moment is None else moment.date()


def hours_until(start: str | None, *, now: datetime) -> float:
    moment = moment_of(start, now=now)
    if moment is None:
        return 0.0
    return (moment - now).total_seconds() / 3600


_WEEKDAYS = ("пн", "вт", "ср", "чт", "пт", "сб", "нд")

_NEAR_DAYS = 7


def window_note(start: str | None, end: str | None, *, now: datetime) -> str:
    begin = moment_of(start, now=now)
    finish = moment_of(end, now=now)
    if begin is None or finish is None:
        return " — ".join(str(part) for part in (start, end) if part) or "час не назвали"
    local = begin.astimezone(KYIV)
    hours = f"{local:%H:%M}–{finish.astimezone(KYIV):%H:%M}"
    days = (local.date() - now.astimezone(KYIV).date()).days
    if days == 0:
        return f"сьогодні {hours}"
    if days == 1:
        return f"завтра {hours}"
    weekday = _WEEKDAYS[local.weekday()]
    if 0 <= days < _NEAR_DAYS:
        return f"{weekday} {hours}"
    return f"{weekday} {local:%d.%m} {hours}"
