from komora.core.allergens import Allergen, conflicts, explain, is_safe, parse

REAL_FIELD = "ГЛЮТЕН, МОЛОКО, ЯЙЦЯ, ГІРЧИЦЮ, СОЮ"


def test_real_field_from_a_product_card():
    assert parse(REAL_FIELD) == {
        Allergen.GLUTEN,
        Allergen.MILK,
        Allergen.EGGS,
        Allergen.MUSTARD,
        Allergen.SOY,
    }


def test_declension_does_not_break_matching():
    assert parse("ГІРЧИЦЮ") == {Allergen.MUSTARD}
    assert parse("ГІРЧИЦЯ") == {Allergen.MUSTARD}
    assert parse("ГІРЧИЦІ") == {Allergen.MUSTARD}


def test_soy_forms():
    for form in ("СОЮ", "СОЯ", "сої"):
        assert parse(form) == {Allergen.SOY}


def test_soy_stem_does_not_swallow_similar_words():
    assert parse("сосиски") == frozenset()
    assert parse("сорбіт") == frozenset()
    assert parse("сода") == frozenset()


def test_soy_is_found_inside_a_multiword_phrase():
    assert parse("соєві боби") == {Allergen.SOY}
    assert parse("соус соєвий натуральний") == {Allergen.SOY}


def test_separators_variants():
    for field in ("МОЛОКО, ЯЙЦЯ", "МОЛОКО; ЯЙЦЯ", "МОЛОКО та ЯЙЦЯ", "МОЛОКО / ЯЙЦЯ"):
        assert parse(field) == {Allergen.MILK, Allergen.EGGS}


def test_synonyms_map_to_one_allergen():
    assert parse("КЛЕЙКОВИНА") == {Allergen.GLUTEN}
    assert parse("ЛАКТОЗА") == {Allergen.MILK}
    assert parse("СЕЗАМ") == {Allergen.SESAME}


def test_unknown_words_are_ignored_not_fatal():
    assert parse("МОЛОКО, барвник Е150, ЯЙЦЯ") == {Allergen.MILK, Allergen.EGGS}


def test_empty_field_is_empty_set():
    assert parse(None) == frozenset()
    assert parse("") == frozenset()
    assert parse("   ") == frozenset()


def test_conflict_names_exactly_what_clashes():
    product = parse(REAL_FIELD)
    assert conflicts(product, [Allergen.MILK]) == {Allergen.MILK}
    assert conflicts(product, [Allergen.FISH]) == frozenset()


def test_safety_is_the_absence_of_conflict():
    product = parse(REAL_FIELD)
    assert is_safe(product, [Allergen.FISH, Allergen.NUTS]) is True
    assert is_safe(product, [Allergen.NUTS, Allergen.SOY]) is False


def test_product_without_allergens_is_safe_for_everyone():
    assert is_safe(parse(None), [Allergen.MILK, Allergen.GLUTEN]) is True


def test_explanation_is_readable():
    assert explain(parse("МОЛОКО, ГЛЮТЕН")) == "містить: глютен, молоко"
    assert explain(parse(None)) == "без заявлених алергенів"
