from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from komora.agent.basket import pantry_live, read_receipts
from komora.agent.llm import Decision, Usage
from komora.agent.pantry import forget_loop, refine
from komora.config import Settings
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


class _Loop:

    model = "fake-loop"

    def __init__(self, *batches: dict[str, Any]) -> None:
        self.batches = list(batches)
        self.planned = 0
        self.asked: list[str] = []
        self.systems: list[str] = []

    async def decide(self, *, system, user, schema, **_: Any) -> Decision:
        answer: dict[str, Any] = {}
        if "steps" in schema.get("properties", {}):
            self.planned += 1
            self.asked.append(user)
            self.systems.append(system)
            answer = self.batches.pop(0) if self.batches else {"steps": []}
        return Decision(
            data=answer,
            text=json.dumps(answer),
            model=self.model,
            usage=Usage(10, 5),
            duration_ms=1,
        )


def _stand(tmp_path, *, shelf: str | None = "900г") -> SilpoMCP:
    orders = [
        {
            "createdAt": f"2026-08-{day:02d}T10:00:00",
            "sumReg": 53.49,
            "products": [
                {"lagerId": "101", "name": "Молоко Ферма 2,5%", "quantity": 1, "unit": "шт"}
            ],
        }
        for day in (10, 16, 22)
    ]
    (tmp_path / "silpo_get_time_slots.json").write_text(
        json.dumps({"slots": [SLOT]}), encoding="utf-8"
    )
    (tmp_path / "silpo_get_my_offline_orders.json").write_text(
        json.dumps({"orders": orders, "meta": {"limit": 10, "offset": 0, "total": len(orders)}}),
        encoding="utf-8",
    )
    products = (
        []
        if shelf is None
        else [
            {
                "id": "00000000-0000-4000-8000-000000000101",
                "name": "Молоко Ферма 2,5% 900 г",
                "externalProductId": 101,
                "displayRatio": shelf,
                "weighted": False,
                "price": 53.49,
                "available": True,
            }
        ]
    )
    (tmp_path / "silpo_find_products_batch.json").write_text(
        json.dumps({"queries": [{"query": "101", "products": products}]}), encoding="utf-8"
    )
    return SilpoMCP(settings=Settings.model_construct(), fixtures_dir=tmp_path)


def _batch(*names: str, **extra: object) -> dict[str, Any]:
    return {"steps": [{"step": name, "why": "треба"} for name in names], **extra}


async def _ready(tmp_path, llm: Any, *, shelf: str | None = "900г", cold_draw: bool = False):
    forget_loop()
    stand = _stand(tmp_path, shelf=shelf)
    said = Said()
    read = await read_receipts(stand, place=HERE, now=NOW)
    drawn = await pantry_live(
        stand, llm=None if cold_draw else llm, place=HERE, now=NOW, receipts=read, said=said
    )
    return stand, read, drawn, said


async def _spin(
    tmp_path,
    llm: _Loop,
    *,
    turns: int,
    account: str = "гість",
    shelf: str | None = "900г",
    cold_draw: bool = False,
    cold: bool = False,
    continuing: bool = False,
):
    stand, read, drawn, said = await _ready(tmp_path, llm, shelf=shelf, cold_draw=cold_draw)
    return await refine(
        stand,
        drawn=drawn,
        read=read,
        said=said,
        llm=llm,
        now=NOW,
        place=HERE,
        account=account,
        settings=Settings.model_construct(pantry_turns=turns),
        cold=cold,
        continuing=continuing,
    )


def _ids(done) -> list[str]:
    return [step.id for step in done.pantry.trace]


@pytest.mark.anyio
async def test_the_model_is_asked_once_per_turn_and_not_once_per_run(tmp_path):
    llm = _Loop(_batch("pantry.name"), _batch("pantry.rhythm"))
    done = await _spin(tmp_path, llm, turns=3)

    assert llm.planned >= 2, "петля спитала модель один раз -- це не петля"
    assert done.ran is True


@pytest.mark.anyio
async def test_the_second_turn_sees_what_the_first_one_did(tmp_path):
    llm = _Loop(_batch("pantry.name"), _batch("pantry.rhythm"))
    await _spin(tmp_path, llm, turns=3)

    second = json.loads(llm.asked[1])
    assert "ґрунт" in second
    assert second["ґрунт"]["оберт"] == 2
    assert "pantry.name" in second["ґрунт"].get("кроки вже зроблені", [])


@pytest.mark.anyio
async def test_the_first_turn_has_no_ground_to_report_and_says_nothing_about_it(tmp_path):
    llm = _Loop(_batch("pantry.name"))
    await _spin(tmp_path, llm, turns=2)

    first = json.loads(llm.asked[0])["ґрунт"]
    assert first["оберт"] == 1
    assert "не влізло в пачку" not in first
    assert "зрізано валідатором" not in first


@pytest.mark.anyio
async def test_every_turn_names_itself_in_the_trace(tmp_path):
    llm = _Loop(_batch("pantry.name"), _batch("pantry.rhythm"))
    done = await _spin(tmp_path, llm, turns=3)

    assert _ids(done).count("step-batch") >= 2
    assert "step-stop" in _ids(done)
    assert "step-pantry-plan" not in _ids(done)


@pytest.mark.anyio
async def test_the_stop_step_names_the_reason_not_just_the_fact(tmp_path):
    llm = _Loop(_batch("pantry.name"))
    done = await _spin(tmp_path, llm, turns=2)

    (stop,) = [step for step in done.pantry.trace if step.id == "step-stop"]
    assert stop.args["причина"] in {"done", "ceiling", "stuck", "broken"}
    assert stop.args["викликів моделі"] >= 1
    assert "петля спинилась" in stop.result_summary


@pytest.mark.anyio
async def test_two_empty_turns_in_a_row_stop_the_loop_before_the_ceiling(tmp_path):
    llm = _Loop(_batch(), _batch(), _batch())
    done = await _spin(tmp_path, llm, turns=6)

    (stop,) = [step for step in done.pantry.trace if step.id == "step-stop"]
    assert stop.args["причина"] == "stuck"
    assert stop.args["обертів"] < 6


@pytest.mark.anyio
async def test_a_ceiling_of_zero_is_todays_single_plan(tmp_path):
    llm = _Loop(_batch("pantry.name"))
    done = await _spin(tmp_path, llm, turns=0)

    assert llm.planned == 1
    assert "step-pantry-plan" in _ids(done)
    assert "step-batch" not in _ids(done)
    assert "step-stop" not in _ids(done)


@pytest.mark.anyio
async def test_the_pantry_is_redrawn_between_turns_and_the_goal_still_stands(tmp_path):
    llm = _Loop(_batch("pantry.name"), _batch("pantry.rhythm"))
    done = await _spin(tmp_path, llm, turns=3)

    ids = _ids(done)
    assert ids.count("step-pantry-draw") >= 2
    assert "step-pantry-goal" in ids


@pytest.mark.anyio
async def test_the_batch_prompt_is_not_the_single_plan_prompt(tmp_path):
    llm = _Loop(_batch("pantry.name"))
    await _spin(tmp_path, llm, turns=2)

    assert "ПАЧКУ" in llm.systems[0]
    assert "СЛОВНИК КРОКІВ" in llm.systems[0]


class _Home(_Loop):

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.offered: list[str] = []

    async def decide(self, *, system, user, schema, **kw: Any) -> Decision:
        if "questions" in schema.get("properties", {}):
            self.offered = list(json.loads(user).get("види") or [])
            asked = (
                [
                    {
                        "label": self.offered[0],
                        "ask": "як швидко це у вас закінчується?",
                        "covers": self.offered[1:3],
                    }
                ]
                if self.offered
                else []
            )
            return Decision(
                data={"questions": asked},
                text=json.dumps({"questions": asked}),
                model=self.model,
                usage=Usage(1, 1),
                duration_ms=1,
            )
        fields = schema.get("properties", {}).get("kinds", {}).get("items", {})
        keys = fields.get("properties", {})
        if "intent" in keys:
            answer: dict[str, Any] = {
                "kinds": [
                    {
                        "name": "Молоко Ферма 2,5%",
                        "intent": "молоко",
                        "subtype": None,
                        "drink": None,
                    }
                ]
            }
        elif "sanity" in keys:
            answer = {
                "kinds": [
                    {
                        "label": "молоко",
                        "sanity": "беруть про запас",
                        "rhythm_lies": True,
                        "per_day": None,
                        "per_day_unit": None,
                        "aisle": None,
                    }
                ]
            }
        else:
            return await super().decide(system=system, user=user, schema=schema, **kw)
        return Decision(
            data=answer,
            text=json.dumps(answer),
            model=self.model,
            usage=Usage(10, 5),
            duration_ms=1,
        )


@pytest.mark.anyio
async def test_the_question_step_judges_the_pantry_the_guest_will_see(tmp_path):
    forget_loop()
    stand = _stand(tmp_path)
    said = Said()
    read = await read_receipts(stand, place=HERE, now=NOW)
    cold = await pantry_live(stand, llm=None, place=HERE, now=NOW, receipts=read, said=said)
    assert [row.ask for row in cold.items] == [False], "стенд не холодний -- рядок уже питає"

    llm = _Home(_batch("pantry.name", "pantry.rhythm", "pantry.ask"))
    done = await refine(
        stand,
        drawn=cold,
        read=read,
        said=said,
        llm=llm,
        now=NOW,
        place=HERE,
        account="гість",
        settings=Settings.model_construct(pantry_turns=1),
    )

    assert [row.ask for row in done.pantry.items] == [True]
    unasked = [duty for duty in done.goal.unmet if "питання" in duty.name]
    assert unasked == [], f"крок питання розійшовся з вироком мети: {unasked}"
    (ask,) = [step for step in done.pantry.trace if step.id == "step-pantry-ask"]
    assert "нема про що" not in ask.result_summary


@pytest.mark.anyio
async def test_a_loop_that_closed_the_goal_does_not_spend_the_rest_of_the_ceiling(tmp_path):
    llm = _Home(_batch("pantry.name", "pantry.rhythm", "pantry.ask"))
    done = await _spin(tmp_path, llm, turns=3)

    assert done.goal is not None and done.goal.ok, "мета не досягнута -- тест міряє не те"
    assert llm.planned == 1, f"петля спитала модель {llm.planned} рази при досягнутій меті"
    (stop,) = [step for step in done.pantry.trace if step.id == "step-stop"]
    assert stop.args["причина"] == "done"


@pytest.mark.anyio
async def test_zamovchuvannia_teper_petlia_a_ne_odyn_plan(tmp_path):
    assert Settings.model_construct().pantry_turns == 4

    llm = _Loop(_batch("pantry.name"), _batch("pantry.rhythm"))
    stand, read, drawn, said = await _ready(tmp_path, llm)
    done = await refine(stand, drawn=drawn, read=read, said=said, llm=llm, now=NOW, place=HERE)

    ids = [step.id for step in done.pantry.trace]
    assert "step-batch" in ids
    assert "step-pantry-plan" not in ids


@pytest.mark.anyio
async def test_stelia_ne_ie_planom_vytrat_bo_yaloviy_obert_spyniaie(tmp_path):
    llm = _Loop(_batch("pantry.name"))
    done = await _spin(tmp_path, llm, turns=5)

    batches = [step for step in done.pantry.trace if step.id == "step-batch"]
    assert len(batches) == 3


@pytest.mark.anyio
async def test_the_batch_runs_in_the_order_the_model_sent_it(tmp_path):
    llm = _Loop(_batch("pantry.ask", "pantry.name"))
    done = await _spin(tmp_path, llm, turns=1)

    ids = _ids(done)
    assert "step-pantry-ask" in ids and "step-pantry-name" in ids
    assert ids.index("step-pantry-ask") < ids.index("step-pantry-name")
    assert ids.index("step-pantry-draw") > ids.index("step-pantry-name")


@pytest.mark.anyio
async def test_the_questions_see_the_redrawn_pantry_and_the_turn_draws_once(tmp_path):
    llm = _Loop(_batch("pantry.name", "pantry.ask"))
    done = await _spin(tmp_path, llm, turns=1)

    ids = _ids(done)
    assert (
        ids.index("step-pantry-name") < ids.index("step-pantry-draw") < ids.index("step-pantry-ask")
    )
    assert ids.count("step-pantry-draw") == 1


@pytest.mark.anyio
async def test_a_step_outside_the_works_names_itself_instead_of_vanishing(tmp_path):
    llm = _Loop(_batch("pantry.draw", "pantry.name"))
    done = await _spin(tmp_path, llm, turns=1)

    ids = _ids(done)
    assert ids.count("step-pantry-draw") == 1
    (goal,) = [step for step in done.pantry.trace if step.id == "step-pantry-goal"]
    assert goal.args.get("поза набором") == ["pantry.draw"]


def _step(done, step_id: str):
    (step,) = [step for step in done.pantry.trace if step.id == step_id]
    return step


@pytest.mark.anyio
async def test_the_shelf_step_asks_the_shelf_and_the_question_carries_the_packaging(tmp_path):
    llm = _Home(
        _batch("pantry.name", "pantry.rhythm"),
        {"steps": [{"step": "pantry.shelf", "labels": ["молоко"]}, {"step": "pantry.ask"}]},
    )
    done = await _spin(tmp_path, llm, turns=3)

    shelf = _step(done, "step-pantry-shelf")
    assert shelf.args["на полиці"] == 1 and shelf.args["адресно"] == 1
    assert "за оберт" in shelf.args["стеля"]
    assert shelf.tool == "silpo_find_products_batch"
    (probe,) = done.probes
    assert "фасовка 900г" in probe.usual and "1 шт" in probe.usual


@pytest.mark.anyio
async def test_a_label_the_pantry_lacks_is_cut_by_itself_and_named(tmp_path):
    llm = _Home(
        _batch("pantry.name", "pantry.rhythm"),
        {"steps": [{"step": "pantry.shelf", "labels": ["молоко", "єдиноріг"]}]},
    )
    done = await _spin(tmp_path, llm, turns=2)

    shelf = _step(done, "step-pantry-shelf")
    assert shelf.args["на полиці"] == 1
    assert shelf.args["міток немає в коморі"] == ["єдиноріг"]


@pytest.mark.anyio
async def test_an_empty_shelf_is_a_fact_the_next_turn_sees(tmp_path):
    llm = _Home(
        _batch("pantry.name", "pantry.rhythm"),
        {"steps": [{"step": "pantry.shelf"}]},
        _batch("pantry.ask"),
    )
    done = await _spin(tmp_path, llm, turns=4, shelf=None)

    assert _step(done, "step-pantry-shelf").args["на полиці"] == 0
    third = json.loads(llm.asked[2])
    assert third["стан"]["фасовка з полиці відома"] == 1
    (probe,) = done.probes
    assert "на полиці зараз немає" in probe.usual


@pytest.mark.anyio
async def test_a_list_sent_to_a_step_that_ignores_it_is_named(tmp_path):
    llm = _Loop({"steps": [{"step": "pantry.name", "labels": ["молоко"]}]})
    done = await _spin(tmp_path, llm, turns=1)

    assert _step(done, "step-pantry-goal").args["перелік міток не читають"] == ["pantry.name"]


@pytest.mark.anyio
async def test_the_state_the_model_sees_is_of_this_turn_and_not_of_the_first(tmp_path):
    llm = _Home(_batch("pantry.name", "pantry.rhythm"), _batch("pantry.ask"))
    await _spin(tmp_path, llm, turns=2, cold_draw=True)

    first, second = (json.loads(user)["стан"] for user in llm.asked[:2])
    assert first["без мітки виду"] == 1
    assert second["без мітки виду"] == 0
    assert second["мовчазні рядки (мітки)"] == ["молоко"]


@pytest.mark.anyio
async def test_the_shelf_sees_the_rows_after_the_verdict_in_the_same_batch(tmp_path):
    llm = _Home(
        {
            "steps": [
                {"step": "pantry.name"},
                {"step": "pantry.rhythm"},
                {"step": "pantry.shelf"},
                {"step": "pantry.ask"},
            ]
        }
    )
    done = await _spin(tmp_path, llm, turns=2, cold_draw=True)

    ids = _ids(done)
    assert _step(done, "step-pantry-shelf").args["спитав"] == 1
    assert (
        ids.index("step-pantry-rhythm")
        < ids.index("step-pantry-draw")
        < ids.index("step-pantry-shelf")
    )
    assert ids.count("step-pantry-draw") == 1


@pytest.mark.anyio
async def test_a_fact_that_changed_under_the_same_name_counts_as_learned():
    from komora.agent.spine import spin
    from komora.core.facts import Facts
    from komora.core.plan import Plan, Step
    from komora.core.spine import Halt

    facts = Facts()
    grown: dict[str, str] = {}

    async def plan(soil):
        from komora.agent.spine import Batch

        return Batch(plan=Plan(steps=(Step(name="pantry.shelf"),)), stop=False, why="", tokens=1)

    async def run(batch):
        grown[str(len(grown))] = "фасовка"
        facts.put("packaging", dict(grown), step="pantry.shelf")
        return batch.carried

    spun = await spin(
        plan=plan,
        run=run,
        facts=facts,
        duties=lambda: ("є борг",),
        verdict=lambda carried: None,
        ceiling=3,
    )
    assert [turn.learned for turn in spun.turns] == [("packaging",)] * 3
    assert spun.reason is Halt.CEILING

    same = Facts()

    async def run_same(batch):
        same.put("packaging", {"1": "фасовка"}, step="pantry.shelf")
        return batch.carried

    stuck = await spin(
        plan=plan,
        run=run_same,
        facts=same,
        duties=lambda: ("є борг",),
        verdict=lambda carried: None,
        ceiling=5,
    )
    assert stuck.reason is Halt.STUCK and len(stuck.turns) == 3


@pytest.mark.anyio
async def test_the_verdict_step_judges_only_the_labels_it_was_addressed_to(tmp_path):
    llm = _Home(
        _batch("pantry.name"),
        {"steps": [{"step": "pantry.rhythm", "labels": ["молоко", "єдиноріг"]}]},
        {"steps": [{"step": "pantry.keeps", "labels": ["єдиноріг"]}]},
    )
    done = await _spin(tmp_path, llm, turns=3, cold_draw=True)

    rhythm = _step(done, "step-pantry-rhythm")
    assert rhythm.args["міток"] == 1 and rhythm.args["адресно"] == 1
    assert rhythm.args["міток немає в коморі"] == ["єдиноріг"]
    keeps = _step(done, "step-pantry-keeps")
    assert keeps.args["міток"] == 0 and "адресно" not in keeps.args
    assert keeps.args["міток немає в коморі"] == ["єдиноріг"]


@pytest.mark.anyio
async def test_the_naming_call_announces_itself_before_it_goes(tmp_path):
    llm = _Loop(_batch("pantry.name"))
    done = await _spin(tmp_path, llm, turns=2)

    ids = _ids(done)
    assert "step-naming-ahead" in ids
    assert ids.index("step-naming-ahead") < ids.index("step-pantry-name")
    ahead = next(step for step in done.pantry.trace if step.id == "step-naming-ahead")
    assert ahead.result_summary.startswith("називаю ")
    assert ahead.args["спитаю"] > 0


@pytest.mark.anyio
async def test_a_turn_without_naming_promises_no_naming(tmp_path):
    llm = _Loop(_batch("pantry.rhythm"))
    done = await _spin(tmp_path, llm, turns=2)

    assert "step-naming-ahead" not in _ids(done)


@pytest.mark.anyio
async def test_a_continued_cold_fill_names_from_process_memory(tmp_path, monkeypatch):
    import komora.agent.steps.pantry as steps

    seen: list[dict[str, Any]] = []
    real = steps.intent_names

    async def spy(llm, names, **kw):
        seen.append({"live": llm is not None, **kw})
        return await real(llm, names, **kw)

    monkeypatch.setattr(steps, "intent_names", spy)

    await _spin(tmp_path, _Loop(_batch("pantry.name")), turns=1, cold=True, continuing=True)
    live = [call for call in seen if call["live"]]
    assert live, "крок називання не пішов у модель -- тест ні про що"
    assert all(call["use_cache"] is False and call["memory"] is True for call in live)

    seen.clear()
    await _spin(tmp_path, _Loop(_batch("pantry.name")), turns=1, cold=True)
    assert all(call["memory"] is False for call in seen if call["live"])
