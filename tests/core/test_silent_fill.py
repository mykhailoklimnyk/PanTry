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


def _abandoned() -> HistoryItem:
    return _kind("Печиво кинуте", days=[116, 122, 128, 134])


def _due() -> HistoryItem:
    return _kind("Молоко живе", days=[9, 16, 23, 30])


def test_the_abandoned_kind_stands_behind_the_living_one():
    pool = fill_pool([_abandoned(), _due()], moment=NOW, soon=3).pool
    order = [item.key for item in sorted(pool, key=lambda c: (c.rank, c.key))]

    assert order == ["Молоко живе", "Печиво кинуте"]


def test_the_deeper_the_silence_the_lower_it_stands():
    deep = _kind("Кинуте давно", days=[300, 306, 312, 318])
    shallow = _kind("Кинуте недавно", days=[40, 46, 52, 58])

    pool = fill_pool([deep, shallow], moment=NOW, soon=3).pool
    order = [item.key for item in sorted(pool, key=lambda c: (c.rank, c.key))]

    assert order == ["Кинуте недавно", "Кинуте давно"]


def test_the_silence_is_measured_in_cycles_and_not_in_days():
    late = _kind("Рідкий і спізнився", days=[200, 290, 380, 470])
    gone = _kind("Частий і кинутий", days=[100, 103, 106, 109])

    pool = fill_pool([late, gone], moment=NOW, soon=3).pool
    ranks = {item.key: item.rank for item in pool}
    order = [item.key for item in sorted(pool, key=lambda c: (c.rank, c.key))]

    assert all(rank >= SILENT_RANK for rank in ranks.values())
    assert order == ["Рідкий і спізнився", "Частий і кинутий"]
    assert ranks["Рідкий і спізнився"] == SILENT_RANK + 2
    assert ranks["Частий і кинутий"] == SILENT_RANK + 33


def test_the_ordering_axis_is_the_one_the_module_declares():
    gone = _kind("Частий і кинутий", days=[100, 103, 106, 109])
    beat = gone.rhythm(NOW)

    assert beat.silence is not None
    pool = fill_pool([gone], moment=NOW, soon=3).pool

    assert pool[0].rank == SILENT_RANK + round(beat.silence)


def test_the_abandoned_kind_says_silence_and_not_a_cycle():
    pool = fill_pool([_abandoned()], moment=NOW, soon=3).pool

    assert len(pool) == 1
    assert pool[0].why.startswith("давно не брав")
    assert "закінчилось за циклом" not in pool[0].why


def test_the_abandoned_kind_is_not_thrown_out():
    pool = fill_pool([_abandoned()], moment=NOW, soon=3).pool

    assert [item.key for item in pool] == ["Печиво кинуте"]
    assert pool[0].rank >= SILENT_RANK


def test_a_living_kind_keeps_its_place_at_the_head():
    pool = fill_pool([_due()], moment=NOW, soon=3).pool

    assert pool[0].rank < 0
    assert pool[0].why == "закінчилось за циклом"
