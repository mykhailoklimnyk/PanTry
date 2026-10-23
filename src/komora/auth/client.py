from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx

from komora.logging import get_logger

log = get_logger(__name__)

TIMEOUT_S = 20.0


class AuthError(RuntimeError):
    ...


_UNREACHABLE = (httpx.HTTPError, httpx.InvalidURL, OSError)


async def _ask(
    http: httpx.AsyncClient, method: str, url: str, *, what: str, **kwargs: Any
) -> httpx.Response:
    try:
        return await http.request(method, url, **kwargs)
    except _UNREACHABLE as exc:
        raise AuthError(f"{what}: сервер не відповів ({type(exc).__name__})") from exc


def _payload(response: httpx.Response, *, what: str) -> Any:
    try:
        return response.json()
    except ValueError as exc:
        raise AuthError(f"{what}: відповідь не JSON") from exc


@dataclass(frozen=True, slots=True)
class Endpoints:
    authorize: str
    token: str
    register: str
    revoke: str | None = None

    @property
    def can_revoke(self) -> bool:
        return bool(self.revoke)


async def discover(base_url: str, *, http: httpx.AsyncClient) -> Endpoints:
    url = base_url.rstrip("/") + "/.well-known/oauth-authorization-server"
    what = "метадані OAuth"
    response = await _ask(http, "GET", url, what=what)
    if response.status_code >= 400:
        raise AuthError(f"метадані OAuth недоступні: {response.status_code}")

    data = _payload(response, what=what)
    try:
        return Endpoints(
            authorize=data["authorization_endpoint"],
            token=data["token_endpoint"],
            register=data["registration_endpoint"],
            revoke=data.get("revocation_endpoint"),
        )
    except KeyError as exc:
        raise AuthError(f"у метаданих OAuth немає {exc.args[0]}") from exc


async def register_client(
    endpoints: Endpoints, *, redirect_uri: str, name: str, http: httpx.AsyncClient
) -> str:
    what = "реєстрація клієнта"
    response = await _ask(
        http,
        "POST",
        endpoints.register,
        what=what,
        json={
            "client_name": name,
            "redirect_uris": [redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
        },
    )
    if response.status_code >= 400:
        raise AuthError(f"реєстрація клієнта відмовлена: {response.status_code}")

    client_id = _payload(response, what=what).get("client_id")
    if not client_id:
        raise AuthError("сервер зареєстрував клієнта, але не повернув client_id")
    log.info("auth.client_registered", redirect_uri=redirect_uri)
    return str(client_id)


def authorize_url(
    endpoints: Endpoints,
    *,
    client_id: str,
    redirect_uri: str,
    challenge: str,
    state: str,
) -> str:
    query = urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
        }
    )
    return f"{endpoints.authorize}?{query}"


async def _token_call(
    endpoints: Endpoints, form: dict[str, str], *, http: httpx.AsyncClient
) -> dict[str, Any]:
    what = "обмін токена"
    response = await _ask(http, "POST", endpoints.token, what=what, data=form)
    if response.status_code >= 400:
        detail = ""
        try:
            detail = str(response.json().get("error") or "")
        except ValueError:
            detail = response.text[:120]
        raise AuthError(f"{endpoints.token}: {response.status_code} {detail}".strip())

    payload = _payload(response, what=what)
    if not isinstance(payload, dict):
        raise AuthError("відповідь /token не об'єкт")
    return payload


async def exchange(
    endpoints: Endpoints,
    *,
    client_id: str,
    code: str,
    verifier: str,
    redirect_uri: str,
    http: httpx.AsyncClient,
) -> dict[str, Any]:
    return await _token_call(
        endpoints,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
            "client_id": client_id,
            "code_verifier": verifier,
        },
        http=http,
    )


async def renew(
    endpoints: Endpoints, *, client_id: str, refresh_token: str, http: httpx.AsyncClient
) -> dict[str, Any]:
    return await _token_call(
        endpoints,
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": client_id,
        },
        http=http,
    )


async def revoke(
    endpoints: Endpoints,
    *,
    client_id: str,
    token: str,
    hint: str = "refresh_token",
    http: httpx.AsyncClient,
) -> bool:
    if not endpoints.revoke:
        return False
    try:
        response = await _ask(
            http,
            "POST",
            endpoints.revoke,
            what="відкликання токена",
            data={"token": token, "token_type_hint": hint, "client_id": client_id},
        )
    except AuthError as exc:
        log.warning("auth.revoke_unreachable", error=str(exc)[:90])
        return False
    if response.status_code == 200:
        return True
    log.warning("auth.revoke_failed", status=response.status_code)
    return False


def http_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=TIMEOUT_S)


__all__ = [
    "AuthError",
    "Endpoints",
    "authorize_url",
    "discover",
    "exchange",
    "http_client",
    "register_client",
    "renew",
    "revoke",
]
