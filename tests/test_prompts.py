from __future__ import annotations

import pytest

from komora.agent import prompts
from komora.agent.prompts import Prompt


@pytest.fixture
def registry(monkeypatch: pytest.MonkeyPatch) -> dict[str, Prompt]:
    fresh: dict[str, Prompt] = {}
    monkeypatch.setattr(prompts, "REGISTRY", fresh)
    return fresh


def test_digest_is_the_head_of_sha256(registry):
    written = prompts.register("naming", "Ти ведеш домашню комору.")
    assert written.name == "naming"
    assert len(written.digest) == prompts.DIGEST_CHARS
    assert prompts.digest_of("naming") == written.digest


def test_the_same_text_registers_twice_without_a_word(registry):
    first = prompts.register("naming", "той самий текст")
    again = prompts.register("naming", "той самий текст")
    assert first.digest == again.digest


def test_one_name_carries_one_text(registry):
    prompts.register("naming", "перший")
    with pytest.raises(ValueError, match="одне ім'я"):
        prompts.register("naming", "другий")


def test_an_empty_prompt_is_refused(registry):
    with pytest.raises(ValueError, match="порожній"):
        prompts.register("naming", "   \n  ")


def test_a_name_out_of_the_registry_is_an_error_not_an_empty_string(registry):
    with pytest.raises(KeyError, match="немає в реєстрі"):
        prompts.digest_of("такого немає")


def test_a_whole_prompt_stamps_as_name_at_digest(registry):
    prompts.register("naming", "Ти ведеш домашню комору.")
    assert prompts.stamp("naming", "Ти ведеш домашню комору.") == (
        f"naming@{prompts.digest_of('naming')}"
    )


def test_a_composed_prompt_names_its_parts_in_the_order_they_stand(registry):
    prompts.register("pick.head", "ГОЛОВА. ")
    prompts.register("pick.tail", "ХВІСТ.")
    prompts.register("skill.promo", "ПРО АКЦІЮ.")

    stamp = prompts.stamp("pick", "ГОЛОВА. ХВІСТ.")
    assert stamp.startswith("pick[head@")
    assert stamp.index("head@") < stamp.index("tail@")

    with_skill = prompts.stamp("pick", "ГОЛОВА. ХВІСТ.\n\nПРО АКЦІЮ.")
    assert with_skill.endswith(f"skill.promo@{prompts.digest_of('skill.promo')}]")


def test_a_part_that_did_not_travel_is_not_in_the_stamp(registry):
    prompts.register("pick.head", "ГОЛОВА. ")
    prompts.register("skill.promo", "ПРО АКЦІЮ.")
    assert "skill.promo" not in prompts.stamp("pick", "ГОЛОВА. ")


def test_a_prompt_out_of_the_registry_names_itself(registry):
    prompts.register("pick.head", "ГОЛОВА.")
    assert prompts.stamp("trap", "зовсім інший текст") == "trap[поза реєстром]"


def test_the_registry_of_the_product_is_full_after_load_all():
    prompts.load_all()
    for name in ("pick.head", "pick.tail", "pick.queue", "pick.label"):
        assert name in prompts.REGISTRY
    for name in ("naming", "keeps", "chain", "loop", "occasion", "plan"):
        assert name in prompts.REGISTRY
    assert {name for name in prompts.REGISTRY if name.startswith("skill.")}


def test_two_editions_of_one_prompt_do_not_share_a_digest(registry):
    from komora.agent.basket import _PICK_HEAD

    was = prompts.register("pick.head", _PICK_HEAD)
    edited = prompts.register("pick.head.чернетка", _PICK_HEAD + " Ще речення.")
    assert edited.digest != was.digest
