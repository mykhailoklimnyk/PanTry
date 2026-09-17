from komora.core.homoglyphs import (
    bare,
    fold,
    fold_names,
    is_allowed,
    mixed_words,
    script_of,
    stray_chars,
)


def test_a_word_with_latin_vowels_merges_with_its_twin():
    twin = fold("молоко")
    broken = fold("мoлoко")
    assert broken.text == twin.text
    assert broken.changed


def test_a_foreign_brand_is_not_touched():
    folded = fold("Напій Trash 0,5 л")
    assert folded.text == "Напій Trash 0,5 л"
    assert not folded.changed and not folded.odd


def test_a_word_that_cannot_be_healed_stays_whole_and_names_itself():
    folded = fold("вино кріплене таwny")
    assert folded.text == "вино кріплене таwny"
    assert folded.odd == ("таwny",)
    assert not folded.changed


def test_the_typographic_apostrophe_is_the_same_class():
    folded = fold("з м’ятною начинкою")
    assert folded.text == "з м'ятною начинкою"
    assert folded.changed


def test_invisible_characters_go_without_a_trace_of_themselves():
    folded = fold("мол​око")
    assert folded.text == "молоко"
    assert folded.changed


def test_clean_text_is_returned_untouched():
    for text in ("молоко", "Sprite 0,5 л", "", "2 шт · 120 ₴"):
        folded = fold(text)
        assert folded.text == text
        assert not folded.changed and not folded.odd


def test_the_label_of_an_intent_survives_a_latin_lookalike():
    assert fold("cи01").text == "си01"


def test_what_counts_as_a_typeable_character():
    for ch in "aЯ7 -.«»—·₴":
        assert is_allowed(ch)
    for ch in ("​", "í", "’", "−"):
        assert not is_allowed(ch)


def test_emoji_are_a_deliberate_part_of_the_interface():
    assert is_allowed("☕") and is_allowed("\U0001f9c0")


def test_stray_chars_lists_every_offender_once():
    assert stray_chars("мол​око​") == ["​"]
    assert stray_chars("молоко") == []


def test_mixed_words_names_the_word_its_cure_and_whether_it_worked():
    word, suggestion, healed = mixed_words("мoлoко свіже")[0]
    assert (word, suggestion, healed) == ("мoлoко", "молоко", True)


def test_a_mixed_word_that_cannot_be_healed_is_marked_as_such():
    (_word, _suggestion, healed) = mixed_words("вино кріплене таwny")[0]
    assert healed is False


def test_the_alphabet_comes_from_the_line_not_from_the_word():
    assert script_of("час: він не namір, він обставина") == "cyr"
    assert script_of("Sprite Zero 0,5 l") == "lat"


def test_a_letter_with_a_diacritic_is_healed_by_the_alphabet_of_the_line():
    assert fold("молокí").text == "молокі"
    assert fold("Napói Trash").text == "Napoi Trash"


def test_a_diacritic_makes_a_word_odd_even_in_one_alphabet():
    from komora.core.homoglyphs import is_odd

    assert is_odd("молокí")
    assert is_odd("мoлoко")
    assert not is_odd("молоко") and not is_odd("Trash")


def test_the_emoji_range_starts_exactly_where_it_says():
    assert is_allowed("☀")
    assert not is_allowed("◿")


def test_the_tilde_stays_typeable():
    assert is_allowed("~") and is_allowed(" ") and is_allowed("!")


def test_a_symbol_below_the_emoji_range_is_not_an_emoji():
    assert not is_allowed("©")


def test_a_cyrillic_lookalike_inside_a_latin_word_goes_latin():
    folded = fold("Sprite Zеro 0,5 l")
    assert folded.text == "Sprite Zero 0,5 l"
    assert folded.fixed == (("Zеro", "Zero"),)


def test_what_was_changed_is_named_pair_by_pair():
    folded = fold("мoлoко")
    assert folded.fixed == (("мoлoко", "молоко"),)


def test_a_character_swap_outside_a_word_names_itself_too():
    folded = fold("з м’ятною")
    assert folded.text == "з м'ятною"
    assert folded.fixed == (("з м’ятною", "з м'ятною"),)


def test_escapes_do_not_invent_words_out_of_nothing():
    assert mixed_words(r"print(\nСценаріїв)") == []


def test_the_apostrophe_goes_in_every_form_it_arrives_in():
    assert bare("м'ясо") == bare("м\u2019ясо") == bare("мясо") == "мясо"


def test_only_the_apostrophe_goes_and_nothing_else():
    assert bare("біло-сірий") == "біло-сірий"
    assert bare("«Премія»") == "«Премія»"


def test_a_latin_word_keeps_its_letters():
    assert bare("Lay's") == "Lays"


def test_a_word_without_an_apostrophe_comes_back_untouched():
    assert bare("молоко") == "молоко"


def test_a_latin_letter_at_the_head_of_a_cyrillic_word_is_healed():
    got = fold_names("X\u043b\u0456\u0431 \u041a\u0438\u0457\u0432\u0441\u044c\u043a\u0438\u0439")
    assert got.text == "Хліб Київський"
    assert got.odd == ()


def test_a_size_the_row_context_cannot_fix_is_fixed_by_the_word():
    mixed = "Пакет паперовий \u0425L"
    assert fold(mixed).odd == ("ХL",), "рядковий вибір тут безсилий -- це і є задача"
    assert fold_names(mixed).text == "Пакет паперовий XL"


def test_a_word_neither_alphabet_can_cure_is_left_alone_and_named():
    mixed = "Vito\u0413\u0440\u0430\u043d\u043e сир"
    got = fold_names(mixed)
    assert got.text == mixed
    assert got.odd == ("VitoГрано",)


def test_a_word_BOTH_alphabets_would_cure_is_left_alone():
    both = "c\u043e"
    got = fold_names(both)
    assert got.text == both, "вибір навмання тут гірший за мовчання"
    assert got.odd == (both,), "і слово мусить назвати себе"


def test_a_purely_latin_brand_is_not_touched():
    assert fold_names("Trash пакети").text == "Trash пакети"
    assert fold_names("Lay's класичні").text == "Lay's класичні"


def test_an_empty_name_is_not_a_crash():
    assert fold_names("").text == ""


def test_the_typographic_apostrophe_is_straightened_here_too():
    assert fold_names("М\u2019ясо мідій").text == "М'ясо мідій"
