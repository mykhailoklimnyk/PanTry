from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from komora.agent import basket, sanity
from komora.agent.basket import Keeps, Naming
from komora.api.app import app
from komora.api.auth_routes import require_guest
from komora.api.schemas import Pantry


class Session:
    access = "живий-токен"
    refresh = "живий-refresh"
    owner = "власник-сесії"
    account = "відбиток-акаунта"


@pytest.fixture
def seen() -> list[dict[str, Any]]:
    return []


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, seen: list[dict[str, Any]]) -> TestClient:
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
        seen.append(dict(kw))
        return Pantry(
            items=[], receipts=0, orders=0, kinds=0, tracked_from=3, hidden=[], unlisted=0
        )

    async def _nothing(*_a: Any, **_kw: Any) -> dict[str, Any]:
        return {}

    async def _mode(*_a: Any, **_kw: Any) -> str:
        return "receipts"

    monkeypatch.setattr("komora.api.app.SilpoMCP", _Silpo)
    monkeypatch.setattr("komora.api.app.place_of", _place)
    monkeypatch.setattr("komora.api.app._seen_receipts", _paper)
    monkeypatch.setattr("komora.api.app.pantry_live", _pantry)
    monkeypatch.setattr("komora.api.app._marks_of", _nothing)
    monkeypatch.setattr("komora.api.app._manual_of", _nothing)
    monkeypatch.setattr("komora.api.app._cycles_of", _nothing)
    monkeypatch.setattr("komora.api.app._source_of", _mode)
    monkeypatch.setattr("komora.api.app.get_pool", lambda: None)
    app.dependency_overrides[require_guest] = lambda: Session()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_a_cold_opening_keeps_another_guests_process_memory(client: TestClient) -> None:
    basket._cache_names({"Молоко Яготинське 2,5%": Naming(intent="молоко", subtype="")})
    basket._KEEPS_CACHE["молоко"] = Keeps.DAYS
    sanity._CACHE["молоко"] = sanity.facts_store.Facts(sanity="норма")

    assert client.get("/api/pantry?cold=true").status_code == 200

    assert basket._cached_name("Молоко Яготинське 2,5%") is not None
    assert "молоко" in basket._KEEPS_CACHE
    assert "молоко" in sanity._CACHE


def test_a_cold_opening_still_draws_without_any_cache(
    client: TestClient, seen: list[dict[str, Any]]
) -> None:
    client.get("/api/pantry?cold=true")

    assert seen[-1]["use_cache"] is False
