from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest

from komora.agent import basket
from komora.agent.basket import Naming, kind_key, manual_key, pantry_live
from komora.config import Settings
from komora.core.location import Location
from komora.core.location import Source as BranchSource
from komora.core.said import Said
from komora.mcp.client import SilpoMCP

NOW = datetime(2026, 9, 6, tzinfo=UTC)
HERE = Location(branch_id="філія", source=BranchSource.CONFIG, address=None)
SLOT = {
    "start": "2026-09-06T09:00:00+00:00",
    "end": "2026-09-06T11:00:00+00:00",
    "available": True,
    "deliveryType": "DeliveryHome",
    "deliveryCost": 89,
    "minOrderCost": 599,
    "maxWeight": 50,
}

DRINK = "Йогурт Живинка питний 1,5%"
BREAD = "Хліб Київхліб український"


class _Silent:

    class _Empty:
        data: dict[str, object] = {}  # noqa: RUF012

    async def decide(self, **_kw: object) -> _Empty:
        return self._Empty()


def _stand(tmp_path, *names: str) -> SilpoMCP:
    (tmp_path / "silpo_get_time_slots.json").write_text(
        json.dumps({"slots": [SLOT]}), encoding="utf-8"
    )
    orders = [
        {
            "createdAt": (NOW - timedelta(days=day)).strftime("%Y-%m-%d"),
            "sumReg": 50,
            "products": [
                {"lagerId": str(100 + index), "name": name, "quantity": 1, "unit": "шт"}
                for index, name in enumerate(names)
            ],
        }
        for day in (2, 9, 16, 23)
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
            DRINK: Naming(intent="йогурт", subtype="питний"),
            BREAD: Naming(intent="хліб", subtype="український"),
        }
    )


@pytest.mark.anyio
async def test_hiding_a_named_row_actually_hides_it(tmp_path, named) -> None:
    mcp = _stand(tmp_path, DRINK, BREAD)

    pantry = await pantry_live(
        mcp,
        llm=_Silent(),
        now=NOW,
        place=HERE,
        said=Said(hidden=(kind_key(DRINK),)),
    )

    assert [row.label for row in pantry.items] == ["хліб · український"]


@pytest.mark.anyio
async def test_the_hidden_row_names_itself(tmp_path, named) -> None:
    mcp = _stand(tmp_path, DRINK, BREAD)

    pantry = await pantry_live(
        mcp,
        llm=_Silent(),
        now=NOW,
        place=HERE,
        said=Said(hidden=(kind_key(DRINK),)),
    )

    assert pantry.hidden == ["йогурт · питний"]


@pytest.mark.anyio
async def test_hiding_one_subtype_does_not_take_its_twin(tmp_path) -> None:
    skyr = "Йогурт Галичина скір 0%"
    basket._cache_names(
        {
            DRINK: Naming(intent="йогурт", subtype="питний"),
            skyr: Naming(intent="йогурт", subtype="скір"),
        }
    )
    mcp = _stand(tmp_path, DRINK, skyr)

    pantry = await pantry_live(
        mcp,
        llm=_Silent(),
        now=NOW,
        place=HERE,
        said=Said(hidden=(kind_key(DRINK),)),
    )

    assert [row.label for row in pantry.items] == ["йогурт · скір"]


def test_the_display_separator_never_becomes_a_key():
    assert manual_key("йогурт · питний") == "йогурт питний"
    assert manual_key("йогурт · скір") == "йогурт скір"
    assert manual_key("йогурт · питний") != manual_key("йогурт · скір")


def test_a_word_the_guest_typed_is_untouched():
    assert manual_key("батарейки") == "батарейки"
    assert manual_key("  туалетний папір  ") == "туалетний папір"


def test_the_key_is_still_only_two_words_and_this_is_said_out_loud():
    assert manual_key("вода питна · дитяча") == manual_key("вода питна")
