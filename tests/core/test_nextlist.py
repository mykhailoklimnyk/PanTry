from komora.core.nextlist import OUT, PROMO, SOON, Pick, Row, changes, choose, why


def _row(label: str, **extra) -> Row:
    return Row(
        kind=label.casefold(),
        label=label,
        **{"running_out": False, "days_left": None, **extra},
    )


def test_what_ran_out_goes_first_and_what_is_uneven_does_not_go_at_all():
    picks = choose(
        [
            _row("Хліб", running_out=True, days_left=0),
            _row("Кава", days_left=None),
            _row("Молоко", days_left=2),
        ],
        gap_days=3,
        limit=10,
    )

    assert [pick.label for pick in picks] == ["Хліб", "Молоко"]
    assert [pick.reason for pick in picks] == [OUT, SOON]


def test_the_horizon_is_the_guests_own_trip_gap():
    rows = [_row("Молоко", days_left=5)]

    assert choose(rows, gap_days=2, limit=10) == ()
    assert [pick.label for pick in choose(rows, gap_days=7, limit=10)] == ["Молоко"]


def test_a_promo_habit_carries_its_mark_as_advice_and_not_as_a_promise():
    picks = choose([_row("Пиво", running_out=True, days_left=0, promo=True)], gap_days=3, limit=5)

    assert [pick.reason for pick in picks] == [PROMO]
    assert why(picks[0]) == "береш це по акції — без знижки не бери"


def test_a_row_the_guest_added_by_hand_has_no_cycle_and_no_place_here():
    assert choose([_row("Васабі", running_out=True, manual=True)], gap_days=3, limit=5) == ()


def test_the_ceiling_cuts_the_weakest_reason_first():
    picks = choose(
        [
            _row("Молоко", days_left=1),
            _row("Хліб", running_out=True, days_left=0),
            _row("Сир", days_left=2),
        ],
        gap_days=3,
        limit=2,
    )

    assert [pick.label for pick in picks] == ["Хліб", "Молоко"]


def test_the_words_of_a_reason_say_which_day_it_is():
    assert why(Pick("х", "Хліб", OUT, 0)) == "закінчилось сьогодні"
    assert why(Pick("х", "Хліб", OUT, 2)) == "майже закінчилось: лишилось ~2 дн"
    assert why(Pick("х", "Хліб", OUT, -3)) == "мало закінчитись 3 дн тому"
    assert why(Pick("х", "Хліб", OUT, None)) == "закінчилось"
    assert why(Pick("м", "Молоко", SOON, 2)) == "закінчиться за 2 дн — до наступного походу"
    assert why(Pick("м", "Молоко", SOON, None)) == "закінчиться до наступного походу"


def test_changes_name_both_sides_and_silence_is_a_legal_answer():
    assert changes({"х": "Хліб"}, {"х": "Хліб"}) == ()
    assert changes({}, {"х": "Хліб"}) == ("додав Хліб",)
    assert changes({"к": "Кава"}, {}) == ("зняв Кава — більше не закінчується",)


def test_a_negative_ceiling_takes_nothing_instead_of_everything():
    assert choose([_row("Хліб", running_out=True)], gap_days=3, limit=-1) == ()
