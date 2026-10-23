from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

SAME_SENTENCE = 0.05

SPREAD_FLOOR = 20

_CYRILLIC = re.compile(r"[а-яіїєґА-ЯІЇЄҐ]")
_DIGIT = re.compile(r"\d")


class Fact(Protocol):

    @property
    def keeps(self) -> str | None: ...
    @property
    def sanity(self) -> str | None: ...
    @property
    def rhythm_lies(self) -> bool | None: ...
    @property
    def per_day(self) -> Decimal | None: ...
    @property
    def per_day_unit(self) -> str | None: ...


@dataclass(frozen=True, slots=True)
class Finding:

    rule: str
    note: str


@dataclass(frozen=True, slots=True)
class Report:

    rows: int
    with_keeps: int
    with_sanity: int
    unique_sanity: int
    lies: int
    findings: tuple[Finding, ...]

    @property
    def clean(self) -> bool:
        return not self.findings

    def lines(self) -> list[str]:
        out = [
            f"перевірка: рядків {self.rows}, зі стелею {self.with_keeps}, "
            f"з глуздом {self.with_sanity}, різних речень {self.unique_sanity}, "
            f"«ритм бреше» {self.lies}"
        ]
        if self.clean:
            out.append("  зауважень немає")
        else:
            out.extend(f"  {f.rule}: {f.note}" for f in self.findings)
        return out


def audit(facts: Mapping[str, Fact]) -> Report:
    rows = list(facts.values())
    sentences = [str(row.sanity or "").strip() for row in rows]
    said = [s for s in sentences if s]
    with_keeps = sum(1 for row in rows if row.keeps)
    counted = Counter(said)
    findings: list[Finding] = []

    half = sum(1 for row in rows if row.keeps and not (row.sanity or "").strip())
    if half:
        findings.append(Finding("половина відповіді", f"мітки зі стелею, але без глузду: {half}"))
    orphan = sum(1 for row in rows if (row.sanity or "").strip() and not row.keeps)
    if orphan:
        findings.append(Finding("половина відповіді", f"мітки з глуздом, але без стелі: {orphan}"))

    if said:
        text, times = counted.most_common(1)[0]
        if times / len(said) > SAME_SENTENCE:
            findings.append(
                Finding(
                    "одне речення на багатьох",
                    f"«{text}» -- {times} разів з {len(said)}",
                )
            )

    digits = [s for s in said if _DIGIT.search(s)]
    if digits:
        findings.append(
            Finding("вигадане число", f"речень із цифрою: {len(digits)}, напр. «{digits[0]}»")
        )

    foreign = [s for s in said if not _CYRILLIC.search(s)]
    if foreign:
        findings.append(
            Finding("чужа абетка", f"речень без кирилиці: {len(foreign)}, напр. «{foreign[0]}»")
        )

    unitless = sum(1 for row in rows if row.per_day is not None and not row.per_day_unit)
    if unitless:
        findings.append(Finding("число без одиниці", f"норма без «г» чи «шт»: {unitless}"))

    lies = sum(1 for row in rows if row.rhythm_lies)
    answered = [row for row in rows if row.rhythm_lies is not None]
    if len(answered) >= SPREAD_FLOOR and lies in (0, len(answered)):
        findings.append(
            Finding("вирок без розкиду", f"«ритм бреше» однаковий у всіх {len(answered)}")
        )

    tiers = {row.keeps for row in rows if row.keeps}
    if with_keeps >= SPREAD_FLOOR and len(tiers) == 1:
        findings.append(Finding("ярус без розкиду", f"стеля зберігання одна на всі {with_keeps}"))

    return Report(
        rows=len(rows),
        with_keeps=with_keeps,
        with_sanity=len(said),
        unique_sanity=len(counted),
        lies=lies,
        findings=tuple(findings),
    )


__all__ = ["SAME_SENTENCE", "SPREAD_FLOOR", "Fact", "Finding", "Report", "audit"]
