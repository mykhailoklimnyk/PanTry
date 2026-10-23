from __future__ import annotations

from komora.db import pool as pool_module


class FakePool:

    def __init__(self) -> None:
        self.opened = 0
        self.closed = 0
        self.waited: bool | None = None

    async def open(self, wait: bool = False, **_: object) -> None:
        self.opened += 1
        self.waited = wait

    async def close(self) -> None:
        self.closed += 1


async def test_the_owner_clears_the_singleton_when_it_closes_the_pool(monkeypatch):
    pool = FakePool()
    monkeypatch.setattr(pool_module, "_pool", pool)

    async with pool_module.pool_lifespan(wait=False) as opened:
        assert opened is pool
        assert pool.opened == 1

    assert pool.closed == 1
    assert pool_module._pool is None


async def test_a_cron_waits_for_the_database_and_a_served_guest_does_not(monkeypatch):
    for wants_wait, opened_with in ((None, True), (False, False)):
        pool = FakePool()
        monkeypatch.setattr(pool_module, "_pool", pool)
        manager = (
            pool_module.pool_lifespan()
            if wants_wait is None
            else pool_module.pool_lifespan(wait=wants_wait)
        )
        async with manager:
            pass
        assert pool.waited is opened_with
