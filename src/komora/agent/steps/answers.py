from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field, replace

from komora.agent.basket import same_kind
from komora.agent.steps.ground import Ground
from komora.agent.understand import answered_note
from komora.core.occasion import EventStyle, Occasion
from komora.core.understanding import ANSWER_WAIT_S, Question, waited_note


@dataclass(slots=True)
class Heard:

    ground: Ground
    answer_of: Callable[[str, float], Awaitable[str | None]] | None
    questions: Sequence[Question] = ()
    said: list[str] = field(default_factory=list, init=False)
    intents: dict[str, str] = field(default_factory=dict, init=False)
    occasion: Occasion | None = field(default=None, init=False)

    async def wait(self, occasion: Occasion, intents: list[str]) -> Occasion:
        if self.questions and self.answer_of is not None:
            chosen = await asyncio.gather(
                *(self.answer_of(question.id, ANSWER_WAIT_S) for question in self.questions)
            )
            for question, picked in zip(self.questions, chosen, strict=True):
                option = question.option(picked) if picked else None
                if option is None:
                    self.ground.trace.add(
                        "step-answer",
                        "agent.understand",
                        {"питання": question.ask, "стеля, с": int(ANSWER_WAIT_S)},
                        waited_note(question, ANSWER_WAIT_S),
                        tag="без відповіді",
                        tag_tone="muted",
                    )
                    continue
                self.said.append(f"{question.ask} — {option.label}")
                if option.style is not None:
                    occasion = replace(occasion, style=EventStyle(option.style))
                for name in option.intents:
                    if any(same_kind(name, known) for known in intents):
                        continue
                    intents.append(name)
                    self.intents[name] = f"з твоєї відповіді: {option.label}"
                self.ground.trace.add(
                    "step-answer",
                    "agent.understand",
                    {"питання": question.ask, "варіант": option.label},
                    answered_note(question, option.label)
                    + (
                        f"; беру під це {len(self.intents)} нових намірів"
                        if self.intents
                        else "; складу намірів це не міняє, але міняє вибір товару"
                    ),
                    decision="слово гостя важить більше за наш здогад про задачу",
                    tag="відповідь",
                    tag_tone="good",
                )
        self.occasion = occasion
        return occasion


__all__ = ["Heard"]
