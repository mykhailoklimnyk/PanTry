from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from komora.core.trace import Tone

MAX_STEPS = 40

MAX_WRITES = 6


class Aim(StrEnum):

    BASKET = "кошик"
    PANTRY = "комора"


class Phase(StrEnum):
    PLACE = "місце"
    SLOT = "слот"
    HISTORY = "історія"
    PANTRY = "комора"
    INTENTS = "наміри"
    SHELF = "полиця"
    DECIDE = "рішення"
    ECONOMY = "економіка"
    CART = "кошик"


@dataclass(frozen=True, slots=True)
class StepKind:

    name: str
    phase: Phase
    tool: str
    """Інструмент MCP або `code` для чистого обчислення і `model` для
    виклику моделі. Назва інструмента -- та сама, що в описах
    (`docs/mcp-tools.json`), щоб перевірка «крок кличе те, що описано»
    була рівністю рядків."""
    needs: frozenset[str] = frozenset()
    gives: frozenset[str] = frozenset()
    writes: bool = False
    repeatable: bool = False
    """Чи може стояти в плані більше одного разу. Пошук і перечитування --
    так; читання історії -- ні: другий похід за тими самими чеками це або
    помилка моделі, або петля."""


def _kind(
    name: str,
    phase: Phase,
    tool: str,
    *,
    needs: Sequence[str] = (),
    gives: Sequence[str] = (),
    writes: bool = False,
    repeatable: bool = False,
) -> StepKind:
    return StepKind(
        name=name,
        phase=phase,
        tool=tool,
        needs=frozenset(needs),
        gives=frozenset(gives),
        writes=writes,
        repeatable=repeatable,
    )


STEPS: tuple[StepKind, ...] = (
    _kind("place.address", Phase.PLACE, "silpo_get_my_delivery_addresses", gives=("address",)),
    _kind(
        "place.delivery_types",
        Phase.PLACE,
        "silpo_get_available_delivery_types",
        needs=("address",),
        gives=("delivery_types",),
    ),
    _kind("place.cart", Phase.PLACE, "silpo_get_my_shopping_cart", gives=("cart",)),
    _kind("place.decide", Phase.PLACE, "code", gives=("branch", "delivery_type")),
    _kind(
        "slot.list",
        Phase.SLOT,
        "silpo_get_time_slots",
        needs=("branch", "delivery_type"),
        gives=("slots",),
    ),
    _kind("slot.pick", Phase.SLOT, "code", needs=("slots",), gives=("slot",)),
    _kind(
        "history.receipts",
        Phase.HISTORY,
        "silpo_get_my_offline_orders",
        needs=("branch", "slot"),
        gives=("receipts",),
    ),
    _kind("history.orders", Phase.HISTORY, "silpo_get_my_online_orders", gives=("orders",)),
    _kind("history.model", Phase.HISTORY, "code", needs=("receipts",), gives=("history",)),
    _kind(
        "pantry.draw",
        Phase.PANTRY,
        "code",
        needs=("history",),
        gives=("pantry",),
        repeatable=True,
    ),
    _kind("pantry.name", Phase.PANTRY, "model", needs=("history",), gives=("named",)),
    _kind("pantry.rhythm", Phase.PANTRY, "model", needs=("named",), gives=("verdicts",)),
    _kind("pantry.keeps", Phase.PANTRY, "model", needs=("named",), gives=("keeps",)),
    _kind("pantry.aisle", Phase.PANTRY, "model", needs=("named",), gives=("aisles",)),
    _kind(
        "pantry.shelf",
        Phase.PANTRY,
        "silpo_find_products_batch",
        needs=("pantry", "history"),
        gives=("packaging",),
        repeatable=True,
    ),
    _kind(
        "pantry.ask",
        Phase.PANTRY,
        "model",
        needs=("pantry",),
        gives=("questions", "asked"),
        repeatable=True,
    ),
    _kind("intents.compose", Phase.INTENTS, "code", needs=("history",), gives=("intents",)),
    _kind(
        "shelf.search",
        Phase.SHELF,
        "silpo_find_products_batch",
        needs=("branch", "slot", "intents"),
        gives=("candidates", "intents"),
        repeatable=True,
    ),
    _kind(
        "shelf.by_article",
        Phase.SHELF,
        "silpo_find_products_batch",
        needs=("branch", "slot", "history"),
        gives=("candidates",),
        repeatable=True,
    ),
    _kind(
        "shelf.kind",
        Phase.SHELF,
        "silpo_get_products",
        needs=("branch", "slot", "intents"),
        gives=("candidates",),
        repeatable=True,
    ),
    _kind(
        "shelf.similar",
        Phase.SHELF,
        "silpo_get_similar_products",
        needs=("candidates",),
        gives=("candidates",),
        repeatable=True,
    ),
    _kind(
        "shelf.card",
        Phase.SHELF,
        "silpo_get_product_details",
        needs=("candidates",),
        gives=("candidates",),
        repeatable=True,
    ),
    _kind(
        "decide.pick",
        Phase.DECIDE,
        "model",
        needs=("intents", "candidates"),
        gives=("picks",),
        repeatable=True,
    ),
    _kind("decide.clarify", Phase.DECIDE, "code", needs=("picks",), gives=("questions",)),
    _kind(
        "decide.loop",
        Phase.DECIDE,
        "model",
        needs=("lines", "candidates"),
        gives=("lines",),
        repeatable=True,
    ),
    _kind(
        "decide.chain",
        Phase.DECIDE,
        "model",
        needs=("candidates",),
        gives=("lines", "chains"),
        repeatable=True,
    ),
    _kind(
        "economy.settle",
        Phase.ECONOMY,
        "code",
        needs=("lines", "slot"),
        gives=("economics",),
        repeatable=True,
    ),
    _kind(
        "cart.create",
        Phase.CART,
        "silpo_create_shopping_cart",
        needs=("address", "delivery_type", "slot"),
        gives=("cart",),
        writes=True,
    ),
    _kind(
        "cart.slot",
        Phase.CART,
        "silpo_update_shopping_cart",
        needs=("cart", "slot"),
        gives=("cart",),
        writes=True,
    ),
    _kind(
        "cart.write",
        Phase.CART,
        "silpo_add_or_update_cart_products",
        needs=("cart", "lines", "economics"),
        gives=("written",),
        writes=True,
        repeatable=True,
    ),
    _kind(
        "cart.remove",
        Phase.CART,
        "silpo_remove_cart_products",
        needs=("cart", "written"),
        gives=("written",),
        writes=True,
        repeatable=True,
    ),
    _kind(
        "cart.reread",
        Phase.CART,
        "silpo_get_shopping_cart_by_id",
        needs=("cart",),
        gives=("cart", "validations"),
        repeatable=True,
    ),
    _kind(
        "cart.revalidate",
        Phase.CART,
        "code",
        needs=("validations", "chains"),
        gives=("lines",),
        repeatable=True,
    ),
)

BY_NAME: Mapping[str, StepKind] = {kind.name: kind for kind in STEPS}

_PIPELINE: tuple[Phase, ...] = (
    Phase.PLACE,
    Phase.SLOT,
    Phase.HISTORY,
    Phase.PANTRY,
    Phase.INTENTS,
    Phase.SHELF,
    Phase.DECIDE,
    Phase.ECONOMY,
    Phase.CART,
)
_DEPTH: Mapping[Phase, int] = {phase: depth for depth, phase in enumerate(_PIPELINE)}

_BEFORE_SLOT_OK = frozenset({Phase.PLACE, Phase.SLOT, Phase.HISTORY, Phase.PANTRY, Phase.INTENTS})

_WRITES_NEED_REREAD = frozenset({"cart.create", "cart.slot", "cart.write", "cart.remove"})

ESSENTIAL_BEFORE_WRITE = ("decide.pick", "economy.settle")

DECIDES: Mapping[Aim, str] = {Aim.BASKET: "decide.pick"}

PHASES: Mapping[Aim, frozenset[Phase]] = {
    Aim.PANTRY: frozenset({Phase.PANTRY}),
    Aim.BASKET: frozenset(Phase) - {Phase.PANTRY},
}

CORE_AFTER_PLAN: Mapping[Aim, tuple[str, ...]] = {
    Aim.BASKET: (
        "intents.compose",
        "shelf.search",
        "decide.pick",
        "decide.chain",
        "economy.settle",
    ),
    Aim.PANTRY: (),
}

BEFORE_PANTRY = ("history.receipts", "history.orders", "history.model", "pantry.draw")

NO_RUNNER = frozenset({"shelf.card", "shelf.similar"})


@dataclass(frozen=True, slots=True)
class Step:

    name: str
    why: str = ""
    """Одне речення моделі -- навіщо цей крок. У трейс, не в код."""
    labels: tuple[str, ...] = ()
    """До яких МІТОК крок застосувати (`docs/pantry-8.md`, крок 3). Порожньо --
    до всіх: це і зворотна сумісність, і теплий шлях. Без адреси крок -- це
    команда «оброби все», а на 157 заголовках рішення від команди відрізняє
    саме перелік."""
    stray: tuple[str, ...] = ()
    """Мітки, яких у коморі немає, -- зрізані ПОШТУЧНО, а не з кроком (клас
    `salvage`), і названі, бо мовчазний різ від зламаного ключа не
    відрізнити (#132)."""

    @property
    def kind(self) -> StepKind:
        return BY_NAME[self.name]


@dataclass(frozen=True, slots=True)
class Dropped:

    name: str
    reason: str
    position: int


class Refusal(StrEnum):

    EMPTY = "нема чого дати"
    RULE = "без входу"
    BROKE = "збій"
    ORPHAN = "без виконавця"


@dataclass(frozen=True, slots=True)
class Refused:

    name: str
    why: str
    kind: Refusal


@dataclass(frozen=True, slots=True)
class Did:

    name: str
    why: str


@dataclass(frozen=True, slots=True)
class Carried:

    steps: int = 0
    writes: int = 0
    seen: frozenset[str] = frozenset()
    pending_reread: bool = False


@dataclass(frozen=True, slots=True)
class Plan:
    steps: tuple[Step, ...]
    dropped: tuple[Dropped, ...] = ()
    fatal: str | None = None
    """Чому план не годиться ЦІЛКОМ навіть після різу. None -- годиться."""
    source: str = "model"
    carried: Carried = Carried()
    """Стан ПІСЛЯ цього плану -- вхід наступної пачки."""

    @property
    def ok(self) -> bool:
        return self.fatal is None

    @property
    def writes(self) -> int:
        return sum(1 for step in self.steps if step.kind.writes)

    def names(self) -> tuple[str, ...]:
        return tuple(step.name for step in self.steps)


PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "goal": {"type": "string"},
        "steps": {
            "type": "array",
            "salvage": True,
            "items": {
                "type": "object",
                "properties": {
                    "step": {"type": "string", "enum": [kind.name for kind in STEPS]},
                    "why": {"type": ["string", "null"]},
                    "labels": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["step"],
            },
        },
    },
    "required": ["steps"],
}


BATCH_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "goal": {"type": "string"},
        "steps": PLAN_SCHEMA["properties"]["steps"],
        "stop": {"type": "boolean"},
        "why": {"type": ["string", "null"]},
    },
    "required": ["steps"],
}


def facts_of(names: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set().union(*(BY_NAME[name].gives for name in names))))


def verdict(carried: Carried, *, aim: Aim = Aim.BASKET) -> str | None:
    if carried.pending_reread:
        return "запис у кошик без перечитування після нього"
    essential = DECIDES.get(aim)
    if essential is None:
        return None
    if not carried.steps:
        return "жодного кроку не лишилось"
    if essential not in carried.seen:
        return f"у плані немає рішення ({essential})"
    return None


def _late(kind: StepKind, readers: Sequence[StepKind], ahead: Mapping[str, int]) -> str | None:
    depth = _DEPTH[kind.phase]
    for reader in readers:
        if _DEPTH[reader.phase] <= depth:
            continue
        if ahead.get(reader.name):
            continue
        common = sorted(kind.gives & reader.needs)
        if common:
            return f"запізнілий давач: {', '.join(common)} уже прочитав {reader.name}"
    return None


def validate(
    raw: Mapping[str, Any] | Sequence[Any],
    *,
    writes_allowed: bool,
    known: Sequence[str] = (),
    carried: Carried | None = None,
    whole: bool = True,
    aim: Aim = Aim.BASKET,
    labels: Iterable[str] | None = None,
) -> Plan:
    was = carried if carried is not None else Carried()
    items: Any = raw.get("steps") or () if isinstance(raw, Mapping) else raw
    if not isinstance(items, Sequence) or isinstance(items, str | bytes):
        return Plan(steps=(), fatal="план не список кроків", carried=was)

    kept: list[Step] = []
    dropped: list[Dropped] = []
    have: set[str] = set(known)
    seen: set[str] = set(was.seen)
    slot_known = "slot" in have
    pending_reread = was.pending_reread
    writes = was.writes
    taken = was.steps

    parsed = [_read(item) for item in items]
    ahead = Counter(name for name, _, _ in parsed if name is not None)
    readers: list[StepKind] = []
    addressable = None if labels is None else frozenset(labels)

    for position, (name, why, sent) in enumerate(parsed):
        if name is None:
            dropped.append(
                Dropped(name=str(items[position])[:60], reason="крок без назви", position=position)
            )
            continue
        ahead[name] -= 1
        kind = BY_NAME.get(name)
        if kind is None:
            dropped.append(Dropped(name=name, reason="кроку немає в словнику", position=position))
            continue
        if taken >= MAX_STEPS:
            dropped.append(
                Dropped(name=name, reason=f"понад стелю {MAX_STEPS} кроків", position=position)
            )
            continue
        allowed = PHASES.get(aim)
        if allowed is not None and kind.phase not in allowed:
            dropped.append(
                Dropped(
                    name=name,
                    reason=f"крок фази «{kind.phase}» — ця мета його не виконує",
                    position=position,
                )
            )
            continue
        if name in seen and not kind.repeatable:
            dropped.append(
                Dropped(name=name, reason="повтор кроку, який не повторюється", position=position)
            )
            continue
        missing = sorted(kind.needs - have)
        if missing:
            dropped.append(
                Dropped(
                    name=name,
                    reason="немає входу: " + ", ".join(missing),
                    position=position,
                )
            )
            continue
        overdue = _late(kind, readers, ahead)
        if overdue is not None:
            dropped.append(Dropped(name=name, reason=overdue, position=position))
            continue
        if not slot_known and kind.phase not in _BEFORE_SLOT_OK:
            dropped.append(Dropped(name=name, reason="полиця до слота", position=position))
            continue
        if kind.writes:
            if not writes_allowed:
                dropped.append(
                    Dropped(name=name, reason="запис без дозволу клієнта", position=position)
                )
                continue
            if writes >= MAX_WRITES:
                dropped.append(
                    Dropped(
                        name=name, reason=f"понад стелю {MAX_WRITES} записів", position=position
                    )
                )
                continue
            absent = [step for step in ESSENTIAL_BEFORE_WRITE if step not in seen]
            if absent:
                dropped.append(
                    Dropped(
                        name=name,
                        reason="запис до рішення: бракує " + ", ".join(absent),
                        position=position,
                    )
                )
                continue
            writes += 1
        if name in _WRITES_NEED_REREAD:
            pending_reread = True
        elif name == "cart.reread":
            pending_reread = False
        kept.append(Step(name=name, why=why, **_address(sent, addressable)))
        readers.append(kind)
        seen.add(name)
        taken += 1
        have |= kind.gives
        if "slot" in kind.gives:
            slot_known = True

    now = Carried(steps=taken, writes=writes, seen=frozenset(seen), pending_reread=pending_reread)
    return Plan(
        steps=tuple(kept),
        dropped=tuple(dropped),
        fatal=verdict(now, aim=aim) if whole else None,
        carried=now,
    )


def _read(item: Any) -> tuple[str | None, str, tuple[str, ...]]:
    if isinstance(item, str):
        return (item.strip() or None), "", ()
    if isinstance(item, Mapping):
        name = item.get("step") or item.get("name")
        why = item.get("why") or ""
        raw = item.get("labels")
        sent = tuple(
            str(label).strip()
            for label in (raw if isinstance(raw, list | tuple) else ())
            if str(label).strip()
        )
        return (str(name).strip() or None) if name else None, str(why), sent
    return None, "", ()


def _address(sent: tuple[str, ...], allowed: frozenset[str] | None) -> dict[str, tuple[str, ...]]:
    unique = tuple(dict.fromkeys(sent))
    if allowed is None:
        return {"labels": unique, "stray": ()}
    return {
        "labels": tuple(label for label in unique if label in allowed),
        "stray": tuple(label for label in unique if label not in allowed),
    }


def code_plan(*, source: str, writes: bool, budget: bool = False) -> Plan:
    if source == "pantry":
        cold = validate(
            ["pantry.name", "pantry.rhythm", "pantry.keeps", "pantry.aisle", "pantry.ask"],
            writes_allowed=False,
            known=facts_of(BEFORE_PANTRY),
            aim=Aim.PANTRY,
        )
        return Plan(
            steps=cold.steps,
            dropped=cold.dropped,
            fatal=cold.fatal,
            source="code",
            carried=cold.carried,
        )
    if source == "cart":
        names = [
            "place.cart",
            "place.decide",
            "slot.list",
            "slot.pick",
            "history.receipts",
            "history.orders",
            "history.model",
            "intents.compose",
            "shelf.search",
            "decide.pick",
            "decide.chain",
            "economy.settle",
        ]
    else:
        names = [
            "place.address",
            "place.delivery_types",
            "place.cart",
            "place.decide",
            "slot.list",
            "slot.pick",
            "history.receipts",
            "history.orders",
            "history.model",
            "intents.compose",
            "shelf.search",
            "shelf.by_article",
            "decide.pick",
            "decide.clarify",
            "decide.chain",
            "decide.loop",
            "economy.settle",
        ]
    if budget:
        names.append("economy.settle")
    if writes:
        names += ["cart.slot", "cart.write", "cart.reread", "cart.revalidate", "cart.reread"]
    plan = validate(names, writes_allowed=writes)
    return Plan(
        steps=plan.steps,
        dropped=plan.dropped,
        fatal=plan.fatal,
        source="code",
        carried=plan.carried,
    )


def repair_note(plan: Plan) -> str:
    if not plan.dropped and plan.fatal is None:
        return ""
    parts = [f"«{d.name}» (крок {d.position + 1}): {d.reason}" for d in plan.dropped]
    if plan.fatal:
        parts.append(f"план цілком: {plan.fatal}")
    return (
        "Не пройшли перевірку: "
        + "; ".join(parts)
        + ". Перескладай план, лишаючи лише кроки зі словника."
    )


@dataclass(frozen=True, slots=True)
class Report:

    total: int
    done: tuple[str, ...]
    later: tuple[str, ...]
    unneeded: tuple[str, ...]
    refused: tuple[Refused, ...]
    beyond: tuple[str, ...]
    did: tuple[Did, ...] = ()
    """Кроки, які зробили ФАЗИ поза виконавцем. Уже враховані у `done` і
    `beyond`; тут вони лежать заради ЧОМУ, яке інакше нікуди не доїде."""

    def of(self, kind: Refusal) -> tuple[Refused, ...]:
        return tuple(item for item in self.refused if item.kind is kind)

    @property
    def tag(self) -> str:
        return f"{len(self.done)}/{self.total}"

    @property
    def tone(self) -> Tone:
        if self.of(Refusal.RULE) or self.of(Refusal.BROKE) or self.of(Refusal.ORPHAN):
            return "warn"
        return "muted" if self.unneeded or self.of(Refusal.EMPTY) else "good"

    def summary(self) -> str:
        parts = [f"виконано {len(self.done)} з {self.total} кроків"]
        if self.later:
            parts.append(f"на «Оформити» {len(self.later)}")
        if self.unneeded:
            parts.append(f"не знадобилось {len(self.unneeded)}")
        parts += [f"{kind} {len(hit)}" for kind in Refusal if (hit := self.of(kind))]
        if self.beyond:
            parts.append(f"понад план {len(self.beyond)}")
        return "; ".join(parts)

    def args(self) -> dict[str, Any]:
        counts: dict[str, Any] = {
            "виконано": len(self.done),
            "на оформлення": len(self.later),
            "не знадобилось": len(self.unneeded),
            "понад план": len(self.beyond),
        }
        why_of: dict[str, list[str]] = {}
        for item in self.did:
            why_of.setdefault(item.name, []).append(item.why)
        beyond: list[str] = []
        for name in self.beyond:
            queue = why_of.get(name)
            beyond.append(f"{name} — {queue.pop(0)}" if queue else name)
        rows: dict[str, list[str]] = {
            "виконано": list(self.done),
            "на оформлення": list(self.later),
            "не знадобилось": list(self.unneeded),
            "понад план": beyond,
        }
        for kind in Refusal:
            hit = self.of(kind)
            counts[str(kind)] = len(hit)
            rows[str(kind)] = [f"{item.name} — {item.why}" for item in hit]
        return {**counts, "кроки": rows}


def report(
    planned: Sequence[str],
    *,
    done: Sequence[str],
    also: Iterable[str] = (),
    refused: Sequence[Refused] = (),
    did: Sequence[Did] = (),
) -> Report:
    left = Counter(done)
    left.update(item.name for item in did)
    left.update(name for name in dict.fromkeys(also) if name not in left)
    queues: dict[str, list[Refused]] = {}
    for item in refused:
        queues.setdefault(item.name, []).append(item)

    ran: list[str] = []
    later: list[str] = []
    unneeded: list[str] = []
    took: list[Refused] = []
    for name in planned:
        if left[name] > 0:
            left[name] -= 1
            ran.append(name)
        elif queues.get(name):
            took.append(queues[name].pop(0))
        elif name in NO_RUNNER:
            took.append(
                Refused(name=name, why="конвеєр цього кроку не виконує", kind=Refusal.ORPHAN)
            )
        elif BY_NAME[name].phase is Phase.CART:
            later.append(name)
        else:
            unneeded.append(name)
    took.extend(item for queue in queues.values() for item in queue)
    return Report(
        total=len(planned),
        done=tuple(ran),
        later=tuple(later),
        unneeded=tuple(unneeded),
        refused=tuple(took),
        beyond=tuple(sorted(left.elements())),
        did=tuple(did),
    )


def describe(plan: Plan) -> str:
    text = (
        " -> ".join(
            f"{step.name}[{len(step.labels)}]" if step.labels else step.name for step in plan.steps
        )
        if plan.steps
        else "порожньо"
    )
    stray = [label for step in plan.steps for label in step.stray]
    if stray:
        text += "; міток немає в коморі: " + ", ".join(stray)
    if plan.dropped:
        text += "; знято: " + ", ".join(f"{d.name} ({d.reason})" for d in plan.dropped)
    if plan.fatal:
        text += f"; не годиться: {plan.fatal}"
    return text


__all__ = [
    "BATCH_SCHEMA",
    "BEFORE_PANTRY",
    "BY_NAME",
    "CORE_AFTER_PLAN",
    "DECIDES",
    "ESSENTIAL_BEFORE_WRITE",
    "MAX_STEPS",
    "MAX_WRITES",
    "NO_RUNNER",
    "PHASES",
    "PLAN_SCHEMA",
    "STEPS",
    "Aim",
    "Carried",
    "Did",
    "Dropped",
    "Phase",
    "Plan",
    "Refusal",
    "Refused",
    "Report",
    "Step",
    "StepKind",
    "code_plan",
    "describe",
    "facts_of",
    "repair_note",
    "report",
    "validate",
    "verdict",
]
