from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping, Sized
from dataclasses import dataclass
from typing import Any

from komora.core.plan import STEPS, StepKind

NAMES: frozenset[str] = frozenset().union(*((kind.needs | kind.gives) for kind in STEPS))

BEFORE = "відоме наперед"


def size_of(value: Any) -> int:
    if isinstance(value, Sized) and not isinstance(value, str | bytes):
        return len(value)
    return 1


@dataclass(frozen=True, slots=True)
class Fact:

    name: str
    value: Any
    step: str
    """Крок, який його дав, або `BEFORE`."""
    batch: int
    """Пачка, у якій це сталось. Нуль -- до першої пачки."""
    size: int

    def told(self) -> str:
        return f"{self.size} ({self.step})"


class Facts:

    def __init__(self, known: Mapping[str, Any] | None = None) -> None:
        self._facts: dict[str, Fact] = {}
        self._writes: dict[str, int] = {}
        for name, value in (known or {}).items():
            if value is not None:
                self.put(name, value, step=BEFORE, batch=0)

    def put(self, name: str, value: Any, *, step: str, batch: int = 0) -> Fact:
        if name not in NAMES:
            raise KeyError(
                f"факту «{name}» немає в словнику кроків: покласти його нікуди, "
                "бо жоден крок його не читає — додай ім'я в needs/gives"
            )
        if value is None:
            raise ValueError(
                f"факт «{name}» порожній (None): це не факт, а його відсутність — "
                "крок, який нічого не дав, мусить сказати це відмовою"
            )
        fact = Fact(name=name, value=value, step=step, batch=batch, size=size_of(value))
        self._facts[name] = fact
        self._writes[name] = self._writes.get(name, 0) + 1
        return fact

    def get(self, name: str) -> Any:
        return self._facts[name].value

    def origin(self, name: str) -> Fact | None:
        return self._facts.get(name)

    def writes(self, name: str) -> int:
        return self._writes.get(name, 0)

    def __contains__(self, name: object) -> bool:
        return name in self._facts

    def __iter__(self) -> Iterator[str]:
        return iter(self.names())

    def __len__(self) -> int:
        return len(self._facts)

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._facts))

    def missing(self, kind: StepKind) -> tuple[str, ...]:
        return tuple(sorted(kind.needs - set(self._facts)))

    def bind(self, kind: StepKind) -> dict[str, Any]:
        return self.take(kind.needs)

    def take(self, names: Iterable[str]) -> dict[str, Any]:
        return {name: self._facts[name].value for name in sorted(names)}

    def ground(self) -> dict[str, str]:
        return {name: fact.told() for name, fact in sorted(self._facts.items())}


def unreachable() -> tuple[str, ...]:
    given: set[str] = set().union(*(kind.gives for kind in STEPS))
    needed: set[str] = set().union(*(kind.needs for kind in STEPS))
    return tuple(sorted(needed - given))


__all__ = ["BEFORE", "NAMES", "Fact", "Facts", "size_of", "unreachable"]
