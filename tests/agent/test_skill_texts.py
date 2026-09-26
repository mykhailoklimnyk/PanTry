from __future__ import annotations

import pytest

from komora.agent.skills import HEADER, READS, block, fields, text
from komora.core.skills import CONTAINER, FILES, ORDER, PACK, Skill


@pytest.mark.parametrize("name", ORDER)
def test_every_skill_has_a_text_and_it_is_not_empty(name: str):
    body = text(name)
    assert body.strip()
    assert body.startswith(f"# Скіл «{name}»")


@pytest.mark.parametrize("name", ORDER)
def test_every_skill_says_when_it_applies_and_what_it_reads(name: str):
    body = text(name)
    assert "**Коли.**" in body
    assert "**Читає.**" in body


@pytest.mark.parametrize("name", ORDER)
def test_every_skill_is_short_enough_to_stay_next_to_its_neighbour(name: str):
    bullets = [line for line in text(name).splitlines() if line.startswith("- ")]
    assert 5 <= len(bullets) <= 12, f"{name}: {len(bullets)} пунктів"


def test_the_block_is_empty_when_nothing_fired():
    assert block(()) == ""


def test_the_block_keeps_the_order_it_was_given():
    made = block([Skill(ORDER[1], "..."), Skill(ORDER[0], "...")])
    assert made.index(text(ORDER[1])) < made.index(text(ORDER[0]))
    assert made.startswith("\n\n" + HEADER)


def test_an_unreadable_skill_costs_one_instruction_and_not_the_whole_block():
    made = block([Skill(ORDER[0], "..."), Skill("такого скіла немає", "...")])
    assert text(ORDER[0]) in made
    assert "такого скіла немає" not in made


def test_a_missing_file_never_reaches_the_prompt_as_a_name():
    assert block([Skill("вигаданий", "...")]) == ""


@pytest.mark.parametrize("name", ORDER)
def test_the_file_is_read_from_the_package_not_from_the_repository(name: str):
    from importlib import resources

    path = resources.files("komora.agent.skills").joinpath(f"{FILES[name]}.md")
    assert path.is_file()
    assert path.read_text(encoding="utf-8").strip() == text(name)


@pytest.mark.parametrize("name", ORDER)
def test_every_skill_names_the_fields_it_judges_by(name: str):
    assert fields(name), f"{name}: у рядку «Читає» немає жодного поля в бектиках"


def test_the_fields_are_the_ones_the_file_names_and_in_its_order():
    assert fields(PACK) == ("фасовка", "ціна", "за_100г", "назва")
    assert fields(CONTAINER) == ("назва",)


def test_a_skill_we_cannot_read_names_no_fields_instead_of_guessing():
    assert fields("такого скіла немає") == ()


def test_only_the_reads_paragraph_counts_and_not_the_bullets_below():
    made = (
        "# Скіл «вигаданий»\n\n"
        f"{READS} У кандидаті -- `назва`, `ціна`.\n\n"
        "- Порівнюй `за_100г` лише в прикладі цього пункту.\n"
    )
    fields.cache_clear()
    try:
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr("komora.agent.skills.text", lambda _name: made)
            assert fields("вигаданий") == ("назва", "ціна")
    finally:
        fields.cache_clear()


def test_a_file_without_the_reads_line_says_nothing_instead_of_everything():
    fields.cache_clear()
    try:
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr("komora.agent.skills.text", lambda _name: "# Скіл «німий»\n\n- `ціна`\n")
            assert fields("німий") == ()
    finally:
        fields.cache_clear()
