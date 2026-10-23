from __future__ import annotations

from hashlib import blake2s
from typing import Any

SENSITIVE_KEYS = frozenset(
    {
        "address",
        "addresses",
        "latitude",
        "longitude",
        "phone",
        "email",
        "firstname",
        "lastname",
        "middlename",
        "birthday",
        "birthdate",
        "cardnumber",
        "loyaltycardnumber",
        "flat",
        "floor",
        "entrance",
        "house",
        "building",
        "apartment",
        "housenumber",
        "street",
        "locality",
        "courriercomment",
        "postcode",
        "token",
        "accesstoken",
        "authorization",
        "restrictions",
    }
)

QUASI_IDENTIFIER_KEYS = frozenset({"branchid", "filid", "companyid", "polygonid"})

PLACEHOLDER = "[redacted]"
HASH_PREFIX = "id:"


def _mask_identifier(value: Any) -> str:
    text = str(value)
    if text.startswith(HASH_PREFIX):
        return text
    digest = blake2s(text.encode("utf-8"), digest_size=4).digest()
    return f"{HASH_PREFIX}{int.from_bytes(digest, 'big') % 10**8:08d}"


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in SENSITIVE_KEYS:
                cleaned[key] = PLACEHOLDER
            elif lowered in QUASI_IDENTIFIER_KEYS:
                cleaned[key] = _mask_identifier(item)
            else:
                cleaned[key] = redact(item)
        return cleaned

    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]

    return value
