from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from komora.core.bar import Bottle, DrinkKind, Kind, fork_of, rows, said_group, said_row
from komora.core.pantry import manual_id

NOW = datetime(2026, 8, 25, tzinfo=UTC)


def _bottle(
    article: str,
    *,
    price: str | None = "50.99",
    receipts: int = 1,
    days: int | None = 0,
    pack: str = "0,5л",
    name: str = "Пиво",
) -> Bottle:
    return Bottle(
        article=article,
        name=name,
        receipts=receipts,
        price=Decimal(price) if price is not None else None,
        last_at=None if days is None else NOW - timedelta(days=days),
        pack=pack,
    )


def _kind(*bottles: Bottle, label: str = "пиво світле", key: str = "light|пиво") -> Kind:
    return Kind(key=key, label=label, group=DrinkKind.LIGHT, bottles=bottles)


def test_two_prices_are_the_guests_own_bounds():
    fork, note = fork_of([Decimal("44.99"), Decimal("62.49")], pack="0,5л")

    assert (fork.low, fork.high) == (Decimal(44), Decimal(63))
    assert note == "брав 0,5л за 44–63 ₴"


def test_rounding_only_widens_the_fork():
    fork, _ = fork_of([Decimal("44.01"), Decimal("62.01")])

    assert fork.low == Decimal(44)
    assert fork.high == Decimal(63)


def test_one_price_names_the_percent_out_loud():
    fork, note = fork_of([Decimal("189.00")])

    assert (fork.low, fork.high) == (Decimal("170.1"), Decimal("207.9"))
    assert note == "брав за 189 ₴, беру 10% в обидва боки"


def test_the_pack_travels_with_the_number():
    _, note = fork_of([Decimal("99")], pack="4*0,33л")

    assert "4*0,33л" in note


def test_the_fork_stays_inside_one_pack():
    kind = _kind(
        _bottle("1", price="50.99", receipts=5, days=16, pack="0,5л"),
        _bottle("2", price="264", receipts=2, days=40, pack="4*0,5л"),
    )

    (row,) = rows([kind], now=NOW).rows

    assert row.usual.article == "1", "звичне — найсвіжіша пляшка виду"
    assert row.price == Decimal("50.99")
    assert (row.fork.low, row.fork.high) == (Decimal("45.89"), Decimal("56.09"))
    assert row.fork_note == "брав 0,5л за 51 ₴, беру 10% в обидва боки"
    assert "264" not in row.fork_note


def test_times_counts_every_bottle_of_the_kind():
    kind = _kind(
        _bottle("1", receipts=5, days=16),
        _bottle("2", receipts=4, days=40),
    )

    (row,) = rows([kind], now=NOW).rows

    assert row.times == 9
    assert row.share == "5 з 9"
    assert row.days_since == 16, "свіжість — за найсвіжішою покупкою виду"


def test_a_kind_without_a_single_price_does_not_become_a_row():
    assert rows([_kind(_bottle("1", price=None))], now=NOW).rows == ()


def test_a_skipped_kind_does_not_take_the_rest_of_the_bar_with_it():
    broken = _kind(_bottle("1", price=None), label="сидр", key="light|сидр")
    fine = _kind(_bottle("2", receipts=4), label="пиво", key="light|пиво")

    assert [row.label for row in rows([broken, fine], now=NOW).rows] == ["пиво"]


def test_the_usual_bottle_is_the_freshest_one_even_if_it_is_not_the_most_bought():
    old_favourite = _bottle("1", receipts=9, days=90, price="40")
    fresh = _bottle("2", receipts=1, days=2, price="60")

    (row,) = rows([_kind(old_favourite, fresh)], now=NOW).rows

    assert row.usual.article == "2"
    assert row.price == Decimal(60)
    assert row.share == "1 з 10"


def test_a_kind_without_a_single_date_does_not_become_a_row():
    kind = _kind(Bottle(article="1", name="Пиво", receipts=2, price=Decimal(50)))

    assert rows([kind], now=NOW).rows == ()


def test_a_row_carries_the_id_and_the_group_of_its_kind():
    kind = _kind(_bottle("1"), label="пиво", key="light|пиво")

    (row,) = rows([kind], now=NOW).rows

    assert row.id == "light|пиво"
    assert row.group is DrinkKind.LIGHT
    assert row.label == "пиво"


def test_the_most_usual_kind_comes_first():
    rare = _kind(_bottle("1", receipts=1, days=1), label="сидр", key="light|сидр")
    usual = _kind(_bottle("2", receipts=9, days=30), label="пиво", key="light|пиво")

    assert [row.label for row in rows([rare, usual], now=NOW).rows] == ["пиво", "сидр"]


def test_a_purchase_in_the_future_does_not_make_days_negative():
    kind = _kind(_bottle("1", days=-2))

    (row,) = rows([kind], now=NOW).rows

    assert row.days_since == 0


def test_a_bottle_without_a_date_does_not_outrank_a_dated_one():
    mine = _bottle("own", price="40", receipts=9, days=2)
    stranger = _bottle("stranger", price="264", receipts=1, days=None, pack="4*0,5л")

    (row,) = rows([_kind(mine, stranger)], now=NOW).rows

    assert row.usual.article == "own", "невідома дата — не сьогоднішня"
    assert row.price == Decimal(40)
    assert row.usual.pack == "0,5л"
    assert "264" not in row.fork_note


def test_a_dateless_bottle_still_counts_toward_the_fork():
    kind = _kind(
        _bottle("dated", price="40", receipts=1, days=3),
        _bottle("dateless", price="60", receipts=9, days=None),
    )

    (row,) = rows([kind], now=NOW).rows

    assert row.usual.article == "dated", "невідома дата — не сьогоднішня"
    assert (row.fork.low, row.fork.high) == (Decimal(40), Decimal(60))
    assert row.fork_note == "брав 0,5л за 40–60 ₴"


def test_two_bottles_of_the_same_day_are_ranked_by_receipts():
    rare = _bottle("1", price="90", receipts=1, days=4)
    often = _bottle("2", price="50", receipts=7, days=4)

    (row,) = rows([_kind(rare, often)], now=NOW).rows

    assert row.usual.article == "2"


def test_a_kind_whose_only_priced_bottle_has_no_date_does_not_become_a_row():
    dateless = _bottle("1", price="50", receipts=3, days=None)
    priceless = _bottle("2", price=None, receipts=1, days=5)

    assert rows([_kind(dateless, priceless)], now=NOW).rows == ()


def test_the_last_purchase_is_counted_from_the_same_bottles_as_the_usual_one():
    kind = _kind(
        _bottle("gift", price="0", receipts=1, days=1),
        _bottle("paid", price="51", receipts=5, days=30),
    )

    (row,) = rows([kind], now=NOW).rows

    assert row.usual.article == "paid"
    assert row.days_since == 30, "дата — з пляшки, яка може стати звичною"


def test_a_one_hryvnia_price_stays_inside_the_fork():
    kind = _kind(
        _bottle("promo", price="1", receipts=1, days=9),
        _bottle("paid", price="51", receipts=5, days=3),
    )

    (row,) = rows([kind], now=NOW).rows

    assert row.usual.article == "paid"
    assert (row.fork.low, row.fork.high) == (Decimal(1), Decimal(51))
    assert row.fork_note == "брав 0,5л за 1–51 ₴"


def test_a_zero_price_does_not_take_the_whole_bar_down():
    gift = _kind(_bottle("1", price="0", receipts=3, days=1), label="сидр", key="light|сидр")
    fine = _kind(_bottle("2", receipts=4), label="пиво", key="light|пиво")

    assert [row.label for row in rows([gift, fine], now=NOW).rows] == ["пиво"]


def test_a_zero_price_never_enters_the_fork():
    kind = _kind(
        _bottle("gift", price="0", receipts=3, days=1),
        _bottle("paid", price="51", receipts=5, days=3),
    )

    (row,) = rows([kind], now=NOW).rows

    assert row.usual.article == "paid", "нуль з чека звичною пляшкою не робить"
    assert row.price == Decimal(51)
    assert (row.fork.low, row.fork.high) == (Decimal("45.9"), Decimal("56.1"))
    assert row.fork_note == "брав 0,5л за 51 ₴, беру 10% в обидва боки"


def test_a_dropped_kind_is_counted_not_swallowed():
    dated = _kind(_bottle("1", price="51"))
    undated = _kind(_bottle("2", price="44", days=None), label="сидр", key="light|сидр")
    shelf = rows([dated, undated], now=NOW)
    assert [row.label for row in shelf.rows] == ["пиво світле"]
    assert shelf.dropped == 1


def test_a_shelf_where_nothing_was_dropped_says_zero():
    shelf = rows([_kind(_bottle("1", price="51"))], now=NOW)
    assert shelf.dropped == 0


def test_a_kind_dropped_for_a_zero_price_is_counted_too():
    shelf = rows([_kind(_bottle("1", price="0"))], now=NOW)
    assert shelf.rows == ()
    assert shelf.dropped == 1


def test_two_dropped_kinds_are_counted_as_two():
    alive = _kind(_bottle("1", price="51"))
    first = _kind(_bottle("2", price="44", days=None), label="сидр", key="light|сидр")
    second = _kind(_bottle("3", price="0"), label="вино", key="wine|вино")
    shelf = rows([alive, first, second], now=NOW)
    assert len(shelf.rows) == 1
    assert shelf.dropped == 2


def test_the_usual_bottle_carries_its_pack():
    kind = Kind(
        key="beer",
        label="Пиво світле",
        group="light",
        bottles=(
            Bottle(
                article="1",
                name="Оболонь Преміум",
                receipts=4,
                price=Decimal("51"),
                last_at=NOW,
                pack="0,5л",
            ),
        ),
    )

    [row] = rows([kind], now=NOW).rows

    assert row.usual is not None and row.usual.pack == "0,5л"
    assert "0,5л" in row.fork_note


def test_a_hand_written_row_carries_no_numbers_because_they_would_be_ours():
    row = said_row("віскі", "  Віскі Jameson  ", group=DrinkKind.STRONG)

    assert row.said is True
    assert row.label == "Віскі Jameson", "пробіли по краях -- не частина слова гостя"
    assert row.group is DrinkKind.STRONG
    assert row.usual is None and row.price is None
    assert row.fork is None and row.fork_note == ""
    assert row.times == 0
    assert row.days_since is None, "нуль тут читався б як «востаннє сьогодні» (#76)"


def test_the_id_of_a_hand_written_row_is_the_fingerprint_of_the_kind():
    assert said_row("віскі", "Віскі Jameson", group=None).id == manual_id("віскі")
    assert said_row("  ВІСКІ ", "інша назва", group=None).id == manual_id("віскі")


def test_a_kind_the_model_did_not_call_a_drink_keeps_no_group():
    assert said_row("комбуча", "Комбуча", group=None).group is None


def test_without_a_word_from_the_guest_the_models_guess_stands():
    assert said_group("лікер", DrinkKind.STRONG, {}) == (DrinkKind.STRONG, False)


def test_the_guests_word_outweighs_the_guess_and_says_so():
    assert said_group("лікер", DrinkKind.WINE, {"лікер": DrinkKind.STRONG}) == (
        DrinkKind.STRONG,
        True,
    )


def test_a_word_that_agrees_with_the_guess_still_counts_as_said():
    assert said_group("віскі", DrinkKind.STRONG, {"віскі": DrinkKind.STRONG}) == (
        DrinkKind.STRONG,
        True,
    )


def test_a_word_about_a_neighbour_does_not_move_this_kind():
    assert said_group("пиво світле", DrinkKind.LIGHT, {"віскі": DrinkKind.STRONG}) == (
        DrinkKind.LIGHT,
        False,
    )


def test_the_guest_can_name_a_shelf_the_model_left_empty():
    assert said_group("компот", None, {"компот": DrinkKind.LIGHT}) == (
        DrinkKind.LIGHT,
        True,
    )


def test_no_word_and_no_guess_stays_no_shelf():
    assert said_group("компот", None, {}) == (None, False)


def test_a_hand_written_row_carries_whose_shelf_it_is():
    row = said_row("віскі", "Віскі", group=DrinkKind.STRONG, group_said=True)

    assert row.group is DrinkKind.STRONG
    assert row.group_said is True


def test_a_hand_written_row_says_nothing_about_a_shelf_nobody_moved():
    assert said_row("віскі", "Віскі", group=DrinkKind.STRONG).group_said is False


def test_a_counted_row_carries_whose_shelf_it_is():
    kind = Kind(
        key="strong|лікер",
        label="лікер",
        group=DrinkKind.STRONG,
        bottles=(_bottle("1"),),
        group_said=True,
    )

    [row] = rows([kind], now=NOW).rows

    assert row.group_said is True


def test_a_counted_row_nobody_moved_says_nothing():
    [row] = rows([_kind(_bottle("1"))], now=NOW).rows

    assert row.group_said is False


def _alcohol_tree():
    from komora.core.dictionary import Node

    return [
        Node(id="1", title="Алкоголь", parent_id=None, slug="alkogol-4457"),
        Node(id="2", title="Міцний алкоголь", parent_id="1", slug="mitsnyi-alkogol-4458"),
        Node(id="3", title="Ром", parent_id="2", slug="rom-4468"),
        Node(id="4", title="Лікери, бальзами, біттери", parent_id="2", slug="likery-4470"),
        Node(id="5", title="Пиво", parent_id="1", slug="pyvo-4503"),
        Node(id="6", title="Українське пиво", parent_id="5", slug="ukrainske-pyvo-4504"),
        Node(id="7", title="Імпортне пиво", parent_id="5", slug="importne-pyvo-4505"),
        Node(
            id="8",
            title="Безалкогольний алкоголь",
            parent_id="1",
            slug="bezalkogolnyi-alkogol-4464",
        ),
        Node(id="9", title="Безалкогольне пиво", parent_id="8", slug="bezalk-pyvo-4466"),
        Node(id="10", title="Сир твердий", parent_id=None, slug="syry-1"),
    ]


def test_the_tree_names_the_kind_and_the_shelf_where_the_model_guessed_wrong():
    from komora.core import bar as core

    shelves = core.shelf_map(_alcohol_tree())
    found = core.shelved("532439", {"532439": frozenset({"rom-4468"})}, shelves)
    assert found is not None
    assert found.label == "ром"
    assert found.group is core.DrinkKind.STRONG


def test_a_node_that_only_refines_its_parent_gives_the_parent_word():
    from komora.core import bar as core

    shelves = core.shelf_map(_alcohol_tree())
    nodes = {"a": frozenset({"ukrainske-pyvo-4504"}), "b": frozenset({"importne-pyvo-4505"})}
    first = core.shelved("a", nodes, shelves)
    second = core.shelved("b", nodes, shelves)
    assert first is not None and second is not None
    assert first.label == second.label == "пиво"
    assert first.group is core.DrinkKind.LIGHT


def test_the_tree_stays_silent_where_it_knows_nothing_and_on_the_teetotal_shelf():
    from komora.core import bar as core

    shelves = core.shelf_map(_alcohol_tree())
    assert core.shelved("нема", {}, shelves) is None
    assert core.shelved("c", {"c": frozenset({"syry-1"})}, shelves) is None
    assert core.shelved("d", {"d": frozenset({"bezalk-pyvo-4466"})}, shelves) is None


def test_a_renumbered_tree_breaks_towards_the_model_and_not_towards_a_wrong_shelf():
    from komora.core import bar as core
    from komora.core.dictionary import Node

    renumbered = [
        Node(id="2", title="Міцний алкоголь", parent_id=None, slug="mitsnyi-alkogol-9999"),
        Node(id="3", title="Ром", parent_id="2", slug="rom-9998"),
    ]
    shelves = core.shelf_map(renumbered)
    assert core.shelved("x", {"x": frozenset({"rom-9998"})}, shelves) is None
