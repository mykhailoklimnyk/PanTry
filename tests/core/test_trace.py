from komora.core.trace import SUMMARY_CHARS, fits


def test_the_ceiling_is_the_measured_p90_of_live_phrases():
    assert SUMMARY_CHARS == 120


def test_a_phrase_exactly_at_the_ceiling_still_fits():
    assert fits("я" * SUMMARY_CHARS)
    assert not fits("я" * (SUMMARY_CHARS + 1))


def test_an_empty_phrase_fits_and_that_is_not_the_same_as_a_good_one():
    assert fits("")
