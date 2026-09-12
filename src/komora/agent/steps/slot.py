from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from komora.agent.basket import SLOT_LOOKAHEAD, AssemblyError, slots_query
from komora.agent.executor import Made
from komora.agent.steps.ground import Ground
from komora.core import slots as core_slots
from komora.core.slots import window_note
from komora.db import receipts as receipts_store
from komora.logging import get_logger

log = get_logger(__name__)

SLOTS_TOOL = "silpo_get_time_slots"


class Slots:

    def __init__(self, ground: Ground) -> None:
        self.ground = ground
        self.note: str = ""
        """Підстава вибору -- на екран, поруч зі слотом (#88)."""

    async def choose(self, bound: Mapping[str, Any]) -> Made:
        outcome = await self.ground.mcp.call(
            SLOTS_TOOL,
            slots_query(
                bound["branch"] or None,
                bound["delivery_type"],
                SLOT_LOOKAHEAD,
                since=self.ground.moment,
            ),
        )
        offered = outcome.payload_raw.get("slots", [])
        known_cart = self.ground.facts.origin("cart")
        cart = known_cart.value if known_cart is not None else {}
        choice = core_slots.choose(
            [(row.get("start"), bool(row.get("available"))) for row in offered],
            wanted=str(cart.get("slot")) if cart.get("slot") else None,
            habit=await self._habit(),
            now=self.ground.moment,
        )
        slot = offered[choice.index] if choice else None
        if slot is None or choice is None:
            raise AssemblyError(
                f"{core_slots.no_free_note(bound['delivery_type'], len(offered))}"
                " — збирати нема під що"
            )
        self.note = core_slots.basis_note(choice)
        return Made(
            facts={"slots": offered, "slot": slot},
            args={
                "deliveryTypes": [bound["delivery_type"]],
                "limit": SLOT_LOOKAHEAD,
                "вікно": f"{slot['start']} — {slot['end']}",
            },
            summary=f"обрано слот {window_note(slot['start'], slot['end'], now=self.ground.moment)}"
            f" — вільних {choice.free} з {choice.offered} найближчих",
            decision=self.note,
            tag=None if choice.basis is core_slots.Basis.CART else "не з кошика",
            tag_tone="muted",
        )

    async def _habit(self) -> dict[int, int]:
        if self.ground.pool is None or not self.ground.account:
            return {}
        try:
            return await receipts_store.slot_hours(self.ground.pool, self.ground.account)
        except Exception as exc:
            log.warning("slot.habit_unavailable", error=str(exc))
            return {}


__all__ = ["SLOTS_TOOL", "Slots"]
