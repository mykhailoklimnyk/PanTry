from datetime import UTC, date, datetime
from decimal import Decimal

from komora.core.delivery import CostTier, DeliveryTerms
from komora.core.slots import (
    REASON_NOT_AVAILABLE,
    REASON_ORDER_MIN,
    REASON_WEIGHT_MAX,
    Basis,
    Restricted,
    Slot,
    SlotConstraints,
    basis_note,
    choose,
    day_of,
    first_usable,
    hours_until,
    is_usable,
    no_free_note,
    restriction_reason,
    same_moment,
    slot_blockers,
    window_note,
)

TERMS = DeliveryTerms(
    base_cost=Decimal("89"),
    tiers=(CostTier(cost=Decimal("59"), from_order_cost=Decimal("1199")),),
    min_order_cost=Decimal("599"),
    max_weight_kg=Decimal("50"),
)


def slot(
    hour: int,
    *,
    available: bool = True,
    constraints: SlotConstraints | None = None,
    day: int = 13,
) -> Slot:
    return Slot(
        start=datetime(2026, 8, day, hour, tzinfo=UTC),
        end=datetime(2026, 8, day, hour + 2, tzinfo=UTC),
        available=available,
        delivery_type="DeliveryHome",
        terms=TERMS,
        constraints=constraints or SlotConstraints(),
    )


def test_clean_slot_has_no_blockers():
    assert slot_blockers(slot(8), order_total=Decimal("700"), total_weight_kg=Decimal("10")) == ()
    assert is_usable(slot(8), order_total=Decimal("700")) is True


def test_unavailable_slot_is_blocked():
    assert REASON_NOT_AVAILABLE in slot_blockers(slot(8, available=False))


def test_first_slot_of_the_day_refuses_cooked_food():
    morning = slot(6, constraints=SlotConstraints(cooked_food=True, own_cooking=True))

    reasons = slot_blockers(morning, cart_categories=[Restricted.COOKED_FOOD])

    assert restriction_reason(Restricted.COOKED_FOOD) in reasons
    assert restriction_reason(Restricted.OWN_COOKING) not in reasons


def test_restriction_only_fires_for_categories_actually_in_the_cart():
    morning = slot(6, constraints=SlotConstraints(cooked_food=True, own_cooking=True))
    assert slot_blockers(morning, cart_categories=[]) == ()


def test_all_reasons_are_reported_at_once():
    reasons = slot_blockers(
        slot(6, available=False, constraints=SlotConstraints(cooked_food=True)),
        cart_categories=[Restricted.COOKED_FOOD],
        order_total=Decimal("100"),
        total_weight_kg=Decimal("80"),
    )

    assert set(reasons) == {
        REASON_NOT_AVAILABLE,
        restriction_reason(Restricted.COOKED_FOOD),
        REASON_ORDER_MIN,
        REASON_WEIGHT_MAX,
    }


def test_thresholds_are_inclusive():
    assert REASON_ORDER_MIN not in slot_blockers(slot(8), order_total=Decimal("599"))
    assert REASON_ORDER_MIN in slot_blockers(slot(8), order_total=Decimal("598.99"))
    assert REASON_WEIGHT_MAX not in slot_blockers(slot(8), total_weight_kg=Decimal("50"))
    assert REASON_WEIGHT_MAX in slot_blockers(slot(8), total_weight_kg=Decimal("50.01"))


def test_unnamed_weight_limit_blocks_nothing():
    pickup = Slot(
        start=datetime(2026, 8, 13, 8, tzinfo=UTC),
        end=datetime(2026, 8, 13, 8, 30, tzinfo=UTC),
        available=True,
        delivery_type="SelfPickup",
        terms=DeliveryTerms(
            base_cost=Decimal(0),
            tiers=(),
            min_order_cost=Decimal("199"),
            max_weight_kg=Decimal(0),
        ),
        constraints=SlotConstraints(),
    )

    assert REASON_WEIGHT_MAX not in slot_blockers(pickup, total_weight_kg=Decimal("120"))


def test_unchecked_dimensions_are_not_invented():
    assert slot_blockers(slot(8)) == ()


def test_first_usable_skips_blocked_slots_and_keeps_time_order():
    slots = [
        slot(10),
        slot(6, constraints=SlotConstraints(cooked_food=True)),
        slot(8, available=False),
    ]

    chosen = first_usable(slots, cart_categories=[Restricted.COOKED_FOOD])

    assert chosen is not None
    assert chosen.start.hour == 10


def test_first_usable_returns_none_when_nothing_fits():
    assert first_usable([slot(6, available=False), slot(8, available=False)]) is None


def test_constraints_map_to_categories():
    limited = SlotConstraints(alcohol=True, tobacco=True).limited()
    assert limited == frozenset({Restricted.ALCOHOL, Restricted.TOBACCO})
    assert SlotConstraints().limited() == frozenset()


def test_the_cart_slot_wins_while_it_is_still_free():
    choice = choose([("08:00", True), ("10:00", True)], wanted="10:00")

    assert choice is not None
    assert choice.index == 1
    assert choice.basis is Basis.CART
    assert (choice.free, choice.offered) == (2, 2)


def test_a_taken_cart_slot_falls_back_to_the_first_free_one():
    choice = choose([("08:00", False), ("10:00", True), ("12:00", True)], wanted="08:00")

    assert choice is not None
    assert choice.index == 1
    assert choice.basis is Basis.FIRST
    assert (choice.free, choice.offered) == (2, 3)


def test_a_single_free_slot_is_not_called_the_first_one():
    choice = choose([("08:00", False), ("10:00", True)], wanted=None)

    assert choice is not None
    assert choice.basis is Basis.ONLY


def test_the_cart_slot_beats_even_a_lonely_alternative():
    choice = choose([("08:00", False), ("10:00", True)], wanted="10:00")

    assert choice is not None
    assert choice.basis is Basis.CART


def test_nothing_free_means_no_choice_at_all():
    assert choose([("08:00", False)], wanted="08:00") is None
    assert choose([], wanted=None) is None


def test_a_cart_slot_that_is_no_longer_offered_is_not_matched():
    choice = choose([("10:00", True), ("12:00", True)], wanted="06:00")

    assert choice is not None
    assert choice.basis is Basis.FIRST


def test_the_note_names_our_own_window_and_not_the_whole_week():
    only = basis_note(choose([("08:00", False), ("10:00", True)], wanted=None))
    assert only == "єдиний вільний з 2 найближчих — вибору не було"

    first = basis_note(choose([("08:00", True), ("10:00", True)], wanted=None))
    assert first == "перший вільний із 2 у 2 найближчих"

    kept = basis_note(choose([("08:00", True)], wanted="08:00"))
    assert kept == "слот уже стояв у кошику і досі вільний — не міняли"


def test_the_refusal_counts_the_windows_we_got_not_the_ceiling_we_asked():
    assert no_free_note("SelfPickup", 3) == (
        "серед 3 найближчих слотів SelfPickup немає жодного вільного"
    )


def test_a_single_taken_window_is_still_counted_as_one():
    assert no_free_note("DeliveryHome", 1) == (
        "серед 1 найближчих слотів DeliveryHome немає жодного вільного"
    )


def test_no_windows_at_all_is_not_the_same_as_all_of_them_taken():
    assert no_free_note("DeliveryHome", 0) == "на DeliveryHome не прийшло жодного слота"


NOW = datetime(2026, 8, 23, 12, 0, tzinfo=UTC)


def test_the_gap_to_the_slot_is_counted_in_hours():
    assert hours_until("2026-08-24T18:00:00+00:00", now=NOW) == 30
    assert hours_until("2026-08-23T14:30:00+00:00", now=NOW) == 2.5


def test_a_slot_that_already_started_gives_a_negative_gap():
    assert hours_until("2026-08-23T09:00:00+00:00", now=NOW) == -3


def test_a_date_without_a_zone_is_read_in_the_zone_of_now():
    assert hours_until("2026-08-24T12:00:00", now=NOW) == 24


def test_the_delivery_day_is_the_reference_point_for_freshness():
    assert day_of("2026-08-25T18:00:00+00:00", now=NOW) == date(2026, 8, 25)


def test_a_day_without_a_slot_is_none_not_today():
    assert day_of(None, now=NOW) is None
    assert day_of("завтра вранці", now=NOW) is None


def test_an_unreadable_slot_reads_as_a_near_one():
    assert hours_until("завтра вранці", now=NOW) == 0.0
    assert hours_until(None, now=NOW) == 0.0
    assert hours_until("", now=NOW) == 0.0


def test_the_window_of_today_is_named_today_and_in_kyiv_hours():
    assert (
        window_note("2026-08-23T14:00:00+00:00", "2026-08-23T16:00:00+00:00", now=NOW)
        == "сьогодні 17:00–19:00"
    )


def test_tomorrow_is_named_tomorrow_and_the_rest_by_weekday():
    assert (
        window_note("2026-08-24T06:00:00+00:00", "2026-08-24T08:00:00+00:00", now=NOW)
        == "завтра 09:00–11:00"
    )
    assert (
        window_note("2026-08-26T06:00:00+00:00", "2026-08-26T08:00:00+00:00", now=NOW)
        == "ср 09:00–11:00"
    )


def test_beyond_a_week_the_weekday_stops_naming_the_day():
    assert (
        window_note("2026-09-04T06:00:00+00:00", "2026-09-04T08:00:00+00:00", now=NOW)
        == "пт 04.09 09:00–11:00"
    )


def test_a_naive_date_is_read_in_the_zone_of_now():
    assert window_note("2026-08-23T14:00:00", "2026-08-23T16:00:00", now=NOW).startswith("сьогодні")


def test_an_unreadable_window_is_given_back_as_it_came():
    assert window_note("завтра вранці", "опівдні", now=NOW) == "завтра вранці — опівдні"
    assert window_note("2026-08-23T14:00:00+00:00", None, now=NOW) == "2026-08-23T14:00:00+00:00"
    assert window_note(None, None, now=NOW) == "час не назвали"


def test_one_moment_written_two_ways_is_still_one_moment():
    assert same_moment("2026-08-23T14:00:00Z", "2026-08-23T14:00:00+00:00")
    assert same_moment("2026-08-23T17:00:00+03:00", "2026-08-23T14:00:00+00:00")
    assert same_moment("2026-08-23T14:00:00", "2026-08-23T14:00:00")


def test_two_different_moments_stay_different():
    assert not same_moment("2026-08-23T14:00:00Z", "2026-08-23T16:00:00Z")
    assert not same_moment("2026-08-23T14:00:00Z", None)
    assert not same_moment(None, "2026-08-23T14:00:00Z")
    assert same_moment("завтра вранці", "завтра вранці")
    assert not same_moment("завтра вранці", "2026-08-23T14:00:00Z")
    assert same_moment(None, None)
