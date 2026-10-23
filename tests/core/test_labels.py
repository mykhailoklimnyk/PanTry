from komora.core.labels import (
    NO_LETTERS,
    by_skeleton,
    echoed,
    label,
    labels,
    resolve,
    skeleton,
)


def test_the_label_carries_both_the_word_and_the_number():
    assert label("молоко", 1) == "мо01"
    assert label("Хліб", 12) == "хл12"


def test_a_word_without_letters_still_gets_a_label():
    assert label("7up", 3) == "up03"
    assert label("100%", 4) == f"{NO_LETTERS}04"


def test_the_same_intent_twice_keeps_one_label():
    assert labels(["сир", "хліб", "сир"]) == {"сир": "си01", "хліб": "хл02"}


def test_labels_of_an_empty_list():
    assert labels([]) == {}


def test_a_corrupted_half_lands_outside_the_set_not_on_a_neighbour():
    of = {mark: name for name, mark in labels(["молоко", "хліб"]).items()}
    assert resolve("мо01", of) == "молоко"
    assert resolve("мо02", of) is None
    assert resolve("хл01", of) is None


def test_the_intent_itself_is_accepted_too():
    of = {mark: name for name, mark in labels(["молоко"]).items()}
    assert resolve("молоко", of) == "молоко"


def test_anything_else_is_refused():
    of = {mark: name for name, mark in labels(["молоко"]).items()}
    assert resolve("", of) is None
    assert resolve("Молоко", of) is None
    assert resolve("мо1", of) is None


def test_the_separator_does_not_survive_the_skeleton():
    same = skeleton("йогурт · фруктовий")
    assert skeleton("йогурт фруктовий") == same
    assert skeleton("йогурт-фруктовий") == same
    assert skeleton("ЙОГУРТ·ФРУКТОВИЙ") == same


def test_a_dropped_apostrophe_survives_too():
    assert skeleton("горіхи · кеш'ю") == skeleton("горіхи кешю")


def test_a_different_kind_keeps_a_different_skeleton():
    assert skeleton("вода питна · дитяча") != skeleton("вода питна")


def test_the_echo_lands_on_the_label_we_asked():
    of = by_skeleton(["йогурт · фруктовий", "вода питна · дитяча"])

    assert echoed("йогурт фруктовий", of) == "йогурт · фруктовий"
    assert echoed("вода питна дитяча", of) == "вода питна · дитяча"


def test_an_echo_of_something_we_did_not_ask_is_refused():
    of = by_skeleton(["йогурт · фруктовий"])

    assert echoed("ковбаса салямі", of) is None
    assert echoed("", of) is None


def test_a_tie_binds_nothing():
    of = by_skeleton(["йогурт · фруктовий", "йогурт фруктовий"])

    assert of == {}
    assert echoed("йогурт фруктовий", of) is None


def test_a_label_with_nothing_but_punctuation_is_not_a_key():
    assert by_skeleton(["···", "йогурт"]) == {skeleton("йогурт"): "йогурт"}
