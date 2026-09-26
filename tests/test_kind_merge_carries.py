from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from komora.agent.basket import HistoryItem, arrived_note, history_kinds

NOW = datetime(2026, 9, 20, 12, tzinfo=UTC)


def _sku(
    name: str,
    *,
    day: int,
    lager_id: str = "1",
    **fields: object,
) -> HistoryItem:
    moment = datetime(2026, 9, day, 10, tzinfo=UTC)
    return HistoryItem(
        lager_id=lager_id,
        name=name,
        unit="шт",
        receipts=1,
        qty_total=Decimal(1),
        recent_receipts=1,
        qty_recent=Decimal(1),
        moments=[moment],
        **fields,  # type: ignore[arg-type]
    )


def test_the_merged_kind_keeps_the_online_quantities():
    kinds = history_kinds(
        [
            _sku("Вода Моршинська 1,5 л", day=10, online_qtys=[Decimal(6)]),
            _sku("Вода Моршинська негазована", day=12, online_qtys=[Decimal(6)]),
        ],
        now=NOW,
    )
    assert len(kinds) == 1
    assert kinds[0].online_qtys == [Decimal(6), Decimal(6)]
    assert kinds[0].typical_qty == 6


def test_the_merged_kind_keeps_the_latest_delivery():
    fresh = datetime(2026, 9, 19, 10, tzinfo=UTC)
    kinds = history_kinds(
        [
            _sku("Хліб Київський", day=10, online_last=datetime(2026, 9, 10, 10, tzinfo=UTC)),
            _sku("Хліб Київський нарізний", day=19, online_last=fresh),
        ],
        now=NOW,
    )
    assert kinds[0].online_last == fresh
    assert arrived_note(kinds[0], 1) == "приїхало вчора"


def test_the_merged_kind_keeps_the_freshest_price():
    kinds = history_kinds(
        [
            _sku(
                "Сир Комо",
                day=10,
                price=Decimal("80.00"),
                price_at=datetime(2026, 9, 10, 10, tzinfo=UTC),
            ),
            _sku(
                "Сир Комо твердий",
                day=18,
                price=Decimal("99.00"),
                price_at=datetime(2026, 9, 18, 10, tzinfo=UTC),
            ),
        ],
        now=NOW,
    )
    assert kinds[0].price == Decimal("99.00")
    assert kinds[0].typical_cost == Decimal("99.00")


def test_the_older_price_does_not_overwrite_the_fresher_one():
    kinds = history_kinds(
        [
            _sku(
                "Сир Комо твердий",
                day=18,
                price=Decimal("99.00"),
                price_at=datetime(2026, 9, 18, 10, tzinfo=UTC),
            ),
            _sku(
                "Сир Комо",
                day=10,
                price=Decimal("80.00"),
                price_at=datetime(2026, 9, 10, 10, tzinfo=UTC),
            ),
        ],
        now=NOW,
    )
    assert kinds[0].price == Decimal("99.00")


def test_the_named_cycle_brings_its_author_along():
    kinds = history_kinds(
        [
            _sku("Серветки Ruta", day=10, said_cycle=20, said_from="папір туалетний"),
            _sku("Серветки Ruta сухі", day=12, said_cycle=30, said_from="рушники паперові"),
        ],
        now=NOW,
    )
    assert kinds[0].said_cycle == 20
    assert kinds[0].said_from == "папір туалетний"


def test_the_guests_own_word_wins_a_tie():
    kinds = history_kinds(
        [
            _sku("Серветки Ruta", day=10, said_cycle=20, said_from="папір туалетний"),
            _sku("Серветки Ruta сухі", day=12, said_cycle=20, said_from=None),
        ],
        now=NOW,
    )
    assert kinds[0].said_cycle == 20
    assert kinds[0].said_from is None


def test_a_single_sku_kind_keeps_its_fields_too():
    kinds = history_kinds(
        [
            _sku(
                "Кава Jacobs",
                day=19,
                online_last=datetime(2026, 9, 19, 10, tzinfo=UTC),
                online_qtys=[Decimal(2), Decimal(2)],
                price=Decimal("250.00"),
                price_at=datetime(2026, 9, 19, 10, tzinfo=UTC),
                said_cycle=14,
                said_from="чай чорний",
            )
        ],
        now=NOW,
    )
    row = kinds[0]
    assert row.online_last is not None
    assert row.online_qtys == [Decimal(2), Decimal(2)]
    assert row.price == Decimal("250.00")
    assert row.price_at is not None
    assert row.said_from == "чай чорний"
