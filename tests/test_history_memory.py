from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from komora.agent.basket import Receipts
from komora.api import history
from komora.api.app import app
from komora.api.auth_routes import require_guest
from komora.api.schemas import Pantry

NOW = datetime(2026, 9, 2, 12, 0, tzinfo=UTC)


class Session:
    access = "живий-токен"
    refresh = "живий-refresh"
    owner = "власник-сесії"
    account = "відбиток-акаунта"


@pytest.fixture(autouse=True)
def clean() -> None:
    history.forget_all()


class TestPamiat:
    def test_prochytane_vertaietsia_tym_samym(self) -> None:
        paper = object()
        history.remember(paper, owner="гість", now=NOW)
        assert history.recall("гість", now=NOW) is paper

    def test_chuzhe_ne_distaietsia(self) -> None:
        history.remember(object(), owner="гість", now=NOW)
        assert history.recall("інший", now=NOW) is None

    def test_bez_vlasnyka_ne_zberihaietsia(self) -> None:
        history.remember(object(), owner="", now=NOW)
        assert history.recall("", now=NOW) is None

    def test_stare_ne_vertaietsia(self) -> None:
        history.remember(object(), owner="гість", now=NOW)
        later = NOW + timedelta(seconds=history.TTL_S + 1)
        assert history.recall("гість", now=later) is None

    def test_vykhid_zabyraie_pokupky(self) -> None:
        history.remember(object(), owner="гість", now=NOW)
        history.forget("гість")
        assert history.recall("гість", now=NOW) is None

    def test_dovhyi_protses_ne_trymaie_chuzhi_cheky_vichno(self) -> None:
        for number in range(history.MAX_GUESTS + 3):
            history.remember(object(), owner=f"гість-{number}", now=NOW)
        assert history.recall("гість-0", now=NOW) is None
        assert history.recall(f"гість-{history.MAX_GUESTS + 2}", now=NOW) is not None

    def test_aktyvnyi_hist_ne_vylitaie_cherez_tykh_khto_zaishov_i_pishov(self) -> None:
        history.remember(object(), owner="активний", now=NOW)
        for number in range(history.MAX_GUESTS - 1):
            history.remember(object(), owner=f"перехожий-{number}", now=NOW)
            assert history.recall("активний", now=NOW) is not None
        history.remember(object(), owner="ще-один", now=NOW)
        assert history.recall("активний", now=NOW) is not None


@pytest.fixture
def reads(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    went: list[str] = []

    class _Silpo:
        def __init__(self, *_a: Any, **_kw: Any) -> None: ...

        async def __aenter__(self) -> Any:
            return self

        async def __aexit__(self, *_exc: object) -> bool:
            return False

    async def _place(*_a: Any, **_kw: Any) -> None:
        return None

    async def _read(*_a: Any, **_kw: Any) -> object:
        went.append("чеки")
        return _paper()

    async def _pantry(*_a: Any, **kw: Any) -> Pantry:
        return Pantry(items=[], receipts=9, orders=0, kinds=3, tracked_from=3, unlisted=0)

    async def _nothing(*_a: Any, **_kw: Any) -> dict[str, Any]:
        return {}

    async def _mode(*_a: Any, **_kw: Any) -> str:
        return "receipts"

    async def _wiped(*_a: Any, **_kw: Any) -> int:
        return 0

    monkeypatch.setattr("komora.api.app.SilpoMCP", _Silpo)
    monkeypatch.setattr("komora.api.app.place_of", _place)
    monkeypatch.setattr("komora.api.app.read_receipts", _read)
    monkeypatch.setattr("komora.api.app.pantry_live", _pantry)
    monkeypatch.setattr("komora.api.app.get_pool", lambda: None)
    monkeypatch.setattr("komora.api.app._marks_of", _nothing)
    monkeypatch.setattr("komora.api.app._manual_of", _nothing)
    monkeypatch.setattr("komora.api.app._cycles_of", _nothing)
    monkeypatch.setattr("komora.api.app._source_of", _mode)
    monkeypatch.setattr("komora.api.app.pantry_marks.wipe_items", _wiped)
    return went


def _paper() -> Receipts:
    return Receipts(slot={}, branch_id=None, history=[], count=9)


@pytest.fixture
def client(reads: list[str]) -> TestClient:
    app.dependency_overrides[require_guest] = lambda: Session()
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_pravka_spysku_ne_chytaie_pokupky_vzahali(client: TestClient, reads: list[str]) -> None:
    client.get("/api/pantry")
    assert reads == ["чеки"], "відкриття мусить читати"

    client.delete("/api/pantry/items")
    client.delete("/api/pantry/items")

    assert reads == ["чеки"], "правка списку не має ходити в «Сільпо» по чеки"


def test_vidkryttia_ekrana_chytaie_zanovo(client: TestClient, reads: list[str]) -> None:
    client.get("/api/pantry")
    client.get("/api/pantry")

    assert reads == ["чеки", "чеки"]


class TestVlasnaKopiia:

    def _remembered(self) -> Receipts:
        from komora.agent.basket import HistoryItem

        read = Receipts(
            slot={},
            branch_id="branch-1",
            history=[HistoryItem(lager_id="1", name="Хліб Київський", unit="шт")],
            count=1,
        )
        history.remember(read, owner=Session.owner)
        return read

    def test_dva_chytachi_pravliat_rizni_riadky(self) -> None:
        from komora.api.app import _remembered_receipts

        stored = self._remembered()
        first = _remembered_receipts(Session())
        second = _remembered_receipts(Session())
        assert first is not None and second is not None

        first.history[0].marked_at = NOW

        assert second.history[0].marked_at is None, "сусідній запит не має бачити чужу правку"
        assert stored.history[0].marked_at is None, "пам'ять сесії лишається прочитаним"

    def test_kopiia_ne_perepysuie_sam_spysok(self) -> None:
        from komora.api.app import _remembered_receipts

        self._remembered()
        first = _remembered_receipts(Session())
        second = _remembered_receipts(Session())
        assert first is not None and second is not None
        first.history.clear()
        assert len(second.history) == 1
