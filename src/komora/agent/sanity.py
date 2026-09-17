from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from decimal import Decimal, InvalidOperation
from typing import Any

from komora.agent.prompts import register as register_prompt
from komora.agent.prompts import stamp as prompt_stamp
from komora.core import batching
from komora.core import labels as label_bones
from komora.db import facts as facts_store
from komora.db.pool import DictPool
from komora.logging import get_logger

log = get_logger(__name__)

TOKENS_PER_LABEL = 120

SANITY_SYSTEM = (
    "Тобі дають перелік видів товарів, які родина купує в супермаркеті. "
    "Про кожен скажи дві речі. "
    "Перше -- `sanity`: одне коротке речення здорового глузду про те, як цей "
    "вид зникає вдома. Приклад: паляничку з'їдають за раз; морозиво влітку "
    "беруть частіше, ніж узимку; пральний порошок витрачають рівно. "
    "Не вигадуй чисел і не пиши порад -- лише факт про сам товар. "
    "Друге -- `rhythm_lies`: чи брехатиме про цей вид оцінка, зроблена з "
    "того, ЯК ЧАСТО його купують. true там, де покупка не дорівнює "
    "споживанню: сезонне, те, що з'їдається за раз, те, що беруть про запас "
    "чи про гостей. false там, де ритм покупок і є ритм витрачання. "
    "Третє -- НОРМА: скільки цього витрачає ОДНА людина за добу. Число в "
    "`per_day`, а одиницю назви в `per_day_unit`: `г` для всього, що має вагу "
    "чи об'єм (рідини рахуй грамами, 1 мл це 1 г), `шт` для штучного. "
    "Приклади: вода -- 1500 г, хліб -- 250 г, кава мелена -- 15 г, цигарки -- "
    "1 шт (пачка), туалетний папір -- 0.15 шт (рулон). "
    "Не пиши норму на УПАКОВКУ: скільки грамів у пачці, ми знаємо самі, а от "
    "яка пачка в цього гостя -- ти не знаєш. "
    "Це норма ДЛЯ ОДНІЄЇ ЛЮДИНИ і про сам товар, а не про конкретну родину. "
    "Для їжі, напоїв і побутової хімії норма існує завжди -- дай своє "
    "найкраще наближення, навіть грубе. Нуль став лише там, де витрачання "
    "не міряється добою взагалі (посуд, техніка). "
    "Відповідай тими самими мітками, які тобі дали, і не додавай нових."
)

SANITY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "kinds": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string"},
                    "sanity": {"type": "string"},
                    "rhythm_lies": {"type": "boolean"},
                    "per_day": {"type": "number"},
                    "per_day_unit": {"type": "string", "enum": ["г", "шт"]},
                },
                "required": ["label", "sanity", "rhythm_lies", "per_day", "per_day_unit"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["kinds"],
    "additionalProperties": False,
}

register_prompt("sanity", SANITY_SYSTEM)

_CACHE: dict[str, facts_store.Facts] = {}


def _norm(raw: Any) -> Decimal | None:
    try:
        value = Decimal(str(raw))
    except InvalidOperation, TypeError, ValueError:
        return None
    return value if value > 0 else None


NORM_UNITS = frozenset({"г", "шт"})


def _unit(raw: Any) -> str | None:
    text = str(raw or "").strip()
    return text if text in NORM_UNITS else None


def forget_sense() -> None:
    _CACHE.clear()


async def _ask_sense(llm: Any, part: Sequence[str]) -> list[dict[str, Any]]:
    decision = await llm.decide(
        system=SANITY_SYSTEM,
        user=json.dumps({"види": list(part)}, ensure_ascii=False),
        schema=SANITY_SCHEMA,
        schema_name="sanity",
        prompt=prompt_stamp("sanity", SANITY_SYSTEM),
        max_tokens=max(2048, TOKENS_PER_LABEL * len(part)),
        temperature=0.0,
    )
    return list(decision.data.get("kinds", []))


async def intent_sense(
    llm: Any,
    labels: Sequence[str],
    *,
    pool: DictPool | None = None,
    use_cache: bool = True,
    batches: int = 1,
) -> dict[str, facts_store.Facts]:
    fresh = [label for label in labels if label.strip() and (not use_cache or label not in _CACHE)]
    asked_now: dict[str, facts_store.Facts] = {}
    if fresh and pool is not None and use_cache:
        try:
            known = await facts_store.load(pool, fresh)
        except Exception as exc:
            log.warning("pantry.sense.cache_unreadable", error=str(exc))
        else:
            _CACHE.update({label: row for label, row in known.items() if row.sanity})
            fresh = [label for label in fresh if label not in _CACHE]
    if fresh and llm is not None:
        try:
            parts = [[fresh[index] for index in group] for group in batching.split(fresh, batches)]
            answers = await asyncio.gather(
                *(_ask_sense(llm, part) for part in parts), return_exceptions=True
            )
            rows: list[tuple[str, dict[str, Any]]] = []
            broke: list[BaseException] = []
            for part, answer in zip(parts, answers, strict=True):
                if isinstance(answer, BaseException):
                    broke.append(answer)
                    continue
                bones = label_bones.by_skeleton(part)
                rows.extend(
                    (label_bones.echoed(str(row.get("label", "")), bones) or "", row)
                    for row in answer
                )
            if broke and not rows:
                raise broke[0]
            for one in broke:
                log.warning("pantry.sense.batch_failed", error=str(one))
            asked = {facts_store.fingerprint(label): label for label in fresh}
            got: dict[str, facts_store.Facts] = {}
            lost = 0
            drifted = 0
            for by_bones, row in rows:
                sentence = str(row.get("sanity") or "").strip()
                if not sentence:
                    continue
                echo = str(row.get("label", ""))
                original = asked.get(facts_store.fingerprint(echo))
                if original is None:
                    original = by_bones or None
                    if original is not None:
                        drifted += 1
                if original is None:
                    lost += 1
                    continue
                got[original] = facts_store.Facts(
                    sanity=sentence,
                    rhythm_lies=bool(row.get("rhythm_lies")),
                    per_day=_norm(row.get("per_day")),
                    per_day_unit=_unit(row.get("per_day_unit")),
                )
            if drifted:
                log.info("sense.echo_drifted", drifted=drifted, asked=len(fresh))
            if lost:
                log.warning("sense.echo_mismatch", lost=lost, asked=len(fresh))
            asked_now = got
            _CACHE.update(got)
            if pool is not None and got and use_cache:
                try:
                    await facts_store.save(pool, got)
                except Exception as exc:
                    log.warning("pantry.sense.cache_unwritable", error=str(exc))
        except Exception as exc:
            log.warning("pantry.sense.failed", error=str(exc))
    if not use_cache:
        return dict(asked_now)
    return {label: _CACHE[label] for label in labels if label in _CACHE}


__all__ = [
    "SANITY_SCHEMA",
    "SANITY_SYSTEM",
    "TOKENS_PER_LABEL",
    "forget_sense",
    "intent_sense",
]
