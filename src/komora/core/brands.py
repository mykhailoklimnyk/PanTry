from __future__ import annotations

import re
from decimal import Decimal
from itertools import pairwise

MIN_SKELETON = 3

_TRANSLIT = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "h",
    "ґ": "g",
    "д": "d",
    "е": "e",
    "є": "e",
    "ж": "zh",
    "з": "z",
    "и": "i",
    "і": "i",
    "ї": "i",
    "й": "i",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "h",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "щ": "sh",
    "ь": "",
    "ю": "u",
    "я": "a",
    "ы": "i",
    "э": "e",
    "ё": "e",
    "ъ": "",
}

_SAME_SOUND = {"c": "k", "q": "k", "w": "v", "x": "ks"}

_VOWELS = frozenset("aeiouy")

_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)

_DIGITS = re.compile(r"\d+(?:[.,]\d+)?")


def skeleton(word: str) -> str:
    latin = "".join(_TRANSLIT.get(char, char) for char in word.casefold())
    sounded = "".join(_SAME_SOUND.get(char, char) for char in latin)
    letters: list[str] = []
    for char in sounded:
        if not char.isalpha():
            continue
        if letters and letters[-1] == char:
            continue
        letters.append(char)
    body = "".join(char for char in letters if char not in _VOWELS)
    return body if len(body) >= MIN_SKELETON else ""


def same_word(word: str, other: str) -> bool:
    mine = skeleton(word)
    return bool(mine) and mine == skeleton(other)


def _numbers(text: str) -> set[Decimal]:
    return {Decimal(token.replace(",", ".")) for token in _DIGITS.findall(text)}


def carried_by(word: str, name: str) -> bool:
    target = skeleton(word)
    if not target:
        return False
    if not _numbers(word).issubset(_numbers(name)):
        return False
    tokens = words(name)
    if any(skeleton(token) == target for token in tokens):
        return True
    return any(skeleton(first + second) == target for first, second in pairwise(tokens))


def words(name: str) -> tuple[str, ...]:
    return tuple(_WORD.findall(name))


def head_word(name: str) -> str:
    tokens = words(name)
    return tokens[0] if tokens else ""
