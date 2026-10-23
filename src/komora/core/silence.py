from __future__ import annotations

from dataclasses import dataclass

MIN_ASKED = 5

MUTE_SHARE = 2 / 3


@dataclass(frozen=True, slots=True)
class Silence:

    asked: int = 0
    empty: int = 0

    @property
    def share(self) -> float:
        return self.empty / self.asked if self.asked else 0.0

    def plus(self, asked: int, empty: int) -> Silence:
        return Silence(asked=self.asked + asked, empty=self.empty + empty)

    def healed(self, count: int) -> Silence:
        return Silence(asked=self.asked, empty=max(0, self.empty - count))


def is_mute(silence: Silence) -> bool:
    return silence.asked >= MIN_ASKED and silence.share > MUTE_SHARE


def mute_note(silence: Silence) -> str:
    return (
        f"полиця не відповіла на {silence.empty} запитів з {silence.asked} — "
        "це не маленький кошик, а мовчання магазину; спробуй ще раз за хвилину"
    )


__all__ = ["MIN_ASKED", "MUTE_SHARE", "Silence", "is_mute", "mute_note"]
