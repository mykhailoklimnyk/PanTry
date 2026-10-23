from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import e2e_port


@pytest.fixture
def killed(monkeypatch):
    seen: list[int] = []
    monkeypatch.setattr(e2e_port, "kill", seen.append)
    return seen


def test_a_free_port_is_left_alone(monkeypatch, killed):
    monkeypatch.setattr(e2e_port, "holders", lambda port=0: [])
    monkeypatch.setattr(e2e_port, "started", lambda name: None)

    assert e2e_port.check() == 0
    assert killed == []


def test_a_live_foreign_run_is_refused_not_killed(monkeypatch, killed, capsys):
    monkeypatch.setattr(e2e_port, "holders", lambda port=0: [4242])
    monkeypatch.setattr(
        e2e_port, "started", running("npx playwright test --project=desktop")
    )

    assert e2e_port.check() == 1
    assert killed == [], "убили чужий живий прогін"
    said = capsys.readouterr().out
    assert "інший процес" in said
    assert "4242" in said, "відмова мусить назвати, ХТО тримає порт"


def running(*command_lines: str):
    return lambda name: (
        "2026-09-08 09:00" if any(name in line for line in command_lines) else None
    )


def test_a_browser_server_next_door_is_not_a_test_run(monkeypatch, killed, capsys):
    left = [7]
    monkeypatch.setattr(e2e_port, "holders", lambda port=0: list(left))
    monkeypatch.setattr(e2e_port, "started", running("npx @playwright/mcp@latest"))
    monkeypatch.setattr(e2e_port, "kill", lambda pid: left.clear())

    assert e2e_port.check() == 0, "сусідній сервер браузера прийнято за прогін тестів"


def test_the_refusal_names_when_the_run_started(monkeypatch, killed, capsys):
    monkeypatch.setattr(e2e_port, "holders", lambda port=0: [4242])
    monkeypatch.setattr(e2e_port, "started", lambda name: "2026-09-07 23:28")

    assert e2e_port.check() == 1
    assert "2026-09-07 23:28" in capsys.readouterr().out


def test_an_orphaned_server_is_swept_and_says_so(monkeypatch, capsys):
    left = [7]
    monkeypatch.setattr(e2e_port, "holders", lambda port=0: list(left))
    monkeypatch.setattr(e2e_port, "started", lambda name: None)
    monkeypatch.setattr(e2e_port, "kill", lambda pid: left.clear())

    assert e2e_port.check() == 0
    said = capsys.readouterr().out
    assert "осиротілий" in said
    assert "7" in said


def test_a_port_that_will_not_free_is_a_refusal_not_a_green_light(monkeypatch, capsys):
    monkeypatch.setattr(e2e_port, "holders", lambda port=0: [9])
    monkeypatch.setattr(e2e_port, "started", lambda name: None)
    monkeypatch.setattr(e2e_port, "kill", lambda pid: None)

    assert e2e_port.check() == 1
    assert "не звільнився" in capsys.readouterr().out


def test_look_only_never_kills(monkeypatch, killed, capsys):
    monkeypatch.setattr(e2e_port, "holders", lambda port=0: [11])
    monkeypatch.setattr(e2e_port, "started", lambda name: None)

    assert e2e_port.check(sweep=False) == 1
    assert killed == []
    assert "зайнятий" in capsys.readouterr().out


def test_the_port_matches_the_playwright_config():
    config = (Path(__file__).resolve().parents[1] / "web" / "playwright.config.ts").read_text(
        encoding="utf-8"
    )
    assert f"--port {e2e_port.PORT}" in config
    assert f"127.0.0.1:{e2e_port.PORT}" in config
