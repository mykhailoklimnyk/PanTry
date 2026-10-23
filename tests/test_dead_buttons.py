from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from dead_buttons import WEB, dead


def _check(tmp_path: Path, markup: str) -> list[tuple[int, str]]:
    path = tmp_path / "Probe.svelte"
    path.write_text(markup, encoding="utf-8")
    return dead(path)


def test_the_tree_has_no_dead_buttons() -> None:
    assert {p.name: rows for p in WEB.rglob("*.svelte") if (rows := dead(p))} == {}


def test_the_check_catches_a_button_without_a_handler(tmp_path: Path) -> None:
    found = _check(tmp_path, '<button class="secondary" type="button">Написати</button>')
    assert [line for line, _ in found] == [1]


def test_a_handler_is_enough(tmp_path: Path) -> None:
    assert _check(tmp_path, "<button onclick={() => f()}>Так</button>") == []


def test_an_arrow_inside_the_handler_does_not_end_the_tag(tmp_path: Path) -> None:
    markup = '<button aria-label="далі >" onclick={() => a > b && f()}>Так</button>'
    assert _check(tmp_path, markup) == []


def test_submit_inside_a_form_is_not_dead(tmp_path: Path) -> None:
    markup = '<form onsubmit={send}><button type="submit">Додати</button></form>'
    assert _check(tmp_path, markup) == []


def test_submit_outside_a_form_is_dead(tmp_path: Path) -> None:
    found = _check(tmp_path, '<button type="submit">Додати</button>')
    assert [line for line, _ in found] == [1]


def test_a_spread_carries_the_handler_from_the_parent(tmp_path: Path) -> None:
    assert _check(tmp_path, "<button {...rest}>Так</button>") == []


def test_a_button_in_styles_or_comments_is_text_not_markup(tmp_path: Path) -> None:
    markup = "<!-- <button>приклад</button> -->\n<style>\n  /* <button> */\n  b {}\n</style>"
    assert _check(tmp_path, markup) == []


def test_line_numbers_survive_the_skipped_blocks(tmp_path: Path) -> None:
    markup = "<style>\n  b {}\n</style>\n<button>мертва</button>"
    assert [line for line, _ in _check(tmp_path, markup)] == [4]


def test_a_hyphen_is_not_an_attribute_start(tmp_path: Path) -> None:
    for attrs in (
        'data-once="1"',
        'data-only="1"',
        'aria-onepage="1"',
        'title="one=two"',
    ):
        found = _check(tmp_path, f"<button {attrs}>Мертва</button>")
        assert [line for line, _ in found] == [1], attrs


def test_a_shorthand_handler_still_counts(tmp_path: Path) -> None:
    assert _check(tmp_path, "<button {onclick}>Так</button>") == []
