from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from komora.core import brands
from komora.core.homoglyphs import APOSTROPHES
from komora.core.words import plural

PROMO = "акція"
PACK = "фасовка"
CONTAINER = "тара"
EVENT = "подія"
KIDS = "дитяче"
LIMITS = "обмеження"
BRAND = "бренд"
THRIFT = "економія"

ORDER: tuple[str, ...] = (PROMO, PACK, CONTAINER, EVENT, KIDS, LIMITS, BRAND, THRIFT)

PANTRY_IDLE = "комора без роботи"

PANTRY_NEW = "комора порожня"

PANTRY_ORDER: tuple[str, ...] = (PANTRY_NEW, PANTRY_IDLE)

FILES: Mapping[str, str] = {
    PANTRY_NEW: "pantry_new",
    PANTRY_IDLE: "pantry_idle",
    PROMO: "promo",
    PACK: "pack",
    CONTAINER: "container",
    EVENT: "event",
    KIDS: "kids",
    LIMITS: "limits",
    BRAND: "brand",
    THRIFT: "thrift",
}

EVENT_MODES = frozenset({"event"})

_APOSTROPHES = str.maketrans(dict(APOSTROPHES))
_SPACES = re.compile(r"\s+")
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)

_PACK_RE = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:кг|мл|мг|гр|г|л)\b|упаковк|пачк|фасовк|маленьк|велик(?:а|у|ий|і|ої|ою|е)?\b|літр"
)

_CONTAINER_RE = re.compile(
    r"\bскл[оаеяі]|\bпет(?![а-яіїєґ])|пластик|бляшан|з/б|жерстян|тетра[- ]?пак|дой[- ]?пак|алюмін"
)

_KIDS_RE = re.compile(r"дитин|дитяч|дітк|малюк|немовл")

_LIMITS_RE = re.compile(r"\bбез\b|не містить|безлактоз|безглютен|веган|вегетаріан|пісн")

_THRIFT_RE = re.compile(r"дешевш|найдешев|економ|бюджетн|вигідн")


@dataclass(frozen=True, slots=True)
class Skill:

    name: str
    why: str


def _said(skill: Skill, fields: Mapping[str, Sequence[str]] | None) -> str:
    said = f"{skill.name} ({skill.why})"
    if fields is None:
        return said
    named = list(fields.get(skill.name) or ())
    if not named:
        return f"{said} -- поля не названі"
    if len(named) == 1:
        return f"{said} -- судить лише полем {named[0]}"
    return f"{said} -- судить полями " + ", ".join(named)


@dataclass(frozen=True, slots=True)
class Selection:

    skills: tuple[Skill, ...] = ()
    unmatched: tuple[str, ...] = ()

    def phrase(self, fields: Mapping[str, Sequence[str]] | None = None) -> str:
        head = (
            "підключено: " + "; ".join(_said(s, fields) for s in self.skills)
            if self.skills
            else "жодного: тригерів не було"
        )
        if not self.unmatched:
            return head
        return (
            head
            + "; без скіла: "
            + ", ".join(f"правило «{rule}»" for rule in self.unmatched)
            + " -- судити нема чим"
        )

    def note(self) -> str:
        if not self.skills:
            head = "жодного скіла: тригерів не було"
        else:
            head = f"підключено {len(self.skills)}: " + ", ".join(s.name for s in self.skills)
        if not self.unmatched:
            return head
        return (
            head
            + f"; без скіла {len(self.unmatched)} "
            + plural(len(self.unmatched), "правило", "правила", "правил")
        )


def norm(text: str) -> str:
    return _SPACES.sub(" ", text.translate(_APOSTROPHES).casefold()).strip()


_KIND_STEM = 5


def _same_kind(word: str, head: str) -> bool:
    if brands.same_word(word, head):
        return True
    mine, other = word.casefold(), head.casefold()
    if mine == other:
        return True
    return (
        len(mine) >= _KIND_STEM
        and len(other) >= _KIND_STEM
        and mine[:_KIND_STEM] == other[:_KIND_STEM]
    )


def narrowing(phrase: str, names: Sequence[str]) -> str:
    heads = [head for name in names if (head := brands.head_word(name))]
    words = _WORD.findall(phrase)
    if any(_same_kind(word, head) for word in words for head in heads):
        return ""
    for word in words:
        if any(brands.carried_by(word, name) for name in names):
            return word
    return ""


def pantry_skills(state: Mapping[str, int]) -> Selection:
    empty = all(
        state.get(name, 0) == 0 for name in ("рядків", "дописано руками", "чеків прочитано")
    )
    if empty:
        return Selection(skills=(Skill(name=PANTRY_NEW, why="ні рядків, ні дописаного, ні чеків"),))
    labelled = state.get("міток виду", 0)
    idle = [
        name
        for name in ("без мітки виду", "без вироку про ритм", "без стелі зберігання")
        if state.get(name, 0) == 0
    ]
    if not labelled or not idle:
        return Selection()
    return Selection(skills=(Skill(name=PANTRY_IDLE, why="нуль у: " + ", ".join(idle)),))


def select(
    rules: Sequence[str] = (),
    *,
    occasion_mode: str = "",
    occasion_phrase: str = "",
    intents: Sequence[str] = (),
    promo_kinds: int = 0,
    promo_on_shelf: bool = False,
    shelf: Mapping[str, Sequence[str]] | None = None,
) -> Selection:
    found: dict[str, str] = {}
    fired: set[str] = set()

    def by_rule(name: str, pattern: re.Pattern[str]) -> None:
        for rule in rules:
            if pattern.search(norm(rule)):
                fired.add(rule)
                found.setdefault(name, f"правило «{rule}»")

    def by_intent(name: str, pattern: re.Pattern[str]) -> None:
        for intent in intents:
            if pattern.search(norm(intent)):
                found.setdefault(name, f"намір «{intent}»")

    if promo_kinds > 0:
        found[PROMO] = (
            f"акційна звичка: {promo_kinds} {plural(promo_kinds, 'вид', 'види', 'видів')}"
        )
    elif promo_on_shelf:
        found[PROMO] = "твій артикул на полиці зі старою ціною"

    by_rule(PACK, _PACK_RE)
    by_intent(PACK, _PACK_RE)
    by_rule(CONTAINER, _CONTAINER_RE)
    by_rule(KIDS, _KIDS_RE)
    by_intent(KIDS, _KIDS_RE)
    by_rule(LIMITS, _LIMITS_RE)
    by_rule(THRIFT, _THRIFT_RE)

    if occasion_mode in EVENT_MODES:
        found[EVENT] = f"привід «{occasion_phrase or occasion_mode}»"

    for intent in intents:
        names = list((shelf or {}).get(intent) or ())
        if names and (word := narrowing(intent, names)):
            found.setdefault(BRAND, f"намір «{intent}» звужує вид словом «{word}»")

    return Selection(
        skills=tuple(Skill(name, found[name]) for name in ORDER if name in found),
        unmatched=tuple(rule for rule in rules if rule not in fired),
    )


__all__ = [
    "BRAND",
    "CONTAINER",
    "EVENT",
    "EVENT_MODES",
    "FILES",
    "KIDS",
    "LIMITS",
    "ORDER",
    "PACK",
    "PANTRY_IDLE",
    "PANTRY_NEW",
    "PANTRY_ORDER",
    "PROMO",
    "THRIFT",
    "Selection",
    "Skill",
    "narrowing",
    "norm",
    "pantry_skills",
    "select",
]
