from __future__ import annotations

import hashlib
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import partial
from typing import Any

from komora.agent.aisle import intent_aisles, known_aisles
from komora.agent.basket import Receipts, Tracer, intent_keeps, plural, stitch, tell_turn
from komora.agent.executor import Executor
from komora.agent.llm import Meter
from komora.agent.plan import describe_tools, plan_batch, plan_run
from komora.agent.probe import Probe
from komora.agent.sanity import intent_sense
from komora.agent.spine import Ground as Soil
from komora.agent.spine import Spun, spin
from komora.agent.steps.ground import Ground
from komora.agent.steps.pantry import Home
from komora.api.schemas import Pantry, TraceStep
from komora.config import Settings
from komora.core.facts import BEFORE, Facts
from komora.core.goal import Goal, Row, pantry_goal
from komora.core.location import Location
from komora.core.plan import BEFORE_PANTRY, Aim, Carried, Plan, describe, facts_of
from komora.core.said import Said
from komora.core.spine import Halt
from komora.db.pool import DictPool
from komora.logging import get_logger
from komora.mcp.client import SilpoMCP

log = get_logger(__name__)

NOTHING_MISSING = "нічого не бракувало"

NOTHING_YET = "уточнювати ще нічого: комора поки порожня"

NOTHING_NEW = "нічого не змінилось з минулого разу"

NO_MODEL = "моделі немає — комора лишається як прочиталась"

NOTHING_FOUND = "нічого нового не знайшлось"

_SEEN: dict[str, str] = {}

WORKS: dict[str, tuple[str, str, str]] = {
    "pantry.name": ("name", "step-pantry-name", "model"),
    "pantry.rhythm": ("rhythm", "step-pantry-rhythm", "model"),
    "pantry.keeps": ("keeps", "step-pantry-keeps", "model"),
    "pantry.aisle": ("aisle", "step-pantry-aisle", "model"),
    "pantry.shelf": ("shelf", "step-pantry-shelf", "silpo_find_products_batch"),
    "pantry.ask": ("ask", "step-pantry-ask", "model"),
}

ADDRESSED = frozenset(
    {"pantry.rhythm", "pantry.keeps", "pantry.aisle", "pantry.shelf", "pantry.ask"}
)

ROW_READERS = frozenset({"pantry.shelf", "pantry.ask"})


def forget_loop(account: str = "") -> None:
    if account:
        _SEEN.pop(account, None)
    else:
        _SEEN.clear()


@dataclass(frozen=True, slots=True)
class Refined:

    pantry: Pantry
    note: str
    goal: Goal | None = None
    tokens: int = 0
    probes: tuple[Probe, ...] = ()

    @property
    def ran(self) -> bool:
        return self.goal is not None


def _mark(read: Receipts, said: Said, drawn: Pantry) -> str:
    lacks = "".join(
        f"{row.id}{int(row.named)}{int(bool(row.sanity))}{int(row.ask)}" for row in drawn.items
    )
    words = f"{said.source}{len(said.marks)}{len(said.cycles)}{len(said.listed)}{len(said.hidden)}"
    return hashlib.sha256(f"{read.count}|{read.orders}|{words}|{lacks}".encode()).hexdigest()


def _tell_loop(trace: Tracer, spun: Spun) -> None:
    trace.add(
        "step-stop",
        "code",
        {
            "причина": spun.reason.name.lower(),
            "обертів": len(spun.turns),
            "викликів моделі": spun.calls,
            "токенів": spun.tokens,
            "тривалість петлі, мс": spun.duration_ms,
        },
        f"петля спинилась: {spun.reason.value} "
        f"({len(spun.turns)} {plural(len(spun.turns), 'оберт', 'оберти', 'обертів')}, "
        f"{spun.duration_ms / 1000:.1f} с разом)",
        duration_ms=None,
        tag="мета" if spun.reason is Halt.DONE else spun.reason.name.lower(),
        tag_tone="good" if spun.reason is Halt.DONE else "warn",
    )


def _rows_of(pantry: Pantry) -> list[Row]:
    return [
        Row(
            label=row.label,
            named=row.named,
            counted=row.cycle_days is not None,
            explained=bool(row.sanity),
            asks=row.ask,
        )
        for row in pantry.items
        if row.source == "receipts"
    ]


async def refine(
    mcp: SilpoMCP,
    *,
    drawn: Pantry,
    read: Receipts,
    said: Said,
    llm: Any = None,
    settings: Settings | None = None,
    now: datetime | None = None,
    place: Location | None = None,
    pool: DictPool | None = None,
    account: str = "",
    on_step: Callable[[TraceStep], None] | None = None,
    cold: bool = False,
    continuing: bool = False,
    batches: int | None = None,
    answered: Mapping[str, int] | None = None,
    more: bool = False,
    seq_from: int = 0,
) -> Refined:
    if llm is None:
        return _quiet(drawn, NO_MODEL, {"модель": "немає"}, on_step)
    mark = _mark(read, said, drawn)
    if account and not cold and _SEEN.get(account) == mark:
        return _quiet(drawn, NOTHING_NEW, {"відбиток": mark[:12]}, on_step)

    trace = Tracer(on_step, start=seq_from)
    if answered:
        trace.add(
            "step-pantry-heard",
            "code",
            {
                "відповідей": len(answered),
                **{label: f"{days} дн" for label, days in answered.items()},
            },
            f"почув гостя: {len(answered)} "
            f"{plural(len(answered), 'відповідь', 'відповіді', 'відповідей')}",
            tag=f"{len(answered)} відп.",
            tag_tone="good",
        )
    facts = Facts()
    facts.put("history", read.history, step=BEFORE)
    facts.put("pantry", drawn.items, step=BEFORE)
    ground = Ground(
        mcp=mcp,
        cfg=settings or Settings(),
        moment=now or datetime.now(UTC),
        facts=facts,
        trace=trace,
        pool=pool,
        account=account,
        llm=llm,
        batches=batches,
    )
    home = Home(
        ground, said=said, read=read, drawn=drawn, place=place, cold=cold, continuing=continuing
    )
    tools = await describe_tools(mcp)
    shape = await _shape(read, drawn, pool=pool)
    goal_text = "доведи стан дому: кожен рядок каже число або речення"
    runner = Executor(
        facts,
        plan=Plan(steps=()),
        trace=trace,
        writes_allowed=False,
        aim=Aim.PANTRY,
        meter=Meter.of(llm),
    )

    def _closed() -> bool:
        return bool(answered) and not more

    def _duties() -> tuple[str, ...]:
        judged = pantry_goal(_rows_of(home.pantry), questions=_questions(facts), closed=_closed())
        return tuple(duty.why or duty.name for duty in judged.unmet)

    outside: list[str] = []
    unread: list[str] = []

    async def _turn(batch: Plan) -> Carried:
        runner.adopt(batch)

        async def _draw() -> None:
            await runner.run(
                "pantry.draw", home.draw, step_id="step-pantry-draw", tool="code", beyond=True
            )

        dirty = drawn_now = False
        for step in batch.steps:
            entry = WORKS.get(step.name)
            if entry is None:
                outside.append(step.name)
                continue
            method, step_id, tool = entry
            if step.name in ROW_READERS and dirty:
                await _draw()
                dirty, drawn_now = False, True
            work = getattr(home, method)
            if step.name in ADDRESSED:
                work = partial(work, labels=step.labels, stray=step.stray)
            elif step.labels or step.stray:
                unread.append(step.name)
            made = await runner.run(step.name, work, step_id=step_id, tool=tool)
            dirty = dirty or (made is not None and step.name not in ROW_READERS)
        if dirty or not drawn_now:
            await _draw()
        return runner.carried

    async def _ask(soil: Soil):
        rows = list(home.pantry.items)
        return await plan_batch(
            llm,
            soil,
            source="pantry",
            writes=False,
            budget=False,
            tools=tools,
            goal=goal_text,
            aim=Aim.PANTRY,
            state={
                **(await _shape(read, home.pantry, pool=pool)),
                "мовчазні рядки (мітки)": [
                    row.label for row in rows if row.named and row.cycle_days is None
                ],
                "фасовка з полиці відома": len(home.packaging),
            },
            labels=[row.label for row in rows if row.named],
        )

    turns = (settings or Settings()).pantry_turns
    source = "code"
    tokens = 0
    if turns > 0:
        spun = await spin(
            plan=_ask,
            run=_turn,
            facts=facts,
            duties=_duties,
            verdict=lambda _carried: None,
            waiting=lambda: bool(home.probes),
            refused=lambda: tuple(f"{item.name}: {item.why}" for item in runner.refused),
            ceiling=turns,
            on_turn=lambda turn: tell_turn(trace, turn),
        )
        _tell_loop(trace, spun)
        tokens = spun.tokens
        if any(turn.planned for turn in spun.turns):
            source = "model"
    else:
        planned = await plan_run(
            llm,
            source="pantry",
            writes=False,
            budget=False,
            known=facts_of(BEFORE_PANTRY),
            tools=tools,
            goal=goal_text,
            aim=Aim.PANTRY,
            state=shape,
        )
        trace.add(
            "step-pantry-plan",
            "model",
            {"кроків": len(planned.plan.steps), "спроб": planned.attempts},
            f"{planned.note}: {describe(planned.plan)}",
            duration_ms=planned.duration_ms,
            prompt=planned.prompt,
        )
        await _turn(planned.plan)
        source = planned.plan.source
        tokens = planned.tokens
    goal = pantry_goal(_rows_of(home.pantry), questions=_questions(facts), closed=_closed())
    trace.add(
        "step-pantry-goal",
        "code",
        {
            **goal.told(),
            **({"поза набором": outside} if outside else {}),
            **({"перелік міток не читають": unread} if unread else {}),
        },
        goal.note(),
        tag="мета" if goal.ok else "не все",
        tag_tone="good" if goal.ok else "warn",
    )
    if account and not home.probes:
        _SEEN[account] = _mark(read, said, home.pantry)
    log.info(
        "pantry.loop",
        steps=len(runner.done),
        refused=len(runner.refused),
        met=goal.ok,
        source=source,
    )
    return Refined(
        pantry=home.pantry.model_copy(
            update={
                "trace": stitch(
                    *(() if seq_from else (home.pantry.trace,)),
                    trace.steps,
                    start=seq_from + 1,
                )
            }
        ),
        note=_note(runner.done, drawn, home.pantry),
        goal=goal,
        tokens=tokens,
        probes=tuple(home.probes),
    )


async def _shape(read: Receipts, drawn: Pantry, *, pool: DictPool | None) -> dict[str, int]:
    rows = _rows_of(drawn)
    labels = sorted({row.label for row in drawn.items if row.named})
    judged = await intent_sense(None, labels, pool=pool)
    kept = await intent_keeps(None, labels, pool=pool)
    shelved = await intent_aisles(None, labels, await known_aisles(pool), pool=pool)
    return {
        "рядків": len(rows),
        "без мітки виду": sum(1 for row in rows if not row.named),
        "міток виду": len(labels),
        "без числа і без речення": sum(1 for row in rows if not row.counted and not row.explained),
        "без вироку про ритм": len(labels) - len(judged),
        "без стелі зберігання": len(labels) - len(kept),
        "без відділу": len(labels) - len(shelved),
        "просять слова гостя": sum(1 for row in rows if row.asks),
        "дописано руками": sum(1 for row in drawn.items if row.source == "manual"),
        "чеків прочитано": read.count,
    }


def _quiet(
    drawn: Pantry,
    note: str,
    args: dict[str, Any],
    on_step: Callable[[TraceStep], None] | None = None,
) -> Refined:
    told = Tracer(on_step)
    told.add("step-pantry-loop", "code", args, note)
    return Refined(
        pantry=drawn.model_copy(update={"trace": stitch(drawn.trace, told.steps)}), note=note
    )


def _questions(facts: Facts) -> list[str]:
    return list(facts.get("questions")) if "questions" in facts else []


def _changed(before: Pantry, after: Pantry) -> int:
    was = {row.id: (row.label, row.sanity, row.cycle_days, row.ask) for row in before.items}
    now = {row.id: (row.label, row.sanity, row.cycle_days, row.ask) for row in after.items}
    return sum(1 for key in was.keys() | now.keys() if was.get(key) != now.get(key))


def _note(done: list[str], before: Pantry, after: Pantry) -> str:
    if not before.items and not after.items:
        return NOTHING_YET
    if not [name for name in done if name != "pantry.draw"]:
        return NOTHING_MISSING
    rows = _changed(before, after)
    return f"уточнено: {rows}" if rows else NOTHING_FOUND


__all__ = [
    "NOTHING_FOUND",
    "NOTHING_MISSING",
    "NOTHING_NEW",
    "NOTHING_YET",
    "NO_MODEL",
    "Refined",
    "forget_loop",
    "refine",
]
