from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from komora.agent.basket import Receipts
from komora.api import app as api_app
from komora.api import history
from komora.api.app import app
from komora.api.auth_routes import require_guest
from komora.api.schemas import Pantry
from komora.core.location import Location, Source


class Session:
    access = "живий-токен"
    refresh = "живий-refresh"
    owner = "власник-сесії"
    account = "відбиток-акаунта"


@pytest.fixture(autouse=True)
def clean() -> None:
    history.forget_all()


def _where(branch: str, source: Source = Source.CONFIG) -> Location:
    return Location(branch_id=branch, source=source)


def _seen(*, branch: str | None, ends: str | None = None) -> Receipts:
    return Receipts(slot={"end": ends} if ends else {}, branch_id=branch, history=[], count=1)


class TestTaSamaPolytsia:
    def test_inshyi_mahazyn_ne_prokhodyt(self) -> None:
        assert not api_app._same_shelf(_seen(branch="branch-1"), place=_where("branch-2"))

    def test_toi_samyi_mahazyn_prokhodyt(self) -> None:
        assert api_app._same_shelf(_seen(branch="branch-1"), place=_where("branch-1"))

    def test_bez_mistsia_pamiat_lyshaietsia(self) -> None:
        assert api_app._same_shelf(_seen(branch="branch-1"), place=None)

    def test_mynulyi_slot_ne_prokhodyt(self) -> None:
        gone = (datetime.now(UTC) - timedelta(hours=2)).isoformat()
        assert not api_app._same_shelf(_seen(branch="branch-1", ends=gone), place=None)

    def test_slot_shcho_shche_ide_prokhodyt(self) -> None:
        later = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
        assert api_app._same_shelf(_seen(branch="branch-1", ends=later), place=None)

    def test_nerozbirlyvyi_slot_ne_vymykaie_pamiat(self) -> None:
        assert api_app._same_shelf(_seen(branch="branch-1", ends="не дата"), place=None)


@pytest.fixture
def moves(monkeypatch: pytest.MonkeyPatch) -> list[Location]:
    spot = [_where("branch-1")]

    async def _place(*_a: Any, **_kw: Any) -> Location:
        return spot[0]

    monkeypatch.setattr("komora.api.app.place_of", _place)
    return spot


@pytest.fixture
def reads(monkeypatch: pytest.MonkeyPatch, moves: list[Location]) -> list[str]:
    went: list[str] = []

    class _Silpo:
        def __init__(self, *_a: Any, **_kw: Any) -> None: ...

        async def __aenter__(self) -> Any:
            return self

        async def __aexit__(self, *_exc: object) -> bool:
            return False

    async def _read(*_a: Any, **kw: Any) -> Receipts:
        went.append("чеки")
        spot = kw.get("place")
        return Receipts(
            slot={},
            branch_id=spot.branch_id if spot is not None else None,
            history=[],
            count=9,
        )

    async def _pantry(*_a: Any, **_kw: Any) -> Pantry:
        return Pantry(items=[], receipts=9, orders=0, kinds=3, tracked_from=3, unlisted=0)

    async def _nothing(*_a: Any, **_kw: Any) -> dict[str, Any]:
        return {}

    async def _mode(*_a: Any, **_kw: Any) -> str:
        return "receipts"

    async def _wiped(*_a: Any, **_kw: Any) -> int:
        return 0

    monkeypatch.setattr("komora.api.app.SilpoMCP", _Silpo)
    monkeypatch.setattr("komora.api.app.read_receipts", _read)
    monkeypatch.setattr("komora.api.app.pantry_live", _pantry)
    monkeypatch.setattr("komora.api.app.get_pool", lambda: None)
    monkeypatch.setattr("komora.api.app._marks_of", _nothing)
    monkeypatch.setattr("komora.api.app._manual_of", _nothing)
    monkeypatch.setattr("komora.api.app._cycles_of", _nothing)
    monkeypatch.setattr("komora.api.app._source_of", _mode)
    monkeypatch.setattr("komora.api.app.pantry_marks.wipe_items", _wiped)
    return went


@pytest.fixture
def client(reads: list[str]) -> TestClient:
    app.dependency_overrides[require_guest] = lambda: Session()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_zmina_filii_chytaie_cheky_zanovo(
    client: TestClient, reads: list[str], moves: list[Location]
) -> None:
    client.get("/api/pantry")
    assert reads == ["чеки"]

    client.delete("/api/pantry/items")
    assert reads == ["чеки"], "правка того самого магазину не ходить по чеки"

    moves[0] = _where("branch-2", Source.ADDRESS)
    client.delete("/api/pantry/items")
    assert reads == ["чеки", "чеки"], "інший магазин -- інша полиця, отже інші чеки"
