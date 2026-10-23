from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from komora.api.app import app
from komora.api.auth_routes import require_guest
from komora.api.schemas import Pantry, PantryItem


class Session:
    access = "живий-токен"
    refresh = "живий-refresh"
    owner = "власник-сесії"
    account = "відбиток-акаунта"


class _Store:

    def __init__(self) -> None:
        self.kinds: set[str] = set()

    async def load_hidden(self, _pool: Any, account: str) -> list[str]:
        return sorted(self.kinds)

    async def hide(self, _pool: Any, account: str, kind: str) -> None:
        self.kinds.add(kind)

    async def unhide(self, _pool: Any, account: str, kind: str) -> None:
        self.kinds.discard(kind)


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> _Store:
    kept = _Store()
    for name in ("load_hidden", "hide", "unhide"):
        monkeypatch.setattr(f"komora.api.app.pantry_marks.{name}", getattr(kept, name))
    monkeypatch.setattr("komora.api.app.get_pool", lambda: None)
    return kept


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, store: _Store) -> TestClient:
    asked: list[str] = []

    class _Silpo:
        def __init__(self, *_a: Any, **_kw: Any) -> None: ...

        async def __aenter__(self) -> Any:
            return self

        async def __aexit__(self, *_exc: object) -> bool:
            return False

    async def _place(*_a: Any, **_kw: Any) -> None:
        return None

    async def _paper(*_a: Any, **_kw: Any) -> object:
        return object()

    async def _kind(_mcp: Any, adjustment: Any, **_kw: Any) -> str:
        asked.append(str(adjustment.id))
        return str(adjustment.id)

    async def _pantry(*_a: Any, **kw: Any) -> Pantry:
        said = kw["said"]
        return Pantry(
            items=[
                PantryItem(id=key, label=key, unit="шт", state="оцінка")
                for key in sorted(said.hidden)
            ],
            receipts=9,
            orders=0,
            kinds=3,
            tracked_from=3,
            hidden=sorted(said.hidden),
            unlisted=0,
        )

    async def _nothing(*_a: Any, **_kw: Any) -> dict[str, Any]:
        return {}

    async def _mode(*_a: Any, **_kw: Any) -> str:
        return "receipts"

    monkeypatch.setattr("komora.api.app.SilpoMCP", _Silpo)
    monkeypatch.setattr("komora.api.app.place_of", _place)
    monkeypatch.setattr("komora.api.app._seen_receipts", _paper)
    monkeypatch.setattr("komora.api.app.name_kind", _kind)
    monkeypatch.setattr("komora.api.app.pantry_live", _pantry)
    monkeypatch.setattr("komora.api.app._marks_of", _nothing)
    monkeypatch.setattr("komora.api.app._manual_of", _nothing)
    monkeypatch.setattr("komora.api.app._cycles_of", _nothing)
    monkeypatch.setattr("komora.api.app._source_of", _mode)
    app.dependency_overrides[require_guest] = lambda: Session()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_the_word_is_written_and_not_just_drawn(client: TestClient, store: _Store) -> None:
    response = client.patch("/api/pantry", json={"id": "корм котячий", "action": "hide"})

    assert response.status_code == 200
    assert store.kinds == {"корм котячий"}


def test_hiding_is_reversible(client: TestClient, store: _Store) -> None:
    client.patch("/api/pantry", json={"id": "корм котячий", "action": "hide"})

    client.patch("/api/pantry", json={"id": "корм котячий", "action": "unhide"})

    assert store.kinds == set()


def test_hiding_twice_changes_nothing(client: TestClient, store: _Store) -> None:
    client.patch("/api/pantry", json={"id": "корм котячий", "action": "hide"})
    client.patch("/api/pantry", json={"id": "корм котячий", "action": "hide"})

    assert store.kinds == {"корм котячий"}


def test_what_was_hidden_comes_back_with_the_answer(
    client: TestClient, store: _Store
) -> None:
    body = client.patch(
        "/api/pantry", json={"id": "корм котячий", "action": "hide"}
    ).json()

    assert body["hidden"] == ["корм котячий"]
