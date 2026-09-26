from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from typing import Annotated
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from structlog.contextvars import bind_contextvars

from komora.agent.pantry import forget_loop
from komora.api import history, places, quota, runs
from komora.api.schemas import GuestLink, LlmKeyRequest
from komora.auth import client as oauth
from komora.auth import flow, llm_key, pkce, session
from komora.auth.crypto import SealError
from komora.config import settings
from komora.db import newcomers
from komora.db.pool import get_pool
from komora.logging import get_logger
from komora.mcp.client import MCPCallError, SilpoMCP

log = get_logger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

HOME = "/"


def _key() -> str:
    if not settings.guest_login_ready:
        raise HTTPException(
            status_code=503,
            detail="Вхід гостя не налаштований: немає KOMORA_SESSION_KEY.",
        )
    return settings.session_key


def _configured() -> str | None:
    try:
        return _key()
    except HTTPException as exc:
        log.error("auth.not_configured", error=str(exc.detail)[:90])
        return None


def _redirect_uri() -> str:
    return settings.public_url.rstrip("/") + "/api/auth/callback"


_DROPPED_BY_BROWSER = ("\t", "\n", "\r")


def _safe_return(target: str | None) -> str:
    if not target:
        return HOME
    probe = target.replace("\\", "/")
    for char in _DROPPED_BY_BROWSER:
        probe = probe.replace(char, "")
    if not probe.startswith("/") or probe.startswith("//"):
        return HOME
    return probe


def _set_cookie(response: Response, name: str, value: str, *, max_age: int) -> None:
    response.set_cookie(
        name,
        value,
        max_age=max_age,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/",
    )


def read_session(request: Request) -> session.GuestSession | None:
    raw = request.cookies.get(session.COOKIE_NAME)
    if not raw or not settings.guest_login_ready:
        return None
    try:
        return session.unpack(raw, key=settings.session_key)
    except (SealError, ValueError) as exc:
        log.info("auth.cookie_unreadable", error=str(exc)[:80])
        return None


def _drop_cookie(response: Response, name: str) -> None:
    response.delete_cookie(name, path="/", secure=True, httponly=True, samesite="lax")


def read_llm_key(request: Request) -> str | None:
    raw = request.cookies.get(llm_key.COOKIE_NAME)
    if not raw:
        return None
    try:
        return llm_key.unpack(raw, key=settings.session_key)
    except (SealError, ValueError) as exc:
        log.info("auth.llm_key_unreadable", error=str(exc)[:80])
        return None


LlmKey = Annotated[str | None, Depends(read_llm_key)]


def forget(response: Response, *, keep_key: bool = False) -> None:
    _drop_cookie(response, session.COOKIE_NAME)
    if not keep_key:
        _drop_cookie(response, llm_key.COOKIE_NAME)


async def require_guest(request: Request) -> session.GuestSession:
    guest = read_session(request)
    if guest is None or guest.expired(datetime.now(UTC)):
        raise HTTPException(
            status_code=401,
            detail="Потрібне з'єднання з акаунтом «Сільпо» — підключи його на початку.",
        )
    bind_contextvars(owner=guest.owner[:8], account=guest.account[:8] or "невідомий")
    return guest


Guest = Annotated[session.GuestSession, Depends(require_guest)]


@router.get("/session", response_model=GuestLink)
async def whoami(request: Request, response: Response) -> GuestLink:
    guest = read_session(request)
    if guest is None:
        return GuestLink(connected=False)

    now = datetime.now(UTC)
    if guest.expired(now):
        forget(response, keep_key=True)
        return GuestLink(connected=False, reason="термін дії з'єднання минув")

    renew_failed = False
    if guest.renewable(now):
        renewed = await _renew(guest, now=now)
        if renewed is not None:
            guest = renewed
            _set_cookie(
                response,
                session.COOKIE_NAME,
                session.pack(guest, key=settings.session_key),
                max_age=session.MAX_AGE_DAYS * 24 * 3600,
            )
        else:
            renew_failed = True

    return GuestLink(
        connected=True,
        expires_at=guest.expires_at,
        greet=await _greeting(guest),
        llm_key=read_llm_key(request) is not None,
        reason=(
            "оновити доступ не вдалося: «Сільпо» не відповідає — з'єднання працює до кінця строку"
            if renew_failed
            else None
        ),
    )


async def _greeting(guest: session.GuestSession) -> int | None:
    if not guest.account:
        return None
    try:
        return await newcomers.claim_greeting(get_pool(), account=guest.account)
    except Exception as exc:
        log.info("auth.greeting_skipped", error=str(exc)[:80])
        return None


async def _renew(guest: session.GuestSession, *, now: datetime) -> session.GuestSession | None:
    if not guest.refresh:
        return None
    try:
        async with oauth.http_client() as http:
            endpoints = await oauth.discover(_issuer(), http=http)
            client_id = await _client_id(endpoints, http=http)
            tokens = await oauth.renew(
                endpoints, client_id=client_id, refresh_token=guest.refresh, http=http
            )
    except oauth.AuthError as exc:
        log.warning("auth.renew_skipped", error=str(exc)[:90])
        return None
    return session.from_token_response(tokens, now=now, previous=guest)


@router.get("/start")
async def start(request: Request, return_to: str | None = None) -> Response:
    key = _configured()
    if key is None:
        return _failed("вхід гостя не налаштований")
    try:
        async with oauth.http_client() as http:
            endpoints = await oauth.discover(_issuer(), http=http)
            client_id = await _client_id(endpoints, http=http)
    except oauth.AuthError as exc:
        log.warning("auth.start_unavailable", error=str(exc)[:90])
        return _failed("логін «Сільпо» не відповів")

    handshake = pkce.start()
    pending = flow.start(handshake, return_to=_safe_return(return_to), now=datetime.now(UTC))

    target = oauth.authorize_url(
        endpoints,
        client_id=client_id,
        redirect_uri=_redirect_uri(),
        challenge=handshake.challenge,
        state=handshake.state,
    )
    response = RedirectResponse(target, status_code=307)
    _set_cookie(
        response,
        flow.COOKIE_NAME,
        flow.pack(pending, key=key),
        max_age=int(flow.TTL.total_seconds()),
    )
    return response


@router.get("/callback")
async def callback(request: Request, code: str | None = None, state: str | None = None) -> Response:
    key = _configured()
    if key is None:
        return _failed("вхід гостя не налаштований")
    raw = request.cookies.get(flow.COOKIE_NAME)
    if not raw or not code or not state:
        return _failed("вхід не почався або обірвався")

    try:
        pending = flow.unpack(raw, key=key)
        flow.verify(pending, state=state, now=datetime.now(UTC))
    except (SealError, ValueError) as exc:
        log.warning("auth.callback_rejected", error=str(exc)[:90])
        return _failed(str(exc))

    async with oauth.http_client() as http:
        try:
            endpoints = await oauth.discover(_issuer(), http=http)
            client_id = await _client_id(endpoints, http=http)
        except oauth.AuthError as exc:
            log.warning("auth.discovery_failed", error=str(exc)[:90])
            return _failed("сервер логіну не відповів")
        try:
            tokens = await oauth.exchange(
                endpoints,
                client_id=client_id,
                code=code,
                verifier=pending.verifier,
                redirect_uri=_redirect_uri(),
                http=http,
            )
        except oauth.AuthError as exc:
            log.warning("auth.exchange_failed", error=str(exc)[:90])
            return _failed("обмін коду не вдався")

    guest = session.from_token_response(tokens, now=datetime.now(UTC))
    guest = await _identify(guest)
    response = RedirectResponse(pending.return_to, status_code=303)
    _set_cookie(
        response,
        session.COOKIE_NAME,
        session.pack(guest, key=key),
        max_age=session.MAX_AGE_DAYS * 24 * 3600,
    )
    _drop_cookie(response, flow.COOKIE_NAME)
    log.info("auth.connected")
    return response


@router.post("/logout")
async def logout(request: Request) -> Response:
    guest = read_session(request)
    revoked = False
    try:
        if guest is not None:
            _forget_belongings(guest.owner, account=guest.account)
            revoked = await _revoke(guest)
    except Exception as exc:
        log.warning("auth.logout_incomplete", error=str(exc)[:90])

    response = Response(status_code=204)
    forget(response)
    log.info("auth.logout", revoked=revoked)
    return response


def _forget_belongings(owner: str, *, account: str = "") -> None:
    belongings = (
        ("place", places.forget),
        ("history", history.forget),
        ("runs", runs.forget),
        ("quota", quota.forget),
    )
    for what, forget_one in belongings:
        try:
            forget_one(owner)
        except Exception as exc:
            log.warning("auth.forget_failed", what=what, error=str(exc)[:90])
    if account:
        try:
            forget_loop(account)
        except Exception as exc:
            log.warning("auth.forget_failed", what="pantry_loop", error=str(exc)[:90])


async def _revoke(guest: session.GuestSession) -> bool:
    try:
        async with oauth.http_client() as http:
            endpoints = await oauth.discover(_issuer(), http=http)
            client_id = await _client_id(endpoints, http=http)
            return await oauth.revoke(
                endpoints,
                client_id=client_id,
                token=guest.refresh or guest.access,
                hint="refresh_token" if guest.refresh else "access_token",
                http=http,
            )
    except oauth.AuthError as exc:
        log.warning("auth.revoke_unavailable", error=str(exc)[:90])
        return False


async def _identify(guest: session.GuestSession) -> session.GuestSession:
    try:
        async with SilpoMCP(token=guest.access) as mcp:
            outcome = await mcp.call("silpo_get_my_profile")
        profile = outcome.payload_raw.get("profile")
        profile_id = str(profile.get("id") or "") if isinstance(profile, dict) else ""
    except (MCPCallError, RuntimeError, OSError) as exc:
        log.info("auth.profile_skipped", error=str(exc)[:80])
        return guest
    if not profile_id:
        return guest

    account = newcomers.fingerprint(profile_id)
    known = replace(guest, account=account)
    if account in settings.insider_accounts():
        log.info("auth.insider")
        return known
    try:
        position = await newcomers.arrive(get_pool(), account=account)
    except Exception as exc:
        log.info("auth.newcomer_skipped", error=str(exc)[:80])
        return known
    if position is not None:
        log.info("auth.newcomer", position=position)
    return known


def _issuer() -> str:
    parsed = urlparse(settings.mcp_url)
    return f"{parsed.scheme}://{parsed.netloc}"


async def _client_id(endpoints: oauth.Endpoints, *, http) -> str:
    if settings.oauth_client_id:
        return settings.oauth_client_id
    client_id = await oauth.register_client(
        endpoints, redirect_uri=_redirect_uri(), name="Комора", http=http
    )
    log.warning("auth.client_registered_on_the_fly", client_id=client_id)
    return client_id


def _failed(reason: str) -> RedirectResponse:
    response = RedirectResponse(HOME, status_code=303)
    _drop_cookie(response, flow.COOKIE_NAME)
    log.info("auth.failed", reason=reason[:90])
    return response


__all__ = ["Guest", "forget", "read_session", "require_guest", "router"]


@router.put("/llm-key", response_model=GuestLink)
async def save_llm_key(request: Request, response: Response, body: LlmKeyRequest) -> GuestLink:
    tidy = llm_key.tidy(body.key)
    if not llm_key.looks_like_key(tidy):
        raise HTTPException(
            status_code=400,
            detail="це не схоже на ключ OpenAI — він починається з «sk-»",
        )
    _set_cookie(
        response,
        llm_key.COOKIE_NAME,
        llm_key.pack(tidy, key=settings.session_key),
        max_age=llm_key.MAX_AGE_DAYS * 24 * 3600,
    )
    return (await whoami(request, response)).model_copy(update={"llm_key": True})


@router.delete("/llm-key", response_model=GuestLink)
async def drop_llm_key(request: Request, response: Response) -> GuestLink:
    _drop_cookie(response, llm_key.COOKIE_NAME)
    return (await whoami(request, response)).model_copy(update={"llm_key": False})
