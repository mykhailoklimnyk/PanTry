from __future__ import annotations

from komora.core.pantry import is_manual, manual_id, regrouped


def test_the_same_kind_gives_the_same_id_anywhere():
    assert manual_id("молоко") == manual_id("молоко")
    assert manual_id("молоко") != manual_id("хліб")


def test_case_and_edges_do_not_make_a_second_row():
    assert manual_id("  Молоко ") == manual_id("молоко")


def test_the_id_does_not_carry_the_guests_word():
    said = "ліки від тиску"
    assert said not in manual_id(said)
    assert manual_id(said).startswith("manual:")


def test_only_a_manual_row_answers_to_manual():
    assert is_manual(manual_id("молоко")) is True
    assert is_manual("42") is False
    assert is_manual("") is False


def test_the_same_word_under_the_same_label_says_nothing():
    assert regrouped("васабі", "васабі") is False
    assert regrouped("  Молоко ", "молоко") is False


def test_a_label_that_swallowed_the_word_says_so():
    assert regrouped("Спрайт", "напій газований · лимон-лайм") is True


def test_a_narrowed_kind_counts_as_regrouped_too():
    assert regrouped("молоко", "молоко · безлактозне") is True
