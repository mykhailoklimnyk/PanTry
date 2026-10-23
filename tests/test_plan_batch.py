from __future__ import annotations

import json

import pytest

from komora.agent.llm import Decision, ModelError, Usage
from komora.agent.plan import BATCH_HEAD, BATCH_TOKENS, plan_batch
from komora.agent.spine import Ground
from komora.core.plan import BATCH_SCHEMA

GOOD = ["intents.compose", "shelf.search"]


class _Planner:

    model = "fake-batcher"

    def __init__(self, *answers: object) -> None:
        self.answers = list(answers)
        self.systems: list[str] = []
        self.users: list[str] = []
        self.limits: list[int] = []

    async def decide(self, *, system, user, schema, schema_name="decision", max_tokens=2048, **_):
        self.systems.append(system)
        self.users.append(user)
        self.limits.append(max_tokens)
        answer = self.answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return Decision(
            data=answer,
            text=json.dumps(answer),
            model=self.model,
            usage=Usage(80, 40),
            duration_ms=1,
        )


def _batch(names: list[str], **extra: object) -> dict:
    return {"steps": [{"step": name, "why": "треба"} for name in names], **extra}


def _ground(**over: object) -> Ground:
    base: dict = {
        "turn": 2,
        "facts": {
            "branch": "id:1",
            "slot": "18-20",
            "history": "40 рядків",
            "intents": "12",
            "candidates": "31, своїх 4",
        },
        "unmet": ("намір «хліб» без адреси",),
        "left": 4,
    }
    base.update(over)
    return Ground(**base)  # type: ignore[arg-type]


@pytest.mark.anyio
async def test_a_batch_from_the_model_is_taken_as_is():
    llm = _Planner(_batch(GOOD))
    batch = await plan_batch(llm, _ground(), source="list", writes=False, budget=False)

    assert batch.plan.names() == tuple(GOOD)
    assert batch.plan.source == "model"
    assert batch.tokens == 120
    assert batch.stop is False


@pytest.mark.anyio
async def test_the_model_sees_the_ground_and_not_just_the_task():
    llm = _Planner(_batch(GOOD))
    await plan_batch(llm, _ground(), source="list", writes=False, budget=False)

    said = json.loads(llm.users[0])
    assert "ґрунт" in said
    ground = said["ґрунт"]
    assert ground["оберт"] == 2
    assert ground["обертів лишилось"] == 4
    assert ground["здобуто"]["candidates"] == "31, своїх 4"
    assert ground["ще винні"] == ["намір «хліб» без адреси"]


@pytest.mark.anyio
async def test_the_ground_carries_sizes_and_never_bodies():
    llm = _Planner(_batch(GOOD))
    await plan_batch(llm, _ground(), source="list", writes=False, budget=False)

    said = json.loads(llm.users[0])
    assert all(isinstance(value, str) for value in said["ґрунт"]["здобуто"].values())


@pytest.mark.anyio
async def test_an_empty_ground_field_does_not_travel():
    llm = _Planner(_batch(GOOD))
    await plan_batch(llm, _ground(unmet=(), facts={}), source="list", writes=False, budget=False)

    ground = json.loads(llm.users[0])["ґрунт"]
    assert "ще винні" not in ground
    assert "здобуто" not in ground
    assert "не влізло в пачку" not in ground
    assert "зрізано валідатором" not in ground


@pytest.mark.anyio
async def test_the_cut_from_the_previous_turn_comes_back_with_its_reason():
    llm = _Planner(_batch(GOOD))
    await plan_batch(
        llm,
        _ground(cut=("economy.settle",), dropped=("cart.write: запис без перечитування",)),
        source="list",
        writes=False,
        budget=False,
    )

    ground = json.loads(llm.users[0])["ґрунт"]
    assert ground["не влізло в пачку"] == ["economy.settle"]
    assert ground["зрізано валідатором"] == ["cart.write: запис без перечитування"]


@pytest.mark.anyio
async def test_stop_is_carried_with_its_reason():
    llm = _Planner(_batch([], stop=True, why="кошик зібрано, більше нема чого"))
    batch = await plan_batch(llm, _ground(), source="list", writes=False, budget=False)

    assert batch.stop is True
    assert batch.why == "кошик зібрано, більше нема чого"
    assert batch.plan.ok


@pytest.mark.anyio
async def test_a_missing_stop_means_keep_going():
    llm = _Planner(_batch(GOOD))
    batch = await plan_batch(llm, _ground(), source="list", writes=False, budget=False)

    assert batch.stop is False
    assert batch.why == ""


@pytest.mark.anyio
async def test_an_empty_batch_is_an_answer_and_a_refusal_is_not():
    empty = await plan_batch(
        _Planner(_batch([], stop=True, why="усе зроблено")),
        _ground(),
        source="list",
        writes=False,
        budget=False,
    )
    assert empty.plan.ok and empty.plan.steps == ()

    broken = await plan_batch(
        _Planner(ModelError("таймаут")),
        _ground(),
        source="list",
        writes=False,
        budget=False,
    )
    assert not broken.plan.ok
    assert broken.stop is False
    assert "модель не відповіла" in (broken.plan.fatal or "")


@pytest.mark.anyio
async def test_without_a_model_there_is_no_loop_and_it_says_so():
    batch = await plan_batch(None, _ground(), source="list", writes=False, budget=False)

    assert batch.plan.steps == ()
    assert batch.plan.source == "code"
    assert batch.stop is True
    assert batch.why == "моделі немає"


@pytest.mark.anyio
async def test_the_batch_prompt_says_it_is_a_batch_and_says_it_first():
    llm = _Planner(_batch(GOOD))
    await plan_batch(llm, _ground(), source="list", writes=False, budget=False)

    assert llm.systems[0].startswith(BATCH_HEAD)
    assert "СЛОВНИК КРОКІВ" in llm.systems[0]


@pytest.mark.anyio
async def test_the_answer_ceiling_is_small_enough_to_forbid_a_whole_plan():
    llm = _Planner(_batch(GOOD))
    await plan_batch(llm, _ground(), source="list", writes=False, budget=False)

    assert llm.limits[0] == BATCH_TOKENS
    assert BATCH_TOKENS <= 1024


def test_the_batch_schema_asks_only_for_the_steps():
    assert BATCH_SCHEMA["required"] == ["steps"]
    assert set(BATCH_SCHEMA["properties"]) == {"goal", "steps", "stop", "why"}
    assert BATCH_SCHEMA["properties"]["steps"].get("salvage") is True
    assert "maxItems" not in BATCH_SCHEMA["properties"]["steps"]
