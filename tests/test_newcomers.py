from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Any

import pytest
from psycopg_pool import PoolTimeout

from komora.api import auth_routes
from komora.auth.crypto import generate_key
from komora.auth.session import GuestSession
from komora.db import intents, newcomers, pantry, rules, spend

ACCOUNT = "a" * 64

POOL_DEFAULT = 30.0


class _Result:
    def __init__(self, row: dict[str, Any] | None) -> None:
        self._row = row

    async def fetchone(self) -> dict[str, Any] | None:
        return self._row


class _Conn:

    def __init__(self, rows: list[dict[str, Any] | None]) -> None:
        self._rows = list(rows)
        self.queries: list[str] = []

    async def execute(self, query: str, params: dict[str, Any] | None = None) -> _Result:
        self.queries.append(query)
        return _Result(self._rows.pop(0) if self._rows else None)


class _Pool:
    def __init__(self, rows: list[dict[str, Any] | None]) -> None:
        self.conn = _Conn(rows)
        self.timeouts: list[float] = []

    def connection(self, timeout: float = POOL_DEFAULT):
        self.timeouts.append(timeout)
        return self._open()

    @asynccontextmanager
    async def _open(self):
        yield self.conn


class _DeadPool:

    def __init__(self) -> None:
        self.timeouts: list[float] = []

    def connection(self, timeout: float = POOL_DEFAULT) -> _DeadConnection:
        self.timeouts.append(timeout)
        return _DeadConnection(timeout)


class _DeadConnection:
    def __init__(self, timeout: float) -> None:
        self._timeout = timeout

    async def __aenter__(self) -> None:
        await asyncio.sleep(self._timeout)
        raise PoolTimeout(f"couldn't get a connection after {self._timeout:.2f} sec")

    async def __aexit__(self, *exc: object) -> bool:
        return False


def test_fingerprint_is_stable():
    assert newcomers.fingerprint("id-1") == newcomers.fingerprint("id-1")


def test_fingerprint_hides_the_id():
    raw = "dde9e996-e876-48c2-ab85-807677b48f30"
    seen = newcomers.fingerprint(raw)
    assert raw not in seen
    assert len(seen) == 64


def test_different_accounts_differ():
    assert newcomers.fingerprint("id-1") != newcomers.fingerprint("id-2")


async def test_second_visit_is_not_a_newcomer():
    pool = _Pool([None])
    assert await newcomers.arrive(pool, account=ACCOUNT) is None


async def test_first_visit_returns_the_position():
    pool = _Pool([{"account": ACCOUNT}, {"position": 3}])
    assert await newcomers.arrive(pool, account=ACCOUNT) == 3


async def test_greeting_is_claimed_once():
    pool = _Pool([None])
    assert await newcomers.claim_greeting(pool, account=ACCOUNT) is None


async def test_greeting_within_the_limit():
    pool = _Pool([{"account": ACCOUNT}, {"position": newcomers.GREET_LIMIT}])
    assert await newcomers.claim_greeting(pool, account=ACCOUNT) == newcomers.GREET_LIMIT


async def test_eleventh_guest_gets_nothing():
    pool = _Pool([{"account": ACCOUNT}, {"position": newcomers.GREET_LIMIT + 1}])
    assert await newcomers.claim_greeting(pool, account=ACCOUNT) is None


async def test_claim_locks_before_counting():
    pool = _Pool([{"account": ACCOUNT}, {"position": 1}])
    await newcomers.claim_greeting(pool, account=ACCOUNT)
    assert pool.conn.queries[0].strip().startswith("update")


def test_the_ceiling_is_the_one_the_neighbours_hold():
    assert newcomers.DB_TIMEOUT == 2.0
    assert {
        intents.DB_TIMEOUT,
        pantry.DB_TIMEOUT,
        rules.DB_TIMEOUT,
        spend.DB_TIMEOUT,
    } == {newcomers.DB_TIMEOUT}


async def test_arrival_asks_for_the_ceiling():
    pool = _Pool([{"account": ACCOUNT}, {"position": 1}])
    await newcomers.arrive(pool, account=ACCOUNT)
    assert pool.timeouts == [newcomers.DB_TIMEOUT]


async def test_greeting_asks_for_the_ceiling():
    pool = _Pool([{"account": ACCOUNT}, {"position": 1}])
    await newcomers.claim_greeting(pool, account=ACCOUNT)
    assert pool.timeouts == [newcomers.DB_TIMEOUT]


async def test_dead_database_gives_up_by_the_ceiling(monkeypatch):
    monkeypatch.setattr(newcomers, "DB_TIMEOUT", 0.05)
    pool = _DeadPool()

    with pytest.raises(PoolTimeout):
        await asyncio.wait_for(newcomers.claim_greeting(pool, account=ACCOUNT), timeout=1.0)

    assert pool.timeouts == [0.05]


async def test_dead_database_does_not_hold_the_arrival_either(monkeypatch):
    monkeypatch.setattr(newcomers, "DB_TIMEOUT", 0.05)
    pool = _DeadPool()

    with pytest.raises(PoolTimeout):
        await asyncio.wait_for(newcomers.arrive(pool, account=ACCOUNT), timeout=1.0)

    assert pool.timeouts == [0.05]


@pytest.fixture
def key(monkeypatch) -> str:
    value = generate_key()
    monkeypatch.setattr(auth_routes.settings, "session_key", value)
    return value


async def test_no_account_means_no_greeting(key):
    guest = GuestSession(access="t", account="")
    assert await auth_routes._greeting(guest) is None


async def test_dead_database_does_not_break_the_session(key, monkeypatch):

    async def _boom(*args, **kwargs):
        raise RuntimeError("база недоступна")

    monkeypatch.setattr(auth_routes.newcomers, "claim_greeting", _boom)
    assert await auth_routes._greeting(GuestSession(access="t", account=ACCOUNT)) is None


async def test_dead_database_does_not_freeze_the_session(key, monkeypatch):
    monkeypatch.setattr(newcomers, "DB_TIMEOUT", 0.05)
    pool = _DeadPool()
    monkeypatch.setattr(auth_routes, "get_pool", lambda: pool)

    greeting = auth_routes._greeting(GuestSession(access="t", account=ACCOUNT))

    assert await asyncio.wait_for(greeting, timeout=1.0) is None
    assert pool.timeouts == [0.05]


async def test_insiders_never_take_a_slot(key, monkeypatch):
    profile_id = "insider-id"
    account = newcomers.fingerprint(profile_id)
    monkeypatch.setattr(auth_routes.settings, "insiders", f" {account} , інше ")

    registered: list[str] = []

    async def _arrive(pool, *, account):
        registered.append(account)
        return 1

    monkeypatch.setattr(auth_routes.newcomers, "arrive", _arrive)
    monkeypatch.setattr(auth_routes, "SilpoMCP", _profile_client(profile_id))

    guest = await auth_routes._identify(GuestSession(access="t"))

    assert registered == []
    assert guest.account == account


async def test_a_sleeping_database_does_not_cost_the_guest_his_account(key, monkeypatch):
    monkeypatch.setattr(auth_routes.settings, "insiders", "")

    async def _boom(pool, *, account):
        raise RuntimeError("база спить")

    monkeypatch.setattr(auth_routes.newcomers, "arrive", _boom)
    monkeypatch.setattr(auth_routes, "SilpoMCP", _profile_client("guest-id"))

    guest = await auth_routes._identify(GuestSession(access="t"))

    assert guest.account == newcomers.fingerprint("guest-id")


async def test_profile_failure_keeps_the_login(key, monkeypatch):

    class _Broken:
        def __init__(self, **kwargs) -> None:
            pass

        async def __aenter__(self):
            raise RuntimeError("MCP недоступний")

        async def __aexit__(self, *exc) -> None:
            return None

    monkeypatch.setattr(auth_routes, "SilpoMCP", _Broken)
    guest = GuestSession(access="t", owner="own")

    assert (await auth_routes._identify(guest)).account == ""


async def test_identify_keeps_the_session_intact(key, monkeypatch):
    monkeypatch.setattr(auth_routes.settings, "insiders", "")

    async def _arrive(pool, *, account):
        return 2

    monkeypatch.setattr(auth_routes.newcomers, "arrive", _arrive)
    monkeypatch.setattr(auth_routes, "SilpoMCP", _profile_client("guest-id"))

    before = GuestSession(access="t", refresh="r", owner="own", branch_id="b1")
    after = await auth_routes._identify(before)

    assert after.account == newcomers.fingerprint("guest-id")
    assert (after.access, after.refresh, after.owner, after.branch_id) == (
        before.access,
        before.refresh,
        before.owner,
        before.branch_id,
    )


def _profile_client(profile_id: str):

    class _Outcome:
        def __init__(self) -> None:
            self.payload_raw = {"success": True, "profile": {"id": profile_id}}

    class _Client:
        def __init__(self, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc) -> None:
            return None

        async def call(self, tool: str, arguments=None) -> _Outcome:
            assert tool == "silpo_get_my_profile"
            return _Outcome()

    return _Client
