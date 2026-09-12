from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from komora.agent.basket import assemble_list
from komora.api.schemas import BuildRequest
from test_agent_basket import mcp  # noqa: F401

MOMENT = datetime(2026, 8, 14, 14, 30, 5, 991538, tzinfo=UTC)

REQUEST = {"mode": "week", "shoppingList": ["молоко", "шафран", "кава"]}

PICK = [{"intent": "молоко", "chosen_id": "101", "qty": 1, "reason": "звичний"}]


class _Planning:

    model = "fake-model"

    def __init__(
        self, batches: list[dict[str, Any]], *, picks: list[list[dict[str, Any]]] | None = None
    ) -> None:
        self.batches = list(batches)
        self.asked: list[dict[str, Any]] = []
        self.picks = list(picks or [])
        self.pick_users: list[str] = []
        self.occasion: dict[str, Any] = {"add": [], "skip": []}

    async def decide(self, *, system, user, schema, schema_name="decision", max_tokens=2048, **_):
        from komora.agent.llm import Decision, Usage

        properties = schema.get("properties", {})
        if "steps" in properties and "stop" in properties:
            self.asked.append(json.loads(user))
            data = self.batches.pop(0) if self.batches else {"steps": [], "stop": True}
        elif "add" in properties and "skip" in properties:
            data = self.occasion
        elif "picks" in properties:
            self.pick_users.append(user)
            data = {"picks": self.picks.pop(0) if self.picks else PICK}
        else:
            data = {}
        return Decision(data=data, text="", model=self.model, usage=Usage(1, 1), duration_ms=1)


def _steps(basket: Any, name: str) -> list[Any]:
    return [step for step in basket.trace if step.id == name]


async def test_the_loop_runs_a_step_again_when_the_model_asks_for_it(mcp) -> None:  # noqa: F811
    llm = _Planning(
        [
            {"steps": [{"name": "decide.loop"}], "stop": False},
            {"steps": [], "stop": True, "why": "більше нема чого"},
        ]
    )

    assembled = await assemble_list(
        mcp, llm=llm, request=BuildRequest.model_validate(REQUEST), now=MOMENT
    )

    assert len(_steps(assembled.basket, "step-loop")) == 2
    spin = _steps(assembled.basket, "step-spin")
    assert len(spin) == 1
    assert spin[0].args["обертів"] == 2
    turns = _steps(assembled.basket, "step-turn")
    assert [t.result_summary.split(":")[0] for t in turns] == ["оберт 1", "оберт 2"]
    assert turns[0].args["виконано"] == ["decide.loop"]
    assert turns[1].decision == "більше нема чого"
    assert "ще винні" in turns[0].args


async def test_the_model_word_stops_the_loop_and_the_ceiling_does_not_decide(mcp) -> None:  # noqa: F811
    llm = _Planning([{"steps": [], "stop": True, "why": "усе, що можна, знайдено"}])

    assembled = await assemble_list(
        mcp, llm=llm, request=BuildRequest.model_validate(REQUEST), now=MOMENT
    )

    spin = _steps(assembled.basket, "step-spin")[0]
    assert spin.args["причина"] == "said"
    assert spin.args["обертів"] == 1


async def test_a_step_outside_the_closed_set_is_refused_aloud(mcp) -> None:  # noqa: F811
    llm = _Planning(
        [
            {"steps": [{"name": "history.receipts"}, {"name": "decide.chain"}], "stop": False},
            {"steps": [], "stop": True},
        ]
    )

    assembled = await assemble_list(
        mcp, llm=llm, request=BuildRequest.model_validate(REQUEST), now=MOMENT
    )

    spin = _steps(assembled.basket, "step-spin")[0]
    assert spin.args["поза набором"] == ["history.receipts"]
    assert len(_steps(assembled.basket, "step-lines")) == 2


async def test_a_basket_that_needs_nothing_costs_no_planner_call(mcp) -> None:  # noqa: F811
    llm = _Planning([])
    request = BuildRequest.model_validate({"mode": "week", "shoppingList": ["молоко"]})

    assembled = await assemble_list(mcp, llm=llm, request=request, now=MOMENT)

    spin = _steps(assembled.basket, "step-spin")[0]
    assert spin.args["обертів"] == 0
    assert llm.asked == []


async def test_the_replan_sees_the_basket_and_the_money(mcp) -> None:  # noqa: F811
    llm = _Planning([{"steps": [], "stop": True}])
    request = BuildRequest.model_validate({**REQUEST, "budget": 1600})

    await assemble_list(mcp, llm=llm, request=request, now=MOMENT)

    state = llm.asked[0]["стан"]
    assert state["рядків кошика"] == 2
    assert state["не знайшлось"] == ["шафран"]
    assert state["межа, грн"] == "1600"
    assert state["коридор, грн"] == "1440-1760"
    assert "зібрано, грн" in state and "до верхньої межі, грн" in state
    assert state["кроки оберту"] == "decide.chain, decide.loop, decide.pick"


async def test_an_addressed_pick_asks_only_the_named_intents(mcp) -> None:  # noqa: F811
    llm = _Planning(
        [
            {"steps": [{"name": "decide.pick", "labels": ["молоко", "єдиноріг"]}], "stop": False},
            {"steps": [], "stop": True},
        ]
    )

    assembled = await assemble_list(
        mcp, llm=llm, request=BuildRequest.model_validate(REQUEST), now=MOMENT
    )

    picked = _steps(assembled.basket, "step-agent")
    assert len(picked) == 2
    assert picked[1].args["адресно"] == 1
    assert picked[1].args["наміри"] == ["молоко"]
    assert "кава" not in llm.pick_users[1]


async def test_a_loop_pick_without_address_takes_only_intents_without_a_row(mcp) -> None:  # noqa: F811
    llm = _Planning(
        [{"steps": [{"name": "decide.pick"}], "stop": False}, {"steps": [], "stop": True}]
    )

    assembled = await assemble_list(
        mcp, llm=llm, request=BuildRequest.model_validate(REQUEST), now=MOMENT
    )

    picked = _steps(assembled.basket, "step-agent")[1]
    assert picked.args["без рядка"] == 1
    assert picked.args["наміри"] == ["шафран"]
    assert len(llm.pick_users) == 1, "шафран не має кандидатів -- виклику моделі не було"


async def test_a_pick_made_in_the_loop_reaches_the_rows(mcp) -> None:  # noqa: F811
    llm = _Planning(
        [
            {
                "steps": [{"name": "decide.pick", "labels": ["молоко"]}, {"name": "decide.chain"}],
                "stop": False,
            },
            {"steps": [], "stop": True},
        ],
        picks=[PICK, [{"intent": "молоко", "chosen_id": "102", "qty": 1, "reason": "звичний"}]],
    )

    assembled = await assemble_list(
        mcp, llm=llm, request=BuildRequest.model_validate(REQUEST), now=MOMENT
    )

    milk = next(line for line in assembled.lines if line.intent == "молоко")
    assert milk.product["externalProductId"] == 102


async def test_the_agent_raises_the_limit_for_guests(mcp) -> None:  # noqa: F811
    llm = _Planning([{"steps": [], "stop": True}])
    llm.occasion = {"add": [], "skip": [], "target": 3000, "target_why": "гості на шістьох"}
    request = BuildRequest.model_validate(
        {**REQUEST, "mode": "event", "occasionPeople": 6, "budget": 1600}
    )

    assembled = await assemble_list(mcp, llm=llm, request=request, now=MOMENT)

    agent = assembled.basket.agent_target
    assert agent is not None and agent.refused is None
    assert (agent.named, agent.target, agent.why) == (1600, 3000, "гості на шістьох")
    assert llm.asked[0]["стан"]["межа, грн"] == "3000"
    occasion = _steps(assembled.basket, "step-occasion")[0]
    assert occasion.args["агент пропонує, грн"] == "3000"


async def test_a_limit_named_by_the_guest_is_not_touched(mcp) -> None:  # noqa: F811
    llm = _Planning([{"steps": [], "stop": True}])
    llm.occasion = {"add": [], "skip": [], "target": 3000, "target_why": "гості на шістьох"}
    request = BuildRequest.model_validate(
        {**REQUEST, "mode": "event", "occasionPeople": 6, "budget": 1600, "budgetSaid": True}
    )

    assembled = await assemble_list(mcp, llm=llm, request=request, now=MOMENT)

    agent = assembled.basket.agent_target
    assert agent is not None and agent.refused and agent.target == 1600
    assert llm.asked[0]["стан"]["межа, грн"] == "1600"
    assert "відмова" in _steps(assembled.basket, "step-occasion")[0].args
