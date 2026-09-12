from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime

MAX_GUESTS = 16

TTL_S = 1800.0


@dataclass(frozen=True, slots=True)
class Seen:

    receipts: object
    at: datetime

    def fresh(self, now: datetime) -> bool:
        return (now - self.at).total_seconds() < TTL_S


_SEEN: OrderedDict[str, Seen] = OrderedDict()


def remember(receipts: object, *, owner: str, now: datetime | None = None) -> None:
    if not owner:
        return
    _SEEN[owner] = Seen(receipts, now or datetime.now(UTC))
    _SEEN.move_to_end(owner)
    while len(_SEEN) > MAX_GUESTS:
        _SEEN.popitem(last=False)


def recall(owner: str, *, now: datetime | None = None) -> object | None:
    seen = _SEEN.get(owner)
    if seen is None:
        return None
    if not seen.fresh(now or datetime.now(UTC)):
        _SEEN.pop(owner, None)
        return None
    _SEEN.move_to_end(owner)
    return seen.receipts


def forget(owner: str) -> None:
    _SEEN.pop(owner, None)


def forget_all() -> None:
    _SEEN.clear()


__all__ = ["MAX_GUESTS", "TTL_S", "Seen", "forget", "forget_all", "recall", "remember"]
