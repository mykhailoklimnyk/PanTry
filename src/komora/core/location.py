from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum

HOME_DELIVERY = "DeliveryHome"


class Source(StrEnum):

    ADDRESS = "address"
    CART = "cart"
    CONFIG = "config"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class Address:

    label: str
    latitude: float
    longitude: float
    id: str | None = None
    """Id збереженої адреси. None — знайдена пошуком, в акаунті її немає."""
    tag: str | None = None
    kind: str | None = None
    """`addressType` для створення кошика (#272): «flat» у збереженої адреси
    з квартирою, «house» без неї. None -- не знаємо, і тоді кошик
    створюється як «house»: поле обов'язкове, а вигадати краще нема з чого."""
    city: str | None = None
    street: str | None = None
    house: str | None = None


@dataclass(frozen=True, slots=True)
class Location:

    branch_id: str | None = None
    source: Source = Source.NONE
    address: Address | None = None
    branches: Mapping[str, str] = field(default_factory=dict)
    """Філія по КОЖНОМУ способу: слоти самовивозу живуть не там, де слоти
    кур'єра, і один branchId на всіх дає «недоступне все, крім кур'єра»."""
    offered: frozenset[str] | None = None
    """Способи, доступні за адресою. `None` — не питали; порожньо — не возять."""

    @property
    def known(self) -> bool:
        return self.branch_id is not None

    def branch_for(self, delivery_type: str) -> str | None:
        return self.branches.get(delivery_type) or self.branch_id

    def address_branch(self, delivery_type: str) -> str | None:
        return self.branches.get(delivery_type) or self.branches.get(HOME_DELIVERY)

    def offers(self, delivery_type: str) -> bool | None:
        if self.offered is None:
            return None
        return delivery_type in self.offered


def label_of(
    *,
    city: str | None = None,
    street: str | None = None,
    building: str | None = None,
    apartment: str | None = None,
) -> str:
    parts = [part.strip() for part in (city, street, building) if part and part.strip()]
    label = ", ".join(parts)
    flat = (apartment or "").strip()
    if flat:
        label = f"{label}, кв. {flat}" if label else f"кв. {flat}"
    return label


def choose_address(
    addresses: Sequence[Address], *, preferred_id: str | None = None
) -> Address | None:
    if preferred_id:
        chosen = next((item for item in addresses if item.id == preferred_id), None)
        if chosen is not None:
            return chosen
    return addresses[0] if addresses else None


def decide(
    *,
    from_address: str | None = None,
    from_cart: str | None = None,
    from_config: str | None = None,
) -> tuple[str | None, Source]:
    if from_address:
        return from_address, Source.ADDRESS
    if from_cart:
        return from_cart, Source.CART
    if from_config:
        return from_config, Source.CONFIG
    return None, Source.NONE


SOURCE_NOTES: Mapping[Source, str] = {
    Source.ADDRESS: "магазин збирання визначено за цією адресою",
    Source.CART: "магазин узято з кошика, який уже є в акаунті — назви адресу, якщо веземо не туди",
    Source.CONFIG: (
        "магазин з налаштувань сервера, не за твоєю адресою — "
        "назви адресу, і ціни з наявністю будуть з твоєї філії"
    ),
    Source.NONE: "магазин ще не визначено — назви адресу доставки",
}


def source_note(source: Source) -> str:
    return SOURCE_NOTES.get(source, SOURCE_NOTES[Source.NONE])


__all__ = [
    "HOME_DELIVERY",
    "SOURCE_NOTES",
    "Address",
    "Location",
    "Source",
    "choose_address",
    "decide",
    "label_of",
    "source_note",
]
