from __future__ import annotations

import re
from collections.abc import Iterable
from functools import cache
from importlib import resources

from komora.agent.prompts import register as register_prompt
from komora.core.skills import FILES, Skill
from komora.logging import get_logger

log = get_logger(__name__)

HEADER = (
    "СКІЛИ ПІД ЦЕЙ КОШИК. Нижче -- інструкції, які спрацювали саме на цьому "
    "наборі фактів. Вони уточнюють, ЧИМ судити, і не скасовують правил вище."
)


READS = "**Читає.**"

_FIELD = re.compile(r"`([^`]+)`")

_PARAGRAPH = "\n\n"


@cache
def text(name: str) -> str:
    stem = FILES[name]
    return (
        resources.files(__package__ or "komora.agent.skills")
        .joinpath(f"{stem}.md")
        .read_text(encoding="utf-8")
        .strip()
    )


@cache
def fields(name: str) -> tuple[str, ...]:
    try:
        body = text(name)
    except KeyError, OSError:
        return ()
    _, _, rest = body.partition(READS)
    if not rest:
        return ()
    seen: dict[str, None] = {}
    for word in _FIELD.findall(rest.split(_PARAGRAPH, 1)[0]):
        seen.setdefault(word, None)
    return tuple(seen)


PANTRY_HEADER = (
    "СКІЛИ ПІД ЦЮ КОМОРУ. Нижче -- інструкції, які спрацювали саме на цьому "
    "стані дому. Вони уточнюють, ЧИМ судити, і не скасовують правил вище."
)


def block(skills: Iterable[Skill], *, header: str = HEADER) -> str:
    parts: list[str] = []
    for skill in skills:
        try:
            parts.append(text(skill.name))
        except (KeyError, OSError) as exc:
            log.warning("skills.text_unreadable", skill=skill.name, error=str(exc)[:80])
    if not parts:
        return ""
    return "\n\n" + header + "\n\n" + "\n\n".join(parts)


def _register_texts() -> None:
    register_prompt("skill.header", HEADER)
    for name, stem in FILES.items():
        try:
            register_prompt(f"skill.{stem}", text(name))
        except (KeyError, OSError) as exc:
            log.warning("skills.text_unregistered", skill=name, error=str(exc)[:80])


_register_texts()


__all__ = ["HEADER", "PANTRY_HEADER", "READS", "block", "fields", "text"]
