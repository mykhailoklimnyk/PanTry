from __future__ import annotations

from datetime import UTC, datetime

from komora.core.said import (
    GUEST,
    PURCHASES,
    SOURCE_MANUAL,
    SOURCE_RECEIPTS,
    Said,
    origin_of_list,
)

NOW = datetime(2026, 9, 4, 9, 0, tzinfo=UTC)
THEN = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)


def test_the_receipts_mode_reads_only_what_the_guest_typed_himself():
    assert origin_of_list(SOURCE_RECEIPTS) == GUEST


def test_the_list_mode_reads_both_origins():
    assert origin_of_list(SOURCE_MANUAL) is None


def test_an_unknown_mode_falls_back_to_the_narrow_side():
    assert origin_of_list("") == GUEST
    assert origin_of_list(PURCHASES) == GUEST


def test_silence_is_a_whole_object_and_not_a_missing_argument():
    empty = Said()

    assert empty.source == SOURCE_RECEIPTS
    assert empty.marks == {} and empty.cycles == {}
    assert empty.listed == {} and empty.written == {}
    assert list(empty.hidden) == []


def test_a_fresh_mark_is_added_to_the_others_and_wins_over_the_old_one():
    before = Said(marks={"хліб": THEN, "молоко": THEN})

    after = before.with_marks({"хліб": NOW})

    assert after.marks == {"хліб": NOW, "молоко": THEN}
    assert before.marks == {"хліб": THEN, "молоко": THEN}, "прочитане не міняється"


def test_a_named_cycle_can_be_taken_back_in_the_very_same_answer():
    before = Said(cycles={"хліб": 2})

    assert before.with_cycles({}).cycles == {}
    assert before.with_cycles({"молоко": 5}).cycles == {"молоко": 5}


def test_the_two_questions_about_the_list_stay_apart():
    said = Said(
        source=SOURCE_MANUAL,
        listed={"васабі": "васабі", "хліб": "Хліб Київський"},
        written={"васабі": "васабі"},
    )

    assert said.listed != said.written
    assert said.written == {"васабі": "васабі"}


def test_a_row_hidden_now_is_gone_from_the_very_same_answer():
    before = Said(hidden=("корм котячий",))

    assert list(before.with_hidden("шампунь", away=True).hidden) == [
        "корм котячий",
        "шампунь",
    ]
    assert list(before.with_hidden("корм котячий", away=False).hidden) == []


def test_hiding_twice_does_not_double_the_row():
    said = Said(hidden=("корм котячий",)).with_hidden("корм котячий", away=True)

    assert list(said.hidden) == ["корм котячий"]
