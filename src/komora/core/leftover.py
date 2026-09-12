from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

WHOLE = Decimal(1)


@dataclass(frozen=True, slots=True)
class Leftover:

    left_ratio: float
    """Скільки циклу лишилось. Це і є смуга на екрані.

    Понад 1.0 буває і це не помилка: гість сказав, що взяв більше за звичне,
    тобто вдома запас на кілька циклів (#103). Смуга від цього не росте —
    вона й так повна, — а числа поруч (`days_left`, `qty`) кажуть, наскільки
    саме. Зрізати тут означало б забути сказане гостем."""

    days_left: int
    """Днів до кінця за циклом. Нуль тут означає те саме, що `running_out`.
    Більше за цикл — запас наперед."""

    running_out: bool

    qty: Decimal | None
    """Скільки лишилось в одиниці рядка, або None — «кількість не вісь цього
    виду». Не `int`: ваговий вид міряється частками («ще ~0,2 кг»), і
    округлення до цілого перетворило б звичні 300 г на кілограм."""


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
