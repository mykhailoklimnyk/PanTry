from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from komora.agent.basket import HistoryItem
from komora.api.app import app
from komora.api.auth_routes import require_guest
from komora.api.schemas import Pantry
from komora.core.levels import Seen
from komora.db import swaps as saved_swaps

NOW = datetime(2026, 9, 8, tzinfo=UTC)
KIND = "йогурт живинка"


class Session:
    access = "живий-токен"
    refresh = "живий-refresh"
    owner = "власник-сесії"
    account = "відбиток-акаунта"


class _Store:

    def __init__(self) -> None:
        self.rows: dict[str, saved_swaps.Saved] = {}
        self.broken = False

    async def save(self, _pool: Any, _account: str, rows: dict[str, saved_swaps.Saved]) -> int:
        if self.broken:
            raise RuntimeError("сховище не відповіло")
        self.rows.update(rows)
        return len(rows)

    async def drop(self, _pool: Any, _account: str, kind: str) -> int:
        if self.broken:
            raise RuntimeError("сховище не відповіло")
        return 1 if self.rows.pop(kind, None) is not None else 0


def _row() -> HistoryItem:
    return HistoryItem(
        lager_id="101",
        name="Йогурт Живинка питний 1,5% 300г",
        unit="300г",
        receipts=9,
        qty_total=Decimal(9),
        moments=[NOW],
        sources=[
            Seen(
                label="Йогурт Живинка питний",
                unit="300г",
                receipts=6,
                days_since=3,
                article="101",
            ),
            Seen(
                label="Йогурт Галичина питний",
                unit="300г",
                receipts=3,
                days_since=9,
                article="102",
            ),
        ],
    )


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> _Store:
    kept = _Store()
    for name in ("save", "drop"):
        monkeypatch.setattr(f"komora.api.app.saved_swaps.{name}", getattr(kept, name))
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

    async def _resolve(*_a: Any, **_kw: Any) -> HistoryItem:
        return _row()

    async def _pantry(*_a: Any, **_kw: Any) -> Pantry:
        return Pantry(
            items=[], receipts=9, orders=0, kinds=3, tracked_from=3, hidden=[], unlisted=0
        )

    async def _nothing(*_a: Any, **_kw: Any) -> dict[str, Any]:
        return {}

    async def _mode(*_a: Any, **_kw: Any) -> str:
        return "receipts"

    monkeypatch.setattr("komora.api.app.SilpoMCP", _Silpo)
    monkeypatch.setattr("komora.api.app.place_of", _place)
    monkeypatch.setattr("komora.api.app._seen_receipts", _paper)
    monkeypatch.setattr("komora.agent.basket.resolve_kind", _resolve)
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


def test_the_signed_mandate_lands_under_the_kind_of_the_receipt(
    client: TestClient, store: _Store
) -> None:
    response = client.patch(
        "/api/pantry", json={"id": "101", "action": "mandate", "chain": ["102"]}
    )

    assert response.status_code == 200
    assert list(store.rows) == [KIND]
    assert [link.article for link in store.rows[KIND].links] == ["102"]


def test_the_link_name_comes_from_the_receipts_and_not_from_the_request(
    client: TestClient, store: _Store
) -> None:
    client.patch("/api/pantry", json={"id": "101", "action": "mandate", "chain": ["102"]})

    (link,) = store.rows[KIND].links
    assert link.name == "Йогурт Галичина питний"


def test_an_article_outside_the_guests_own_purchases_is_refused_aloud(
    client: TestClient, store: _Store
) -> None:
    response = client.patch(
        "/api/pantry", json={"id": "101", "action": "mandate", "chain": ["102", "999"]}
    )

    assert response.status_code == 409
    assert not store.rows, "півмандата гірше за нуль: гість не має як зрозуміти, яка половина"


def test_the_head_of_the_row_is_not_a_link(client: TestClient, store: _Store) -> None:
    response = client.patch(
        "/api/pantry", json={"id": "101", "action": "mandate", "chain": ["101"]}
    )

    assert response.status_code == 409


def test_forgetting_the_mandate_removes_it_and_does_not_empty_it(
    client: TestClient, store: _Store
) -> None:
    store.rows[KIND] = saved_swaps.Saved("Йогурт Живинка", (saved_swaps.Link("102", "Галичина"),))

    response = client.patch("/api/pantry", json={"id": "101", "action": "forget_mandate"})

    assert response.status_code == 200
    assert not store.rows


def test_an_empty_chain_is_a_refusal_and_not_a_way_to_forget(
    client: TestClient, store: _Store
) -> None:
    store.rows[KIND] = saved_swaps.Saved("Йогурт Живинка", (saved_swaps.Link("102", "Галичина"),))

    response = client.patch("/api/pantry", json={"id": "101", "action": "mandate", "chain": []})

    assert response.status_code == 409
    assert store.rows, "порожній перелік не має права мовчки знімати підписане"


def test_a_dead_store_says_so_on_the_write(client: TestClient, store: _Store) -> None:
    store.broken = True

    response = client.patch(
        "/api/pantry", json={"id": "101", "action": "mandate", "chain": ["102"]}
    )

    assert response.status_code == 503
