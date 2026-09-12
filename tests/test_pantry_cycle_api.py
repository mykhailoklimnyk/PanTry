from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import pytest
from fastapi.testclient import TestClient

from komora.api.app import app
from komora.api.auth_routes import require_guest
from komora.api.schemas import Pantry

pytestmark = pytest.mark.anyio

ACCOUNT = "відбиток-акаунта"


class Session:
    access = "живий-токен"
    refresh = "живий-refresh"
    owner = "власник-сесії"
    account = ACCOUNT


class _Store:

    def __init__(self) -> None:
        self.cycles: dict[tuple[str, str], int] = {}

    async def load_cycles(self, _pool: Any, account: str) -> dict[str, int]:
        return {kind: days for (who, kind), days in self.cycles.items() if who == account}

    async def save_cycle(self, _pool: Any, account: str, kind: str, days: int) -> None:
        self.cycles[(account, kind)] = days

    async def drop_cycle(self, _pool: Any, account: str, kind: str) -> None:
        self.cycles.pop((account, kind), None)

    async def load(self, _pool: Any, _account: str) -> dict[str, Any]:
        return {}

    async def load_items(self, _pool: Any, _account: str) -> dict[str, str]:
        return {}

    async def save(self, *_a: Any, **_kw: Any) -> None: ...


class _DeadStore(_Store):
    async def save_cycle(self, *_a: Any, **_kw: Any) -> None:
        raise ConnectionError("сховище не відповідає")


class _Silpo:
    def __init__(self, *_a: Any, **_kw: Any) -> None: ...

    async def __aenter__(self) -> _Silpo:
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False


async def _place(*_a: Any, **_kw: Any) -> None:
    return None


EMPTY = Pantry(items=[], receipts=3, kinds=1, tracked_from=3)


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> _Store:
    kept = _Store()
    for name in ("load", "load_items", "load_cycles", "save", "save_cycle", "drop_cycle"):
        monkeypatch.setattr(f"komora.api.app.pantry_marks.{name}", getattr(kept, name))
    monkeypatch.setattr("komora.api.app.get_pool", lambda: None)
    return kept


@pytest.fixture
def seen(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    got: dict[str, Any] = {}

    async def _live(*_a: Any, **kw: Any) -> Pantry:
        got.update(kw)
        return EMPTY

    async def _named(*_a: Any, **kw: Any) -> tuple[str, int | None]:
        got["named_receipts"] = kw.get("receipts")
        return "хліб київський", _named.days

    paper = object()

    async def _read(*_a: Any, **_kw: Any) -> Any:
        got["reads"] = got.get("reads", 0) + 1
        return paper

    _named.days = 2  # type: ignore[attr-defined]
    monkeypatch.setattr("komora.api.app.pantry_live", _live)
    monkeypatch.setattr("komora.api.app.name_cycle", _named)
    monkeypatch.setattr("komora.api.app.read_receipts", _read)
    monkeypatch.setattr("komora.api.app.place_of", _place)
    monkeypatch.setattr("komora.api.app.SilpoMCP", _Silpo)
    got["_named"] = _named
    got["_paper"] = paper
    return got


@pytest.fixture
def client(seen: dict[str, Any], store: _Store) -> TestClient:
    app.dependency_overrides[require_guest] = lambda: Session()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_the_named_cycle_reaches_the_store(client: TestClient, store: _Store) -> None:
    response = client.patch("/api/pantry", json={"id": "101", "action": "cycle", "days": 2})

    assert response.status_code == 200
    assert store.cycles == {(ACCOUNT, "хліб київський"): 2}


def test_the_answer_already_counts_the_new_word(client: TestClient, seen: dict[str, Any]) -> None:
    client.patch("/api/pantry", json={"id": "101", "action": "cycle", "days": 2})

    assert seen["said"].cycles == {"хліб київський": 2}


def test_taking_the_word_back_reaches_the_store_too(
    client: TestClient, store: _Store, seen: dict[str, Any]
) -> None:
    store.cycles[(ACCOUNT, "хліб київський")] = 2
    seen["_named"].days = None

    response = client.patch("/api/pantry", json={"id": "101", "action": "forget_cycle"})

    assert response.status_code == 200
    assert store.cycles == {}
    assert seen["said"].cycles == {}, "рядок повертається до оцінки з чеків уже в цій відповіді"


def test_a_store_that_did_not_answer_says_so_out_loud(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    dead = _DeadStore()
    monkeypatch.setattr("komora.api.app.pantry_marks.save_cycle", dead.save_cycle)

    response = client.patch("/api/pantry", json={"id": "101", "action": "cycle", "days": 2})

    assert response.status_code == 503
    assert "ще раз" in response.json()["detail"]


def test_the_basket_is_built_with_what_the_guest_said(
    monkeypatch: pytest.MonkeyPatch, store: _Store
) -> None:
    store.cycles[(ACCOUNT, "хліб київський")] = 2
    got: dict[str, Any] = {}

    async def _assemble(*_a: Any, **kw: Any) -> Any:
        got.update(kw)
        raise _Stop

    class _Stop(Exception): ...

    @asynccontextmanager
    async def _counted(*_a: Any, **_kw: Any):
        yield

    monkeypatch.setattr("komora.api.app.assemble_list", _assemble)
    monkeypatch.setattr("komora.api.app.place_of", _place)
    monkeypatch.setattr("komora.api.app.SilpoMCP", _Silpo)
    monkeypatch.setattr("komora.api.app.quota.counted", _counted)
    app.dependency_overrides[require_guest] = lambda: Session()
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            client.post("/api/basket", json={})
    finally:
        app.dependency_overrides.clear()

    assert got.get("cycles") == {"хліб київський": 2}
    assert got.get("marks") == {}, "позначки теж передаються — просто тут їх немає"


def test_a_foreign_cart_is_not_explained_by_our_pantry(
    monkeypatch: pytest.MonkeyPatch, store: _Store
) -> None:
    store.cycles[(ACCOUNT, "хліб київський")] = 2
    got: dict[str, Any] = {}

    async def _assemble_cart(*_a: Any, **kw: Any) -> Any:
        got.update(kw)
        raise RuntimeError("далі не йдемо")

    @asynccontextmanager
    async def _counted(*_a: Any, **_kw: Any):
        yield

    monkeypatch.setattr("komora.api.app.assemble_cart", _assemble_cart)
    monkeypatch.setattr("komora.api.app.place_of", _place)
    monkeypatch.setattr("komora.api.app.SilpoMCP", _Silpo)
    monkeypatch.setattr("komora.api.app.quota.counted", _counted)
    app.dependency_overrides[require_guest] = lambda: Session()
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            client.post("/api/basket", json={"source": "cart"})
    finally:
        app.dependency_overrides.clear()

    assert "cycles" not in got
    assert "marks" not in got


def test_the_receipts_are_read_once_for_the_whole_word(
    client: TestClient, seen: dict[str, Any]
) -> None:
    client.patch("/api/pantry", json={"id": "101", "action": "cycle", "days": 2})

    assert seen["reads"] == 1
    assert seen["named_receipts"] is seen["_paper"]
    assert seen["receipts"] is seen["_paper"]


def test_a_touch_on_a_row_does_not_drop_the_exclusive_mode(
    client: TestClient, seen: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:

    async def _mode(*_a: Any, **_kw: Any) -> str:
        return "manual"

    monkeypatch.setattr("komora.api.app.pantry_marks.load_source", _mode)

    client.patch("/api/pantry", json={"id": "101", "action": "cycle", "days": 2})

    assert seen["said"].source == "manual"


def test_a_mark_reads_caches_and_never_asks_the_model(
    client: TestClient, seen: dict[str, Any]
) -> None:
    response = client.patch("/api/pantry", json={"id": "101", "action": "cycle", "days": 2})

    assert response.status_code == 200
    assert seen["ask"] is False
