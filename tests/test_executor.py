from __future__ import annotations

from typing import Any

import pytest

from komora.agent.executor import BEYOND, Executor, Made
from komora.core.facts import Facts
from komora.core.plan import MAX_WRITES, Plan, Refusal, Step, validate


class _Trace:

    def __init__(self) -> None:
        self.steps: list[dict[str, Any]] = []

    def add(
        self,
        step_id: str,
        tool: str,
        args: dict[str, Any],
        summary: str,
        *,
        duration_ms: int | None = None,
        calls: int | None = None,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
        decision: str | None = None,
        tag: str | None = None,
        tag_tone: str = "muted",
        prompt: str | None = None,
    ) -> None:
        self.steps.append(
            {
                "id": step_id,
                "tool": tool,
                "calls": calls,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "args": args,
                "summary": summary,
                "duration_ms": duration_ms,
                "tag": tag,
                "tag_tone": tag_tone,
            }
        )


def _ready() -> dict[str, Any]:
    return {"slot": {"start": "s"}, "intents": ["хліб"], "candidates": {"хліб": []}}


def _plan(*names: str) -> Plan:
    return Plan(steps=tuple(Step(name=name) for name in names))


def _gives(**facts: Any):
    async def work(bound):
        return Made(facts=facts, summary="зроблено")

    return work


def _runner(*names: str, known: dict[str, Any] | None = None, writes: bool = False):
    trace = _Trace()
    facts = Facts(known or {})
    return Executor(facts, plan=_plan(*names), trace=trace, writes_allowed=writes), trace, facts


@pytest.mark.anyio
async def test_a_step_the_plan_did_not_ask_for_leaves_no_trace_at_all():
    runner, trace, _ = _runner("decide.pick")

    assert await runner.run("shelf.similar", _gives(candidates={}), step_id="s", tool="t") is None
    assert trace.steps == [] and runner.done == [] and runner.refused == []


@pytest.mark.anyio
async def test_a_step_without_its_input_refuses_by_name_and_the_run_lives_on():
    runner, trace, facts = _runner("shelf.by_article", known={"slot": {"start": "s"}})

    made = await runner.run(
        "shelf.by_article", _gives(candidates={}), step_id="step-article", tool="silpo"
    )

    assert made is None
    assert [(r.name, r.kind) for r in runner.refused] == [("shelf.by_article", Refusal.RULE)]
    assert runner.done == []
    step = trace.steps[0]
    assert step["id"] == "step-article" and step["tag"] == "не виконано"
    assert "немає входу: branch, history" in step["summary"]
    assert "candidates" not in facts


@pytest.mark.anyio
async def test_a_step_that_did_not_give_what_it_promised_is_a_named_refusal():
    runner, trace, facts = _runner("decide.pick", known=_ready())

    async def silent(bound):
        return Made(facts={}, summary="нічого не обрав")

    assert await runner.run("decide.pick", silent, step_id="step-agent", tool="агент") is None
    assert "не дав обіцяного: picks" in trace.steps[0]["summary"]
    assert "lines" not in facts
    assert [r.kind for r in runner.refused] == [Refusal.BROKE]


@pytest.mark.anyio
async def test_a_fact_beyond_the_promise_is_refused_too():
    runner, trace, _ = _runner("decide.pick", known=_ready())

    async def greedy(bound):
        return Made(facts={"lines": ["рядок"], "chains": {"а": ()}}, summary="")

    assert await runner.run("decide.pick", greedy, step_id="step-agent", tool="агент") is None
    assert "дав факт поза обіцянкою: chains" in trace.steps[0]["summary"]
    assert [r.kind for r in runner.refused] == [Refusal.BROKE]


@pytest.mark.anyio
async def test_a_step_that_threw_does_not_take_the_run_with_it():
    runner, trace, _ = _runner(
        "shelf.similar", known={"slot": {"start": "s"}, "candidates": {"а": []}}
    )

    async def broken(bound):
        raise RuntimeError("мережа впала")

    assert await runner.run("shelf.similar", broken, step_id="step-sim", tool="silpo") is None
    assert "збій кроку (мережа впала)" in trace.steps[0]["summary"]
    assert [(r.name, r.kind) for r in runner.refused] == [("shelf.similar", Refusal.BROKE)]


@pytest.mark.anyio
async def test_the_step_is_bound_from_the_bag_and_says_what_it_gave():
    runner, trace, facts = _runner(
        "shelf.by_article",
        known={"branch": "id:1", "slot": {"start": "s"}, "history": ["чек"]},
    )
    seen: dict[str, Any] = {}

    async def work(bound):
        seen.update(bound)
        return Made(facts={"candidates": {"а": [1], "б": [2]}}, args={"своє": 1}, summary="ок")

    await runner.run("shelf.by_article", work, step_id="step-article", tool="silpo")

    assert seen == {"branch": "id:1", "slot": {"start": "s"}, "history": ["чек"]}
    assert facts.get("candidates") == {"а": [1], "б": [2]}
    step = trace.steps[0]
    assert step["args"]["своє"] == 1
    assert step["args"]["крок"] == "shelf.by_article"
    assert step["args"]["входи"] == ["branch", "history", "slot"]
    assert step["args"]["дав"] == {"candidates": "2 (shelf.by_article)"}
    assert step["duration_ms"] is not None
    assert runner.done == ["shelf.by_article"]


@pytest.mark.anyio
async def test_the_write_ceiling_is_counted_over_the_whole_run_not_over_a_batch():
    names = ["decide.pick", "decide.chain", "economy.settle"] + ["cart.write"] * (MAX_WRITES + 1)
    trace = _Trace()
    facts = Facts({**_ready(), "cart": {"id": "c"}})
    runner = Executor(facts, plan=_plan(*names), trace=trace, writes_allowed=True)

    await runner.run("decide.pick", _gives(picks=[{"i": "хліб"}]), step_id="s1", tool="агент")
    await runner.run("decide.chain", _gives(lines=["рядок"], chains={}), step_id="s1b", tool="код")
    await runner.run("economy.settle", _gives(economics={"сума": 1}), step_id="s2", tool="код")
    for batch in (1, 2):
        for _ in range(3 if batch == 1 else 4):
            await runner.run("cart.write", _gives(written=["а"]), step_id="s3", tool="silpo")

    assert runner.done.count("cart.write") == MAX_WRITES
    refused = [s for s in trace.steps if s["tag"] == "не виконано"]
    assert len(refused) == 1
    assert f"понад стелю {MAX_WRITES} записів" in refused[0]["summary"]


@pytest.mark.anyio
async def test_a_write_without_a_reread_is_finished_by_the_executor_itself():
    trace = _Trace()
    facts = Facts({**_ready(), "cart": {"id": "c"}})
    runner = Executor(
        facts,
        plan=_plan("decide.pick", "decide.chain", "economy.settle", "cart.write"),
        trace=trace,
        writes_allowed=True,
    )
    await runner.run("decide.pick", _gives(picks=[{"i": "хліб"}]), step_id="s1", tool="агент")
    await runner.run("decide.chain", _gives(lines=["рядок"], chains={}), step_id="s1b", tool="код")
    await runner.run("economy.settle", _gives(economics={"сума": 1}), step_id="s2", tool="код")
    await runner.run("cart.write", _gives(written=["а"]), step_id="s3", tool="silpo")
    assert runner.carried.pending_reread

    made = await runner.settle(
        _gives(cart={"id": "c"}, validations=[]), step_id="step-reread", tool="silpo"
    )

    assert made is not None and not runner.carried.pending_reread
    assert trace.steps[-1]["summary"].startswith(BEYOND)
    assert await runner.settle(_gives(cart={}), step_id="step-reread", tool="silpo") is None


@pytest.mark.anyio
async def test_the_executor_asks_the_same_validator_the_plan_asks():
    trace = _Trace()
    facts = Facts(_ready())
    runner = Executor(facts, plan=_plan("decide.pick"), trace=trace, writes_allowed=False)
    await runner.run("decide.pick", _gives(picks=[{"i": "хліб"}]), step_id="s", tool="агент")

    later = validate(
        ["decide.clarify"],
        writes_allowed=False,
        known=facts.names(),
        carried=runner.carried,
        whole=False,
    )

    assert later.steps and later.carried.steps == 2
    assert "decide.pick" in later.carried.seen


@pytest.mark.anyio
async def test_the_stage_can_move_a_step_in_and_out_of_the_plan():
    runner, _trace, _ = _runner("decide.pick", known={**_ready(), "picks": []})

    runner.move("add", "decide.loop")
    assert runner.wants("decide.loop")
    runner.move("skip", "decide.loop")
    assert not runner.wants("decide.loop")
    assert await runner.run("decide.loop", _gives(lines=[]), step_id="s", tool="агент") is None


@pytest.mark.anyio
async def test_one_walk_that_closes_several_steps_writes_one_trace_and_names_all():
    runner, trace, facts = _runner(
        "history.receipts", "history.orders", "history.model", known={"branch": "б", "slot": {}}
    )

    async def work(bound):
        assert "receipts" not in bound, "вхід, який похід дає собі сам, ззовні не питається"
        return Made(
            facts={"receipts": [1, 2, 3], "orders": ["з"], "history": ["товар"]},
            summary="3 чеків",
        )

    made = await runner.run_all(
        ["history.receipts", "history.orders", "history.model"],
        work,
        step_id="step-history",
        tool="silpo_get_my_offline_orders",
    )

    assert made is not None
    assert len(trace.steps) == 1
    assert runner.done == ["history.receipts", "history.orders", "history.model"]
    assert facts.origin("orders").step == "history.orders"
    assert facts.origin("history").step == "history.model"


@pytest.mark.anyio
async def test_half_a_walk_does_not_happen():
    runner, trace, _ = _runner("history.receipts", known={"branch": "б", "slot": {}})

    made = await runner.run_all(
        ["history.receipts", "history.orders"],
        _gives(receipts=[1], orders=[]),
        step_id="step-history",
        tool="silpo_get_my_offline_orders",
    )

    assert made is None and trace.steps == [] and runner.done == []


@pytest.mark.anyio
async def test_a_plan_that_arrives_later_is_adopted_and_does_not_erase_what_ran():
    runner, _, _ = _runner("place.decide")

    assert runner.wants("place.decide") and not runner.wants("shelf.search")
    runner.adopt(_plan("shelf.search", "decide.pick"))

    assert runner.wants("shelf.search") and runner.wants("place.decide")


@pytest.mark.anyio
async def test_a_step_that_gave_nothing_refuses_in_its_own_words_and_its_own_tone():
    runner, trace, facts = _runner("place.cart")

    async def work(bound):
        return Made(absent="кошик не прочитався — слот беремо перший вільний", tag_tone="muted")

    made = await runner.run(
        "place.cart", work, step_id="step-cart", tool="silpo_get_my_shopping_cart"
    )

    assert made is None and "cart" not in facts
    assert [(r.name, r.kind) for r in runner.refused] == [("place.cart", Refusal.EMPTY)]
    step = trace.steps[0]
    assert step["summary"] == "кошик не прочитався — слот беремо перший вільний"
    assert step["tag"] == "не виконано" and step["tag_tone"] == "muted"
    assert step["args"]["причина"].startswith("кошик не прочитався")


@pytest.mark.anyio
async def test_the_end_of_the_run_is_not_a_broken_step():

    class _Over(RuntimeError): ...

    trace = _Trace()
    runner = Executor(
        Facts(_ready()),
        plan=_plan("decide.pick"),
        trace=trace,
        writes_allowed=False,
        fatal=(_Over,),
    )

    async def work(bound):
        raise _Over("слотів немає")

    with pytest.raises(_Over):
        await runner.run("decide.pick", work, step_id="step-agent", tool="агент")
    assert runner.refused == [], "кінець прогону -- не відмова кроку"
