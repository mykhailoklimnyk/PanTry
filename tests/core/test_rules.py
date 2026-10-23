from __future__ import annotations

import re

from komora.core.rules import (
    MAX_LABEL,
    NO_RESTRICTION,
    clean,
    key,
    own_rule,
    profile_rule,
    profile_rules,
    rule_id,
    too_long,
)


def test_no_restrictions_comes_as_a_row_not_as_an_empty_list():
    assert profile_rule(NO_RESTRICTION, None) is None
    assert profile_rules([{"slug": "all-food", "name": None}]) == []


def test_a_restriction_without_a_name_still_gets_words():
    rule = profile_rule("gluten-free", None)
    assert rule is not None
    assert rule.label == "без глютену"
    assert rule.permanent is True
    assert rule.active is True


def test_their_name_beats_our_dictionary():
    rule = profile_rule("gluten-free", "Без глютену (їхніми словами)")
    assert rule is not None
    assert rule.label == "Без глютену (їхніми словами)"


def test_an_unknown_slug_is_shown_as_is_not_swallowed():
    rule = profile_rule("halal", None)
    assert rule is not None
    assert rule.label == "halal"


def test_an_empty_slug_is_not_a_rule():
    assert profile_rule("", None) is None
    assert profile_rule(None, "щось") is None


def test_the_same_slug_twice_is_one_chip():
    rules = profile_rules(
        [{"slug": "vegan", "name": None}, {"slug": "vegan", "name": "веганське"}]
    )
    assert [rule.id for rule in rules] == ["profile:vegan"]


def test_the_whole_list_keeps_their_names_not_only_our_dictionary():
    rules = profile_rules([{"slug": "vegan", "name": "Веганський раціон"}])

    assert [rule.label for rule in rules] == ["Веганський раціон"]


def test_two_different_restrictions_are_two_chips():
    rules = profile_rules(
        [{"slug": "vegan", "name": None}, {"slug": "gluten-free", "name": None}]
    )

    assert [rule.id for rule in rules] == ["profile:vegan", "profile:gluten-free"]


def test_profile_rules_survive_a_row_that_is_not_a_restriction():
    rules = profile_rules(
        [{"slug": "all-food", "name": None}, {"slug": "lactose-free", "name": None}]
    )
    assert [rule.label for rule in rules] == ["без лактози"]


def test_the_id_carries_no_words_of_the_guest():
    ident = rule_id("без свинини, але індичку можна")
    assert re.fullmatch(r"rule:[0-9a-f]{16}", ident), ident
    assert "свинин" not in ident


def test_the_same_words_give_the_same_id_on_any_device():
    assert rule_id("Без свинини") == rule_id("без   свинини ")
    assert rule_id("без свинини") != rule_id("без цукру")


def test_words_are_kept_as_written():
    assert clean("  Без свинини,   але індичку   можна  ") == "Без свинини, але індичку можна"
    assert key("Без Свинини") == "без свинини"


def test_a_new_rule_starts_ACTIVE_and_carries_its_own_id():
    rule = own_rule("без свинини")

    assert rule.active is True
    assert rule.id == rule_id("без свинини")


def test_a_guest_rule_keeps_the_state_it_arrived_with():
    rule = own_rule("менше цукру", active=False)
    assert rule.active is False
    assert rule.permanent is False
    assert rule.label == "менше цукру"


def test_a_rule_longer_than_the_ceiling_is_refused_not_trimmed():
    assert too_long("а" * MAX_LABEL) is False
    assert too_long("а" * (MAX_LABEL + 1)) is True
    assert too_long(" " + "а" * MAX_LABEL + "  ") is False
