from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from komora.agent.basket import slots_query
from komora.agent.place import resolve as resolve_place
from komora.api.schemas import WeekSpend
from komora.config import Settings
from komora.config import settings as _default_settings
from komora.core.location import HOME_DELIVERY, Location
from komora.core.spending import spent_since, week_start
from komora.logging import get_logger
from komora.mcp.client import SilpoMCP

log = get_logger(__name__)


class WeekSpendError(RuntimeError):
    """Тижневу рамку порахувати нічим — з людською причиною."""


LOCAL = ZoneInfo("Europe/Kyiv")

MAX_WEEK_PAGES = 3

WEEK_PAGE = 10


async def week_spend(
    mcp: SilpoMCP,
    *,
    settings: Settings | None = None,
    now: datetime | None = None,
    place: Location | None = None,
) -> WeekSpend:
    cfg = settings if settings is not None else _default_settings
    moment = now or datetime.now(UTC)
    since = week_start(moment.astimezone(LOCAL).replace(tzinfo=None))

    where = place if place is not None else await resolve_place(mcp, settings=cfg)
    branch_id = where.branch_for(HOME_DELIVERY) or cfg.branch_id
    slots = (
        await mcp.call(
            "silpo_get_time_slots",
            slots_query(branch_id, HOME_DELIVERY, 5, since=moment),
        )
    ).payload_raw.get("slots") or []
    slot = next((s for s in slots if s.get("available")), slots[0] if slots else None)
    if slot is None:
        raise WeekSpendError("немає жодного слота — без нього чеки не читаються")

    orders: list[dict[str, Any]] = []
    for _ in range(MAX_WEEK_PAGES):
        payload = (
            await mcp.call(
                "silpo_get_my_offline_orders",
                {
                    "branchId": branch_id,
                    "deliveryType": slot["deliveryType"],
                    "timeslotStart": slot["start"],
                    "timeslotEnd": slot["end"],
                    "limit": WEEK_PAGE,
                    "offset": len(orders),
                    "dateStart": since.isoformat(),
                },
            )
        ).payload_raw
        batch = payload.get("orders") or []
        orders += batch
        total = (payload.get("meta") or {}).get("total")
        if len(batch) < WEEK_PAGE or (total is not None and len(orders) >= int(total)):
            break

    spent, receipts = spent_since(orders, since)
    log.info("spending.week", receipts=receipts, since=since.date().isoformat())
    return WeekSpend(spent=spent, receipts=receipts, since=since)


__all__ = ["LOCAL", "MAX_WEEK_PAGES", "WEEK_PAGE", "WeekSpendError", "week_spend"]
