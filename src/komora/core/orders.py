from __future__ import annotations

from enum import StrEnum


class Stage(StrEnum):

    NEW = "new"
    COLLECTING = "collecting"
    COLLECTED = "collected"
    DELIVERING = "delivering"
    RECEIVED = "received"
    CANCELED = "canceled"
    UNKNOWN = "unknown"


_STATUSES: dict[str, Stage] = {
    "new": Stage.NEW,
    "collecting": Stage.COLLECTING,
    "collected": Stage.COLLECTED,
    "delivery_in_progress": Stage.DELIVERING,
    "received": Stage.RECEIVED,
    "canceled": Stage.CANCELED,
}


def stage_of(status: str | None) -> Stage:
    return _STATUSES.get((status or "").strip().lower(), Stage.UNKNOWN)


__all__ = ["Stage", "stage_of"]
