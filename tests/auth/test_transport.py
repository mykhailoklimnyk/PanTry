from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient

from komora.api import auth_routes
from komora.api.app import app
from komora.auth import client as oauth
from komora.auth import flow, pkce
from komora.auth.crypto import generate_key
from komora.auth.session import COOKIE_NAME, GuestSession, pack

NOW = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)

BASE = "https://mcp.silpo.ua"
REDIRECT = "https://komora.klimnyk.dev/api/auth/callback"

ENDPOINTS = oauth.Endpoints(
    authorize=f"{BASE}/authorize",
    token=f"{BASE}/token",
    register=f"{BASE}/register",
    revoke=f"{BASE}/token",
)


def _refuse(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


def _dead_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(_refuse))


@pytest.fixture
def dead_mcp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(oauth, "http_client", _dead_client)


@pytest.fixture
def key(monkeypatch: pytest.MonkeyPatch) -> str:
    value = generate_key()
    monkeypatch.setattr(auth_routes.settings, "session_key", value)
    monkeypatch.setattr(auth_routes.settings, "oauth_client_id", "komora-test")
    return value


@pytest.fixture
def guest() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


def _cookie(value: str, *, name: str = COOKIE_NAME) -> dict[str, str]:
    return {"cookie": f"{name}={value}"}


def _renewable(key: str) -> str:
    session = GuestSession(
        access="живий-токен",
        refresh="живий-refresh",
        issued_at=datetime.now(UTC) - timedelta(days=20),
        expires_at=datetime.now(UTC) + timedelta(days=10),
    )
    assert session.renewable(datetime.now(UTC)), "сесія не в тому вікні, тест міряє не те"
    return pack(session, key=key)


def _explode(owner: str) -> None:
    raise RuntimeError("прибирання впало")


def _put_out(response: httpx.Response) -> bool:
    return any(
        COOKIE_NAME in header and ("Max-Age=0" in header or "01 Jan 1970" in header)
        for header in response.headers.get_list("set-cookie")
    )


def test_logout_puts_out_the_cookie_even_when_mcp_is_down(
    guest: TestClient, key: str, dead_mcp: None
) -> None:
    response = guest.post("/api/auth/logout", headers=_cookie(_renewable(key)))

    assert response.status_code != 500, "гість натиснув «Вийти» і побачив збій"
    assert response.status_code == 204
    assert _put_out(response), "cookie лишилась живою — гість вийшов лише на вигляд"


def test_session_stays_connected_when_renewal_cannot_reach_mcp(
    guest: TestClient, key: str, dead_mcp: None
) -> None:
    response = guest.get("/api/auth/session", headers=_cookie(_renewable(key)))

    assert response.status_code == 200, "фронт прочитає це як «бекенда немає»"
    assert response.json()["connected"] is True
    assert not _put_out(response), "чинний токен викинуто через чужу мережу"


def test_start_answers_with_a_page_not_json(guest: TestClient, key: str, dead_mcp: None) -> None:
    response = guest.get("/api/auth/start", follow_redirects=False)

    assert response.status_code != 500, "у вкладці відкрилась помилка, а не сторінка"
    assert response.status_code == 303
    assert response.headers["location"] == auth_routes.HOME


def test_callback_answers_with_a_page_not_json(
    guest: TestClient, key: str, dead_mcp: None
) -> None:
    handshake = pkce.start()
    pending = flow.start(handshake, return_to="/", now=datetime.now(UTC))
    response = guest.get(
        f"/api/auth/callback?code=код&state={handshake.state}",
        headers=_cookie(flow.pack(pending, key=key), name=flow.COOKIE_NAME),
        follow_redirects=False,
    )

    assert response.status_code != 500, "у вкладці відкрилась помилка, а не сторінка"
    assert response.status_code == 303
    assert response.headers["location"] == auth_routes.HOME


def test_one_failing_cleanup_does_not_cancel_the_others(
    guest: TestClient, key: str, dead_mcp: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    swept: list[str] = []
    monkeypatch.setattr(auth_routes.places, "forget", _explode)
    monkeypatch.setattr(auth_routes.runs, "forget", lambda owner: swept.append("runs"))
    monkeypatch.setattr(auth_routes.quota, "forget", lambda owner: swept.append("quota"))

    response = guest.post("/api/auth/logout", headers=_cookie(_renewable(key)))

    assert response.status_code == 204
    assert _put_out(response), "cookie мусить гаснути і тут"
    assert swept == ["runs", "quota"], f"впала перша прибиральниця забрала решту: {swept}"


@pytest.mark.parametrize("door", ["/api/auth/start", "/api/auth/callback"])
def test_a_missing_session_key_is_a_page_not_json(
    guest: TestClient, monkeypatch: pytest.MonkeyPatch, door: str
) -> None:
    monkeypatch.setattr(auth_routes.settings, "session_key", "")

    response = guest.get(door, follow_redirects=False)

    assert response.status_code == 303, "гість побачив JSON замість сторінки"
    assert response.headers["location"] == auth_routes.HOME


CALLS = {
    "discover": lambda http: oauth.discover(BASE, http=http),
    "register_client": lambda http: oauth.register_client(
        ENDPOINTS, redirect_uri=REDIRECT, name="Комора", http=http
    ),
    "exchange": lambda http: oauth.exchange(
        ENDPOINTS, client_id="c", code="код", verifier="v", redirect_uri=REDIRECT, http=http
    ),
    "renew": lambda http: oauth.renew(ENDPOINTS, client_id="c", refresh_token="r", http=http),
    "revoke": lambda http: oauth.revoke(ENDPOINTS, client_id="c", token="t", http=http),
}

RAISING = [name for name in CALLS if name != "revoke"]


@pytest.mark.parametrize("name", RAISING)
async def test_transport_failure_leaves_the_port_as_auth_error(name: str) -> None:
    async with _dead_client() as http:
        with pytest.raises(oauth.AuthError):
            await CALLS[name](http)


@pytest.mark.parametrize("name", RAISING)
async def test_a_body_that_is_not_json_leaves_the_port_as_auth_error(name: str) -> None:

    def html(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>502 Bad Gateway</html>")

    async with httpx.AsyncClient(transport=httpx.MockTransport(html)) as http:
        with pytest.raises(oauth.AuthError):
            await CALLS[name](http)


async def test_revoke_keeps_its_promise_not_to_raise() -> None:
    async with _dead_client() as http:
        assert await CALLS["revoke"](http) is False


def _module_coroutines() -> dict[str, object]:
    return {
        name: func
        for name, func in inspect.getmembers(oauth, inspect.iscoroutinefunction)
        if func.__module__ == oauth.__name__
    }


def test_no_coroutine_reaches_the_network_behind_the_ports_back() -> None:
    offenders = {
        name: [call for call in ("http.get(", "http.post(", "http.request(") if call in source]
        for name, func in _module_coroutines().items()
        if name != "_ask"
        for source in [inspect.getsource(func)]
        if any(call in source for call in ("http.get(", "http.post(", "http.request("))
    }

    assert not offenders, f"повз `_ask` у мережу ходять: {offenders}"


def test_every_public_coroutine_is_tried_against_a_dead_transport() -> None:
    public = {name for name in _module_coroutines() if not name.startswith("_")}

    assert public == set(CALLS), f"порт і таблиця розійшлись: {public ^ set(CALLS)}"
