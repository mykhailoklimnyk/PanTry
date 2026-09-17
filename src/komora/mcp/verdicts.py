from __future__ import annotations

import json
from functools import cache
from pathlib import Path

from komora.core.instructions import Verdict
from komora.logging import get_logger

log = get_logger(__name__)

REGISTER = Path(__file__).resolve().parent / "verdicts.json"


@cache
def load() -> tuple[Verdict, ...]:
    try:
        rows = json.loads(REGISTER.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("mcp.verdicts_unreadable", error=str(exc)[:160])
        return ()
    return tuple(
        Verdict(
            tool=str(row.get("tool") or ""),
            sha=str(row.get("sha") or ""),
            kind=str(row.get("kind") or ""),
            verdict=str(row.get("verdict") or ""),
            where=str(row.get("where") or ""),
        )
        for row in rows
    )


__all__ = ["REGISTER", "load"]
