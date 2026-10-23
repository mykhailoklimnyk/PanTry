from __future__ import annotations

from decimal import Decimal

from komora.agent.basket import qty_for_api

PIECE = {"weighted": False, "displayRatio": "шт", "step": 1}
WEIGHED = {"weighted": True, "displayRatio": "кг", "step": 0.2}


def test_a_fractional_piece_becomes_whole():
    assert qty_for_api(Decimal("1.3"), PIECE) == 1


def test_a_whole_piece_stays_itself():
    assert qty_for_api(Decimal(3), PIECE) == 3


def test_rounding_goes_down_and_not_up():
    assert qty_for_api(Decimal("2.7"), PIECE) == 2


def test_less_than_one_piece_is_still_one():
    assert qty_for_api(Decimal("0.5"), PIECE) == 1


def test_the_weighed_quantity_is_not_touched():
    assert qty_for_api(Decimal("0.365"), WEIGHED) == 0.365


def test_a_whole_weighed_quantity_stays_an_int():
    assert qty_for_api(Decimal(3), WEIGHED) == 3
    assert isinstance(qty_for_api(Decimal(3), WEIGHED), int)


def test_the_ratio_wins_over_the_flag():
    nectarine = {"weighted": False, "displayRatio": "кг", "step": 0.4}

    assert qty_for_api(Decimal("0.4"), nectarine) == 0.4


def test_a_card_without_fields_is_treated_as_pieces():
    assert qty_for_api(Decimal("1.3"), {}) == 1
