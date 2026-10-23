from __future__ import annotations

from komora.core.slicing import Habit, form_of, habit, is_sliced, note, wish


def test_the_shelf_says_sliced_four_different_ways():
    assert is_sliced("Хліб Київхліб Тост світлий нарізаний")
    assert is_sliced("Сьомга слабосолена «Премія», нарізка")
    assert is_sliced("Хліб Agrola Обідній Вінницький нарізний")
    assert is_sliced("Хліб Agrola тостовий ніжний різаний")
    assert is_sliced("Сир плавлений «Премія» Чеддер скибочками 36,2%")


def test_silence_is_not_a_claim_about_the_whole_loaf():
    assert not is_sliced("Хліб «Рум'янець» цільнозерновий пшеничний")
    assert not is_sliced("Батон Київхліб Пшеничний")


def test_a_number_in_the_name_is_not_a_word():
    assert not is_sliced("2,5% 400г")


def test_the_form_has_words_for_both_sides():
    assert form_of("Хліб Київхліб Столичний житній нарізаний") == "нарізаний"
    assert form_of("Хліб «Рум'янець» «Литовський»") == "без нарізки"


def test_one_receipt_is_not_a_habit():
    assert habit([("Сьомга «Премія» нарізка", 1)]).sliced is None


def test_a_tie_leaves_no_default():
    both = [("Хліб Київхліб Тост нарізаний", 1), ("Хліб Київхліб Оксамитовий", 1)]
    assert habit(both).sliced is None


def test_the_majority_wins_and_names_its_basis():
    guest = habit(
        [
            ("Хліб «Рум'янець» цільнозерновий пшеничний", 7),
            ("Хліб Рум'янець З льоном нарізний", 1),
        ]
    )
    assert guest.sliced is False
    assert guest.says() == "у твоїх чеках цей вид 7 без нарізки, 1 нарізаним"


def test_a_sliced_habit_is_just_as_possible():
    guest = habit([("Хліб тостовий нарізаний", 4), ("Хліб цільнозерновий", 1)])
    assert guest.sliced is True
    assert guest.says() == "у твоїх чеках цей вид 1 без нарізки, 4 нарізаним"


def test_receipts_without_purchases_do_not_vote():
    guest = habit([("Хліб нарізаний", 0), ("Хліб цільний", 3), ("Хліб інший", -2)])
    assert guest.sliced is False
    assert guest.sliced_receipts == 0
    assert guest.plain_receipts == 3


def test_an_empty_history_says_it_met_nothing():
    assert habit([]).says() == "у твоїх чеках цей вид не траплявся"


def test_the_wish_is_silent_when_the_shelf_has_no_second_form():
    assert (
        wish(
            "Хліб «Рум'янець» цільнозерновий пшеничний",
            ["Хліб «Рум'янець» цільнозерновий пшеничний", "Хліб «Рум'янець» «Литовський»"],
        )
        is None
    )


def test_the_wish_names_the_form_when_the_shelf_has_both():
    options = [
        "Хліб «Рум'янець» цільнозерновий пшеничний",
        "Хліб «Рум'янець» «Австрійський» нарізаний",
    ]
    assert wish("Хліб «Рум'янець» цільнозерновий пшеничний", options) == "без нарізки"
    assert wish("Хліб «Рум'янець» «Австрійський» нарізаний", options) == "нарізаний"


def test_the_wish_needs_no_options_of_its_own_kind_to_stay_quiet():
    assert wish("Хліб Київхліб Пшеничний нарізаний", []) is None


def test_the_note_stays_silent_when_the_form_matches_the_habit():
    guest = Habit(False, 1, 7)
    assert note("Хліб «Рум'янець» цільнозерновий пшеничний", guest) is None


def test_the_note_speaks_when_the_form_disagrees():
    guest = Habit(False, 1, 7)
    assert note("Хліб «Рум'янець» «Австрійський» нарізаний", guest) == (
        "у твоїх чеках цей вид 7 без нарізки, 1 нарізаним"
    )


def test_without_a_habit_there_is_nothing_to_disagree_with():
    assert note("Хліб Київхліб Тост світлий нарізаний", Habit(None, 1, 1)) is None


def test_every_sku_of_the_kind_adds_up():
    guest = habit(
        [
            ("Хліб Київхліб Тост світлий нарізаний", 2),
            ("Хліб Київхліб Столичний житній нарізаний", 3),
            ("Хліб Київхліб Оксамитовий", 1),
        ]
    )
    assert (guest.sliced_receipts, guest.plain_receipts) == (5, 1)
    assert guest.sliced is True

    plain = habit(
        [
            ("Хліб Рум'янець цільнозерновий", 4),
            ("Хліб Рум'янець Литовський", 2),
            ("Хліб Рум'янець з льоном нарізаний", 1),
        ]
    )
    assert (plain.sliced_receipts, plain.plain_receipts) == (1, 6)
    assert plain.sliced is False


def test_two_receipts_are_already_a_habit_when_they_agree():
    assert habit([("Хліб цільнозерновий", 2)]).sliced is False
    assert habit([("Хліб тостовий нарізаний", 1), ("Хліб Столичний нарізаний", 1)]).sliced is True


def test_no_habit_still_shows_the_distribution():
    tie = habit([("Хліб нарізаний", 3), ("Хліб цільний", 3)])
    assert tie.sliced is None
    assert (tie.sliced_receipts, tie.plain_receipts) == (3, 3)
    assert tie.says() == "у твоїх чеках цей вид 3 без нарізки, 3 нарізаним"
