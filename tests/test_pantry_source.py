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
        self.mode: dict[tuple[str, str], str] = {}
        self.items: dict[tuple[str, str, str], str] = {}
        self.origins: dict[tuple[str, str, str], str] = {}
        self.wiped = 0

    async def load_source(self, _pool: Any, account: str, scope: str) -> str:
        return self.mode.get((account, scope), "receipts")

    async def save_source(self, _pool: Any, account: str, scope: str, mode: str) -> None:
        self.mode[(account, scope)] = mode

    async def load_items(
        self, _pool: Any, account: str, *, scope: str, origin: str | None = None
    ) -> dict[str, str]:
        return {
            kind: label
            for (owner, area, kind), label in self.items.items()
            if owner == account
            and area == scope
            and (origin is None or self.origins.get((owner, area, kind), "guest") == origin)
        }

    async def add_items(
        self, _pool: Any, account: str, rows: dict[str, str], *, scope: str, origin: str
    ) -> int:
        for kind, label in rows.items():
            self.items[(account, scope, kind)] = label
            self.origins[(account, scope, kind)] = origin
        return len(rows)

    async def wipe_items(self, _pool: Any, account: str, *, scope: str) -> int:
        gone = [key for key in self.items if key[0] == account and key[1] == scope]
        for key in gone:
            del self.items[key]
        self.wiped += 1
        return len(gone)


def _row(label: str, *, source: str, named: bool = True) -> PantryItem:
    return PantryItem(
        id=f"id:{label}",
        label=label,
        unit="шт",
        state="оцінка",
        source=source,
        named=named,
    )


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> _Store:
    kept = _Store()
    for name in ("load_source", "save_source", "load_items", "add_items", "wipe_items"):
        monkeypatch.setattr(f"komora.api.app.pantry_marks.{name}", getattr(kept, name))
    monkeypatch.setattr("komora.api.app.get_pool", lambda: None)
    return kept


@pytest.fixture
def seen(monkeypatch: pytest.MonkeyPatch, store: _Store) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    async def fake(*_a: Any, **kw: Any) -> Pantry:
        calls.append(kw)
        rows = [
            _row("Хліб", source="receipts"),
            _row("Молоко", source="receipts"),
            _row("Гречка Сквирянка", source="receipts", named=False),
        ]
        if kw["said"].source == "manual":
            written = await store.load_items(None, "відбиток-акаунта", scope="pantry")
            rows = [_row(label, source="manual") for label in written.values()]
        return Pantry(
            items=rows,
            receipts=9,
            orders=3,
            kinds=12,
            tracked_from=3,
            source=kw["said"].source,
            unlisted=0,
        )

    monkeypatch.setattr("komora.api.app.pantry_live", fake)
    return calls


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    async def _place(*_a: Any, **_kw: Any) -> None:
        return None

    class _Silpo:
        def __init__(self, *_a: Any, **_kw: Any) -> None: ...

        async def __aenter__(self) -> _Silpo:
            return self

        async def __aexit__(self, *_exc: object) -> bool:
            return False

    async def _paper(_mcp: Any, _guest: Any, *, fresh: bool, place: Any) -> Any:
        return object()

    monkeypatch.setattr("komora.api.app._seen_receipts", _paper)
    monkeypatch.setattr("komora.api.app.place_of", _place)
    monkeypatch.setattr("komora.api.app.SilpoMCP", _Silpo)
    app.dependency_overrides[require_guest] = lambda: Session()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_by_default_the_list_is_filled_by_purchases(
    client: TestClient, store: _Store, seen: list[dict[str, Any]]
) -> None:
    body = client.get("/api/pantry").json()

    assert body["source"] == "receipts"
    assert seen[0]["said"].source == "receipts"


def test_the_choice_reaches_the_store_and_the_screen(
    client: TestClient, store: _Store, seen: list[dict[str, Any]]
) -> None:
    body = client.put("/api/pantry/source", json={"mode": "manual"}).json()

    assert store.mode == {("відбиток-акаунта", "pantry"): "manual"}
    assert body["source"] == "manual"


def test_a_foreign_mode_is_refused_by_the_port(client: TestClient, store: _Store) -> None:
    assert client.put("/api/pantry/source", json={"mode": "будь-що"}).status_code == 422
    assert store.mode == {}


def test_a_store_that_did_not_answer_says_so_out_loud(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, store: _Store
) -> None:

    async def dead(*_a: Any, **_kw: Any) -> None:
        raise ConnectionError("сховище не відповідає")

    monkeypatch.setattr("komora.api.app.pantry_marks.save_source", dead)

    response = client.put("/api/pantry/source", json={"mode": "manual"})

    assert response.status_code == 503
    assert "не зберігся" in response.json()["detail"]


def test_a_dead_store_leaves_the_pantry_working(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, seen: list[dict[str, Any]]
) -> None:

    async def dead(*_a: Any, **_kw: Any) -> str:
        raise ConnectionError("сховище не відповідає")

    monkeypatch.setattr("komora.api.app.pantry_marks.load_source", dead)

    assert client.get("/api/pantry").json()["source"] == "receipts"


def test_generating_from_purchases_fills_the_list(
    client: TestClient, store: _Store, seen: list[dict[str, Any]]
) -> None:
    body = client.post("/api/pantry/generate").json()

    assert set(store.items.values()) == {"Хліб", "Молоко"}
    assert body["items"], "назад їде ПЕРЕрахована комора, а не стан до дії"


def test_generating_twice_does_not_double_the_list(
    client: TestClient, store: _Store, seen: list[dict[str, Any]]
) -> None:
    client.post("/api/pantry/generate")
    client.post("/api/pantry/generate")

    assert len(store.items) == 2


def test_wiping_clears_only_what_the_guest_wrote(
    client: TestClient, store: _Store, seen: list[dict[str, Any]]
) -> None:
    client.post("/api/pantry/generate")
    assert store.items

    body = client.delete("/api/pantry/items").json()

    assert store.items == {}
    assert [item["label"] for item in body["items"]] == [
        "Хліб",
        "Молоко",
        "Гречка Сквирянка",
    ], "у режимі чеків список стерто, а комора рахується далі"


def test_an_empty_list_in_guest_mode_is_not_the_same_as_an_untouched_one(
    client: TestClient, store: _Store, seen: list[dict[str, Any]]
) -> None:
    client.put("/api/pantry/source", json={"mode": "manual"})
    body = client.delete("/api/pantry/items").json()

    assert body["items"] == []
    assert body["source"] == "manual", "порожньо, але це ВИБІР гостя, а не порожнеча"


def test_every_action_answers_with_a_recomputed_pantry(
    client: TestClient, store: _Store, seen: list[dict[str, Any]]
) -> None:
    for call in (
        lambda: client.put("/api/pantry/source", json={"mode": "manual"}),
        lambda: client.post("/api/pantry/generate"),
        lambda: client.delete("/api/pantry/items"),
    ):
        response = call()
        assert response.status_code == 200
        assert "source" in response.json()


def test_an_unnamed_kind_does_not_land_in_the_list(
    client: TestClient, store: _Store, seen: list[dict[str, Any]]
) -> None:
    client.post("/api/pantry/generate")

    assert "Гречка Сквирянка" not in set(store.items.values())


def _typed(store: _Store, kind: str, label: str) -> None:
    store.items[("відбиток-акаунта", "pantry", kind)] = label
    store.origins[("відбиток-акаунта", "pantry", kind)] = "guest"


def test_the_receipts_mode_does_not_read_what_was_generated_from_purchases(
    client: TestClient, store: _Store, seen: list[dict[str, Any]]
) -> None:
    client.post("/api/pantry/generate")
    seen.clear()

    client.get("/api/pantry")

    assert seen[-1]["said"].source == "receipts"
    assert seen[-1]["said"].listed == {}


def test_the_guest_own_words_survive_the_receipts_mode(
    client: TestClient, store: _Store, seen: list[dict[str, Any]]
) -> None:
    _typed(store, "васабі", "Васабі")
    client.post("/api/pantry/generate")
    seen.clear()

    client.get("/api/pantry")

    assert seen[-1]["said"].listed == {"васабі": "Васабі"}


def test_the_list_mode_reads_both_what_was_typed_and_what_was_generated(
    client: TestClient, store: _Store, seen: list[dict[str, Any]]
) -> None:
    _typed(store, "васабі", "Васабі")
    client.post("/api/pantry/generate")
    client.put("/api/pantry/source", json={"mode": "manual"})
    seen.clear()

    client.get("/api/pantry")

    read = seen[-1]["said"].listed
    assert read["васабі"] == "Васабі"
    assert len(read) > 1
