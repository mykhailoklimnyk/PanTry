from decimal import Decimal

import pytest

from komora.core.packaging import (
    is_sold_by_weight,
    parse_energy,
    parse_pack_weight,
    price_per_100g,
    quantize_to_step,
    receipt_unit,
    sale_step,
    sale_unit,
)


@pytest.mark.parametrize(
    ("text", "grams"),
    [
        ("Молоко Селянське 350г", "350"),
        ("Вода Карпатська Джерельна 0,95л", "950"),
        ("Крупа гречана 1 кг", "1000"),
        ("Йогурт 500 мл", "500"),
        ("Печиво 200 g", "200"),
    ],
)
def test_weight_is_parsed_from_the_name(text, grams):
    assert parse_pack_weight(text) == Decimal(grams)


def test_multipack_counts_the_whole_pack():
    assert parse_pack_weight("Молоко 2х200 г") == Decimal(400)
    assert parse_pack_weight("Вода 6x1,5л") == Decimal(9000)


def test_latin_and_cyrillic_multiplication_sign_both_work():
    assert parse_pack_weight("Сік 3x1л") == parse_pack_weight("Сік 3х1л")


def test_missing_weight_is_none_not_zero():
    assert parse_pack_weight("Молоко ультрапастеризоване Селянське 1%") is None
    assert parse_pack_weight("") is None
    assert parse_pack_weight(None) is None


def test_percentage_is_not_mistaken_for_weight():
    assert parse_pack_weight("Сметана 15%") is None


def test_energy_field_splits_kcal_and_kj():
    energy = parse_energy("54/225")
    assert energy is not None
    assert energy.kcal == Decimal(54)
    assert energy.kj == Decimal(225)


def test_energy_tolerates_spaces_and_comma():
    energy = parse_energy("54,5 / 225")
    assert energy is not None and energy.kcal == Decimal("54.5")


def test_single_number_is_read_as_kcal():
    energy = parse_energy("120")
    assert energy is not None and energy.kcal == Decimal(120) and energy.kj is None


def test_no_energy_is_none():
    assert parse_energy(None) is None
    assert parse_energy("") is None


def test_ratio_wins_over_the_weighted_flag():
    assert is_sold_by_weight(weighted=False, ratio="кг", step=Decimal("0.4")) is True


def test_weighted_flag_alone_is_enough():
    assert is_sold_by_weight(weighted=True, ratio=None, step=None) is True


def test_fractional_step_implies_weight():
    assert is_sold_by_weight(weighted=False, ratio=None, step=Decimal("0.35")) is True


def test_plain_piece_goods_are_not_weighted():
    assert is_sold_by_weight(weighted=False, ratio="шт", step=Decimal(1)) is False


def test_quantity_rounds_up_to_the_step():
    assert quantize_to_step(Decimal("0.5"), Decimal("0.35")) == Decimal("0.70")
    assert quantize_to_step(Decimal("0.35"), Decimal("0.35")) == Decimal("0.35")


def test_no_step_leaves_quantity_alone():
    assert quantize_to_step(Decimal("1.7"), None) == Decimal("1.7")
    assert quantize_to_step(Decimal("1.7"), Decimal(0)) == Decimal("1.7")


def test_multipack_with_an_asterisk():
    assert parse_pack_weight("16*8,5г") == Decimal("136.0")
    assert parse_pack_weight("2х200 г") == Decimal("400")
    assert parse_pack_weight("6x1,5л") == Decimal("9000")


def test_price_per_100g_from_the_pack():
    assert price_per_100g(
        Decimal("39.99"), weighted=False, ratio="900г", step=Decimal(1)
    ) == Decimal("39.99") * 100 / 900


def test_weighted_price_is_already_per_kilogram():
    assert price_per_100g(
        Decimal("272.46"), weighted=True, ratio="100г", step=Decimal("0.4")
    ) == Decimal("27.246")


def test_piece_goods_have_no_common_unit():
    assert price_per_100g(Decimal("89"), weighted=False, ratio="10шт", step=Decimal(1)) is None
    assert price_per_100g(Decimal("89"), weighted=False, ratio=None, step=None) is None


def test_no_price_no_unit_price():
    assert price_per_100g(None, weighted=False, ratio="900г", step=None) is None
    assert price_per_100g(Decimal(0), weighted=False, ratio="900г", step=None) is None


def test_the_receipt_unit_speaks_for_the_pantry_row():
    assert receipt_unit("г") == "кг"
    assert receipt_unit("шт") == "шт"
    assert receipt_unit("л") == "л"


def test_a_pack_size_in_the_receipt_is_a_pack():
    assert receipt_unit("100г") == "уп"
    assert receipt_unit("1,5л") == "уп"


def test_a_silent_receipt_names_no_unit():
    assert receipt_unit(None) == ""
    assert receipt_unit("   ") == ""


def test_a_weighed_good_is_sold_in_kilograms():
    assert sale_unit(weighted=True, ratio="100г", step=Decimal("0.4")) == "кг"
    assert sale_unit(weighted=False, ratio="кг", step=Decimal("0.4")) == "кг"


def test_litres_do_not_become_kilograms():
    assert sale_unit(weighted=True, ratio="0,5л", step=Decimal("0.5")) == "л"
    assert sale_unit(weighted=True, ratio="л", step=None) == "л"


def test_piece_goods_have_no_sale_unit():
    assert sale_unit(weighted=False, ratio="900г", step=Decimal(1)) is None
    assert sale_unit(weighted=False, ratio="10шт", step=Decimal(1)) is None
    assert sale_unit(weighted=False, ratio=None, step=None) is None


def test_an_unreadable_ratio_still_weighs_in_kilograms():
    assert sale_unit(weighted=True, ratio="шматок", step=None) == "кг"


def test_the_step_comes_from_the_card_not_from_the_packaging():
    assert sale_step(ratio="100г", step=Decimal("0.4")) == Decimal("0.4")


def test_without_a_step_the_packaging_names_it():
    assert sale_step(ratio="100г", step=None) == Decimal("0.1")
    assert sale_step(ratio="0,5л", step=None) == Decimal("0.5")


def test_a_silent_card_falls_back_to_the_smallest_step():
    assert sale_step(ratio=None, step=None) == Decimal("0.1")
    assert sale_step(ratio="шматок", step=Decimal(0)) == Decimal("0.1")
