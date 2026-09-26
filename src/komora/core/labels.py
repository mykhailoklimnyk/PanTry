from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence

NO_LETTERS = "хх"


def label(name: str, ordinal: int) -> str:
    letters = "".join(c for c in name.casefold() if c.isalpha())[:2] or NO_LETTERS
    return f"{letters}{ordinal:02d}"


def labels(names: Sequence[str]) -> dict[str, str]:
    made: dict[str, str] = {}
    for name in names:
        if name not in made:
            made[name] = label(name, len(made) + 1)
    return made


def resolve(answered: str, of: Mapping[str, str]) -> str | None:
    if answered in of:
        return of[answered]
    return answered if answered in of.values() else None


_NOT_A_LETTER = re.compile(r"[^\w]", flags=re.UNICODE)


def skeleton(text: str) -> str:
    return _NOT_A_LETTER.sub("", text).casefold()


def by_skeleton(labels: Iterable[str]) -> dict[str, str]:
    seen: dict[str, str] = {}
    tied: set[str] = set()
    for one in labels:
        key = skeleton(one)
        if not key:
            continue
        if key in seen and seen[key] != one:
            tied.add(key)
        seen.setdefault(key, one)
    return {key: value for key, value in seen.items() if key not in tied}


def echoed(answered: str, of: Mapping[str, str]) -> str | None:
    return of.get(skeleton(answered))


__all__ = ["NO_LETTERS", "by_skeleton", "echoed", "label", "labels", "resolve", "skeleton"]
