from __future__ import annotations

from komora.core.silence import MIN_ASKED, Silence, is_mute, mute_note


def test_the_broken_run_is_called_mute():
    assert is_mute(Silence(asked=41, empty=39))


def test_the_healthy_run_is_not():
    assert not is_mute(Silence(asked=36, empty=2))


def test_a_guest_with_rare_kinds_is_not_a_mute_shelf():
    assert not is_mute(Silence(asked=12, empty=4))


def test_a_short_run_is_not_judged_at_all():
    assert not is_mute(Silence(asked=2, empty=2))
    assert not is_mute(Silence(asked=MIN_ASKED - 1, empty=MIN_ASKED - 1))


def test_exactly_at_the_floor_the_share_starts_to_count():
    assert is_mute(Silence(asked=MIN_ASKED, empty=MIN_ASKED))


def test_the_share_itself_is_a_strict_boundary():
    assert not is_mute(Silence(asked=9, empty=6))
    assert is_mute(Silence(asked=9, empty=7))


def test_batches_add_up_into_one_verdict():
    seen = Silence().plus(3, 3).plus(3, 3)

    assert seen == Silence(asked=6, empty=6)
    assert is_mute(seen)


def test_an_empty_counter_divides_by_nothing():
    assert Silence().share == 0.0
    assert not is_mute(Silence())


def test_the_note_names_both_numbers_and_the_right_advice():
    said = mute_note(Silence(asked=41, empty=39))

    assert "39" in said
    assert "41" in said
    assert "ще раз" in said
