from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta

from komora import runtime
from komora.db import receipts as store
from komora.db.pool import pool_lifespan

runtime.console()

ACCOUNT = "перевірка-сховища-259"

NOW = datetime.now(UTC)


def say(label: str, value: object) -> None:
    print(f"{label:<40}{value}")


async def check() -> int:
    async with pool_lifespan() as pool:
        async with pool.connection() as conn:
            await conn.execute("delete from receipts where account = %(a)s", {"a": ACCOUNT})
            await conn.execute("delete from receipt_reads where account = %(a)s", {"a": ACCOUNT})

        say("ватерлінія до першого читання", await store.mark(pool, ACCOUNT, store.OFFLINE))

        bought = NOW - timedelta(days=5)
        written = await store.save(
            pool,
            ACCOUNT,
            store.OFFLINE,
            [("чек-1", bought, {"products": [{"lagerId": "1", "priceSeen": 44}]})],
        )
        say("записано", written)

        await store.touch(pool, ACCOUNT, store.OFFLINE, last_at=bought)
        seen = await store.mark(pool, ACCOUNT, store.OFFLINE)
        assert seen is not None, "ватерлінія не з'явилась"
        assert seen.last_at == bought, f"ватерлінія стала не туди: {seen.last_at}"
        say("ватерлінія", seen.last_at)

        await store.touch(pool, ACCOUNT, store.OFFLINE, last_at=bought - timedelta(days=30))
        seen = await store.mark(pool, ACCOUNT, store.OFFLINE)
        assert seen is not None and seen.last_at == bought, "ватерлінія поїхала НАЗАД"
        say("назад не їде", "так")

        rows = await store.load(pool, ACCOUNT, store.OFFLINE)
        assert len(rows) == 1, f"прочиталось {len(rows)} замість одного"
        assert isinstance(rows[0], dict), f"jsonb повернувся як {type(rows[0]).__name__}"
        assert rows[0]["products"][0]["priceSeen"] == 44, "поле не пережило запис"
        say("прочитано", len(rows))

        await store.save(
            pool,
            ACCOUNT,
            store.OFFLINE,
            [("чек-1", bought, {"products": [{"lagerId": "1", "priceSeen": 50}]})],
        )
        rows = await store.load(pool, ACCOUNT, store.OFFLINE)
        assert len(rows) == 1, "той самий чек ліг двічі"
        assert rows[0]["products"][0]["priceSeen"] == 50, "повторний запис не оновив"
        say("повторний запис", "оновлює")


        async with pool.connection() as conn:
            await conn.execute("delete from receipts where account = %(a)s", {"a": ACCOUNT})
            await conn.execute("delete from receipt_reads where account = %(a)s", {"a": ACCOUNT})

    print("сховище чеків відповідає на справжній базі")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(runtime.run(check()))
    except AssertionError as exc:
        print(f"СХОВИЩЕ ЗЛАМАНЕ: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
