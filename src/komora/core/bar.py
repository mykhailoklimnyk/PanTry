from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal
from enum import StrEnum
from itertools import pairwise

from komora.core.dictionary import Node
from komora.core.mandate import DEFAULT_FORK_PERCENT, Fork, price_fork
from komora.core.pantry import manual_id

ALCOHOL_HEADS = frozenset(
    {
        "пиво",
        "вино",
        "горілка",
        "коньяк",
        "віскі",
        "ром",
        "джин",
        "лікер",
        "сидр",
        "шампанське",
        "вермут",
        "текіла",
        "бренді",
        "настоянка",
        "наливка",
        "просекко",
    }
)


def alcohol_word(name: str) -> bool:
    head = name.strip().split()
    return bool(head) and head[0].lower() in ALCOHOL_HEADS


class DrinkKind(StrEnum):

    STRONG = "strong"
    WINE = "wine"
    LIGHT = "light"


@dataclass(frozen=True, slots=True)
class Bottle:

    article: str
    name: str
    receipts: int
    price: Decimal | None = None
    last_at: datetime | None = None
    pack: str = ""


@dataclass(frozen=True, slots=True)
class Kind:

    key: str
    label: str
    group: DrinkKind
    bottles: tuple[Bottle, ...]
    group_said: bool = False


@dataclass(frozen=True, slots=True)
class Row:

    id: str
    label: str
    group: DrinkKind | None
    group_said: bool = False
    times: int = 0
    days_since: int | None = None
    usual: Bottle | None = None
    price: Decimal | None = None
    share: str = ""
    fork: Fork | None = None
    fork_note: str = ""
    said: bool = False


def _share(part: int, whole: int) -> str:
    return f"{part} з {whole}"


_NO_DATE = datetime.min.replace(tzinfo=UTC)


def _freshness(bottle: Bottle) -> tuple[bool, datetime, int]:
    return (bottle.last_at is not None, bottle.last_at or _NO_DATE, bottle.receipts)


def fork_of(prices: Sequence[Decimal], *, pack: str = "") -> tuple[Fork, str]:
    said_pack = f" {pack}" if pack else ""
    low, high = min(prices), max(prices)
    if low != high:
        wide = Fork(
            low=low.quantize(Decimal("1"), rounding=ROUND_FLOOR),
            high=high.quantize(Decimal("1"), rounding=ROUND_CEILING),
        )
        return wide, f"брав{said_pack} за {wide.low}–{wide.high} ₴"
    fork = price_fork(low)
    said = low.quantize(Decimal("1"))
    return (
        fork,
        f"брав{said_pack} за {said} ₴, беру {DEFAULT_FORK_PERCENT}% в обидва боки",
    )


SHELVES: Mapping[str, DrinkKind | None] = {
    "mitsnyi-alkogol-4458": DrinkKind.STRONG,
    "vermuty-4461": DrinkKind.WINE,
    "tykhi-vyna-4459": DrinkKind.WINE,
    "igrysti-vyna-ta-shampanske-4460": DrinkKind.WINE,
    "pyvo-4503": DrinkKind.LIGHT,
    "slaboalkogolni-napoi-sydr-4463": DrinkKind.LIGHT,
    "bezalkogolnyi-alkogol-4464": None,
}


@dataclass(frozen=True, slots=True)
class Shelved:

    group: DrinkKind
    label: str


def _title_head(title: str) -> str:
    head = title.split(",")[0]
    head = head.split(" та ")[0]
    return " ".join(head.casefold().split())


def _refines(title: str, parent: str) -> bool:
    word = _title_head(parent).split()
    return bool(word) and word[-1] in _title_head(title).split()


def shelf_map(nodes: Sequence[Node]) -> dict[str, Shelved]:
    by_id = {node.id: node for node in nodes}
    out: dict[str, Shelved] = {}
    for node in nodes:
        chain: list[Node] = []
        step: Node | None = node
        seen: set[str] = set()
        while step is not None and step.id not in seen:
            seen.add(step.id)
            chain.append(step)
            if step.slug in SHELVES:
                break
            step = by_id.get(step.parent_id) if step.parent_id else None
        if not chain or chain[-1].slug not in SHELVES:
            continue
        group = SHELVES[chain[-1].slug]
        if group is None:
            continue
        label = chain[0]
        for lower, upper in pairwise(chain):
            if not _refines(lower.title, upper.title):
                break
            label = upper
        out[node.slug] = Shelved(group=group, label=_title_head(label.title))
    return out


def shelved(
    article: str,
    nodes: Mapping[str, frozenset[str]],
    shelves: Mapping[str, Shelved],
) -> Shelved | None:
    for slug in sorted(nodes.get(article, ())):
        found = shelves.get(slug)
        if found is not None:
            return found
    return None


def said_group(
    key: str, guessed: DrinkKind | None, said: Mapping[str, DrinkKind]
) -> tuple[DrinkKind | None, bool]:
    chosen = said.get(key)
    if chosen is None:
        return guessed, False
    return chosen, True


def said_row(kind: str, label: str, *, group: DrinkKind | None, group_said: bool = False) -> Row:
    return Row(
        id=manual_id(kind),
        label=label.strip(),
        group=group,
        group_said=group_said,
        said=True,
    )


@dataclass(frozen=True, slots=True)
class Shelf:

    rows: tuple[Row, ...]
    dropped: int = 0


def rows(kinds: Sequence[Kind], *, now: datetime) -> Shelf:
    built: list[Row] = []
    dropped = 0
    for kind in kinds:
        priced = [
            (bottle, bottle.price)
            for bottle in kind.bottles
            if bottle.price is not None and bottle.price > 0
        ]
        moments = [bottle.last_at for bottle, _ in priced if bottle.last_at is not None]
        if not priced or not moments:
            dropped += 1
            continue
        usual, price = max(priced, key=lambda pair: _freshness(pair[0]))
        prices = [value for bottle, value in priced if bottle.pack == usual.pack]
        times = sum(bottle.receipts for bottle in kind.bottles)
        fork, note = fork_of(prices, pack=usual.pack)
        built.append(
            Row(
                id=kind.key,
                label=kind.label,
                group=kind.group,
                group_said=kind.group_said,
                times=times,
                days_since=max(0, (now - max(moments)).days),
                usual=usual,
                price=price,
                share=_share(usual.receipts, times),
                fork=fork,
                fork_note=note,
            )
        )
    built.sort(key=lambda row: (-row.times, row.days_since, row.label))
    return Shelf(tuple(built), dropped)


__all__ = [
    "Bottle",
    "DrinkKind",
    "Kind",
    "Row",
    "Shelf",
    "fork_of",
    "rows",
    "said_group",
    "said_row",
]
