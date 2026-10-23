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
        self.intents: set[str] = set()
        self.scopes: list[str] = []

    async def load_splits(self, _pool: Any, _account: str, *, scope: str) -> list[str]:
        self.scopes.append(scope)
        return sorted(self.intents)

    async def split(self, _pool: Any, _account: str, intent: str, *, scope: str) -> None:
        self.scopes.append(scope)
        self.intents.add(intent)

    async def unsplit(self, _pool: Any, _account: str, intent: str, *, scope: str) -> None:
        self.scopes.append(scope)
        self.intents.discard(intent)


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> _Store:
    kept = _Store()
    for name in ("load_splits", "split", "unsplit"):
        monkeypatch.setattr(f"komora.api.app.pantry_marks.{name}", getattr(kept, name))
    monkeypatch.setattr("komora.api.app.get_pool", lambda: None)
    return kept


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, store: _Store) -> TestClient:

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

    async def _pantry(*_a: Any, **kw: Any) -> Pantry:
        said = kw["said"]
        return Pantry(
            items=[
                PantryItem(id=name, label=name, unit="шт", state="оцінка", group=name)
                for name in sorted(said.apart)
            ],
            receipts=9,
            orders=0,
            kinds=3,
            tracked_from=3,
            unlisted=0,
        )

    async def _nothing(*_a: Any, **_kw: Any) -> dict[str, Any]:
        return {}

    async def _empty(*_a: Any, **_kw: Any) -> list[str]:
        return []

    async def _mode(*_a: Any, **_kw: Any) -> str:
        return "receipts"

    monkeypatch.setattr("komora.api.app.SilpoMCP", _Silpo)
    monkeypatch.setattr("komora.api.app.place_of", _place)
    monkeypatch.setattr("komora.api.app._seen_receipts", _paper)
    monkeypatch.setattr("komora.api.app.pantry_live", _pantry)
    monkeypatch.setattr("komora.api.app._marks_of", _nothing)
    monkeypatch.setattr("komora.api.app._manual_of", _nothing)
    monkeypatch.setattr("komora.api.app._cycles_of", _nothing)
    monkeypatch.setattr("komora.api.app._hidden_of", _empty)
    monkeypatch.setattr("komora.api.app._source_of", _mode)
    app.dependency_overrides[require_guest] = lambda: Session()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_the_word_is_written_and_not_just_drawn(client: TestClient, store: _Store) -> None:
    answer = client.patch("/api/pantry", json={"id": "", "action": "split", "group": "йогурт"})

    assert answer.status_code == 200
    assert store.intents == {"йогурт"}


def test_the_answer_already_shows_the_split(client: TestClient, store: _Store) -> None:
    answer = client.patch("/api/pantry", json={"id": "", "action": "split", "group": "йогурт"})

    assert [row["group"] for row in answer.json()["items"]] == ["йогурт"]


def test_splitting_is_reversible(client: TestClient, store: _Store) -> None:
    client.patch("/api/pantry", json={"id": "", "action": "split", "group": "йогурт"})

    answer = client.patch("/api/pantry", json={"id": "", "action": "unsplit", "group": "йогурт"})

    assert answer.status_code == 200
    assert store.intents == set()
    assert answer.json()["items"] == []


def test_the_intent_is_tidied_before_it_becomes_a_key(client: TestClient, store: _Store) -> None:
    client.patch("/api/pantry", json={"id": "", "action": "split", "group": "  вода   питна  "})

    assert store.intents == {"вода питна"}


def test_an_empty_intent_is_refused_and_writes_nothing(client: TestClient, store: _Store) -> None:
    answer = client.patch("/api/pantry", json={"id": "", "action": "split", "group": "   "})

    assert answer.status_code == 422
    assert store.intents == set()


def test_the_split_lives_in_the_pantry_scope(client: TestClient, store: _Store) -> None:
    client.patch("/api/pantry", json={"id": "", "action": "split", "group": "йогурт"})

    assert set(store.scopes) == {"pantry"}


def test_the_shared_naming_cache_is_never_touched(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, store: _Store
) -> None:
    written: list[object] = []

    async def _save(*args: Any, **kw: Any) -> None:
        written.append((args, kw))

    monkeypatch.setattr("komora.db.intents.save", _save)

    client.patch("/api/pantry", json={"id": "", "action": "split", "group": "йогурт"})
    client.patch("/api/pantry", json={"id": "", "action": "unsplit", "group": "йогурт"})

    assert written == []
