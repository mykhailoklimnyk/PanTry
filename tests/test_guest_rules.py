from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import pytest
from fastapi.testclient import TestClient

from komora.api.app import app
from komora.api.auth_routes import require_guest
from komora.core.rules import own_rule, rule_id
from komora.db import rules as store

pytestmark = pytest.mark.anyio

ACCOUNT = "0" * 64
OTHER = "1" * 64


class _Rows:

    def __init__(self) -> None:
        self.data: dict[tuple[str, str], dict[str, Any]] = {}
        self.order = 0

    def upsert(self, args: dict[str, Any]) -> None:
        ident = (args["account"], args["rule_id"])
        if ident in self.data:
            self.data[ident] |= {"label": args["label"], "active": args["active"]}
            return
        self.order += 1
        self.data[ident] = {
            "rule_id": args["rule_id"],
            "label": args["label"],
            "active": args["active"],
            "added_at": self.order,
        }

    def rows(self, account: str) -> list[dict[str, Any]]:
        mine = [row for ident, row in self.data.items() if ident[0] == account]
        return sorted(mine, key=lambda row: (row["added_at"], row["rule_id"]))


class _Conn:
    def __init__(self, rows: _Rows) -> None:
        self.rows = rows
        self.result: list[dict[str, Any]] = []

    async def execute(self, sql: str, args: dict[str, Any] | None = None) -> Any:
        args = args or {}
        text = " ".join(sql.split())
        if text.startswith("select"):
            self.result = self.rows.rows(args["account"])
        elif text.startswith("insert"):
            self.rows.upsert(args)
            self.result = []
        elif text.startswith("update"):
            row = self.rows.data.get((args["account"], args["rule_id"]))
            if row is not None:
                row["active"] = args["active"]
            self.result = [{"rule_id": args["rule_id"]}] if row else []
        elif text.startswith("delete"):
            gone = self.rows.data.pop((args["account"], args["rule_id"]), None)
            self.result = [{"rule_id": args["rule_id"]}] if gone else []
        return self

    async def fetchall(self) -> list[dict[str, Any]]:
        return self.result

    async def fetchone(self) -> dict[str, Any] | None:
        return self.result[0] if self.result else None


class _Pool:
    def __init__(self, rows: _Rows | None = None) -> None:
        self.rows = rows or _Rows()

    @asynccontextmanager
    async def connection(self, **_: Any):
        yield _Conn(self.rows)


class _DeadPool:

    @asynccontextmanager
    async def connection(self, **_: Any):
        raise ConnectionError("база не відповідає")


class _Guest:
    access = "живий-токен"
    refresh = None
    owner = "власник-сесії"
    account = ACCOUNT


class _Anonymous(_Guest):

    account = ""


async def test_the_word_of_one_guest_is_not_visible_to_another():
    pool = _Pool()
    await store.save(pool, ACCOUNT, own_rule("без свинини"))

    assert [rule.label for rule in await store.load(pool, ACCOUNT)] == ["без свинини"]
    assert await store.load(pool, OTHER) == []


async def test_an_account_we_do_not_know_reads_nothing_instead_of_everything():
    assert await store.load(_Pool(), "") == []


async def test_the_same_words_twice_stay_one_rule():
    pool = _Pool()
    await store.save(pool, ACCOUNT, own_rule("Без свинини"))
    await store.save(pool, ACCOUNT, own_rule("без   свинини", active=False))

    rules = await store.load(pool, ACCOUNT)

    assert len(rules) == 1
    assert rules[0].active is False


async def test_touching_a_rule_that_is_not_there_says_so():
    pool = _Pool()

    assert await store.toggle(pool, ACCOUNT, "rule:0123456789abcdef", active=False) is False
    assert await store.remove(pool, ACCOUNT, "rule:0123456789abcdef") is False


@pytest.fixture
def rows() -> _Rows:
    return _Rows()


@pytest.fixture
def guest(monkeypatch: pytest.MonkeyPatch, rows: _Rows) -> TestClient:
    monkeypatch.setattr("komora.api.app.get_pool", lambda: _Pool(rows))
    app.dependency_overrides[require_guest] = lambda: _Guest()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_a_rule_written_once_is_there_after_a_new_login(guest: TestClient) -> None:
    added = guest.post("/api/rules", json={"label": "без свинини"})
    assert added.status_code == 200
    assert [row["label"] for row in added.json()] == ["без свинини"]

    app.dependency_overrides[require_guest] = lambda: _Guest()
    again = guest.get("/api/rules")

    assert [row["label"] for row in again.json()] == ["без свинини"]
    assert again.json()[0]["permanent"] is False


def test_the_first_sync_brings_the_state_of_the_rule_not_just_its_words(
    guest: TestClient,
) -> None:
    guest.post("/api/rules", json={"label": "менше цукру", "active": False})

    assert guest.get("/api/rules").json()[0]["active"] is False


def test_an_empty_rule_is_refused_not_saved(guest: TestClient) -> None:
    assert guest.post("/api/rules", json={"label": "   "}).status_code == 422
    assert guest.get("/api/rules").json() == []


def test_a_rule_longer_than_the_ceiling_is_refused_out_loud(guest: TestClient) -> None:
    answer = guest.post("/api/rules", json={"label": "я" * 200})

    assert answer.status_code == 422
    assert "довше" in answer.json()["detail"]


def test_a_toggle_survives_and_keeps_the_order(guest: TestClient) -> None:
    guest.post("/api/rules", json={"label": "без свинини"})
    guest.post("/api/rules", json={"label": "менше цукру"})

    switched = guest.patch(f"/api/rules/{rule_id('без свинини')}", json={"active": False})

    assert [row["label"] for row in switched.json()] == ["без свинини", "менше цукру"]
    assert switched.json()[0]["active"] is False


def test_switching_a_rule_that_is_not_there_is_a_404(guest: TestClient) -> None:
    answer = guest.patch("/api/rules/rule:deadbeefdeadbeef", json={"active": False})

    assert answer.status_code == 404


def test_deleting_twice_is_not_a_failure(guest: TestClient) -> None:
    guest.post("/api/rules", json={"label": "без свинини"})
    ident = rule_id("без свинини")

    assert guest.delete(f"/api/rules/{ident}").json() == []
    assert guest.delete(f"/api/rules/{ident}").status_code == 200


def test_the_guests_words_never_ride_in_the_request_path(guest: TestClient) -> None:
    ident = guest.post("/api/rules", json={"label": "без свинини"}).json()[0]["id"]

    assert "свинин" not in ident
    assert ident.startswith("rule:")


def test_an_unknown_account_asks_to_come_back_instead_of_showing_nothing(
    monkeypatch: pytest.MonkeyPatch, rows: _Rows
) -> None:
    monkeypatch.setattr("komora.api.app.get_pool", lambda: _Pool(rows))
    app.dependency_overrides[require_guest] = lambda: _Anonymous()
    try:
        answer = TestClient(app).get("/api/rules")
    finally:
        app.dependency_overrides.clear()

    assert answer.status_code == 409
    assert "перезайди" in answer.json()["detail"]


def test_a_dead_database_is_a_refusal_not_an_empty_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("komora.api.app.get_pool", lambda: _DeadPool())
    app.dependency_overrides[require_guest] = lambda: _Guest()
    try:
        client = TestClient(app)

        assert client.get("/api/rules").status_code == 503
        assert client.post("/api/rules", json={"label": "без свинини"}).status_code == 503
    finally:
        app.dependency_overrides.clear()
