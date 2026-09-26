from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any


def week_start(now: datetime) -> datetime:
    return (now - timedelta(days=now.weekday())).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def receipt_moment(order: Mapping[str, Any]) -> datetime | None:
    raw = order.get("createdAt")
    if not raw:
        return None
    try:
        moment = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    return moment.replace(tzinfo=None)


def spent_since(orders: Sequence[Mapping[str, Any]], since: datetime) -> tuple[Decimal, int]:
    edge = since.replace(tzinfo=None)
    total = Decimal(0)
    count = 0
    for order in orders:
        moment = receipt_moment(order)
        if moment is None or moment < edge:
            continue
        amount = order.get("sumReg")
        if amount is None:
            continue
        total += Decimal(str(amount))
        count += 1
    return total, count


__all__ = ["receipt_moment", "spent_since", "week_start"]
