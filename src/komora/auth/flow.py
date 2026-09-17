from __future__ import annotations

import json
from base64 import urlsafe_b64decode, urlsafe_b64encode
from dataclasses import dataclass
from datetime import datetime, timedelta

from komora.auth.crypto import SealError, seal, unseal
from komora.auth.pkce import Handshake, same_secret

COOKIE_NAME = "__Host-komora-flow"

TTL = timedelta(minutes=10)


@dataclass(frozen=True, slots=True)
class Flow:

    state: str
    verifier: str
    return_to: str
    expires_at: datetime

    def expired(self, now: datetime) -> bool:
        return now >= self.expires_at


def start(handshake: Handshake, *, return_to: str, now: datetime) -> Flow:
    return Flow(
        state=handshake.state,
        verifier=handshake.verifier,
        return_to=return_to,
        expires_at=now + TTL,
    )


def pack(flow: Flow, *, key: str) -> str:
    payload = {
        "s": flow.state,
        "v": flow.verifier,
        "r": flow.return_to,
        "e": flow.expires_at.isoformat(),
    }
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return urlsafe_b64encode(seal(raw, key=key)).decode("ascii").rstrip("=")


def unpack(cookie: str, *, key: str) -> Flow:
    try:
        sealed = urlsafe_b64decode(cookie + "=" * (-len(cookie) % 4))
    except (ValueError, TypeError) as exc:
        raise SealError("cookie потоку не base64url") from exc

    payload = json.loads(unseal(sealed, key=key))
    if not isinstance(payload, dict) or not payload.get("s") or not payload.get("v"):
        raise SealError("cookie потоку неповна")
    return Flow(
        state=str(payload["s"]),
        verifier=str(payload["v"]),
        return_to=str(payload.get("r") or "/"),
        expires_at=datetime.fromisoformat(str(payload["e"])),
    )


def verify(flow: Flow, *, state: str, now: datetime) -> None:
    if flow.expired(now):
        raise SealError("час на вхід минув — почни спочатку")
    if not same_secret(flow.state, state):
        raise SealError("відповідь не на наш запит входу")


__all__ = ["COOKIE_NAME", "TTL", "Flow", "pack", "start", "unpack", "verify"]
