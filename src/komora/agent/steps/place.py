from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from komora.agent.executor import Made
from komora.agent.place import resolve as resolve_place
from komora.agent.steps.ground import Ground
from komora.api.schemas import OrderFeedback
from komora.core.feedback import changes_of, contacts_of
from komora.core.location import Location, decide, source_note
from komora.core.location import Source as BranchSource
from komora.core.plan import Refusal
from komora.logging import get_logger
from komora.mcp.client import MCPCallError, SilpoMCP, missing_resource

log = get_logger(__name__)

CART_TOOL = "silpo_get_my_shopping_cart"
CART_BY_ID_TOOL = "silpo_get_shopping_cart_by_id"
TYPES_TOOL = "silpo_get_available_delivery_types"
ADDRESSES_TOOL = "silpo_get_my_delivery_addresses"


async def read_cart(mcp: SilpoMCP) -> dict[str, Any]:
    cart_id = (await mcp.call(CART_TOOL)).payload_raw.get("shoppingCartId")
    if not cart_id:
        return {}
    details = (await mcp.call(CART_BY_ID_TOOL, {"shoppingCartId": cart_id})).payload_raw
    cart = details.get("cart") or {}
    shipments = cart.get("shipments") or []
    return {
        "id": str(cart_id),
        "branch": shipments[0].get("branchId") if shipments else None,
        "slot": (cart.get("timeslot") or {}).get("start"),
        "feedback": OrderFeedback(
            changes=changes_of(cart.get("feedbackChanges")),
            contacts=contacts_of(cart.get("feedbackContacts")),
        ),
    }


class Place:

    def __init__(self, ground: Ground, *, known: Location | None = None) -> None:
        self.ground = ground
        self.known = known
        self.where: Location | None = known
        self.source: BranchSource | None = None
        self.branch_id: str | None = None

    @property
    def cart(self) -> Mapping[str, Any]:
        got = self.ground.facts.origin("cart")
        return got.value if got is not None else {}

    @property
    def feedback(self) -> OrderFeedback:
        got = self.cart.get("feedback")
        return got if isinstance(got, OrderFeedback) else OrderFeedback()

    @property
    def cart_slot(self) -> str | None:
        got = self.cart.get("slot")
        return str(got) if got else None

    async def address(self, bound: Mapping[str, Any]) -> Made:
        where = await resolve_place(self.ground.mcp, settings=self.ground.cfg)
        self.where = where
        return Made(
            facts={"address": where, "delivery_types": where.branches},
            args={"адреса в акаунті": where.address is not None},
            summary=(
                f"адреса є, способів отримання з філією {len(where.branches)}"
                if where.address is not None
                else "адреси в акаунті немає — філію візьмемо з кошика або налаштувань"
            ),
            tag=None if where.address is not None else "без адреси",
            tag_tone="muted",
        )

    async def read(self, bound: Mapping[str, Any]) -> Made:
        try:
            cart = await read_cart(self.ground.mcp)
        except MCPCallError as exc:
            log.warning("basket.cart_context_failed", error=str(exc))
            if missing_resource(exc):
                return Made(
                    facts={"cart": {}},
                    summary="кошика в акаунті ще немає — слот беремо перший вільний",
                    tag_tone="muted",
                )
            return Made(
                args={"помилка": str(exc)[:400]},
                absent=f"кошик не прочитався ({str(exc)[:50]}) — слот беремо перший вільний",
                absent_kind=Refusal.BROKE,
                tag_tone="warn",
            )
        return Made(
            facts={"cart": cart},
            summary=(
                f"кошик прочитано, слот у ньому: {cart['slot'] or 'не виставлений'}"
                if cart
                else "кошик в акаунті порожній — слот беремо перший вільний"
            ),
            tag_tone="muted",
        )

    async def settle(self, bound: Mapping[str, Any]) -> Made:
        where = self.where
        branch_id, source = decide(
            from_address=(
                where.address_branch(self.ground.delivery_type) if where is not None else None
            ),
            from_cart=self.cart.get("branch"),
            from_config=self.ground.cfg.branch_id,
        )
        self.branch_id, self.source = branch_id, source
        return Made(
            facts={"branch": branch_id or "", "delivery_type": self.ground.delivery_type},
            summary=source_note(source)
            + ("" if self.known is None else " · місце з пам'яті сесії — походу не було"),
            decision="наявність міряється там, звідки збиратимуть",
            tag=None if source is BranchSource.ADDRESS else "не за адресою",
            tag_tone="muted" if source is BranchSource.ADDRESS else "warn",
        )


__all__ = ["ADDRESSES_TOOL", "CART_TOOL", "TYPES_TOOL", "Place", "read_cart"]
