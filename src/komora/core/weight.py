from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from decimal import Decimal

from komora.core.packaging import parse_pack_weight, sale_unit

GRAMS_IN_KG = Decimal(1000)


@dataclass(frozen=True, slots=True)
class WeighedLine:
    external_product_id: str
    qty: Decimal
    unit_weight_g: int


@dataclass(frozen=True, slots=True)
class Estimate:

    kg: Decimal
    unknown: int
    """Скільки рядків ваги не назвали. Поки він не нуль, `kg` — НИЖНЯ межа."""

    @property
    def complete(self) -> bool:
        return self.unknown == 0


def unit_weight_kg(
    *, weighted: bool | None, ratio: str | None, step: Decimal | None
) -> Decimal | None:
    if sale_unit(weighted=weighted, ratio=ratio, step=step) is not None:
        return Decimal(1)
    grams = parse_pack_weight(ratio)
    if grams is None or grams <= 0:
        return None
    return grams / GRAMS_IN_KG


def cart_weight(lines: Iterable[tuple[Decimal, Decimal | None]]) -> Estimate:
    total = Decimal(0)
    unknown = 0
    for qty, unit in lines:
        if unit is None:
            unknown += 1
        else:
            total += qty * unit
    return Estimate(kg=total, unknown=unknown)


def over_limit(kg: Decimal, max_weight_kg: Decimal | None) -> Decimal:
    if not max_weight_kg or max_weight_kg <= 0:
        return Decimal(0)
    return max(Decimal(0), kg - max_weight_kg)


def line_weight_g(line: WeighedLine) -> Decimal:
    return line.qty * line.unit_weight_g


def total_weight_g(lines: Iterable[WeighedLine]) -> Decimal:
    return sum((line_weight_g(line) for line in lines), Decimal(0))


def total_weight_kg(lines: Iterable[WeighedLine]) -> Decimal:
    return total_weight_g(lines) / GRAMS_IN_KG


def exceeds_limit(lines: Iterable[WeighedLine], max_weight_kg: Decimal) -> bool:
    return total_weight_kg(lines) > max_weight_kg


def portions(line: WeighedLine) -> list[Decimal]:
    whole = int(line.qty)
    remainder = line.qty - whole
    parts = [Decimal(1)] * whole
    if remainder > 0:
        parts.append(remainder)
    return parts


def split_by_weight(
    lines: Sequence[WeighedLine],
    max_weight_kg: Decimal,
) -> tuple[tuple[WeighedLine, ...], ...]:
    if max_weight_kg <= 0:
        raise ValueError("max_weight_kg має бути додатним")

    limit_g = max_weight_kg * GRAMS_IN_KG

    units: list[tuple[Decimal, WeighedLine]] = []
    for line in lines:
        for part in portions(line):
            weight = part * line.unit_weight_g
            if weight > limit_g:
                raise ValueError(
                    f"одна одиниця {line.external_product_id} важить більше за ліміт "
                    f"{max_weight_kg} кг — перевір weight_g у products"
                )
            units.append((part, line))

    units.sort(key=lambda unit: (-(unit[0] * unit[1].unit_weight_g), unit[1].external_product_id))

    bins: list[dict[str, Decimal]] = []
    sources: list[dict[str, WeighedLine]] = []
    loads: list[Decimal] = []

    for part, line in units:
        weight = part * line.unit_weight_g
        for index, load in enumerate(loads):
            if load + weight <= limit_g:
                target = index
                break
        else:
            bins.append({})
            sources.append({})
            loads.append(Decimal(0))
            target = len(bins) - 1

        pid = line.external_product_id
        bins[target][pid] = bins[target].get(pid, Decimal(0)) + part
        sources[target][pid] = line
        loads[target] += weight

    return tuple(
        tuple(
            WeighedLine(
                external_product_id=pid,
                qty=qty,
                unit_weight_g=sources[index][pid].unit_weight_g,
            )
            for pid, qty in shipment.items()
        )
        for index, shipment in enumerate(bins)
    )
