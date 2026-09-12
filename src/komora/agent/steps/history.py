from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from komora.agent.basket import (
    HISTORY_PAGE,
    MAX_HISTORY_PAGES,
    MAX_ONLINE_PAGES,
    ONLINE_PAGE,
    RECENT_DAYS,
    HistoryItem,
    Online,
    apply_cycles,
    apply_marks,
    load_history,
)
from komora.agent.executor import Made
from komora.agent.steps.ground import Ground

RECEIPTS_TOOL = "silpo_get_my_offline_orders"
ORDERS_TOOL = "silpo_get_my_online_orders"


@dataclass(frozen=True, slots=True)
class Papers:

    count: int
    capped: bool

    def __len__(self) -> int:
        return self.count


class History:

    def __init__(
        self,
        ground: Ground,
        *,
        marks: Mapping[str, Any] | None = None,
        cycles: Mapping[str, int] | None = None,
    ) -> None:
        self.ground = ground
        self.marks = marks or {}
        self.cycles = cycles or {}
        self.items: list[HistoryItem] = []
        self.receipts = 0
        self.sizes: list[int] = []
        self.web: Online | None = None

    @property
    def capped(self) -> bool:
        return self.receipts >= MAX_HISTORY_PAGES * HISTORY_PAGE

    async def read(self, bound: Mapping[str, Any]) -> Made:
        items, receipts, _ms, sizes, web = await load_history(
            self.ground.mcp,
            bound["slot"],
            bound["branch"] or None,
            now=self.ground.moment,
            pool=self.ground.pool,
            account=self.ground.account,
        )
        self.items, self.receipts, self.sizes, self.web = items, receipts, sizes, web
        apply_marks(items, self.marks)
        apply_cycles(items, self.cycles)
        bought = (
            f"{receipts} чеків" + (f" і {web.count} замовлень " if web.count else " ")
            if receipts
            else f"{web.count} замовлень (чеків магазину немає) "
        )
        return Made(
            facts={
                "receipts": Papers(count=receipts, capped=self.capped),
                "orders": web,
                "history": items,
            },
            args={
                "max_pages": MAX_HISTORY_PAGES,
                "online_pages": MAX_ONLINE_PAGES,
                "online_page": ONLINE_PAGE,
            },
            summary=(
                "покупок у «Сільпо» ще не видно — цикли рахувати нема з чого"
                if receipts == 0 and web.count == 0
                else bought
                + (
                    f"(стеля {MAX_HISTORY_PAGES * HISTORY_PAGE} — глибша історія не читалась)"
                    if self.capped
                    else f"(вся історія, свіжі {RECENT_DAYS} днів важать більше)"
                )
                + f", {len(items)} різних товарів"
            ),
            decision="історія покупок читається лише разом з магазином і слотом; "
            "сам набір чеків від магазину не залежить",
            tag="стеля історії" if self.capped else None,
            tag_tone="warn",
        )


__all__ = ["ORDERS_TOOL", "RECEIPTS_TOOL", "History", "Papers"]
