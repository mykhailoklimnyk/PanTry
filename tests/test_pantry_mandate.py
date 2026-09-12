from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from komora.agent.basket import (
    HistoryItem,
    _mandates_of,
    build_lines,
    kind_key,
    pantry_live,
    saved_for,
)
from komora.config import Settings
from komora.core.levels import Seen
from komora.core.location import Location
from komora.core.location import Source as BranchSource
from komora.core.mandate import build_comment
from komora.db import swaps as saved_swaps
from komora.mcp.client import SilpoMCP

NOW = datetime(2026, 9, 8, tzinfo=UTC)


def _card(article: str, name: str, price: float = 30.0) -> dict:
    return {
        "id": f"uuid-{article}",
        "externalProductId": article,
        "name": name,
        "price": price,
        "stock": 20,
        "available": True,
        "step": 1,
        "displayRatio": "1шт",
        "weighted": False,
        "companyId": "company",
        "branchId": "branch",
        "slug": f"slug-{article}",
    }


ZHYVYNKA = _card("101", "Йогурт Живинка питний 1,5% 300г")
GALYCHYNA = _card("102", "Йогурт Галичина питний 2,5% 300г", 32.0)
ALIEN = _card("103", "Йогурт Ферма скір 400г", 34.0)


def _seen(article: str, label: str, days: int | None, receipts: int = 3) -> Seen:
    return Seen(
        label=label,
        unit="300г",
        receipts=receipts,
        days_since=days,
        article=article,
    )


def _kind(sources: list[Seen], *, name: str = ZHYVYNKA["name"]) -> HistoryItem:
    return HistoryItem(
        lager_id="101",
        name=name,
        unit="300г",
        receipts=9,
        qty_total=Decimal(9),
        moments=[NOW],
        sources=sources,
    )


class _Pool:
    """Пул, який нічого не виконує: усе читання підмінене нижче."""


class _Row:

    def __init__(self, ident: str) -> None:
        self.id = ident


async def _mandates(rows, kinds, stored, monkeypatch, account: str = "guest"):
    async def _load(_pool, _who):
        if isinstance(stored, Exception):
            raise stored
        return stored

    monkeypatch.setattr("komora.agent.basket.saved_swaps.load", _load)
    return await _mandates_of(rows, kinds, _Pool(), account)


@pytest.mark.asyncio
async def test_a_row_without_an_agreement_proposes_the_guests_own_article(monkeypatch):
    kinds = [_kind([_seen("101", "Йогурт Живинка", 3), _seen("102", "Йогурт Галичина", 9)])]

    found = await _mandates([_Row("101")], kinds, {}, monkeypatch)

    assert not found["101"].agreed
    assert [link.article for link in found["101"].links] == ["102"]


@pytest.mark.asyncio
async def test_an_agreed_chain_wins_over_the_proposal(monkeypatch):
    kinds = [_kind([_seen("101", "Йогурт Живинка", 3), _seen("102", "Йогурт Галичина", 9)])]
    stored = {
        kind_key(ZHYVYNKA["name"]): saved_swaps.Saved(
            ZHYVYNKA["name"], (saved_swaps.Link("103", "Йогурт Ферма"),)
        )
    }

    found = await _mandates([_Row("101")], kinds, stored, monkeypatch)

    assert found["101"].agreed
    assert [link.article for link in found["101"].links] == ["103"]


@pytest.mark.asyncio
async def test_the_key_is_the_receipt_kind_and_not_the_label(monkeypatch):
    kinds = [_kind([_seen("101", "Йогурт Живинка", 3), _seen("102", "Йогурт Галичина", 9)])]
    stored = {
        kind_key("йогурт · питний"): saved_swaps.Saved(
            "йогурт · питний", (saved_swaps.Link("103", "Йогурт Ферма"),)
        )
    }

    found = await _mandates([_Row("101")], kinds, stored, monkeypatch)

    assert not found["101"].agreed, "мітка рядка не є ключем сховища"


@pytest.mark.asyncio
async def test_a_dead_store_leaves_the_pantry_working(monkeypatch):
    kinds = [_kind([_seen("101", "Йогурт Живинка", 3), _seen("102", "Йогурт Галичина", 9)])]

    found = await _mandates([_Row("101")], kinds, RuntimeError("нема бази"), monkeypatch)

    assert found == {}


@pytest.mark.asyncio
async def test_a_row_the_receipts_do_not_know_gets_no_mandate(monkeypatch):
    kinds = [_kind([_seen("101", "Йогурт Живинка", 3)])]

    found = await _mandates([_Row("manual-1")], kinds, {}, monkeypatch)

    assert found == {}


def _lines(saved, intent: str, *, trace=None, hint: HistoryItem | None = None):
    return build_lines(
        [intent],
        {intent: [ZHYVYNKA, GALYCHYNA, ALIEN]},
        {intent: hint} if hint is not None else {},
        {intent: {"chosen_id": "101", "qty": 1}},
        saved_chains=saved,
        trace=trace,
    )


def test_a_mandate_signed_in_the_pantry_reaches_the_comment_by_the_cycle_road():
    lines, _, _ = _lines({kind_key(ZHYVYNKA["name"]): ("102",)}, ZHYVYNKA["name"])

    (line,) = lines
    assert [alt.external_product_id for alt in line.chain] == ["102"]
    assert "Галичина" in build_comment(chain=line.chain).comment


def test_a_mandate_signed_in_the_pantry_reaches_the_comment_by_the_list_road():
    hint = _kind([_seen("101", "Йогурт Живинка", 3)])

    lines, _, _ = _lines({kind_key(ZHYVYNKA["name"]): ("102",)}, "йогурт · питний", hint=hint)

    (line,) = lines
    assert [alt.external_product_id for alt in line.chain] == ["102"]
    assert "Галичина" in build_comment(chain=line.chain).comment


def test_the_literal_key_still_wins_and_nothing_agreed_earlier_is_lost():
    hint = _kind([_seen("101", "Йогурт Живинка", 3)])
    stored = {kind_key("йогурт · питний"): ("103",), kind_key(ZHYVYNKA["name"]): ("102",)}

    lines, _, _ = _lines(stored, "йогурт · питний", hint=hint)

    (line,) = lines
    assert [alt.external_product_id for alt in line.chain] == ["103"]


def test_a_kind_the_history_does_not_recognise_keeps_the_computed_chain():
    found = saved_for("йогурт · питний", None, {kind_key(ZHYVYNKA["name"]): ("102",)})

    assert found.chain == ()
    assert not found.from_row


def test_the_trace_counts_mandates_that_came_from_the_pantry_row():
    from komora.agent.basket import Tracer

    trace = Tracer()
    hint = _kind([_seen("101", "Йогурт Живинка", 3)])
    _lines({kind_key(ZHYVYNKA["name"]): ("102",)}, "йогурт · питний", trace=trace, hint=hint)
    step = next(s for s in trace.steps if s.id == "step-saved-swaps")

    assert "з рядка комори: 1" in step.result_summary


ROAD_A = "Йогурт Живинка питний 1,5%"
ROAD_B = "Йогурт Живинка класичний 300г"
SLOT = {
    "start": "2026-09-09T09:00:00+00:00",
    "end": "2026-09-09T11:00:00+00:00",
    "available": True,
    "deliveryType": "DeliveryHome",
    "deliveryCost": 89,
    "minOrderCost": 599,
    "maxWeight": 50,
}


def _stand(tmp_path, orders: list[dict]) -> SilpoMCP:
    (tmp_path / "silpo_get_time_slots.json").write_text(
        json.dumps({"slots": [SLOT]}), encoding="utf-8"
    )
    (tmp_path / "silpo_get_my_offline_orders.json").write_text(
        json.dumps({"orders": orders, "meta": {"limit": 10, "offset": 0, "total": len(orders)}}),
        encoding="utf-8",
    )
    return SilpoMCP(settings=Settings.model_construct(), fixtures_dir=tmp_path)


def _bill(day: int, *names: str) -> dict:
    return {
        "createdAt": f"2026-09-{day:02d}T10:00:00",
        "sumReg": 53.49,
        "products": [
            {"lagerId": ROAD_ARTICLES[name], "name": name, "quantity": 1, "unit": "шт"}
            for name in names
        ],
    }


ROAD_ARTICLES = {ROAD_A: "901", ROAD_B: "902"}


@pytest.mark.asyncio
async def test_the_row_that_reaches_the_screen_carries_its_mandate(tmp_path, monkeypatch):

    async def _load(_pool, _who):
        return {}

    monkeypatch.setattr("komora.agent.basket.saved_swaps.load", _load)
    orders = [_bill(day, ROAD_A, ROAD_B) for day in (1, 3, 5, 7)]

    pantry = await pantry_live(
        _stand(tmp_path, orders),
        now=datetime(2026, 9, 8, 12, tzinfo=UTC),
        place=Location(branch_id="філія", source=BranchSource.CONFIG, address=None),
        pool=object(),
        account="guest",
    )

    rows = [item for item in pantry.items if item.mandate is not None]
    assert rows, "рядок з двома своїми артикулами мусить мати що запропонувати"
    assert not rows[0].mandate.agreed
    assert rows[0].mandate.links
