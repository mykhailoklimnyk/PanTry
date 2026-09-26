from __future__ import annotations

import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from komora.core.facts import Facts
from komora.core.plan import BY_NAME, Aim, Carried, Did, Plan, Refusal, Refused, validate
from komora.core.trace import Tone
from komora.logging import get_logger

log = get_logger(__name__)

BEYOND = "понад план: інваріант"


class Trace(Protocol):

    def add(
        self,
        step_id: str,
        tool: str,
        args: dict[str, Any],
        summary: str,
        *,
        duration_ms: int | None = None,
        calls: int | None = None,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
        decision: str | None = None,
        tag: str | None = None,
        tag_tone: Tone = "muted",
        prompt: str | None = None,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class Made:

    facts: Mapping[str, Any] = field(default_factory=dict)
    args: dict[str, Any] = field(default_factory=dict)
    summary: str = ""
    decision: str | None = None
    tag: str | None = None
    tag_tone: Tone = "muted"
    tool: str = ""
    prompt: str | None = None
    absent: str = ""
    absent_kind: Refusal = Refusal.EMPTY


Work = Callable[[Mapping[str, Any]], Awaitable[Made]]


class Executor:

    def __init__(
        self,
        facts: Facts,
        *,
        plan: Plan,
        trace: Trace,
        writes_allowed: bool,
        aim: Aim = Aim.BASKET,
        fatal: tuple[type[BaseException], ...] = (),
        carried: Carried | None = None,
        meter: Any = None,
    ) -> None:
        self.meter = meter
        self.facts = facts
        self.trace = trace
        self.writes_allowed = writes_allowed
        self.aim = aim
        self.fatal = fatal
        self.planned: set[str] = set(plan.names())
        self.carried: Carried = carried or Carried()
        self.done: list[str] = []
        self.refused: list[Refused] = []
        self.did: list[Did] = []

    def wants(self, name: str) -> bool:
        return name in self.planned

    def credit(self, name: str, why: str) -> None:
        self.did.append(Did(name=name, why=why))

    def move(self, change: str, name: str) -> None:
        if change == "add":
            self.planned.add(name)
        else:
            self.planned.discard(name)

    def adopt(self, plan: Plan) -> None:
        self.planned |= set(plan.names())

    async def run(
        self,
        name: str,
        work: Work,
        *,
        step_id: str,
        tool: str,
        beyond: bool = False,
    ) -> Made | None:
        return await self.run_all([name], work, step_id=step_id, tool=tool, beyond=beyond)

    async def run_all(
        self,
        names: Sequence[str],
        work: Work,
        *,
        step_id: str,
        tool: str,
        beyond: bool = False,
    ) -> Made | None:
        if not beyond and any(not self.wants(name) for name in names):
            return None
        kinds = [BY_NAME[name] for name in names]
        checked = validate(
            list(names),
            writes_allowed=self.writes_allowed,
            known=self.facts.names(),
            carried=self.carried,
            aim=self.aim,
            whole=False,
        )
        if checked.dropped:
            cut = checked.dropped[0]
            return self._refuse(cut.name, step_id, tool, cut.reason, Refusal.RULE)

        promised: set[str] = set().union(*(kind.gives for kind in kinds))
        needs: set[str] = set().union(*(kind.needs for kind in kinds))
        bound = self.facts.take(name for name in needs if self.facts.origin(name) is not None)
        started = time.perf_counter()
        before = self._counted()
        try:
            made = await work(bound)
        except self.fatal:
            raise
        except Exception as exc:
            log.warning("executor.step_failed", step=names[0], error=str(exc)[:160])
            return self._refuse(
                names[0], step_id, tool, f"збій кроку ({str(exc)[:60]})", Refusal.BROKE
            )
        spent = int((time.perf_counter() - started) * 1000)
        calls, tokens_in, tokens_out = self._since(before)

        if made.absent:
            return self._refuse(
                names[0],
                step_id,
                tool,
                made.absent,
                made.absent_kind,
                tone=made.tag_tone,
                args=made.args,
                summary=made.absent,
            )
        extra = sorted(set(made.facts) - promised)
        if extra:
            return self._refuse(
                names[0],
                step_id,
                tool,
                "дав факт поза обіцянкою: " + ", ".join(extra),
                Refusal.BROKE,
            )
        missed = sorted(promised - set(made.facts))
        if missed:
            return self._refuse(
                names[0], step_id, tool, "не дав обіцяного: " + ", ".join(missed), Refusal.BROKE
            )

        author = {give: kind.name for kind in kinds for give in kind.gives}
        gained = {
            key: self.facts.put(key, value, step=author[key]).told()
            for key, value in sorted(made.facts.items())
        }
        self.carried = checked.carried
        self.done.extend(names)
        self.trace.add(
            step_id,
            made.tool or tool,
            {**made.args, "крок": ", ".join(names), "входи": sorted(needs), "дав": gained},
            (f"{BEYOND}; {made.summary}" if beyond else made.summary),
            duration_ms=spent,
            calls=calls,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            decision=made.decision,
            tag=made.tag,
            tag_tone=made.tag_tone,
            prompt=made.prompt,
        )
        return made

    def _counted(self) -> tuple[int, int, int] | None:
        meter = self.meter
        if meter is None:
            return None
        return (meter.calls, meter.input_tokens, meter.output_tokens)

    def _since(
        self, before: tuple[int, int, int] | None
    ) -> tuple[int | None, int | None, int | None]:
        after = self._counted()
        if before is None or after is None:
            return (None, None, None)
        return (after[0] - before[0], after[1] - before[1], after[2] - before[2])

    async def settle(self, reread: Work, *, step_id: str, tool: str) -> Made | None:
        if not self.carried.pending_reread:
            return None
        return await self.run("cart.reread", reread, step_id=step_id, tool=tool, beyond=True)

    def _refuse(
        self,
        name: str,
        step_id: str,
        tool: str,
        why: str,
        kind: Refusal,
        *,
        tone: Tone = "warn",
        args: dict[str, Any] | None = None,
        summary: str | None = None,
    ) -> None:
        self.refused.append(Refused(name=name, why=why, kind=kind))
        log.info("executor.step_refused", step=name, reason=why, kind=str(kind))
        self.trace.add(
            step_id,
            tool,
            {**(args or {}), "крок": name, "причина": why, "уже відомо": self.facts.names()},
            summary if summary is not None else f"крок «{name}» не виконано: {why}",
            tag="не виконано",
            tag_tone=tone,
        )
        return None


__all__ = ["BEYOND", "Executor", "Made", "Trace", "Work"]
