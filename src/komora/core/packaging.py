from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal

_ML_TO_G = Decimal(1)

_UNIT_TO_GRAMS = {
    "г": Decimal(1),
    "гр": Decimal(1),
    "g": Decimal(1),
    "кг": Decimal(1000),
    "kg": Decimal(1000),
    "мл": _ML_TO_G,
    "ml": _ML_TO_G,
    "л": _ML_TO_G * 1000,
    "l": _ML_TO_G * 1000,
}

_NUMBER = r"\d+(?:[.,]\d+)?"
_UNITS = "|".join(sorted(_UNIT_TO_GRAMS, key=len, reverse=True))

_MULTIPACK = re.compile(
    rf"(?P<count>\d+)\s*[хx×*]\s*(?P<amount>{_NUMBER})\s*(?P<unit>{_UNITS})\b",
    re.IGNORECASE,
)
_SINGLE = re.compile(rf"(?P<amount>{_NUMBER})\s*(?P<unit>{_UNITS})\b", re.IGNORECASE)

_ENERGY = re.compile(rf"(?P<kcal>{_NUMBER})\s*/\s*(?P<kj>{_NUMBER})")

_WEIGHT_RATIOS = frozenset({"кг", "kg", "г", "g", "л", "l"})

_SALE_UNITS = {
    "кг": "кг",
    "kg": "кг",
    "г": "кг",
    "gr": "кг",
    "g": "кг",
    "л": "л",
    "l": "л",
    "мл": "л",
    "ml": "л",
}

_FALLBACK_STEP = Decimal("0.1")

RECEIPT_GRAM_UNITS = frozenset({"г", "гр", "g", "грам", "грами", "грамів"})

_PACK_UNIT = re.compile(r"^\d+[.,]?\d*\s*(г|гр|мл|л)$")


def _to_decimal(raw: str) -> Decimal:
    return Decimal(raw.replace(",", "."))


def parse_pack_weight(text: str | None) -> Decimal | None:
    if not text:
        return None

    multi = _MULTIPACK.search(text)
    if multi:
        count = Decimal(multi.group("count"))
        amount = _to_decimal(multi.group("amount"))
        return count * amount * _UNIT_TO_GRAMS[multi.group("unit").lower()]

    single = _SINGLE.search(text)
    if single:
        return _to_decimal(single.group("amount")) * _UNIT_TO_GRAMS[single.group("unit").lower()]

    return None


@dataclass(frozen=True, slots=True)
class Energy:
    kcal: Decimal
    kj: Decimal | None = None


def parse_energy(raw: str | None) -> Energy | None:
    if not raw:
        return None

    pair = _ENERGY.search(raw)
    if pair:
        return Energy(kcal=_to_decimal(pair.group("kcal")), kj=_to_decimal(pair.group("kj")))

    lone = re.search(_NUMBER, raw)
    return Energy(kcal=_to_decimal(lone.group())) if lone else None


def is_sold_by_weight(*, weighted: bool | None, ratio: str | None, step: Decimal | None) -> bool:
    if ratio and ratio.strip().lower() in _WEIGHT_RATIOS:
        return True
    if weighted:
        return True
    return bool(step and step % 1 != 0)


def price_per_100g(
    price: Decimal | None,
    *,
    weighted: bool | None,
    ratio: str | None,
    step: Decimal | None = None,
) -> Decimal | None:
    if price is None or price <= 0:
        return None
    if is_sold_by_weight(weighted=weighted, ratio=ratio, step=step):
        return price / 10
    grams = parse_pack_weight(ratio)
    if not grams or grams <= 0:
        return None
    return price * 100 / grams


def sale_unit(*, weighted: bool | None, ratio: str | None, step: Decimal | None) -> str | None:
    if not is_sold_by_weight(weighted=weighted, ratio=ratio, step=step):
        return None
    text = (ratio or "").strip().lower()
    named = _SALE_UNITS.get(text)
    if named:
        return named
    found = _SINGLE.search(text)
    if found:
        return _SALE_UNITS.get(found.group("unit").lower(), "кг")
    return "кг"


def receipt_unit(raw: str | None) -> str:
    text = (raw or "").strip()
    lowered = text.lower()
    if not lowered:
        return ""
    if lowered in RECEIPT_GRAM_UNITS:
        return "кг"
    if _PACK_UNIT.match(lowered):
        return "уп"
    return text


def sale_step(*, ratio: str | None, step: Decimal | None) -> Decimal:
    if step and step > 0:
        return step
    grams = parse_pack_weight(ratio)
    if grams and grams > 0:
        return grams / 1000
    return _FALLBACK_STEP


def quantize_to_step(quantity: Decimal, step: Decimal | None) -> Decimal:
    if not step or step <= 0:
        return quantity
    steps = (quantity / step).to_integral_value(rounding="ROUND_CEILING")
    return steps * step
