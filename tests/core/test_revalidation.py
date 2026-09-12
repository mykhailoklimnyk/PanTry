from decimal import Decimal

from komora.core.revalidation import (
    Line,
    Verdict,
    first_available,
    plan_rewrites,
    verdict_of,
)
from komora.core.substitution import Alternative, Source


def _line(qty: str = "2", stock: str | None = "5", flagged: bool = False) -> Line:
    return Line(
        external_product_id="907480",
        product_id="uuid-907480",
        name="Чай чорний Pickwick",
        quantity=Decimal(qty),
        stock=None if stock is None else Decimal(stock),
        flagged=flagged,
    )


def _alt(article: str, name: str, stock: int | None = 10, available: bool = True) -> Alternative:
    return Alternative(
        external_product_id=article,
        name=name,
        source=Source.SIMILAR,
        price=Decimal("50"),
        stock=stock,
        available=available,
    )


def test_enough_stock_rides_as_is():
    assert verdict_of(_line(qty="2", stock="5")) is Verdict.OK


def test_zero_stock_is_gone():
    assert verdict_of(_line(stock="0")) is Verdict.GONE


def test_less_than_ordered_is_short():
    assert verdict_of(_line(qty="20", stock="9")) is Verdict.SHORT


def test_unknown_stock_alone_is_not_a_reason_to_rewrite():
    assert verdict_of(_line(stock=None)) is Verdict.OK


def test_unknown_stock_with_api_flag_is_gone():
    assert verdict_of(_line(stock=None, flagged=True)) is Verdict.GONE


def test_known_stock_outweighs_the_flag():
    assert verdict_of(_line(qty="1", stock="5", flagged=True)) is Verdict.OK


def test_first_available_keeps_the_agreed_order():
    chain = (_alt("1", "перша"), _alt("2", "друга"))
    alternative, index, covered = first_available(chain, needed=Decimal(1))
    assert (alternative.name, index, covered) == ("перша", 1, Decimal(1))


def test_unavailable_link_is_skipped_not_reordered():
    chain = (_alt("1", "перша", available=False), _alt("2", "друга"))
    alternative, index, _ = first_available(chain, needed=Decimal(1))
    assert (alternative.name, index) == ("друга", 2)


def test_link_without_stock_is_skipped():
    chain = (_alt("1", "перша", stock=0), _alt("2", "друга"))
    alternative, index, _ = first_available(chain, needed=Decimal(1))
    assert (alternative.name, index) == ("друга", 2)


def test_unknown_stock_of_a_link_counts_as_enough():
    _, _, covered = first_available((_alt("1", "перша", stock=None),), needed=Decimal(3))
    assert covered == Decimal(3)


def test_link_covers_only_what_it_has():
    _, _, covered = first_available((_alt("1", "перша", stock=2),), needed=Decimal(5))
    assert covered == Decimal(2)


def test_empty_chain_gives_nothing():
    assert first_available((), needed=Decimal(1)) == (None, 0, Decimal(0))


def test_healthy_lines_are_not_in_the_plan():
    assert plan_rewrites([_line()], {}) == []


def test_gone_line_is_replaced_by_the_first_link():
    line = _line(qty="2", stock="0")
    chain = {"907480": (_alt("907476", "Чай зелений Pickwick"),)}
    [rewrite] = plan_rewrites([line], chain)

    assert rewrite.verdict is Verdict.GONE
    assert rewrite.keep_quantity == Decimal(0)
    assert rewrite.replacement_quantity == Decimal(2)
    assert rewrite.link_index == 1
    assert not rewrite.needs_approval
    assert rewrite.note == (
        "звичного не було — поклав погоджену заміну №1: Чай зелений Pickwick"
    )


def test_gone_without_a_plan_b_asks_out_loud():
    [rewrite] = plan_rewrites([_line(stock="0")], {})

    assert rewrite.needs_approval
    assert rewrite.replacement is None
    assert rewrite.link_index == 0
    assert "потрібне рішення гостя" in rewrite.note


def test_short_line_keeps_what_is_there_and_tops_up_with_the_link():
    line = _line(qty="20", stock="9")
    chain = {"907480": (_alt("907476", "Чай зелений Pickwick", stock=50),)}
    [rewrite] = plan_rewrites([line], chain)

    assert rewrite.verdict is Verdict.SHORT
    assert rewrite.keep_quantity == Decimal(9)
    assert rewrite.replacement_quantity == Decimal(11)
    assert rewrite.note.startswith("на полиці 9 з 20 — поклав погоджену заміну №1")


def test_partial_cover_says_so_instead_of_pretending():
    line = _line(qty="20", stock="9")
    chain = {"907480": (_alt("907476", "Чай зелений", stock=4),)}
    [rewrite] = plan_rewrites([line], chain)

    assert rewrite.replacement_quantity == Decimal(4)
    assert "закрито 4 з 11" in rewrite.note


def test_quantities_read_as_numbers_not_as_decimal_tails():
    line = Line(
        external_product_id="1",
        product_id="uuid",
        name="Товар",
        quantity=Decimal("2.000"),
        stock=Decimal("1.00"),
    )
    [rewrite] = plan_rewrites([line], {})
    assert "на полиці 1 з 2," in rewrite.note


def test_weighted_line_survives_fractions():
    line = Line(
        external_product_id="1",
        product_id="uuid",
        name="Нектарин",
        quantity=Decimal("1.2"),
        stock=Decimal("0.4"),
    )
    chain = {"1": (_alt("2", "Персик", stock=None),)}
    [rewrite] = plan_rewrites([line], chain)

    assert rewrite.keep_quantity == Decimal("0.4")
    assert rewrite.replacement_quantity == Decimal("0.8")


def test_plan_covers_every_broken_line_and_nothing_else():
    lines = [
        _line(qty="1", stock="5"),
        Line(external_product_id="2", product_id="u2", name="Друге", quantity=Decimal(1),
             stock=Decimal(0)),
        Line(external_product_id="3", product_id="u3", name="Третє", quantity=Decimal(3),
             stock=Decimal(1)),
    ]
    plan = plan_rewrites(lines, {})
    assert [r.line.external_product_id for r in plan] == ["2", "3"]
