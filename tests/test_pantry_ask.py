from __future__ import annotations

from datetime import UTC, datetime, timedelta

from komora.agent.basket import HistoryItem, Naming, kind_row
from komora.core.cycles import Keeps, Trust
from komora.db.facts import Facts

NOW = datetime(2026, 9, 7, tzinfo=UTC)

NAMES = {"паляничка київська": Naming(intent="паляничка")}


def _bread(*, days_apart: int, said_cycle: int | None = None) -> HistoryItem:
    return HistoryItem(
        lager_id="1",
        name="Паляничка Київська",
        unit="шт",
        receipts=4,
        moments=[NOW - timedelta(days=days_apart * step) for step in (3, 2, 1)],
        said_cycle=said_cycle,
        keeps=Keeps.DAYS,
        rhythm_lies=True,
    )


SENSE = {"паляничка": Facts(sanity="хліб їдять нерівно", rhythm_lies=True)}


def test_a_kind_the_guest_already_answered_is_not_asked_again() -> None:
    row = kind_row(_bread(days_apart=32, said_cycle=3), moment=NOW, names=NAMES, sense=SENSE)

    assert row is not None
    assert row.trust == Trust.SAID
    assert row.ask is False


def test_a_kind_we_see_only_a_part_of_is_not_asked_at_all() -> None:
    row = kind_row(_bread(days_apart=32), moment=NOW, names=NAMES, sense=SENSE)

    assert row is not None
    assert row.trust == Trust.NOT_RHYTHM
    assert row.ask is False
    assert "не тільки тут" in (row.state or "")


def test_a_kind_whose_rhythm_lies_within_its_shelf_life_still_asks() -> None:
    row = kind_row(_bread(days_apart=3), moment=NOW, names=NAMES, sense=SENSE)

    assert row is not None
    assert row.trust == Trust.NOT_RHYTHM
    assert row.ask is True
    assert "не дорівнює витрачанню" in (row.state or "")
