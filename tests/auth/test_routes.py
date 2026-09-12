from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException, Response

from komora.api import auth_routes
from komora.auth.crypto import generate_key
from komora.auth.session import COOKIE_NAME, GuestSession, pack

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)


class _Request:

    def __init__(self, cookies: dict[str, str]) -> None:
        self.cookies = cookies


@pytest.fixture
def key(monkeypatch) -> str:
    value = generate_key()
    monkeypatch.setattr(auth_routes.settings, "session_key", value)
    return value


@pytest.mark.parametrize("target", ["/cart", "/pantry?tab=1", "/"])
def test_own_paths_are_kept(target):
    assert auth_routes._safe_return(target) == target


@pytest.mark.parametrize(
    "target",
    [
        "https://evil.example/steal",
        "//evil.example/steal",
        "http://evil.example",
        "javascript:alert(1)",
        "",
        None,
    ],
)
def test_anything_that_leaves_the_site_goes_home(target):
    assert auth_routes._safe_return(target) == auth_routes.HOME


def test_protocol_relative_url_is_the_one_people_forget():
    assert auth_routes._safe_return("//evil.example") == "/"


@pytest.mark.parametrize(
    "target",
    [
        "/\\evil.example",
        "/\\\\evil.example",
        "\\\\evil.example",
    ],
)
def test_backslash_is_a_slash_for_the_browser(target):
    assert auth_routes._safe_return(target) == auth_routes.HOME


@pytest.mark.parametrize("invisible", ["\t", "\n", "\r"])
def test_invisible_characters_do_not_hide_the_second_slash(invisible):
    assert auth_routes._safe_return(f"/{invisible}/evil.example") == auth_routes.HOME


def test_own_path_survives_the_normalisation():
    assert auth_routes._safe_return("/pantry?tab=1") == "/pantry?tab=1"


def test_what_leaves_is_what_was_checked():
    assert auth_routes._safe_return("/cart\n?tab=1") == "/cart?tab=1"


def test_valid_cookie_becomes_a_session(key):
    guest = GuestSession(access="токен", issued_at=NOW, expires_at=NOW + timedelta(days=30))
    request = _Request({COOKIE_NAME: pack(guest, key=key)})
    restored = auth_routes.read_session(request)  # type: ignore[arg-type]
    assert restored is not None and restored.access == "токен"


@pytest.mark.anyio
async def test_whoami_names_the_llm_key_cookie_on_every_state_poll(key):
    from komora.auth import llm_key

    guest = GuestSession(access="токен", issued_at=NOW, expires_at=NOW + timedelta(days=30))
    cookies = {COOKIE_NAME: pack(guest, key=key)}
    bare = await auth_routes.whoami(_Request(cookies), Response())  # type: ignore[arg-type]
    assert bare.connected and bare.llm_key is False

    cookies[llm_key.COOKIE_NAME] = llm_key.pack("sk-test-1234567890abcdef", key=key)
    keyed = await auth_routes.whoami(_Request(cookies), Response())  # type: ignore[arg-type]
    assert keyed.connected and keyed.llm_key is True


def test_no_cookie_is_simply_not_connected(key):
    assert auth_routes.read_session(_Request({})) is None  # type: ignore[arg-type]


def test_broken_cookie_is_not_connected_rather_than_an_error(key):
    assert auth_routes.read_session(_Request({COOKIE_NAME: "сміття"})) is None  # type: ignore[arg-type]


def test_cookie_from_another_key_is_refused(key):
    stranger = pack(GuestSession(access="чуже"), key=generate_key())
    assert auth_routes.read_session(_Request({COOKIE_NAME: stranger})) is None  # type: ignore[arg-type]


def test_without_a_configured_key_nobody_is_connected(monkeypatch):
    monkeypatch.setattr(auth_routes.settings, "session_key", "")
    cookie = pack(GuestSession(access="токен"), key=generate_key())
    assert auth_routes.read_session(_Request({COOKIE_NAME: cookie})) is None  # type: ignore[arg-type]


def test_forget_clears_the_session_cookie():
    response = Response()
    auth_routes.forget(response)
    header = response.headers.get("set-cookie", "")
    assert COOKIE_NAME in header
    assert "Max-Age=0" in header or "expires=" in header.lower()


async def test_no_cookie_is_a_401_not_somebody_elses_data(key):
    with pytest.raises(HTTPException) as exc:
        await auth_routes.require_guest(_Request({}))  # type: ignore[arg-type]

    assert exc.value.status_code == 401
    assert "Сільпо" in str(exc.value.detail)


async def test_expired_session_is_a_401_too(key):
    stale = GuestSession(
        access="токен",
        issued_at=NOW - timedelta(days=40),
        expires_at=NOW - timedelta(days=1),
    )
    with pytest.raises(HTTPException) as exc:
        await auth_routes.require_guest(_Request({COOKIE_NAME: pack(stale, key=key)}))  # type: ignore[arg-type]

    assert exc.value.status_code == 401


async def test_valid_session_passes_the_token_through(key):
    guest = GuestSession(access="токен-гостя", expires_at=NOW + timedelta(days=30))
    passed = await auth_routes.require_guest(  # type: ignore[arg-type]
        _Request({COOKIE_NAME: pack(guest, key=key)})
    )

    assert passed.access == "токен-гостя"


async def test_configured_owner_token_does_not_stand_in_for_a_guest(key, monkeypatch):
    monkeypatch.setattr(auth_routes.settings, "mcp_token", "токен-власника")

    with pytest.raises(HTTPException) as exc:
        await auth_routes.require_guest(_Request({}))  # type: ignore[arg-type]

    assert exc.value.status_code == 401


def test_redirect_uri_is_built_from_our_own_domain(monkeypatch):
    monkeypatch.setattr(auth_routes.settings, "public_url", "https://komora.klimnyk.dev/")
    assert auth_routes._redirect_uri() == "https://komora.klimnyk.dev/api/auth/callback"


def test_forget_keeps_host_prefix_attributes():
    response = Response()
    auth_routes.forget(response)

    header = response.headers["set-cookie"]
    assert COOKIE_NAME in header
    assert "Secure" in header, f"без Secure браузер відкине видалення: {header}"
    assert "Path=/" in header, f"__Host- вимагає Path=/: {header}"
    assert "Domain" not in header, f"__Host- забороняє Domain: {header}"


def _guest(key: str, *, days: int) -> _Request:
    moment = datetime.now(UTC)
    guest = GuestSession(
        access="живий-токен",
        refresh="є-чим-оновити",
        issued_at=moment - timedelta(days=30 - days),
        expires_at=moment + timedelta(days=days),
        owner="власник",
        account="відбиток",
    )
    return _Request({COOKIE_NAME: pack(guest, key=key)})


@pytest.mark.anyio
async def test_a_failed_renewal_says_so_while_the_link_still_works(key, monkeypatch):
    async def _dead(*_a, **_kw):
        return None

    async def _no_greeting(*_a, **_kw):
        return None

    monkeypatch.setattr(auth_routes, "_renew", _dead)
    monkeypatch.setattr(auth_routes, "_greeting", _no_greeting)

    link = await auth_routes.whoami(_guest(key, days=10), Response())

    assert link.connected is True, "чинний токен -- це підключено, і 500 тут був би брехнею"
    assert link.reason is not None, "мовчазна невдача пізніше виглядає як раптовий вихід"
    assert "оновити доступ не вдалося" in link.reason


@pytest.mark.anyio
async def test_a_successful_renewal_stays_silent(key, monkeypatch):

    async def _renewed(guest, *, now):
        return guest

    async def _no_greeting(*_a, **_kw):
        return None

    monkeypatch.setattr(auth_routes, "_renew", _renewed)
    monkeypatch.setattr(auth_routes, "_greeting", _no_greeting)

    link = await auth_routes.whoami(_guest(key, days=10), Response())

    assert link.connected is True
    assert link.reason is None


@pytest.mark.anyio
async def test_nothing_is_said_when_nothing_was_renewed(key, monkeypatch):

    async def _boom(*_a, **_kw):
        raise AssertionError("оновлюватись ще рано")

    async def _no_greeting(*_a, **_kw):
        return None

    monkeypatch.setattr(auth_routes, "_renew", _boom)
    monkeypatch.setattr(auth_routes, "_greeting", _no_greeting)

    link = await auth_routes.whoami(_guest(key, days=29), Response())

    assert link.reason is None


def test_a_lost_session_keeps_the_guests_model_key_and_logout_does_not():
    from starlette.responses import Response

    from komora.auth import llm_key, session

    kept = Response()
    auth_routes.forget(kept, keep_key=True)
    dropped = " ".join(kept.headers.getlist("set-cookie"))
    assert session.COOKIE_NAME in dropped
    assert llm_key.COOKIE_NAME not in dropped

    out = Response()
    auth_routes.forget(out)
    dropped = " ".join(out.headers.getlist("set-cookie"))
    assert session.COOKIE_NAME in dropped and llm_key.COOKIE_NAME in dropped
