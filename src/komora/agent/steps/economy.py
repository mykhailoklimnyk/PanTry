from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from komora.agent.economics import settle
from komora.agent.executor import Made
from komora.agent.steps.ground import Ground

TOOL = "core.delivery"


@dataclass(slots=True)
class Economy:

    ground: Ground

    async def report(self, bound: Mapping[str, Any]) -> Made:
        from komora.agent.basket import terms_from_slot

        terms = terms_from_slot(bound["slot"])
        money = settle(bound["lines"], terms)
        return Made(
            facts={"economics": money},
            summary=f"разом {money.total} грн, доставка {money.cost} грн"
            + (f"; до мінімуму {terms.min_order_cost} бракує" if money.blockers else ""),
        )


__all__ = ["TOOL", "Economy"]
