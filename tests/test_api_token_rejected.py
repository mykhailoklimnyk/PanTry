from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from komora.api.app import app
from komora.api.auth_routes import require_guest
from komora.auth.session import COOKIE_NAME
from komora.mcp.client import TokenRejected

DOORS = [
    "/api/place",
    "/api/pantry",
    "/api/cart",
    "/api/week-spend",
    "/api/delivery-options",
    "/api/bar",
    "/api/exclusions",
]


class DeadToken:

    def __init__(self, *_args, **_kwargs) -> None: ...

    async def __aenter__(self) -> DeadToken:
        raise TokenRejected("session.initialize", "HTTP 401", attempts=1)

    async def __aexit__(self, *_exc: object) -> bool:
        return False


class Session:

    access = "мертвий-токен"
    refresh = "мертвий-refresh"
    owner = "власник-сесії"


@pytest.fixture
def guest(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr("komora.api.app.SilpoMCP", DeadToken)
    app.dependency_overrides[require_guest] = lambda: Session()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("door", DOORS)
def test_dead_token_asks_to_reconnect(guest: TestClient, door: str) -> None:
    response = guest.get(door)

    assert response.status_code == 401, (
        f"{door} віддав {response.status_code} — гість побачить збій, а не кнопку"
    )


@pytest.mark.parametrize("door", DOORS)
def test_dead_token_puts_out_the_cookie(guest: TestClient, door: str) -> None:
    response = guest.get(door)

    assert COOKIE_NAME in response.headers.get("set-cookie", ""), (
        f"{door} лишив cookie живою"
    )


def test_an_unexpected_failure_leaves_a_trace(monkeypatch, capsys) -> None:

    class Boom:
        def __init__(self, *_a, **_kw) -> None: ...

        async def __aenter__(self) -> Boom:
            raise ValueError("щось геть несподіване")

        async def __aexit__(self, *_exc: object) -> bool:
            return False

    monkeypatch.setattr("komora.api.app.SilpoMCP", Boom)
    app.dependency_overrides[require_guest] = lambda: Session()
    try:
        client = TestClient(app, raise_server_exceptions=False)
        response = client.get("/api/cart")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 500
    assert "api.unhandled" in capsys.readouterr().out, "виняток пройшов повз логи"


def test_the_guest_is_not_shown_our_internals(monkeypatch) -> None:

    class Boom:
        def __init__(self, *_a, **_kw) -> None: ...

        async def __aenter__(self) -> Boom:
            raise ValueError("шлях /opt/komora/src і решта нутрощів")

        async def __aexit__(self, *_exc: object) -> bool:
            return False

    monkeypatch.setattr("komora.api.app.SilpoMCP", Boom)
    app.dependency_overrides[require_guest] = lambda: Session()
    try:
        client = TestClient(app, raise_server_exceptions=False)
        detail = client.get("/api/cart").json()["detail"]
    finally:
        app.dependency_overrides.clear()

    assert "/opt/komora" not in detail
    assert "ValueError" not in detail
