from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

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
    """Скільки обертів уже зроблено, разом з цим."""

    said_stop: bool
    """Чи сказала модель `stop` у цій пачці."""

    unmet: tuple[str, ...] = ()
    """Невиконані зобов'язання мети. Порожньо -- мета досягнута."""

    fatal: str | None = None
    """Вирок над НАБРАНИМ цілком (`core/plan.verdict`). `None` -- годиться."""

    broken: bool = False
    """Чи пачка не пройшла валідатор навіть після різу."""

    idle: int = 0
    """Скільки обертів ПОСПІЛЬ не дали жодного нового факту."""

    waiting: bool = False
    """Чи впирається робота в СЛОВО ГОСТЯ (#386).

    Не те саме, що досягнута мета, і не те саме, що стеля. Борг лишається
    невиконаним, але виконати його цим прогоном нема чим: питання поставлені,
    відповіді ще немає. Крутитись далі означало б платити за оберти, які
    впираються в те саме."""


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
