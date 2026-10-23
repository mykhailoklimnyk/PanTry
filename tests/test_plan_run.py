from __future__ import annotations

import json
from pathlib import Path

import pytest

from komora.agent.basket import BEFORE_PLAN
from komora.agent.llm import Decision, ModelError, Usage
from komora.agent.plan import (
    dictionary_text,
    plan_run,
    tools_digest,
    tools_text,
)
from komora.core.instructions import Verdict, fingerprint
from komora.core.plan import BY_NAME, STEPS, Aim, code_plan, facts_of, validate
from komora.mcp.client import SilpoMCP


def _root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "docs" / "mcp-tools.json").is_file():
            return parent
    raise AssertionError("знімка описів не знайшлось: docs/mcp-tools.json")


ROOT = _root()

GOOD = [
    "place.cart",
    "place.decide",
    "slot.list",
    "slot.pick",
    "history.receipts",
    "history.model",
    "intents.compose",
    "shelf.search",
    "shelf.by_article",
    "decide.pick",
    "decide.chain",
    "economy.settle",
]


class _Planner:

    model = "fake-planner"

    def __init__(self, *answers: object) -> None:
        self.answers = list(answers)
        self.systems: list[str] = []

    async def decide(self, *, system, user, schema, schema_name="decision", max_tokens=2048, **_):
        self.systems.append(system)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return Decision(
            data=answer,
            text=json.dumps(answer),
            model=self.model,
            usage=Usage(100, 50),
            duration_ms=1,
        )


def _steps(names: list[str]) -> dict:
    return {"steps": [{"step": name, "why": "треба"} for name in names]}


@pytest.mark.anyio
async def test_a_good_plan_from_the_model_is_taken_as_is():
    llm = _Planner(_steps(GOOD))
    planned = await plan_run(llm, source="list", writes=False, budget=False)
    assert planned.plan.source == "model"
    assert planned.plan.names() == tuple(GOOD)
    assert planned.attempts == 1 and planned.tokens == 150
    assert planned.note == "план від моделі"


@pytest.mark.anyio
async def test_a_broken_plan_gets_one_repair_with_the_reasons_in_the_prompt():
    broken = _steps([*GOOD, "cart.slot", "cart.write"])
    fixed = _steps([*GOOD, "cart.slot", "cart.write", "cart.reread"])
    llm = _Planner(broken, fixed)
    planned = await plan_run(llm, source="list", writes=True, budget=False)
    assert planned.plan.source == "model"
    assert planned.plan.names()[-1] == "cart.reread"
    assert planned.attempts == 2
    assert planned.note == "план від моделі після одного ремонту"
    assert "запис у кошик без перечитування" in llm.systems[1]
    assert "Не пройшли перевірку" in llm.systems[1]


@pytest.mark.anyio
async def test_a_plan_that_fails_twice_falls_back_to_the_code_plan_out_loud():
    llm = _Planner(_steps(["place.cart"]), _steps(["cart.nuke"]))
    planned = await plan_run(llm, source="list", writes=False, budget=True)
    assert planned.plan.source == "code"
    assert planned.plan.names() == code_plan(source="list", writes=False, budget=True).names()
    assert planned.attempts == 2
    assert planned.note.startswith("план моделі не годиться після 2 спроб")
    assert "план з коду" in planned.note


@pytest.mark.anyio
async def test_dropped_steps_do_not_cost_a_repair_when_the_plan_still_works():
    llm = _Planner(_steps([*GOOD, "cart.nuke"]))
    planned = await plan_run(llm, source="list", writes=False, budget=False)
    assert planned.attempts == 1
    assert planned.plan.source == "model"
    assert [d.name for d in planned.plan.dropped] == ["cart.nuke"]
    assert planned.note == "план від моделі, знято 1"


@pytest.mark.anyio
async def test_without_a_model_the_plan_comes_from_code_and_says_so():
    planned = await plan_run(None, source="cart", writes=True, budget=False)
    assert planned.plan.source == "code"
    assert planned.attempts == 0
    assert planned.note == "без моделі: план з коду"


@pytest.mark.anyio
async def test_a_model_error_is_a_code_plan_with_the_error_named():
    llm = _Planner(ModelError("mantle: 503"))
    planned = await plan_run(llm, source="list", writes=False, budget=False)
    assert planned.plan.source == "code"
    assert "модель не відповіла (mantle: 503)" in planned.note


@pytest.mark.anyio
async def test_the_prompt_carries_the_dictionary_the_tools_and_the_task():
    tools = [
        *json.loads((ROOT / "docs" / "mcp-tools.json").read_text(encoding="utf-8")),
        {"name": "silpo_send_flowers", "description": "not ours", "input_schema": {}},
    ]
    llm = _Planner(_steps(GOOD))
    planned = await plan_run(
        llm, source="list", writes=False, budget=True, known=("branch", "slot"), tools=tools
    )
    system = llm.systems[0]
    assert "shelf.by_article" in system and "СЛОВНИК КРОКІВ" in system
    assert "SEARCH BY ARTICLE CODE" in system
    assert "у Коморі інакше" in system
    assert "EXPRESS DELIVERY" not in system
    assert "silpo_send_flowers" not in system
    assert "БЕЗ ВИРОКУ" not in planned.tools_note and planned.tools_note.startswith("15 інстр.")


def test_the_dictionary_text_names_every_step_with_its_tool_and_writes():
    text = dictionary_text() + dictionary_text(Aim.PANTRY)
    for kind in STEPS:
        assert f"- {kind.name} " in text
    assert "cart.write" in text and "ПИШЕ в кошик" in text
    assert "shelf.search" in text and "можна повторювати" in text


def test_tools_digest_keeps_only_the_dictionary_tools_and_only_the_judged():
    tools = [
        {"name": "silpo_get_time_slots", "description": "slots\n\ntwice"},
        {"name": "silpo_get_my_family", "description": "family"},
    ]
    rows = [
        Verdict("silpo_get_time_slots", fingerprint("slots"), "code", "виконує код"),
        Verdict("silpo_get_my_family", fingerprint("family"), "code", "виконує код"),
    ]
    got = tools_digest(tools, verdicts=rows)
    assert got.rows == ("- silpo_get_time_slots: slots",)
    assert got.unjudged == 1


def test_tools_text_with_the_real_register_is_not_empty():
    tools = json.loads((ROOT / "docs" / "mcp-tools.json").read_text(encoding="utf-8"))
    text = tools_text(tools)
    assert "- silpo_find_products_batch: " in text
    assert "silpo_get_my_family" not in text


@pytest.mark.anyio
async def test_fixture_tools_come_from_a_file_beside_the_fixtures(tmp_path):
    (tmp_path / "tools.json").write_text(
        json.dumps([{"name": "silpo_get_time_slots", "description": "d", "inputSchema": {"x": 1}}]),
        encoding="utf-8",
    )
    mcp = SilpoMCP(fixtures_dir=tmp_path)
    assert await mcp.describe_tools() == [
        {"name": "silpo_get_time_slots", "description": "d", "input_schema": {"x": 1}}
    ]


@pytest.mark.anyio
async def test_without_the_file_the_fixture_stand_has_no_descriptions(tmp_path):
    assert await SilpoMCP(fixtures_dir=tmp_path).describe_tools() == []


def test_a_plan_that_starts_at_the_intents_is_not_cut_for_a_missing_history():
    plan = validate(
        ["intents.compose", "shelf.search", "decide.pick", "decide.chain", "economy.settle"],
        writes_allowed=False,
        known=facts_of(BEFORE_PLAN),
    )

    assert plan.dropped == (), "план від намірів не має чого втрачати: історія вже прочитана"
    assert plan.ok and plan.names() == (
        "intents.compose",
        "shelf.search",
        "decide.pick",
        "decide.chain",
        "economy.settle",
    )

    was = ("address", "delivery_types", "cart", "branch", "delivery_type", "slots", "slot")
    old_plan = validate(
        ["intents.compose", "shelf.search", "decide.pick", "decide.chain", "economy.settle"],
        writes_allowed=False,
        known=was,
    )
    assert old_plan.names() == () and old_plan.fatal == "жодного кроку не лишилось"
    assert old_plan.dropped[0].reason == "немає входу: history"


def test_what_the_code_does_before_the_plan_is_one_list_for_both_readers():
    assert set(BEFORE_PLAN) <= set(BY_NAME), "у переліку крок, якого немає в словнику"
    facts = set(facts_of(BEFORE_PLAN))
    assert {"history", "slot", "branch", "delivery_type"} <= facts


def test_the_basket_prompt_names_the_steps_the_code_runs_anyway():
    from komora.agent.plan import system_text
    from komora.core.plan import CORE_AFTER_PLAN, Aim

    _, text = system_text(aim=Aim.BASKET)

    for step in CORE_AFTER_PLAN[Aim.BASKET]:
        assert step in text, f"промпт не назвав крок ядра: {step}"


def test_the_pantry_prompt_stays_byte_for_byte_what_the_traps_measure():
    from komora.agent.plan import system_text
    from komora.core.plan import Aim

    _, text = system_text(aim=Aim.PANTRY)

    assert "КОД РОБИТЬ САМ" not in text


def test_the_executor_plan_reads_the_same_list_as_the_prompt():
    from pathlib import Path

    here = Path(__file__).resolve()
    root = next(p for p in here.parents if (p / "src" / "komora").is_dir())
    text = (root / "src" / "komora" / "agent" / "basket.py").read_text(encoding="utf-8")

    assert "CORE_AFTER_PLAN[Aim.BASKET]" in text, (
        "виконавець кошика набирає перелік ядра сам -- він мусить читати "
        "`core/plan.CORE_AFTER_PLAN`, той самий, який бачить модель"
    )


def test_the_pantry_dictionary_shows_only_what_its_runner_can_do():
    from komora.agent.plan import system_text
    from komora.core.plan import PHASES, STEPS, Aim

    _, text = system_text(aim=Aim.PANTRY)
    allowed = PHASES[Aim.PANTRY]

    for kind in STEPS:
        if kind.phase in allowed:
            assert kind.name in text, f"комора не бачить свого кроку: {kind.name}"
        else:
            assert kind.name not in text, (
                f"коморі показано крок, якого її виконавець не вміє: {kind.name}"
            )


def test_the_basket_dictionary_hides_the_pantry_phase_and_nothing_else():
    from komora.agent.plan import system_text
    from komora.core.plan import STEPS, Aim, Phase

    _, text = system_text(aim=Aim.BASKET)

    for kind in STEPS:
        if kind.phase is Phase.PANTRY:
            assert kind.name not in text, f"кошику показано крок комори: {kind.name}"
        else:
            assert kind.name in text, f"кошик утратив крок словника: {kind.name}"


def test_the_stamp_moves_when_the_dictionary_moves():
    from komora.agent.plan import dictionary_block, system_text
    from komora.agent.prompts import stamp
    from komora.core.plan import Aim

    for aim in (Aim.BASKET, Aim.PANTRY):
        name, text = system_text(aim=aim)
        told = stamp(name, text)
        assert "dict@" in told, f"{aim}: словника немає в стампі"
        assert dictionary_block(aim) in text, f"{aim}: у промпт поїхав НЕ зареєстрований словник"


def test_the_two_dictionaries_do_not_borrow_each_other_names():
    from komora.agent.plan import system_text
    from komora.agent.prompts import stamp
    from komora.core.plan import Aim

    name, text = system_text(aim=Aim.BASKET)
    basket = stamp(name, text)

    assert "plan-pantry" not in basket, "стамп кошика назвав словник комори"


@pytest.mark.anyio
async def test_a_plan_without_the_decision_gets_it_written_by_code():
    without = _steps([name for name in GOOD if name != "decide.pick"])
    llm = _Planner(without, without)
    planned = await plan_run(llm, source="list", writes=False, budget=False)
    assert planned.plan.source == "model"
    assert "decide.pick" in planned.plan.names()
    assert "дописано кодом" in planned.note
