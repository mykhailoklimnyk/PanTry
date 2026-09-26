from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _script() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "passk_snapshot", ROOT / "scripts" / "passk_snapshot.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def gate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    module = _script()
    monkeypatch.setattr(module, "SNAPSHOT", tmp_path / "passk.json")
    return module


def _write(gate: ModuleType, prompts: dict[str, str]) -> None:
    gate.SNAPSHOT.write_text(
        json.dumps(
            {
                "date": "2026-09-03",
                "commit": "abc1234",
                "runs": 5,
                "models": {"mistral.large": {"passk": 22, "total": 22, "pass1": 100, "shaky": []}},
                "prompts": prompts,
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _live(gate: ModuleType) -> dict[str, str]:
    return gate._registry()


def test_matching_digests_pass(gate, capsys):
    _write(gate, _live(gate))
    assert gate.check() == 0
    assert "чинний" in capsys.readouterr().out


def test_a_changed_prompt_stops_and_names_itself(gate, capsys):
    stale = _live(gate)
    stale["pick.head"] = "00000000"
    _write(gate, stale)

    assert gate.check() == 1
    said = capsys.readouterr().out
    assert "протухло" in said
    assert "pick.head" in said
    assert "compare_models.py --runs 5 --snapshot" in said


def test_a_prompt_that_vanished_stops_too(gate, capsys):
    stale = _live(gate)
    stale["pick.якого.немає"] = "12345678"
    _write(gate, stale)

    assert gate.check() == 1
    said = capsys.readouterr().out
    assert "промпта більше немає" in said


def test_a_missing_snapshot_stops(gate, capsys):
    assert gate.check() == 1
    assert "Зняти" in capsys.readouterr().out


def test_a_snapshot_without_a_single_digest_stops(gate, capsys):
    _write(gate, {})
    assert gate.check() == 1
    assert "жодного хеша" in capsys.readouterr().out


def test_an_unmeasured_prompt_is_named_but_does_not_stop(gate, capsys):
    live = _live(gate)
    partial = {name: digest for name, digest in live.items() if name != "keeps"}
    assert "keeps" in live, "промпт `keeps` зник — онови тест разом із продуктом"
    _write(gate, partial)

    assert gate.check() == 0
    said = capsys.readouterr().out
    assert "НЕ перевірені" in said
    assert "keeps" in said


def test_the_live_registry_is_the_whole_product(gate):
    live = _live(gate)
    for name in ("pick.head", "pick.tail", "naming", "chain", "loop", "plan"):
        assert name in live
