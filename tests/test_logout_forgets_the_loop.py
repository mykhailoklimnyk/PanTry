from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from komora.agent import pantry as pantry_loop
from komora.api import auth_routes
from komora.api.app import app


class Guest:
    access = "живий-токен"
    refresh = "живий-refresh"
    owner = "власник-сесії"
    account = "відбиток-акаунта"

    def expired(self, _now: Any) -> bool:
        return False


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    async def _revoked(*_a: Any, **_kw: Any) -> bool:
        return True

    monkeypatch.setattr(auth_routes, "read_session", lambda _request: Guest())
    monkeypatch.setattr(auth_routes, "_revoke", _revoked)
    return TestClient(app)


def test_logout_forgets_the_pantry_loop_mark(client: TestClient) -> None:
    pantry_loop.forget_loop()
    pantry_loop._SEEN[Guest.account] = "відбиток входу"

    assert client.post("/api/auth/logout").status_code == 204

    assert Guest.account not in pantry_loop._SEEN


def test_logout_does_not_wipe_the_marks_of_other_accounts(client: TestClient) -> None:
    pantry_loop.forget_loop()
    pantry_loop._SEEN["сусід"] = "його відбиток"
    pantry_loop._SEEN[Guest.account] = "відбиток входу"

    client.post("/api/auth/logout")

    assert pantry_loop._SEEN.get("сусід") == "його відбиток"


def test_a_session_without_an_account_leaves_everyone_alone(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:

    class Nameless(Guest):
        account = ""

    monkeypatch.setattr(auth_routes, "read_session", lambda _request: Nameless())
    pantry_loop.forget_loop()
    pantry_loop._SEEN["сусід"] = "його відбиток"

    client.post("/api/auth/logout")

    assert pantry_loop._SEEN.get("сусід") == "його відбиток"
