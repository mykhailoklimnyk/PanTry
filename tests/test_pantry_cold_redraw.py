from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi.testclient import TestClient

from komora.agent.steps.pantry import Home
from komora.api.app import app
from komora.api.auth_routes import require_guest
from komora.api.schemas import Pantry, PantryItem
from komora.core.said import Said


class Session:
    access = "живий-токен"
    refresh = "живий-refresh"
    owner = "власник-сесії"
    account = "відбиток-акаунта"


def _empty() -> Pantry:
    return Pantry(items=[], receipts=0, orders=0, kinds=0, tracked_from=3, hidden=[], unlisted=0)


class _Ground:

    mcp = None
    llm = None
    cfg = None
    moment = None
    pool = None
    account = "відбиток-акаунта"


@pytest.fixture
def drawn(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    seen: list[dict[str, Any]] = []

    async def _pantry(*_a: Any, **kw: Any) -> Pantry:
        seen.append(dict(kw))
        return _empty()

    monkeypatch.setattr("komora.agent.steps.pantry.pantry_live", _pantry)
    return seen


def _home(*, cold: bool) -> Home:
    return Home(
        _Ground(),  # type: ignore[arg-type]
        said=Said(),
        read=object(),  # type: ignore[arg-type]
        drawn=_empty(),
        cold=cold,
    )


def test_a_cold_loop_redraws_without_the_eternal_cache(drawn: list[dict[str, Any]]) -> None:
    asyncio.run(_home(cold=True).draw({}))

    assert drawn[-1]["use_cache"] is False


def test_a_warm_loop_redraws_with_it(drawn: list[dict[str, Any]]) -> None:
    asyncio.run(_home(cold=False).draw({}))

    assert drawn[-1]["use_cache"] is True


def test_the_redraw_always_reads_process_memory(drawn: list[dict[str, Any]]) -> None:
    asyncio.run(_home(cold=True).draw({}))

    assert drawn[-1]["memory"] is True


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

    async def _kind(_mcp: Any, adjustment: Any, **_kw: Any) -> str:
        return str(adjustment.id)

    async def _mark(*_a: Any, **_kw: Any) -> dict[str, Any]:
        return {}

    async def _pantry(*_a: Any, **kw: Any) -> Pantry:
        seen.append(dict(kw))
        return Pantry(
            items=[PantryItem(id="молоко", label="молоко", unit="шт", state="оцінка")],
            receipts=9,
            orders=0,
            kinds=3,
            tracked_from=3,
            hidden=[],
            unlisted=0,
        )

    async def _nothing(*_a: Any, **_kw: Any) -> dict[str, Any]:
        return {}

    async def _mode(*_a: Any, **_kw: Any) -> str:
        return "receipts"

    async def _save(*_a: Any, **_kw: Any) -> None:
        return None

    monkeypatch.setattr("komora.api.app.SilpoMCP", _Silpo)
    monkeypatch.setattr("komora.api.app.place_of", _place)
    monkeypatch.setattr("komora.api.app._seen_receipts", _paper)
    monkeypatch.setattr("komora.api.app.name_kind", _kind)
    monkeypatch.setattr("komora.api.app.mark_pantry", _mark)
    monkeypatch.setattr("komora.api.app.pantry_live", _pantry)
    monkeypatch.setattr("komora.api.app.pantry_marks.save", _save)
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


@pytest.fixture
def seen() -> list[dict[str, Any]]:
    return []


def test_a_touch_in_a_cold_session_redraws_cold(
    client: TestClient, seen: list[dict[str, Any]]
) -> None:
    response = client.patch("/api/pantry?cold=true", json={"id": "молоко", "action": "bought"})

    assert response.status_code == 200
    assert seen[-1]["use_cache"] is False
    assert seen[-1]["memory"] is True


def test_a_touch_without_the_switch_reads_the_cache_as_before(
    client: TestClient, seen: list[dict[str, Any]]
) -> None:
    client.patch("/api/pantry", json={"id": "молоко", "action": "bought"})

    assert seen[-1]["use_cache"] is True
