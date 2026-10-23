from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from typing import Any

from komora.agent.prompts import register as register_prompt
from komora.agent.prompts import stamp as prompt_stamp
from komora.core import batching, catalog
from komora.core import labels as label_bones
from komora.core.aisles import CATCH_ALL
from komora.db import categories as categories_store
from komora.db import facts as facts_store
from komora.db.pool import DictPool
from komora.logging import get_logger

log = get_logger(__name__)

TOKENS_PER_LABEL = 60

AISLE_SYSTEM = (
    "Тобі дають види товарів з домашньої комори і ЗАКРИТИЙ перелік відділів. "
    "Кожному виду постав РІВНО ОДИН відділ з переліку -- той, у якому гість "
    "шукав би цей вид у супермаркеті. "
    "Відділи не вигадуй і не переписуй: бери рядок з переліку дослівно. "
    f"Не підходить жоден -- став «{CATCH_ALL}». "
    "Відповідай тими самими мітками, які тобі дали, і не додавай нових."
)

AISLE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "kinds": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "aisle": {"type": "string"},
                },
                "required": ["label", "aisle"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["kinds"],
    "additionalProperties": False,
}

register_prompt("aisle", AISLE_SYSTEM)

_CACHE: dict[str, str] = {}


async def known_aisles(pool: DictPool | None) -> list[str]:
    if pool is None:
        return []
    try:
        tree = await categories_store.load(pool)
    except Exception as exc:
        log.warning("pantry.aisle.tree_unreadable", error=str(exc))
        return []
    return sorted(catalog.roots_of(tree))


def forget_aisles() -> None:
    _CACHE.clear()


async def _ask(llm: Any, part: Sequence[str], vocabulary: Sequence[str]) -> list[dict[str, Any]]:
    decision = await llm.decide(
        system=AISLE_SYSTEM,
        user=json.dumps({"відділи": list(vocabulary), "види": list(part)}, ensure_ascii=False),
        schema=AISLE_SCHEMA,
        schema_name="aisle",
        prompt=prompt_stamp("aisle", AISLE_SYSTEM),
        max_tokens=max(2048, TOKENS_PER_LABEL * len(part)),
        temperature=0.0,
    )
    return list(decision.data.get("kinds", []))


async def aisles_known(
    labels: Sequence[str], *, pool: DictPool | None = None, use_cache: bool = True
) -> dict[str, str]:
    if not use_cache:
        return {}
    fresh = [label for label in labels if label.strip() and label not in _CACHE]
    if fresh and pool is not None:
        try:
            stored = await facts_store.load(pool, fresh)
        except Exception as exc:
            log.warning("pantry.aisle.cache_unreadable", error=str(exc))
        else:
            _CACHE.update({label: row.aisle for label, row in stored.items() if row.aisle})
    return {label: _CACHE[label] for label in labels if label in _CACHE}


async def intent_aisles(
    llm: Any,
    labels: Sequence[str],
    vocabulary: Sequence[str],
    *,
    pool: DictPool | None = None,
    use_cache: bool = True,
    batches: int = 1,
) -> dict[str, str]:
    known = set(vocabulary)
    if not known:
        return {}
    fresh = [label for label in labels if label.strip() and (not use_cache or label not in _CACHE)]
    asked_now: dict[str, str] = {}
    if fresh and pool is not None and use_cache:
        try:
            stored = await facts_store.load(pool, fresh)
        except Exception as exc:
            log.warning("pantry.aisle.cache_unreadable", error=str(exc))
        else:
            _CACHE.update(
                {
                    label: row.aisle
                    for label, row in stored.items()
                    if row.aisle and row.aisle in known
                }
            )
            fresh = [label for label in fresh if label not in _CACHE]
    if fresh and llm is not None:
        try:
            parts = [[fresh[index] for index in group] for group in batching.split(fresh, batches)]
            answers = await asyncio.gather(
                *(_ask(llm, part, vocabulary) for part in parts), return_exceptions=True
            )
            rows: dict[str, str] = {}
            broke = 0
            for part, answer in zip(parts, answers, strict=True):
                if isinstance(answer, BaseException):
                    broke += 1
                    continue
                bones = label_bones.by_skeleton(part)
                for one in answer:
                    label = label_bones.echoed(str(one.get("label") or ""), bones)
                    aisle = str(one.get("aisle") or "")
                    if label is None or aisle not in known:
                        continue
                    rows[label] = aisle
            if broke:
                log.warning("pantry.aisle.batch_failed", broke=broke, batches=len(parts))
            asked_now.update(rows)
            _CACHE.update(rows)
            if pool is not None and use_cache and rows:
                try:
                    await facts_store.save(
                        pool, {label: facts_store.Facts(aisle=one) for label, one in rows.items()}
                    )
                except Exception as exc:
                    log.warning("pantry.aisle.cache_unwritable", error=str(exc))
        except Exception as exc:
            log.warning("pantry.aisle.failed", error=str(exc))
    if not use_cache:
        return dict(asked_now)
    return {label: _CACHE[label] for label in labels if label in _CACHE}


__all__ = [
    "AISLE_SCHEMA",
    "AISLE_SYSTEM",
    "TOKENS_PER_LABEL",
    "forget_aisles",
    "intent_aisles",
    "known_aisles",
]
