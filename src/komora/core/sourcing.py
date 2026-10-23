from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from komora.core.channels import Channel, admissible
from komora.core.substitution import LOW_STOCK_THRESHOLD, Alternative, is_risky


class Resolution(StrEnum):

    IN_STOCK = "in_stock"
    OTHER_BRANCH = "other_branch"
    OTHER_CHANNEL = "other_channel"
    SUBSTITUTE = "substitute"
    UNAVAILABLE = "unavailable"


@dataclass(frozen=True, slots=True)
class BranchStock:
    branch_id: str
    stock: int | None
    available: bool


@dataclass(frozen=True, slots=True)
class Plan:
    resolution: Resolution
    branch_id: str | None = None
    channel: Channel | None = None
    substitute: Alternative | None = None
    reason: str = ""


def resolve(
    *,
    home_branch: BranchStock,
    other_branches: Sequence[BranchStock] = (),
    channels: Iterable[Channel] = (),
    chain: Sequence[Alternative] = (),
    hours_until_runout: int | None = None,
    perishable: bool = False,
    low_stock_threshold: int = LOW_STOCK_THRESHOLD,
) -> Plan:
    usable = admissible(
        channels, hours_until_runout=hours_until_runout, perishable=perishable
    )

    if home_branch.available and home_branch.stock:
        risky = is_risky(home_branch.stock, threshold=low_stock_threshold)
        return Plan(
            resolution=Resolution.IN_STOCK,
            branch_id=home_branch.branch_id,
            reason=(
                f"є у своїй філії, залишок {home_branch.stock}"
                + (" — мало, заміна напоготові" if risky else "")
            ),
        )

    pickup = next((c for c in usable if c.scope.value == "any"), None)
    if pickup is not None:
        best = _richest(other_branches)
        if best is not None:
            return Plan(
                resolution=Resolution.OTHER_BRANCH,
                branch_id=best.branch_id,
                channel=pickup,
                reason=(
                    f"у своїй філії немає, але є в іншій (залишок {best.stock}) — "
                    f"{pickup.name}, той самий товар"
                ),
            )

    other = next((c for c in usable if c.scope.value != "any"), None)
    if other is not None and other_branches:
        best = _richest(other_branches)
        if best is not None:
            return Plan(
                resolution=Resolution.OTHER_CHANNEL,
                branch_id=best.branch_id,
                channel=other,
                reason=f"той самий товар, довший шлях — {other.name}",
            )

    if chain:
        return Plan(
            resolution=Resolution.SUBSTITUTE,
            substitute=chain[0],
            reason=f"ніде немає — заміна на {chain[0].name}",
        )

    return Plan(
        resolution=Resolution.UNAVAILABLE,
        reason="немає ні в наявності, ні чим замінити",
    )


def _richest(branches: Sequence[BranchStock]) -> BranchStock | None:
    candidates = [b for b in branches if b.available and b.stock]
    if not candidates:
        return None
    return max(candidates, key=lambda b: (b.stock or 0, b.branch_id))
