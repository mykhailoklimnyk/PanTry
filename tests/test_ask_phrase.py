from __future__ import annotations

import ast
import inspect
import re
import textwrap
from pathlib import Path

from komora.core.cycles import ASK_NOTE, coverage_note

NOTES_WITHOUT_ADVICE = 1


def _root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "web" / "src" / "lib" / "facts.ts").is_file():
            return parent
    raise AssertionError("не знайшлось web/src/lib/facts.ts")


def _returns_of_coverage_note() -> list[ast.Return]:
    tree = ast.parse(textwrap.dedent(inspect.getsource(coverage_note)))
    return [node for node in ast.walk(tree) if isinstance(node, ast.Return)]


def _mentions_ask(node: ast.Return) -> bool:
    return any(isinstance(inner, ast.Name) and inner.id == "ASK_NOTE" for inner in ast.walk(node))


def test_the_screen_does_not_retype_the_phrase_it_turns_into_a_button() -> None:
    root = _root()
    typed: list[str] = []
    for path in sorted(root.glob("web/src/**/*")):
        if path.suffix not in {".svelte", ".ts"} or path.name == "facts.ts":
            continue
        if ASK_NOTE in path.read_text(encoding="utf-8"):
            typed.append(str(path.relative_to(root)).replace("\\", "/"))

    assert not typed, (
        f"фраза «{ASK_NOTE}» набрана руками у {', '.join(typed)} -- "
        "розійдеться з реченням сервера на одну кому, і кнопка мовчки стане "
        "текстом (#364). Дім у неї один: імпортуй ASK_PHRASE з lib/facts"
    )


def test_the_screen_reads_the_phrase_from_the_one_home() -> None:
    screen = (_root() / "web" / "src" / "lib" / "screens" / "Cart.svelte").read_text(
        encoding="utf-8"
    )
    assert "ASK_PHRASE" in screen, (
        "Cart.svelte більше не читає ASK_PHRASE: або кнопку зняли, або фразу "
        "повернули на екран копією (#364)"
    )


def test_the_generated_phrase_matches_the_server_word_for_word() -> None:
    facts = (_root() / "web" / "src" / "lib" / "facts.ts").read_text(encoding="utf-8")
    found = re.search(r'export const ASK_PHRASE = "([^"]*)"', facts)
    assert found is not None, "ASK_PHRASE зник з facts.ts -- екрану нема що шукати"
    assert found.group(1) == ASK_NOTE, (
        "фраза на екрані розійшлась із фразою сервера: "
        f"у facts.ts «{found.group(1)}», у core.cycles «{ASK_NOTE}». "
        "Перегенеруй: uv run python scripts/gen_facts.py"
    )


def test_every_sentence_about_a_shortfall_carries_the_advice() -> None:
    returns = _returns_of_coverage_note()
    assert len(returns) > NOTES_WITHOUT_ADVICE, "coverage_note лишився без гілок недобору"

    silent = [node.lineno for node in returns if not _mentions_ask(node)]
    assert len(silent) == NOTES_WITHOUT_ADVICE, (
        f"речень без поради {len(silent)} (рядки {silent}), а дозволено "
        f"{NOTES_WITHOUT_ADVICE}: недобір без «{ASK_NOTE}» лишає гостя перед "
        "поясненням, з якого немає дороги (#364, #38)"
    )


def test_the_shortfall_states_really_say_it_and_the_covered_one_does_not() -> None:
    shortfalls = [
        dict(takes_cycles=False, receipts=5, kinds=4, uneven=2, tracked_from=3, orders=1),
        dict(takes_cycles=True, receipts=0, kinds=0, uneven=0, tracked_from=3, orders=0),
        dict(takes_cycles=True, receipts=5, kinds=0, uneven=0, tracked_from=3, orders=1),
        dict(takes_cycles=True, receipts=5, kinds=4, uneven=4, tracked_from=3, orders=1),
        dict(takes_cycles=True, receipts=5, kinds=4, uneven=2, tracked_from=3, orders=1),
    ]
    for state in shortfalls:
        note = coverage_note(**state)
        assert ASK_NOTE in note, f"недобір без дороги в поле: {note}"

    covered = coverage_note(
        takes_cycles=True, receipts=5, kinds=4, uneven=0, tracked_from=3, orders=1
    )
    assert ASK_NOTE not in covered, (
        "порада там, де недобору немає, читається як докір за покупки, "
        f"яких гість не робив (#101): {covered}"
    )
