from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from komora.api.app import app
from komora.api.auth_routes import require_guest
from komora.api.schemas import Bar, BarItem
from komora.core.bar import DrinkKind
from komora.core.pantry import manual_id


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
        self.drinks: dict[tuple[str, str], str] = {}

    async def load_drinks(self, _pool: Any, account: str) -> dict[str, DrinkKind]:
        return {
            kind: DrinkKind(group)
            for (owner, kind), group in self.drinks.items()
            if owner == account
        }

    async def save_drink(self, _pool: Any, account: str, kind: str, group: str) -> None:
        self.drinks[(account, kind)] = group

    async def drop_drink(self, _pool: Any, account: str, kind: str) -> None:
        self.drinks.pop((account, kind), None)

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
            if owner == account and area == scope
        }

    async def add_item(
        self, _pool: Any, account: str, kind: str, label: str, *, scope: str
    ) -> None:
        self.items[(account, scope, kind)] = label

    async def add_items(
        self, _pool: Any, account: str, rows: dict[str, str], *, scope: str, origin: str
    ) -> int:
        for kind, label in rows.items():
            self.items[(account, scope, kind)] = label
            self.origins[(account, scope, kind)] = origin
        return len(rows)

    async def drop_item(self, _pool: Any, account: str, kind: str, *, scope: str) -> None:
        self.items.pop((account, scope, kind), None)

    async def wipe_items(self, _pool: Any, account: str, *, scope: str) -> int:
        gone = [key for key in self.items if key[0] == account and key[1] == scope]
        for key in gone:
            del self.items[key]
        return len(gone)


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> _Store:
    kept = _Store()
    for name in (
        "load_source",
        "save_source",
        "load_items",
        "add_item",
        "add_items",
        "drop_item",
        "wipe_items",
        "load_drinks",
        "save_drink",
        "drop_drink",
    ):
        monkeypatch.setattr(f"komora.api.app.pantry_marks.{name}", getattr(kept, name))
    monkeypatch.setattr("komora.api.app.get_pool", lambda: None)
    return kept


@pytest.fixture
def seen(monkeypatch: pytest.MonkeyPatch, store: _Store) -> list[dict[str, Any]]:
    calls: list[dict[str, Any]] = []

    async def fake(*_a: Any, **kw: Any) -> Bar:
        calls.append(kw)
        rows = [BarItem(id="light|пиво", label="пиво", kind="light", times=3)]
        if kw["said"].source == "manual":
            rows = [
                BarItem(id=manual_id(kind), label=label, source="manual")
                for kind, label in kw["said"].listed.items()
            ]
        return Bar(
            items=rows,
            receipts=9,
            orders=3,
            kinds=12,
            named=4,
            tracked_from=3,
            source=kw["said"].source,
        )

    monkeypatch.setattr("komora.api.app.bar_live", fake)
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


def test_the_written_kind_lands_in_the_bar_and_not_in_the_pantry(
    client: TestClient, store: _Store, seen: list[dict[str, Any]]
) -> None:
    response = client.post("/api/bar/manual", json={"label": "віскі"})

    assert response.status_code == 200
    assert store.items == {("відбиток-акаунта", "bar", "віскі"): "віскі"}


def test_wiping_the_bar_leaves_the_pantry_alone(
    client: TestClient, store: _Store, seen: list[dict[str, Any]]
) -> None:
    store.items[("відбиток-акаунта", "pantry", "хліб")] = "хліб"
    store.items[("відбиток-акаунта", "bar", "віскі")] = "віскі"

    assert client.delete("/api/bar/items").status_code == 200

    assert store.items == {("відбиток-акаунта", "pantry", "хліб"): "хліб"}


def test_the_bar_flag_is_its_own(
    client: TestClient, store: _Store, seen: list[dict[str, Any]]
) -> None:
    assert client.put("/api/bar/source", json={"mode": "manual"}).status_code == 200

    assert store.mode == {("відбиток-акаунта", "bar"): "manual"}
    assert seen[-1]["said"].source == "manual"


def test_generating_the_bar_fills_it_from_the_counted_rows(
    client: TestClient, store: _Store, seen: list[dict[str, Any]]
) -> None:
    assert client.post("/api/bar/generate").status_code == 200

    assert store.items == {("відбиток-акаунта", "bar", "пиво"): "пиво"}


def test_a_row_counted_from_receipts_cannot_be_taken_back(
    client: TestClient, store: _Store, seen: list[dict[str, Any]]
) -> None:
    response = client.delete("/api/bar/manual/light|пиво")

    assert response.status_code == 404


def test_a_written_row_can_be_taken_back(
    client: TestClient, store: _Store, seen: list[dict[str, Any]]
) -> None:
    store.items[("відбиток-акаунта", "bar", "віскі")] = "віскі"

    response = client.delete(f"/api/bar/manual/{manual_id('віскі')}")

    assert response.status_code == 200
    assert store.items == {}


def test_every_action_answers_with_a_recomputed_bar(
    client: TestClient, store: _Store, seen: list[dict[str, Any]]
) -> None:
    before = len(seen)
    client.put("/api/bar/source", json={"mode": "manual"})
    client.post("/api/bar/manual", json={"label": "віскі"})
    client.post("/api/bar/generate")
    client.delete("/api/bar/items")

    assert len(seen) - before == 5


def test_an_empty_label_is_refused_before_the_store(
    client: TestClient, store: _Store, seen: list[dict[str, Any]]
) -> None:
    assert client.post("/api/bar/manual", json={"label": "   "}).status_code == 422
    assert store.items == {}


def test_the_word_about_a_shelf_lands_under_the_kind_not_the_row(
    client: TestClient, store: _Store, seen: list[dict[str, Any]]
) -> None:
    response = client.put("/api/bar/group", json={"label": "Лікер Oakheart", "kind": "strong"})

    assert response.status_code == 200
    assert store.drinks == {("відбиток-акаунта", "лікер oakheart"): "strong"}
    assert seen[-1]["said"].drinks == {"лікер oakheart": DrinkKind.STRONG}


def test_the_guest_can_take_his_word_back(
    client: TestClient, store: _Store, seen: list[dict[str, Any]]
) -> None:
    store.drinks[("відбиток-акаунта", "лікер")] = "strong"

    assert client.put("/api/bar/group", json={"label": "лікер", "kind": None}).status_code == 200

    assert store.drinks == {}


def test_the_word_goes_to_the_bar_and_never_to_the_naming_cache(
    client: TestClient, store: _Store, seen: list[dict[str, Any]]
) -> None:
    client.put("/api/bar/group", json={"label": "лікер", "kind": "strong"})

    assert store.items == {}, "полиця -- позначка ПОВЕРХ здогаду, а не рядок списку"


def test_an_empty_label_is_refused_before_the_store_here_too(
    client: TestClient, store: _Store, seen: list[dict[str, Any]]
) -> None:
    assert client.put("/api/bar/group", json={"label": " ", "kind": "strong"}).status_code == 422
    assert store.drinks == {}


def test_a_shelf_that_is_not_ours_never_reaches_the_store(
    client: TestClient, store: _Store, seen: list[dict[str, Any]]
) -> None:
    assert client.put("/api/bar/group", json={"label": "лікер", "kind": "ром"}).status_code == 422
    assert store.drinks == {}


def test_the_shelf_answers_with_a_recomputed_bar(
    client: TestClient, store: _Store, seen: list[dict[str, Any]]
) -> None:
    before = len(seen)
    client.put("/api/bar/group", json={"label": "лікер", "kind": "wine"})

    assert len(seen) - before == 1
