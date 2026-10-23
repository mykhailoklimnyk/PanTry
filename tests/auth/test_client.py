from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from komora.auth.client import (
    AuthError,
    Endpoints,
    authorize_url,
    discover,
    exchange,
    register_client,
    renew,
    revoke,
)

BASE = "https://mcp.silpo.ua"
REDIRECT = "https://komora.klimnyk.dev/api/auth/callback"

METADATA = {
    "issuer": BASE,
    "authorization_endpoint": f"{BASE}/authorize",
    "token_endpoint": f"{BASE}/token",
    "registration_endpoint": f"{BASE}/register",
    "revocation_endpoint": f"{BASE}/token",
    "grant_types_supported": ["authorization_code", "refresh_token"],
    "code_challenge_methods_supported": ["plain", "S256"],
}

ENDPOINTS = Endpoints(
    authorize=f"{BASE}/authorize",
    token=f"{BASE}/token",
    register=f"{BASE}/register",
    revoke=f"{BASE}/token",
)


def client_of(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_discover_reads_all_four_addresses():
    async with client_of(lambda r: httpx.Response(200, json=METADATA)) as http:
        found = await discover(BASE, http=http)
    assert found == ENDPOINTS
    assert found.can_revoke


async def test_discover_survives_a_server_without_revocation():
    lean = {k: v for k, v in METADATA.items() if k != "revocation_endpoint"}
    async with client_of(lambda r: httpx.Response(200, json=lean)) as http:
        found = await discover(BASE, http=http)
    assert found.revoke is None
    assert not found.can_revoke


async def test_discover_names_the_missing_field():
    broken = {k: v for k, v in METADATA.items() if k != "token_endpoint"}
    async with client_of(lambda r: httpx.Response(200, json=broken)) as http:
        with pytest.raises(AuthError, match="token_endpoint"):
            await discover(BASE, http=http)


async def test_discover_refuses_to_guess_when_metadata_is_down():
    async with client_of(lambda r: httpx.Response(503)) as http:
        with pytest.raises(AuthError, match="503"):
            await discover(BASE, http=http)


async def test_registration_declares_a_public_client():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        return httpx.Response(201, json={"client_id": "komora-1"})

    async with client_of(handler) as http:
        client_id = await register_client(
            ENDPOINTS, redirect_uri=REDIRECT, name="Комора", http=http
        )

    assert client_id == "komora-1"
    assert seen["redirect_uris"] == [REDIRECT]
    assert seen["token_endpoint_auth_method"] == "none", "секрету в публічного клієнта немає"
    assert "refresh_token" in seen["grant_types"], "без цього оновлення на візиті неможливе"


async def test_registration_without_client_id_is_an_error():
    async with client_of(lambda r: httpx.Response(201, json={"ok": True})) as http:
        with pytest.raises(AuthError, match="client_id"):
            await register_client(ENDPOINTS, redirect_uri=REDIRECT, name="Комора", http=http)


def test_authorize_url_carries_s256_not_plain():
    url = authorize_url(
        ENDPOINTS, client_id="komora-1", redirect_uri=REDIRECT, challenge="ch", state="st"
    )
    query = parse_qs(urlparse(url).query)
    assert query["code_challenge_method"] == ["S256"]
    assert query["code_challenge"] == ["ch"]
    assert query["state"] == ["st"]
    assert query["redirect_uri"] == [REDIRECT]
    assert query["response_type"] == ["code"]


def test_authorize_url_never_carries_the_verifier():
    url = authorize_url(
        ENDPOINTS, client_id="komora-1", redirect_uri=REDIRECT, challenge="ch", state="st"
    )
    assert "code_verifier" not in url


async def test_exchange_sends_the_verifier_and_the_same_redirect():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(parse_qs(request.content.decode()))
        return httpx.Response(200, json={"access_token": "at", "expires_in": 2592000})

    async with client_of(handler) as http:
        payload = await exchange(
            ENDPOINTS,
            client_id="komora-1",
            code="code-1",
            verifier="v",
            redirect_uri=REDIRECT,
            http=http,
        )

    assert payload["access_token"] == "at"
    assert seen["code_verifier"] == ["v"]
    assert seen["redirect_uri"] == [REDIRECT]
    assert seen["grant_type"] == ["authorization_code"]


async def test_oauth_error_is_reported_as_its_cause():

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "invalid_grant"})

    async with client_of(handler) as http:
        with pytest.raises(AuthError, match="invalid_grant"):
            await exchange(
                ENDPOINTS,
                client_id="komora-1",
                code="стертий",
                verifier="v",
                redirect_uri=REDIRECT,
                http=http,
            )


async def test_renew_uses_the_refresh_grant():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(parse_qs(request.content.decode()))
        return httpx.Response(200, json={"access_token": "новий", "expires_in": 2592000})

    async with client_of(handler) as http:
        payload = await renew(ENDPOINTS, client_id="komora-1", refresh_token="rt", http=http)

    assert payload["access_token"] == "новий"
    assert seen["grant_type"] == ["refresh_token"]
    assert seen["refresh_token"] == ["rt"]


async def test_revoke_reports_success():
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(parse_qs(request.content.decode()))
        return httpx.Response(200)

    async with client_of(handler) as http:
        assert await revoke(ENDPOINTS, client_id="komora-1", token="rt", http=http)

    assert seen["token"] == ["rt"]
    assert seen["token_type_hint"] == ["refresh_token"]


async def test_revoke_failure_does_not_block_logout():
    async with client_of(lambda r: httpx.Response(500)) as http:
        assert not await revoke(ENDPOINTS, client_id="komora-1", token="rt", http=http)


async def test_revoke_without_an_endpoint_says_no_instead_of_pretending():
    lean = Endpoints(authorize="a", token="t", register="r")
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200)

    async with client_of(handler) as http:
        assert not await revoke(lean, client_id="komora-1", token="rt", http=http)
    assert calls == [], "нікуди не ходимо, якщо адреси немає"
