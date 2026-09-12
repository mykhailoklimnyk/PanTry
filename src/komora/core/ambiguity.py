from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from komora.core.dictionary import STEM, same_word, words_of
from komora.core.packaging import is_sold_by_weight, price_per_100g

MAX_OPTIONS = 4

MAX_QUESTIONS = 3


@dataclass(frozen=True, slots=True)
class Option:

    title: str
    slug: str
    count: int
    price_from: Decimal | None = None
    by_weight: bool = False
    """Ціна за КІЛОГРАМ, а не за штуку: у вагового товару API так і віддає,
    і підписати її просто гривнями означало б показати 272 ₴ за шматок."""
    query: str = ""
    """ФРАЗА, якою цей варіант шукається на полиці (#280).

    Порожньо -- варіант це вузол дерева, і звужує він переліком вузла.
    Непорожньо -- варіант назвала МОДЕЛЬ («свинина лопатка»), вузла під ним
    немає, і єдине, чим його звузити, -- та сама фраза в пошуку. Без неї
    відповідь чипом міняла б лише слово в промпті, а обирати модель далі
    мусила б з тих самих двадцяти шашликів."""

    @property
    def empty(self) -> bool:
        return not self.count

    @property
    def key(self) -> str:
        return self.slug or self.query


def _touches(left: str, right: str) -> bool:
    if same_word(left, right):
        return True
    return len(left) >= STEM and left[:STEM] == right[:STEM]


def axis_of(ask: str, word: str) -> tuple[str, ...]:
    said = words_of(word)
    return tuple(
        item for item in words_of(ask) if not any(_touches(item, spoken) for spoken in said)
    )


def on_axis(title: str, axis: Sequence[str]) -> bool:
    return any(_touches(left, right) for left in axis for right in words_of(title))


def _price(product: dict[str, Any]) -> Decimal | None:
    raw = product.get("price")
    if raw is None:
        return None
    price = Decimal(str(raw))
    return price if price > 0 else None


def _by_weight(product: dict[str, Any]) -> bool:
    step = product.get("step")
    return is_sold_by_weight(
        weighted=product.get("weighted"),
        ratio=product.get("displayRatio"),
        step=Decimal(str(step)) if step is not None else None,
    )


def option(title: str, slug: str, products: Sequence[dict[str, Any]], *, query: str = "") -> Option:
    prices = [price for price in map(_price, products) if price is not None]
    weighted = [product for product in products if _by_weight(product)]
    return Option(
        title=title,
        slug=slug,
        query=query,
        count=len(products),
        price_from=min(prices) if prices else None,
        by_weight=len(weighted) * 2 > len(products),
    )


def unit_prices(products: Iterable[dict[str, Any]]) -> list[Decimal]:
    found = []
    for product in products:
        step = product.get("step")
        price = price_per_100g(
            _price(product),
            weighted=product.get("weighted"),
            ratio=product.get("displayRatio"),
            step=Decimal(str(step)) if step is not None else None,
        )
        if price is not None:
            found.append(price)
    return found


def usable(options: Iterable[Option], *, limit: int = MAX_OPTIONS) -> tuple[Option, ...]:
    seen: set[str] = set()
    kept: list[Option] = []
    for item in options:
        if item.empty or not item.key or item.key in seen:
            continue
        seen.add(item.key)
        kept.append(item)
        if len(kept) >= limit:
            break
    return tuple(kept)


__all__ = [
    "MAX_OPTIONS",
    "MAX_QUESTIONS",
    "Option",
    "axis_of",
    "on_axis",
    "option",
    "unit_prices",
    "usable",
]
