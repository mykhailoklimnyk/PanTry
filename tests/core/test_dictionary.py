from __future__ import annotations

import pytest

from komora.core.dictionary import (
    Dictionary,
    Drift,
    Level,
    Node,
    diff,
    echoes,
    normalize,
    same_word,
    words_of,
)

TREE = [
    Node("root-milk", "Молочні продукти та яйця"),
    Node("eggs", "Яйця", "root-milk"),
    Node("eggs-hen", "Курячі яйця", "eggs"),
    Node("eggs-quail", "Перепелині яйця", "eggs"),
    Node("milk", "Молоко, вершки", "root-milk"),
    Node("root-veg", "Овочі"),
    Node("cucumber", "Огірки", "root-veg"),
    Node("tomato", "Помідори", "root-veg"),
    Node("root-fish", "Риба"),
    Node("fish-fresh", "Свіжа риба", "root-fish"),
    Node("root-meat", "М'ясо"),
    Node("poultry", "М'ясо птиці", "root-meat"),
]


@pytest.fixture
def tree() -> Dictionary:
    return Dictionary(TREE)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Молоко ", "молоко"),
        ("ЯЙЦЯ", "яйця"),
        ("\u043c\u2019\u044f\u0441\u043e", "м'ясо"),
        ("\u043c\u02bc\u044f\u0441\u043e", "м'ясо"),
    ],
)
def test_normalize(raw: str, expected: str) -> None:
    assert normalize(raw) == expected


def test_apostrophe_does_not_split_a_word() -> None:
    assert words_of("М'ясо птиці") == ("м'ясо", "птиці")


def test_exact_title_wins(tree: Dictionary) -> None:
    matches = tree.lookup("яйця")
    assert matches[0].node.id == "eggs"
    assert matches[0].level is Level.TITLE
    assert [m.level for m in matches].count(Level.WORD) >= 1


def test_word_inside_a_title(tree: Dictionary) -> None:
    match = tree.best("молоко")
    assert match is not None
    assert match.node.id == "milk"
    assert match.level is Level.WORD


def test_stem_catches_the_plural(tree: Dictionary) -> None:
    match = tree.best("огірок")
    assert match is not None
    assert match.node.id == "cucumber"
    assert match.level is Level.STEM


def test_short_word_still_reaches_longer_titles() -> None:
    tree = Dictionary([Node("cheese", "Сири"), Node("syrup", "Сиропи")])
    found = {m.node.id for m in tree.lookup("сир")}
    assert found == {"cheese", "syrup"}


def test_case_and_spaces_do_not_matter(tree: Dictionary) -> None:
    assert tree.best("  ПОМІДОРИ ").node.id == "tomato"  # type: ignore[union-attr]


def test_unknown_word_proves_nothing(tree: Dictionary) -> None:
    assert tree.lookup("полуниця") == ()
    assert tree.proves_intent("полуниця") is False
    assert tree.proves_intent("яйця") is True


def test_empty_word_is_not_a_lookup(tree: Dictionary) -> None:
    assert tree.lookup("   ") == ()


def test_ties_are_broken_by_the_shorter_title() -> None:
    tree = Dictionary(
        [
            Node("a", "Ягоди заморожені"),
            Node("b", "Ягоди"),
        ]
    )
    assert [m.node.id for m in tree.lookup("ягоди")] == ["b", "a"]


def test_roots_are_the_entry_point(tree: Dictionary) -> None:
    assert {node.title for node in tree.roots()} == {
        "Молочні продукти та яйця",
        "Овочі",
        "Риба",
        "М'ясо",
    }


def test_orphan_is_a_root_not_a_lost_node() -> None:
    tree = Dictionary([Node("child", "Кефір", "missing-parent")])
    assert [node.id for node in tree.roots()] == ["child"]


def test_children_and_length(tree: Dictionary) -> None:
    assert {node.title for node in tree.children("eggs")} == {
        "Курячі яйця",
        "Перепелині яйця",
    }
    assert tree.children("eggs-hen") == ()
    assert tree.children("немає такого") == ()
    assert len(tree) == len(TREE)
    assert tree.node("eggs") is not None
    assert tree.node("немає такого") is None


def test_breadth_is_the_ambiguity_axis(tree: Dictionary) -> None:
    assert tree.narrowing("яйця") == ("Курячі яйця", "Перепелині яйця")
    assert tree.narrowing("огірки") == ()
    assert tree.narrowing("полуниця") == ()


def test_diff_names_every_kind_of_change() -> None:
    before = [Node("a", "Яйця"), Node("b", "Молоко"), Node("c", "Кефір", "b")]
    after = [Node("a", "Яйця курячі"), Node("c", "Кефір", "a"), Node("d", "Ряжанка")]

    drift = diff(before, after)

    assert [node.id for node in drift.added] == ["d"]
    assert [(was.title, now.title) for was, now in drift.renamed] == [("Яйця", "Яйця курячі")]
    assert [(was.id, now.parent_id) for was, now in drift.moved] == [("c", "a")]
    assert [node.id for node in drift.gone] == ["b"]
    assert drift.quiet is False
    assert drift.summary() == "додано 1, перейменовано 1, переїхало 1, зникло 1"


def test_quiet_run_says_so() -> None:
    same = [Node("a", "Яйця")]
    drift = diff(same, list(same))
    assert drift.quiet is True
    assert drift.summary() == "дерево не змінилось"
    assert Drift().quiet is True


def test_diff_order_is_stable() -> None:
    before: list[Node] = []
    after = [Node("z", "Я"), Node("a", "А"), Node("m", "М")]
    assert [node.id for node in diff(before, after).added] == ["a", "m", "z"]


def test_plural_title_beats_a_qualified_one() -> None:
    tree = Dictionary(
        [
            Node("hard", "Сири"),
            Node("curd", "Сир кисломолочний", "dairy"),
            Node("dairy", "Молочні продукти"),
        ]
    )
    match = tree.best("сир")
    assert match is not None
    assert match.node.id == "hard"
    assert match.level is Level.FORM


@pytest.mark.parametrize(
    ("word", "other", "same"),
    [
        ("сир", "сири", True),
        ("ковбаса", "ковбаси", True),
        ("крупа", "крупи", True),
        ("лимон", "лимонна", False),
        ("сир", "сирники", False),
        ("молоко", "молочні", False),
        ("ка", "кава", False),
    ],
)
def test_same_word_only_forgives_the_ending(word: str, other: str, same: bool) -> None:
    assert same_word(word, other) is same


def test_form_only_applies_to_a_one_word_title() -> None:
    tree = Dictionary([Node("craft", "Крафтові сири")])
    match = tree.best("сир")
    assert match is not None
    assert match.level is Level.NEAR
    assert match.strong is False, "слабкий рівень не має керувати вибором виду"


def test_a_longer_ending_is_a_different_word() -> None:
    tree = Dictionary([Node("acid", "Лимонна кислота")])
    match = tree.best("лимон")
    assert match is not None
    assert match.level is Level.STEM


def test_candidates_are_readings_not_refinements() -> None:
    tree = Dictionary(
        [
            Node("hard", "Сири", None, "syry"),
            Node("cream", "Крем-сири", "hard", "krem-syry"),
            Node("dairy", "Молочні продукти", None, "dairy"),
            Node("curd", "Сир кисломолочний", "dairy", "syr-kyslo"),
        ]
    )
    assert [node.id for node in tree.candidates("сир")] == ["hard", "curd"]


def test_candidates_drop_the_ancestor_too() -> None:
    tree = Dictionary(
        [
            Node("milk-group", "Молоко, вершки"),
            Node("milk", "Молоко", "milk-group"),
        ]
    )
    assert [node.id for node in tree.candidates("молоко")] == ["milk"]


def test_cousins_are_different_intents() -> None:
    tree = Dictionary(
        [
            Node("dairy", "Молочні продукти"),
            Node("milk", "Молоко", "dairy"),
            Node("condensed", "Згущене молоко", "dairy"),
        ]
    )
    assert [node.id for node in tree.candidates("молоко")] == ["milk", "condensed"]


def test_candidates_are_capped(tree: Dictionary) -> None:
    tree = Dictionary([Node(f"n{i}", f"Вода {i}" if i else "Вода") for i in range(6)])
    assert len(tree.candidates("вода", limit=2)) == 2


def test_weak_levels_never_become_candidates() -> None:
    tree = Dictionary([Node("syrup", "Сиропи")])
    assert tree.lookup("сир")[0].level is Level.STEM
    assert tree.candidates("сир") == ()


def test_ancestors_walk_up_and_survive_a_loop() -> None:
    tree = Dictionary(
        [
            Node("root", "Напої"),
            Node("water", "Вода", "root"),
            Node("still", "Негазована вода", "water"),
        ]
    )
    assert [node.id for node in tree.ancestors("still")] == ["water", "root"]
    assert tree.ancestors("root") == ()
    assert tree.ancestors("немає") == ()

    looped = Dictionary([Node("a", "А", "b"), Node("b", "Б", "a")])
    assert [node.id for node in looped.ancestors("a")] == ["b"]


def test_related_is_only_the_same_branch() -> None:
    tree = Dictionary(
        [
            Node("root", "Напої"),
            Node("water", "Вода", "root"),
            Node("sweet", "Солодка вода", "root"),
        ]
    )
    assert tree.related("water", "root") is True
    assert tree.related("root", "water") is True
    assert tree.related("water", "water") is True
    assert tree.related("water", "sweet") is False


def test_slug_is_the_key_of_an_answer() -> None:
    tree = Dictionary([Node("water", "Вода", None, "voda-5087")])
    node = tree.by_slug("voda-5087")
    assert node is not None and node.id == "water"
    assert tree.by_slug("немає-такого") is None


def test_the_name_that_repeats_the_word_says_nothing_new() -> None:
    assert echoes("сир", "Сири") is True
    assert echoes("свинина", "Свинина") is True
    assert echoes("пиво", "Пиво") is True
    assert echoes("сир", "Сир кисломолочний") is False
    assert echoes("сир", "Сири тверді") is False
    assert echoes("сир", "Сиропи") is False
    assert echoes("", "Сири") is False
    assert echoes("сир", "") is False
