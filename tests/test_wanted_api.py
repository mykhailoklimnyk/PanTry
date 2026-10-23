from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from komora.api.app import app
from komora.api.auth_routes import require_guest
from komora.api.schemas import CheckoutResult
from komora.core.pantry import manual_id
from komora.db.wanted import Want


class Session:
    access = "живий-токен"
    refresh = "живий-refresh"
    owner = "власник-сесії"
    account = "відбиток-акаунта"


class _Store:

    def __init__(self) -> None:
        self.rows: dict[tuple[str, str], Want] = {}

    async def load(self, _pool: Any, account: str) -> dict[str, Want]:
        return {kind: row for (owner, kind), row in self.rows.items() if owner == account}

    async def add(self, _pool: Any, account: str, kind: str, label: str, *, at_home: bool) -> None:
        self.rows[(account, kind)] = Want(label, at_home)

    async def drop(self, _pool: Any, account: str, kinds: Any) -> int:
        gone = [kind for kind in kinds if (account, kind) in self.rows]
        for kind in gone:
            del self.rows[(account, kind)]
        return len(gone)


class _Pantry:

    def __init__(self) -> None:
        self.items: dict[tuple[str, str, str], str] = {}
        self.origins: dict[tuple[str, str, str], str] = {}
        self.marks: dict[tuple[str, str], datetime] = {}

    async def add_items(
        self, _pool: Any, account: str, rows: dict[str, str], *, scope: str, origin: str
    ) -> int:
        for kind, label in rows.items():
            self.items[(account, scope, kind)] = label
            self.origins[(account, scope, kind)] = origin
        return len(rows)

    async def save(self, _pool: Any, account: str, marks: dict[str, datetime]) -> None:
        for kind, moment in marks.items():
            self.marks[(account, kind)] = moment


class _DeadStore(_Store):
    async def add(self, *_a: Any, **_kw: Any) -> None:
        raise ConnectionError("сховище не відповідає")


@pytest.fixture
def store(monkeypatch: pytest.MonkeyPatch) -> _Store:
    kept = _Store()
    for name in ("load", "add", "drop"):
        monkeypatch.setattr(f"komora.api.app.wanted_store.{name}", getattr(kept, name))
    monkeypatch.setattr("komora.api.app.get_pool", lambda: None)
    return kept


@pytest.fixture
def pantry(monkeypatch: pytest.MonkeyPatch) -> _Pantry:
    kept = _Pantry()
    for name in ("add_items", "save"):
        monkeypatch.setattr(f"komora.api.app.pantry_marks.{name}", getattr(kept, name))
    return kept


@pytest.fixture
def client() -> TestClient:
    app.dependency_overrides[require_guest] = lambda: Session()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_a_written_row_reaches_the_store_and_comes_back(client: TestClient, store: _Store) -> None:
    response = client.post("/api/list", json={"label": "батарейки"})

    assert response.status_code == 200
    assert store.rows == {("відбиток-акаунта", "батарейки"): Want("батарейки", True)}
    assert [row["label"] for row in response.json()] == ["батарейки"]
    assert [row["atHome"] for row in response.json()] == [True]


def test_an_empty_row_is_refused_before_the_store(client: TestClient, store: _Store) -> None:
    assert client.post("/api/list", json={"label": "  "}).status_code == 422
    assert store.rows == {}


def test_a_store_that_did_not_answer_says_so_out_loud(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    dead = _DeadStore()
    for name in ("load", "add", "drop"):
        monkeypatch.setattr(f"komora.api.app.wanted_store.{name}", getattr(dead, name))
    monkeypatch.setattr("komora.api.app.get_pool", lambda: None)

    response = client.post("/api/list", json={"label": "батарейки"})

    assert response.status_code == 503
    assert "не зберігся" in response.json()["detail"]


def test_a_row_can_be_taken_back(client: TestClient, store: _Store) -> None:
    store.rows[("відбиток-акаунта", "батарейки")] = Want("батарейки", True)

    response = client.delete(f"/api/list/{manual_id('батарейки')}")

    assert response.status_code == 200
    assert store.rows == {}


def test_an_id_without_the_fingerprint_is_not_a_row_of_this_list(
    client: TestClient, store: _Store
) -> None:
    assert client.delete("/api/list/батарейки").status_code == 404


@dataclass
class _Line:
    intent: str


@dataclass
class _Plan:
    lines: list[_Line]


def _checkout_stand(monkeypatch: pytest.MonkeyPatch, *, intents: list[str]) -> None:
    monkeypatch.setattr("komora.api.app.runs.recall", lambda *_a, **_kw: _Plan([]))
    monkeypatch.setattr(
        "komora.api.app.writable", lambda _lines: ([_Line(intent) for intent in intents], [])
    )

    async def fake_hand_off(*_a: Any, **_kw: Any) -> CheckoutResult:
        return CheckoutResult(written=len(intents), summary="записано")

    monkeypatch.setattr("komora.api.app.hand_off", fake_hand_off)

    class _Silpo:
        def __init__(self, *_a: Any, **_kw: Any) -> None: ...

        async def __aenter__(self) -> Any:
            return self

        async def __aexit__(self, *_exc: object) -> bool:
            return False

    monkeypatch.setattr("komora.api.app.SilpoMCP", _Silpo)


def test_what_went_into_the_cart_burns_and_names_itself(
    client: TestClient, store: _Store, pantry: _Pantry, monkeypatch: pytest.MonkeyPatch
) -> None:
    store.rows[("відбиток-акаунта", "батарейки")] = Want("батарейки", True)
    _checkout_stand(monkeypatch, intents=["батарейки AA"])

    response = client.post("/api/basket/run-1/checkout")

    assert response.status_code == 200
    assert response.json()["wantedBurned"] == ["батарейки"]
    assert store.rows == {}


def test_what_did_not_go_stays_in_the_list(
    client: TestClient, store: _Store, pantry: _Pantry, monkeypatch: pytest.MonkeyPatch
) -> None:
    store.rows[("відбиток-акаунта", "батарейки")] = Want("батарейки", True)
    store.rows[("відбиток-акаунта", "лампочка")] = Want("лампочка", True)
    _checkout_stand(monkeypatch, intents=["батарейки AA"])

    response = client.post("/api/basket/run-1/checkout")

    assert response.json()["wantedBurned"] == ["батарейки"]
    assert store.rows == {("відбиток-акаунта", "лампочка"): Want("лампочка", True)}


def test_a_dead_store_does_not_break_a_written_cart(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    dead = _DeadStore()

    async def boom(*_a: Any, **_kw: Any) -> dict[str, str]:
        raise ConnectionError("сховище не відповідає")

    monkeypatch.setattr("komora.api.app.wanted_store.load", boom)
    monkeypatch.setattr("komora.api.app.wanted_store.drop", dead.drop)
    monkeypatch.setattr("komora.api.app.get_pool", lambda: None)
    _checkout_stand(monkeypatch, intents=["батарейки"])

    response = client.post("/api/basket/run-1/checkout")

    assert response.status_code == 200
    assert response.json()["written"] == 1
    assert response.json()["wantedBurned"] == []


def test_a_burned_row_lands_in_the_pantry_with_the_moment_it_arrived(
    client: TestClient, store: _Store, pantry: _Pantry, monkeypatch: pytest.MonkeyPatch
) -> None:
    store.rows[("відбиток-акаунта", "батарейки")] = Want("батарейки", True)
    _checkout_stand(monkeypatch, intents=["батарейки AA"])

    response = client.post("/api/basket/run-1/checkout")

    assert response.json()["wantedStocked"] == ["батарейки"]
    assert pantry.items == {("відбиток-акаунта", "pantry", "батарейки"): "батарейки"}
    assert pantry.origins == {("відбиток-акаунта", "pantry", "батарейки"): "guest"}
    assert ("відбиток-акаунта", "батарейки") in pantry.marks


def test_a_one_off_row_burns_but_stays_out_of_the_pantry(
    client: TestClient, store: _Store, pantry: _Pantry, monkeypatch: pytest.MonkeyPatch
) -> None:
    store.rows[("відбиток-акаунта", "вугілля")] = Want("вугілля", False)
    _checkout_stand(monkeypatch, intents=["вугілля для мангала"])

    response = client.post("/api/basket/run-1/checkout")

    assert response.json()["wantedBurned"] == ["вугілля"]
    assert response.json()["wantedStocked"] == []
    assert pantry.items == {}
    assert pantry.marks == {}
    assert store.rows == {}


def test_the_flag_rides_with_the_word(client: TestClient, store: _Store) -> None:
    response = client.post("/api/list", json={"label": "вугілля", "atHome": False})

    assert store.rows[("відбиток-акаунта", "вугілля")] == Want("вугілля", False)
    assert [row["atHome"] for row in response.json()] == [False]


def test_writing_the_same_word_again_is_the_switch(client: TestClient, store: _Store) -> None:
    client.post("/api/list", json={"label": "вугілля", "atHome": True})
    response = client.post("/api/list", json={"label": "вугілля", "atHome": False})

    assert len(store.rows) == 1
    assert store.rows[("відбиток-акаунта", "вугілля")] == Want("вугілля", False)
    assert [row["atHome"] for row in response.json()] == [False]


def test_a_pantry_that_did_not_answer_does_not_break_a_written_cart(
    client: TestClient, store: _Store, monkeypatch: pytest.MonkeyPatch
) -> None:

    async def boom(*_a: Any, **_kw: Any) -> int:
        raise ConnectionError("сховище не відповідає")

    monkeypatch.setattr("komora.api.app.pantry_marks.add_items", boom)
    store.rows[("відбиток-акаунта", "батарейки")] = Want("батарейки", True)
    _checkout_stand(monkeypatch, intents=["батарейки AA"])

    response = client.post("/api/basket/run-1/checkout")

    assert response.status_code == 200
    assert response.json()["written"] == 1
    assert response.json()["wantedBurned"] == []


@dataclass
class _Occasion:
    mode: Any


@dataclass
class _Budget:
    budget: float


@dataclass
class _EventPlan:
    lines: list[_Line]
    occasion: _Occasion
    basket: _Budget


class _Refused:

    def __init__(self, status: int, *, after_body: bool) -> None:
        self.status = status
        self.after_body = after_body

    def __call__(self, *_a: Any, **_kw: Any) -> Any:
        return self

    async def __aenter__(self) -> None:
        from fastapi import HTTPException

        if not self.after_body:
            raise HTTPException(status_code=self.status, detail="стеля прогонів вичерпана")

    async def __aexit__(self, *_exc: object) -> bool:
        from fastapi import HTTPException

        if self.after_body:
            raise HTTPException(status_code=self.status, detail="гроші проєкту скінчились")
        return False


def _event_stand(monkeypatch: pytest.MonkeyPatch, refused: _Refused) -> None:
    from komora.api.schemas import CartTotals
    from komora.core.occasion import BuildMode

    plan = _EventPlan([_Line("батарейки AA")], _Occasion(BuildMode.EVENT), _Budget(3000))
    monkeypatch.setattr("komora.api.app.runs.recall", lambda *_a, **_kw: plan)
    monkeypatch.setattr("komora.api.app.writable", lambda _lines: ([_Line("батарейки AA")], []))

    async def fake_hand_off(*_a: Any, **_kw: Any) -> CheckoutResult:
        return CheckoutResult(
            written=1,
            summary="записано",
            totals=CartTotals(products=500, discount=0, delivery=0, to_pay=500),
        )

    async def fake_top_up(*_a: Any, **_kw: Any) -> _EventPlan:
        return _EventPlan([_Line("батарейки AA"), _Line("шафран")], plan.occasion, plan.basket)

    monkeypatch.setattr("komora.api.app.hand_off", fake_hand_off)
    monkeypatch.setattr("komora.api.app.top_up_table", fake_top_up)
    monkeypatch.setattr("komora.api.app._run_llm", lambda *_a, **_kw: object())
    monkeypatch.setattr("komora.api.app.quota.counted", refused)

    class _Silpo:
        def __init__(self, *_a: Any, **_kw: Any) -> None: ...

        async def __aenter__(self) -> Any:
            return self

        async def __aexit__(self, *_exc: object) -> bool:
            return False

    monkeypatch.setattr("komora.api.app.SilpoMCP", _Silpo)


@pytest.mark.parametrize(
    ("status", "after_body"),
    [(402, True), (429, False)],
    ids=["гроші скінчились після добору", "стеля не пустила добір"],
)
def test_a_refused_top_up_does_not_eat_the_cart_that_is_already_written(
    client: TestClient,
    store: _Store,
    pantry: _Pantry,
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    after_body: bool,
) -> None:
    store.rows[("відбиток-акаунта", "батарейки")] = Want("батарейки", True)
    _event_stand(monkeypatch, _Refused(status, after_body=after_body))

    response = client.post("/api/basket/run-1/checkout")

    assert response.status_code == 200
    assert response.json()["written"] == 1
    assert response.json()["wantedBurned"] == ["батарейки"]


def test_the_refused_top_up_names_itself_in_the_trace() -> None:
    from fastapi import HTTPException

    from komora.api.app import _topup_refused

    before = CheckoutResult(written=1, summary="записано")
    after = _topup_refused(before, HTTPException(status_code=402, detail="додай свій ключ"))

    assert before.trace == []
    step = after.trace[-1]
    assert step.id == "step-topup-refused"
    assert "додай свій ключ" in step.result_summary
    assert after.warnings == []
