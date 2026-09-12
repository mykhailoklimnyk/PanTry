from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from komora.core.facts import Facts
from komora.core.plan import Carried, Plan, Step
from komora.core.spine import BATCH_MAX, MAX_TURNS, Halt, Progress, halt, trim
from komora.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class Ground:

    turn: int
    facts: Mapping[str, str] = field(default_factory=dict)
    unmet: tuple[str, ...] = ()
    cut: tuple[str, ...] = ()
    dropped: tuple[str, ...] = ()
    refused: tuple[str, ...] = ()
    left: int = 0
    done: tuple[str, ...] = ()

    def told(self) -> dict[str, Any]:
        said: dict[str, Any] = {"оберт": self.turn, "обертів лишилось": self.left}
        if self.facts:
            said["здобуто"] = dict(self.facts)
        if self.done:
            said["кроки вже зроблені"] = list(self.done)
        if self.unmet:
            said["ще винні"] = list(self.unmet)
        if self.cut:
            said["не влізло в пачку"] = list(self.cut)
        if self.dropped:
            said["зрізано валідатором"] = list(self.dropped)
        if self.refused:
            said["відкинуто виконавцем"] = list(self.refused)
        return said


@dataclass(frozen=True, slots=True)
class Batch:

    plan: Plan
    stop: bool = False
    why: str = ""
    tokens: int = 0


@dataclass(frozen=True, slots=True)
class Turn:

    number: int
    planned: tuple[str, ...]
    executed: tuple[str, ...]
    cut: tuple[str, ...]
    dropped: tuple[str, ...]
    learned: tuple[str, ...]
    said_stop: bool
    why: str
    tokens: int


@dataclass(frozen=True, slots=True)
class Spun:

    turns: tuple[Turn, ...]
    reason: Halt
    tokens: int
    duration_ms: int

    @property
    def calls(self) -> int:
        return len(self.turns)


type PlanBatch = Callable[[Ground], Awaitable[Batch]]
type RunBatch = Callable[[Plan], Awaitable[Carried]]
type Duties = Callable[[], tuple[str, ...]]
type Verdict = Callable[[Carried], str | None]


def _snapshot(facts: Facts) -> dict[str, tuple[int, Any]]:
    return {
        name: (origin.size, facts.get(name))
        for name in facts.names()
        if (origin := facts.origin(name))
    }


def _learned(before: Mapping[str, tuple[int, Any]], facts: Facts) -> tuple[str, ...]:
    changed = []
    for name in facts.names():
        origin = facts.origin(name)
        if origin is None:
            continue
        was = before.get(name)
        if was is None or was[0] != origin.size or was[1] != origin.value:
            changed.append(name)
    return tuple(sorted(changed))


async def spin(
    *,
    plan: PlanBatch,
    run: RunBatch,
    facts: Facts,
    duties: Duties,
    verdict: Verdict,
    ceiling: int = MAX_TURNS,
    cap: int = BATCH_MAX,
    obey_stop: bool = False,
    waiting: Callable[[], bool] | None = None,
    refused: Callable[[], tuple[str, ...]] | None = None,
    on_turn: Callable[[Turn], None] | None = None,
) -> Spun:
    started = time.perf_counter()
    turns: list[Turn] = []
    carried = Carried()
    tokens = 0
    idle = 0
    said_stop = False
    why = ""
    broken = False
    cut_names: tuple[str, ...] = ()
    dropped_names: tuple[str, ...] = ()

    while True:
        stop = halt(
            Progress(
                turn=len(turns),
                said_stop=said_stop,
                unmet=duties(),
                fatal=verdict(carried),
                broken=broken,
                idle=idle,
                waiting=bool(waiting and waiting()),
            ),
            ceiling=ceiling,
            obey_stop=obey_stop,
        )
        if stop is not None:
            log.info(
                "spine.halt",
                reason=stop.name.lower(),
                turns=len(turns),
                tokens=tokens,
                why=why[:120],
            )
            return Spun(
                turns=tuple(turns),
                reason=stop,
                tokens=tokens,
                duration_ms=int((time.perf_counter() - started) * 1000),
            )

        number = len(turns) + 1
        before = _snapshot(facts)
        ground = Ground(
            turn=number,
            refused=tuple(refused()) if refused else (),
            facts=facts.ground(),
            unmet=duties(),
            cut=cut_names,
            dropped=dropped_names,
            left=max(0, ceiling - len(turns)),
            done=tuple(sorted(carried.seen)),
        )
        batch = await plan(ground)
        tokens += batch.tokens
        said_stop = batch.stop
        why = batch.why
        broken = not batch.plan.ok

        kept, over = trim(batch.plan.steps, cap=cap)
        cut_names = tuple(step.name for step in over)
        dropped_names = tuple(f"{item.name}: {item.reason}" for item in batch.plan.dropped)

        executed: tuple[str, ...] = ()
        if kept and not broken:
            carried = await run(_only(batch.plan, kept))
            executed = tuple(step.name for step in kept)

        learned = _learned(before, facts)
        idle = 0 if learned else idle + 1
        turn = Turn(
            number=number,
            planned=batch.plan.names(),
            executed=executed,
            cut=cut_names,
            dropped=dropped_names,
            learned=learned,
            said_stop=said_stop,
            why=why,
            tokens=batch.tokens,
        )
        turns.append(turn)
        if on_turn is not None:
            on_turn(turn)


def _only(plan: Plan, steps: tuple[Step, ...]) -> Plan:
    return Plan(
        steps=steps,
        dropped=plan.dropped,
        fatal=plan.fatal,
        source=plan.source,
        carried=plan.carried,
    )


__all__ = ["Batch", "Ground", "PlanBatch", "RunBatch", "Spun", "Turn", "spin"]
