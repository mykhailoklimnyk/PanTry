from __future__ import annotations

from datetime import datetime, timedelta


def stocked_at(
    *,
    now: datetime,
    cycle_days: int,
    typical_qty: float,
    qty: float,
) -> datetime:
    if typical_qty <= 0:
        return now
    share = max(0.0, qty / typical_qty)
    return now - timedelta(days=round(cycle_days * (1.0 - share)))


def bought_now(now: datetime) -> datetime:
    return now


__all__ = ["bought_now", "stocked_at"]
