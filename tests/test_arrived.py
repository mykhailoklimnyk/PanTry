from __future__ import annotations

from datetime import UTC, datetime, timedelta

from komora.agent.basket import ARRIVED_DAYS, HistoryItem, arrived_note, kind_row

NOW = datetime(2026, 9, 10, 12, tzinfo=UTC)


def _milk(*, last_days_ago: int, online: bool, online_older: bool = False) -> HistoryItem:
    moments = [NOW - timedelta(days=last_days_ago + gap) for gap in (14, 7, 0)]
    item = HistoryItem(lager_id="1", name="Молоко Яготинське 2,5%", unit="шт", receipts=3)
    item.moments = moments
    if online:
        item.online_last = moments[0] if online_older else moments[-1]
    return item


def test_a_delivery_from_yesterday_says_so_on_the_row() -> None:
    row = kind_row(_milk(last_days_ago=1, online=True), moment=NOW)

    assert row is not None
    assert row.arrived == "приїхало вчора"


def test_a_delivery_from_today_is_named_today() -> None:
    assert arrived_note(_milk(last_days_ago=0, online=True), 0) == "приїхало сьогодні"


def test_a_purchase_at_the_till_does_not_arrive() -> None:
    row = kind_row(_milk(last_days_ago=1, online=False), moment=NOW)

    assert row is not None
    assert row.arrived is None


def test_beyond_the_ceiling_it_is_no_longer_news() -> None:
    assert arrived_note(_milk(last_days_ago=ARRIVED_DAYS, online=True), ARRIVED_DAYS) == (
        f"приїхало {ARRIVED_DAYS} дн тому"
    )
    assert (
        arrived_note(_milk(last_days_ago=ARRIVED_DAYS + 1, online=True), ARRIVED_DAYS + 1) is None
    )


def test_an_older_delivery_behind_a_newer_receipt_is_not_an_arrival() -> None:
    assert arrived_note(_milk(last_days_ago=1, online=True, online_older=True), 1) is None


def test_without_a_date_nothing_is_claimed() -> None:
    assert arrived_note(_milk(last_days_ago=1, online=True), None) is None
