from __future__ import annotations

import pytest

from komora.core.spine import (
    BATCH_MAX,
    MAX_TURNS,
    STUCK_TURNS,
    Halt,
    Progress,
    halt,
    trim,
)


def running() -> Progress:
    return Progress(turn=1, said_stop=False, unmet=("кошик має рядки",))


def test_a_healthy_turn_does_not_stop() -> None:
    assert halt(running()) is None


def test_the_goal_alone_stops_the_run() -> None:
    assert halt(Progress(turn=1, said_stop=False)) is Halt.DONE
    assert halt(Progress(turn=1, said_stop=True)) is Halt.DONE


def test_stop_before_the_decision_does_not_stop_the_run() -> None:
    assert halt(Progress(turn=1, said_stop=True, unmet=("намір «хліб» загублено",))) is None


def test_stop_over_an_unclosed_write_does_not_stop_the_run() -> None:
    assert halt(Progress(turn=1, said_stop=True, fatal="запис без перечитування")) is None
    assert halt(Progress(turn=1, said_stop=False, fatal="запис без перечитування")) is None


def test_a_broken_batch_outranks_every_other_reason() -> None:
    broken = Progress(turn=MAX_TURNS, said_stop=True, broken=True, idle=STUCK_TURNS)
    assert halt(broken) is Halt.BROKEN


def test_the_ceiling_stops_exactly_at_its_number() -> None:
    assert halt(Progress(turn=MAX_TURNS - 1, said_stop=False, unmet=("є",))) is None
    assert halt(Progress(turn=MAX_TURNS, said_stop=False, unmet=("є",))) is Halt.CEILING


def test_a_goal_reached_on_the_last_allowed_turn_is_success_not_a_cutoff() -> None:
    assert halt(Progress(turn=MAX_TURNS, said_stop=True)) is Halt.DONE


def test_the_idle_counter_stops_exactly_at_its_number() -> None:
    assert halt(Progress(turn=1, said_stop=False, unmet=("є",), idle=STUCK_TURNS - 1)) is None
    assert halt(Progress(turn=1, said_stop=False, unmet=("є",), idle=STUCK_TURNS)) is Halt.STUCK


def test_one_empty_turn_is_not_yet_a_stuck_loop() -> None:
    assert STUCK_TURNS > 1
    assert halt(Progress(turn=1, said_stop=False, unmet=("є",), idle=1)) is None


def test_the_ceiling_is_judged_before_the_idle_loop() -> None:
    both = Progress(turn=MAX_TURNS, said_stop=False, unmet=("є",), idle=STUCK_TURNS)
    assert halt(both) is Halt.CEILING


def test_the_ceiling_is_a_parameter_so_a_run_may_forbid_the_loop_entirely() -> None:
    assert halt(Progress(turn=0, said_stop=False, unmet=("є",)), ceiling=0) is Halt.CEILING


@pytest.mark.parametrize("count", [0, 1, BATCH_MAX - 1, BATCH_MAX])
def test_a_batch_within_the_cap_keeps_every_step(count: int) -> None:
    names = tuple(f"крок{n}" for n in range(count))
    kept, cut = trim(names)
    assert kept == names
    assert cut == ()


def test_a_batch_over_the_cap_loses_its_TAIL_and_the_tail_is_named() -> None:
    names = tuple(f"крок{n}" for n in range(BATCH_MAX + 2))
    kept, cut = trim(names)
    assert kept == names[:BATCH_MAX]
    assert cut == names[BATCH_MAX:]
    assert len(kept) + len(cut) == len(names)


def test_the_cap_is_a_parameter_and_the_split_holds_at_one() -> None:
    kept, cut = trim(("а", "б", "в"), cap=1)
    assert kept == ("а",)
    assert cut == ("б", "в")


def test_every_reason_to_stop_says_something_different() -> None:
    words = [halt.value for halt in Halt]
    assert len(set(words)) == len(words)
    assert all(word.strip() for word in words)


def test_the_model_word_does_not_stop_the_loop_by_default() -> None:
    stuck = Progress(turn=1, said_stop=True, unmet=("борг",))

    assert halt(stuck, ceiling=6) is None


def test_the_model_word_stops_the_loop_where_it_is_asked_for() -> None:
    stuck = Progress(turn=1, said_stop=True, unmet=("борг",))

    assert halt(stuck, ceiling=6, obey_stop=True) is Halt.SAID


def test_the_ceiling_stays_older_than_the_model_word() -> None:
    quiet = Progress(turn=6, said_stop=False, unmet=("борг",))

    assert halt(quiet, ceiling=6, obey_stop=True) is Halt.CEILING


def test_a_met_goal_beats_the_model_word() -> None:
    done = Progress(turn=1, said_stop=True, unmet=())

    assert halt(done, ceiling=6, obey_stop=True) is Halt.DONE


def test_waiting_for_the_guest_is_not_the_same_as_a_met_goal() -> None:
    asked = Progress(turn=1, said_stop=False, unmet=("мовчать 12",), waiting=True)

    assert halt(asked, ceiling=6) is Halt.WAITING


def test_a_met_goal_beats_waiting_for_the_guest() -> None:
    done = Progress(turn=1, said_stop=False, unmet=(), waiting=True)

    assert halt(done, ceiling=6) is Halt.DONE


def test_without_questions_nothing_waits() -> None:
    quiet = Progress(turn=1, said_stop=False, unmet=("мовчать 12",))

    assert halt(quiet, ceiling=6) is None
