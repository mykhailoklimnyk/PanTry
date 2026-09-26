from komora.core.prompt import FOREIGN_LIMIT, is_empty, prune, tame


def test_a_null_field_does_not_ride_to_the_model():
    assert prune({"назва": "Молоко", "оброблене": None}) == {"назва": "Молоко"}


def test_an_empty_container_is_emptiness_too():
    assert prune({"а": [], "б": "", "в": {}, "г": ()}) == {}


def test_zero_is_a_fact_about_the_product_and_stays():
    assert prune({"залишок": 0, "ціна": 0.0, "нарізка": False}) == {
        "залишок": 0,
        "ціна": 0.0,
        "нарізка": False,
    }


def test_the_cut_reaches_products_inside_the_list():
    asked = {
        "наміри": [
            {"намір": "молоко", "кандидати": [{"id": "1", "стара_ціна": None}]},
        ]
    }
    assert prune(asked) == {"наміри": [{"намір": "молоко", "кандидати": [{"id": "1"}]}]}


def test_a_position_never_disappears_even_when_it_empties():
    assert prune({"кандидати": [{"id": None}, {"id": "2"}]}) == {"кандидати": [{}, {"id": "2"}]}


def test_a_field_that_empties_after_the_cut_goes_too():
    assert prune({"а": {"б": None}}) == {}


def test_what_counts_as_empty():
    assert is_empty(None) and is_empty([]) and is_empty("") and is_empty({})
    assert not is_empty(0) and not is_empty(False) and not is_empty("0")


def test_an_ordinary_name_passes_untouched():
    assert tame("Пюре Mark&Mart запечене яблучко без цукру") == (
        "Пюре Mark&Mart запечене яблучко без цукру",
        False,
    )


def test_a_control_character_becomes_a_space():
    healed, changed = tame("рядок\nз переносом")
    assert healed == "рядок з переносом"
    assert changed


def test_a_control_character_that_split_does_NOT_see_is_removed_too():
    healed, changed = tame("а\x07б")
    assert healed == "а б"
    assert changed
    assert tame("а\x00б")[0] == "а б"
    assert tame("а\x7fб")[0] == "а б"


def test_a_tab_and_a_carriage_return_go_too():
    assert tame("а\tб\rв")[0] == "а б в"


def test_a_non_breaking_space_is_folded_to_an_ordinary_one():
    assert tame("м'ясо\u00a0рулет")[0] == "м'ясо рулет"


def test_a_name_at_the_ceiling_is_not_cut():
    text = "а" * FOREIGN_LIMIT
    assert tame(text) == (text, False)


def test_a_name_one_over_the_ceiling_is_cut_and_says_so():
    healed, changed = tame("а" * (FOREIGN_LIMIT + 1))
    assert len(healed) == FOREIGN_LIMIT
    assert changed


def test_a_cut_that_lands_right_after_a_space_does_not_keep_it():
    text = "а" * (FOREIGN_LIMIT - 1) + " " + "б" * 10
    healed, changed = tame(text)
    assert changed
    assert healed == "а" * (FOREIGN_LIMIT - 1)
    assert not healed.endswith(" ")


def test_the_ceiling_is_the_measured_one():
    assert FOREIGN_LIMIT == 120


def test_an_empty_name_is_not_a_crash():
    assert tame("") == ("", False)


def test_a_name_of_only_control_characters_becomes_empty():
    healed, changed = tame("\n\t\r")
    assert healed == ""
    assert changed
