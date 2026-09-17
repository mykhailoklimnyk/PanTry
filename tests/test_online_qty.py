from __future__ import annotations

from decimal import Decimal

from komora.agent.basket import ONLINE_HABIT_MIN, HistoryItem


def _water(*, till: list[int], online: list[int]) -> HistoryItem:
    item = HistoryItem(
        lager_id="w", name="Вода мінеральна", unit="шт", receipts=len(till) + len(online)
    )
    item.qty_total = Decimal(sum(till) + sum(online))
    item.recent_receipts = item.receipts
    item.qty_recent = item.qty_total
    item.online_qtys = [Decimal(q) for q in online]
    return item


def test_two_deliveries_by_the_block_beat_a_dozen_single_bottles_at_the_till() -> None:
    assert _water(till=[1] * 12, online=[6, 6]).typical_qty == 6


def test_a_single_delivery_is_not_a_habit_yet() -> None:
    assert _water(till=[1] * 12, online=[6]).typical_qty == 1
    assert ONLINE_HABIT_MIN == 2


def test_the_delivery_habit_is_a_median_not_a_mean() -> None:
    assert _water(till=[], online=[6, 6, 24]).typical_qty == 6
