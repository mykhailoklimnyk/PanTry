from __future__ import annotations

import hashlib

PREFIX = "manual"


def manual_id(kind: str) -> str:
    digest = hashlib.sha256(kind.strip().casefold().encode("utf-8")).hexdigest()
    return f"{PREFIX}:{digest[:16]}"


def regrouped(said: str, label: str) -> bool:
    return _plain(said) != _plain(label)


def _plain(text: str) -> str:
    return " ".join(text.casefold().split())


def is_manual(row_id: str) -> bool:
    return row_id.startswith(f"{PREFIX}:")


__all__ = ["PREFIX", "is_manual", "manual_id", "regrouped"]
