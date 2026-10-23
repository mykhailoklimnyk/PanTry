from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from komora.core.words import plural

OCCASION_LIMIT = 8


class BuildMode(StrEnum):

    LIST = "list"
    WEEK = "week"
    EVENT = "event"


class EventStyle(StrEnum):

    COOKING = "cooking"
    READY = "ready"


_WITH_PEOPLE = frozenset({BuildMode.EVENT})

_LABELS = {
    BuildMode.LIST: "зі списку",
    BuildMode.WEEK: "на тиждень",
    BuildMode.EVENT: "подія",
}

_STYLES = {
    EventStyle.COOKING: (
        "Гість ГОТУЄ сам: бери сировину й інгредієнти (м'ясо, овочі, сири "
        "шматком), а не готові страви й нарізки."
    ),
    EventStyle.READY: (
        "Гість БЕРЕ ГОТОВЕ: бери нарізки, готові закуски й страви, а не "
        "сировину, яку ще треба готувати."
    ),
}

_TASKS = {
    BuildMode.EVENT: (
        "Подія (гості, вечірка): стіл, а не тижневий запас. Докинь те, чим "
        "накривають стіл — закуски, сир, м'ясо, овочі до столу, напої, "
        "десерт. Подія НЕ Є регулярною покупкою: усе, що гість бере за своїм "
        "розкладом незалежно від гостей (корм для тварин, гігієна, побутова "
        "хімія, засоби для прання), під цей привід не йде — знімай його."
    ),
}


def people_phrase(count: int) -> str:
    return f"{count} {plural(count, 'людина', 'людини', 'людей')}"


@dataclass(frozen=True, slots=True)
class Occasion:

    mode: BuildMode
    people: int | None = None
    style: EventStyle | None = None

    @property
    def named(self) -> bool:
        return self.mode is BuildMode.EVENT

    @property
    def takes_cycles(self) -> bool:
        return self.mode is not BuildMode.LIST

    @property
    def takes_pantry(self) -> bool:
        return self.mode is BuildMode.WEEK

    @property
    def fills_target(self) -> bool:
        return self.mode is BuildMode.WEEK

    @property
    def label(self) -> str:
        return _LABELS[self.mode]

    def phrase(self) -> str:
        parts = [self.label]
        if self.people is not None:
            parts.append(people_phrase(self.people))
        if self.style is not None:
            parts.append("готує сам" if self.style is EventStyle.COOKING else "бере готове")
        return ", ".join(parts)

    def task(self) -> str:
        if not self.named:
            return ""
        task = _TASKS[self.mode]
        if self.people is not None:
            task = f"{task} Людей: {people_phrase(self.people)}."
        if self.style is not None:
            task = f"{task} {_STYLES[self.style]}"
        return task


def occasion_of(mode: str, people: int | None, style: str | None = None) -> Occasion:
    try:
        chosen = BuildMode(mode)
    except ValueError:
        return Occasion(BuildMode.LIST)
    if chosen not in _WITH_PEOPLE:
        return Occasion(chosen)
    try:
        taste = EventStyle(style) if style else None
    except ValueError:
        taste = None
    return Occasion(
        chosen,
        people if people is not None and people >= 1 else None,
        taste,
    )


__all__ = [
    "OCCASION_LIMIT",
    "BuildMode",
    "EventStyle",
    "Occasion",
    "occasion_of",
    "people_phrase",
]
