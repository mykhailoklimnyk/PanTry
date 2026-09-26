from __future__ import annotations

import pytest

from komora.core.skills import (
    _KIND_STEM,
    BRAND,
    CONTAINER,
    EVENT,
    FILES,
    KIDS,
    LIMITS,
    ORDER,
    PACK,
    PANTRY_IDLE,
    PANTRY_NEW,
    PANTRY_ORDER,
    PROMO,
    THRIFT,
    Selection,
    Skill,
    _same_kind,
    narrowing,
    norm,
    pantry_skills,
    select,
)

SHELF = {
    "Спрайт": [
        "Напій Sprite 0,5 л",
        "Напій Coca-Cola Classic з/б 0,33 л",
        "Вода Bonaqua негазована 1,5 л",
    ]
}


def names(chosen: Selection) -> list[str]:
    return [skill.name for skill in chosen.skills]


def test_a_basket_without_facts_gets_no_skills():
    chosen = select([], intents=["молоко", "хліб"])
    assert chosen.skills == ()
    assert chosen.unmatched == ()
    assert chosen.phrase() == "жодного: тригерів не було"


def test_the_promo_skill_reads_the_habit_and_names_how_many():
    assert names(select([], promo_kinds=3)) == [PROMO]
    assert "3 види" in select([], promo_kinds=3).skills[0].why
    assert "1 вид" in select([], promo_kinds=1).skills[0].why


def test_the_promo_skill_stays_silent_without_a_habit_and_without_the_shelf():
    assert names(select([], promo_kinds=0)) == []


def test_the_promo_skill_wakes_on_the_shelf_alone():
    chosen = select([], promo_on_shelf=True)
    assert names(chosen) == [PROMO]
    assert "полиці" in chosen.skills[0].why


@pytest.mark.parametrize("rule", ["по 100 г", "молоко 2 л", "бери упаковку побільше", "0,5 кг"])
def test_the_pack_skill_hears_a_named_size(rule: str):
    assert PACK in names(select([rule]))


@pytest.mark.parametrize("rule", ["без свинини", "тільки українське", "2 відсотки жиру"])
def test_the_pack_skill_stays_silent_without_a_size(rule: str):
    assert PACK not in names(select([rule]))


def test_the_pack_skill_hears_the_size_inside_the_intent_too():
    chosen = select([], intents=["Молоко Ферма 2,5% 900 г"])
    assert names(chosen) == [PACK]
    assert chosen.skills[0].why.startswith("намір")


def test_a_rule_beats_an_intent_when_both_name_a_size():
    chosen = select(["по 100 г"], intents=["Молоко Ферма 900 г"])
    assert chosen.skills[0].why == "правило «по 100 г»"


@pytest.mark.parametrize(
    "rule",
    [
        "тільки скляна пляшка",
        "пиво в склі",
        "пляшка зі скла",
        "воду в ПЕТ",
        "тільки ПЕТ-пляшка",
        "пиво з/б",
        "не бери пластик",
        "молоко тетрапак",
    ],
)
def test_the_container_skill_hears_the_material(rule: str):
    assert CONTAINER in names(select([rule]))


@pytest.mark.parametrize("rule", ["бери дешевше", "без цукру", "петрушку не бери"])
def test_the_container_skill_stays_silent_on_other_words(rule: str):
    assert CONTAINER not in names(select([rule]))


def test_the_event_skill_wakes_only_on_a_table():
    assert names(select([], occasion_mode="event")) == [EVENT]
    assert names(select([], occasion_mode="list")) == []
    assert names(select([], occasion_mode="week")) == []
    assert names(select([], occasion_mode="")) == []


def test_the_event_skill_says_the_occasion_in_words():
    chosen = select([], occasion_mode="event", occasion_phrase="подія, 6 людей")
    assert chosen.skills[0].why == "привід «подія, 6 людей»"


@pytest.mark.parametrize("text", ["щось для дитини", "дитяче печиво", "смаколик малюку"])
def test_the_kids_skill_hears_the_child(text: str):
    assert KIDS in names(select([text]))
    assert KIDS in names(select([], intents=[text]))


@pytest.mark.parametrize("text", ["без глютену", "молоко 1 л"])
def test_the_kids_skill_stays_silent_otherwise(text: str):
    assert KIDS not in names(select([text]))


@pytest.mark.parametrize(
    "rule", ["без лактози", "не містить горіхів", "веганське", "пісне меню", "безглютенове"]
)
def test_the_limits_skill_hears_a_ban(rule: str):
    assert LIMITS in names(select([rule]))


def test_the_limits_skill_reads_rules_and_not_the_shelf():
    assert LIMITS not in names(select([], intents=["Пюре яблучне без цукру"]))


@pytest.mark.parametrize("rule", ["бери дешевше", "економно", "бюджетно", "щоб вигідніше"])
def test_the_thrift_skill_hears_the_ask(rule: str):
    assert THRIFT in names(select([rule]))


def test_the_thrift_skill_stays_silent_on_a_price_in_the_intent():
    assert THRIFT not in names(select([], intents=["Молоко дешеве"]))


def test_the_brand_skill_needs_a_shelf_to_prove_the_word():
    assert BRAND not in names(select([], intents=["Спрайт"]))
    assert BRAND in names(select([], intents=["Спрайт"], shelf=SHELF))


def test_the_brand_skill_stays_silent_when_the_word_heads_the_names():
    shelf = {"молоко": ["Молоко Ферма 2,5% 900 г", "Молоко Селянське 1 л"]}
    assert BRAND not in names(select([], intents=["молоко"], shelf=shelf))


@pytest.mark.parametrize(
    ("intent", "shelf_names"),
    [
        ("пральний порошок", ["Порошок пральний Ariel 450 г", "Порошок пральний Gala 2,4 кг"]),
        ("пиво світле", ["Пиво Оболонь Світле 0,5 л", "Пиво Hike Світле 0,5 л"]),
        ("сир кисломолочний", ["Сир кисломолочний Яготинський 5%", "Сир Гауда 45%"]),
    ],
)
def test_an_adjective_next_to_a_kind_word_is_not_a_brand(intent: str, shelf_names: list[str]):
    assert narrowing(intent, shelf_names) == ""
    assert BRAND not in names(select([], intents=[intent], shelf={intent: shelf_names}))


def test_the_brand_skill_names_the_word_it_found():
    chosen = select([], intents=["Спрайт"], shelf=SHELF)
    assert chosen.skills[0].why == "намір «Спрайт» звужує вид словом «Спрайт»"


def test_a_rule_never_reaches_the_brand_skill_and_that_is_measured():
    shelf = {"сир": ["Сир Український 50%", "Сир Гауда 45%"]}
    assert narrowing("тільки українське", shelf["сир"]) == "українське"
    chosen = select(["тільки українське"], intents=["сир"], shelf=shelf)
    assert chosen.skills == ()
    assert chosen.unmatched == ("тільки українське",)


def test_a_rule_without_a_skill_says_so_out_loud():
    chosen = select(["тільки українське"])
    assert chosen.unmatched == ("тільки українське",)
    assert chosen.phrase() == (
        "жодного: тригерів не було; без скіла: правило «тільки українське» -- судити нема чим"
    )


def test_a_rule_that_fired_something_is_not_reported_as_unmatched():
    chosen = select(["без лактози"])
    assert names(chosen) == [LIMITS]
    assert chosen.unmatched == ()


def test_the_same_rule_is_reported_once_even_when_two_skills_read_it():
    chosen = select(["без лактози, 1 л"])
    assert names(chosen) == [PACK, LIMITS]
    assert chosen.unmatched == ()


def test_the_order_is_fixed_and_does_not_follow_the_guest():
    first = select(["бери дешевше", "без лактози", "по 100 г"])
    second = select(["по 100 г", "без лактози", "бери дешевше"])
    assert names(first) == names(second) == [PACK, LIMITS, THRIFT]
    assert names(first) == [name for name in ORDER if name in names(first)]


def test_everything_fires_at_once_and_stays_in_order():
    chosen = select(
        ["по 100 г", "тільки скло", "без лактози", "бери дешевше", "для дитини"],
        occasion_mode="event",
        intents=["Спрайт"],
        promo_kinds=2,
        shelf=SHELF,
    )
    assert names(chosen) == list(ORDER)
    assert chosen.unmatched == ()


def test_the_phrase_names_both_halves():
    chosen = select(["по 100 г", "тільки українське"], promo_kinds=3)
    assert chosen.phrase() == (
        "підключено: акція (акційна звичка: 3 види); фасовка (правило «по 100 г»); "
        "без скіла: правило «тільки українське» -- судити нема чим"
    )


def test_the_phrase_names_the_fields_each_skill_judges_by():
    chosen = select(["по 100 г", "тільки скло"])
    assert chosen.phrase({"фасовка": ("фасовка", "ціна"), "тара": ("назва",)}) == (
        "підключено: фасовка (правило «по 100 г») -- судить полями фасовка, ціна; "
        "тара (правило «тільки скло») -- судить лише полем назва"
    )


def test_a_skill_whose_fields_are_unknown_says_so_instead_of_looking_judgeless():
    chosen = select(["тільки скло"])
    assert chosen.phrase({}) == "підключено: тара (правило «тільки скло») -- поля не названі"
    assert chosen.phrase() == "підключено: тара (правило «тільки скло»)"


def test_norm_folds_case_and_the_typographic_apostrophe():
    odd = chr(0x2019)
    assert norm(f"  Об{odd}ЄМ   0,5 Л ") == "об'єм 0,5 л"


def test_every_skill_in_the_order_has_a_file_and_no_file_is_orphaned():
    assert set(ORDER) | set(PANTRY_ORDER) == set(FILES)
    assert not set(ORDER) & set(PANTRY_ORDER)
    assert len(set(FILES.values())) == len(FILES)


def test_a_skill_carries_its_reason():
    skill = Skill(name=PROMO, why="акційна звичка: 3 види")
    assert (skill.name, skill.why) == (PROMO, "акційна звичка: 3 види")


def test_the_kind_stem_boundary_is_inclusive_on_both_words():
    assert len("какао") == _KIND_STEM
    assert _same_kind("какао", "какаові")
    assert _same_kind("какаові", "какао")
    assert not _same_kind("кака", "какао")
    assert not _same_kind("какао", "кака")


def test_narrowing_is_empty_when_no_word_is_carried_by_any_name():
    assert narrowing("чай зелений", ["Молоко Галичина 2,5%"]) == ""


def test_the_promo_reason_declines_the_number_and_names_the_shelf():
    assert select([], promo_kinds=5).skills[0].why == "акційна звичка: 5 видів"
    assert select([], promo_kinds=2).skills[0].why == "акційна звичка: 2 види"
    assert select([], promo_on_shelf=True).skills[0].why == "твій артикул на полиці зі старою ціною"


def test_an_empty_pantry_asks_for_the_newcomer_skill():
    got = pantry_skills({})
    assert [skill.name for skill in got.skills] == [PANTRY_NEW]
    assert got.skills[0].why == "ні рядків, ні дописаного, ні чеків"


@pytest.mark.parametrize("source", ["рядків", "дописано руками", "чеків прочитано"])
def test_any_one_source_of_work_makes_the_pantry_not_empty(source):
    got = pantry_skills({source: 1})
    assert got.skills == ()


def test_without_kind_labels_nothing_is_claimed():
    assert pantry_skills({"рядків": 12, "міток виду": 0, "без мітки виду": 0}).skills == ()


def test_a_pantry_with_work_left_everywhere_stays_silent():
    state = {
        "рядків": 12,
        "міток виду": 12,
        "без мітки виду": 3,
        "без вироку про ритм": 2,
        "без стелі зберігання": 1,
    }
    assert pantry_skills(state).skills == ()


def test_one_finished_axis_is_enough_and_it_is_named():
    state = {
        "рядків": 12,
        "міток виду": 12,
        "без мітки виду": 0,
        "без вироку про ритм": 4,
        "без стелі зберігання": 4,
    }
    got = pantry_skills(state)
    assert [skill.name for skill in got.skills] == [PANTRY_IDLE]
    assert got.skills[0].why == "нуль у: без мітки виду"


def test_the_finished_axes_are_named_in_the_dictionary_order():
    got = pantry_skills({"рядків": 9, "міток виду": 9})
    assert got.skills[0].why == (
        "нуль у: без мітки виду, без вироку про ритм, без стелі зберігання"
    )
