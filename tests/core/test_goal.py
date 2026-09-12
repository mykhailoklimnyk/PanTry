from __future__ import annotations

from komora.core.goal import (
    NAMED,
    Duty,
    Goal,
    Row,
    basket_goal,
    handover_goal,
    homeless,
    pantry_goal,
    resolution_goal,
)
from komora.core.trace import fits

WHOLE = {"рядок кошика": ["молоко"], "не знайшлось": ["шафран"]}


def test_an_intent_that_landed_nowhere_is_named_and_not_merely_counted():
    lost = homeless(["молоко", "шафран", "кава"], WHOLE)

    assert lost == ("кава",)


def test_every_address_counts_and_one_is_enough():
    for address in (
        "рядок кошика",
        "питання гостю",
        "не знайшлось",
        "не збирають на слот",
        "агент не взяв",
        "відкладено",
        "зняте під межу",
        "чекає акції",
        "злито в сусідній рядок",
    ):
        assert homeless(["кава"], {address: ["кава"]}) == (), address


def test_a_repeated_intent_is_reported_once():
    assert homeless(["кава", "кава"], {}) == ("кава",)


def test_the_basket_goal_is_met_when_every_intent_has_an_address():
    goal = basket_goal(intents=["молоко", "шафран"], addresses=WHOLE, decided=True, model=True)

    assert goal.ok and goal.broken == () and goal.unmet == ()
    assert goal.told() == {"кожен намір має адресу": "так", "рішення відбулось": "так"}
    assert goal.note() == "мета досягнута — кожен намір має адресу; рішення відбулось"


def test_a_lost_intent_stops_the_run_and_says_which():
    goal = basket_goal(intents=["молоко", "кава"], addresses=WHOLE, decided=True, model=True)

    assert not goal.ok
    assert [duty.name for duty in goal.broken] == ["кожен намір має адресу"]
    assert "загублено 1: кава" in goal.refusal()
    assert goal.told()["рішення відбулось"] == "так"


def test_many_lost_intents_are_named_up_to_the_ceiling_and_counted_whole():
    names = [f"вид {n}" for n in range(NAMED + 2)]
    goal = basket_goal(intents=names, addresses={}, decided=True, model=True)

    why = goal.unmet[0].why
    assert why.startswith(f"загублено {len(names)}: ")
    assert why.count(",") == NAMED - 1


def test_a_silent_model_is_reported_and_does_not_stop_the_run():
    goal = basket_goal(intents=["молоко", "шафран"], addresses=WHOLE, decided=False, model=True)

    assert not goal.ok and goal.broken == ()
    assert goal.told()["рішення відбулось"] == "агент не дійшов до вибору"


def test_without_a_model_there_is_no_duty_to_decide_at_all():
    goal = basket_goal(intents=["молоко", "шафран"], addresses=WHOLE, decided=False, model=False)

    assert goal.ok and [duty.name for duty in goal.duties] == ["кожен намір має адресу"]


def _handover(**over):
    return handover_goal(
        **{
            "written": ["101", "202"],
            "planned": ["101", "202"],
            "cart_id": "c-1",
            "slot_written": "2026-09-05T06:00:00+00:00",
            "slot_planned": "2026-09-05T06:00:00+00:00",
            "reread": True,
            **over,
        }
    )


def test_a_clean_handover_meets_every_duty():
    goal = _handover()

    assert goal.ok and len(goal.duties) == 4


def test_a_cart_missing_from_the_response_is_named_alone():
    goal = _handover(cart_id=None)

    assert [duty.name for duty in goal.broken] == ["кошик існує у відповіді"]


def test_a_write_that_was_not_reread_is_named_alone():
    goal = _handover(reread=False)

    assert [duty.name for duty in goal.broken] == ["кошик перечитано після запису"]


def test_a_cart_on_another_slot_names_both_slots():
    goal = _handover(slot_written="2026-09-06T06:00:00+00:00")

    assert [duty.name for duty in goal.broken] == ["слот кошика дорівнює слоту плану"]
    assert "2026-09-06" in goal.unmet[0].why and "2026-09-05" in goal.unmet[0].why


def test_a_line_that_did_not_arrive_is_named_and_an_extra_one_is_not_a_fault():
    goal = _handover(written=["101", "999"])

    assert [duty.name for duty in goal.broken] == ["записане дорівнює запланованому"]
    assert "не доїхало 1: 202" in goal.unmet[0].why


def test_a_duty_marked_not_fatal_is_reported_but_does_not_break_the_goal():
    goal = Goal(duties=(Duty(name="а", ok=False, why="чому", fatal=False),))

    assert not goal.ok and goal.unmet and goal.broken == ()
    assert goal.note() == "мета НЕ досягнута: 1 з 1 — чому"
    assert goal.told() == {"а": "чому"}


def _row(label, *, named=True, counted=True, explained=False, asks=False):
    return Row(label=label, named=named, counted=counted, explained=explained, asks=asks)


def test_a_number_and_a_sentence_are_both_answers_and_neither_is_silence():
    goal = pantry_goal(
        [_row("хліб"), _row("паляниця", counted=False, explained=True)], questions=[]
    )

    assert goal.duties[0].ok
    assert goal.duties[0].why == ""


def test_a_row_that_says_neither_is_named_in_the_duty_not_merely_counted():
    goal = pantry_goal(
        [_row("хліб"), _row("сіль", counted=False), _row("перець", counted=False)],
        questions=[],
    )

    assert goal.duties[0].ok is False
    assert goal.duties[0].why == "мовчать 2: сіль, перець"


def test_the_silent_rows_are_named_up_to_the_ceiling_and_counted_whole():
    rows = [_row(f"вид {i}", counted=False) for i in range(NAMED + 2)]

    goal = pantry_goal(rows, questions=[])

    assert goal.duties[0].why == "мовчать 5: вид 0, вид 1, вид 2…"


def test_a_row_without_a_kind_label_is_named_and_the_named_ones_are_not():
    goal = pantry_goal([_row("хліб"), _row("Гречка Сквирянка", named=False)], questions=[])

    assert goal.duties[1].ok is False
    assert goal.duties[1].why == "без мітки виду 1: Гречка Сквирянка"


def test_asking_rows_are_met_by_a_question_even_when_the_ceiling_cut_the_rest():
    rows = [_row("паляниця", asks=True), _row("кава", asks=True)]

    assert pantry_goal(rows, questions=["паляниця"]).duties[2].ok
    assert pantry_goal(rows, questions=[]).duties[2].why == (
        "просять слова гостя 2, а питання не поставлено: паляниця, кава"
    )


def test_a_pantry_that_asks_nothing_meets_the_duty_without_any_question():
    goal = pantry_goal([_row("хліб")], questions=[])

    assert goal.ok
    assert goal.note() == (
        "мета досягнута — кожен рядок каже число або речення; "
        "неназвані названі або перелічені; питання гостю названі"
    )
    assert fits(goal.note()), goal.note()


def test_the_pantry_goal_reports_and_never_stops_the_run():
    goal = pantry_goal([_row("сіль", named=False, counted=False, asks=True)], questions=[])

    assert goal.ok is False
    assert goal.unmet == goal.duties
    assert goal.broken == ()


def test_an_intent_that_reached_a_line_is_addressed():
    goal = resolution_goal(["молоко"], addressed={"рядок кошика": ["молоко"]})

    assert goal.ok is True
    assert goal.unmet == ()
    assert goal.duties[0].why == ""


def test_an_intent_with_no_address_names_itself_and_the_count():
    goal = resolution_goal(["молоко", "шафран"], addressed={"рядок кошика": ["молоко"]})

    assert goal.ok is False
    assert goal.duties[0].why == "без рядка 1: шафран"


def test_the_duty_is_not_fatal_and_never_refuses_the_basket():
    goal = resolution_goal(["шафран"], addressed={})

    assert goal.ok is False
    assert goal.broken == ()


def test_a_refusal_is_not_an_address_here_and_that_is_the_whole_point():
    addressed = {"рядок кошика": ["молоко"]}
    assert resolution_goal(["молоко", "шафран"], addressed=addressed).ok is False
    assert (
        basket_goal(
            intents=["молоко", "шафран"],
            addresses={**addressed, "не знайшлось": ["шафран"]},
            decided=True,
            model=True,
        ).ok
        is True
    )


def test_a_merged_intent_counts_as_arrived():
    goal = resolution_goal(
        ["томат la", "томат гордій"],
        addressed={"рядок кошика": ["томат гордій"], "злито в сусідній рядок": ["томат la"]},
    )

    assert goal.ok is True


def test_a_question_to_the_guest_is_an_address_too():
    goal = resolution_goal(["сир"], addressed={"питання гостю": ["сир"]})

    assert goal.ok is True


def test_the_names_of_the_left_are_cut_and_the_cut_says_so():
    left = [f"вид {n}" for n in range(NAMED + 2)]
    goal = resolution_goal(left, addressed={})

    assert goal.duties[0].why.startswith(f"без рядка {len(left)}: ")
    assert goal.duties[0].why.endswith("…")
    assert goal.duties[0].why.count(",") == NAMED - 1


def test_the_same_intent_twice_is_one_debt():
    goal = resolution_goal(["сіль", "сіль"], addressed={})

    assert goal.duties[0].why == "без рядка 1: сіль"


def test_a_run_that_just_heard_the_guest_is_not_blamed_for_not_asking():
    rows = [_row("паляниця", asks=True), _row("кава", asks=True)]

    assert pantry_goal(rows, questions=[], closed=True).duties[2].ok
    assert pantry_goal(rows, questions=[], closed=True).duties[2].name == (
        "питання цього відкриття почуті"
    )
    assert not pantry_goal(rows, questions=[], closed=False).duties[2].ok
