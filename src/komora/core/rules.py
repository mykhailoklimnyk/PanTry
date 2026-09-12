from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

MAX_LABEL = 120

NO_RESTRICTION = "all-food"

PROFILE_LABELS = {
    "gluten-free": "без глютену",
    "lactose-free": "без лактози",
    "vegan": "веганське",
    "vegetarian": "вегетаріанське",
    "sugar-free": "без цукру",
}

_SPACES = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class Rule:

    id: str
    label: str
    permanent: bool
    active: bool


def clean(label: str) -> str:
    return _SPACES.sub(" ", label.strip())


def key(label: str) -> str:
    return clean(label).casefold()


def rule_id(label: str) -> str:
    digest = hashlib.sha256(key(label).encode("utf-8")).hexdigest()
    return f"rule:{digest[:16]}"


def profile_rule(slug: object, name: object) -> Rule | None:
    code = clean(str(slug or ""))
    if not code or code == NO_RESTRICTION:
        return None
    label = clean(str(name or "")) or PROFILE_LABELS.get(code.casefold()) or code
    return Rule(id=f"profile:{code}", label=label, permanent=True, active=True)


def profile_rules(restrictions: Iterable[Mapping[str, object]]) -> list[Rule]:
    seen: dict[str, Rule] = {}
    for row in restrictions:
        rule = profile_rule(row.get("slug"), row.get("name"))
        if rule is not None:
            seen.setdefault(rule.id, rule)
    return list(seen.values())


def own_rule(label: str, *, active: bool = True) -> Rule:
    text = clean(label)
    return Rule(id=rule_id(text), label=text, permanent=False, active=active)


def too_long(label: str) -> bool:
    return len(clean(label)) > MAX_LABEL


__all__ = [
    "MAX_LABEL",
    "NO_RESTRICTION",
    "PROFILE_LABELS",
    "Rule",
    "clean",
    "key",
    "own_rule",
    "profile_rule",
    "profile_rules",
    "rule_id",
    "too_long",
]
