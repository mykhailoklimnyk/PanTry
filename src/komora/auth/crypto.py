from __future__ import annotations

import os
from base64 import urlsafe_b64decode, urlsafe_b64encode

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

KEY_BYTES = 32
NONCE_BYTES = 12


class SealError(RuntimeError):
    """Ключ непридатний або шифротекст не той, яким його записали."""


def generate_key() -> str:
    return urlsafe_b64encode(os.urandom(KEY_BYTES)).decode("ascii")


def _cipher(key: str) -> AESGCM:
    try:
        raw = urlsafe_b64decode(key + "=" * (-len(key) % 4))
    except (ValueError, TypeError) as exc:
        raise SealError("KOMORA_SESSION_KEY не base64url") from exc
    if len(raw) != KEY_BYTES:
        raise SealError(f"KOMORA_SESSION_KEY має бути {KEY_BYTES} байтів, а не {len(raw)}")
    return AESGCM(raw)


def seal(plaintext: str, *, key: str) -> bytes:
    nonce = os.urandom(NONCE_BYTES)
    return nonce + _cipher(key).encrypt(nonce, plaintext.encode("utf-8"), None)


def unseal(sealed: bytes, *, key: str) -> str:
    if len(sealed) <= NONCE_BYTES:
        raise SealError("шифротекст коротший за nonce — запис пошкоджений")
    nonce, payload = sealed[:NONCE_BYTES], sealed[NONCE_BYTES:]
    try:
        return _cipher(key).decrypt(nonce, payload, None).decode("utf-8")
    except InvalidTag as exc:
        raise SealError(
            "токен не розшифровується: змінився KOMORA_SESSION_KEY або запис підмінено"
        ) from exc


__all__ = ["KEY_BYTES", "NONCE_BYTES", "SealError", "generate_key", "seal", "unseal"]
