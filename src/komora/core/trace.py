from __future__ import annotations

from typing import Literal

SUMMARY_CHARS = 120


Tone = Literal["good", "warn", "muted"]


def fits(summary: str) -> bool:
    return len(summary) <= SUMMARY_CHARS


__all__ = ["SUMMARY_CHARS", "Tone", "fits"]
