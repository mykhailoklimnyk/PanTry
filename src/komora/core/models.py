from __future__ import annotations

from dataclasses import dataclass

MISTRAL_LARGE = "mistral.mistral-large-3-675b-instruct"
LUNA = "gpt-5.6-luna"


@dataclass(frozen=True, slots=True)
class Recommended:

    id: str
    label: str
    note: str
    needs_key: bool
    fast_by_default: bool


RECOMMENDED: tuple[Recommended, ...] = (
    Recommended(
        id=MISTRAL_LARGE,
        label="Mistral Large 3",
        note="повільніше, зате безкоштовно — платить проєкт",
        needs_key=False,
        fast_by_default=True,
    ),
    Recommended(
        id=LUNA,
        label="GPT-5.6 Luna",
        note="швидше, але з твоїм ключем OpenAI",
        needs_key=True,
        fast_by_default=True,
    ),
)

_BY_ID = {row.id: row for row in RECOMMENDED}


def needs_guest_key(model: str) -> bool:
    row = _BY_ID.get(model)
    return row is not None and row.needs_key


def payer_of(model: str) -> str:
    return "guest" if needs_guest_key(model) else "project"


def supports_fast(model: str) -> bool:
    return model in _BY_ID


def fast_by_default(model: str) -> bool:
    row = _BY_ID.get(model)
    return row is not None and row.fast_by_default


def batches_for(model: str, *, fast: bool | None, fallback: int) -> int:
    if not supports_fast(model):
        return fallback
    del fast
    return 2


def pantry_batches_for(model: str, *, fast: bool | None, fallback: int) -> int:
    if not supports_fast(model):
        return fallback
    del fast
    return fallback


__all__ = [
    "LUNA",
    "MISTRAL_LARGE",
    "RECOMMENDED",
    "Recommended",
    "batches_for",
    "fast_by_default",
    "needs_guest_key",
    "pantry_batches_for",
    "payer_of",
    "supports_fast",
]
