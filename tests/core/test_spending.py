from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from komora.core.spending import receipt_moment, spent_since, week_start


def receipt(created: str | None, total: float | None) -> dict:
    order: dict = {}
    if created is not None:
        order["createdAt"] = created
    if total is not None:
        order["sumReg"] = total
    return order


def test_week_starts_on_monday():
    assert week_start(datetime(2026, 8, 18, 23, 47, 31, 153318)) == datetime(2026, 8, 17)


def test_monday_is_its_own_week_start():
    assert week_start(datetime(2026, 8, 17, 0, 30)) == datetime(2026, 8, 17)


def test_sunday_belongs_to_the_week_that_started_before_it():
    assert week_start(datetime(2026, 8, 23, 21, 5)) == datetime(2026, 8, 17)


def test_the_sum_comes_from_the_receipt_not_from_multiplying_prices():
    orders = [
        receipt("2026-08-17T09:00:00", 597.66),
        receipt("2026-08-18T20:09:01", 402.34),
    ]
    assert spent_since(orders, datetime(2026, 8, 17)) == (Decimal("1000.00"), 2)


def test_receipts_before_the_week_do_not_count():
    orders = [
        receipt("2026-08-16T18:00:00", 500),
        receipt("2026-08-17T08:00:00", 120),
    ]
    assert spent_since(orders, datetime(2026, 8, 17)) == (Decimal("120"), 1)


def test_a_receipt_at_the_very_start_of_the_week_counts():
    orders = [receipt("2026-08-17T00:00:00", 250)]
    assert spent_since(orders, datetime(2026, 8, 17)) == (Decimal("250"), 1)


def test_a_receipt_without_a_sum_is_not_counted_as_zero():
    orders = [receipt("2026-08-17T08:00:00", None), receipt("2026-08-17T09:00:00", 80)]
    assert spent_since(orders, datetime(2026, 8, 17)) == (Decimal("80"), 1)


def test_a_receipt_without_a_time_is_not_counted():
    orders = [receipt(None, 999), receipt("не дата", 999)]
    assert spent_since(orders, datetime(2026, 8, 17)) == (Decimal(0), 0)


def test_the_receipt_time_is_local_and_stays_local():
    assert receipt_moment(receipt("2026-08-16T20:09:01", 1)) == datetime(2026, 8, 16, 20, 9, 1)
    assert receipt_moment(receipt("2026-08-16T20:09:01+00:00", 1)) == datetime(
        2026, 8, 16, 20, 9, 1
    )


def test_an_empty_week_is_zero_with_zero_receipts():
    assert spent_since([], datetime(2026, 8, 17)) == (Decimal(0), 0)
