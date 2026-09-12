from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

from komora.agent.basket import load_history
from komora.db import receipts as store

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 9, 2, tzinfo=UTC)

SLOT = {
    "start": "2026-09-02T11:30:00+00:00",
    "end": "2026-09-02T13:00:00+00:00",
    "available": True,
    "deliveryType": "DeliveryHome",
}

ACCOUNT = "sha256-акаунта"


def _paper(day: int, total: str, *, name: str = "Молоко Яготинське") -> dict[str, Any]:
    return {
        "createdAt": (NOW - timedelta(days=day)).isoformat(),
        "sumReg": total,
        "branchId": "id:12345678",
        "receiptUrl": "https://example/чек",
        "filialName": "вул. Прикладна, буд. 1",
        "cityName": "Місто",
        "chequeMagicName": "Миловидні обійми",
        "products": [
            {
                "lagerId": "111",
                "name": name,
                "unit": "шт",
                "quantity": 1,
                "price": 40,
                "branchId": "id:12345678",
                "catalogProduct": {"price": 44, "slug": "moloko-111"},
            }
        ],
    }


def _order(ident: str, day: int, status: str) -> dict[str, Any]:
    return {
        "orderId": ident,
        "createdAt": (NOW - timedelta(days=day)).isoformat(),
        "status": status,
        "amount": 500,
        "number": "36705277",
        "delivery": {"type": "DeliveryHome"},
        "address": {"city": "Місто", "street": "вул. Прикладна", "building": "1", "apartment": "2"},
        "products": [
            {
                "id": "uuid",
                "name": "Хліб",
                "quantity": 1,
                "subtotal": 30,
                "branchId": "id:12345678",
                "companyId": "uuid-company",
            }
        ],
    }


class _Outcome:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload_raw = payload
        self.duration_ms = 1


class _Silpo:

    def __init__(
        self, papers: list[dict[str, Any]], orders: list[dict[str, Any]] | None = None
    ) -> None:
        self.papers = papers
        self.orders = orders or []
        self.asked: list[dict[str, Any]] = []

    async def call(self, tool: str, args: dict[str, Any] | None = None) -> _Outcome:
        self.asked.append({"tool": tool, **(args or {})})
        if tool == "silpo_get_my_offline_orders":
            since = str((args or {}).get("dateStart") or "")
            fresh = [p for p in self.papers if str(p["createdAt"]) >= since]
            return _Outcome({"orders": fresh, "meta": {"total": len(fresh)}})
        if tool == "silpo_get_my_online_orders":
            return _Outcome({"orders": self.orders, "meta": {"total": len(self.orders)}})
        raise AssertionError(f"зайвий виклик: {tool}")

    def offline_calls(self) -> int:
        return sum(1 for a in self.asked if a["tool"] == "silpo_get_my_offline_orders")

    def online_calls(self) -> int:
        return sum(1 for a in self.asked if a["tool"] == "silpo_get_my_online_orders")


class _Conn:
    def __init__(self, pool: _Pool) -> None:
        self.pool = pool
        self._rows: list[dict[str, Any]] = []
        self._row: dict[str, Any] | None = None

    async def execute(self, sql: str, args: Any = None) -> Any:
        source = (args or {}).get("source")
        if "from receipts" in sql:
            self._rows = [
                {"payload": payload} for payload in self.pool.stored.get(source, {}).values()
            ]
        elif "from receipt_reads" in sql:
            self._row = self.pool.marks.get(source)
        elif "insert into receipt_reads" in sql:
            self.pool.touched.append(args)
            last = (args or {}).get("last_at")
            known = self.pool.marks.get(source)
            if known is None or (last is not None and last > known["last_at"]):
                self.pool.marks[source] = {"last_at": last, "read_at": NOW}
        return self

    async def fetchall(self) -> list[dict[str, Any]]:
        return self._rows

    async def fetchone(self) -> dict[str, Any] | None:
        return self._row

    @asynccontextmanager
    async def cursor(self):
        yield self

    async def executemany(self, sql: str, rows: Any) -> None:
        for row in rows:
            self.pool.written.append(row)
            self.pool.stored.setdefault(row["source"], {})[row["ident"]] = _loads(row["payload"])


def _loads(payload: str) -> dict[str, Any]:
    import json

    return json.loads(payload)


class _Pool:

    def __init__(self) -> None:
        self.stored: dict[str, dict[str, dict[str, Any]]] = {}
        self.marks: dict[str, dict[str, Any]] = {}
        self.written: list[dict[str, Any]] = []
        self.touched: list[Any] = []

    @asynccontextmanager
    async def connection(self, **_: Any):
        yield _Conn(self)


class _DeadPool:

    @asynccontextmanager
    async def connection(self, **_: Any):
        raise ConnectionError("база не відповідає")
        yield  # pragma: no cover -- недосяжно, але робить це генератором


async def test_the_first_visit_reads_everything_and_writes_it_down():
    mcp = _Silpo([_paper(30, "300.00"), _paper(10, "200.00")])
    pool = _Pool()

    history, receipts, _, _, _ = await load_history(
        mcp, SLOT, "branch", now=NOW, pool=pool, account=ACCOUNT
    )

    assert receipts == 2
    assert len(history) == 1, "обидва чеки про той самий вид"
    assert len(pool.stored[store.OFFLINE]) == 2
    assert pool.marks[store.OFFLINE]["last_at"] == NOW - timedelta(days=10), (
        "ватерлінія мусить стати на НАЙСВІЖІШУ покупку, а не на момент читання"
    )


async def test_the_second_visit_asks_only_for_the_tail():
    papers = [_paper(30, "300.00"), _paper(10, "200.00")]
    pool = _Pool()
    await load_history(_Silpo(papers), SLOT, "branch", now=NOW, pool=pool, account=ACCOUNT)

    again = _Silpo([*papers, _paper(1, "150.00")])
    history, receipts, _, _, _ = await load_history(
        again, SLOT, "branch", now=NOW, pool=pool, account=ACCOUNT
    )

    asked = next(a for a in again.asked if a["tool"] == "silpo_get_my_offline_orders")
    since = datetime.fromisoformat(asked["dateStart"])
    assert since < NOW - timedelta(days=10), "відступ назад -- чек буває заднім числом"
    assert since > NOW - timedelta(days=20), "але не з початку історії, інакше сенсу немає"
    assert receipts == 3, "давній чек мусить прийти зі сховища, а не зникнути"
    assert history[0].receipts == 3


async def test_an_order_still_on_its_way_is_not_written_down():
    mcp = _Silpo([], [_order("живе", 1, "collecting"), _order("виконане", 5, "received")])
    pool = _Pool()

    await load_history(mcp, SLOT, "branch", now=NOW, pool=pool, account=ACCOUNT)

    assert set(pool.stored.get(store.ONLINE, {})) == {"виконане"}


async def test_the_shelf_answer_never_reaches_the_store():
    mcp = _Silpo([_paper(3, "100.00")])
    pool = _Pool()

    await load_history(mcp, SLOT, "branch", now=NOW, pool=pool, account=ACCOUNT)

    saved = next(iter(pool.stored[store.OFFLINE].values()))
    row = saved["products"][0]
    assert "catalogProduct" not in row, "відповідь про полицю сусідньої філії"
    assert row["priceSeen"] == 44, (
        "ціна картки лишається, інакше оцінка сповзає на заплачене "
        "(медіана +7,3%, p90 +59,4%, замір 02.09)"
    )
    assert row["price"] == 40, "заплачене -- незмінний факт покупки"
    assert "branchId" not in saved and "branchId" not in row, "район у сховище не їде"
    assert "receiptUrl" not in saved, "посилання на фіскальний чек -- документ гостя"
    assert "filialName" not in saved and "cityName" not in saved, "адреса магазину -- район"


async def test_the_stored_price_still_feeds_the_estimate():
    mcp = _Silpo([_paper(3, "100.00")])
    pool = _Pool()
    await load_history(mcp, SLOT, "branch", now=NOW, pool=pool, account=ACCOUNT)

    history, _, _, _, _ = await load_history(
        _Silpo([]), SLOT, "branch", now=NOW, pool=pool, account=ACCOUNT
    )

    assert history[0].price is not None
    assert int(history[0].price) == 44, "ціна, яку ми бачили, а не заплачена"


async def test_a_dead_database_still_gives_the_whole_history():
    mcp = _Silpo([_paper(30, "300.00"), _paper(10, "200.00")])

    history, receipts, _, _, _ = await load_history(
        mcp, SLOT, "branch", now=NOW, pool=_DeadPool(), account=ACCOUNT
    )

    assert receipts == 2
    assert history[0].receipts == 2
    asked = next(a for a in mcp.asked if a["tool"] == "silpo_get_my_offline_orders")
    assert asked["dateStart"].startswith("2015"), "без бази читаємо з початку історії"


async def test_without_an_account_nothing_is_stored():
    pool = _Pool()

    await load_history(
        _Silpo([_paper(3, "100.00")]), SLOT, "branch", now=NOW, pool=pool, account=""
    )

    assert pool.written == []


async def test_the_watermark_never_moves_backwards():
    pool = _Pool()
    await load_history(
        _Silpo([_paper(1, "100.00")]), SLOT, "branch", now=NOW, pool=pool, account=ACCOUNT
    )
    high = pool.marks[store.OFFLINE]["last_at"]

    await load_history(
        _Silpo([_paper(40, "999.00")]), SLOT, "branch", now=NOW, pool=pool, account=ACCOUNT
    )

    assert pool.marks[store.OFFLINE]["last_at"] == high


def test_the_watermark_is_guarded_by_the_query_itself():
    assert "greatest(" in store._TOUCH
    assert "on conflict" in store._TOUCH


async def test_forgetting_an_account_has_a_place_to_live():
    assert await store.forget(_Pool(), ACCOUNT) is None


async def test_an_empty_history_is_still_a_history_that_was_read():
    pool = _Pool()

    await load_history(_Silpo([]), SLOT, "branch", now=NOW, pool=pool, account=ACCOUNT)

    assert store.OFFLINE in pool.marks, "порожній хвіст -- теж прочитаний хвіст"
    assert pool.marks[store.OFFLINE]["last_at"] is None
    assert pool.written == [], "але записувати нема чого"


def test_stored_row_keeps_only_the_allowed_fields_of_both_live_shapes():
    from komora.agent.basket import _stored_row

    online = _order("o1", 1, "received")
    row = _stored_row(online)
    assert "address" not in row, "дім гостя в сховище не їде"
    assert set(row) <= {
        "orderId",
        "number",
        "status",
        "createdAt",
        "amount",
        "delivery",
        "products",
    }
    assert set(row["products"][0]) == {"id", "name", "quantity", "subtotal", "companyId"}

    paper = _stored_row(_paper(1, "51"))
    assert {"filialName", "cityName", "receiptUrl", "chequeMagicName", "branchId"}.isdisjoint(paper)
    assert paper["sumReg"] == "51" and "rewards" not in paper
    item = paper["products"][0]
    assert item["priceSeen"] == 44 and "branchId" not in item and "catalogProduct" not in item

    assert "новеПоле" not in _stored_row({**online, "новеПоле": 1}), "невідоме поле не лягає"
