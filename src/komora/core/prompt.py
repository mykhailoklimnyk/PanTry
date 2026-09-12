from __future__ import annotations

from typing import Any


def is_empty(value: Any) -> bool:
    return value is None or (isinstance(value, str | list | dict | tuple) and not value)


def prune(value: Any) -> Any:
    if isinstance(value, dict):
        pruned = {key: prune(item) for key, item in value.items()}
        return {key: item for key, item in pruned.items() if not is_empty(item)}
    if isinstance(value, list):
        return [prune(item) for item in value]
    return value


FOREIGN_LIMIT = 120

_CONTROL = {chr(c) for c in range(0x20)} | {chr(0x7F)}


def tame(text: str, *, limit: int = FOREIGN_LIMIT) -> tuple[str, bool]:
    tamed = "".join(" " if ch in _CONTROL else ch for ch in text)
    tamed = " ".join(tamed.split())
    if len(tamed) > limit:
        tamed = tamed[:limit].rstrip()
    return tamed, tamed != text


__all__ = ["FOREIGN_LIMIT", "is_empty", "prune", "tame"]
