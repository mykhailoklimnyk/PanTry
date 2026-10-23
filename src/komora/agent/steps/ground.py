from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from komora.agent.executor import Trace
from komora.config import Settings
from komora.core.facts import Facts
from komora.db.pool import DictPool
from komora.mcp.client import SilpoMCP


@dataclass(frozen=True, slots=True)
class Ground:

    mcp: SilpoMCP
    cfg: Settings
    moment: datetime
    facts: Facts
    trace: Trace
    pool: DictPool | None = None
    account: str = ""
    delivery_type: str = ""
    llm: Any = None
    batches: int | None = None

    @property
    def packs(self) -> int:
        return self.cfg.pantry_batches if self.batches is None else self.batches


__all__ = ["Ground"]
