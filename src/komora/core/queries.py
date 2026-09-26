from __future__ import annotations

import re
from collections.abc import Sequence

NOISE = re.compile(r"[0-9%]|[a-zA-Z]")

MIN_WORD = 3


def words(name: str) -> list[str]:
    return [word for word in re.split(r"[\s,./]+", name.strip()) if word]


def head(name: str, count: int) -> str:
    return " ".join(words(name)[:count])


def kind_words(name: str) -> str:
    plain = [w for w in words(name) if not NOISE.search(w) and len(w) >= MIN_WORD]
    return " ".join(plain[:2])


def narrow(name: str) -> tuple[str, ...]:
    full = " ".join(words(name))
    steps: list[str] = []
    for step in (kind_words(name), head(name, 2), head(name, 1)):
        if step and step != full and step not in steps:
            steps.append(step)
    return tuple(steps)


BOUND = frozenset({"з", "із", "зі", "без", "для", "на"})

BOUND_PHRASES = frozenset({("на", "основі")})


def bound_at(parts: Sequence[str], i: int) -> int:
    if i >= len(parts):
        return 0
    if i + 1 < len(parts) and (parts[i], parts[i + 1]) in BOUND_PHRASES:
        return 2
    return 1 if parts[i] in BOUND else 0


def one_product(name: str) -> bool:
    return any(word in BOUND for word in name.casefold().split())


def norm_query(text: str) -> str:
    return " ".join(text.split()).casefold()


def covers(whole: str, part: str) -> bool:
    mine = words(part)
    if not mine:
        return False
    theirs = words(whole)
    return any(theirs[i : i + len(mine)] == mine for i in range(len(theirs) - len(mine) + 1))


def dedupe(intents: list[str]) -> list[str]:
    seen: dict[str, str] = {}
    for intent in intents:
        key = norm_query(intent)
        if key and key not in seen:
            seen[key] = intent
    return list(seen.values())


__all__ = [
    "BOUND",
    "MIN_WORD",
    "NOISE",
    "covers",
    "dedupe",
    "head",
    "kind_words",
    "narrow",
    "norm_query",
    "one_product",
    "words",
]
