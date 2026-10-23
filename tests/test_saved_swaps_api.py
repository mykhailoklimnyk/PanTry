from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pytest
from fastapi.testclient import TestClient

from komora.api.app import app
from komora.api.auth_routes import require_guest
from komora.core.pantry import manual_id
from komora.db.swaps import Link, Saved


class Session:
    access = "живий-токен"
    refresh = "живий-refresh"
    owner = "власник-сесії"
    account = "відбиток-акаунта"


class _Store:

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], Saved] = {}

    async def load(self, _pool: Any, account: str) -> dict[str, Saved]:
        return {kind: row for (owner, kind), row in self.rows.items() if owner == account}

    async def save(self, _pool: Any, account: str, rows: dict[str, Saved]) -> int:
        for kind, row in rows.items():
            self.rows[(account, kind)] = row
        return len(rows)

    async def drop(self, _pool: Any, account: str, kind: str) -> int:
        return 1 if self.rows.pop((account, kind), None) is not None else 0


@dataclass
class _Alt:
    external_product_id: str
    name: str


@dataclass
class _Line:
    intent: str
    product: dict[str, Any]
    chain: tuple[_Alt, ...]


@dataclass
class _Plan:
    lines: list[_Line]


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> _Store:
    kept = _Store()
    for name in ("load", "save", "drop"):
        monkeypatch.setattr(f"komora.api.app.saved_swaps.{name}", getattr(kept, name))
    monkeypatch.setattr("komora.api.app.get_pool", lambda: None)
    return kept


@pytest.fixture
def client() -> TestClient:
    app.dependency_overrides[require_guest] = lambda: Session()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _swap_stand(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = _Plan(
        [
            _Line(
                "молоко",
                {"externalProductId": "101"},
                (_Alt("103", "Молоко Ферма"), _Alt("102", "Молоко Яготинське")),
            )
        ]
    )
    monkeypatch.setattr("komora.api.app.runs.recall", lambda *_a, **_kw: plan)
    monkeypatch.setattr("komora.api.app.swaps.apply", lambda run, _d: run)
    monkeypatch.setattr("komora.api.app.runs.remember", lambda run, **_kw: _basket())


def _basket() -> Any:
    from komora.api.schemas import Basket, RunStats

    return Basket(
        run_id="run-1",
        lines=[],
        trace=[],
        total=Decimal("0"),
        delivery_cost=Decimal("0"),
        total_weight_kg=Decimal("0"),
        stats=RunStats(
            receipts=0,
            cycled=0,
            mcp_calls=0,
            duration_ms=0,
            cost_usd=Decimal("0"),
            model="fake",
        ),
    )


def test_nothing_is_remembered_without_an_explicit_yes(
    client: TestClient, store: _Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    _swap_stand(monkeypatch)

    response = client.post(
        "/api/basket/run-1/swaps",
        json={"swaps": [{"externalProductId": "101", "chain": ["103", "102"]}]},
    )

    assert response.status_code == 200
    assert store.rows == {}


def test_an_explicit_yes_saves_under_the_kind_not_the_article(
    client: TestClient, store: _Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    _swap_stand(monkeypatch)

    client.post(
        "/api/basket/run-1/swaps",
        json={
            "swaps": [{"externalProductId": "101", "chain": ["103", "102"]}],
            "remember": True,
        },
    )

    assert store.rows == {
        ("відбиток-акаунта", "молоко"): Saved(
            "молоко", (Link("103", "Молоко Ферма"), Link("102", "Молоко Яготинське"))
        )
    }


def test_a_row_the_guest_never_saw_is_not_remembered(
    client: TestClient, store: _Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    _swap_stand(monkeypatch)

    client.post(
        "/api/basket/run-1/swaps",
        json={
            "swaps": [{"externalProductId": "999", "chain": ["103"]}],
            "remember": True,
        },
    )

    assert store.rows == {}


def test_a_dead_store_does_not_break_the_agreement(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:

    async def boom(*_a: Any, **_kw: Any) -> int:
        raise ConnectionError("сховище не відповідає")

    monkeypatch.setattr("komora.api.app.saved_swaps.save", boom)
    monkeypatch.setattr("komora.api.app.get_pool", lambda: None)
    _swap_stand(monkeypatch)

    response = client.post(
        "/api/basket/run-1/swaps",
        json={
            "swaps": [{"externalProductId": "101", "chain": ["103"]}],
            "remember": True,
        },
    )

    assert response.status_code == 200


def test_the_saved_list_names_what_the_guest_signed(
    client: TestClient, store: _Store
) -> None:
    store.rows[("відбиток-акаунта", "молоко")] = Saved(
        "молоко", (Link("103", "Молоко Ферма"),)
    )

    rows = client.get("/api/swaps/saved").json()

    assert rows == [
        {"id": manual_id("молоко"), "label": "молоко", "links": ["Молоко Ферма"]}
    ]


def test_an_agreement_can_be_taken_back(client: TestClient, store: _Store) -> None:
    store.rows[("відбиток-акаунта", "молоко")] = Saved("молоко", (Link("103", "Ферма"),))

    response = client.delete(f"/api/swaps/saved/{manual_id('молоко')}")

    assert response.status_code == 200
    assert store.rows == {}


def test_an_id_without_the_fingerprint_is_not_an_agreement(
    client: TestClient, store: _Store
) -> None:
    assert client.delete("/api/swaps/saved/молоко").status_code == 404


def test_a_link_the_guest_found_by_search_is_what_gets_remembered(
    client: TestClient, store: _Store, monkeypatch: pytest.MonkeyPatch
) -> None:
    from komora.agent.basket import Assembled, PlanLine
    from komora.agent.swaps import remember_options
    from komora.api.schemas import Basket, RunStats, SwapOption

    def _card(article: str, name: str) -> dict[str, Any]:
        return {
            "id": f"uuid-{article}",
            "companyId": "c",
            "branchId": "b",
            "name": name,
            "price": "100",
            "externalProductId": article,
            "stock": 4,
            "available": True,
        }

    plan = Assembled(
        basket=Basket(
            run_id="run-1",
            lines=[],
            total=Decimal("0"),
            delivery_cost=Decimal("0"),
            total_weight_kg=Decimal("0"),
            stats=RunStats(
                receipts=0,
                cycled=0,
                mcp_calls=0,
                duration_ms=0,
                cost_usd=Decimal("0"),
                model="тест",
            ),
        ),
        lines=[
            PlanLine(
                intent="вода мінеральна",
                product=_card("101", "Вода Карпатська"),
                qty=Decimal(1),
                reason="звичне",
                from_history=None,
            )
        ],
        unresolved=[],
        slot={},
    )
    remember_options(
        plan,
        [
            SwapOption(
                external_product_id="202",
                name="Моршинська сильногазована 1,5 л",
                price=Decimal("40"),
                stock=4,
                available=True,
            )
        ],
    )
    monkeypatch.setattr("komora.api.app.runs.recall", lambda *_a, **_kw: plan)
    monkeypatch.setattr("komora.api.app.runs.remember", lambda run, **_kw: _basket())

    client.post(
        "/api/basket/run-1/swaps",
        json={
            "swaps": [{"externalProductId": "101", "chain": ["202"]}],
            "remember": True,
        },
    )

    saved = store.rows[("відбиток-акаунта", "вода мінеральна")]
    assert [link.name for link in saved.links] == ["Моршинська сильногазована 1,5 л"]
