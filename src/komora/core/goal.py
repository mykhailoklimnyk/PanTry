from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

NAMED = 3


@dataclass(frozen=True, slots=True)
class Duty:

    name: str
    ok: bool
    why: str = ""
    """Порожньо -- виконане. Інакше причина СЛОВАМИ, з числом."""
    fatal: bool = True
    """Чи невиконане зупиняє прогін.

    Не всі зобов'язання рівні, і плутати їх коштує продукту. Загублений
    намір -- НАША поломка: законної причини в неї немає, тож кошик віддавати
    не можна. А «рішення відбулось» описує ЯКІСТЬ прогону: модель мовчить --
    кошик збирається за історією, і це задокументований відкат (#151), а не
    поломка. Відмова на ньому вимкнула б продукт рівно тоді, коли він
    свідомо працює без моделі."""


@dataclass(frozen=True, slots=True)
class Goal:

    duties: tuple[Duty, ...]

    @property
    def ok(self) -> bool:
        return all(duty.ok for duty in self.duties)

    @property
    def unmet(self) -> tuple[Duty, ...]:
        return tuple(duty for duty in self.duties if not duty.ok)

    @property
    def broken(self) -> tuple[Duty, ...]:
        return tuple(duty for duty in self.unmet if duty.fatal)

    def refusal(self) -> str:
        return "кошик не зібрано: " + "; ".join(duty.why or duty.name for duty in self.broken)

    def note(self) -> str:
        if self.ok:
            return "мета досягнута — " + "; ".join(duty.name for duty in self.duties)
        return f"мета НЕ досягнута: {len(self.unmet)} з {len(self.duties)} — " + "; ".join(
            duty.why or duty.name for duty in self.unmet
        )

    def told(self) -> dict[str, str]:
        return {duty.name: "так" if duty.ok else (duty.why or "ні") for duty in self.duties}


def homeless(intents: Sequence[str], addresses: Mapping[str, Iterable[str]]) -> tuple[str, ...]:
    placed: set[str] = set()
    for names in addresses.values():
        placed |= set(names)
    return tuple(intent for intent in dict.fromkeys(intents) if intent not in placed)


def basket_goal(
    *,
    intents: Sequence[str],
    addresses: Mapping[str, Iterable[str]],
    decided: bool,
    model: bool,
) -> Goal:
    lost = homeless(intents, addresses)
    duties = [
        Duty(
            name="кожен намір має адресу",
            ok=not lost,
            why=(
                ""
                if not lost
                else f"загублено {len(lost)}: "
                + ", ".join(lost[:NAMED])
                + ("…" if len(lost) > NAMED else "")
            ),
        )
    ]
    if model:
        duties.append(
            Duty(
                name="рішення відбулось",
                ok=decided,
                why="" if decided else "агент не дійшов до вибору",
                fatal=False,
            )
        )
    return Goal(duties=tuple(duties))


def resolution_goal(intents: Sequence[str], *, addressed: Mapping[str, Iterable[str]]) -> Goal:
    left = homeless(intents, addressed)
    return Goal(
        duties=(
            Duty(
                name="кожен намір дійшов до рядка або питання",
                ok=not left,
                why="" if not left else f"без рядка {len(left)}: " + _some(left),
                fatal=False,
            ),
        )
    )


@dataclass(frozen=True, slots=True)
class Row:

    label: str
    named: bool
    """Мітку виду дав агент, а не перші два слова чека (#151)."""
    counted: bool
    """Є ЧИСЛО: доведений цикл, смуга, «ще ~N дн»."""
    explained: bool
    """Є РЕЧЕННЯ, чому числа немає (#305)."""
    asks: bool
    """Саме тут слово гостя змінить рядок найбільше: ритм бреше, а свого
    числа гість не називав."""


def pantry_goal(rows: Sequence[Row], *, questions: Sequence[str], closed: bool = False) -> Goal:
    silent = [row.label for row in rows if not row.counted and not row.explained]
    nameless = [row.label for row in rows if not row.named]
    asking = [row.label for row in rows if row.asks]
    unasked = [] if closed or questions else asking
    return Goal(
        duties=(
            Duty(
                name="кожен рядок каже число або речення",
                ok=not silent,
                why="" if not silent else f"мовчать {len(silent)}: " + _some(silent),
                fatal=False,
            ),
            Duty(
                name="неназвані названі або перелічені",
                ok=not nameless,
                why=("" if not nameless else f"без мітки виду {len(nameless)}: " + _some(nameless)),
                fatal=False,
            ),
            Duty(
                name=("питання цього відкриття почуті" if closed else "питання гостю названі"),
                ok=not unasked,
                why=(
                    ""
                    if not unasked
                    else f"просять слова гостя {len(unasked)}, а питання не поставлено: "
                    + _some(unasked)
                ),
                fatal=False,
            ),
        )
    )


def _some(labels: Sequence[str]) -> str:
    return ", ".join(labels[:NAMED]) + ("…" if len(labels) > NAMED else "")


def handover_goal(
    *,
    written: Sequence[str],
    planned: Sequence[str],
    cart_id: str | None,
    slot_written: str | None,
    slot_planned: str | None,
    reread: bool,
) -> Goal:
    missing = [article for article in dict.fromkeys(planned) if article not in set(written)]
    return Goal(
        duties=(
            Duty(
                name="кошик існує у відповіді",
                ok=bool(cart_id),
                why="" if cart_id else "кошика немає у відповіді після запису",
            ),
            Duty(
                name="кошик перечитано після запису",
                ok=reread,
                why="" if reread else "запис не перечитано — стан кошика невідомий",
            ),
            Duty(
                name="слот кошика дорівнює слоту плану",
                ok=slot_written == slot_planned,
                why=(
                    ""
                    if slot_written == slot_planned
                    else f"кошик стоїть на {slot_written or 'без слота'}, "
                    f"а план збирався на {slot_planned or 'без слота'}"
                ),
            ),
            Duty(
                name="записане дорівнює запланованому",
                ok=not missing,
                why=(
                    ""
                    if not missing
                    else f"не доїхало {len(missing)}: "
                    + ", ".join(missing[:NAMED])
                    + ("…" if len(missing) > NAMED else "")
                ),
            ),
        )
    )


__all__ = [
    "NAMED",
    "Duty",
    "Goal",
    "Row",
    "basket_goal",
    "handover_goal",
    "homeless",
    "pantry_goal",
    "resolution_goal",
]
