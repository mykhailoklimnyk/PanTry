from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from komora.api import progress
from komora.api.schemas import TraceOption, TraceQuestion, TraceStep

NOW = datetime(2026, 9, 2, 20, 0, tzinfo=UTC)


def _step(seq: int) -> TraceStep:
    return TraceStep(
        id=f"step-{seq}", seq=seq, tool="t", args={}, duration_ms=0, result_summary=f"крок {seq}"
    )


@pytest.fixture(autouse=True)
def _clean():
    progress.forget_all()
    yield
    progress.forget_all()


def test_steps_are_readable_the_moment_they_are_pushed():
    progress.open_channel("key-1", owner="гість", now=NOW)
    assert progress.read("key-1", owner="гість", now=NOW) == progress.Progress(steps=(), done=False)

    progress.push("key-1", _step(1))
    progress.push("key-1", _step(2))
    seen = progress.read("key-1", owner="гість", now=NOW)
    assert seen is not None
    assert [s.seq for s in seen.steps] == [1, 2] and seen.done is False

    progress.finish("key-1", now=NOW)
    assert progress.read("key-1", owner="гість", now=NOW).done is True  # type: ignore[union-attr]


def test_a_foreign_key_and_a_missing_key_look_the_same():
    progress.open_channel("key-1", owner="гість", now=NOW)
    assert progress.read("key-1", owner="сусід", now=NOW) is None
    assert progress.read("key-9", owner="гість", now=NOW) is None


def test_a_push_into_no_channel_does_not_break_the_build():
    progress.push("nobody", _step(1))
    progress.finish("nobody")


def test_a_finished_channel_stops_taking_steps_and_dies_after_its_ttl():
    progress.open_channel("key-1", owner="гість", now=NOW)
    progress.finish("key-1", now=NOW)
    progress.push("key-1", _step(1))
    assert progress.read("key-1", owner="гість", now=NOW).steps == ()  # type: ignore[union-attr]

    later = NOW + progress.DONE_TTL + timedelta(seconds=1)
    assert progress.read("key-1", owner="гість", now=later) is None


def test_a_build_that_never_finished_is_swept_and_the_oldest_channels_give_way():
    progress.open_channel("stale", owner="гість", now=NOW)
    later = NOW + progress.STALE_TTL + timedelta(seconds=1)
    assert progress.read("stale", owner="гість", now=later) is None

    for i in range(progress.MAX_CHANNELS + 1):
        progress.open_channel(f"k{i}", owner="гість", now=NOW)
    assert progress.read("k0", owner="гість", now=NOW) is None
    assert progress.read(f"k{progress.MAX_CHANNELS}", owner="гість", now=NOW) is not None


def test_reopening_the_same_key_starts_clean():
    progress.open_channel("key-1", owner="гість", now=NOW)
    progress.push("key-1", _step(1))
    progress.open_channel("key-1", owner="гість", now=NOW)
    assert progress.read("key-1", owner="гість", now=NOW).steps == ()  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("key", "ok"),
    [
        ("2f1c9a4e-7b3d-4c1e-9f0a-1b2c3d4e5f60", True),
        ("abcdefgh", True),
        ("short", False),
        ("", False),
        (None, False),
        ("з пробілом і кирилицею", False),
        ("x" * 65, False),
    ],
)
def test_the_key_is_shaped_like_an_id_because_it_rides_in_the_path(key, ok):
    assert progress.valid_key(key) is ok


class _Guest:
    access = "живий-токен"
    refresh = None
    owner = "власник-сесії"
    account = "відбиток"


def test_the_endpoint_shows_own_steps_and_hides_foreign_and_malformed_keys():
    from fastapi.testclient import TestClient

    from komora.api.app import app
    from komora.api.auth_routes import require_guest

    channel = "2f1c9a4e-7b3d-4c1e-9f0a-1b2c3d4e5f60"
    live = datetime.now(UTC)
    progress.open_channel(channel, owner="власник-сесії", now=live)
    progress.push(channel, _step(1))
    app.dependency_overrides[require_guest] = _Guest
    try:
        client = TestClient(app)
        seen = client.get(f"/api/progress/{channel}")
        assert seen.status_code == 200
        assert [s["seq"] for s in seen.json()["steps"]] == [1] and seen.json()["done"] is False
        assert client.get("/api/progress/no-such-key-here").status_code == 404
        assert client.get("/api/progress/bad key").status_code == 404
        progress.open_channel("someone-elses-key", owner="сусід", now=live)
        assert client.get("/api/progress/someone-elses-key").status_code == 404
    finally:
        app.dependency_overrides.clear()


def _asking(seq: int = 1) -> TraceStep:
    return TraceStep(
        id="step-ask",
        seq=seq,
        tool="agent.understand",
        args={},
        result_summary="питаю гостя",
        question=TraceQuestion(
            id="q1",
            ask="Готуєш сам чи береш готове?",
            options=[
                TraceOption(id="o1", label="готую сам", style="cooking"),
                TraceOption(id="o2", label="беру готове", style="ready"),
            ],
            wait_s=25,
        ),
    )


async def test_the_answer_reaches_the_build_that_is_waiting_for_it():
    progress.open_channel("key-1", owner="гість")
    progress.push("key-1", _asking())

    waiting = asyncio.ensure_future(progress.wait("key-1", "q1", seconds=5))
    await asyncio.sleep(0)
    assert progress.answer("key-1", owner="гість", question_id="q1", option_id="o2") is True

    assert await waiting == "o2"


async def test_waiting_for_an_answer_that_never_comes_ends_by_the_ceiling():
    progress.open_channel("key-1", owner="гість")
    progress.push("key-1", _asking())

    assert await progress.wait("key-1", "q1", seconds=0.05) is None


async def test_waiting_for_a_question_nobody_asked_returns_at_once():
    progress.open_channel("key-1", owner="гість")

    assert await progress.wait("key-1", "q1", seconds=5) is None
    assert await progress.wait("no-such-key", "q1", seconds=5) is None


def test_a_foreign_owner_cannot_answer_for_the_guest():
    progress.open_channel("key-1", owner="гість")
    progress.push("key-1", _asking())

    assert progress.answer("key-1", owner="сусід", question_id="q1", option_id="o1") is False


def test_an_option_that_was_never_shown_is_refused():
    progress.open_channel("key-1", owner="гість")
    progress.push("key-1", _asking())

    assert progress.answer("key-1", owner="гість", question_id="q1", option_id="o9") is False
    assert progress.answer("key-1", owner="гість", question_id="q9", option_id="o1") is False


def test_the_second_answer_to_the_same_question_is_ignored():
    progress.open_channel("key-1", owner="гість")
    progress.push("key-1", _asking())

    assert progress.answer("key-1", owner="гість", question_id="q1", option_id="o1") is True
    assert progress.answer("key-1", owner="гість", question_id="q1", option_id="o2") is False


def test_the_answer_endpoint_hides_a_foreign_channel_behind_the_same_404():
    from fastapi.testclient import TestClient

    from komora.api.app import app
    from komora.api.auth_routes import require_guest

    channel = "3a2b1c0d-9e8f-4a7b-8c6d-5e4f3a2b1c0d"
    live = datetime.now(UTC)
    progress.open_channel(channel, owner="власник-сесії", now=live)
    progress.push(channel, _asking())
    app.dependency_overrides[require_guest] = _Guest
    try:
        client = TestClient(app)
        said = client.post(
            f"/api/progress/{channel}/answer",
            json={"questionId": "q1", "optionId": "o1"},
        )
        assert said.status_code == 200 and said.json()["taken"] is True

        progress.open_channel("someone-elses-key", owner="сусід", now=live)
        assert (
            client.post(
                "/api/progress/someone-elses-key/answer",
                json={"questionId": "q1", "optionId": "o1"},
            ).status_code
            == 404
        )
        assert (
            client.post(
                "/api/progress/bad key/answer", json={"questionId": "q1", "optionId": "o1"}
            ).status_code
            == 404
        )
    finally:
        app.dependency_overrides.clear()


def test_an_answer_that_came_too_late_is_a_fact_not_an_error():
    from fastapi.testclient import TestClient

    from komora.api.app import app
    from komora.api.auth_routes import require_guest

    channel = "4b3c2d1e-0f9a-4b8c-9d7e-6f5a4b3c2d1e"
    progress.open_channel(channel, owner="власник-сесії", now=datetime.now(UTC))
    app.dependency_overrides[require_guest] = _Guest
    try:
        said = TestClient(app).post(
            f"/api/progress/{channel}/answer",
            json={"questionId": "q1", "optionId": "o1"},
        )
        assert said.status_code == 200 and said.json()["taken"] is False
    finally:
        app.dependency_overrides.clear()
