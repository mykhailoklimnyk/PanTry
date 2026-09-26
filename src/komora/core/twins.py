from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal


def norm(text: str) -> str:
    return " ".join(text.split()).casefold()


def head_word(key: str) -> str:
    parts = norm(key).split()
    return parts[0] if parts else ""


def group_key(*, phrase: str, kind_key: str) -> str:
    said = norm(phrase)
    return said or head_word(kind_key)


@dataclass(frozen=True, slots=True)
class Row:

    intent: str
    article: str
    name: str
    phrase: str = ""
    kind_key: str = ""
    guest_word: bool = False
    own_article: bool = False
    price: Decimal = Decimal(0)
    receipts: int = 0
    recent_receipts: int = 0
    unit_price: str = ""
    promo: str = ""
    came_from: str = ""
    sections: frozenset[str] = frozenset()
    bought: frozenset[str] = frozenset()

    @property
    def key(self) -> str:
        return group_key(phrase=self.phrase, kind_key=self.kind_key or self.intent)


@dataclass(frozen=True, slots=True)
class Group:

    key: str
    rows: tuple[Row, ...]
    by_section: bool = False

    @property
    def articles(self) -> tuple[str, ...]:
        return tuple(row.article for row in self.rows)


def groups(rows: Sequence[Row]) -> tuple[Group, ...]:
    keyed = [row for row in rows if row.key]
    by_phrase: dict[str, int] = {}
    for row in keyed:
        by_phrase[row.key] = by_phrase.get(row.key, 0) + 1
    parent = list(range(len(keyed)))

    def root(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    first: dict[str, int] = {}
    for index, row in enumerate(keyed):
        lonely = by_phrase[row.key] == 1
        sections = row.sections if lonely else frozenset()
        for axis in (f"фраза:{row.key}", *(f"відділ:{norm(s)}" for s in sections)):
            if axis in first:
                parent[root(index)] = root(first[axis])
            else:
                first[axis] = index
    buckets: dict[int, list[Row]] = {}
    for index, row in enumerate(keyed):
        buckets.setdefault(root(index), []).append(row)
    out: list[Group] = []
    for bucket in buckets.values():
        if len(bucket) < 2:
            continue
        phrases = {row.key for row in bucket}
        if len(phrases) == 1:
            out.append(Group(key=bucket[0].key, rows=tuple(bucket)))
            continue
        shared = set.intersection(*({norm(s) for s in row.sections} for row in bucket))
        key = min(shared) if shared else " / ".join(sorted(phrases))
        out.append(Group(key=key, rows=tuple(bucket), by_section=True))
    return tuple(out)


def together(group: Group) -> tuple[str, ...]:
    said: list[str] = []
    rows = [row for row in group.rows if row.bought]
    for index, first in enumerate(rows):
        for second in rows[index + 1 :]:
            both = len(first.bought & second.bought)
            trips = len(first.bought | second.bought)
            how = "по черзі, тобто вдома одне замінює інше" if both == 0 else "разом"
            said.append(
                f"{first.article} і {second.article}: {how} -- в один похід "
                f"{both} з {trips} походів з будь-яким із двох"
            )
    return tuple(said)


@dataclass(frozen=True, slots=True)
class Verdict:

    key: str
    same: bool
    keep: str = ""
    why: str = ""
    drop: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Drop:

    intent: str
    name: str
    kept_intent: str
    kept_name: str
    why: str


SAID_MODEL = "агент каже: це одна потреба вдома"
SAID_GUEST = "агент каже: це одна потреба; лишаю те, що назвав сам гість"
SAID_OWN = "агент каже: це одна потреба; лишаю свій артикул з чеків, а не заміну"
NOT_SAME = "агент каже: це різні потреби"
NO_ANSWER = "агент про цю пару не відповів"
NO_KEEP = "агент не назвав, кого лишити"
ALL_GUEST = "решта рядків групи -- слова гостя"
NOT_IN_TURNS = (
    "агент каже: одна потреба, але чеки цього не доводять -- це беруть разом або не брали"
)


@dataclass(frozen=True, slots=True)
class Judged:

    dropped: tuple[Drop, ...] = ()
    guest_kept: tuple[str, ...] = ()
    own_kept: tuple[str, ...] = ()
    left: Mapping[str, str] = field(default_factory=dict)

    @property
    def intents(self) -> tuple[str, ...]:
        return tuple(drop.intent for drop in self.dropped)


def judge(pairs: Sequence[Group], verdicts: Mapping[str, Verdict]) -> Judged:
    dropped: list[Drop] = []
    guest_kept: list[str] = []
    own_kept: list[str] = []
    left: dict[str, str] = {}
    for group in pairs:
        verdict = verdicts.get(group.key)
        if verdict is None:
            left[group.key] = NO_ANSWER
            continue
        if not verdict.same:
            left[group.key] = NOT_SAME
            continue
        kept = next((row for row in group.rows if row.article == verdict.keep), None)
        if kept is None:
            left[group.key] = NO_KEEP
            continue
        involved = (
            tuple(row for row in group.rows if row.article in verdict.drop or row is kept)
            if verdict.drop
            else group.rows
        )
        ours = SAID_MODEL
        if not kept.guest_word:
            said_by_guest = next((row for row in involved if row.guest_word), None)
            own = next((row for row in involved if row.own_article), None)
            if said_by_guest is not None:
                kept, ours = said_by_guest, SAID_GUEST
                guest_kept.append(group.key)
            elif not kept.own_article and own is not None:
                kept, ours = own, SAID_OWN
                own_kept.append(group.key)
        goes = [row for row in involved if row.article != kept.article and not row.guest_word]
        if group.by_section:
            proven = [
                row
                for row in goes
                if row.bought and kept.bought and not (row.bought & kept.bought)
            ]
            if goes and not proven:
                left[group.key] = NOT_IN_TURNS
                continue
            goes = proven
        if not goes:
            left[group.key] = ALL_GUEST
            continue
        said = verdict.why.strip() or ours
        dropped.extend(
            Drop(
                intent=row.intent,
                name=row.name,
                kept_intent=kept.intent,
                kept_name=kept.name,
                why=said,
            )
            for row in goes
        )
    return Judged(
        dropped=tuple(dropped),
        guest_kept=tuple(guest_kept),
        own_kept=tuple(own_kept),
        left=left,
    )


__all__ = [
    "ALL_GUEST",
    "NOT_IN_TURNS",
    "NOT_SAME",
    "NO_ANSWER",
    "NO_KEEP",
    "SAID_GUEST",
    "SAID_MODEL",
    "SAID_OWN",
    "Drop",
    "Group",
    "Judged",
    "Row",
    "Verdict",
    "group_key",
    "groups",
    "head_word",
    "judge",
    "norm",
    "together",
]
