from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import check  # noqa: E402


def _names(paths: list[str], **kw) -> list[str]:
    return [gate.name for gate in check.plan(paths, **kw)]


def test_text_is_checked_even_when_nothing_looks_like_code():
    assert _names([]) == ["текст"]
    assert "текст" in _names(["docs/history.md"])


def test_a_python_change_does_not_drag_the_front_along():
    chosen = _names(["src/komora/core/cycles.py"])

    assert "тести" in chosen and "типи (ty)" in chosen
    assert "e2e" not in chosen
    assert "типи фронта" not in chosen


def test_a_front_change_brings_the_cheap_gates_but_not_e2e():
    chosen = _names(["web/src/lib/screens/Cart.svelte"])

    assert "токени теми" in chosen and "кнопки без обробника" in chosen
    assert "типи фронта" in chosen
    assert "e2e" not in chosen
    assert "тести" not in chosen


def test_the_contract_gate_stands_on_the_file_that_generates_it():
    assert "types.ts" in _names(["src/komora/api/schemas.py"])
    assert "types.ts" not in _names(["src/komora/api/app.py"])


def test_licenses_depend_on_dependencies_not_on_code():
    assert "ліцензії" in _names(["uv.lock"])
    assert "ліцензії" in _names(["web/package-lock.json"])
    assert "ліцензії" not in _names(["src/komora/core/cycles.py"])


def test_full_runs_everything_the_partial_pass_could_ever_choose():
    every = set(_names([], full=True, e2e=True))
    for paths in (
        ["src/komora/api/schemas.py"],
        ["web/src/App.svelte"],
        ["uv.lock"],
        ["docs/history.md"],
        ["scripts/check.py"],
    ):
        assert set(_names(paths)) <= every, paths


def test_full_takes_both_widths_and_the_partial_pass_takes_one():
    full = next(gate for gate in check.plan([], full=True, e2e=True) if gate.name == "e2e")
    assert "--project=desktop" not in full.command

    partial = next(
        gate for gate in check.plan(["web/x.svelte"], e2e=True) if gate.name == "e2e"
    )
    assert "--project=desktop" in partial.command
    assert partial.note and not full.note


def test_e2e_is_asked_for_and_never_arrives_on_its_own():
    chosen = _names(["web/src/App.svelte"], e2e=True)
    assert "e2e" in chosen

    quiet = _names(["web/src/App.svelte"])
    assert "типи фронта" in quiet and "токени теми" in quiet
    assert "e2e" not in quiet


def test_the_cheapest_gate_goes_first_and_the_slowest_last():
    chosen = _names(["src/komora/api/schemas.py", "web/src/App.svelte"], e2e=True)

    assert chosen[0] == "текст"
    assert chosen[-1] == "e2e"
    assert chosen.index("тести") < chosen.index("типи фронта")
    for made in ("types.ts", "facts.ts", "repo-map"):
        assert chosen.index(made) < chosen.index("тести"), made


def test_every_gate_names_where_it_runs():
    for gate in check.plan([], full=True, e2e=True):
        node = gate.command[0] in {"npm", "npx"}
        assert (gate.cwd == "web") == node, gate.name


def test_the_front_gate_calls_npm_and_not_npx_npm():
    front = next(g for g in check.plan([], full=True, e2e=True) if g.name == "типи фронта")
    assert front.command[:2] == ("npm", "run")

    e2e = next(g for g in check.plan([], full=True, e2e=True) if g.name == "e2e")
    assert e2e.command[:2] == ("npx", "playwright")


def test_a_missing_program_is_not_a_red_gate():
    assert check.resolve(["точно-немає-такої-команди"]) is None
    found = check.resolve(["git", "status"])
    assert found is not None and found[1] == "status"


def test_publication_runs_these_very_gates_and_keeps_no_second_list():
    import publish

    assert publish.check is check

    every = set(_names([], full=True, e2e=True))
    assert "e2e" in every and "текст" in every

    without = set(_names([], full=True, e2e=False))
    assert "e2e" not in without
    assert without | {"e2e"} == every, "різниця має бути РІВНО в e2e, а не в чомусь ще"
