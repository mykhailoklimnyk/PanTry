from komora.core.catalog import (
    DISPLAY_FLOOR,
    DISPLAY_LEAST,
    display_roots,
    kind_keys,
    kind_only,
    kind_word,
    kinds_of,
    roots_of,
    same_kind,
)
from komora.core.dictionary import Node

CAT = {
    "1": frozenset({"m-iasni-rulety-4747"}),
    "2": frozenset({"kopchena-ryba-ta-moreprodukty-4442"}),
    "3": frozenset({"m-iasni-rulety-4747", "fermerski-m-iasni-delikatesy-5470"}),
}


def test_the_kinds_of_one_article_are_its_own_nodes():
    assert kinds_of(["1"], CAT) == frozenset({"m-iasni-rulety-4747"})


def test_two_articles_of_the_guest_merge_their_nodes():
    assert kinds_of(["1", "3"], CAT) == frozenset(
        {"m-iasni-rulety-4747", "fermerski-m-iasni-delikatesy-5470"}
    )


def test_an_unknown_article_adds_nothing_and_does_not_raise():
    assert kinds_of(["1", "999"], CAT) == frozenset({"m-iasni-rulety-4747"})


def test_no_articles_at_all_give_no_kinds():
    assert kinds_of([], CAT) == frozenset()


def test_an_empty_catalog_gives_no_kinds():
    assert kinds_of(["1", "3"], {}) == frozenset()


def test_the_fish_roll_is_not_the_same_kind_as_the_meat_roll():
    assert not same_kind("2", kinds_of(["1"], CAT), CAT)


def test_the_meat_roll_of_another_brand_is_the_same_kind():
    assert same_kind("3", kinds_of(["1"], CAT), CAT)


def test_an_article_is_the_same_kind_as_itself():
    assert same_kind("1", kinds_of(["1"], CAT), CAT)


def test_without_the_guests_kinds_nothing_is_the_same_kind():
    assert not same_kind("1", frozenset(), CAT)


def test_a_candidate_missing_from_the_map_is_not_declared_foreign():
    assert not same_kind("999", kinds_of(["1"], CAT), CAT)


def test_one_shared_node_out_of_several_is_not_enough():
    cat = {"a": frozenset({"x", "y"}), "b": frozenset({"y", "z"})}
    assert not same_kind("b", kinds_of(["a"], cat), cat)


def test_a_narrower_set_inside_a_wider_one_is_the_same_kind():
    cat = {"a": frozenset({"x", "y"}), "b": frozenset({"y"})}
    assert same_kind("b", kinds_of(["a"], cat), cat)
    assert same_kind("a", kinds_of(["b"], cat), cat)


def test_the_squid_is_not_the_same_kind_as_the_hake():
    cat = {
        "хек": frozenset({"zamorozhena-ryba-4432", "zamorozheni-moreprodukty-i-ryba-5181"}),
        "окунь": frozenset({"zamorozhena-ryba-4432", "zamorozheni-moreprodukty-i-ryba-5181"}),
        "кальмар": frozenset(
            {"zamorozheni-moreprodukty-i-ryba-5181", "zamorozheni-moreprodukty-ta-moliusky-4451"}
        ),
        "креветка": frozenset(
            {"zamorozheni-moreprodukty-i-ryba-5181", "zamorozheni-moreprodukty-ta-moliusky-4451"}
        ),
    }
    mine = kinds_of(["хек"], cat)
    assert same_kind("окунь", mine, cat)
    assert not same_kind("кальмар", mine, cat)
    assert not same_kind("креветка", mine, cat)


def test_two_articles_of_the_guest_widen_what_counts_as_his_kind():
    cat = {
        "хек": frozenset({"ryba", "moreprodukty-i-ryba"}),
        "коктейль": frozenset({"moliusky", "moreprodukty-i-ryba"}),
        "кальмар": frozenset({"moliusky", "moreprodukty-i-ryba"}),
    }
    assert not same_kind("кальмар", kinds_of(["хек"], cat), cat)
    assert same_kind("кальмар", kinds_of(["хек", "коктейль"], cat), cat)


def test_disjoint_nodes_are_not_the_same_kind():
    cat = {"a": frozenset({"x"}), "b": frozenset({"z"})}
    assert not same_kind("b", kinds_of(["a"], cat), cat)


def test_an_article_with_no_nodes_at_all_is_not_the_same_kind():
    cat = {"a": frozenset({"x"}), "b": frozenset()}
    assert not same_kind("b", kinds_of(["a"], cat), cat)


SHELF = frozenset({"promo-a", "promo-b"})
DAIRY = frozenset({"moloko", "syry"})
BOOZE = frozenset({"pyvo", "vyno"})
ROOTS = {"Добрі промо": SHELF, "Молочні": DAIRY, "Алкоголь": BOOZE}


def _catalog(shelf: int, dairy_only: int, booze_only: int):
    found = {}
    for i in range(dairy_only):
        found[f"d{i}"] = {"moloko"}
    for i in range(booze_only):
        found[f"b{i}"] = {"pyvo"}
    for i in range(shelf):
        found[f"s{i}"] = {"moloko", "promo-a"}
    return found


def test_a_root_with_no_products_of_its_own_is_a_shelf():
    found = _catalog(shelf=3, dairy_only=10, booze_only=10)
    assert display_roots(found, ROOTS, least=1) == frozenset({"Добрі промо"})


def test_a_root_where_most_products_live_only_there_is_a_kind():
    found = _catalog(shelf=1, dairy_only=10, booze_only=10)
    assert "Молочні" not in display_roots(found, ROOTS, least=1)
    assert "Алкоголь" not in display_roots(found, ROOTS, least=1)


def test_a_root_too_small_to_judge_is_left_alone():
    found = _catalog(shelf=3, dairy_only=10, booze_only=10)
    assert display_roots(found, ROOTS, least=1000) == frozenset()


def test_the_shelf_nodes_are_cut_and_the_kind_nodes_stay():
    found = _catalog(shelf=3, dairy_only=10, booze_only=10)
    kept, shelves = kind_only(found, ROOTS, least=1)
    assert shelves == frozenset({"Добрі промо"})
    assert all("promo-a" not in nodes for nodes in kept.values())
    assert kept["s0"] == frozenset({"moloko"})


def test_an_article_left_without_any_kind_node_stays_in_the_map():
    found = {**_catalog(shelf=3, dairy_only=10, booze_only=10), "x": {"promo-a"}}
    kept, _ = kind_only(found, ROOTS, least=1)
    assert "x" in kept
    assert kept["x"] == frozenset()


def test_a_product_seen_only_on_the_shelf_stops_being_the_same_kind():
    found = {**_catalog(shelf=3, dairy_only=10, booze_only=10)}
    found["макарони"] = {"promo-a"}
    found["молоко-х"] = {"moloko", "promo-a"}
    assert same_kind("макарони", kinds_of(["молоко-х"], found), found)
    kept, shelves = kind_only(found, ROOTS, least=1)
    assert shelves == frozenset({"Добрі промо"})
    assert not same_kind("макарони", kinds_of(["молоко-х"], kept), kept)


def test_the_floor_is_a_gap_not_a_tuned_number():
    found = _catalog(shelf=3, dairy_only=10, booze_only=10)
    for floor in (0.25, 0.4, 0.5, 0.55):
        assert display_roots(found, ROOTS, floor=floor, least=1) == frozenset({"Добрі промо"})


def _roots_with(alone: int, shared: int):
    found = {}
    for i in range(alone):
        found[f"a{i}"] = {"moloko"}
    for i in range(shared):
        found[f"s{i}"] = {"moloko", "promo-a"}
    return found


def test_a_root_exactly_at_the_floor_is_not_a_shelf():
    found = _roots_with(alone=5, shared=5)
    assert display_roots(found, ROOTS, floor=0.5, least=1) == frozenset({"Добрі промо"})


def test_a_root_one_step_below_the_floor_is_a_shelf():
    found = _roots_with(alone=4, shared=6)
    assert display_roots(found, ROOTS, floor=0.5, least=1) == frozenset({"Добрі промо", "Молочні"})


def test_a_root_exactly_at_the_least_is_judged():
    found = _roots_with(alone=0, shared=4)
    assert display_roots(found, ROOTS, floor=0.5, least=4) == frozenset({"Добрі промо", "Молочні"})


def test_a_root_one_short_of_the_least_is_left_alone():
    found = _roots_with(alone=0, shared=3)
    assert display_roots(found, ROOTS, floor=0.5, least=4) == frozenset()


def test_a_root_nobody_reached_is_a_kind_not_a_shelf():
    assert display_roots({}, ROOTS, least=1) == frozenset()


def test_the_shipped_floor_and_least_are_the_measured_ones():
    assert DISPLAY_FLOOR == 0.5
    assert DISPLAY_LEAST == 200


def test_kinds_of_merges_and_does_not_intersect():
    cat = {"a": frozenset({"x"}), "b": frozenset({"y"})}
    assert kinds_of(["a", "b"], cat) == frozenset({"x", "y"})


def test_kind_only_returns_the_shelves_it_actually_cut():
    found = _roots_with(alone=1, shared=9)
    kept, shelves = kind_only(found, ROOTS, least=1)
    for title in shelves:
        for slug in ROOTS[title]:
            assert all(slug not in nodes for nodes in kept.values())


def test_a_small_root_does_not_stop_the_judging_of_the_next_one():
    found = {f"m{i}": {"moloko"} for i in range(8)}
    for i in range(3):
        found[f"s{i}"] = {"moloko", "promo-a"}
    found["tiny"] = {"nothing"}
    roots = {"Дрібний": frozenset({"nothing"}), "Добрі промо": SHELF, "Молочні": DAIRY}
    assert display_roots(found, roots, least=2) == frozenset({"Добрі промо"})


def test_kind_only_hands_the_floor_down_to_the_judging():
    found = _catalog(shelf=3, dairy_only=10, booze_only=10)
    strict, _ = kind_only(found, ROOTS, floor=0.9, least=1)
    lenient, _ = kind_only(found, ROOTS, floor=0.5, least=1)
    assert strict != lenient, "інша межа мусить давати інший різ"
    assert all("moloko" not in nodes for nodes in strict.values())
    assert any("moloko" in nodes for nodes in lenient.values())


WATER = {
    "w1": frozenset({"mineralna-voda-4001"}),
    "w2": frozenset({"dytiacha-voda-4002"}),
    "w3": frozenset({"mineralna-voda-4001", "pytna-voda-4003"}),
}
WATER_ROWS = [
    ("Вода мінеральна Моршинська", "w1"),
    ("Вода дитяча Малятко", "w2"),
    ("Вода мінеральна Поляна", "w3"),
]


def test_the_node_splits_kinds_that_share_the_first_word():
    keys = kind_keys(WATER_ROWS, WATER)
    assert keys.key("Вода дитяча Малятко") != keys.key("Вода мінеральна Моршинська")


def test_the_shared_node_keeps_them_one_kind():
    keys = kind_keys(WATER_ROWS, WATER)
    assert keys.key("Вода мінеральна Моршинська") == keys.key("Вода мінеральна Поляна")


def test_a_different_first_word_is_a_different_kind():
    keys = kind_keys([*WATER_ROWS, ("Томат Гордій Черрі", "t1")], {**WATER, "t1": frozenset({"n"})})
    assert keys.key("Томат Гордій Черрі") == "томат·Томат Гордій Черрі"
    assert keys.key("Томат Гордій Черрі") not in keys.by_word["вода"]


def test_an_unknown_article_does_not_split_anything():
    keys = kind_keys([*WATER_ROWS, ("Вода питна Моршинка", "w9")], WATER)
    assert len(keys.by_word["вода"]) == 1


def test_two_kinds_stay_together_through_a_third():
    catalog = {
        "a": frozenset({"n1"}),
        "b": frozenset({"n1", "n2"}),
        "c": frozenset({"n2"}),
    }
    rows = [("Сир Альфа", "a"), ("Сир Бета", "b"), ("Сир Гама", "c")]
    keys = kind_keys(rows, catalog)
    assert keys.key("Сир Альфа") == keys.key("Сир Гама")
    assert keys.by_word["сир"] == frozenset({"сир·Сир Альфа"})


def test_the_guest_word_covers_every_kind_of_that_word():
    keys = kind_keys(WATER_ROWS, WATER)
    assert keys.covering("Вода") == frozenset(
        {"вода·Вода дитяча Малятко", "вода·Вода мінеральна Моршинська"}
    )


def test_the_guest_word_covers_the_same_kinds_written_with_a_small_letter():
    keys = kind_keys(WATER_ROWS, WATER)
    assert keys.covering("вода") == keys.covering("Вода")
    assert keys.covering("вода") == frozenset(
        {"вода·Вода дитяча Малятко", "вода·Вода мінеральна Моршинська"}
    )


def test_the_kind_word_is_the_first_one_and_it_is_folded():
    assert kind_word("Вода мінеральна Моршинська") == "вода"
    assert kind_word("вода") == "вода"


def test_a_name_without_a_single_word_keeps_itself():
    assert kind_word("  ,  ") == ","


def test_a_known_row_covers_only_its_own_kind():
    keys = kind_keys(WATER_ROWS, WATER)
    assert keys.covering("Вода дитяча Малятко") == frozenset({"вода·Вода дитяча Малятко"})


def test_an_unseen_name_falls_back_to_its_first_word():
    keys = kind_keys(WATER_ROWS, WATER)
    assert keys.key("Хліб Київський") == "хліб"
    assert keys.covering("Хліб Київський") == frozenset({"хліб"})


"""Корені дерева: що під ними лежить і хто взагалі коренем є.

ЧОМУ ЦІ ТЕСТИ З'ЯВИЛИСЬ ПІЗНО ЗА ФУНКЦІЮ. `roots_of` жила в `jobs/catalog`
під іменем `_roots`, тобто ПОЗА мутаційним контуром, і тестів на неї не було
взагалі -- її перевіряв лише обхід каталогу цілком. Переїзд у `core/`
(#337: другий читач -- навігатор комори) затягнув її в контур голою, і
прогін 06.09 сказав це першим же рядком: 21 мутант зі статусом «без тестів»,
усі в цій функції. Це гірше за вижилого -- вижилий каже «тут діра», а цей
каже «сюди не дивились» (#50, #205).
"""


def tree(*rows: tuple[str, str, str | None, str]) -> list[Node]:
    return [
        Node(id=node, title=title, parent_id=parent, slug=slug)
        for node, title, parent, slug in rows
    ]


def test_a_root_carries_everything_beneath_it():
    got = roots_of(
        tree(
            ("r", "Заморожена продукція", None, "zamorozhena"),
            ("a", "Морозиво", "r", "morozyvo"),
            ("b", "Пломбір", "a", "plombir"),
        )
    )
    assert got == {"Заморожена продукція": frozenset({"zamorozhena", "morozyvo", "plombir"})}


def test_only_a_node_without_a_parent_becomes_a_root():
    got = roots_of(
        tree(
            ("r", "Заморожена продукція", None, "zamorozhena"),
            ("a", "Морозиво", "r", "morozyvo"),
        )
    )
    assert list(got) == ["Заморожена продукція"]


def test_sibling_roots_do_not_leak_into_each_other():
    got = roots_of(
        tree(
            ("r1", "Сири", None, "syry"),
            ("r2", "Риба", None, "ryba"),
            ("a", "Гауда", "r1", "gauda"),
            ("b", "Оселедець", "r2", "oseledets"),
        )
    )
    assert got == {"Сири": frozenset({"syry", "gauda"}), "Риба": frozenset({"ryba", "oseledets"})}


def test_a_root_without_children_is_still_a_root():
    assert roots_of(tree(("r", "БАДи", None, "bady"))) == {"БАДи": frozenset({"bady"})}


def test_a_node_without_a_slug_answers_with_its_id():
    got = roots_of(
        tree(
            ("r", "Сири", None, ""),
            ("a", "Гауда", "r", ""),
        )
    )
    assert got == {"Сири": frozenset({"r", "a"})}


def test_an_empty_tree_has_no_roots():
    assert roots_of([]) == {}
