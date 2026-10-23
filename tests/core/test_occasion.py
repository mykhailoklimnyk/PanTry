from __future__ import annotations

from komora.core.occasion import (
    OCCASION_LIMIT,
    BuildMode,
    EventStyle,
    Occasion,
    occasion_of,
    people_phrase,
)


def test_a_mode_without_an_occasion_is_not_a_fourth_state():
    for mode in (BuildMode.LIST, BuildMode.WEEK):
        plain = occasion_of(mode.value, None)

        assert not plain.named
        assert plain.task() == "", "нема чого казати агентові — нема й виклику"
        assert plain.label


def test_every_named_mode_carries_a_task_because_every_chip_promises_something():
    for mode in BuildMode:
        occasion = Occasion(mode)
        if mode is not BuildMode.EVENT:
            continue
        assert occasion.named
        assert occasion.task(), f"режим {mode} обіцяє з екрана і мусить щось казати"
        assert occasion.label


def test_the_headcount_lives_only_where_it_means_something():
    assert occasion_of("event", 4).people == 4
    assert occasion_of("event", 12).people == 12
    assert occasion_of("week", 4).people is None
    assert occasion_of("list", 4).people is None


def test_a_headcount_that_cannot_be_true_is_dropped_rather_than_repeated():
    assert occasion_of("event", 0).people is None
    assert occasion_of("event", -3).people is None
    assert occasion_of("event", None).people is None


def test_an_unknown_mode_becomes_a_list_instead_of_falling():
    assert occasion_of("halloween", 5).mode is BuildMode.LIST
    assert not occasion_of("", None).named


def test_the_mode_decides_where_the_intents_come_from():
    listed, week, event = (occasion_of(mode, 4) for mode in ("list", "week", "event"))

    assert not listed.takes_cycles and not listed.takes_pantry and not listed.fills_target
    assert week.takes_cycles and week.takes_pantry and week.fills_target
    assert event.takes_cycles, "без потреб приводу не було б чого знімати"
    assert not event.takes_pantry, "подія не про запас удома"
    assert not event.fills_target, "добір повернув би те, що привід щойно зняв"


def test_the_style_of_the_event_reaches_the_task_only_when_the_guest_said_it():
    silent = occasion_of("event", 4)
    cooking = occasion_of("event", 4, "cooking")
    ready = occasion_of("event", 4, "ready")

    assert silent.style is None
    assert "готує" not in silent.phrase() and "готове" not in silent.phrase()
    assert cooking.style is EventStyle.COOKING
    assert "сировин" in cooking.task().casefold()
    assert ready.style is EventStyle.READY
    assert "готов" in ready.task().casefold()


def test_an_unknown_style_is_silence_and_not_a_crash():
    assert occasion_of("event", 4, "хз").style is None
    assert occasion_of("event", 4, "").style is None
    assert occasion_of("week", 4, "cooking").style is None, "стиль без події безглуздий"


def test_the_phrase_declines_the_word_for_people():
    assert people_phrase(1) == "1 людина"
    assert people_phrase(2) == "2 людини"
    assert people_phrase(5) == "5 людей"
    assert people_phrase(11) == "11 людей", "одинадцять ламає наївне правило"
    assert occasion_of("event", 3).phrase() == "подія, 3 людини"


def test_the_task_names_the_headcount_so_the_agent_scales_by_it_not_by_a_multiplier():
    task = occasion_of("event", 12).task()

    assert "12" in task
    assert occasion_of("week", None).task().count("12") == 0


def test_the_event_task_says_out_loud_that_regular_purchases_do_not_belong():
    task = occasion_of("event", 4).task().casefold()

    assert "не є регулярною" in task
    assert "корм" in task


def test_the_ceiling_of_additions_is_a_number_and_it_is_small():
    assert 1 < OCCASION_LIMIT <= 12


def test_a_single_guest_is_still_a_headcount():
    assert occasion_of("event", 1).people == 1
    assert occasion_of("event", 1).phrase() == "подія, 1 людина"
