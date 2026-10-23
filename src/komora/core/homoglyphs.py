from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

ALLOWED_PUNCT = {
    "—": "тире — основний роздільник у нашому тексті",
    "–": "коротке тире в діапазонах: «11:00–13:00»",
    "«": "українські лапки",
    "»": "українські лапки",
    "·": "розділювач у рядках інтерфейсу: «2 шт · 120 ₴»",
    "₴": "гривня",
    "→": "стрілка в схемах конвеєра і в документації",
    "←": "стрілка назад у схемах",
    "↗": "посилання, яке веде НАЗОВНІ: гість має бачити це до кліку",
    "↑": "порядок ланки в ланцюжку замін: підняти",
    "↓": "порядок ланки в ланцюжку замін: опустити",
    "№": "номер ланки ланцюжка замін",
    "±": "похибка циклу",
    "×": "множення в розборі пакування і в лічильниках",
    "≥": "поріг",
    "≤": "поріг",
    "≠": "нерівність у тестах",
    "…": "трикрапка",
    "°": "градус",
    "§": "посилання на пункт умов хакатону",
    "✓": "стан «доставлено» у звірці",
    "✕": "кнопка «прибрати» в рядку кошика",
    "›": "шеврон у рядку-переході",
    "‹": "шеврон назад",
    "◆": "маркер у списку правил",
    "═": "рамка у виводі CLI",
    "⚠": "попередження у виводі генератора",
    "▾": "стрілка селектора моделі в шапці",
    "∅": "порожній стан кошика і рядок, який не доїхав до замовлення",
    "⇒": "стрілка в коментарях до токенів теми",
    "↔": "двобічний зв'язок у схемах",
    "½": "половина в описі налаштування",
    "¼": "чверть у нумерації розділів setup.md — крон, вставлений між двома",
    "⏭": "маркер «не потрібне» в реєстрі інструментів MCP",
    "✅": "маркер «вживається» в реєстрі інструментів MCP",
    "✎": "маркер «пише» в реєстрі інструментів MCP",
    "🔒": "маркер «чутливе» в реєстрі інструментів MCP",
    "🔹": "маркер рядка в реєстрі інструментів MCP",
    " ": "нерозривний пробіл — тримає число з одиницею в одному рядку",
    "️": "селектор емодзі",
}

TO_CYRILLIC = {
    "A": "А",
    "B": "В",
    "C": "С",
    "E": "Е",
    "H": "Н",
    "I": "І",
    "K": "К",
    "M": "М",
    "O": "О",
    "P": "Р",
    "T": "Т",
    "X": "Х",
    "Y": "У",
    "a": "а",
    "c": "с",
    "e": "е",
    "i": "і",
    "k": "к",
    "o": "о",
    "p": "р",
    "x": "х",
    "y": "у",
}
TO_LATIN = {cyr: lat for lat, cyr in TO_CYRILLIC.items()}

DIACRITICS = {
    "í": ("і", "i"),
    "ì": ("і", "i"),
    "î": ("і", "i"),
    "ï": ("ї", "i"),
    "é": ("е", "e"),
    "è": ("е", "e"),
    "ê": ("е", "e"),
    "ë": ("е", "e"),
    "á": ("а", "a"),
    "à": ("а", "a"),
    "â": ("а", "a"),
    "ä": ("а", "a"),
    "ó": ("о", "o"),
    "ò": ("о", "o"),
    "ô": ("о", "o"),
    "ö": ("о", "o"),
    "ú": ("у", "u"),
    "ù": ("у", "u"),
    "û": ("у", "u"),
    "ü": ("у", "u"),
    "ý": ("у", "y"),
    "ÿ": ("у", "y"),
    "ç": ("с", "c"),
    "ñ": ("н", "n"),
}

APOSTROPHES = {"’": "'", "ʼ": "'", "‘": "'", "´": "'"}

DIRECT = {
    "“": '"',
    "”": '"',
    "−": "-",
    "‐": "-",
    "‑": "-",
    "​": "",
    "‌": "",
    "‍": "",
    "﻿": "",
    "­": "",
    " ": " ",
}

CYRILLIC = re.compile(r"[Ѐ-ӿ]")
LATIN = re.compile(r"[A-Za-z]")
WORD = re.compile(r"[^\W\d_]+", re.UNICODE)

ESCAPE = re.compile(r"\\[nrtvfab0\\'\"]|\\u[0-9a-fA-F]{4}|\\x[0-9a-fA-F]{2}")


def is_allowed(ch: str) -> bool:
    if ch in "\n\r\t" or " " <= ch <= "~":
        return True
    if ch in ALLOWED_PUNCT or CYRILLIC.fullmatch(ch):
        return True
    return unicodedata.category(ch) == "So" and ord(ch) >= 0x2600


def script_of(context: str) -> str:
    cyr = len(CYRILLIC.findall(context))
    lat = len(LATIN.findall(context))
    return "cyr" if cyr >= lat else "lat"


def fix_word(word: str, script: str) -> str:
    out = []
    for ch in word:
        if ch in DIACRITICS:
            out.append(DIACRITICS[ch][0 if script == "cyr" else 1])
        elif script == "cyr" and ch in TO_CYRILLIC:
            out.append(TO_CYRILLIC[ch])
        elif script == "lat" and ch in TO_LATIN:
            out.append(TO_LATIN[ch])
        else:
            out.append(ch)
    return "".join(out)


def is_mixed(word: str) -> bool:
    return bool(CYRILLIC.search(word) and LATIN.search(word))


def is_odd(word: str) -> bool:
    return is_mixed(word) or any(ch in DIACRITICS for ch in word)


def mixed_words(text: str) -> list[tuple[str, str, bool]]:
    found: dict[str, tuple[str, bool]] = {}
    for line in text.splitlines():
        clean_line = ESCAPE.sub(" ", line)
        script = script_of(clean_line)
        for word in WORD.findall(clean_line):
            if not is_mixed(word):
                continue
            fixed = fix_word(word, script)
            found[word] = (fixed, not is_mixed(fixed))
    return sorted((word, *rest) for word, rest in found.items())


def stray_chars(text: str) -> list[str]:
    return sorted({ch for ch in text if not is_allowed(ch)})


@dataclass(frozen=True, slots=True)
class Folded:

    text: str
    fixed: tuple[tuple[str, str], ...] = ()
    odd: tuple[str, ...] = ()

    @property
    def changed(self) -> bool:
        return bool(self.fixed)


def fold(text: str) -> Folded:
    if not text:
        return Folded(text)
    swapped = "".join(DIRECT.get(ch, ch) for ch in text)
    for odd, plain in APOSTROPHES.items():
        swapped = swapped.replace(odd, plain)
    fixed: list[tuple[str, str]] = []
    odd_words: list[str] = []
    script = script_of(swapped)

    def heal(match: re.Match[str]) -> str:
        word = match.group(0)
        if not is_odd(word):
            return word
        healed = fix_word(word, script)
        if is_odd(healed):
            odd_words.append(word)
            return word
        fixed.append((word, healed))
        return healed

    out = WORD.sub(heal, swapped)
    if swapped != text:
        fixed.append((text, swapped))
    return Folded(out, tuple(fixed), tuple(dict.fromkeys(odd_words)))


def fold_names(text: str) -> Folded:
    if not text:
        return Folded(text)
    swapped = "".join(DIRECT.get(ch, ch) for ch in text)
    for odd, plain in APOSTROPHES.items():
        swapped = swapped.replace(odd, plain)
    fixed: list[tuple[str, str]] = []
    odd_words: list[str] = []

    def heal(match: re.Match[str]) -> str:
        word = match.group(0)
        if not is_odd(word):
            return word
        healed = [fix_word(word, script) for script in ("cyr", "lat")]
        cured = [candidate for candidate in healed if not is_odd(candidate)]
        if len(cured) != 1:
            odd_words.append(word)
            return word
        fixed.append((word, cured[0]))
        return cured[0]

    out = WORD.sub(heal, swapped)
    if swapped != text:
        fixed.append((text, swapped))
    return Folded(out, tuple(fixed), tuple(dict.fromkeys(odd_words)))


def bare(word: str) -> str:
    for odd in APOSTROPHES:
        word = word.replace(odd, "'")
    return word.replace("'", "")


__all__ = [
    "ALLOWED_PUNCT",
    "APOSTROPHES",
    "CYRILLIC",
    "DIACRITICS",
    "DIRECT",
    "ESCAPE",
    "LATIN",
    "TO_CYRILLIC",
    "TO_LATIN",
    "WORD",
    "Folded",
    "bare",
    "fix_word",
    "fold",
    "fold_names",
    "is_allowed",
    "is_mixed",
    "is_odd",
    "mixed_words",
    "script_of",
    "stray_chars",
]
