from komora.core.aisles import BY_WORD_ONLY, CATCH_ALL, aisles, by_word_only

ROOTS = {
    "Фрукти, овочі": frozenset({"ovochi", "frukty"}),
    "Молочні продукти та яйця": frozenset({"moloko", "yaitsia"}),
    "Дитячі товари": frozenset({"dytiache"}),
}


def test_a_row_stands_under_the_root_of_its_article():
    got = aisles([("a", ["111"])], {"111": frozenset({"ovochi"})}, ROOTS)
    assert got.of == {"a": "Фрукти, овочі"}
    assert [aisle.title for aisle in got.order] == ["Фрукти, овочі"]
    assert got.order[0].rows == 1


def test_a_row_without_a_root_is_not_lost():
    got = aisles([("a", ["невідомий"])], {}, ROOTS)
    assert got.of == {"a": CATCH_ALL}


def test_a_row_with_no_articles_at_all_is_not_lost():
    assert aisles([("a", [])], {}, ROOTS).of == {"a": CATCH_ALL}


def test_the_majority_of_articles_picks_the_aisle():
    got = aisles(
        [("a", ["1", "2", "3"])],
        {
            "1": frozenset({"moloko"}),
            "2": frozenset({"moloko"}),
            "3": frozenset({"dytiache"}),
        },
        ROOTS,
    )
    assert got.of == {"a": "Молочні продукти та яйця"}


def test_a_tie_is_broken_by_name_and_not_by_luck():
    catalog = {"1": frozenset({"moloko"}), "2": frozenset({"dytiache"})}
    first = aisles([("a", ["1", "2"])], catalog, ROOTS)
    second = aisles([("a", ["2", "1"])], catalog, ROOTS)
    assert first.of == second.of == {"a": "Дитячі товари"}


def test_the_rail_follows_the_list_and_not_the_size_of_the_aisle():
    got = aisles(
        [
            ("гострий", ["1"]),
            ("сам", ["2"]),
            ("тихий", ["3"]),
            ("ще", ["4"]),
        ],
        {
            "1": frozenset({"dytiache"}),
            "2": frozenset({"moloko"}),
            "3": frozenset({"moloko"}),
            "4": frozenset({"moloko"}),
        },
        ROOTS,
    )
    assert [aisle.title for aisle in got.order] == ["Дитячі товари", "Молочні продукти та яйця"]
    assert [aisle.rows for aisle in got.order] == [1, 3]


def test_the_nameless_aisle_stands_last_even_when_its_row_is_first():
    got = aisles(
        [("a", ["хтозна"]), ("b", ["1"])],
        {"1": frozenset({"ovochi"})},
        ROOTS,
    )
    assert [aisle.title for aisle in got.order] == ["Фрукти, овочі", CATCH_ALL]


def test_without_a_tree_there_is_no_rail_at_all():
    got = aisles([("a", ["1"])], {"1": frozenset({"ovochi"})}, {})
    assert got.order == ()
    assert got.of == {}


def test_an_empty_pantry_gives_an_empty_rail():
    got = aisles([], {}, ROOTS)
    assert got.of == {}
    assert got.order == ()


def test_every_row_gets_an_aisle_and_the_counts_add_up():
    rows = [("a", ["1"]), ("b", ["2"]), ("c", []), ("d", ["1"])]
    got = aisles(rows, {"1": frozenset({"ovochi"}), "2": frozenset({"moloko"})}, ROOTS)
    assert set(got.of) == {"a", "b", "c", "d"}
    assert sum(aisle.rows for aisle in got.order) == len(rows)


def test_a_node_deep_under_the_root_still_answers_with_the_root():
    roots = {"Заморожена продукція": frozenset({"zamorozhena", "morozyvo", "plombir"})}
    got = aisles([("a", ["1"])], {"1": frozenset({"plombir"})}, roots)
    assert got.of == {"a": "Заморожена продукція"}


def test_the_named_aisle_beats_the_tree():
    got = aisles(
        [("a", ["111"])],
        {"111": frozenset({"dytiache"})},
        ROOTS,
        {"a": "Молочні продукти та яйця"},
    )
    assert got.of == {"a": "Молочні продукти та яйця"}


def test_the_tree_keeps_the_row_when_the_model_said_catch_all():
    got = aisles([("a", ["111"])], {"111": frozenset({"ovochi"})}, ROOTS, {"a": CATCH_ALL})
    assert got.of == {"a": "Фрукти, овочі"}


def test_the_named_aisle_covers_what_the_tree_does_not_know():
    got = aisles([("a", ["111"])], {}, ROOTS, {"a": "Фрукти, овочі"})
    assert got.of == {"a": "Фрукти, овочі"}


def test_a_row_without_a_named_aisle_still_gets_the_tree():
    got = aisles([("a", ["111"]), ("b", ["222"])], {"111": frozenset({"ovochi"})}, ROOTS, {"b": ""})
    assert got.of == {"a": "Фрукти, овочі", "b": CATCH_ALL}


def test_the_rail_order_follows_the_named_aisles_too():
    got = aisles(
        [("a", ["111"]), ("b", ["222"])],
        {"111": frozenset({"moloko"}), "222": frozenset({"ovochi"})},
        ROOTS,
        {"a": "Фрукти, овочі"},
    )
    assert [aisle.title for aisle in got.order] == ["Фрукти, овочі"]
    assert got.order[0].rows == 2


def test_only_the_named_aisles_ride_by_the_guests_word_alone():
    assert by_word_only("Соуси і спеції") is True
    assert all(by_word_only(aisle) for aisle in BY_WORD_ONLY)
    assert by_word_only("Бакалія і консерви") is False
    assert by_word_only(CATCH_ALL) is False
    assert by_word_only(None) is False
    assert by_word_only("") is False

