from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

DEFAULT_BUFFER_HOURS = 12


class BranchScope(StrEnum):

    OWN = "own"
    ANY = "any"
    HUB = "hub"


@dataclass(frozen=True, slots=True)
class Channel:
    name: str
    lead_time_hours: int
    scope: BranchScope
    min_order_cost: Decimal
    max_weight_kg: Decimal | None
    carries_perishables: bool


def is_admissible(
    channel: Channel,
    *,
    hours_until_runout: int | None,
    perishable: bool = False,
    buffer_hours: int = DEFAULT_BUFFER_HOURS,
) -> bool:
    if perishable and not channel.carries_perishables:
        return False
    if hours_until_runout is None:
        return True
    return channel.lead_time_hours + buffer_hours <= hours_until_runout


def admissible(
    channels: Iterable[Channel],
    *,
    hours_until_runout: int | None,
    perishable: bool = False,
    buffer_hours: int = DEFAULT_BUFFER_HOURS,
) -> tuple[Channel, ...]:
    fitting = [
        channel
        for channel in channels
        if is_admissible(
            channel,
            hours_until_runout=hours_until_runout,
            perishable=perishable,
            buffer_hours=buffer_hours,
        )
    ]
    return tuple(sorted(fitting, key=lambda c: (c.lead_time_hours, c.name)))


def needs_forecast(channel: Channel, *, typical_notice_hours: int = 24) -> bool:
    return channel.lead_time_hours > typical_notice_hours
