from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Any

from komora.agent.aisle import intent_aisles, known_aisles
from komora.agent.basket import (
    Naming,
    Receipts,
    Tally,
    _amount_text,
    history_kinds,
    intent_keeps,
    intent_names,
    is_service_item,
    kind_key,
    naming_candidates,
    naming_labels,
    pantry_live,
    plural,
    search_products,
)
from komora.agent.executor import Made
from komora.agent.probe import MAX_QUESTIONS, Probe, intent_probe
from komora.agent.sanity import intent_sense
from komora.agent.steps.ground import Ground
from komora.api.schemas import Pantry
from komora.core.location import Location
from komora.core.packaging import sale_unit
from komora.core.said import Said

SHELF_ROWS = 8


@dataclass(frozen=True, slots=True)
class Pack:

    article: str
    on_shelf: bool
    name: str = ""
    ratio: str | None = None
    weighted: bool | None = None
    unit: str | None = None

    @property
    def text(self) -> str:
        if not self.on_shelf:
            return "на полиці зараз немає"
        if self.unit:
            return f"продають на вагу, {self.unit}"
        return f"фасовка {self.ratio}" if self.ratio else "фасовки картка не назвала"


def _only(labels: Sequence[str], wanted: Sequence[str], stray: Sequence[str]) -> list[str]:
    if not wanted and stray:
        return []
    chosen = set(wanted)
    return [label for label in labels if not chosen or label in chosen]


def _addressed(labels: Sequence[str], stray: Sequence[str]) -> dict[str, Any]:
    told: dict[str, Any] = {}
    if labels:
        told["адресно"] = len(labels)
    if stray:
        told["міток немає в коморі"] = list(stray)
    return told


class Home:

    def __init__(
        self,
        ground: Ground,
        *,
        said: Said,
        read: Receipts,
        drawn: Pantry,
        place: Location | None = None,
        cold: bool = False,
        continuing: bool = False,
    ) -> None:
        self.ground = ground
        self.said = said
        self.read = read
        self.place = place
        self.pantry = drawn
        self.names: dict[str, Naming] = {}
        self._shelf: list[str] | None = None
        self.cold = cold
        self.continuing = continuing
        self.probes: list[Probe] = []
        self.packaging: dict[str, Pack] = {}

    async def name(self, bound: Mapping[str, Any]) -> Made:
        tally = Tally()
        kinds = history_kinds([item for item in bound["history"] if not is_service_item(item.name)])
        candidates = naming_candidates(kinds, self.said.listed.values())
        probe = Tally()
        await intent_names(
            None,
            candidates,
            pool=self.ground.pool,
            tally=probe,
            use_cache=not self.cold,
            memory=not self.cold or self.continuing,
        )
        to_ask = len(candidates) - probe.named_cached
        if to_ask > 0 and self.ground.llm is not None:
            self.ground.trace.add(
                "step-naming-ahead",
                "model",
                {"спитаю": to_ask, "з кешу": probe.named_cached, "пачок": self.ground.packs},
                f"називаю {to_ask} {plural(to_ask, 'вид', 'види', 'видів')} у "
                f"{self.ground.packs} {plural(self.ground.packs, 'пачку', 'пачки', 'пачок')} — "
                "найдовший крок: модель читає кожну назву з чека",
                tag_tone="muted",
            )
        self.names = await intent_names(
            self.ground.llm,
            candidates,
            pool=self.ground.pool,
            tally=tally,
            use_cache=not self.cold,
            memory=not self.cold or self.continuing,
            batches=self.ground.packs,
        )
        return Made(
            facts={"named": self.names},
            args={
                "кандидатів": len(candidates),
                "з кешу": tally.named_cached,
                "пачок": self.ground.packs,
            },
            summary=(
                f"названо {len(self.names)} з {len(candidates)}: "
                f"з кешу {tally.named_cached}, спитано {tally.named_asked}"
                + (f" — тому й довше, {self.ground.packs} пач." if tally.named_asked else "")
            ),
        )

    async def rhythm(
        self, bound: Mapping[str, Any], *, labels: Sequence[str] = (), stray: Sequence[str] = ()
    ) -> Made:
        wanted, labels = tuple(labels), _only(naming_labels(bound["named"]), labels, stray)
        sense = await intent_sense(
            self.ground.llm,
            labels,
            pool=self.ground.pool,
            use_cache=not self.cold,
            batches=self.ground.packs,
        )
        return Made(
            facts={"verdicts": sense},
            args={"міток": len(labels), "пачок": self.ground.packs, **_addressed(wanted, stray)},
            summary=(
                f"глузд про вид: {len(sense)} з {len(labels)}"
                if labels
                else "називати ще нема чого — глузду теж"
            ),
        )

    async def keeps(
        self, bound: Mapping[str, Any], *, labels: Sequence[str] = (), stray: Sequence[str] = ()
    ) -> Made:
        wanted, labels = tuple(labels), _only(naming_labels(bound["named"]), labels, stray)
        keeps = await intent_keeps(
            self.ground.llm,
            labels,
            pool=self.ground.pool,
            use_cache=not self.cold,
            batches=self.ground.packs,
        )
        return Made(
            facts={"keeps": keeps},
            args={"міток": len(labels), "пачок": self.ground.packs, **_addressed(wanted, stray)},
            summary=f"стеля зберігання: {len(keeps)} з {len(labels)}",
        )

    async def aisle(
        self, bound: Mapping[str, Any], *, labels: Sequence[str] = (), stray: Sequence[str] = ()
    ) -> Made:
        wanted, labels = tuple(labels), _only(naming_labels(bound["named"]), labels, stray)
        if self._shelf is None:
            self._shelf = await known_aisles(self.ground.pool)
        vocabulary = self._shelf
        found = await intent_aisles(
            self.ground.llm,
            labels,
            vocabulary,
            pool=self.ground.pool,
            use_cache=not self.cold,
            batches=self.ground.packs,
        )
        return Made(
            facts={"aisles": found},
            args={
                "міток": len(labels),
                "відділів у словнику": len(vocabulary),
                "пачок": self.ground.packs,
                **_addressed(wanted, stray),
            },
            summary=(
                f"відділ виду: {len(found)} з {len(labels)}"
                if vocabulary
                else "дерева категорій немає — відділ питати нема з чого"
            ),
        )

    async def shelf(
        self, bound: Mapping[str, Any], *, labels: Sequence[str] = (), stray: Sequence[str] = ()
    ) -> Made:
        rows = list(bound["pantry"])
        wanted = set(_only([row.label for row in rows], labels, stray)) if labels or stray else None
        silent = [
            row
            for row in rows
            if row.named
            and row.cycle_days is None
            and row.id.isdigit()
            and row.id not in self.packaging
            and (wanted is None or row.label in wanted)
        ]
        take, left = silent[:SHELF_ROWS], silent[SHELF_ROWS:]
        found = 0
        shelf_ms: int | None = None
        if take:
            hits, shelf_ms = await search_products(
                self.ground.mcp, [row.id for row in take], self.read.slot, self.read.branch_id
            )
            for row in take:
                own = [p for p in hits.get(row.id, []) if str(p.get("externalProductId")) == row.id]
                if own:
                    card = own[0]
                    ratio = None if card.get("displayRatio") is None else str(card["displayRatio"])
                    self.packaging[row.id] = Pack(
                        article=row.id,
                        on_shelf=True,
                        name=str(card.get("name") or ""),
                        ratio=ratio,
                        weighted=card.get("weighted"),
                        unit=sale_unit(weighted=card.get("weighted"), ratio=ratio, step=None),
                    )
                    found += 1
                else:
                    self.packaging[row.id] = Pack(article=row.id, on_shelf=False)
        answered = sum(1 for row in rows if row.id in self.packaging)
        return Made(
            facts={"packaging": dict(self.packaging)},
            args={
                "рядків": len(rows),
                "спитав": len(take),
                "на полиці": found,
                "відповідь полиці вже є": answered,
                "стеля": f"{SHELF_ROWS} рядків за оберт",
                "лишилось наступному оберту": len(left),
                "мс пошуку": shelf_ms,
                **_addressed(labels, stray),
            },
            summary=(
                f"полиця про свій артикул: спитав {len(take)}, на полиці {found}"
                + (f", ще {len(left)} за стелею" if left else "")
                if take
                else (
                    "перелік не про кого: адресовані рядки вже мають відповідь полиці або число"
                    if wanted
                    else "полицю питати нема про кого: мовчазних рядків без відповіді полиці немає"
                )
            ),
            decision="крок поставив план: фасовку й одиницю знає лише полиця, і без них "
            "питання гостю без осі",
            tag=f"+{found}" if found else None,
            tag_tone="good" if found else "muted",
        )

    async def ask(
        self, bound: Mapping[str, Any], *, labels: Sequence[str] = (), stray: Sequence[str] = ()
    ) -> Made:
        rows = list(bound["pantry"])
        asking = [row.label for row in rows if row.ask]
        keys = {str(item.lager_id): kind_key(item.name) for item in self.read.history}
        under = {row.label: keys[row.id] for row in rows if row.id in keys}
        usual = {
            row.label: (
                f"зазвичай береш {_amount_text(row.usual_qty)} {row.unit}".rstrip()
                + (f" · {self.packaging[row.id].text}" if row.id in self.packaging else "")
            )
            for row in rows
            if row.usual_qty
        }
        wanted = set(_only([row.label for row in rows], labels, stray)) if labels or stray else None
        silent = [
            row.label
            for row in rows
            if row.cycle_days is None
            and row.named
            and row.label in under
            and (wanted is None or row.label in wanted)
        ]
        probes, thrown, tokens = await intent_probe(self.ground.llm, silent)
        probes = [
            replace(
                probe,
                kind=under[probe.label],
                usual=usual.get(probe.label, ""),
                covers=tuple(label for label in probe.covers if label in under),
                cover_kinds=tuple(under[label] for label in probe.covers if label in under),
            )
            for probe in probes
            if probe.label in under
        ]
        self.probes = probes
        covers = sum(len(probe.covers) for probe in probes)
        return Made(
            facts={
                "questions": [label for probe in probes for label in (probe.label, *probe.covers)],
                "asked": probes,
            },
            args={
                "рядків": len(rows),
                "питає рядків": len(asking),
                "рядків без числа": len(silent),
                "ще без мітки": sum(1 for row in rows if not row.named),
                "без ключа запису": sum(1 for row in rows if row.id not in keys),
                "питань": len(probes),
                "пояснює сусідів": covers,
                "стеля": f"{MAX_QUESTIONS} питання",
                "токенів": tokens,
                **({"зрізано": thrown} if thrown else {}),
                **_addressed(labels, stray),
            },
            summary=(
                f"питаю про {len(probes)} з {len(silent)} мовчазних; відповіді пояснять ще {covers}"
                if probes
                else f"мовчазних рядків {len(silent)}, а питати нема про що"
            ),
            decision="про що спитати -- рішення агента: він обирає ті види, "
            "відповідь на які пояснює сусідні; стеля питань стала",
            tag=f"{len(probes)} пит." if probes else "без питань",
            tag_tone="good" if probes else "muted",
        )

    async def draw(self, bound: Mapping[str, Any]) -> Made:
        self.pantry = await pantry_live(
            self.ground.mcp,
            llm=self.ground.llm,
            settings=self.ground.cfg,
            now=self.ground.moment,
            place=self.place,
            pool=self.ground.pool,
            account=self.ground.account,
            said=self.said,
            receipts=self.read,
            ask=False,
        )
        rows = self.pantry.items
        return Made(
            facts={"pantry": rows},
            args={"рядків": len(rows), "названих": sum(1 for row in rows if row.named)},
            summary=(
                f"комора перемальована: {len(rows)} рядків, "
                f"{sum(1 for row in rows if row.named)} з міткою виду"
            ),
        )


__all__ = ["SHELF_ROWS", "Home", "Pack"]
