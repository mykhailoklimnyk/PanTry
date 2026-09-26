from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from komora.core import models
from komora.core.quota import (
    PRICES,
    Limits,
    Spent,
    cost_of,
    day_end,
    day_start,
    in_words,
    runs_word,
    verdict,
)

LIMITS = Limits(
    per_session=6,
    per_day=12,
    day_usd=Decimal("2.00"),
    total_usd=Decimal("40.00"),
)

NOON = datetime(2026, 8, 24, 9, 0, tzinfo=UTC)


def test_cost_counts_input_and_output_at_their_own_prices():
    price = PRICES["mistral.mistral-large-3-675b-instruct"]
    assert price.input_usd != price.output_usd

    cost = cost_of("mistral.mistral-large-3-675b-instruct", 1_000_000, 1_000_000)
    assert cost == price.input_usd + price.output_usd


def test_cost_of_a_real_run_is_cents_not_zero():
    cost = cost_of("mistral.mistral-large-3-675b-instruct", 6410, 1562)
    assert cost is not None
    assert Decimal("0.005") < cost < Decimal("0.01")


def test_an_unknown_model_has_no_price_instead_of_a_zero_one():
    assert cost_of("openai.gpt-oss-120b", 10_000, 1_000) is None
    assert cost_of("", 0, 0) is None


def test_half_a_millionth_rounds_up_not_to_the_nearest_even():
    assert cost_of("mistral.mistral-large-3-675b-instruct", 1, 0) == Decimal("0.000001")


def test_dollars_on_screen_round_up_at_the_half_cent():
    result = verdict(LIMITS, Spent(total_usd=Decimal("40.005")), now=NOON)
    assert result.headline == "бюджет моделі вичерпано: $40.01 з $40.00"


def test_a_priced_model_with_no_tokens_costs_nothing():
    assert cost_of("mistral.devstral-2-123b", 0, 0) == Decimal(0)


def test_every_model_we_offer_has_a_price():
    assert set(PRICES) == {
        "mistral.mistral-large-3-675b-instruct",
        "mistral.devstral-2-123b",
        "gpt-5.6-luna",
    }
    assert {row.id for row in models.RECOMMENDED} <= set(PRICES)


def test_the_day_belongs_to_the_guest_not_to_utc():
    night = datetime(2026, 8, 24, 22, 30, tzinfo=UTC)
    assert day_start(night) == datetime(2026, 8, 24, 21, 0, tzinfo=UTC)
    assert day_end(night) == datetime(2026, 8, 25, 21, 0, tzinfo=UTC)


def test_the_day_is_a_calendar_day_not_twenty_four_hours():
    inside = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
    assert day_start(inside) == datetime(2026, 10, 24, 21, 0, tzinfo=UTC)
    assert day_end(inside) == datetime(2026, 10, 25, 22, 0, tzinfo=UTC)
    assert day_end(inside) - day_start(inside) == timedelta(hours=25)


def test_the_start_of_the_day_is_the_end_of_the_previous_one():
    assert day_end(NOON) - day_start(NOON) == timedelta(hours=24)


def test_the_boundary_is_midnight_exactly_seconds_included():
    messy = datetime(2026, 8, 24, 9, 37, 41, 123456, tzinfo=UTC)
    assert day_start(messy) == datetime(2026, 8, 23, 21, 0, tzinfo=UTC)
    assert day_end(messy) == datetime(2026, 8, 24, 21, 0, tzinfo=UTC)


def test_runs_are_counted_in_words_a_person_would_say():
    assert runs_word(1) == "прогін"
    assert runs_word(2) == "прогони"
    assert runs_word(4) == "прогони"
    assert runs_word(5) == "прогонів"
    assert runs_word(0) == "прогонів"


def test_the_teens_are_the_exception_every_plural_rule_forgets():
    assert runs_word(11) == "прогонів"
    assert runs_word(12) == "прогонів"
    assert runs_word(14) == "прогонів"
    assert runs_word(21) == "прогін"
    assert runs_word(22) == "прогони"
    assert runs_word(111) == "прогонів"


def test_waiting_is_said_in_hours_when_it_is_hours():
    now = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
    assert in_words(now, now + timedelta(minutes=40)) == "через 40 хв"
    assert in_words(now, now + timedelta(minutes=59)) == "через 59 хв"
    assert in_words(now, now + timedelta(minutes=60)) == "через 1 год"
    assert in_words(now, now + timedelta(hours=6, minutes=47)) == "через 7 год"


def test_an_hour_is_sixty_minutes_and_the_rounding_shows_it():
    now = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
    assert in_words(now, now + timedelta(minutes=1425)) == "через 24 год"


def test_a_moment_already_past_is_zero_not_a_negative_wait():
    now = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)
    assert in_words(now, now - timedelta(hours=3)) == "через 0 хв"


def test_the_state_line_names_both_ceilings_before_either_fires():
    result = verdict(LIMITS, Spent(session_runs=2, day_runs=5), now=NOON)
    assert result.allowed
    assert result.scope is None
    assert result.action is None
    assert result.headline == "прогонів: 2 з 6 у цій сесії, 5 з 12 за добу"


def test_what_is_left_is_the_nearest_of_the_two_guest_ceilings():
    assert verdict(LIMITS, Spent(session_runs=5, day_runs=1), now=NOON).left == 1
    assert verdict(LIMITS, Spent(session_runs=1, day_runs=11), now=NOON).left == 1
    assert verdict(LIMITS, Spent(), now=NOON).left == 6


def test_money_does_not_turn_into_runs():
    rich = verdict(LIMITS, Spent(day_usd=Decimal("1.99")), now=NOON)
    assert rich.allowed
    assert rich.left == 6


def test_a_model_without_a_price_is_named_out_loud():
    result = verdict(LIMITS, Spent(day_runs=3, unpriced=2), now=NOON)
    assert result.headline == (
        "прогонів: 0 з 6 у цій сесії, 3 з 12 за добу"
        " · 2 прогони на моделі без прайсу — гроші по них не рахувались"
    )


def test_the_session_ceiling_says_what_is_left_for_the_day():
    result = verdict(LIMITS, Spent(session_runs=6, day_runs=6), now=NOON)
    assert result.scope == "session"
    assert result.headline == "стеля цієї сесії вичерпана: 6 з 6"
    assert result.action == (
        "за добу лишилось ще 6 прогонів — вони відкриються в новій сесії: "
        "«Вийти» і підключитись знову. Стеля сесії ловить зациклений клієнт, "
        "а не тебе"
    )
    assert result.resets_at is None
    assert result.left == 0


def test_the_day_ceiling_says_when_it_opens():
    result = verdict(LIMITS, Spent(session_runs=1, day_runs=12), now=NOON)
    assert result.scope == "day"
    assert result.headline == "на сьогодні стеля прогонів вичерпана: 12 з 12"
    assert result.resets_at == day_end(NOON)
    assert result.action == (
        "оновиться опівночі за Києвом, через 12 год. Комора і решта екранів "
        "працюють. Потрібно більше — напиши автору"
    )


def test_the_daily_budget_speaks_in_dollars_the_bill_will_show():
    result = verdict(LIMITS, Spent(day_usd=Decimal("2.0000001")), now=NOON)
    assert result.scope == "budget-day"
    assert result.headline == "денна межа витрат на модель вичерпана: $2.00 з $2.00"
    assert result.resets_at == day_end(NOON)
    assert result.action == (
        "оновиться опівночі за Києвом, через 12 год. Комора і решта екранів "
        "працюють. Потрібно раніше — напиши автору"
    )


def test_the_total_budget_does_not_promise_tomorrow():
    result = verdict(LIMITS, Spent(total_usd=Decimal("40.00")), now=NOON)
    assert result.scope == "budget-total"
    assert result.resets_at is None
    assert result.headline == "бюджет моделі вичерпано: $40.00 з $40.00"
    assert result.action == (
        "сам він не поновиться. Комора, кошик у «Сільпо» і решта екранів "
        "працюють — вони рахуються з чеків, не з моделі. Потрібна жива "
        "збірка — напиши автору"
    )
    assert "опівночі" not in result.action


def test_the_longest_recovery_wins_when_several_ceilings_fired():
    everything = Spent(
        session_runs=6,
        day_runs=12,
        day_usd=Decimal("5.00"),
        total_usd=Decimal("50.00"),
    )
    assert verdict(LIMITS, everything, now=NOON).scope == "budget-total"

    no_total = Spent(session_runs=6, day_runs=12, day_usd=Decimal("5.00"))
    assert verdict(LIMITS, no_total, now=NOON).scope == "budget-day"

    no_money = Spent(session_runs=6, day_runs=12)
    assert verdict(LIMITS, no_money, now=NOON).scope == "day"


def test_a_ceiling_that_fired_leaves_an_action_every_time():
    hits = [
        Spent(session_runs=6),
        Spent(day_runs=12),
        Spent(day_usd=Decimal("2.00")),
        Spent(total_usd=Decimal("40.00")),
    ]
    for spent in hits:
        result = verdict(LIMITS, spent, now=NOON)
        assert not result.allowed
        assert result.action
        assert result.headline


def test_the_ceiling_fires_exactly_at_the_limit_not_after_it():
    assert verdict(LIMITS, Spent(day_runs=11), now=NOON).allowed
    assert not verdict(LIMITS, Spent(day_runs=12), now=NOON).allowed
    assert verdict(LIMITS, Spent(day_usd=Decimal("1.999999")), now=NOON).allowed
    assert not verdict(LIMITS, Spent(day_usd=Decimal("2.00")), now=NOON).allowed


def test_insiders_see_the_same_numbers_and_the_ceiling_that_would_have_fired():
    spent = Spent(session_runs=9, day_runs=20)
    result = verdict(LIMITS, spent, now=NOON, exempt=True)
    assert result.allowed
    assert result.action is None
    assert result.headline == (
        "прогонів: 9 з 6 у цій сесії, 20 з 12 за добу"
        " · стеля спрацювала б тут, але на своїх не діє"
    )
    assert result.resets_at == day_end(NOON)


def test_an_insider_past_the_ceiling_has_nothing_left_to_count_down():
    result = verdict(LIMITS, Spent(session_runs=99, day_runs=99), now=NOON, exempt=True)
    assert result.left == 0


def test_a_run_still_working_holds_its_place_in_the_ceiling():
    below = verdict(LIMITS, Spent(session_runs=4, day_runs=4), now=NOON)
    assert below.allowed

    same_numbers_two_in_flight = verdict(
        LIMITS,
        Spent(session_runs=4, day_runs=4, session_flying=2, day_flying=2),
        now=NOON,
    )
    assert not same_numbers_two_in_flight.allowed
    assert same_numbers_two_in_flight.scope == "session"


def test_the_refusal_adds_up_with_the_clicks_the_guest_made():
    result = verdict(
        LIMITS,
        Spent(session_runs=4, day_runs=4, session_flying=2, day_flying=2),
        now=NOON,
    )
    assert result.headline == "стеля цієї сесії вичерпана: 6 (4 + 2 в роботі) з 6"


def test_a_ceiling_closed_by_work_in_progress_says_wait_not_log_out():
    result = verdict(
        LIMITS,
        Spent(session_runs=4, day_runs=4, session_flying=2, day_flying=2),
        now=NOON,
    )
    assert result.action == (
        "місце зайняте: 2 прогони ще в роботі. Воно звільниться саме, щойно "
        "збірка завершиться. Новий вхід тут не допоможе: місце тримає робота, "
        "а не сесія"
    )


def test_a_ceiling_closed_by_finished_runs_still_says_log_out():
    result = verdict(LIMITS, Spent(session_runs=6, day_runs=6), now=NOON)
    assert result.action == (
        "за добу лишилось ще 6 прогонів — вони відкриються в новій сесії: "
        "«Вийти» і підключитись знову. Стеля сесії ловить зациклений клієнт, "
        "а не тебе"
    )


def test_the_day_ceiling_closed_by_work_in_progress_does_not_send_you_to_midnight():
    result = verdict(
        LIMITS, Spent(session_runs=1, day_runs=11, day_flying=1), now=NOON
    )
    assert result.scope == "day"
    assert result.headline == "на сьогодні стеля прогонів вичерпана: 12 (11 + 1 в роботі) з 12"
    assert result.action == (
        "місце зайняте: 1 прогін ще в роботі. Воно звільниться саме, щойно "
        "збірка завершиться. До півночі чекати не треба"
    )
    assert result.resets_at == day_end(NOON)


def test_the_day_ceiling_reached_without_help_still_waits_for_midnight():
    result = verdict(LIMITS, Spent(session_runs=1, day_runs=12, day_flying=1), now=NOON)
    assert result.action is not None
    assert result.action.startswith("оновиться опівночі за Києвом")


def test_the_state_line_names_the_places_already_taken():
    result = verdict(LIMITS, Spent(session_runs=2, day_runs=2, day_flying=3), now=NOON)
    assert result.allowed
    assert result.headline == (
        "прогонів: 2 з 6 у цій сесії, 2 з 12 за добу · у роботі ще 3 прогони — "
        "місце вже зайняте"
    )


def test_the_state_line_says_nothing_when_nothing_is_in_flight():
    result = verdict(LIMITS, Spent(session_runs=2, day_runs=2), now=NOON)
    assert result.headline == "прогонів: 2 з 6 у цій сесії, 2 з 12 за добу"


def test_what_is_left_drops_by_the_runs_in_flight():
    result = verdict(
        LIMITS,
        Spent(session_runs=1, day_runs=1, session_flying=2, day_flying=2),
        now=NOON,
    )
    assert result.left == 3


def test_money_ceilings_do_not_count_runs_in_flight():
    result = verdict(
        LIMITS,
        Spent(day_usd=Decimal("1.99"), total_usd=Decimal("1.99"), day_flying=5),
        now=NOON,
    )
    assert result.allowed
    assert "$" not in result.headline


def test_the_session_action_counts_the_day_places_that_are_taken_too():
    result = verdict(
        LIMITS, Spent(session_runs=6, day_runs=6, day_flying=2), now=NOON
    )
    assert result.action is not None
    assert result.action.startswith("за добу лишилось ще 4 прогони")


def test_a_place_taken_by_someone_else_counts_for_insiders_too():
    result = verdict(
        LIMITS,
        Spent(session_runs=4, day_runs=4, session_flying=2, day_flying=2),
        now=NOON,
        exempt=True,
    )
    assert result.allowed
    assert result.headline == (
        "прогонів: 4 з 6 у цій сесії, 4 з 12 за добу · у роботі ще 2 прогони — "
        "місце вже зайняте · стеля спрацювала б тут, але на своїх не діє"
    )
