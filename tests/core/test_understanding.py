from __future__ import annotations

from komora.core.trace import fits
from komora.core.understanding import (
    ANSWER_WAIT_S,
    MAX_OPTIONS,
    MIN_OPTIONS,
    PLAN_GATED,
    UNDERSTAND_ADD,
    UNDERSTAND_QUESTIONS,
    Change,
    PlanChange,
    Question,
    Understanding,
    read,
    waited_note,
)


def _question(ask: str = "Готуєш сам?", options: int = 2, **extra) -> dict:
    return {
        "ask": ask,
        "options": [{"label": f"варіант {n}"} for n in range(options)],
        **extra,
    }


def test_a_question_without_options_is_a_dead_end_and_is_cut_by_name():
    seen = read(
        {"questions": [_question(options=1), _question("Скільки?")], "add": [], "drop": []},
        intents=[],
        protected=[],
    )

    assert [question.ask for question in seen.questions] == ["Скільки?"]
    assert seen.thrown and "варіантів менше" in seen.thrown[0]


def test_the_ceiling_of_questions_cuts_the_tail_and_says_how_many():
    seen = read(
        {"questions": [_question(f"Питання {n}") for n in range(5)], "add": [], "drop": []},
        intents=[],
        protected=[],
    )

    assert len(seen.questions) == UNDERSTAND_QUESTIONS
    assert sum("понад стелю" in note for note in seen.thrown) == 5 - UNDERSTAND_QUESTIONS


def test_options_are_capped_and_deduplicated_because_a_list_is_not_a_question():
    raw = _question(options=0)
    raw["options"] = [{"label": "готую"}, {"label": "Готую"}] + [
        {"label": f"інше {n}"} for n in range(6)
    ]

    seen = read({"questions": [raw], "add": [], "drop": []}, intents=[], protected=[])

    labels = [option.label for option in seen.questions[0].options]
    assert len(labels) == MAX_OPTIONS
    assert labels[0] == "готую" and "Готую" not in labels
    assert seen.thrown == ("питання «Готуєш сам?»: варіантів 7, лишаю 4",)


def test_the_option_carries_the_intents_it_opens():
    raw = _question(options=0)
    raw["options"] = [
        {"label": "беру готове", "intents": ["нарізка м'ясна", "  "], "style": "ready"},
        {"label": "готую сам", "intents": None, "style": "cooking"},
    ]

    options = (
        read({"questions": [raw], "add": [], "drop": []}, intents=[], protected=[])
        .questions[0]
        .options
    )

    assert options[0].intents == ("нарізка м'ясна",)
    assert options[0].style == "ready"
    assert options[1].intents == () and options[1].style == "cooking"


def test_an_unknown_style_is_silence_because_an_invented_choice_is_worse_than_none():
    raw = _question(options=0)
    raw["options"] = [{"label": "а", "style": "гриль"}, {"label": "б"}]

    options = (
        read({"questions": [raw], "add": [], "drop": []}, intents=[], protected=[])
        .questions[0]
        .options
    )

    assert options[0].style is None and options[1].style is None


def test_the_stage_cannot_drop_what_the_guest_said_himself():
    seen = read(
        {
            "questions": [],
            "add": [],
            "drop": [{"intent": "молоко", "why": "не для події"}, {"intent": "корм", "why": "р"}],
        },
        intents=["молоко", "корм"],
        protected=["молоко"],
    )

    assert [change.intent for change in seen.dropped] == ["корм"]
    assert any("слово гостя" in note for note in seen.thrown)


def test_a_dropped_intent_that_is_not_in_the_list_is_not_invented_into_one():
    seen = read(
        {"questions": [], "add": [], "drop": [{"intent": "васабі"}]},
        intents=["молоко"],
        protected=[],
    )

    assert seen.dropped == ()


def test_added_intents_are_capped_and_do_not_duplicate_what_is_already_there():
    seen = read(
        {
            "questions": [],
            "add": [{"intent": "молоко"}] + [{"intent": f"вид {n}"} for n in range(10)],
            "drop": [],
        },
        intents=["молоко"],
        protected=["молоко"],
    )

    assert len(seen.added) == UNDERSTAND_ADD
    assert "молоко" not in {change.intent for change in seen.added}
    assert any("понад стелю" in note for note in seen.thrown)


def test_a_plan_change_outside_the_gated_steps_is_cut_because_it_would_change_nothing():
    seen = read(
        {
            "questions": [],
            "add": [],
            "drop": [],
            "plan": [
                {"change": "add", "step": "shelf.by_article"},
                {"change": "skip", "step": "decide.pick"},
                {"change": "add", "step": "вигаданий.крок"},
                {"change": "перекинути", "step": "decide.loop"},
            ],
        },
        intents=[],
        protected=[],
    )

    assert [(item.change, item.step) for item in seen.plan] == [("add", "shelf.by_article")]
    assert len(seen.thrown) == 3


def test_every_gated_step_is_a_real_step_of_the_dictionary():
    from komora.core.plan import BY_NAME

    assert PLAN_GATED and set(BY_NAME) >= PLAN_GATED


def test_the_note_has_three_states_and_none_looks_like_another():
    assert "не спрацював" in Understanding(failure="таймаут").note()
    assert "нічого не змінив" in Understanding().note()
    said = Understanding(questions=(Question(id="q1", ask="Готуєш?", why="", options=()),)).note()
    assert "питаю 1" in said and "Готуєш?" not in said


def test_the_note_stays_within_the_step_ceiling_on_a_full_stage():
    stage = Understanding(
        questions=tuple(
            Question(id=f"q{n}", ask=f"Питання номер {n} про вибір товару?", why="", options=())
            for n in range(3)
        ),
        added=tuple(
            Change(intent=f"Дуже довга назва наміру номер {n}", why="привід") for n in range(20)
        ),
        dropped=tuple(Change(intent=f"Знятий намір номер {n}", why="є вдома") for n in range(20)),
        plan=(PlanChange(change="skip", step="shelf.by_article", why="немає числових артикулів"),),
    )
    assert fits(stage.note()), stage.note()


def test_the_waiting_note_names_the_question_and_the_ceiling():
    note = waited_note(Question(id="q1", ask="Готуєш сам?", why="", options=()), ANSWER_WAIT_S)

    assert "Готуєш сам?" in note and "25" in note


def test_the_ceilings_are_small_numbers_and_the_wait_is_shorter_than_a_run():
    assert MIN_OPTIONS == 2 and 2 < MAX_OPTIONS <= 6
    assert 0 < UNDERSTAND_QUESTIONS <= 3
    assert 5.0 <= ANSWER_WAIT_S <= 40.0


def test_a_question_that_is_not_an_object_is_cut_by_its_number():
    seen = read(
        {"questions": ["Готуєш?", _question()], "add": [], "drop": []},
        intents=[],
        protected=[],
    )

    assert len(seen.questions) == 1
    assert seen.thrown == ("питання 1: не об'єкт",)


def test_a_question_without_text_is_cut_even_when_it_has_options():
    raw = _question(ask="   ")

    seen = read({"questions": [raw], "add": [], "drop": []}, intents=[], protected=[])

    assert seen.questions == ()
    assert seen.thrown == ("питання 1: без тексту",)


def test_a_broken_option_does_not_count_towards_the_minimum():
    raw = _question(options=0)
    raw["options"] = ["готую", {"label": "  "}, {"label": "беру готове"}]

    seen = read({"questions": [raw], "add": [], "drop": []}, intents=[], protected=[])

    assert seen.questions == ()
    assert seen.thrown and "варіантів менше" in seen.thrown[0]


def test_the_option_id_counts_raw_positions_so_the_answer_matches_what_was_shown():
    raw = _question(options=0)
    raw["options"] = [{"label": "  "}, {"label": "готую"}, {"label": "беру готове"}]

    options = (
        read({"questions": [raw], "add": [], "drop": []}, intents=[], protected=[])
        .questions[0]
        .options
    )

    assert [option.id for option in options] == ["o2", "o3"]


def test_the_reason_for_the_question_travels_with_it():
    raw = _question(why="  від цього залежить  весь стіл ")

    why = (
        read({"questions": [raw], "add": [], "drop": []}, intents=[], protected=[]).questions[0].why
    )

    assert why == "від цього залежить весь стіл"


def test_a_protected_intent_is_named_the_way_the_guest_wrote_it():
    seen = read(
        {"questions": [], "add": [], "drop": [{"intent": "  МОЛОКО  "}]},
        intents=["Молоко Ферма 2,5%", "молоко"],
        protected=["молоко"],
    )

    assert seen.dropped == ()
    assert seen.thrown == ("«молоко»: це слово гостя, зняти не можна",)


def test_the_same_intent_dropped_twice_is_one_line_not_two():
    seen = read(
        {
            "questions": [],
            "add": [],
            "drop": [{"intent": "корм"}, {"intent": "КОРМ"}, "корм"],
        },
        intents=["корм"],
        protected=[],
    )

    assert [change.intent for change in seen.dropped] == ["корм"]


def test_a_plan_change_with_an_unknown_verb_is_cut_by_name():
    step = sorted(PLAN_GATED)[0]
    seen = read(
        {"questions": [], "add": [], "plan": [{"step": step, "change": "MOVE"}]},
        intents=[],
        protected=[],
    )

    assert seen.plan == ()
    assert seen.thrown == (f"крок «{step}»: невідома зміна «move»",)


def test_a_step_outside_the_dictionary_is_cut_before_the_gate_is_checked():
    seen = read(
        {"questions": [], "add": [], "plan": [{"step": "step-вигаданий", "change": "add"}]},
        intents=[],
        protected=[],
    )

    assert seen.thrown == ("крок «step-вигаданий»: такого немає в словнику",)


def test_the_same_step_twice_leaves_one_change():
    step = sorted(PLAN_GATED)[0]
    seen = read(
        {
            "questions": [],
            "add": [],
            "plan": [
                {"step": step, "change": "skip", "why": "перше"},
                {"step": step, "change": "add", "why": "друге"},
            ],
        },
        intents=[],
        protected=[],
    )

    assert [(item.change, item.why) for item in seen.plan] == [("skip", "перше")]


def test_an_added_intent_without_a_name_is_not_an_intent():
    seen = read(
        {"questions": [], "add": [{"why": "під стіл"}, {"intent": "  "}, "сир"], "drop": []},
        intents=[],
        protected=[],
    )

    assert seen.added == ()


def _cut(cut: list[str], said: list[str]) -> Understanding:
    return read(
        {"questions": [], "add": [], "drop": [], "cut": cut},
        intents=said,
        protected=said,
    )


def test_three_pieces_of_one_intent_become_one_because_the_comma_is_not_a_border():
    seen = _cut(["морозиво хрещатик фісташка"], ["морозиво", "хрещатик", "фісташка"])

    assert seen.cut == ("морозиво хрещатик фісташка",)
    assert not seen.thrown
    assert seen.touched, "переріз -- це зміна, і етап не має права мовчати про неї"


def test_what_the_cut_did_not_take_is_named_and_not_swallowed():
    seen = _cut(["молоко"], ["молоко", "0501234567", "привіт"])

    assert seen.cut == ("молоко",)
    assert seen.ignored == ("0501234567", "привіт")


def test_a_cut_that_takes_nothing_is_erasure_and_the_comma_stays():
    seen = _cut(["цукерки"], ["молоко", "хліб"])

    assert seen.cut == ()
    assert any("не взяв із тексту нічого" in note for note in seen.thrown)


def test_more_intents_than_words_typed_is_refused_because_that_is_invention():
    seen = _cut(["сир", "хліб", "молоко"], ["0501234567"])

    assert seen.cut == ()
    assert any("при 1 словах гостя" in note for note in seen.thrown)


def test_a_cut_that_agrees_with_our_split_is_an_answer_and_not_silence():
    seen = _cut(["молоко", "хліб"], ["молоко", "хліб"])

    assert seen.cut == ("молоко", "хліб")


def test_no_cut_at_all_stays_empty_and_touches_nothing():
    seen = read(
        {"questions": [], "add": [], "drop": []}, intents=["молоко"], protected=["молоко"]
    )

    assert seen.cut == ()
    assert not seen.touched
