from __future__ import annotations

import pytest

from komora.core.facts import BEFORE, NAMES, Facts, size_of, unreachable
from komora.core.plan import BY_NAME, STEPS


def test_the_names_are_the_dictionarys_own_and_not_a_second_list():
    from_steps = set()
    for kind in STEPS:
        from_steps |= set(kind.needs) | set(kind.gives)

    assert from_steps == NAMES
    assert len(NAMES) > 5


def test_no_step_needs_a_fact_nobody_gives():
    assert unreachable() == ()


def test_a_foreign_name_is_refused_by_name():
    facts = Facts()

    with pytest.raises(KeyError, match="словник"):
        facts.put("шоколадка", ["є"], step="shelf.search")


def test_an_absent_fact_is_not_the_same_as_an_empty_one():
    facts = Facts()

    facts.put("candidates", {}, step="shelf.search")
    assert "candidates" in facts and facts.get("candidates") == {}
    assert facts.origin("candidates").size == 0

    with pytest.raises(ValueError, match="відсутність"):
        facts.put("lines", None, step="decide.pick")
    assert "lines" not in facts


def test_what_was_known_before_the_plan_says_so():
    facts = Facts({"branch": "id:1", "slot": {"start": "s"}})

    assert facts.origin("branch").step == BEFORE
    assert facts.origin("branch").told() == f"1 ({BEFORE})"


def test_a_none_among_the_known_is_skipped_and_not_refused():
    facts = Facts({"branch": None, "slot": {"start": "s"}})

    assert "branch" not in facts and "slot" in facts


def test_the_size_counts_the_collection_and_not_what_is_inside_it():
    assert size_of({"молоко": [1, 2, 3], "хліб": [4]}) == 2
    assert size_of([]) == 0
    assert size_of(7) == 1
    assert size_of("id:1") == 1
    assert size_of(b"id:1") == 1


def test_a_rewritten_fact_moves_its_origin_to_the_last_step():
    facts = Facts()

    facts.put("candidates", {"а": [1]}, step="shelf.search")
    facts.put("candidates", {"а": [1], "б": [2]}, step="shelf.by_article")

    origin = facts.origin("candidates")
    assert origin.step == "shelf.by_article" and origin.size == 2
    assert facts.writes("candidates") == 2
    assert facts.writes("lines") == 0


def test_binding_hands_the_step_exactly_what_it_declared():
    facts = Facts({"branch": "id:1", "slot": {"start": "s"}})
    facts.put("history", ["чек"], step="history.model")

    bound = facts.bind(BY_NAME["shelf.by_article"])

    assert bound == {"branch": "id:1", "slot": {"start": "s"}, "history": ["чек"]}


def test_what_is_missing_is_named_and_not_merely_counted():
    facts = Facts({"slot": {"start": "s"}})

    assert facts.missing(BY_NAME["shelf.by_article"]) == ("branch", "history")
    with pytest.raises(KeyError):
        facts.bind(BY_NAME["shelf.by_article"])


def test_the_ground_truth_is_sizes_and_origins_not_bodies():
    facts = Facts({"branch": "id:1"})
    facts.put("candidates", {"молоко": [{"name": "..."}] * 20}, step="shelf.search")

    assert facts.ground() == {
        "branch": f"1 ({BEFORE})",
        "candidates": "1 (shelf.search)",
    }


def test_a_fact_carries_no_axis_that_nobody_reads():
    fact = Facts().put("branch", "id:1", step=BEFORE)

    assert not hasattr(fact, "batch")
    assert fact.told() == f"1 ({BEFORE})"


def test_the_bag_counts_and_lists_what_it_holds():
    facts = Facts({"branch": "id:1"})
    facts.put("lines", ["рядок"], step="decide.pick")

    assert len(facts) == 2
    assert facts.names() == ("branch", "lines") == tuple(facts)
    assert facts.origin("candidates") is None
