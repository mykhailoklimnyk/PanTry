from decimal import Decimal

import pytest

from komora.core.substitution import (
    SHELF_TURNOVER_HOURS,
    Alternative,
    Readiness,
    Source,
    acceptance_rate,
    delivers_enough,
    is_burned,
    is_risky,
    kinship,
    pack_distance,
    pack_rank,
    price_within,
    rank_chain,
    readiness,
)


def alt(
    pid: str,
    source: Source = Source.SIMILAR,
    *,
    price: str = "50",
    accepted: int = 0,
    rejected: int = 0,
    available: bool = True,
    pack: str | None = None,
    per_unit: str | None = None,
    name: str | None = None,
) -> Alternative:
    return Alternative(
        external_product_id=pid,
        name=pid if name is None else name,
        source=source,
        price=Decimal(price),
        accepted_count=accepted,
        rejected_count=rejected,
        available=available,
        pack=None if pack is None else Decimal(pack),
        per_unit=None if per_unit is None else Decimal(per_unit),
    )


def test_unknown_alternative_is_neutral_not_zero():
    assert acceptance_rate(alt("x")) == 0.5


def test_acceptance_rate_uses_real_history():
    assert acceptance_rate(alt("x", accepted=3, rejected=1)) == 0.75


def test_twice_rejected_is_burned():
    assert is_burned(alt("x", rejected=1)) is False
    assert is_burned(alt("x", rejected=2)) is True


def test_burned_alternative_never_appears_in_the_chain():
    chain = rank_chain([alt("burned", rejected=5), alt("fresh")])
    assert [a.external_product_id for a in chain] == ["fresh"]


def test_history_beats_official_replacements_and_similar():
    chain = rank_chain(
        [
            alt("similar", Source.SIMILAR, price="10"),
            alt("official", Source.REPLACEMENTS, price="10"),
            alt("bought_before", Source.HISTORY, price="99"),
        ]
    )
    assert [a.external_product_id for a in chain] == ["bought_before", "official", "similar"]


def test_manual_choice_outranks_everything():
    chain = rank_chain([alt("history", Source.HISTORY), alt("manual", Source.MANUAL)])
    assert chain[0].external_product_id == "manual"


def test_within_one_source_acceptance_wins_then_price():
    chain = rank_chain(
        [
            alt("cheap_rejected", Source.HISTORY, price="10", accepted=1, rejected=1),
            alt("loved", Source.HISTORY, price="90", accepted=9),
            alt("cheap_unknown", Source.HISTORY, price="5"),
        ]
    )
    assert [a.external_product_id for a in chain] == ["loved", "cheap_unknown", "cheap_rejected"]


def test_unavailable_alternatives_are_filtered_out():
    chain = rank_chain([alt("gone", available=False), alt("here")])
    assert [a.external_product_id for a in chain] == ["here"]


def test_exclusions_are_respected():
    chain = rank_chain([alt("fish"), alt("cheese")], excluded_ids=frozenset({"fish"}))
    assert [a.external_product_id for a in chain] == ["cheese"]


def test_chain_is_capped_because_the_comment_field_is_one_line():
    chain = rank_chain([alt(str(i)) for i in range(10)])
    assert len(chain) == 3


def test_chain_length_is_configurable():
    assert len(rank_chain([alt(str(i)) for i in range(10)], max_length=1)) == 1
    assert rank_chain([alt("a")], max_length=0) == ()


def test_negative_chain_length_is_rejected():
    with pytest.raises(ValueError, match="від'ємним"):
        rank_chain([alt("a")], max_length=-1)


def test_ranking_is_deterministic_for_identical_alternatives():
    first = rank_chain([alt("b"), alt("a")])
    second = rank_chain([alt("a"), alt("b")])
    assert [a.external_product_id for a in first] == [a.external_product_id for a in second]


def test_low_stock_means_prepare_a_substitute_in_advance():
    assert is_risky(7) is True
    assert is_risky(171) is False
    assert is_risky(10) is False


def test_unknown_stock_counts_as_risky():
    assert is_risky(None) is True


def test_a_small_leftover_asks_for_a_mandate_however_close_the_slot_is():
    assert readiness(3, hours_to_slot=0) is Readiness.REQUIRED
    assert readiness(3, hours_to_slot=48) is Readiness.REQUIRED
    assert readiness(None, hours_to_slot=1) is Readiness.REQUIRED


def test_a_full_shelf_and_a_near_slot_need_nothing():
    assert readiness(40, hours_to_slot=2) is Readiness.NONE


def test_a_distant_slot_prepares_a_line_that_is_not_at_risk_at_all():
    assert readiness(40, hours_to_slot=30) is Readiness.AHEAD


def test_the_horizon_is_a_ceiling_and_it_counts_from_itself():
    assert readiness(40, hours_to_slot=SHELF_TURNOVER_HOURS) is Readiness.AHEAD
    assert readiness(40, hours_to_slot=SHELF_TURNOVER_HOURS - 0.1) is Readiness.NONE


def test_a_slot_in_the_past_prepares_nothing():
    assert readiness(40, hours_to_slot=-5) is Readiness.NONE


def test_a_smaller_pack_does_not_deliver_what_was_promised():
    assert delivers_enough(Decimal(50), want=Decimal(500)) is False
    assert delivers_enough(Decimal(500), want=Decimal(500)) is True
    assert delivers_enough(Decimal(700), want=Decimal(500)) is True


def test_an_unknown_pack_is_not_a_wrong_pack():
    assert delivers_enough(None, want=Decimal(500)) is True
    assert delivers_enough(Decimal(50), want=None) is True


def test_three_tiers_because_the_owner_named_two_different_limits():
    same = pack_rank(Decimal(500), want=Decimal(500), usual=Decimal(500))
    bigger = pack_rank(Decimal(3000), want=Decimal(500), usual=Decimal(500))
    smaller = pack_rank(Decimal(50), want=Decimal(500), usual=Decimal(500))
    assert (same, bigger, smaller) == (0, 1, 2)


def test_a_bigger_pack_beats_a_broken_promise():
    assert pack_rank(Decimal(700), want=Decimal(500), usual=Decimal(500)) < pack_rank(
        Decimal(50), want=Decimal(500), usual=Decimal(500)
    )


def test_the_chosen_pack_is_a_floor_even_when_the_guest_buys_smaller():
    assert pack_rank(Decimal(300), want=Decimal(500), usual=Decimal(300)) == 2
    assert pack_rank(Decimal(500), want=Decimal(500), usual=Decimal(300)) == 0


def test_without_the_guests_habit_a_bigger_pack_is_not_punished():
    assert pack_rank(Decimal(3000), want=Decimal(500), usual=None) == 0


def test_a_pack_that_delivers_enough_goes_first_even_when_dearer():
    chain = rank_chain(
        [alt("mini", price="77", pack="50"), alt("bottle", price="899", pack="700")],
        want=Decimal(500),
        usual=Decimal(500),
    )
    assert [a.external_product_id for a in chain] == ["bottle", "mini"]


def test_the_pack_axis_is_a_tier_not_a_cut():
    chain = rank_chain([alt("mini", pack="50")], want=Decimal(500), usual=Decimal(500))
    assert [a.external_product_id for a in chain] == ["mini"]


def test_without_a_pack_the_order_stays_exactly_as_it_was():
    chain = rank_chain([alt("dear", price="99"), alt("cheap", price="10")])
    assert [a.external_product_id for a in chain] == ["cheap", "dear"]


def test_price_per_common_unit_orders_inside_the_tier():
    chain = rank_chain(
        [
            alt("small", price="40", pack="500", per_unit="8"),
            alt("big", price="60", pack="1000", per_unit="6"),
        ],
        want=Decimal(500),
        usual=Decimal(1000),
    )
    assert [a.external_product_id for a in chain] == ["big", "small"]


def test_one_candidate_without_a_unit_price_puts_everyone_back_on_the_tag():
    chain = rank_chain(
        [
            alt("cheap-tag", price="40", pack="500"),
            alt("cheap-unit", price="60", pack="1000", per_unit="6"),
        ],
        want=Decimal(500),
        usual=Decimal(1000),
    )
    assert [a.external_product_id for a in chain] == ["cheap-tag", "cheap-unit"]


def test_outside_his_packs_the_closest_one_wins_not_the_cheapest_per_unit():
    chain = rank_chain(
        [
            alt("litre", price="1199", pack="1000", per_unit="119.9"),
            alt("seven", price="899", pack="700", per_unit="128.4"),
        ],
        want=Decimal(500),
        usual=Decimal(500),
    )
    assert [a.external_product_id for a in chain] == ["seven", "litre"]


def test_inside_his_packs_the_better_value_still_wins():
    chain = rank_chain(
        [
            alt("near", price="60", pack="500", per_unit="12"),
            alt("value", price="80", pack="1000", per_unit="8"),
        ],
        want=Decimal(500),
        usual=Decimal(1000),
    )
    assert [a.external_product_id for a in chain] == ["value", "near"]


def test_a_broken_promise_is_ordered_by_how_broken_it_is():
    chain = rank_chain(
        [alt("mini", price="77", pack="50"), alt("third", price="500", pack="300")],
        want=Decimal(500),
        usual=Decimal(500),
    )
    assert [a.external_product_id for a in chain] == ["third", "mini"]


def test_an_unknown_pack_has_no_distance_at_all():
    assert pack_distance(None, want=Decimal(500)) == 0
    assert pack_distance(Decimal(300), want=None) == 0
    assert pack_distance(Decimal(300), want=Decimal(500)) == 200


def test_the_price_corridor_is_twice_both_ways_and_silent_without_a_price():
    assert price_within(15, 30) is True
    assert price_within(15, "7.5") is True
    assert price_within(15, 30.01) is False
    assert price_within(15, 7.49) is False
    assert price_within(15, 45) is False
    assert price_within(None, 45) is True
    assert price_within(15, None) is True
    assert price_within(0, 45) is True
    assert price_within(15, "нема") is True


def test_a_link_that_shares_only_the_kind_word_goes_to_the_tail():
    chain = rank_chain(
        [
            alt("svitanok", price="30", name="Нектар «Світанок» яблучний"),
            alt("jaffa-cherry", price="50", name="Нектар Jaffa вишневий"),
        ],
        like="Нектар Jaffa ананасовий",
    )
    assert [link.external_product_id for link in chain] == ["jaffa-cherry", "svitanok"]


def test_kinship_counts_only_words_that_name_a_product():
    assert kinship("Сік Sandora яблучний", "Сік Galicia яблучний") == 2
    assert kinship("Молоко Ферма 2,5% в/у", "Молоко Яготинське 2,6% в/у") == 1
    assert kinship("Хліб Ситий двір Пшеничний", "Хліб Ситий двір Український") == 3
    assert kinship("будь-що", "") == 0
    assert kinship("", "Молоко") == 0


def test_closeness_never_outranks_the_pack_tier():
    chain = rank_chain(
        [
            alt("mini", name="Віскі Jack Daniels Old No.7", pack="0.05"),
            alt("full", name="Віскі Jameson", pack="0.5"),
        ],
        want=Decimal("0.5"),
        like="Віскі Jack Daniels Old No.7 Tennessee",
    )
    assert chain[0].external_product_id == "full"


def test_without_a_chosen_name_the_axis_is_silent():
    links = [alt("a", price="70", name="Сир Гауда"), alt("b", price="50", name="Сир Едам")]
    assert rank_chain(links) == rank_chain(links, like="")
    assert [link.external_product_id for link in rank_chain(links, like="")] == ["b", "a"]
