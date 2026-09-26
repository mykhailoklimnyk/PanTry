from __future__ import annotations

import hashlib
import json
import secrets
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from komora.auth.crypto import SealError, seal, unseal

COOKIE_NAME = "__Host-komora"

MAX_AGE_DAYS = 30


@dataclass(frozen=True, slots=True)
class GuestSession:

    access: str
    refresh: str | None = None
    owner: str = ""
    account: str = ""
    expires_at: datetime | None = None
    issued_at: datetime | None = None
    branch_id: str | None = None

    def __post_init__(self) -> None:
        if not self.owner:
            derived = hashlib.sha256(self.access.encode("utf-8")).hexdigest()[:22]
            object.__setattr__(self, "owner", derived)

    def expired(self, now: datetime) -> bool:
        return self.expires_at is not None and now >= self.expires_at

    def stale(self, now: datetime) -> bool:
        if self.expires_at is None or self.issued_at is None:
            return False
        return now >= self.issued_at + (self.expires_at - self.issued_at) / 2

    def renewable(self, now: datetime) -> bool:
        return bool(self.refresh) and self.stale(now) and not self.expired(now)


def pack(session: GuestSession, *, key: str) -> str:
    payload = {
        "a": session.access,
        "r": session.refresh,
        "o": session.owner,
        "n": session.account,
        "e": session.expires_at.isoformat() if session.expires_at else None,
        "i": session.issued_at.isoformat() if session.issued_at else None,
        "b": session.branch_id,
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return urlsafe_b64encode(seal(raw, key=key)).decode("ascii").rstrip("=")


def unpack(cookie: str, *, key: str) -> GuestSession:
    try:
        sealed = urlsafe_b64decode(cookie + "=" * (-len(cookie) % 4))
    except (ValueError, TypeError) as exc:
        raise SealError("cookie не base64url") from exc

    payload = json.loads(unseal(sealed, key=key))
    if not isinstance(payload, dict) or not payload.get("a"):
        raise SealError("у cookie немає токена")

    def moment(field: str) -> datetime | None:
        raw = payload.get(field)
        return datetime.fromisoformat(raw) if raw else None

    return GuestSession(
        access=str(payload["a"]),
        refresh=payload.get("r"),
        owner=str(payload.get("o") or ""),
        account=str(payload.get("n") or ""),
        expires_at=moment("e"),
        issued_at=moment("i"),
        branch_id=payload.get("b"),
    )


def expires_from(seconds: int | None, *, now: datetime) -> datetime | None:
    if not seconds:
        return None
    return now.astimezone(UTC) + timedelta(seconds=int(seconds))


def from_token_response(
    payload: dict[str, object],
    *,
    now: datetime,
    previous: GuestSession | None = None,
) -> GuestSession:
    access = str(payload.get("access_token") or "")
    if not access:
        raise SealError("у відповіді /token немає access_token")

    seconds = payload.get("expires_in")
    return GuestSession(
        access=access,
        refresh=str(payload.get("refresh_token") or "") or (previous.refresh if previous else None),
        owner=previous.owner if previous else secrets.token_urlsafe(16),
        account=previous.account if previous else "",
        expires_at=expires_from(int(seconds) if isinstance(seconds, int | str) else None, now=now),
        issued_at=now,
        branch_id=previous.branch_id if previous else None,
    )


__all__ = [
    "COOKIE_NAME",
    "MAX_AGE_DAYS",
    "GuestSession",
    "expires_from",
    "from_token_response",
    "pack",
    "unpack",
]
