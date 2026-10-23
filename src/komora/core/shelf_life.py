from __future__ import annotations

from datetime import date, timedelta

from komora.core.cycles import Keeps, ceiling_days

BUFFER_DAYS = 2

PERISHABLE = frozenset({Keeps.DAYS, Keeps.WEEKS})


def required_until(
    *,
    slot_day: date | None,
    cycle_days: int | None,
    keeps: Keeps | None,
) -> date | None:
    if slot_day is None or cycle_days is None or cycle_days <= 0:
        return None
    if keeps is None or keeps not in PERISHABLE:
        return None
    span = cycle_days + BUFFER_DAYS
    ceiling = ceiling_days(keeps)
    if ceiling is not None and span > ceiling:
        return None
    return slot_day + timedelta(days=span)


def shelf_life_phrase(deadline: date | None) -> str | None:
    if deadline is None:
        return None
    return f"термін придатності не менше ніж до {deadline.strftime('%d.%m')}"


__all__ = ["BUFFER_DAYS", "PERISHABLE", "required_until", "shelf_life_phrase"]
