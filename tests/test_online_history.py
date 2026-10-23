from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

import pytest

from komora.agent.basket import (
    MIN_RECEIPTS,
    history_kinds,
    is_service_item,
    load_history,
)
from komora.mcp.client import SilpoMCP

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 9, 1, tzinfo=UTC)

SLOT = {
    "start": "2026-09-01T11:30:00+00:00",
    "end": "2026-09-01T13:00:00+00:00",
    "available": True,
    "deliveryType": "DeliveryHome",
}


def _receipt(day: str, *, total: float, name: str = "Хліб Київський") -> dict[str, Any]:
    return {
        "createdAt": f"{day}T20:09:01",
        "sumReg": total,
        "products": [
            {"lagerId": 101, "name": name, "unit": "шт", "quantity": 1, "price": 30}
        ],
    }


def _order(day: str, *, total: float, names: list[str], status: str = "received") -> dict:
    return {
        "createdAt": f"{day}T15:40:00",
        "amount": total,
        "status": status,
        "products": [
            {
                "id": f"uuid-{index}",
                "name": name,
                "price": 50,
                "quantity": 1,
                "subtotal": 50,
                "removed": False,
            }
            for index, name in enumerate(names)
        ],
    }


def _stand(tmp_path, *, receipts: list[dict], orders: list[dict]) -> SilpoMCP:
    (tmp_path / "silpo_get_my_offline_orders.json").write_text(
        json.dumps({"orders": receipts}), encoding="utf-8"
    )
    (tmp_path / "silpo_get_my_online_orders.json").write_text(
        json.dumps({"orders": orders}), encoding="utf-8"
    )
    return SilpoMCP(fixtures_dir=tmp_path)


async def _read(stand: SilpoMCP):
    return await load_history(stand, SLOT, "філія", now=NOW)


async def test_an_online_only_kind_reaches_the_history(tmp_path):
    stand = _stand(
        tmp_path,
        receipts=[_receipt("2026-08-01", total=100)],
        orders=[_order("2026-08-05", total=250, names=["Васабі Kikkoman"])],
    )

    history, receipts, _, _, online = await _read(stand)

    assert receipts == 1
    assert online.count == 1
    assert "Васабі Kikkoman" in {item.name for item in history}


async def test_the_two_numbers_do_not_merge_into_one(tmp_path):
    stand = _stand(
        tmp_path,
        receipts=[],
        orders=[_order("2026-08-05", total=250, names=["Васабі Kikkoman"])],
    )

    history, receipts, _, _, online = await _read(stand)

    assert (receipts, online.count) == (0, 1)
    assert history, "покупки є, просто не в магазині"


async def test_a_twin_order_is_not_counted_twice(tmp_path):
    stand = _stand(
        tmp_path,
        receipts=[_receipt("2026-08-05", total=250, name="Хліб Київський")],
        orders=[_order("2026-08-05", total=250, names=["Хліб Київський"])],
    )

    history, receipts, _, _, online = await _read(stand)

    assert (receipts, online.count) == (1, 0)
    assert [item.receipts for item in history] == [1]


async def test_a_cancelled_order_is_not_a_purchase(tmp_path):
    stand = _stand(
        tmp_path,
        receipts=[],
        orders=[_order("2026-08-05", total=250, names=["Васабі"], status="canceled")],
    )

    history, _, _, _, online = await _read(stand)

    assert online.count == 0
    assert history == []


async def test_a_removed_line_is_not_a_purchase(tmp_path):
    order = _order("2026-08-05", total=250, names=["Васабі", "Імбир"])
    order["products"][1]["removed"] = True
    stand = _stand(tmp_path, receipts=[], orders=[order])

    history, _, _, _, online = await _read(stand)

    assert online.count == 1
    assert [item.name for item in history] == ["Васабі"]


async def test_an_online_kind_carries_no_invented_unit(tmp_path):
    stand = _stand(
        tmp_path,
        receipts=[],
        orders=[_order("2026-08-05", total=250, names=["Філе куряче охолоджене"])],
    )

    history, _, _, _, _ = await _read(stand)

    assert [item.unit for item in history] == [""]


async def test_the_receipt_unit_wins_for_the_same_kind(tmp_path):
    stand = _stand(
        tmp_path,
        receipts=[_receipt("2026-08-20", total=100, name="Сир Гауда ваговий")],
        orders=[_order("2026-08-05", total=250, names=["Сир Гауда ваговий"])],
    )

    history, _, _, _, _ = await _read(stand)
    (kind,) = history_kinds([i for i in history if not is_service_item(i.name)])

    assert kind.unit == "шт", "чек новіший, і саме він називає одиницю"


async def test_two_sources_of_one_kind_build_one_cycle(tmp_path):
    stand = _stand(
        tmp_path,
        receipts=[
            _receipt("2026-07-25", total=100, name="Хліб Київський"),
            _receipt("2026-08-01", total=100, name="Хліб Київський"),
            _receipt("2026-08-15", total=100, name="Хліб Київський"),
        ],
        orders=[_order("2026-08-08", total=250, names=["Хліб Київський"])],
    )

    history, _, _, _, _ = await _read(stand)
    (kind,) = history_kinds(history)

    assert kind.receipts == MIN_RECEIPTS + 1, "чотири покупки одного виду з двох джерел"
    assert kind.cycle_days() == 7


async def test_the_online_basket_counts_towards_the_ceiling(tmp_path):
    stand = _stand(
        tmp_path,
        receipts=[_receipt("2026-08-01", total=100)],
        orders=[_order("2026-08-05", total=250, names=["Васабі", "Імбир", "Соєвий соус"])],
    )

    _, _, _, sizes, _ = await _read(stand)

    assert sorted(sizes) == [1, 3]


async def test_a_dead_online_call_leaves_the_receipts_alone(tmp_path):
    (tmp_path / "silpo_get_my_offline_orders.json").write_text(
        json.dumps({"orders": [_receipt("2026-08-01", total=100)]}), encoding="utf-8"
    )
    stand = SilpoMCP(fixtures_dir=tmp_path)

    history, receipts, _, _, online = await _read(stand)

    assert (receipts, online.count) == (1, 0)
    assert [item.name for item in history] == ["Хліб Київський"]


class _Conn:

    def __init__(self, by_product: list[dict[str, Any]], by_name: list[dict[str, Any]]) -> None:
        self._by_product = by_product
        self._by_name = by_name
        self._rows: list[dict[str, Any]] = []

    async def execute(self, sql: str, args: Any = None) -> Any:
        self._rows = self._by_product if "product_id" in sql else self._by_name
        return self

    async def fetchall(self) -> list[dict[str, Any]]:
        return self._rows


class _Pool:
    def __init__(
        self,
        by_name: list[dict[str, Any]] | None = None,
        by_product: list[dict[str, Any]] | None = None,
    ) -> None:
        self._by_name = by_name or []
        self._by_product = by_product or []

    @asynccontextmanager
    async def connection(self, **_: Any):
        yield _Conn(self._by_product, self._by_name)


class _DeadPool:
    @asynccontextmanager
    async def connection(self, **_: Any):
        raise RuntimeError("бази немає")
        yield  # pragma: no cover


async def test_the_name_buys_the_article_from_the_catalogue(tmp_path):
    stand = _stand(
        tmp_path,
        receipts=[],
        orders=[_order("2026-08-05", total=250, names=["Васабі Kikkoman"])],
    )
    pool = _Pool([{"name_key": "васабі kikkoman", "article": "77771"}])

    history, _, _, _, _ = await load_history(stand, SLOT, "філія", now=NOW, pool=pool)

    assert [item.lager_id for item in history] == ["77771"]


async def test_a_name_the_catalogue_does_not_know_still_becomes_a_kind(tmp_path):
    stand = _stand(
        tmp_path,
        receipts=[],
        orders=[_order("2026-08-05", total=250, names=["Авокадо Ready to eat"])],
    )
    pool = _Pool([])

    history, _, _, _, _ = await load_history(stand, SLOT, "філія", now=NOW, pool=pool)

    assert [item.name for item in history] == ["Авокадо Ready to eat"]
    assert history[0].lager_id.startswith("web:")


async def test_a_dead_map_does_not_take_the_purchases_with_it(tmp_path):
    stand = _stand(
        tmp_path,
        receipts=[],
        orders=[_order("2026-08-05", total=250, names=["Васабі Kikkoman"])],
    )

    history, _, _, _, online = await load_history(
        stand, SLOT, "філія", now=NOW, pool=_DeadPool()
    )

    assert online.count == 1
    assert [item.name for item in history] == ["Васабі Kikkoman"]


async def test_the_product_uuid_buys_the_article_exactly(tmp_path):
    stand = _stand(
        tmp_path,
        receipts=[],
        orders=[_order("2026-08-05", total=250, names=["Балик «Кременчукм'ясо»"])],
    )
    pool = _Pool(
        by_product=[
            {"product_id": "uuid-0", "article": "73990", "ratio": None,
             "weighted": False, "step": None}
        ],
        by_name=[{"name_key": "щось інше", "article": "00000"}],
    )

    history, _, _, _, _ = await load_history(stand, SLOT, "філія", now=NOW, pool=pool)

    assert [item.lager_id for item in history] == ["73990"]


async def test_the_unit_comes_from_the_card_not_from_a_guess(tmp_path):
    stand = _stand(
        tmp_path,
        receipts=[],
        orders=[_order("2026-08-05", total=250, names=["Сир Гауда ваговий"])],
    )
    pool = _Pool(
        by_product=[
            {"product_id": "uuid-0", "article": "555", "ratio": "100г",
             "weighted": True, "step": None}
        ]
    )

    history, _, _, _, _ = await load_history(stand, SLOT, "філія", now=NOW, pool=pool)

    assert [item.unit for item in history] == ["кг"]


async def test_a_piece_good_is_an_answer_and_not_a_guess(tmp_path):
    stand = _stand(
        tmp_path,
        receipts=[],
        orders=[_order("2026-08-05", total=250, names=["Шоколад Kinder T8"])],
    )
    piece = _Pool(
        by_product=[
            {"product_id": "uuid-0", "article": "29055", "ratio": "150г",
             "weighted": False, "step": 1}
        ]
    )
    blind = _Pool()

    named, _, _, _, _ = await load_history(stand, SLOT, "філія", now=NOW, pool=piece)
    silent, _, _, _, _ = await load_history(stand, SLOT, "філія", now=NOW, pool=blind)

    assert [item.unit for item in named] == ["шт"]
    assert [item.unit for item in silent] == [""]
