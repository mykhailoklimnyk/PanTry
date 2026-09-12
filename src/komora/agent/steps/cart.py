from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from komora.agent.executor import Made
from komora.agent.steps.ground import Ground

WRITE_TOOL = "silpo_add_or_update_cart_products"
REMOVE_TOOL = "silpo_remove_cart_products"
REREAD_TOOL = "silpo_get_shopping_cart_by_id"
SLOT_TOOL = "silpo_update_shopping_cart"


@dataclass(slots=True)
class Cart:

    ground: Ground
    going: list[Any] = field(default_factory=list, init=False)
    rejected: list[Any] = field(default_factory=list, init=False)
    after: Any = field(default=None, init=False)

    async def write(self, bound: Mapping[str, Any], *, put: Any) -> Made:
        going, rejected = await put()
        self.going, self.rejected = going, rejected
        return Made(
            facts={"written": [str(line.product["id"]) for line in going]},
            args={"рядків": len(going), "відхилено": len(rejected)},
            summary=f"у кошик поїхало {len(going)}"
            + (f", кошик відхилив {len(rejected)}" if rejected else ""),
            decision="мандат їде коментарем до рядка: після оформлення змінити "
            "замовлення вже не можна, і читає його збирач",
            tag=f"-{len(rejected)}" if rejected else f"{len(going)} рядків",
            tag_tone="warn" if rejected else "good",
        )

    async def reread(self, bound: Mapping[str, Any], *, read: Any) -> Made:
        after = await read()
        self.after = after
        blockers = [
            str(item.get("code") or "")
            for item in after.validations
            if str(item.get("type") or "").casefold() == "error"
        ]
        return Made(
            facts={"cart": {"id": after.cart_id}, "validations": list(after.validations)},
            args={"рядків у кошику": len(after.rows), "блокерів": len(blockers)},
            summary=f"кошик перечитано: {len(after.rows)} рядків"
            + (f", блокерів {len(blockers)}" if blockers else ", блокерів немає"),
            tag="блокери" if blockers else "чисто",
            tag_tone="warn" if blockers else "good",
        )


__all__ = ["REMOVE_TOOL", "REREAD_TOOL", "SLOT_TOOL", "WRITE_TOOL", "Cart"]
