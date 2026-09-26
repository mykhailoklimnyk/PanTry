from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

KINDS = ("code", "ours", "open", "off")

MEANING = {
    "code": "виконує наш код; текст їде в промпт як є",
    "ours": "політика вендора, у Коморі інша; їде разом з нашим вироком",
    "open": "не виконуємо, кандидат на фікс; їде з номером задачі",
    "off": "не про нас (чат або сценарій поза продуктом); знімається",
}

QUOTE_CHARS = 150

REBIND_SHARE = 0.5

_SPACES = re.compile(r"\s+")


def blocks(description: str) -> tuple[str, ...]:
    out = []
    for chunk in description.split("\n\n"):
        text = _SPACES.sub(" ", chunk).strip()
        if text:
            out.append(text)
    return tuple(out)


def fingerprint(block: str) -> str:
    return hashlib.sha256(_SPACES.sub(" ", block).strip().encode()).hexdigest()[:12]


@dataclass(frozen=True, slots=True)
class Verdict:

    tool: str
    sha: str
    kind: str
    verdict: str
    where: str = ""

    def valid(self) -> bool:
        return bool(self.tool and self.sha and self.verdict) and self.kind in KINDS


@dataclass(frozen=True, slots=True)
class Gap:

    tool: str
    sha: str
    head: str


@dataclass(frozen=True, slots=True)
class Audit:

    judged: int = 0
    unjudged: tuple[Gap, ...] = ()
    orphaned: tuple[Gap, ...] = ()
    broken: tuple[Gap, ...] = ()
    renamed: tuple[Rename, ...] = ()

    def ok(self) -> bool:
        return not (self.unjudged or self.orphaned or self.broken or self.renamed)

    def lines(self) -> list[str]:
        out = [rename.line() for rename in self.renamed]
        for gap in self.unjudged:
            out.append(f"+ без вироку: {gap.tool} [{gap.sha}] {gap.head}")
        for gap in self.orphaned:
            out.append(f"- вирок без абзацу: {gap.tool} [{gap.sha}] {gap.head}")
        for gap in self.broken:
            out.append(f"! кривий рядок: {gap.tool} [{gap.sha}] {gap.head}")
        return out


def _head(text: str, limit: int = 90) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


def audit(tools: Sequence[Mapping[str, object]], verdicts: Iterable[Verdict]) -> Audit:
    known: dict[tuple[str, str], Verdict] = {}
    broken: list[Gap] = []
    for row in verdicts:
        key = (row.tool, row.sha)
        if not row.valid():
            broken.append(Gap(row.tool, row.sha, f"вирок «{row.kind}»: {_head(row.verdict, 40)}"))
            continue
        if key in known:
            broken.append(Gap(row.tool, row.sha, "ключ уже є в реєстрі"))
            continue
        known[key] = row
    renamed = rebind(tools, known.values())
    was_of = {rename.now: rename.was for rename in renamed}
    live: dict[tuple[str, str], str] = {}
    for tool in tools:
        name = str(tool.get("name") or "")
        for block in blocks(str(tool.get("description") or "")):
            live[(was_of.get(name, name), fingerprint(block))] = block
    unjudged = [Gap(t, s, _head(text)) for (t, s), text in live.items() if (t, s) not in known]
    orphaned = [
        Gap(t, s, _head(row.verdict, 60)) for (t, s), row in known.items() if (t, s) not in live
    ]
    return Audit(
        judged=len(known) - len(orphaned),
        unjudged=tuple(sorted(unjudged, key=lambda g: (g.tool, g.sha))),
        orphaned=tuple(sorted(orphaned, key=lambda g: (g.tool, g.sha))),
        broken=tuple(sorted(broken, key=lambda g: (g.tool, g.sha))),
        renamed=renamed,
    )


@dataclass(frozen=True, slots=True)
class Rename:

    was: str
    now: str
    shared: int
    of: int

    def line(self) -> str:
        return (
            f"~ перейменовано: {self.was} -> {self.now}"
            f" ({self.shared} з {self.of} інструкцій ті самі)"
        )


def rebind(
    tools: Sequence[Mapping[str, object]], verdicts: Iterable[Verdict]
) -> tuple[Rename, ...]:
    known: dict[str, set[str]] = {}
    for row in verdicts:
        if row.valid():
            known.setdefault(row.tool, set()).add(row.sha)
    seen: dict[str, int] = {}
    for shas in known.values():
        for sha in shas:
            seen[sha] = seen.get(sha, 0) + 1
    live: dict[str, set[str]] = {}
    for tool in tools:
        name = str(tool.get("name") or "")
        if name:
            said = blocks(str(tool.get("description") or ""))
            live[name] = {fingerprint(block) for block in said}
    gone = sorted(set(known) - set(live))
    fresh = sorted(set(live) - set(known))
    taken: set[str] = set()
    found: list[Rename] = []
    for was in gone:
        mine = {sha for sha in known[was] if seen.get(sha, 0) == 1}
        if not mine:
            continue
        scored = sorted(
            ((len(mine & live[now]), now) for now in fresh if now not in taken),
            key=lambda pair: (-pair[0], pair[1]),
        )
        if not scored:
            continue
        best, now = scored[0]
        if best < 1 or best < len(mine) * REBIND_SHARE:
            continue
        if len(scored) > 1 and scored[1][0] == best:
            continue
        taken.add(now)
        found.append(Rename(was=was, now=now, shared=best, of=len(mine)))
    return tuple(found)


@dataclass(frozen=True, slots=True)
class Digest:

    rows: tuple[str, ...] = ()
    dropped: int = 0
    unjudged: int = 0
    renamed: tuple[Rename, ...] = ()

    def text(self) -> str:
        return "\n".join(self.rows)


def digest(
    tools: Sequence[Mapping[str, object]],
    verdicts: Iterable[Verdict],
    *,
    wanted: Iterable[str] = (),
) -> Digest:
    judged = [row for row in verdicts if row.valid()]
    known = {(row.tool, row.sha): row for row in judged}
    renamed = rebind(tools, judged)
    was_of = {rename.now: rename.was for rename in renamed}
    keep = set(wanted)
    rows: list[str] = []
    dropped = unjudged = 0
    for tool in tools:
        name = str(tool.get("name") or "")
        was = was_of.get(name, name)
        if keep and name not in keep and was not in keep:
            continue
        said: list[str] = []
        for block in blocks(str(tool.get("description") or "")):
            row = known.get((was, fingerprint(block)))
            if row is None:
                unjudged += 1
                continue
            if row.kind == "off":
                dropped += 1
                continue
            if row.kind == "code":
                said.append(block)
                continue
            mark = "у Коморі інакше" if row.kind == "ours" else "поки не виконуємо"
            said.append(f"[{_head(block, QUOTE_CHARS)} -- {mark}: {row.verdict}]")
        if said:
            title = name if was == name else f"{name} (був {was})"
            rows.append(f"- {title}: " + " ".join(said))
    return Digest(rows=tuple(rows), dropped=dropped, unjudged=unjudged, renamed=renamed)


__all__ = [
    "KINDS",
    "MEANING",
    "QUOTE_CHARS",
    "REBIND_SHARE",
    "Audit",
    "Digest",
    "Gap",
    "Rename",
    "Verdict",
    "audit",
    "blocks",
    "digest",
    "fingerprint",
    "rebind",
]
