import pytest

from komora.agent.basket import Tracer
from komora.core.trace import SUMMARY_CHARS, fits


@pytest.mark.long_summary
def test_the_port_names_a_too_long_phrase_instead_of_cutting_it(capsys):
    trace = Tracer()
    long_phrase = "простиня " * 40

    trace.add("step-needs", "core.cycles", {}, long_phrase)

    assert trace.steps[0].result_summary == long_phrase, "різати не можна"
    said = capsys.readouterr().out
    assert "trace.long_summary" in said
    assert "step-needs" in said and str(len(long_phrase)) in said


def test_a_phrase_within_the_ceiling_says_nothing_to_the_log(capsys):
    trace = Tracer()
    trace.add("step-needs", "core.cycles", {"беру": ["молоко"]}, "беру 1 вид")

    assert "trace.long_summary" not in capsys.readouterr().out
    assert fits(trace.steps[0].result_summary)
    assert len(trace.steps[0].result_summary) <= SUMMARY_CHARS
