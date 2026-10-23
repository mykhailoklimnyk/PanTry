from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

BATCH_MIN = 1
BATCH_MAX = 4

MAX_TURNS = 6

STUCK_TURNS = 2


class Halt(StrEnum):

    DONE = "мета досягнута"
    WAITING = "далі потрібне слово гостя"
    SAID = "модель сказала, що досить"
    CEILING = "стеля перепланів"
    STUCK = "дві пачки поспіль без нового факту"
    BROKEN = "пачка не годиться навіть після різу"


@dataclass(frozen=True, slots=True)
class Progress:

    turn: int

    said_stop: bool

    unmet: tuple[str, ...] = ()

    fatal: str | None = None

    broken: bool = False

    idle: int = 0

    waiting: bool = False


def halt(progress: Progress, *, ceiling: int = MAX_TURNS, obey_stop: bool = False) -> Halt | None:
    if progress.broken:
        return Halt.BROKEN
    if not progress.unmet and progress.fatal is None:
        return Halt.DONE
    if progress.waiting:
        return Halt.WAITING
    if obey_stop and progress.said_stop:
        return Halt.SAID
    if progress.turn >= ceiling:
        return Halt.CEILING
    if progress.idle >= STUCK_TURNS:
        return Halt.STUCK
    return None


def trim[T](items: Sequence[T], *, cap: int = BATCH_MAX) -> tuple[tuple[T, ...], tuple[T, ...]]:
    return tuple(items[:cap]), tuple(items[cap:])


def fresh(was: tuple[int, Any] | None, size: int, value: Any) -> bool:
    if was is None:
        return True
    was_size, was_value = was
    if size > was_size:
        return True
    if was_value == value:
        return False
    if isinstance(value, Mapping) and isinstance(was_value, Mapping):
        return any(key not in was_value or was_value[key] != item for key, item in value.items())
    if isinstance(value, frozenset | set) and isinstance(was_value, frozenset | set):
        return bool(value - was_value)
    return True
