from __future__ import annotations

import pytest

from komora.core.brands import MIN_SKELETON, carried_by, head_word, same_word, skeleton


@pytest.mark.parametrize(
    ("word", "other"),
    [
        ("Спрайт", "Sprite"),
        ("Мівіна", "Mivina"),
        ("Нутелла", "Nutella"),
        ("Моршинська", "Morshynska"),
        ("Кока-кола", "Coca-Cola"),
        ("Пепсі", "Pepsi"),
        ("Фанта", "Fanta"),
    ],
)
def test_the_same_word_in_two_alphabets_is_one_word(word, other):
    assert same_word(word, other)
    assert same_word(other, word), "правило мусить читатись в обидва боки"


@pytest.mark.parametrize(
    ("word", "other"),
    [
        ("Спрайт", "Splat"),
        ("Спрайт", "Spice"),
        ("сир", "сироп"),
        ("Нутелла", "Ноутбук"),
    ],
)
def test_a_phonetic_neighbour_is_not_the_same_word(word, other):
    assert not same_word(word, other)


def test_a_short_word_matches_nothing():
    assert skeleton("кола") == ""
    assert not same_word("кола", "Cola")
    assert not carried_by("кола", "Напій Coca-Cola Classic з/б")
    assert not carried_by("кола", "Паста зубна Splat Professional")


def test_the_ceiling_is_the_only_reason_a_skeleton_is_empty():
    assert len(skeleton("сироп")) >= MIN_SKELETON
    assert skeleton("ой") == ""


def test_doubles_collapse_but_only_when_they_touch():
    assert skeleton("Нутелла") == skeleton("нутела")
    assert skeleton("Кока-кола") == "kkkl"


def test_a_double_stops_itself_and_not_the_rest_of_the_word():
    assert same_word("халумі", "Halloumi")
    assert skeleton("Halloumi") == skeleton("халумі") == "hlm"


def test_the_name_carries_the_word_from_inside():
    assert carried_by("Спрайт", "Напій Sprite 0,5 л")
    assert carried_by("Кока-кола", "Напій Coca-Cola Classic з/б")
    assert carried_by("полуниця", "Ягоди полуниця 250 г")


def test_the_name_that_carries_nothing_says_so():
    assert not carried_by("Спрайт", "Паста зубна Splat Professional")
    assert not carried_by("Спрайт", "Дезодорант Old Spice Night Panther")


def test_numbers_are_checked_because_the_skeleton_is_blind_to_them():
    assert carried_by("Товар 8", "Товар 8 великий")
    assert not carried_by("Товар 8", "Товар 0")


def test_a_number_inside_a_bigger_number_is_not_that_number():
    assert not carried_by("Товар 8", "Товар 18 великий")
    assert not carried_by("Товар 8", "Товар 81")


def test_a_whole_number_is_not_the_head_of_a_fraction():
    assert not carried_by("молоко 1", "Молоко 1,5% Селянське")
    assert not carried_by("молоко 2,5", "Молоко 12,5% Яготинське")


def test_a_fraction_is_one_number_whichever_separator_writes_it():
    assert carried_by("Спрайт 0,5", "Напій Sprite 0,5 л")
    assert carried_by("Спрайт 0.5", "Напій Sprite 0,5 л")
    assert not carried_by("Спрайт 0,5", "Напій Sprite 1,5 л")


def test_a_trailing_zero_is_the_same_number_written_twice():
    assert carried_by("молоко 1", "Молоко 1,0% Селянське")
    assert carried_by("спрайт 1", "Напій Sprite 1,0 л")
    assert carried_by("Спрайт 0,5", "Напій Sprite 0,50 л")


def test_a_word_without_numbers_is_not_judged_by_the_numbers_of_the_name():
    assert carried_by("Спрайт", "Напій Sprite 0,5 л")
    assert carried_by("молоко 2,5", "Молоко 2,5% Яготинське 900 г")


def test_the_head_of_the_name_is_the_kind():
    assert head_word("Напій Sprite 0,5 л") == "Напій"
    assert head_word("Ягоди полуниця 250 г") == "Ягоди"


def test_a_name_without_letters_has_no_head():
    assert head_word("0,5") == ""
    assert head_word("") == ""
