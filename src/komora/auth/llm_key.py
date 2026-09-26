from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode

from komora.auth.crypto import SealError, seal, unseal

COOKIE_NAME = "__Host-komora-llm"

MAX_AGE_DAYS = 30

MAX_LEN = 512


def pack(api_key: str, *, key: str) -> str:
    return urlsafe_b64encode(seal(api_key, key=key)).decode("ascii").rstrip("=")


def unpack(cookie: str, *, key: str) -> str:
    try:
        sealed = urlsafe_b64decode(cookie + "=" * (-len(cookie) % 4))
    except (ValueError, TypeError) as exc:
        raise SealError("cookie ключа не base64url") from exc
    return unseal(sealed, key=key)


def tidy(api_key: str) -> str:
    return "".join(api_key.split())


def looks_like_key(api_key: str) -> bool:
    return bool(api_key) and len(api_key) <= MAX_LEN and api_key.startswith("sk-")


__all__ = [
    "COOKIE_NAME",
    "MAX_AGE_DAYS",
    "MAX_LEN",
    "looks_like_key",
    "pack",
    "tidy",
    "unpack",
]
