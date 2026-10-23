from decimal import Decimal

import pytest

from komora.core.weight import (
    WeighedLine,
    cart_weight,
    exceeds_limit,
    line_weight_g,
    over_limit,
    split_by_weight,
    total_weight_kg,
    unit_weight_kg,
)

LIMIT = Decimal("50")


def line(pid: str, qty: str, grams: int) -> WeighedLine:
    return WeighedLine(external_product_id=pid, qty=Decimal(qty), unit_weight_g=grams)


def test_line_weight_multiplies_quantity():
    assert line_weight_g(line("1", "3", 1500)) == Decimal("4500")


def test_weight_of_empty_cart_is_zero():
    assert total_weight_kg([]) == Decimal(0)


def test_limit_is_not_exceeded_exactly_at_the_boundary():
    lines = [line("water", "10", 5000)]
    assert total_weight_kg(lines) == Decimal("50")
    assert exceeds_limit(lines, LIMIT) is False


def test_limit_is_exceeded_just_above_the_boundary():
    assert exceeds_limit([line("water", "10", 5001)], LIMIT) is True


def test_cart_within_limit_stays_one_delivery():
    shipments = split_by_weight([line("a", "1", 1000), line("b", "2", 500)], LIMIT)
    assert len(shipments) == 1


def test_heavy_cart_splits_into_two():
    lines = [
        line("water", "12", 6000),
        line("food", "2", 4000),
    ]
    shipments = split_by_weight(lines, LIMIT)

    assert len(shipments) == 2
    for shipment in shipments:
        assert total_weight_kg(shipment) <= LIMIT

    packed = {ln.external_product_id for shipment in shipments for ln in shipment}
    assert packed == {"water", "food"}


def test_a_single_line_is_divided_by_the_piece():
    shipments = split_by_weight([line("water", "12", 6000)], LIMIT)

    assert len(shipments) == 2
    quantities = sorted(ln.qty for shipment in shipments for ln in shipment)
    assert quantities == [Decimal(4), Decimal(8)]


def test_split_loses_no_weight_and_no_quantity():
    lines = [line(str(i), "3", 7000) for i in range(5)]
    shipments = split_by_weight(lines, LIMIT)

    assert sum((total_weight_kg(s) for s in shipments), Decimal(0)) == total_weight_kg(lines)

    packed: dict[str, Decimal] = {}
    for shipment in shipments:
        for ln in shipment:
            packed[ln.external_product_id] = packed.get(ln.external_product_id, Decimal(0)) + ln.qty
    assert packed == {str(i): Decimal(3) for i in range(5)}


def test_weighted_remainder_survives_the_split():
    shipments = split_by_weight([line("cheese", "1.35", 1000)], LIMIT)
    total = sum((ln.qty for shipment in shipments for ln in shipment), Decimal(0))
    assert total == Decimal("1.35")


def test_a_single_piece_heavier_than_the_limit_is_a_data_error():
    with pytest.raises(ValueError, match="одна одиниця"):
        split_by_weight([line("anvil", "1", 60_000)], LIMIT)


def test_non_positive_limit_is_rejected():
    with pytest.raises(ValueError, match="додатним"):
        split_by_weight([line("a", "1", 1)], Decimal(0))


def test_piece_weight_comes_from_the_packaging_field():
    assert unit_weight_kg(weighted=False, ratio="900г", step=Decimal(1)) == Decimal("0.9")


def test_multipack_weighs_the_whole_pack():
    assert unit_weight_kg(weighted=False, ratio="16*8,5г", step=Decimal(1)) == Decimal("0.136")


def test_a_weighed_line_measures_itself():
    assert unit_weight_kg(weighted=True, ratio="100г", step=Decimal("0.4")) == Decimal(1)


def test_litres_are_counted_as_kilograms():
    assert unit_weight_kg(weighted=False, ratio="1,5л", step=Decimal(1)) == Decimal("1.5")


def test_a_piece_without_packaging_has_no_weight_at_all():
    assert unit_weight_kg(weighted=False, ratio="10шт", step=Decimal(1)) is None
    assert unit_weight_kg(weighted=False, ratio=None, step=None) is None


def test_the_cart_multiplies_the_unit_by_the_quantity():
    weight = cart_weight([(Decimal(3), Decimal("0.9")), (Decimal("0.4"), Decimal(1))])
    assert weight.kg == Decimal("3.1")
    assert weight.complete is True


def test_an_unknown_line_is_counted_apart_and_not_as_zero():
    weight = cart_weight([(Decimal(1), Decimal("0.5")), (Decimal(2), None)])
    assert weight.kg == Decimal("0.5")
    assert weight.unknown == 1
    assert weight.complete is False


def test_an_empty_cart_weighs_nothing_and_hides_nothing():
    assert cart_weight([]) == cart_weight(())
    assert cart_weight([]).kg == Decimal(0)
    assert cart_weight([]).complete is True


def test_the_excess_is_the_difference_with_the_limit():
    assert over_limit(Decimal("52.5"), LIMIT) == Decimal("2.5")


def test_exactly_at_the_limit_nothing_is_exceeded():
    assert over_limit(LIMIT, LIMIT) == Decimal(0)


def test_a_slot_that_named_no_limit_blocks_nothing():
    assert over_limit(Decimal(80), Decimal(0)) == Decimal(0)
    assert over_limit(Decimal(80), None) == Decimal(0)
