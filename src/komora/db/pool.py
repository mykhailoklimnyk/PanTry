from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from psycopg import AsyncConnection
from psycopg.rows import DictRow, dict_row
from psycopg_pool import AsyncConnectionPool

from komora.config import settings

type DictPool = AsyncConnectionPool[AsyncConnection[DictRow]]

_pool: DictPool | None = None


def get_pool() -> DictPool:
    global _pool
    if _pool is None:
        _pool = AsyncConnectionPool(
            conninfo=settings.database_url,
            connection_class=AsyncConnection[DictRow],
            min_size=1,
            max_size=8,
            open=False,
            kwargs={"row_factory": dict_row, "autocommit": True},
        )
    return _pool


@asynccontextmanager
async def pool_lifespan(*, wait: bool = True) -> AsyncIterator[DictPool]:
    pool = get_pool()
    await pool.open(wait=wait, timeout=30)
    try:
        yield pool
    finally:
        await pool.close()
        globals()["_pool"] = None
