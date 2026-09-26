from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from komora.api.app import app
from komora.api.auth_routes import require_guest
from komora.core.pantry import manual_id


class Session:
    access = "живий-токен"
    refresh = "живий-refresh"
    owner = "власник-сесії"
    account = "відбиток-акаунта"


class _Store:

    def __init__(self) -> None:
        self.items: dict[tuple[str, str, str], str] = {}

    async def load_items(self, _pool: Any, account: str, *, scope: str) -> dict[str, str]:
        return {
            kind: label
            for (owner, area, kind), label in self.items.items()
            if owner == account and area == scope
        }

    async def add_item(
        self, _pool: Any, account: str, kind: str, label: str, *, scope: str
    ) -> None:
        self.items[(account, scope, kind)] = label

    async def drop_item(self, _pool: Any, account: str, kind: str, *, scope: str) -> None:
        self.items.pop((account, scope, kind), None)


class _DeadStore(_Store):

    async def add_item(self, *_a: Any, **_kw: Any) -> None:
        raise ConnectionError("сховище не відповідає")

    async def drop_item(self, *_a: Any, **_kw: Any) -> None:
        raise ConnectionError("сховище не відповідає")


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> _Store:
    kept = _Store()
    monkeypatch.setattr("komora.api.app.pantry_marks.load_items", kept.load_items)
    monkeypatch.setattr("komora.api.app.pantry_marks.add_item", kept.add_item)
    monkeypatch.setattr("komora.api.app.pantry_marks.drop_item", kept.drop_item)
    monkeypatch.setattr("komora.api.app.get_pool", lambda: None)
    return kept


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr("komora.api.app.place_of", _place)
    monkeypatch.setattr("komora.api.app.SilpoMCP", _Silpo)
    app.dependency_overrides[require_guest] = lambda: Session()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


async def _place(*_a: Any, **_kw: Any) -> None:
    return None


class _Silpo:
    def __init__(self, *_a: Any, **_kw: Any) -> None: ...

    async def __aenter__(self) -> _Silpo:
        return self

    async def __aexit__(self, *_exc: object) -> bool:
        return False


def test_a_written_kind_reaches_the_store(client: TestClient, store: _Store) -> None:
    response = client.post("/api/pantry/manual", json={"label": "васабі"})

    assert response.status_code == 200
    assert store.items == {("відбиток-акаунта", "pantry", "васабі"): "васабі"}


def test_a_store_that_did_not_answer_says_so_out_loud(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    dead = _DeadStore()
    monkeypatch.setattr("komora.api.app.pantry_marks.add_item", dead.add_item)
    monkeypatch.setattr("komora.api.app.get_pool", lambda: None)

    response = client.post("/api/pantry/manual", json={"label": "васабі"})

    assert response.status_code == 503
    assert "після оновлення" in response.json()["detail"]


def test_without_an_account_the_list_has_nowhere_to_live(
    client: TestClient, store: _Store, monkeypatch: pytest.MonkeyPatch
) -> None:

    class Anonymous(Session):
        account = ""

    app.dependency_overrides[require_guest] = lambda: Anonymous()

    response = client.post("/api/pantry/manual", json={"label": "васабі"})

    assert response.status_code == 409
    assert store.items == {}


def test_a_written_kind_can_be_taken_back(client: TestClient, store: _Store) -> None:
    store.items[("відбиток-акаунта", "pantry", "васабі")] = "васабі"

    response = client.delete(f"/api/pantry/manual/{manual_id('васабі')}")

    assert response.status_code == 204
    assert store.items == {}


def test_a_receipt_row_cannot_be_deleted_at_all(
    client: TestClient, store: _Store
) -> None:
    response = client.delete("/api/pantry/manual/42")

    assert response.status_code == 422
    assert "з чеків" in response.json()["detail"]


def test_a_dead_store_does_not_pretend_the_row_is_gone(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    dead = _DeadStore()
    dead.items[("відбиток-акаунта", "pantry", "васабі")] = "васабі"
    monkeypatch.setattr("komora.api.app.pantry_marks.load_items", dead.load_items)
    monkeypatch.setattr("komora.api.app.pantry_marks.drop_item", dead.drop_item)
    monkeypatch.setattr("komora.api.app.get_pool", lambda: None)

    response = client.delete(f"/api/pantry/manual/{manual_id('васабі')}")

    assert response.status_code == 503
    assert dead.items, "рядок лишився на місці, і відповідь це каже"


def test_adding_a_kind_never_touches_silpo(
    client: TestClient, store: _Store, monkeypatch: pytest.MonkeyPatch
) -> None:

    class _Dead:
        def __init__(self, *_a: Any, **_kw: Any) -> None: ...

        async def __aenter__(self) -> _Dead:
            raise AssertionError("додавання рядка комори не має ходити в «Сільпо»")

        async def __aexit__(self, *_exc: object) -> bool:
            return False

    monkeypatch.setattr("komora.api.app.SilpoMCP", _Dead)

    response = client.post("/api/pantry/manual", json={"label": "огірки"})

    assert response.status_code == 200
    assert response.json()["label"] == "огірки"
    assert store.items == {("відбиток-акаунта", "pantry", "огірки"): "огірки"}
