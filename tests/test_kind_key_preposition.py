from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from komora.agent.basket import HistoryItem, kind_key, receipts_pantry

NOW = datetime(2026, 9, 7, 12, 0, tzinfo=UTC)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("Сендвіч з баликом", "Сендвіч з бужениною"),
        ("Засіб для миття посуду Fairy Лимон", "Засіб для чищення Cillit Bang"),
        ("Пакет для катання Сільпо 18 кг", "Пакет для м'яса Сільпо 30*50см"),
    ],
)
def test_a_preposition_does_not_glue_two_different_kinds(left: str, right: str) -> None:
    assert kind_key(left) != kind_key(right)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("Корм для котів Whiskas з тунцем в желе", "Корм для котів Gourmet Gold паштет"),
        ("Гель для душу DeepFresh Caramel", "Гель для душу Savon De Royall"),
        ("Фільтри для чаю «Премія» в чайник", "Фільтри для чаю Премія в чашку"),
        ("Окунь без голови С/м", "Окунь без голови свіжоморожений"),
    ],
)
def test_the_cut_does_not_break_a_group_that_was_right(left: str, right: str) -> None:
    assert kind_key(left) == kind_key(right)


def test_a_name_without_a_preposition_keeps_the_two_word_key() -> None:
    assert kind_key("Молоко Яготинське 2.5%") == kind_key("Молоко Яготинське добірне")
    assert kind_key("Вода мінеральна Моршинська") == "вода мінеральна"


def test_a_one_word_name_stays_one_word() -> None:
    assert kind_key("Хліб") == "хліб"


def test_a_name_that_is_only_a_kind_and_a_preposition_does_not_reach_past_its_end() -> None:
    assert kind_key("Сендвіч з") == "сендвіч з"


def test_a_row_without_a_kind_label_shows_the_receipt_not_the_merge_key() -> None:
    receipt = "Томат La Parcela Черрі Angello"
    (row,) = receipts_pantry(
        [
            HistoryItem(
                lager_id="7",
                name=receipt,
                unit="уп",
                receipts=3,
                moments=[NOW - timedelta(days=day) for day in (21, 14, 7)],
            )
        ],
        now=NOW,
    )
    assert row.label == receipt
    assert row.named is False
    assert kind_key(receipt) == "томат la"


def test_a_forecast_stops_hedging_when_the_date_already_answers() -> None:
    fresh = _row_with_said_cycle(days_since=6, cycle=3)
    stale = _row_with_said_cycle(days_since=456, cycle=3)
    assert "мабуть, закінчилось" in fresh.state
    assert "мабуть" not in stale.state
    assert "закінчилось" in stale.state


def _row_with_said_cycle(*, days_since: int, cycle: int):
    from komora.agent.basket import kind_row

    item = HistoryItem(
        lager_id="9",
        name="Морозиво Крем-брюле",
        unit="шт",
        receipts=4,
        moments=[NOW - timedelta(days=days_since + step) for step in (0, cycle, cycle * 2)],
        said_cycle=cycle,
    )
    row = kind_row(item, moment=NOW)
    assert row is not None
    return row


def test_a_compound_preposition_keeps_rum_and_sparkling_wine_apart() -> None:
    from komora.agent.basket import kind_key

    rum = kind_key("Напій на основі рому Oakheart Original 35%")
    wine = kind_key("Напій на основі вина Latinium Sparkling білий напівсолодкий")
    assert rum != wine
    assert rum == kind_key("Напій на основі рому Bacardi Oakheart Original 35%")


def test_the_compound_cut_does_not_break_the_keys_that_already_worked() -> None:
    from komora.agent.basket import kind_key

    assert kind_key("Сендвіч з баликом") != kind_key("Сендвіч з бужениною")
    assert kind_key("Корм для котів Whiskas") == kind_key("Корм для котів Purina")
    assert kind_key("Гель для душу Fa") != kind_key("Гель для миття Fairy")
    assert kind_key("Вода мінеральна Поляна Квасова") == kind_key("Вода мінеральна Моршинська")
    assert kind_key("Хліб") == "хліб"
