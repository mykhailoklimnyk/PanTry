from __future__ import annotations

from komora.core.ceilings import (
    DEFAULT_MAX_QTY,
    DEFAULT_NEEDS,
    DEFAULT_ORDER,
    MAX_NEEDS,
    MIN_NEEDS,
    max_qty,
    usual_basket,
    usual_basket_stats,
    usual_order,
)


def test_without_receipts_the_ceiling_is_the_honest_default():
    assert usual_basket([]) == DEFAULT_NEEDS


def test_the_ceiling_is_the_p75_of_the_guests_receipts():
    sizes = [1, 2, 3, 3, 5, 8, 8, 9, 12, 14, 14, 18, 22, 40, 8, 8]
    assert usual_basket(sizes) == 14


def test_a_lone_receipt_is_the_whole_distribution():
    assert usual_basket([9]) == 9


def test_empty_receipts_do_not_drag_the_ceiling_down():
    assert usual_basket([0, 0, 0, 12, 12, 12]) == 12
    assert usual_basket([0, 0, 0, 0, 0, 0, 0, 12]) == 12


def test_a_single_item_run_to_the_shop_still_counts():
    assert usual_basket([1, 1, 1, 1, 20]) == MIN_NEEDS


def test_two_receipts_take_the_larger_one():
    assert usual_basket([4, 20]) == 20


def test_the_ceiling_never_falls_below_a_workable_basket():
    assert usual_basket([1, 1, 2, 1, 2]) == MIN_NEEDS


def test_one_trip_for_everything_does_not_become_the_norm():
    assert usual_basket([40, 38, 44, 50]) == MAX_NEEDS


def test_the_line_ceiling_comes_from_the_kinds_own_history():
    assert max_qty(2) == 4
    assert max_qty(1) == 2


def test_without_history_the_line_ceiling_stays_global():
    assert max_qty(None) == DEFAULT_MAX_QTY
    assert max_qty(0) == DEFAULT_MAX_QTY


def test_the_line_ceiling_never_exceeds_the_global_one():
    assert max_qty(1000) == DEFAULT_MAX_QTY


def test_the_line_ceiling_never_drops_to_zero():
    assert max_qty(0.4) == 1


_MEASURED = [1, 2, 3, 3, 5, 8, 8, 9, 12, 14, 14, 18, 22, 40, 8, 8]


def test_the_ceiling_carries_the_distribution_it_came_from():
    usual = usual_basket_stats(_MEASURED)

    assert (usual.median, usual.p75, usual.limit) == (8, 14, 14)
    assert usual.receipts == len(_MEASURED)
    assert usual.clamped is False


def test_the_derivation_is_said_in_the_same_words_everywhere():
    assert usual_basket_stats(_MEASURED).phrase() == "медіана 8, p75 14, беру 14"


def test_a_clamped_ceiling_admits_it_was_not_the_p75():
    high = usual_basket_stats([40, 38, 44, 50])
    assert high.limit == MAX_NEEDS and high.clamped is True
    assert "верхня межа стелі" in high.phrase()

    low = usual_basket_stats([1, 1, 2, 1, 2])
    assert low.limit == MIN_NEEDS and low.clamped is True
    assert "нижня межа стелі" in low.phrase()


def test_without_receipts_the_derivation_says_so_instead_of_inventing_a_median():
    empty = usual_basket_stats([])

    assert empty.receipts == 0
    assert empty.clamped is False, "затиснути нема чого — стелі з чеків не було"
    assert empty.phrase() == f"чеків ще немає — беру {DEFAULT_NEEDS} за замовчуванням"


def test_service_receipts_are_out_of_the_derivation_too():
    usual = usual_basket_stats([0, 0, 0, 12, 12, 12])

    assert usual.receipts == 3
    assert usual.median == 12


def test_the_number_and_its_derivation_never_disagree():
    for sizes in ([], [9], _MEASURED, [40, 38, 44, 50], [1, 1, 2]):
        assert usual_basket(sizes) == usual_basket_stats(sizes).limit


def test_the_horizon_is_the_guests_own_rhythm_not_a_week():
    from datetime import date

    from komora.core.ceilings import trip_gap

    every_two_days = [date(2026, 8, day) for day in (1, 3, 5, 7, 9)]
    assert trip_gap(every_two_days) == 2


def test_a_rare_shopper_gets_a_longer_horizon():
    from datetime import date

    from komora.core.ceilings import trip_gap

    monthly = [date(2026, m, 1) for m in (4, 5, 6, 7)]
    assert trip_gap(monthly) == 30


def test_the_horizon_never_collapses_to_zero():
    from datetime import date

    from komora.core.ceilings import DEFAULT_TRIP_GAP, trip_gap

    assert trip_gap([date(2026, 8, 1), date(2026, 8, 1)]) == DEFAULT_TRIP_GAP
    assert trip_gap([]) == DEFAULT_TRIP_GAP
    assert trip_gap([date(2026, 8, 1), date(2026, 8, 2)]) == 1


def test_the_horizon_takes_the_MIDDLE_of_the_distribution():
    from datetime import date

    from komora.core.ceilings import trip_gap

    uneven = [date(2026, 8, day) for day in (1, 2, 4, 7, 17)]
    assert trip_gap(uneven) == 3


class TestOrderTarget:

    def test_the_median_is_the_target_and_the_mean_is_not(self) -> None:
        spend = usual_order([1219, 1400, 1520, 1600, 2145, 6442])

        assert spend.target == 1600, "медіана, округлена до кроку повзунка"
        assert spend.target < 1815, "середнє сюди не потрапляє"

    def test_no_orders_says_the_number_is_ours(self) -> None:
        spend = usual_order([])

        assert spend.guessed is True
        assert spend.target == DEFAULT_ORDER
        assert "твоїх замовлень ще не видно" in spend.phrase()

    def test_the_output_is_said_out_loud(self) -> None:
        said = usual_order([1200, 1500, 2100, 3300]).phrase()

        assert "медіана" in said and "p75" in said

    def test_cancelled_and_returns_do_not_describe_orders(self) -> None:
        spend = usual_order([0, -50, 1500, 1500])

        assert spend.orders == 2

    def test_the_ninth_decile_shows_only_where_it_describes_something(self) -> None:
        few = usual_order([900, 1400, 1520, 2000, 2145, 6442])
        many = usual_order([900, 1000, 1100, 1200, 1300, 1400, 1500, 1600, 1700, 6442])

        assert max(few.presets) == few.p75, "хвіст не став кнопкою"
        assert max(many.presets) > many.p75, "на достатній вибірці дециль є"

    def test_twin_steps_do_not_become_two_identical_buttons(self) -> None:
        spend = usual_order([1500, 1500, 1500])

        assert spend.presets == (1500,)
