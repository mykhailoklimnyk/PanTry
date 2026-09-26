from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from komora.agent import basket
from komora.agent.basket import Naming, kind_key, pantry_live
from komora.config import Settings
from komora.core.location import Location
from komora.core.location import Source as BranchSource
from komora.core.said import Said
from komora.mcp.client import SilpoMCP

NOW = datetime(2026, 9, 20, tzinfo=UTC)
HERE = Location(branch_id="філія", source=BranchSource.CONFIG, address=None)
SLOT = {
    "start": "2026-09-20T09:00:00+00:00",
    "end": "2026-09-20T11:00:00+00:00",
    "available": True,
    "deliveryType": "DeliveryHome",
    "deliveryCost": 89,
    "minOrderCost": 599,
    "maxWeight": 50,
}

OLDER = "Молоко Яготинське 2,5%"
FRESHER = "Молоко Простонаше 2,5%"
BREAD = "Хліб Київхліб український"


class _Silent:

    class _Empty:
        data: dict[str, object] = {}  # noqa: RUF012

    async def decide(self, **_kw: object) -> _Empty:
        return self._Empty()


def _stand(tmp_path, bought: dict[str, list[int]]) -> SilpoMCP:
    (tmp_path / "silpo_get_time_slots.json").write_text(
        json.dumps({"slots": [SLOT]}), encoding="utf-8"
    )
    lagers = {OLDER: "201", FRESHER: "202", BREAD: "301"}
    days: dict[int, list[str]] = {}
    for name, when in bought.items():
        for day in when:
            days.setdefault(day, []).append(name)
    orders = [
        {
            "createdAt": (NOW - timedelta(days=day)).strftime("%Y-%m-%d"),
            "sumReg": 50,
            "products": [
                {"lagerId": lagers[name], "name": name, "quantity": 1, "unit": "шт"}
                for name in names
            ],
        }
        for day, names in sorted(days.items())
    ]
    (tmp_path / "silpo_get_my_offline_orders.json").write_text(
        json.dumps({"orders": orders, "meta": {"limit": 10, "offset": 0, "total": len(orders)}}),
        encoding="utf-8",
    )
    return SilpoMCP(settings=Settings.model_construct(), fixtures_dir=tmp_path)


@pytest.fixture
def named() -> None:
    basket._cache_names(
        {
            OLDER: Naming(intent="молоко", subtype=None),
            FRESHER: Naming(intent="молоко", subtype=None),
            BREAD: Naming(intent="хліб", subtype="український"),
        }
    )


def _bought() -> dict[str, list[int]]:
    return {
        OLDER: [30, 23, 16],
        FRESHER: [9, 5, 2],
        BREAD: [12, 8, 4],
    }


@pytest.mark.anyio
async def test_hiding_the_older_sku_hides_the_whole_label(tmp_path, named) -> None:
    mcp = _stand(tmp_path, _bought())

    pantry = await pantry_live(
        mcp,
        llm=_Silent(),
        now=NOW,
        place=HERE,
        said=Said(hidden=(kind_key(OLDER),)),
    )

    assert [row.label for row in pantry.items] == ["хліб · український"]


@pytest.mark.anyio
async def test_the_row_hidden_that_way_can_be_brought_back(tmp_path, named) -> None:
    mcp = _stand(tmp_path, _bought())

    pantry = await pantry_live(
        mcp,
        llm=_Silent(),
        now=NOW,
        place=HERE,
        said=Said(hidden=(kind_key(OLDER),)),
    )

    assert pantry.hidden == ["молоко"]


@pytest.mark.anyio
async def test_a_different_label_is_not_taken_along(tmp_path, named) -> None:
    mcp = _stand(tmp_path, _bought())

    pantry = await pantry_live(
        mcp,
        llm=_Silent(),
        now=NOW,
        place=HERE,
        said=Said(hidden=(kind_key(BREAD),)),
    )

    assert [row.label for row in pantry.items] == ["молоко"]
