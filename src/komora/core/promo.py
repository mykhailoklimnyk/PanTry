from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from statistics import median
from typing import Any

MIN_PURCHASES = 3

MIN_DISCOUNTED = 2

MOSTLY = (2, 3)

BELOW_CATALOG = Decimal("0.15")
BELOW_OWN_MAX = Decimal("0.15")

CATALOG = "каталог"
SHELF = "полиця"
OWN_MAX = "свій максимум"


@dataclass(frozen=True, slots=True)
class Purchase:

    paid: Decimal
    qty: Decimal = Decimal(1)
    seen: Decimal | None = None
    """Ціна каталогу, яку ми бачили в мить читання чека. None -- не бачили
    (онлайн-рядок несе лише заплачене, старий чек лежить без картки)."""


@dataclass(frozen=True, slots=True)
class Habit:

    purchases: int = 0
    discounted: int = 0
    usual_qty: Decimal | None = None
    """Скільки гість бере, КОЛИ бере по акції: медіана кількості акційних
    покупок. Пиво Hike -- 6 при звичних 6, вода Спортик -- 5 при звичних
    3,5. None -- акційних покупок не було."""
    weighed: bool = False
    """Ваговий вид: вісь на ньому вимкнена свідомо (докстрінг модуля)."""

    @property
    def mostly(self) -> bool:
        share, out_of = MOSTLY
        return (
            not self.weighed
            and self.purchases >= MIN_PURCHASES
            and self.discounted >= MIN_DISCOUNTED
            and self.discounted * out_of >= self.purchases * share
        )

    def phrase(self) -> str:
        if not self.mostly:
            return ""
        text = f"береш по акції: {self.discounted} з {self.purchases}"
        if self.usual_qty is not None and self.usual_qty > 1:
            text += f", зазвичай по {self.usual_qty}"
        return text


def proof(
    purchase: Purchase,
    *,
    regular: Decimal,
    shelf: Decimal | None = None,
    below_catalog: Decimal = BELOW_CATALOG,
    below_own: Decimal = BELOW_OWN_MAX,
) -> str | None:
    if purchase.paid <= 0:
        return None
    seen = purchase.seen if purchase.seen is not None and purchase.seen > 0 else None
    if seen is not None:
        if purchase.paid < seen * (1 - below_catalog):
            return CATALOG
    elif shelf is not None and shelf > 0 and purchase.paid < shelf * (1 - below_catalog):
        return SHELF
    if regular > 0 and purchase.paid < regular * (1 - below_own):
        return OWN_MAX
    return None


def is_discounted(
    purchase: Purchase,
    *,
    regular: Decimal,
    shelf: Decimal | None = None,
    below_catalog: Decimal = BELOW_CATALOG,
    below_own: Decimal = BELOW_OWN_MAX,
) -> bool:
    return (
        proof(
            purchase,
            regular=regular,
            shelf=shelf,
            below_catalog=below_catalog,
            below_own=below_own,
        )
        is not None
    )


def habit(
    purchases: Sequence[Purchase],
    *,
    weighed: bool = False,
    shelf: Decimal | None = None,
    below_catalog: Decimal = BELOW_CATALOG,
    below_own: Decimal = BELOW_OWN_MAX,
) -> Habit:
    valid = [purchase for purchase in purchases if purchase.paid > 0]
    if not valid:
        return Habit(weighed=weighed)
    if any(purchase.seen is not None and purchase.seen > 0 for purchase in valid):
        shelf = None
    regular = max(purchase.paid for purchase in valid)
    flags = [
        is_discounted(
            purchase,
            regular=regular,
            shelf=shelf,
            below_catalog=below_catalog,
            below_own=below_own,
        )
        for purchase in valid
    ]
    on_sale_qty = [
        purchase.qty
        for purchase, discounted in zip(valid, flags, strict=True)
        if discounted and purchase.qty > 0
    ]
    usual = None
    if on_sale_qty:
        usual = Decimal(max(1, round(median(on_sale_qty))))
    return Habit(
        purchases=len(valid),
        discounted=sum(1 for discounted in flags if discounted),
        usual_qty=usual,
        weighed=weighed,
    )


def _money(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except ArithmeticError:
        return None


def purchase_of(row: Mapping[str, Any], qty: Decimal) -> Purchase | None:
    paid = _money(row.get("price"))
    if paid is None:
        return None
    card = row.get("catalogProduct") or {}
    seen = card.get("price") if isinstance(card, Mapping) else None
    if seen is None:
        seen = row.get("priceSeen")
    return Purchase(paid=paid, qty=qty, seen=_money(seen))


def on_sale(product: Mapping[str, Any]) -> bool:
    old = _money(product.get("oldPrice"))
    price = _money(product.get("price"))
    return old is not None and price is not None and old > price


def regular_of(product: Mapping[str, Any]) -> Decimal | None:
    old = _money(product.get("oldPrice"))
    price = _money(product.get("price"))
    if old is not None and price is not None and old > price:
        return old
    return price


def sale_phrase(product: Mapping[str, Any]) -> str:
    old = _money(product.get("oldPrice"))
    price = _money(product.get("price"))
    if old is None or price is None:
        return ""
    return f"було {old}, стало {price}"


__all__ = [
    "BELOW_CATALOG",
    "BELOW_OWN_MAX",
    "CATALOG",
    "MIN_DISCOUNTED",
    "MIN_PURCHASES",
    "MOSTLY",
    "OWN_MAX",
    "SHELF",
    "Habit",
    "Purchase",
    "habit",
    "is_discounted",
    "on_sale",
    "proof",
    "purchase_of",
    "regular_of",
    "sale_phrase",
]
