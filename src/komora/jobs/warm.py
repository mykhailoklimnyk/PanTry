from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from komora import runtime
from komora.agent.basket import intent_keeps, intent_names, slots_query
from komora.agent.llm import Meter, build_llm
from komora.agent.sanity import intent_sense
from komora.config import settings
from komora.core.facts_audit import Report, audit
from komora.core.location import HOME_DELIVERY
from komora.core.quota import run_cost
from komora.db import facts as facts_store
from komora.db import intents as store
from komora.db import spend
from komora.db.pool import DictPool, pool_lifespan
from komora.jobs.categories import fetch_all
from komora.logging import get_logger
from komora.mcp.client import MCPCallError, SilpoMCP

log = get_logger(__name__)

TOOL = "silpo_get_products"

OWNER = "komora-warm"

PER_NODE = 40

BATCH = 40


@dataclass(frozen=True, slots=True)
class Warmed:

    nodes: int
    names: int
    known: int
    named: int
    labels: int
    facts: int
    calls: int
    cost_usd: Decimal | None
    check: Report
    counted: bool = True

    def summary(self) -> str:
        price = "невідомо" if self.cost_usd is None else f"${self.cost_usd}"
        tail = "" if self.counted else " · У ЛІЧИЛЬНИК НЕ ЛЯГЛО"
        head = (
            f"вузлів {self.nodes}, назв каталогу {self.names}, "
            f"уже знали {self.known}, назвали {self.named}, "
            f"міток {self.labels}, з них із фактами {self.facts} "
            f"за {self.calls} викликів, ціна {price}{tail}"
        )
        return "\n".join([head, *self.check.lines()])


async def shelf(mcp: SilpoMCP, slot: dict[str, Any], branch_id: str) -> tuple[int, list[str]]:
    nodes = await fetch_all(mcp, branch_id=branch_id)
    found: list[tuple[int, list[str]]] = []
    for node in nodes:
        if not node.slug:
            continue
        try:
            got = await mcp.call(
                TOOL,
                {
                    "branchId": branch_id,
                    "deliveryType": slot["deliveryType"],
                    "timeslotStart": slot["start"],
                    "timeslotEnd": slot["end"],
                    "category": node.slug,
                    "limit": PER_NODE,
                    "inStock": True,
                    "sortBy": "popularity",
                },
            )
        except MCPCallError as exc:
            log.warning("warm.node_failed", slug=node.slug, error=str(exc))
            continue
        rows = got.payload_raw.get("products") or []
        total = (got.payload_raw.get("meta") or {}).get("total") or len(rows)
        names = [str(row.get("name") or "") for row in rows]
        found.append((int(total), [name for name in names if name]))

    found.sort(key=lambda pair: pair[0], reverse=True)
    ordered: dict[str, None] = {}
    for _, names in found:
        for name in names:
            ordered.setdefault(name, None)
    return len(found), list(ordered)


async def warm(
    mcp: SilpoMCP,
    llm: Any,
    pool: DictPool,
    *,
    branch_id: str,
    limit: int | None = None,
    now: datetime | None = None,
) -> Warmed:
    moment = now or datetime.now(UTC)
    outcome = await mcp.call(
        "silpo_get_time_slots", slots_query(branch_id, HOME_DELIVERY, 5, since=moment)
    )
    slots = outcome.payload_raw.get("slots") or []
    slot = next((s for s in slots if s.get("available")), slots[0] if slots else None)
    if slot is None:
        raise RuntimeError("немає жодного слота — без нього каталог не читається")

    nodes, names = await shelf(mcp, slot, branch_id)
    known = await store.load(pool, names)
    fresh = [name for name in names if name not in known]
    if limit is not None:
        fresh = fresh[:limit]

    meter = Meter.of(llm)
    labels: dict[str, None] = {}
    for intent, subtype, _drink in known.values():
        labels.setdefault(f"{intent} · {subtype}" if subtype else intent, None)

    for start in range(0, len(fresh), BATCH):
        chunk = fresh[start : start + BATCH]
        named = await intent_names(llm, chunk, pool=pool, need_drink=True)
        for naming in named.values():
            if naming.label:
                labels.setdefault(naming.label, None)
        log.info("warm.batch", done=start + len(chunk), left=len(fresh) - start - len(chunk))

    warming = list(labels)[:limit] if limit is not None else list(labels)
    for start in range(0, len(warming), BATCH):
        chunk = warming[start : start + BATCH]
        await intent_keeps(llm, chunk, pool=pool)
        await intent_sense(llm, chunk, pool=pool)
        log.info("warm.facts", done=start + len(chunk), left=len(warming) - start - len(chunk))

    cost = run_cost(meter.model or "", meter.calls, meter.input_tokens, meter.output_tokens)
    if cost is None:
        log.warning("warm.model_without_price", model=meter.model)
    counted = True
    try:
        await spend.record(
            pool,
            account="",
            owner=OWNER,
            kind="warm",
            model=meter.model,
            tokens_in=meter.input_tokens,
            tokens_out=meter.output_tokens,
            cost_usd=cost,
            duration_ms=int((datetime.now(UTC) - moment).total_seconds() * 1000),
            started_at=moment,
        )
    except Exception as exc:
        log.error("warm.spend_unrecorded", error=str(exc)[:200])
        counted = False

    written = await facts_store.load(pool, warming)
    return Warmed(
        nodes=nodes,
        names=len(names),
        known=len(known),
        named=len(await store.load(pool, fresh)),
        labels=len(labels),
        facts=sum(1 for row in written.values() if row.keeps and row.sanity),
        calls=meter.calls,
        cost_usd=cost,
        counted=counted,
        check=audit(written),
    )


async def run(*, branch_id: str | None = None, limit: int | None = None) -> Warmed:
    token, branch = settings.require_operator()
    if not settings.bedrock_api_key:
        raise RuntimeError(
            "Немає ключа до моделі -- нагрівати нема чим. Задай ANTHROPIC_API_KEY "
            "у .env (див. docs/setup.md)."
        )
    llm = build_llm(
        model=settings.bedrock_model_id,
        base_url=settings.bedrock_base_url,
        api_key=settings.bedrock_api_key,
    )
    async with pool_lifespan() as pool, SilpoMCP(token=token) as mcp:
        return await warm(mcp, llm, pool, branch_id=branch_id or branch, limit=limit)


def main() -> int:
    runtime.console()
    parser = argparse.ArgumentParser(description="Нагріти кеш назв видів каталогом")
    parser.add_argument(
        "--limit", type=int, default=None, help="скільки назв назвати за цей прогін"
    )
    parser.add_argument("--branch", default=None, help="філія, з якої читаємо каталог")
    args = parser.parse_args()

    try:
        done = runtime.run(run(branch_id=args.branch, limit=args.limit))
    except Exception as exc:
        log.error("warm.run_failed", error=str(exc))
        return 1

    print(done.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
