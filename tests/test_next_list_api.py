from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from komora.api.app import app
from komora.api.auth_routes import require_guest
from komora.api.schemas import Pantry, PantryItem
from komora.db.wanted import Want

ACCOUNT = "відбиток-акаунта"


class Session:
    access = "живий-токен"
    refresh = "живий-refresh"
    owner = "власник-сесії"
    account = ACCOUNT


class _Store:

    def __init__(self) -> None:
        self.rows: dict[str, Want] = {}

    async def load(self, _pool: Any, account: str) -> dict[str, Want]:
        return dict(self.rows) if account == ACCOUNT else {}

    async def compose(self, _pool: Any, account: str, rows: dict[str, Want]) -> int:
        added = 0
        for kind, row in rows.items():
            if kind in self.rows:
                continue
            self.rows[kind] = Want(row.label, True, "agent", row.why)
            added += 1
        return added

    async def drop_agent(self, _pool: Any, account: str, kinds: Any) -> int:
        gone = [kind for kind in kinds if self.rows.get(kind, Want("")).origin == "agent"]
        for kind in gone:
            del self.rows[kind]
        return len(gone)


def _item(label: str, **extra) -> PantryItem:
    return PantryItem.model_validate(
        {"id": label, "label": label, "state": "оцінка", "unit": "шт", **extra}
    )


def _pantry(*items: PantryItem, gap: int = 3, limit: int = 14) -> Pantry:
    return Pantry(
        items=list(items),
        receipts=40,
        kinds=len(items),
        tracked_from=3,
        trip_gap=gap,
        list_limit=limit,
    )


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> _Store:
    kept = _Store()
    for name in ("load", "compose", "drop_agent"):
        monkeypatch.setattr(f"komora.api.app.wanted_store.{name}", getattr(kept, name))
    monkeypatch.setattr("komora.api.app.get_pool", lambda: None)
    return kept


@pytest.fixture
def client() -> TestClient:
    app.dependency_overrides[require_guest] = lambda: Session()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _shelf(monkeypatch: pytest.MonkeyPatch, pantry: Pantry) -> None:
    async def _now(*_a: Any, **_kw: Any) -> Pantry:
        return pantry

    monkeypatch.setattr("komora.api.app._pantry_now", _now)


def test_the_list_takes_what_ran_out_and_leaves_what_the_cycle_cannot_prove(
    client: TestClient, store: _Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    _shelf(
        monkeypatch,
        _pantry(
            _item("Хліб", running_out=True, days_left=0),
            _item("Кава"),
            _item("Молоко", days_left=2),
        ),
    )

    response = client.post("/api/pantry/next-list")

    assert response.status_code == 200
    body = response.json()
    assert [row["label"] for row in body["rows"]] == ["Хліб", "Молоко"]
    assert body["rows"][0]["why"] == "закінчилось сьогодні"
    assert body["changes"] == ["додав Хліб", "додав Молоко"]


def test_the_guests_own_row_survives_the_recount(
    client: TestClient, store: _Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    store.rows["батарейки"] = Want("батарейки", True, "guest", None)
    _shelf(monkeypatch, _pantry(_item("Хліб", running_out=True, days_left=0)))

    body = client.post("/api/pantry/next-list").json()

    assert {row["label"] for row in body["rows"]} == {"батарейки", "Хліб"}
    assert store.rows["батарейки"].origin == "guest"
    assert body["changes"] == ["додав Хліб"], "чуже слово не подія списку"


def test_what_no_longer_runs_out_is_taken_off_and_said_out_loud(
    client: TestClient, store: _Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    store.rows["кава"] = Want("Кава", True, "agent", "закінчилось сьогодні")
    _shelf(monkeypatch, _pantry(_item("Кава"), _item("Хліб", running_out=True, days_left=0)))

    body = client.post("/api/pantry/next-list").json()

    assert [row["label"] for row in body["rows"]] == ["Хліб"]
    assert body["changes"] == ["додав Хліб", "зняв Кава — більше не закінчується"]


def test_nothing_changed_is_a_legal_answer_and_it_says_so(
    client: TestClient, store: _Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    store.rows["хліб"] = Want("Хліб", True, "agent", "закінчилось сьогодні")
    _shelf(monkeypatch, _pantry(_item("Хліб", running_out=True, days_left=0)))

    body = client.post("/api/pantry/next-list").json()

    assert body["changes"] == []
    assert [row["label"] for row in body["rows"]] == ["Хліб"]
    assert "без агента" in body["note"], "чим складено -- теж відповідь (#209)"


def test_a_store_that_did_not_answer_says_so_out_loud(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:

    async def _dead(*_a: Any, **_kw: Any) -> Any:
        raise ConnectionError("сховище не відповідає")

    monkeypatch.setattr("komora.api.app.wanted_store.load", _dead)
    monkeypatch.setattr("komora.api.app.get_pool", lambda: None)
    _shelf(monkeypatch, _pantry(_item("Хліб", running_out=True, days_left=0)))

    response = client.post("/api/pantry/next-list")

    assert response.status_code == 503
    assert "не склався" in response.json()["detail"]
