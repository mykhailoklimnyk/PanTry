from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from komora.agent.basket import HistoryItem, manual_item, receipts_pantry

NOW = datetime(2026, 8, 26, 12, tzinfo=UTC)


def _kind(name: str, *, cycle: int, since: int, usual: int, unit: str = "шт") -> HistoryItem:
    days = [since + cycle * step for step in range(4)]
    return HistoryItem(
        lager_id=name,
        name=name,
        unit=unit,
        receipts=len(days),
        qty_total=Decimal(usual * len(days)),
        recent_receipts=len(days),
        qty_recent=Decimal(usual * len(days)),
        moments=[NOW - timedelta(days=day) for day in days],
    )


def test_a_zero_in_the_pantry_always_means_it_ran_out():
    kinds = [
        _kind(f"Вид {cycle}-{since}-{usual}", cycle=cycle, since=since, usual=usual)
        for cycle in (2, 7, 14, 30)
        for since in (0, 1, 3, 6, 13, 29, 60)
        for usual in (1, 2, 4, 9)
    ]

    rows = receipts_pantry(kinds, now=NOW, limit=len(kinds))

    assert rows, "сітка не дала жодного рядка -- перевіряти нема чого"
    for row in rows:
        if row.qty is not None and row.qty == 0:
            assert row.running_out, (
                f"«{row.label}» показує нуль, не будучи «закінчилось»: "
                "два різні стани виглядають однаково"
            )


def test_a_row_that_still_has_time_never_shows_zero():
    mid_cycle = [
        _kind("Молоко", cycle=8, since=2, usual=4),
        _kind("Кава", cycle=30, since=1, usual=2),
        _kind("Порошок", cycle=60, since=30, usual=9),
    ]

    rows = receipts_pantry(mid_cycle, now=NOW, limit=len(mid_cycle))

    assert len(rows) == 3
    for row in rows:
        assert not row.running_out
        assert row.qty is None or row.qty > 0, "число посеред циклу не буває нулем"


def test_a_hand_written_row_has_no_quantity_at_all():
    row = manual_item("Пиво Стела", [], now=NOW)

    assert row is not None
    assert row.qty is None
    assert row.usual_qty is None
    assert row.source == "manual"


def test_a_hand_written_row_that_the_receipts_know_follows_the_same_rule():
    known = [_kind("Пиво Львівське", cycle=7, since=21, usual=2)]

    row = manual_item("Пиво Львівське", known, now=NOW)

    assert row is not None
    assert row.running_out, "три цикли мовчання -- це «закінчилось»"
    assert row.qty is None or row.qty == 0
