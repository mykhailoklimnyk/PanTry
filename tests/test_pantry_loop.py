from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import pytest

from komora.agent.basket import pantry_live, read_receipts
from komora.agent.llm import Decision, Usage
from komora.agent.pantry import (
    NO_MODEL,
    NOTHING_FOUND,
    NOTHING_MISSING,
    NOTHING_NEW,
    NOTHING_YET,
    _note,
    forget_loop,
    refine,
)
from komora.config import Settings
from komora.core.location import Location
from komora.core.location import Source as BranchSource
from komora.core.said import Said
from komora.mcp.client import SilpoMCP

NOW = datetime(2026, 8, 26, 12, tzinfo=UTC)
ONE_PLAN = Settings.model_construct(pantry_turns=0)
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


class _Model:

    model = "fake"

    def __init__(self, *plans: dict[str, Any]) -> None:
        self.plans = list(plans)
        self.calls = 0
        self.planned = 0
        self.asked: list[str] = []

    async def decide(self, *, system, user, schema, **_: Any) -> Decision:
        self.calls += 1
        self.asked.append(user)
        answer: dict[str, Any] = {}
        if "steps" in schema.get("properties", {}):
            self.planned += 1
            answer = self.plans.pop(0) if self.plans else {"steps": []}
        return Decision(
            data=answer,
            text=json.dumps(answer),
            model=self.model,
            usage=Usage(10, 5),
            duration_ms=1,
        )


def _stand(tmp_path) -> SilpoMCP:
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
    return SilpoMCP(settings=Settings.model_construct(), fixtures_dir=tmp_path)


def _plan(*names: str) -> dict[str, Any]:
    return {"steps": [{"step": name, "why": "треба"} for name in names]}


async def _ready(tmp_path, llm: Any) -> tuple[SilpoMCP, Any, Any, Said]:
    forget_loop()
    stand = _stand(tmp_path)
    said = Said()
    read = await read_receipts(stand, place=HERE, now=NOW)
    drawn = await pantry_live(stand, llm=llm, place=HERE, now=NOW, receipts=read, said=said)
    return stand, read, drawn, said


def _steps(pantry) -> list[str]:
    return [step.id for step in pantry.trace]


@pytest.mark.anyio
async def test_without_a_model_the_loop_does_not_run_and_says_why(tmp_path):
    stand, read, drawn, said = await _ready(tmp_path, None)

    done = await refine(
        stand, settings=ONE_PLAN, drawn=drawn, read=read, said=said, llm=None, now=NOW, place=HERE
    )

    assert done.ran is False
    assert done.note == NO_MODEL
    assert [row.id for row in done.pantry.items] == [row.id for row in drawn.items]
    assert _steps(done.pantry)[-1] == "step-pantry-loop"


@pytest.mark.anyio
async def test_the_plan_decides_which_steps_run_and_the_redraw_happens_anyway(tmp_path):
    llm = _Model(_plan("pantry.name"))
    stand, read, drawn, said = await _ready(tmp_path, llm)

    done = await refine(
        stand, settings=ONE_PLAN, drawn=drawn, read=read, said=said, llm=llm, now=NOW, place=HERE
    )

    steps = _steps(done.pantry)
    assert "step-pantry-name" in steps
    assert "step-pantry-rhythm" not in steps
    assert "step-pantry-keeps" not in steps
    assert "step-pantry-draw" in steps
    assert done.note == NOTHING_FOUND


def test_an_empty_pantry_does_not_say_nothing_was_missing():
    from komora.api.schemas import Pantry

    empty = Pantry(items=[], receipts=0, orders=4, kinds=0, tracked_from=3)

    assert _note([], empty, empty) == NOTHING_YET
    assert _note(["pantry.name"], empty, empty) == NOTHING_YET


@pytest.mark.anyio
async def test_an_empty_plan_is_a_legal_answer_and_names_itself(tmp_path):
    llm = _Model({"steps": []})
    stand, read, drawn, said = await _ready(tmp_path, llm)

    done = await refine(
        stand, settings=ONE_PLAN, drawn=drawn, read=read, said=said, llm=llm, now=NOW, place=HERE
    )

    assert done.note == NOTHING_MISSING
    assert "step-pantry-name" not in _steps(done.pantry)
    assert "step-pantry-draw" in _steps(done.pantry)


@pytest.mark.anyio
async def test_the_same_input_twice_does_not_ask_the_model_again(tmp_path):
    llm = _Model(_plan("pantry.name"))
    stand, read, drawn, said = await _ready(tmp_path, llm)

    first = await refine(
        stand,
        settings=ONE_PLAN,
        drawn=drawn,
        read=read,
        said=said,
        llm=llm,
        now=NOW,
        place=HERE,
        account="гість",
    )
    spent = llm.calls
    again = await refine(
        stand,
        drawn=first.pantry,
        read=read,
        said=said,
        llm=llm,
        now=NOW,
        place=HERE,
        account="гість",
    )

    assert again.note == NOTHING_NEW
    assert again.ran is False
    assert llm.calls == spent
    assert _steps(again.pantry)[-1] == "step-pantry-loop"


@pytest.mark.anyio
async def test_a_quiet_loop_says_so_in_the_CHANNEL_and_not_only_at_the_end(tmp_path):
    llm = _Model(_plan("pantry.name"))
    stand, read, drawn, said = await _ready(tmp_path, llm)
    first = await refine(
        stand,
        settings=ONE_PLAN,
        drawn=drawn,
        read=read,
        said=said,
        llm=llm,
        now=NOW,
        place=HERE,
        account="гість",
    )
    live: list[str] = []

    again = await refine(
        stand,
        drawn=first.pantry,
        read=read,
        said=said,
        llm=llm,
        now=NOW,
        place=HERE,
        account="гість",
        on_step=lambda step: live.append(step.id),
    )

    assert again.note == NOTHING_NEW
    assert live == ["step-pantry-loop"], "тиха петля лишила читача з порожнім журналом"


@pytest.mark.anyio
async def test_a_loop_without_a_model_says_so_in_the_channel_too(tmp_path):
    stand, read, drawn, said = await _ready(tmp_path, _Model(_plan("pantry.name")))
    live: list[str] = []

    done = await refine(
        stand,
        drawn=drawn,
        read=read,
        said=said,
        llm=None,
        now=NOW,
        place=HERE,
        on_step=lambda step: live.append(step.id),
    )

    assert done.ran is False
    assert live == ["step-pantry-loop"]


@pytest.mark.anyio
async def test_the_loop_names_its_goal_in_the_trace_even_when_it_is_met(tmp_path):
    llm = _Model({"steps": []})
    stand, read, drawn, said = await _ready(tmp_path, llm)

    done = await refine(
        stand, settings=ONE_PLAN, drawn=drawn, read=read, said=said, llm=llm, now=NOW, place=HERE
    )

    goal = next(step for step in done.pantry.trace if step.id == "step-pantry-goal")
    assert goal.result_summary.startswith("мета")
    assert done.goal is not None
    assert done.goal.broken == ()


@pytest.mark.anyio
async def test_the_second_answer_keeps_the_first_trace_and_adds_its_own(tmp_path):
    llm = _Model(_plan("pantry.name"))
    stand, read, drawn, said = await _ready(tmp_path, llm)

    done = await refine(
        stand, settings=ONE_PLAN, drawn=drawn, read=read, said=said, llm=llm, now=NOW, place=HERE
    )

    steps = _steps(done.pantry)
    assert "step-pantry-read" in steps
    assert steps.index("step-pantry-read") < steps.index("step-pantry-plan")
    assert steps[-1] == "step-pantry-goal"


@pytest.mark.anyio
async def test_the_first_drawing_still_asks_and_only_the_redraw_stays_silent(tmp_path):
    llm = _Model()
    forget_loop()
    stand = _stand(tmp_path)
    read = await read_receipts(stand, place=HERE, now=NOW)

    await pantry_live(stand, llm=llm, place=HERE, now=NOW, receipts=read, said=Said())
    asked = llm.calls
    await pantry_live(stand, llm=llm, place=HERE, now=NOW, receipts=read, said=Said(), ask=False)

    assert asked > 0, "перша відмальовка мусить питати модель"
    assert llm.calls == asked, "перемальовування питати вже не має чого"


@pytest.mark.anyio
async def test_the_planner_is_told_what_the_pantry_actually_looks_like(tmp_path):
    llm = _Model({"steps": []})
    stand, read, drawn, said = await _ready(tmp_path, llm)

    await refine(stand, drawn=drawn, read=read, said=said, llm=llm, now=NOW, place=HERE)

    task = next(
        payload
        for payload in (json.loads(text) for text in llm.asked)
        if isinstance(payload, dict) and "задача" in payload
    )
    assert task["стан"]["рядків"] == len(drawn.items)
    assert task["стан"]["чеків прочитано"] == read.count
    assert task["стан"]["без мітки виду"] == len(drawn.items)


@pytest.mark.anyio
async def test_the_loop_says_each_step_while_it_runs_not_after(tmp_path):
    llm = _Model(_plan("pantry.name"))
    stand, read, drawn, said = await _ready(tmp_path, llm)
    live: list[str] = []

    done = await refine(
        stand,
        settings=ONE_PLAN,
        drawn=drawn,
        read=read,
        said=said,
        llm=llm,
        now=NOW,
        place=HERE,
        on_step=lambda step: live.append(step.id),
    )

    assert live, "жоден крок не доїхав до читача -- петля знову мовчить до кінця"
    assert live == _steps(done.pantry)[-len(live) :]
    assert "step-pantry-plan" in live


@pytest.mark.anyio
async def test_a_cold_run_asks_again_and_does_not_answer_from_the_mark(tmp_path):
    llm = _Model(_plan("pantry.name"))
    stand, read, drawn, said = await _ready(tmp_path, llm)

    first = await refine(
        stand,
        settings=ONE_PLAN,
        drawn=drawn,
        read=read,
        said=said,
        llm=llm,
        now=NOW,
        place=HERE,
        account="гість",
    )
    spent = llm.calls
    again = await refine(
        stand,
        drawn=first.pantry,
        read=read,
        said=said,
        llm=llm,
        now=NOW,
        place=HERE,
        account="гість",
        cold=True,
    )

    assert again.note != NOTHING_NEW
    assert again.ran is True
    assert llm.calls > spent


def _two_kinds(tmp_path) -> SilpoMCP:
    orders = [
        {
            "createdAt": f"2026-08-{day:02d}T10:00:00",
            "sumReg": 53.49,
            "products": [
                {"lagerId": "101", "name": "Молоко", "quantity": 1, "unit": "шт"},
                {"lagerId": "202", "name": "Хліб", "quantity": 1, "unit": "шт"},
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
    return SilpoMCP(settings=Settings.model_construct(), fixtures_dir=tmp_path)


async def _packs_asked(tmp_path, monkeypatch, *, batches: int | None) -> int:
    seen: list[int] = []

    async def spy(*_a: Any, batches: int = 1, **_kw: Any) -> dict[str, Any]:
        seen.append(batches)
        return {}

    monkeypatch.setattr("komora.agent.steps.pantry.intent_sense", spy)
    forget_loop()
    stand = _two_kinds(tmp_path)
    said = Said()
    read = await read_receipts(stand, place=HERE, now=NOW)
    llm = _Model(_plan("pantry.name", "pantry.rhythm"))
    drawn = await pantry_live(
        stand, llm=None, place=HERE, now=NOW, receipts=read, said=said, ask=False
    )
    done = await refine(
        stand,
        settings=ONE_PLAN,
        drawn=drawn,
        read=read,
        said=said,
        llm=llm,
        now=NOW,
        place=HERE,
        cold=True,
        batches=batches,
    )
    assert "step-pantry-rhythm" in _steps(done.pantry)
    assert len(seen) == 1
    return seen[0]


@pytest.mark.anyio
async def test_shvydkyi_rezhym_dokhodyt_do_samoho_vyklyku_a_ne_lyshaietsia_u_zapyti(
    tmp_path, monkeypatch
):
    assert await _packs_asked(tmp_path, monkeypatch, batches=1) == 1
    assert await _packs_asked(tmp_path, monkeypatch, batches=2) == 2


@pytest.mark.anyio
async def test_bez_slova_hostia_pachky_lyshaiutsia_za_env(tmp_path, monkeypatch):
    assert Settings.model_construct().pantry_batches == 2
    assert await _packs_asked(tmp_path, monkeypatch, batches=None) == 2


@pytest.mark.anyio
async def test_nazyvannia_teper_tezh_rizhetsia_na_pachky(tmp_path):
    forget_loop()
    stand = _two_kinds(tmp_path)
    said = Said()
    read = await read_receipts(stand, place=HERE, now=NOW)
    llm = _Model(_plan("pantry.name"))
    drawn = await pantry_live(
        stand, llm=None, place=HERE, now=NOW, receipts=read, said=said, ask=False
    )
    done = await refine(
        stand,
        settings=ONE_PLAN,
        drawn=drawn,
        read=read,
        said=said,
        llm=llm,
        now=NOW,
        place=HERE,
        cold=True,
        batches=2,
    )
    assert "step-pantry-name" in _steps(done.pantry)
    assert llm.calls - llm.planned == 2


async def test_the_stitched_trace_numbers_run_through_and_never_repeat(tmp_path):
    llm = _Model(_plan("pantry.name"))
    stand, read, drawn, said = await _ready(tmp_path, llm)

    first = await refine(
        stand,
        settings=ONE_PLAN,
        drawn=drawn,
        read=read,
        said=said,
        llm=llm,
        now=NOW,
        place=HERE,
        account="гість",
    )
    again = await refine(
        stand,
        drawn=first.pantry,
        read=read,
        said=said,
        llm=llm,
        now=NOW,
        place=HERE,
        account="гість",
    )

    for answer in (first, again):
        seqs = [step.seq for step in answer.pantry.trace]
        assert len(seqs) == len(set(seqs)), f"номери кроків повторюються: {seqs}"
        assert seqs == list(range(1, len(seqs) + 1)), f"нумерація не наскрізна: {seqs}"


def test_the_trace_can_continue_the_numbering_of_an_earlier_request():
    from komora.agent.basket import stitch
    from komora.api.schemas import TraceStep

    def _one(name: str) -> TraceStep:
        return TraceStep(id=name, seq=1, tool="code", args={}, result_summary=name)

    first = stitch([_one("a"), _one("b")])
    second = stitch([_one("c")], start=len(first) + 1)

    assert [step.seq for step in first] == [1, 2]
    assert [step.seq for step in second] == [3]
    assert len({step.seq for step in [*first, *second]}) == 3
