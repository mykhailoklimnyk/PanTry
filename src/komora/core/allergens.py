from __future__ import annotations

import re
from collections.abc import Iterable
from enum import StrEnum


class Allergen(StrEnum):
    GLUTEN = "глютен"
    MILK = "молоко"
    EGGS = "яйця"
    SOY = "соя"
    NUTS = "горіхи"
    PEANUTS = "арахіс"
    FISH = "риба"
    CRUSTACEANS = "ракоподібні"
    MOLLUSCS = "молюски"
    SESAME = "кунжут"
    MUSTARD = "гірчиця"
    CELERY = "селера"
    LUPIN = "люпин"
    SULPHITES = "сульфіти"


_STEMS: tuple[tuple[str, Allergen], ...] = (
    ("глютен", Allergen.GLUTEN),
    ("клейковин", Allergen.GLUTEN),
    ("пшениц", Allergen.GLUTEN),
    ("молок", Allergen.MILK),
    ("лактоз", Allergen.MILK),
    ("яйц", Allergen.EGGS),
    ("яєч", Allergen.EGGS),
    ("со", Allergen.SOY),
    ("горіх", Allergen.NUTS),
    ("арахіс", Allergen.PEANUTS),
    ("риб", Allergen.FISH),
    ("ракоподібн", Allergen.CRUSTACEANS),
    ("молюск", Allergen.MOLLUSCS),
    ("кунжут", Allergen.SESAME),
    ("сезам", Allergen.SESAME),
    ("гірчиц", Allergen.MUSTARD),
    ("селер", Allergen.CELERY),
    ("люпин", Allergen.LUPIN),
    ("сульфіт", Allergen.SULPHITES),
    ("діоксид сірки", Allergen.SULPHITES),
)

_SOY_WORDS = frozenset({"соя", "сою", "сої", "соєю", "соєві", "соєвий", "соєве"})

_SPLIT = re.compile(r"[,;/·]|\sта\s|\sі\s")


def parse(field: str | None) -> frozenset[Allergen]:
    if not field:
        return frozenset()

    found: set[Allergen] = set()
    for chunk in _SPLIT.split(field.lower()):
        phrase = chunk.strip(" .()-—«»\"'")
        if not phrase:
            continue

        if any(word.strip(" .()-—«»\"'") in _SOY_WORDS for word in phrase.split()):
            found.add(Allergen.SOY)

        for stem, allergen in _STEMS:
            if stem == "со":
                continue
            if stem in phrase:
                found.add(allergen)
                break

    return frozenset(found)


def conflicts(
    product_allergens: Iterable[Allergen], excluded: Iterable[Allergen]
) -> frozenset[Allergen]:
    return frozenset(product_allergens) & frozenset(excluded)


def is_safe(product_allergens: Iterable[Allergen], excluded: Iterable[Allergen]) -> bool:
    return not conflicts(product_allergens, excluded)


def explain(found: Iterable[Allergen]) -> str:
    names = sorted(a.value for a in found)
    if not names:
        return "без заявлених алергенів"
    return "містить: " + ", ".join(names)
