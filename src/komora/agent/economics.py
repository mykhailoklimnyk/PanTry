from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

from komora.api.schemas import TopUp as TopUpSchema
from komora.core.delivery import DeliveryTerms, delivery_cost

if TYPE_CHECKING:
    from komora.agent.basket import PlanLine

ORDER_MIN = "order.cost.min"


@dataclass(frozen=True, slots=True)
class Economics:

    total: Decimal
    """Скільки коштує те, що справді їде. «Ще є вдома» сюди не входить."""
    base_total: Decimal
    """Скільки коштувало б без акцій. Дорівнює total, якщо знижок немає."""
    cost: Decimal
    """Ціна доставки, яка діє насправді."""
    by_tiers: Decimal
    """Скільки вийшло б за порогами слота. Розбіжність із `cost` означає
    підписку або персональне промо — і вона показується в трейсі, бо це
    чужі гроші, а не наша арифметика."""
    blockers: list[str]
    top_up: TopUpSchema | None

    @property
    def discounted(self) -> Decimal | None:
        return self.base_total if self.base_total > self.total else None

    @property
    def subscription_applies(self) -> bool:
        return self.cost != self.by_tiers


def topup_for(terms: DeliveryTerms, total: Decimal) -> TopUpSchema | None:
    next_tier = next(
        (
            tier
            for tier in sorted(terms.tiers, key=lambda t: t.from_order_cost)
            if tier.from_order_cost > total
        ),
        None,
    )
    if next_tier is None:
        return None
    return TopUpSchema(
        threshold=next_tier.from_order_cost,
        saving=terms.base_cost - next_tier.cost,
        items=[],
    )


def settle(
    lines: Sequence[PlanLine],
    terms: DeliveryTerms,
    *,
    actual_delivery_cost: Decimal | None = None,
    blockers: Sequence[str] = (),
) -> Economics:
    buying = [line for line in lines if not line.at_home]
    total = sum((line.total for line in buying), Decimal(0))
    base_total = sum(
        (
            Decimal(str(line.product.get("oldPrice") or line.product["price"])) * line.qty
            for line in buying
        ),
        Decimal(0),
    )
    by_tiers = delivery_cost(terms, total)
    cost = actual_delivery_cost if actual_delivery_cost is not None else by_tiers

    codes = list(blockers)
    if total < terms.min_order_cost and ORDER_MIN not in codes:
        codes.append(ORDER_MIN)

    cheapest = min((tier.cost for tier in terms.tiers), default=Decimal(0))
    top_up = topup_for(terms, total) if cost > cheapest else None

    return Economics(
        total=total,
        base_total=base_total,
        cost=cost,
        by_tiers=by_tiers,
        blockers=codes,
        top_up=top_up,
    )


__all__ = ["ORDER_MIN", "Economics", "settle", "topup_for"]
