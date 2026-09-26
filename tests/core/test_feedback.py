from __future__ import annotations

import pytest

from komora.core.feedback import (
    Changes,
    Contacts,
    changes_of,
    collector_swaps,
    contacts_of,
    reach_note,
)


def test_the_live_cart_words_are_the_ones_we_parse():
    assert changes_of("approvedChanges") is Changes.APPROVED
    assert changes_of("disapprovedChanges") is Changes.DISAPPROVED
    assert contacts_of("call") is Contacts.CALL
    assert contacts_of("doNotCall") is Contacts.DO_NOT_CALL


@pytest.mark.parametrize("raw", ["", "approved", "APPROVEDCHANGES", "call ", None, 1, True])
def test_an_unknown_word_is_not_knowledge(raw: object):
    assert changes_of(raw) is None
    assert contacts_of(raw) is None


def test_only_the_ban_kills_the_collector_hand():
    assert collector_swaps(Changes.APPROVED) is True
    assert collector_swaps(Changes.DISAPPROVED) is False


def test_not_checked_is_a_third_state_and_not_a_no():
    assert collector_swaps(None) is None


OURS = "до слота заміню сам — ре-валідація галочки не питає"


def test_our_own_hand_is_named_in_every_answer():
    for state in (True, False, None):
        assert reach_note(state).endswith(OURS)


def test_the_note_promises_the_collector_only_when_he_may_act():
    assert reach_note(True).startswith("мандати ляжуть у comment збирачу; ")
    assert reach_note(False).startswith(
        "мандат біля полиці не спрацює: у замовленні стоїть "
        "«не збирайте те, що потребує уточнень»; "
    )
    assert reach_note(None).startswith(
        "чи прочитає мандат збирач — не звіряли, галочка замін не читалась; "
    )
