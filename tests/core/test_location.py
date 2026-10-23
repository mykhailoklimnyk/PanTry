from __future__ import annotations

import pytest

from komora.core.location import (
    HOME_DELIVERY,
    SOURCE_NOTES,
    Address,
    Location,
    Source,
    choose_address,
    decide,
    label_of,
    source_note,
)

HOME = Address(label="Вінниця, вулиця Соборна, 1", latitude=49.2, longitude=28.4, id="a-1")
WORK = Address(label="Вінниця, вулиця Пирогова, 2", latitude=49.3, longitude=28.5, id="a-2")


def test_label_collects_parts_in_reading_order():
    assert (
        label_of(city="Вінниця", street="вулиця Соборна", building="1", apartment="2")
        == "Вінниця, вулиця Соборна, 1, кв. 2"
    )


def test_label_without_apartment_has_no_tail():
    assert label_of(city="Вінниця", street="вулиця Соборна", building="1") == (
        "Вінниця, вулиця Соборна, 1"
    )


def test_missing_parts_leave_no_empty_commas():
    assert label_of(street="вулиця Соборна", building="1") == "вулиця Соборна, 1"


def test_blank_parts_count_as_missing():
    assert label_of(city="  ", street="вулиця Соборна", building="  1 ") == "вулиця Соборна, 1"


def test_apartment_alone_still_says_what_it_is():
    assert label_of(apartment="76") == "кв. 76"


def test_nothing_at_all_is_an_empty_string():
    assert label_of() == ""


def test_guest_choice_wins_over_order_in_the_account():
    assert choose_address([HOME, WORK], preferred_id="a-2") is WORK


def test_without_a_choice_takes_the_first():
    assert choose_address([HOME, WORK]) is HOME


def test_unknown_choice_falls_back_to_the_first_instead_of_nothing():
    assert choose_address([HOME, WORK], preferred_id="a-999") is HOME


def test_empty_account_has_nothing_to_choose():
    assert choose_address([]) is None
    assert choose_address([], preferred_id="a-1") is None


def test_address_beats_cart_and_config():
    assert decide(from_address="b-address", from_cart="b-cart", from_config="b-config") == (
        "b-address",
        Source.ADDRESS,
    )


def test_cart_is_second_when_there_is_no_address():
    assert decide(from_cart="b-cart", from_config="b-config") == ("b-cart", Source.CART)


def test_config_is_the_last_resort_and_says_so():
    assert decide(from_config="b-config") == ("b-config", Source.CONFIG)


def test_no_source_at_all_is_named_none_not_guessed():
    assert decide() == (None, Source.NONE)


@pytest.mark.parametrize("blank", ["", None])
def test_blank_source_is_skipped_like_a_missing_one(blank):
    assert decide(from_address=blank, from_cart="b-cart") == ("b-cart", Source.CART)


def test_branch_for_type_wins_over_the_general_one():
    place = Location(
        branch_id="b-home",
        source=Source.ADDRESS,
        branches={HOME_DELIVERY: "b-home", "LongDelivery": "b-long"},
    )
    assert place.branch_for("LongDelivery") == "b-long"


def test_type_without_its_own_branch_falls_back_to_the_general_one():
    place = Location(branch_id="b-home", source=Source.ADDRESS, branches={HOME_DELIVERY: "b-home"})
    assert place.branch_for("SelfPickup") == "b-home"


def test_empty_branch_for_type_is_not_a_branch():
    place = Location(branch_id="b-home", source=Source.ADDRESS, branches={"SelfPickup": ""})
    assert place.branch_for("SelfPickup") == "b-home"


def test_nothing_known_stays_nothing():
    place = Location()
    assert place.branch_for(HOME_DELIVERY) is None
    assert place.known is False


def test_known_is_about_the_branch_not_about_the_address():
    assert Location(branch_id="b-cart", source=Source.CART).known is True


def test_address_branch_ignores_the_general_fallback():
    place = Location(branch_id="b-config", source=Source.CONFIG)
    assert place.address_branch(HOME_DELIVERY) is None


def test_address_branch_falls_back_to_home_delivery():
    place = Location(branch_id="b-home", source=Source.ADDRESS, branches={HOME_DELIVERY: "b-home"})
    assert place.address_branch("SelfPickup") == "b-home"


def test_address_branch_prefers_its_own_type():
    place = Location(
        branch_id="b-home",
        source=Source.ADDRESS,
        branches={HOME_DELIVERY: "b-home", "LongDelivery": "b-long"},
    )
    assert place.address_branch("LongDelivery") == "b-long"


def test_offered_none_means_we_did_not_ask():
    assert Location(branch_id="b-config", source=Source.CONFIG).offers(HOME_DELIVERY) is None


def test_offered_empty_means_they_do_not_deliver_here():
    place = Location(branch_id="b-home", source=Source.ADDRESS, offered=frozenset())
    assert place.offers(HOME_DELIVERY) is False


def test_offered_answers_yes_and_no_separately():
    place = Location(
        branch_id="b-home", source=Source.ADDRESS, offered=frozenset({HOME_DELIVERY, "NovaPoshta"})
    )
    assert place.offers(HOME_DELIVERY) is True
    assert place.offers("SelfPickup") is False


@pytest.mark.parametrize("source", list(Source))
def test_every_source_has_its_own_words(source):
    assert source_note(source) == SOURCE_NOTES[source]
    assert source_note(source).strip()


def test_sources_do_not_share_wording():
    assert len(set(SOURCE_NOTES.values())) == len(SOURCE_NOTES)


def test_every_source_but_the_address_leaves_an_action():
    for state in Source:
        if state is Source.ADDRESS:
            continue
        assert "назви адресу" in source_note(state), state


def test_the_words_of_a_foreign_shelf_are_pinned_whole():
    assert SOURCE_NOTES[Source.CART] == (
        "магазин узято з кошика, який уже є в акаунті — назви адресу, якщо веземо не туди"
    )
    assert SOURCE_NOTES[Source.CONFIG] == (
        "магазин з налаштувань сервера, не за твоєю адресою — "
        "назви адресу, і ціни з наявністю будуть з твоєї філії"
    )


def test_the_address_line_promises_nothing_to_do():
    assert "назви адресу" not in source_note(Source.ADDRESS)


def test_unknown_source_still_gets_an_honest_line():
    assert source_note("вигадане") == SOURCE_NOTES[Source.NONE]  # type: ignore[arg-type]


def test_address_carries_coordinates_because_they_open_the_chain():
    assert (HOME.latitude, HOME.longitude) == (49.2, 28.4)
    assert HOME.tag is None
