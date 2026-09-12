from __future__ import annotations

import hashlib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

from komora.db.pool import DictPool

DB_TIMEOUT = 2.0

_LOAD = """
select label_sha, keeps, sanity, rhythm_lies, per_day, per_day_unit, aisle
  from intent_facts
 where label_sha = any(%(shas)s)
"""

_UPSERT = """
insert into intent_facts (label_sha, keeps, sanity, rhythm_lies, per_day, per_day_unit, aisle)
values (%(label_sha)s, %(keeps)s, %(sanity)s, %(rhythm_lies)s, %(per_day)s, %(per_day_unit)s,
        %(aisle)s)
on conflict (label_sha) do update
   set keeps       = coalesce(excluded.keeps, intent_facts.keeps),
       sanity      = coalesce(excluded.sanity, intent_facts.sanity),
       rhythm_lies = coalesce(excluded.rhythm_lies, intent_facts.rhythm_lies),
       per_day     = coalesce(excluded.per_day, intent_facts.per_day),
       per_day_unit = coalesce(excluded.per_day_unit, intent_facts.per_day_unit),
       aisle       = coalesce(excluded.aisle, intent_facts.aisle),
       last_seen   = now()
"""


@dataclass(frozen=True, slots=True)
class Facts:

    keeps: str | None = None
    sanity: str | None = None
    rhythm_lies: bool | None = None
    per_day: Decimal | None = None
    """Скільки витрачає одна людина за добу -- в одиниці `per_day_unit`."""
    aisle: str | None = None
    """Відділ, у якому гість шукав би цей вид (#369). `None` -- не питали, і
    це не те саме, що «Інше»: перше означає «спитати ще можна», друге --
    «модель подивилась і не знайшла свого відділу».

    Слово тут МОДЕЛІ, а перелік -- чужого дерева: вона обирає із закритого
    словника коренів і не вигадує (замір 09.09: нуль тегів поза переліком на
    157 заголовках, 98% повторюваності). Сам словник сюди не пишеться -- він
    місцевий до обходу і оновлюється щотижня (0035)."""
    per_day_unit: str | None = None
    """`г` або `шт`. Без неї число не порівнюється ні з чим (#78): «пляшка на
    добу» нічого не означає, поки не сказано, півтора літра в ній чи пів.
    Рідини рахуються грамами (1 мл ~ 1 г) -- наближення назване вголос, і для
    вето в РАЗИ його точності досить."""


def fingerprint(label: str) -> str:
    return hashlib.sha256(" ".join(label.split()).casefold().encode()).hexdigest()


async def load(pool: DictPool, labels: Sequence[str]) -> dict[str, Facts]:
    if not labels:
        return {}
    by_sha = {fingerprint(label): label for label in labels}
    async with pool.connection(timeout=DB_TIMEOUT) as conn:
        rows = await (await conn.execute(_LOAD, {"shas": list(by_sha)})).fetchall()
    return {
        by_sha[row["label_sha"]]: Facts(
            keeps=row["keeps"],
            sanity=row["sanity"],
            rhythm_lies=row["rhythm_lies"],
            per_day=row["per_day"],
            per_day_unit=row["per_day_unit"],
            aisle=row["aisle"],
        )
        for row in rows
        if row["label_sha"] in by_sha
    }


async def save(pool: DictPool, facts: Mapping[str, Facts]) -> None:
    rows = [
        {
            "label_sha": fingerprint(label),
            "keeps": known.keeps,
            "sanity": known.sanity,
            "rhythm_lies": known.rhythm_lies,
            "per_day": known.per_day,
            "per_day_unit": known.per_day_unit,
            "aisle": known.aisle,
        }
        for label, known in facts.items()
        if label.strip()
    ]
    if not rows:
        return
    async with pool.connection(timeout=DB_TIMEOUT) as conn, conn.cursor() as cur:
        await cur.executemany(_UPSERT, rows)


__all__ = ["DB_TIMEOUT", "Facts", "fingerprint", "load", "save"]
