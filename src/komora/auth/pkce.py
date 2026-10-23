from __future__ import annotations

import hashlib
import hmac
import secrets
from base64 import urlsafe_b64encode
from dataclasses import dataclass

ENTROPY_BYTES = 32


def _b64(raw: bytes) -> str:
    return urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def random_token() -> str:
    return _b64(secrets.token_bytes(ENTROPY_BYTES))


def challenge_for(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return _b64(digest)


def fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def same_secret(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


@dataclass(frozen=True, slots=True)
class Handshake:

    state: str
    verifier: str

    @property
    def challenge(self) -> str:
        return challenge_for(self.verifier)


def start() -> Handshake:
    return Handshake(state=random_token(), verifier=random_token())


__all__ = [
    "ENTROPY_BYTES",
    "Handshake",
    "challenge_for",
    "fingerprint",
    "random_token",
    "same_secret",
    "start",
]
