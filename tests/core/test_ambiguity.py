from __future__ import annotations

from decimal import Decimal
from typing import Any

from komora.core.ambiguity import MAX_OPTIONS, Option, axis_of, on_axis, option, unit_prices, usable


def product(
    price: float,
    *,
    ratio: str | None = "900г",
    weighted: bool = False,
    step: float | None = 1,
) -> dict[str, Any]:
    return {
        "externalProductId": int(price),
        "name": f"Товар {price}",
        "price": price,
        "displayRatio": ratio,
        "weighted": weighted,
        "step": step,
    }


def test_price_is_the_smallest_not_the_average() -> None:
    got = option("Молоко", "moloko-253", [product(39.99), product(53.49), product(46.99)])
    assert got.price_from == Decimal("39.99")
    assert got.count == 3
    assert got.by_weight is False
    assert got.empty is False


def test_weighted_node_is_marked_as_per_kilogram() -> None:
    got = option(
        "Свинина",
        "svynyna-4413",
        [product(272.46, ratio="100г", weighted=True, step=0.4), product(228.98, weighted=True)],
    )
    assert got.by_weight is True
    assert got.price_from == Decimal("228.98")


def test_a_weighted_minority_does_not_relabel_the_node() -> None:
    got = option("Сири", "syry", [product(64.99), product(79.9), product(199, weighted=True)])
    assert got.by_weight is False


def test_node_without_prices_still_counts_its_products() -> None:
    got = option("Вода", "voda", [{"externalProductId": 1, "name": "Вода", "price": 0}])
    assert got.count == 1
    assert got.price_from is None
    assert got.empty is False


def test_empty_node_is_never_offered() -> None:
    empty = option("Олія CBD", "oliia-cbd", [])
    assert empty.empty is True
    assert usable([empty]) == ()


def test_options_are_deduped_and_capped() -> None:
    many = [
        Option(title=f"Вид {i}", slug=f"vyd-{i}", count=2, price_from=Decimal(10))
        for i in range(MAX_OPTIONS + 3)
    ]
    twin = Option(title="Інша назва", slug="vyd-0", count=5)
    kept = usable([*many, twin])
    assert len(kept) == MAX_OPTIONS
    assert [item.slug for item in kept] == [f"vyd-{i}" for i in range(MAX_OPTIONS)]


def test_limit_can_be_narrowed() -> None:
    two = [Option(title="А", slug="a", count=1), Option(title="Б", slug="b", count=1)]
    assert len(usable(two, limit=1)) == 1


def test_unit_prices_skip_what_cannot_be_compared() -> None:
    prices = unit_prices(
        [
            product(39.99),
            product(272.46, ratio="100г", weighted=True, step=0.4),
            product(89, ratio="10шт"),
            product(0, ratio="900г"),
        ]
    )
    assert [round(price, 2) for price in prices] == [Decimal("4.44"), Decimal("27.25")]


def test_fractional_step_alone_means_weight() -> None:
    lying = product(120.0, ratio="400г", weighted=False, step=0.4)
    assert option("Нектарини", "nektaryny", [lying]).by_weight is True
    assert unit_prices([lying]) == [Decimal(12)]


def test_half_weighted_is_not_a_majority() -> None:
    mixed = [product(64.99), product(199, weighted=True)]
    assert option("Сири", "syry", mixed).by_weight is False


def test_a_cheap_item_is_still_an_item() -> None:
    assert option("Хліб", "khlib", [product(0.99)]).price_from == Decimal("0.99")


def test_a_bad_option_in_the_middle_does_not_cut_the_tail() -> None:
    kept = usable(
        [
            Option(title="Сири", slug="syry", count=3, price_from=Decimal(99)),
            Option(title="Порожній", slug="empty", count=0),
            Option(title="Сири", slug="syry", count=3),
            Option(title="Сир кисломолочний", slug="syr-kyslo", count=8),
        ]
    )
    assert [item.slug for item in kept] == ["syry", "syr-kyslo"]


COFFEE_ASK = "Яку каву вам взяти: розчинну, мелену чи зернову?"


def test_the_guests_own_word_is_not_an_axis() -> None:
    axis = axis_of(COFFEE_ASK, "кава")
    assert "каву" not in axis
    assert {"розчинну", "мелену", "зернову"} <= set(axis)


def test_a_multiword_intent_takes_all_its_words_out_of_the_axis() -> None:
    assert axis_of("Сир кисломолочний жирний чи знежирений?", "сир кисломолочний") == (
        "жирний",
        "чи",
        "знежирений",
    )


def test_the_axis_reads_a_different_form_of_the_same_word() -> None:
    assert on_axis("Кава в зернах", axis_of(COFFEE_ASK, "кава"))


def test_a_neighbouring_kind_is_not_an_answer() -> None:
    axis = axis_of(COFFEE_ASK, "кава")
    assert not on_axis("Кава (Cava)", axis)
    assert not on_axis("Холодні чаї та кава", axis)
    assert not on_axis("Кава в капсулах", axis)


def test_an_empty_axis_lets_nothing_through() -> None:
    assert axis_of("Кава?", "кава") == ()
    assert not on_axis("Кава в зернах", ())


def test_a_short_word_is_judged_by_form_and_not_by_the_root() -> None:
    assert on_axis("Сири тверді", ("сир",))
    assert not on_axis("Сиропи", ("сир",))


def test_a_long_word_is_judged_by_the_root_even_when_forms_diverge() -> None:
    assert on_axis("Кава меленої обжарки", ("мелену",))
    assert not on_axis("Кава розчинна", ("мелену",))


def test_a_title_without_words_answers_nothing() -> None:
    assert not on_axis("250", axis_of(COFFEE_ASK, "кава"))


def test_a_conjunction_does_not_match_a_conjunction() -> None:
    assert not on_axis("Холодні чаї та кава", ("та", "чи"))
