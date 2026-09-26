from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from komora.agent.pantry import Refined
from komora.agent.probe import Probe
from komora.api.app import app
from komora.api.auth_routes import require_guest
from komora.api.schemas import Pantry


class Session:

    access = "live-token"
    refresh = "live-refresh"
    owner = "власник-сесії"
    account = "відбиток-акаунта"


EMPTY = Pantry(items=[], receipts=1, orders=0, kinds=0, tracked_from=3, unlisted=0)

PROBES = (
    Probe(
        label="хліб",
        ask="як швидко у вас закінчується хліб?",
        covers=("булка", "батон"),
        kind="хліб житній",
        cover_kinds=("булка з", "батон нарізний"),
    ),
)


@pytest.fixture
def saved() -> list[tuple[str, int]]:
    return []


@pytest.fixture
def told() -> list[bool]:
    return []


@pytest.fixture
def client(
    monkeypatch: pytest.MonkeyPatch, saved: list[tuple[str, int]], told: list[bool]
) -> TestClient:
    async def _nothing(*_a: Any, **_kw: Any) -> Any:
        return None

    async def _pantry(*_a: Any, **_kw: Any) -> Pantry:
        return EMPTY

    async def _refine(*_a: Any, **kw: Any) -> Refined:
        told.append(bool(kw.get("answered")))
        return Refined(pantry=EMPTY, note="уточнено: 0", probes=PROBES)

    async def _save_cycle(_pool: Any, _account: str, kind: str, days: int) -> None:
        saved.append((kind, days))

    class _Port:

        def __init__(self, **_kw: Any) -> None:
            self.pressure = 0

        async def __aenter__(self) -> Any:
            return self

        async def __aexit__(self, *_exc: Any) -> None:
            return None

    monkeypatch.setattr("komora.api.app.SilpoMCP", _Port)
    monkeypatch.setattr("komora.api.app.place_of", _nothing)
    monkeypatch.setattr("komora.api.app._seen_receipts", _nothing)
    monkeypatch.setattr("komora.api.app.pantry_live", _pantry)
    monkeypatch.setattr("komora.api.app._pantry_now", _pantry)
    monkeypatch.setattr("komora.api.app.refine_pantry", _refine)
    monkeypatch.setattr("komora.api.app.pantry_marks.save_cycle", _save_cycle)
    monkeypatch.setattr("komora.api.app.wanted_store.load", _nothing)
    monkeypatch.setattr("komora.api.app.get_pool", lambda: None)
    app.dependency_overrides[require_guest] = lambda: Session()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_the_questions_ride_out_with_the_pantry(client: TestClient) -> None:
    answer = client.post("/api/pantry/refine", json={})
    assert answer.status_code == 200, answer.text[:300]
    body = answer.json()
    assert "asked" in body, sorted(body)[:12]

    assert body["asked"] == [
        {
            "label": "хліб",
            "ask": "як швидко у вас закінчується хліб?",
            "covers": ["булка", "батон"],
            "kind": "хліб житній",
            "coverKinds": ["булка з", "батон нарізний"],
            "usual": "",
        }
    ]


def test_an_answer_lands_in_the_same_home_as_the_guest_word(
    client: TestClient, saved: list[tuple[str, int]]
) -> None:
    client.post(
        "/api/pantry/refine",
        json={"answers": {"хліб": 2}, "kinds": {"хліб": "хліб житній"}},
    )

    assert saved == [("хліб житній", 2)]


def test_a_run_without_answers_writes_nothing(
    client: TestClient, saved: list[tuple[str, int]]
) -> None:
    client.post("/api/pantry/refine", json={})

    assert saved == []


def test_more_answers_than_questions_are_cut_to_the_ceiling(
    client: TestClient, saved: list[tuple[str, int]]
) -> None:
    client.post(
        "/api/pantry/refine",
        json={
            "answers": {f"вид {n}": n + 1 for n in range(9)},
            "kinds": {f"вид {n}": f"ключ {n}" for n in range(9)},
        },
    )

    assert len(saved) == 3


def test_an_answer_without_a_write_key_is_refused_instead_of_written(
    client: TestClient, saved: list[tuple[str, int]]
) -> None:
    client.post("/api/pantry/refine", json={"answers": {"хліб": 2}})

    assert saved == []


def test_the_loop_is_told_what_the_guest_just_said(client: TestClient, told: list[bool]) -> None:
    client.post("/api/pantry/refine", json={})
    client.post(
        "/api/pantry/refine",
        json={"answers": {"хліб": 2}, "kinds": {"хліб": "хліб житній"}},
    )

    assert told == [False, True]


def test_the_cut_of_the_guest_answers_names_itself(
    client: TestClient, saved: list[tuple[str, int]]
) -> None:
    from structlog.testing import capture_logs

    with capture_logs() as written:
        client.post(
            "/api/pantry/refine",
            json={
                "answers": {f"вид {n}": n + 1 for n in range(9)},
                "kinds": {f"вид {n}": f"ключ {n}" for n in range(9)},
            },
        )

    assert len(saved) == 3
    capped = [one for one in written if one.get("event") == "pantry.answers_capped"]
    assert capped, [one.get("event") for one in written]
    assert capped[0]["got"] == 9
    assert capped[0]["kept"] == 3
    assert capped[0]["cut"], "зрізане називається поіменно, а не числом"


def test_a_cut_that_did_not_happen_says_nothing(client: TestClient) -> None:
    from structlog.testing import capture_logs

    with capture_logs() as written:
        client.post(
            "/api/pantry/refine",
            json={"answers": {"хліб": 2}, "kinds": {"хліб": "хліб житній"}},
        )

    assert not [one for one in written if one.get("event") == "pantry.answers_capped"]


def test_the_cut_of_the_covers_names_itself(client: TestClient) -> None:
    from structlog.testing import capture_logs

    with capture_logs() as written:
        client.post(
            "/api/pantry/refine",
            json={
                "answers": {"хліб": 2},
                "kinds": {"хліб": "хліб житній"},
                "covers": {"хліб": [f"сусід {n}" for n in range(20)]},
            },
        )

    capped = [one for one in written if one.get("event") == "pantry.covers_capped"]
    assert capped, [one.get("event") for one in written]
    assert capped[0]["got"] == 20
