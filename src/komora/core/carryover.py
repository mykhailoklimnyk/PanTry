from __future__ import annotations

from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


@dataclass(frozen=True, slots=True)
class Extra:

    product_id: str
    """UUID: саме ним `remove_cart_products` адресує рядок."""
    name: str
    quantity: Decimal
    total: Decimal
    """Сума рядка з поля `total` кошика.

    Не `price × quantity`: у вагового товару ціна стоїть за КІЛОГРАМ, і
    множення дало б суму за кілограм там, де в кошику триста грамів.
    """


@dataclass(frozen=True, slots=True)
class CarryOver:

    rows: tuple[Extra, ...] = ()

    @property
    def total(self) -> Decimal:
        return sum((row.total for row in self.rows), Decimal(0))

    def __bool__(self) -> bool:
        return bool(self.rows)


def carried_over(rows: Iterable[Mapping[str, Any]], *, writing: Collection[str]) -> CarryOver:
    return CarryOver(
        rows=tuple(
            extra
            for raw in rows
            if (extra := _extra(raw)) is not None and extra.product_id not in writing
        )
    )


def _extra(raw: Mapping[str, Any]) -> Extra | None:
    product_id = raw.get("productId")
    if not product_id:
        return None
    return Extra(
        product_id=str(product_id),
        name=str(raw.get("name") or "рядок без назви"),
        quantity=_number(raw.get("quantity")),
        total=_number(raw.get("total")),
    )


def _number(raw: Any) -> Decimal:
    try:
        return Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(0)


__all__ = ["CarryOver", "Extra", "carried_over"]
