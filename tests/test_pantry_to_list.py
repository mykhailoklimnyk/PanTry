from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from komora.api.app import app
from komora.api.auth_routes import require_guest
from komora.api.schemas import Pantry, PantryItem
from komora.db.wanted import Want


class Session:
    access = "живий-токен"
    refresh = "живий-refresh"
    owner = "власник-сесії"
    account = "відбиток-акаунта"


ROWS = [
    PantryItem(id="1", label="йогурт · питний", unit="шт", state="оцінка"),
    PantryItem(id="2", label="хліб · тостовий", unit="шт", state="оцінка"),
]


@pytest.fixture
def listed() -> dict[str, Want]:
    return {}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, listed: dict[str, Want]) -> TestClient:
    async def _pantry(*_a: Any, **_kw: Any) -> Pantry:
        return Pantry(
            items=[row.model_copy() for row in ROWS],
            receipts=9,
            orders=0,
            kinds=2,
            tracked_from=3,
            unlisted=0,
        )

    async def _wanted(*_a: Any, **_kw: Any) -> dict[str, Want]:
        return listed

    monkeypatch.setattr("komora.api.app._pantry_now", _pantry)
    monkeypatch.setattr("komora.api.app.wanted_store.load", _wanted)
    monkeypatch.setattr("komora.api.app.get_pool", lambda: None)
    app.dependency_overrides[require_guest] = lambda: Session()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_a_row_in_the_list_says_so(client: TestClient, listed: dict[str, Want]) -> None:
    listed["йогурт питний"] = Want(label="йогурт · питний", at_home=True)

    rows = client.get("/api/pantry").json()["items"]

    assert {row["label"]: row["wanted"] for row in rows} == {
        "йогурт · питний": True,
        "хліб · тостовий": False,
    }


def test_the_key_is_the_one_the_list_writes(client: TestClient, listed: dict[str, Want]) -> None:
    listed["йогурт ·"] = Want(label="йогурт · питний", at_home=True)

    rows = client.get("/api/pantry").json()["items"]

    assert all(not row["wanted"] for row in rows), "старий ключ не має збігатись"


def test_an_empty_list_leaves_every_row_alone(client: TestClient) -> None:
    rows = client.get("/api/pantry").json()["items"]

    assert all(not row["wanted"] for row in rows)


def test_a_dead_store_does_not_break_the_pantry(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:

    async def _dead(*_a: Any, **_kw: Any) -> dict[str, Want]:
        raise RuntimeError("сховище не відповіло")

    monkeypatch.setattr("komora.api.app.wanted_store.load", _dead)

    answer = client.get("/api/pantry")

    assert answer.status_code == 200
    assert len(answer.json()["items"]) == 2
