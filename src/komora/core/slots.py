from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
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
    """Слот уже стояв у кошику і досі вільний, а звичка мовчить або каже те
    саме. Збирати під інший час означало б «обраний час був недоступний»
    на оформленні (живий випадок 14.08) -- доти, доки оформлення не
    навчилось вирівнювати слот саме (`checkout.align_slot`).

    ПРОТИ ЗВИЧКИ ВІН НЕ ТРИМАЄТЬСЯ (10.09, рішення власника). Слот у кошику
    найчастіше ставить наш же попередній прогін, а не гість, і відрізнити
    їх не можна: живий випадок -- кошик тримав «завтра 09:00», а о дев'ятій
    гість доставку не приймає взагалі."""
    FIRST = "first"
    """Перший вільний з кількох. Рішення агента тут немає — є полиця."""
    ONLY = "only"
    """Вільний був один. Це не те саме, що «перший»: «перший з одного» вдає
    вибір, якого не було, — те саме правило, що в картках «Чому саме ці
    позиції» (#43)."""
    HABIT = "habit"
    """Вікно, у яке гість ЗВИЧАЙНО приймає доставку (#349).

    Слова власника 05.09: «треба аналізувати, в який час я зазвичай
    замовляю, і на них планувати». До того обидва правила були про
    НАЯВНІСТЬ -- слот із кошика або перший вільний, -- тобто продукт, який
    будується на ритмі гостя, час доставки брав навмання."""


@dataclass(frozen=True, slots=True)
class Choice:
    index: int
    basis: Basis
    free: int
    offered: int
    """Скільки вікон ми ВЗАГАЛІ бачили — тобто наша стеля, а не весь тиждень
    «Сільпо». Тому в тексті вона й називається: «єдиний вільний» без цього
    слова було б твердженням про чужий асортимент."""
    hour: int | None = None
    """Київська година обраного вікна -- лише при `HABIT`. Разом із двома
    числами нижче вона і є ДОКАЗ звички: «о 15:00 -- 19 з 95»."""
    hour_orders: int = 0
    """Скільки замовлень гість приймав саме в цю годину."""
    orders: int = 0
    """Скільки замовлень стоїть за звичкою взагалі. Без цього числа частка
    не читається: 19 з 95 і 19 з 20 -- різні твердження (#61, #79)."""
    over_cart: bool = False
    """Звичка перемогла слот, який стояв у кошику (10.09). Текст мусить це
    назвати: мовчки замінений слот гість читає як «продукт забув мій
    вибір»."""


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
