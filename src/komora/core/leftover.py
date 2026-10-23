from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

WHOLE = Decimal(1)


@dataclass(frozen=True, slots=True)
class Leftover:

    left_ratio: float

    days_left: int

    running_out: bool

    qty: Decimal | None


def leftover(
    *,
    cycle_days: int,
    days_since: int,
    typical_qty: Decimal | int,
    smallest: Decimal | int = WHOLE,
) -> Leftover:
    running_out = days_since >= cycle_days
    left_ratio = 0.0 if running_out else 1 - days_since / cycle_days
    days_left = 0 if running_out else cycle_days - days_since
    step = Decimal(smallest)
    usual = Decimal(typical_qty)
    if usual <= step and left_ratio <= 1:
        qty = None
    elif running_out:
        qty = Decimal(0)
    else:
        left = usual * Decimal(str(left_ratio))
        qty = max(step, (left / step).quantize(Decimal(1)) * step)
    return Leftover(
        left_ratio=left_ratio,
        days_left=days_left,
        running_out=running_out,
        qty=qty,
    )


__all__ = ["WHOLE", "Leftover", "leftover"]
