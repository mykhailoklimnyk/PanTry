from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from komora.core.plan import BY_NAME

UNDERSTAND_QUESTIONS = 2

MIN_OPTIONS = 2
MAX_OPTIONS = 4

ANSWER_WAIT_S = 25.0

UNDERSTAND_ADD = 6

PLAN_GATED = frozenset({"shelf.by_article", "decide.loop"})

_CHANGE_ITEM = {
    "type": "object",
    "properties": {"intent": {"type": "string"}, "why": {"type": ["string", "null"]}},
    "required": ["intent"],
}

UNDERSTAND_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "questions": {
            "type": "array",
            "salvage": True,
            "items": {
                "type": "object",
                "properties": {
                    "ask": {"type": "string"},
                    "why": {"type": ["string", "null"]},
                    "options": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "label": {"type": "string"},
                                "intents": {
                                    "type": ["array", "null"],
                                    "items": {"type": "string"},
                                },
                                "style": {
                                    "type": ["string", "null"],
                                    "enum": ["cooking", "ready", None],
                                },
                            },
                            "required": ["label"],
                        },
                    },
                },
                "required": ["ask", "options"],
            },
        },
        "cut": {"type": "array", "salvage": True, "items": {"type": "string"}},
        "add": {"type": "array", "salvage": True, "items": _CHANGE_ITEM},
        "drop": {"type": "array", "salvage": True, "items": _CHANGE_ITEM},
        "plan": {
            "type": "array",
            "salvage": True,
            "items": {
                "type": "object",
                "properties": {
                    "change": {"type": "string", "enum": ["add", "skip"]},
                    "step": {"type": "string"},
                    "why": {"type": ["string", "null"]},
                },
                "required": ["change", "step"],
            },
        },
    },
    "required": ["questions", "add", "drop"],
}


@dataclass(frozen=True, slots=True)
class Option:

    id: str
    label: str
    intents: tuple[str, ...] = ()
    style: Literal["cooking", "ready"] | None = None


@dataclass(frozen=True, slots=True)
class Question:

    id: str
    ask: str
    why: str
    options: tuple[Option, ...]

    def option(self, option_id: str) -> Option | None:
        return next((item for item in self.options if item.id == option_id), None)


@dataclass(frozen=True, slots=True)
class Change:

    intent: str
    why: str


@dataclass(frozen=True, slots=True)
class PlanChange:

    change: str
    step: str
    why: str


@dataclass(frozen=True, slots=True)
class Understanding:

    questions: tuple[Question, ...] = ()
    cut: tuple[str, ...] = ()
    ignored: tuple[str, ...] = ()
    added: tuple[Change, ...] = ()
    dropped: tuple[Change, ...] = ()
    plan: tuple[PlanChange, ...] = ()
    thrown: tuple[str, ...] = ()
    model: str = ""
    duration_ms: int = 0
    tokens: int = 0
    failure: str = ""

    @property
    def touched(self) -> bool:
        return bool(self.questions or self.added or self.dropped or self.plan or self.cut)

    def note(self) -> str:
        if self.failure:
            return f"етап розуміння не спрацював ({self.failure})"
        parts = []
        if self.cut:
            said = f"переріз тексту: {len(self.cut)}"
            parts.append(said + (f", не взяв {len(self.ignored)}" if self.ignored else ""))
        if self.questions:
            parts.append(f"питаю {len(self.questions)}")
        if self.added:
            parts.append(f"докинув {len(self.added)}")
        if self.dropped:
            parts.append(f"зняв {len(self.dropped)}")
        if self.plan:
            parts.append(f"правок плану {len(self.plan)}")
        if not parts:
            return "нічого не змінив: задача зрозуміла як є"
        return "; ".join(parts)


def _norm(text: str) -> str:
    return " ".join(str(text).split()).casefold()


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def uncovered(cut: Sequence[str], *, said: Sequence[str]) -> tuple[str, ...]:
    words = {word for line in cut for word in _norm(line).split()}
    return tuple(
        piece for piece in said if all(word not in words for word in _norm(piece).split())
    )


def read(
    data: Mapping[str, Any],
    *,
    intents: Sequence[str],
    protected: Sequence[str],
) -> Understanding:
    thrown: list[str] = []

    questions: list[Question] = []
    for index, raw in enumerate(data.get("questions") or []):
        if not isinstance(raw, Mapping):
            thrown.append(f"питання {index + 1}: не об'єкт")
            continue
        ask = _clean(raw.get("ask"))
        options: list[Option] = []
        seen: set[str] = set()
        for position, item in enumerate(raw.get("options") or []):
            if not isinstance(item, Mapping):
                continue
            label = _clean(item.get("label"))
            key = _norm(label)
            if not label or key in seen:
                continue
            seen.add(key)
            said = _clean(item.get("style")).casefold()
            style: Literal["cooking", "ready"] | None = (
                "cooking" if said == "cooking" else "ready" if said == "ready" else None
            )
            options.append(
                Option(
                    id=f"o{position + 1}",
                    label=label,
                    intents=tuple(
                        name for value in (item.get("intents") or ()) if (name := _clean(value))
                    ),
                    style=style,
                )
            )
        if not ask:
            thrown.append(f"питання {index + 1}: без тексту")
            continue
        if len(options) < MIN_OPTIONS:
            thrown.append(f"питання «{ask[:40]}»: варіантів менше за {MIN_OPTIONS}")
            continue
        if len(questions) >= UNDERSTAND_QUESTIONS:
            thrown.append(f"питання «{ask[:40]}»: понад стелю {UNDERSTAND_QUESTIONS}")
            continue
        if len(options) > MAX_OPTIONS:
            thrown.append(f"питання «{ask[:40]}»: варіантів {len(options)}, лишаю {MAX_OPTIONS}")
        questions.append(
            Question(
                id=f"q{len(questions) + 1}",
                ask=ask,
                why=_clean(raw.get("why")),
                options=tuple(options[:MAX_OPTIONS]),
            )
        )

    known = {_norm(intent): intent for intent in intents}
    untouchable = {_norm(intent) for intent in protected}

    cut: tuple[str, ...] = ()
    ignored: tuple[str, ...] = ()
    reading = [name for value in (data.get("cut") or ()) if (name := _clean(value))]
    if reading:
        room = sum(len(_norm(piece).split()) for piece in protected)
        missed = uncovered(reading, said=protected)
        if room and len(reading) > room:
            thrown.append(f"переріз тексту: намірів {len(reading)} при {room} словах гостя")
        elif protected and len(missed) == len(protected):
            thrown.append("переріз тексту: не взяв із тексту нічого")
        else:
            cut, ignored = tuple(reading), missed

    added: list[Change] = []
    seen_names = set(known)
    for raw in data.get("add") or []:
        if not isinstance(raw, Mapping):
            continue
        intent = _clean(raw.get("intent"))
        key = _norm(intent)
        if not intent or key in seen_names:
            continue
        if len(added) >= UNDERSTAND_ADD:
            thrown.append(f"«{intent}»: понад стелю {UNDERSTAND_ADD} доданих")
            continue
        seen_names.add(key)
        added.append(Change(intent=intent, why=_clean(raw.get("why"))))

    dropped: list[Change] = []
    gone: set[str] = set()
    for raw in data.get("drop") or []:
        if not isinstance(raw, Mapping):
            continue
        key = _norm(_clean(raw.get("intent")))
        if key in untouchable:
            thrown.append(f"«{known.get(key, key)}»: це слово гостя, зняти не можна")
            continue
        if key not in known or key in gone:
            continue
        gone.add(key)
        dropped.append(Change(intent=known[key], why=_clean(raw.get("why"))))

    plan: list[PlanChange] = []
    for raw in data.get("plan") or []:
        if not isinstance(raw, Mapping):
            continue
        step = _clean(raw.get("step"))
        change = _clean(raw.get("change")).casefold()
        if change not in {"add", "skip"}:
            thrown.append(f"крок «{step}»: невідома зміна «{change}»")
            continue
        if step not in BY_NAME:
            thrown.append(f"крок «{step}»: такого немає в словнику")
            continue
        if step not in PLAN_GATED:
            thrown.append(f"крок «{step}»: виконавець його планом не гейтить")
            continue
        if any(item.step == step for item in plan):
            continue
        plan.append(PlanChange(change=change, step=step, why=_clean(raw.get("why"))))

    return Understanding(
        questions=tuple(questions),
        cut=cut,
        ignored=ignored,
        added=tuple(added),
        dropped=tuple(dropped),
        plan=tuple(plan),
        thrown=tuple(thrown),
    )


def waited_note(question: Question, seconds: float) -> str:
    return f"не дочекався відповіді на «{question.ask}» за {seconds:.0f} с — збираю без неї"


__all__ = [
    "ANSWER_WAIT_S",
    "MAX_OPTIONS",
    "MIN_OPTIONS",
    "PLAN_GATED",
    "UNDERSTAND_ADD",
    "UNDERSTAND_QUESTIONS",
    "UNDERSTAND_SCHEMA",
    "Change",
    "Option",
    "PlanChange",
    "Question",
    "Understanding",
    "read",
    "uncovered",
    "waited_note",
]
