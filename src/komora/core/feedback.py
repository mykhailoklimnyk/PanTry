from __future__ import annotations

from enum import StrEnum


class Changes(StrEnum):

    APPROVED = "approvedChanges"
    """«Замініть на схожі товари» — збирач міняє на свій розсуд."""
    DISAPPROVED = "disapprovedChanges"
    """«Не збирайте те, що потребує уточнень» — глобальна заборона міняти."""


class Contacts(StrEnum):

    CALL = "call"
    DO_NOT_CALL = "doNotCall"


def _parsed[T: StrEnum](raw: object, kind: type[T]) -> T | None:
    if not isinstance(raw, str):
        return None
    try:
        return kind(raw)
    except ValueError:
        return None


def changes_of(raw: object) -> Changes | None:
    return _parsed(raw, Changes)


def contacts_of(raw: object) -> Contacts | None:
    return _parsed(raw, Contacts)


def collector_swaps(changes: Changes | None) -> bool | None:
    if changes is None:
        return None
    return changes is not Changes.DISAPPROVED


def reach_note(collector_acts: bool | None) -> str:
    ours = "до слота заміню сам — ре-валідація галочки не питає"
    if collector_acts is False:
        return (
            "мандат біля полиці не спрацює: у замовленні стоїть "
            f"«не збирайте те, що потребує уточнень»; {ours}"
        )
    if collector_acts is None:
        return f"чи прочитає мандат збирач — не звіряли, галочка замін не читалась; {ours}"
    return f"мандати ляжуть у comment збирачу; {ours}"
