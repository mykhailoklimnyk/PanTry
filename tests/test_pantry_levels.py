from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import ClassVar

import pytest

from komora.agent import basket
from komora.agent.basket import Naming, pantry_live
from komora.config import Settings
from komora.core.bar import DrinkKind
from komora.core.location import Location
from komora.core.location import Source as BranchSource
from komora.core.said import Said
from komora.mcp.client import SilpoMCP

NOW = datetime(2026, 8, 26, 12, tzinfo=UTC)
HERE = Location(branch_id="філія", source=BranchSource.CONFIG, address=None)
SLOT = {
    "start": "2026-08-27T09:00:00+00:00",
    "end": "2026-08-27T11:00:00+00:00",
    "available": True,
    "deliveryType": "DeliveryHome",
    "deliveryCost": 89,
    "minOrderCost": 599,
    "maxWeight": 50,
}

DRINKING = "Йогурт Живинка питний 1,5%"
SKYR = "Йогурт Галичина скір 0%"
BREAD = "Хліб Київхліб український"


_ARTICLES: dict[str, str] = {}


def _article(name: str) -> str:
    return _ARTICLES.setdefault(name, str(100 + len(_ARTICLES)))


def _receipt(day: int, *names: str) -> dict:
    return {
        "createdAt": f"2026-08-{day:02d}T10:00:00",
        "sumReg": 53.49,
        "products": [
            {"lagerId": _article(name), "name": name, "quantity": 1, "unit": "шт"}
            for name in names
        ],
    }


class _Silent:

    class _Empty:
        data: ClassVar[dict[str, object]] = {}

    async def decide(self, **_kw: object) -> _Empty:
        return self._Empty()


def _stand(tmp_path, orders: list[dict]) -> SilpoMCP:
    (tmp_path / "silpo_get_time_slots.json").write_text(
        json.dumps({"slots": [SLOT]}), encoding="utf-8"
    )
    (tmp_path / "silpo_get_my_offline_orders.json").write_text(
        json.dumps({"orders": orders, "meta": {"limit": 10, "offset": 0, "total": len(orders)}}),
        encoding="utf-8",
    )
    return SilpoMCP(settings=Settings.model_construct(), fixtures_dir=tmp_path)


@pytest.fixture
def named() -> None:
    basket._cache_names(
        {
            DRINKING: Naming(intent="йогурт", subtype="питний"),
            SKYR: Naming(intent="йогурт", subtype="скір"),
            BREAD: Naming(intent="хліб", subtype="український"),
        }
    )


def _rows(pantry) -> dict[str, str | None]:
    return {row.label: row.group for row in pantry.items}


async def test_two_subtypes_of_one_intent_stand_under_one_heading(tmp_path, named) -> None:
    orders = [_receipt(day, DRINKING, SKYR) for day in (5, 12, 19, 26)]

    pantry = await pantry_live(_stand(tmp_path, orders), now=NOW, place=HERE, llm=_Silent())

    assert _rows(pantry) == {"йогурт · питний": "йогурт", "йогурт · скір": "йогурт"}


async def test_the_key_under_the_heading_does_not_move(tmp_path, named) -> None:
    orders = [_receipt(day, DRINKING, SKYR) for day in (5, 12, 19, 26)]

    pantry = await pantry_live(_stand(tmp_path, orders), now=NOW, place=HERE, llm=_Silent())

    assert len(pantry.items) == 2
    assert {row.id for row in pantry.items} == {_article(DRINKING), _article(SKYR)}
    assert all(row.cycle_days == 7 for row in pantry.items)


async def test_a_lone_subtype_gets_no_heading(tmp_path, named) -> None:
    orders = [_receipt(day, DRINKING, BREAD) for day in (5, 12, 19, 26)]

    pantry = await pantry_live(_stand(tmp_path, orders), now=NOW, place=HERE, llm=_Silent())

    assert _rows(pantry) == {"йогурт · питний": None, "хліб · український": None}


async def test_the_guest_can_take_the_heading_apart(tmp_path, named) -> None:
    orders = [_receipt(day, DRINKING, SKYR) for day in (5, 12, 19, 26)]

    pantry = await pantry_live(
        _stand(tmp_path, orders),
        now=NOW,
        place=HERE,
        llm=_Silent(),
        said=Said(apart=("йогурт",)),
    )

    assert _rows(pantry) == {"йогурт · питний": None, "йогурт · скір": None}


async def test_the_trace_names_the_folding(tmp_path, named) -> None:
    orders = [_receipt(day, DRINKING, SKYR, BREAD) for day in (5, 12, 19, 26)]

    pantry = await pantry_live(_stand(tmp_path, orders), now=NOW, place=HERE, llm=_Silent())

    step = next(step for step in pantry.trace if step.id == "step-pantry-levels")
    assert step.args["груп"] == 1
    assert step.args["згорнуто"] == 2
    assert step.args["рядків"] == len(pantry.items) == 3


async def test_members_of_a_group_stand_together(tmp_path, named) -> None:
    orders = [_receipt(day, DRINKING, BREAD, SKYR) for day in (5, 12, 19, 26)]

    pantry = await pantry_live(_stand(tmp_path, orders), now=NOW, place=HERE, llm=_Silent())

    groups = [row.group for row in pantry.items]
    assert groups.count("йогурт") == 2
    first = groups.index("йогурт")
    assert groups[first : first + 2] == ["йогурт", "йогурт"]


async def test_the_row_names_the_articles_it_was_made_of(tmp_path, named) -> None:
    orders = [
        _receipt(day, DRINKING if day > 12 else "Йогурт Живинка питний 2,5%")
        for day in (5, 12, 19, 26)
    ]

    pantry = await pantry_live(_stand(tmp_path, orders), now=NOW, place=HERE, llm=_Silent())

    row = next(row for row in pantry.items if row.label == "йогурт · питний")
    assert [part.label for part in row.parts] == [
        "Йогурт Живинка питний 1,5%",
        "Йогурт Живинка питний 2,5%",
    ]
    assert [part.receipts for part in row.parts] == [2, 2]
    assert row.parts[0].days_since == 0
    assert row.parts[0].fresh is True


async def test_a_single_article_is_still_named_under_its_row(tmp_path, named) -> None:
    orders = [_receipt(day, BREAD) for day in (5, 12, 19, 26)]

    pantry = await pantry_live(_stand(tmp_path, orders), now=NOW, place=HERE, llm=_Silent())

    row = next(row for row in pantry.items if row.label == "хліб · український")
    assert [part.label for part in row.parts] == [BREAD]
    assert row.parts[0].unit == "шт"


BEER = "Пиво Чернігівське світле 0,5л"


async def test_alcohol_is_kept_by_the_bar_and_named_out_loud(tmp_path) -> None:
    basket._cache_names({BEER: Naming(intent="пиво", subtype="світле", drink=DrinkKind.LIGHT)})
    orders = [_receipt(day, BEER, BREAD) for day in (10, 17, 24)]

    pantry = await pantry_live(_stand(tmp_path, orders), now=NOW, place=HERE, llm=_Silent())

    assert "пиво · світле" not in _rows(pantry)
    assert pantry.at_bar == ["пиво · світле"]
    assert [label for label in _rows(pantry) if "ліб" in label]
    assert pantry.hidden == []
