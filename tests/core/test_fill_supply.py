from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from komora.agent.basket import SILENT_RANK, HistoryItem, fill_pool

NOW = datetime(2026, 9, 6, tzinfo=UTC)


def _kind(name: str, *, days: list[int], price: str = "50") -> HistoryItem:
    moments = [NOW - timedelta(days=day) for day in days]
    return HistoryItem(
        lager_id=name,
        name=name,
        unit="шт",
        receipts=len(days),
        qty_total=Decimal(len(days)),
        recent_receipts=len(days),
        qty_recent=Decimal(len(days)),
        moments=moments,
        price=Decimal(price),
        price_at=max(moments),
    )


def _cat_food() -> HistoryItem:
    return _kind("Корм котячий", days=[30, 150, 270, 390], price="300")


def _uneven() -> HistoryItem:
    return _kind("Печиво нерівне", days=[10, 12, 17, 77])


def _deep_stock() -> HistoryItem:
    return _kind("Сіль велика", days=[40, 290, 540, 790])


def _abandoned() -> HistoryItem:
    return _kind("Печиво кинуте", days=[13, 19, 25, 31])


def _order(*items: HistoryItem) -> list[str]:
    pool = fill_pool(list(items), moment=NOW, soon=3).pool
    return [item.key for item in sorted(pool, key=lambda c: (c.rank, c.key))]


def test_the_stocked_kind_stands_behind_the_one_whose_interval_has_passed():
    assert _order(_cat_food(), _uneven()) == ["Печиво нерівне", "Корм котячий"]


def test_the_supply_layer_does_not_leak_past_the_abandoned_one():
    pool = {item.key: item for item in fill_pool([_deep_stock()], moment=NOW, soon=3).pool}

    assert pool["Сіль велика"].rank < SILENT_RANK
    assert _order(_deep_stock(), _abandoned()) == ["Сіль велика", "Печиво кинуте"]


def test_the_row_says_it_was_added_to_reach_the_named_sum():
    pool = fill_pool([_cat_food()], moment=NOW, soon=3).pool

    assert pool[0].why == "докинуто до суми: береш раз на ~120 дн, вдома ще ~90 дн"


def test_the_weakest_layer_says_it_too():
    pool = fill_pool([_uneven()], moment=NOW, soon=3).pool

    assert pool[0].why == "докинуто до суми: береш нерівно, останній раз 10 дн тому"


def test_a_kind_bought_on_a_single_day_goes_to_the_tail():
    one_day = _kind("Разове", days=[5, 5, 5])

    assert _order(one_day, _uneven()) == ["Печиво нерівне", "Разове"]
