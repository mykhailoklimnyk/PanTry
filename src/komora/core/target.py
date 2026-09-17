from __future__ import annotations

from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal

TOLERANCE = Decimal("0.1")


@dataclass(frozen=True, slots=True)
class Band:

    target: Decimal
    low: Decimal
    high: Decimal

    def holds(self, total: Decimal) -> bool:
        return self.low <= total <= self.high

    def short_by(self, total: Decimal) -> Decimal:
        return max(Decimal(0), self.low - total)

    def over_by(self, total: Decimal) -> Decimal:
        return max(Decimal(0), total - self.high)

    def phrase(self) -> str:
        return f"ціль {self.target:.0f} грн, коридор {self.low:.0f}-{self.high:.0f}"


def band(target: Decimal, *, tolerance: Decimal = TOLERANCE) -> Band:
    return Band(
        target=target,
        low=(target * (1 - tolerance)).quantize(Decimal("0.01")),
        high=(target * (1 + tolerance)).quantize(Decimal("0.01")),
    )


STRETCH = Decimal(3)


@dataclass(frozen=True, slots=True)
class Stretched:

    named: Decimal
    proposed: Decimal
    target: Decimal
    """Прийнята межа: пропозиція агента або названа, коли її відкинуто."""
    why: str = ""
    refused: str | None = None
    """Чому пропозицію не взято. `None` -- взято."""


def stretch(
    named: Decimal, proposed: Decimal | None, *, why: str = "", said: bool = False
) -> Stretched | None:
    if proposed is None:
        return None
    proposed = proposed.quantize(Decimal(1))
    if proposed == named:
        return None
    refused: str | None = None
    if said:
        refused = "межу назвав сам гість -- його число старше за рішення агента"
    elif proposed < named:
        refused = "агент може лише підняти межу під привід; знизити її може лише гість"
    elif proposed > named * STRETCH:
        refused = f"понад стелю x{STRETCH:.0f} від названої межі {named:.0f} грн"
    return Stretched(
        named=named,
        proposed=proposed,
        target=named if refused else proposed,
        why=why,
        refused=refused,
    )


@dataclass(frozen=True, slots=True)
class Candidate:

    key: str
    rank: int
    """Менше — сильніша підстава. Шар важить сотнями, гострота — одиницями:
    «закінчиться за 2 дн» стоїть попереду «закінчиться за 9 дн», але обидва —
    попереду запасу. Гострота МУСИТЬ лишатись у межах свого шару
    (`LAYER_WIDTH`), інакше вона мовчки переносить кандидата в чужий."""
    cost: Decimal | None
    why: str
    kind: str = ""
    """Вид, до якого належить кандидат. Порожньо — вид невідомий, і тоді
    кандидат ні з ким не сперечається: невідоме не має мовчки нікого
    витісняти.

    ЗВОДИТЬСЯ ВІН НЕ ТУТ (#323). Ключ будується зі слова ДВІЧІ і з різних
    джерел -- з назви чека (кандидат) і зі слова гостя (накриття), -- тож
    єдиний дім у нього `core/catalog.kind_word`. Зведення на цьому
    порівнянні полагодило б лише половину: з картою видів обидва боки
    приходять сюди вже готовими класами."""


LAYER_WIDTH = 100

SUPPLY_RANK = 300


def supply_rank(days_left: int | None) -> int:
    if days_left is None:
        return SUPPLY_RANK + LAYER_WIDTH - 1
    return SUPPLY_RANK + min(LAYER_WIDTH - 1, max(0, days_left))


def priced(item: Candidate) -> Decimal | None:
    return item.cost if item.cost is not None and item.cost > 0 else None


@dataclass(frozen=True, slots=True)
class Reach:

    kinds: int = 0
    """Скільки видів мають ціну в чеках -- тобто чим добирати взагалі є."""
    estimate: Decimal | None = None
    """На скільки вони тягнуть разом. `None` -- видів нуль, і суми немає.

    Не нуль: нуль у грошах читається як «безкоштовно» і ховає різницю між
    «порахували і вийшло нічого» та «рахувати нема з чого» (#76)."""


def reach(pool: Iterable[Candidate]) -> Reach:
    costs = [cost for item in pool if (cost := priced(item)) is not None]
    if not costs:
        return Reach()
    return Reach(kinds=len(costs), estimate=sum(costs, Decimal(0)))


@dataclass(frozen=True, slots=True)
class Filled:

    taken: tuple[Candidate, ...] = ()
    spent: Decimal = Decimal(0)
    no_price: int = 0
    same_kind: int = 0
    over_high: int = 0

    def note(self) -> str:
        parts = []
        if self.no_price:
            parts.append(f"{self.no_price} без ціни в чеках")
        if self.same_kind:
            parts.append(f"{self.same_kind} того ж виду, що вже в кошику")
        if self.over_high:
            parts.append(f"{self.over_high} не влізли під верхню межу")
        return ", ".join(parts)


def fill(
    *, have: Decimal, band: Band, pool: Sequence[Candidate], covered: Collection[str] = ()
) -> Filled:
    if have >= band.high:
        return Filled()
    taken: list[Candidate] = []
    seen = {kind for kind in covered if kind}
    spent = Decimal(0)
    no_price = same_kind = over_high = 0
    for item in sorted(pool, key=lambda c: (c.rank, c.key)):
        cost = priced(item)
        if cost is None:
            no_price += 1
            continue
        if have + spent >= band.high:
            break
        if item.kind and item.kind in seen:
            same_kind += 1
            continue
        if have + spent + cost > band.high:
            over_high += 1
            continue
        taken.append(item)
        spent += cost
        if item.kind:
            seen.add(item.kind)
    return Filled(
        taken=tuple(taken),
        spent=spent,
        no_price=no_price,
        same_kind=same_kind,
        over_high=over_high,
    )


OVERSHOOT_OPTIONS = 4

TARGET_STEP = Decimal(100)


@dataclass(frozen=True, slots=True)
class Drop:

    intent: str
    name: str
    price: Decimal
    left: Decimal


@dataclass(frozen=True, slots=True)
class Overshoot:

    drops: tuple[Drop, ...]
    target: Decimal

    def asks(self) -> bool:
        return bool(self.drops)


def overshoot(
    total: Decimal,
    *,
    band: Band,
    rows: Sequence[tuple[str, str, Decimal]],
    limit: int = OVERSHOOT_OPTIONS,
    step: Decimal = TARGET_STEP,
) -> Overshoot:
    over = band.over_by(total)
    drops = tuple(
        Drop(intent=intent, name=name, price=price, left=total - price)
        for intent, name, price in sorted(rows, key=lambda row: -row[2])
        if price >= over
    )[:limit]
    fits = total / (band.high / band.target) if band.target else total
    raised = (fits / step).to_integral_value(rounding="ROUND_CEILING") * step
    return Overshoot(drops=drops, target=raised)


__all__ = [
    "LAYER_WIDTH",
    "OVERSHOOT_OPTIONS",
    "STRETCH",
    "SUPPLY_RANK",
    "TARGET_STEP",
    "TOLERANCE",
    "Band",
    "Candidate",
    "Drop",
    "Filled",
    "Overshoot",
    "Reach",
    "Stretched",
    "band",
    "fill",
    "overshoot",
    "priced",
    "reach",
    "stretch",
    "supply_rank",
]
