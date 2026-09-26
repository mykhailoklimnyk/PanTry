from __future__ import annotations

import json
from datetime import UTC, datetime

from komora.agent.basket import pantry_live
from komora.config import Settings
from komora.core.location import Location
from komora.core.location import Source as BranchSource
from komora.core.said import SOURCE_MANUAL, Said
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


def _receipt(day: int, *, name: str = "Молоко Ферма 2,5%") -> dict:
    return {
        "createdAt": f"2026-08-{day:02d}T10:00:00",
        "sumReg": 53.49,
        "products": [{"lagerId": "101", "name": name, "quantity": 1, "unit": "шт"}],
    }


def _stand(tmp_path, *, orders: list[dict]) -> SilpoMCP:
    (tmp_path / "silpo_get_time_slots.json").write_text(
        json.dumps({"slots": [SLOT]}), encoding="utf-8"
    )
    (tmp_path / "silpo_get_my_offline_orders.json").write_text(
        json.dumps({"orders": orders, "meta": {"limit": 10, "offset": 0, "total": len(orders)}}),
        encoding="utf-8",
    )
    return SilpoMCP(settings=Settings.model_construct(), fixtures_dir=tmp_path)


def _steps(pantry) -> dict[str, object]:
    return {step.id: step for step in pantry.trace}


async def test_the_pantry_trace_stands_even_when_nothing_was_read(tmp_path):
    pantry = await pantry_live(_stand(tmp_path, orders=[]), now=NOW, place=HERE)

    steps = _steps(pantry)
    assert list(steps) == [
        "step-pantry-place",
        "step-pantry-read",
        "step-pantry-names",
        "step-pantry-rows",
        "step-pantry-levels",
        "step-pantry-ceilings",
    ]
    assert steps["step-pantry-read"].args["чеків"] == 0
    assert steps["step-pantry-names"].args["видів"] == 0
    assert steps["step-pantry-rows"].args["рядків"] == 0
    assert steps["step-pantry-levels"].args["груп"] == 0
    assert steps["step-pantry-ceilings"].args["видів"] == 0


async def test_the_numbers_of_the_trace_are_the_numbers_of_the_screen(tmp_path):
    orders = [_receipt(day) for day in (5, 12, 19, 26)]

    pantry = await pantry_live(_stand(tmp_path, orders=orders), now=NOW, place=HERE)

    steps = _steps(pantry)
    assert steps["step-pantry-read"].args["чеків"] == pantry.receipts == 4
    assert steps["step-pantry-names"].args["видів"] == pantry.kinds
    assert steps["step-pantry-rows"].args["рядків"] == len(pantry.items)
    assert steps["step-pantry-levels"].args["рядків"] == len(pantry.items)
    ceilings = steps["step-pantry-ceilings"]
    assert ceilings.args["видів"] == pantry.kinds
    assert ceilings.args["рядків"] == len(pantry.items)
    assert ceilings.args["поза коморою"] == pantry.unlisted
    assert ceilings.args["список на похід"] == pantry.list_limit


async def test_without_a_model_the_naming_step_says_it_is_a_fallback(tmp_path):
    pantry = await pantry_live(
        _stand(tmp_path, orders=[_receipt(day) for day in (5, 12, 19, 26)]),
        now=NOW,
        place=HERE,
    )

    named = _steps(pantry)["step-pantry-names"]
    assert named.args["спитано"] == 0
    assert named.tool == "кеш назв"
    assert "без моделі" in (named.decision or "")


async def test_the_words_of_the_guest_are_counted_in_the_trace(tmp_path):
    orders = [_receipt(day) for day in (5, 12, 19, 26)]
    said = Said(
        source=SOURCE_MANUAL,
        marks={"молоко ферма": NOW},
        cycles={"молоко ферма": 2},
        hidden=("хліб київський",),
        listed={"батарейки": "Батарейки"},
    )

    pantry = await pantry_live(_stand(tmp_path, orders=orders), now=NOW, place=HERE, said=said)

    rows = _steps(pantry)["step-pantry-rows"]
    assert rows.args["позначок"] == 1
    assert rows.args["названих циклів"] == 1
    assert rows.args["сховано"] == 1
    assert rows.args["дописано"] == 1
    assert "слів гостя накладено 4" in rows.result_summary
    assert "режим списку" in (rows.decision or "")


async def test_the_mode_names_itself_even_when_it_is_the_usual_one(tmp_path):
    orders = [_receipt(day) for day in (5, 12, 19, 26)]

    counted = await pantry_live(_stand(tmp_path, orders=orders), now=NOW, place=HERE)
    listed = await pantry_live(
        _stand(tmp_path, orders=orders),
        now=NOW,
        place=HERE,
        said=Said(source=SOURCE_MANUAL, listed={"батарейки": "Батарейки"}),
    )

    assert _steps(counted)["step-pantry-rows"].args["режим"] == "чеки"
    assert _steps(listed)["step-pantry-rows"].args["режим"] == "список гостя"


async def test_the_scope_of_the_words_is_named_by_the_trace(tmp_path):
    orders = [_receipt(day) for day in (5, 12, 19, 26)]

    home = await pantry_live(
        _stand(tmp_path, orders=orders), now=NOW, place=HERE, said=Said(scope="pantry")
    )
    stray = await pantry_live(
        _stand(tmp_path, orders=orders), now=NOW, place=HERE, said=Said(scope="bar")
    )

    assert _steps(home)["step-pantry-rows"].args["область"] == "комора"
    assert _steps(stray)["step-pantry-rows"].args["область"] == "бар"


async def test_the_ceiling_about_the_guest_shows_its_own_distribution(tmp_path):
    orders = [_receipt(day) for day in (5, 12, 19, 26)]

    pantry = await pantry_live(_stand(tmp_path, orders=orders), now=NOW, place=HERE)

    ceilings = _steps(pantry)["step-pantry-ceilings"]
    said = ceilings.decision or ""
    assert "медіана" in said and "p75" in said
    assert f"беру {pantry.list_limit}" in said


async def test_a_shop_that_is_not_the_guests_says_so(tmp_path):
    pantry = await pantry_live(_stand(tmp_path, orders=[]), now=NOW, place=HERE)

    step = _steps(pantry)["step-pantry-place"]
    assert step.args["джерело"] == "config"
    assert step.args["магазин"] == "філія"
    assert "не за твоєю адресою" in step.result_summary
    assert step.tag == "не за адресою"


async def test_a_shop_from_the_address_does_not_cry_wolf(tmp_path):
    here = Location(branch_id="філія", source=BranchSource.ADDRESS, address=None)

    pantry = await pantry_live(_stand(tmp_path, orders=[]), now=NOW, place=here)

    step = _steps(pantry)["step-pantry-place"]
    assert step.args["джерело"] == "address"
    assert step.tag is None


async def test_a_run_that_never_asked_for_a_place_says_that_instead(tmp_path):
    pantry = await pantry_live(_stand(tmp_path, orders=[]), now=NOW)

    step = _steps(pantry)["step-pantry-place"]
    assert step.args["джерело"] == "не питали"
    assert "налаштувань" not in step.result_summary
