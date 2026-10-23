from __future__ import annotations

import pytest

from komora.agent.spine import Batch, Ground, spin
from komora.core.facts import Facts
from komora.core.plan import Carried, Dropped, Plan, Step
from komora.core.spine import BATCH_MAX, STUCK_TURNS, Halt


def plan_of(*names: str, dropped: tuple[Dropped, ...] = (), fatal: str | None = None) -> Plan:
    return Plan(steps=tuple(Step(name) for name in names), dropped=dropped, fatal=fatal)


class Script:

    def __init__(self, *batches: Batch) -> None:
        self.batches = list(batches)
        self.seen: list[Ground] = []

    async def __call__(self, ground: Ground) -> Batch:
        self.seen.append(ground)
        if self.batches:
            return self.batches.pop(0)
        return Batch(plan_of(), stop=True, why="більше нічого")


def owed(facts: Facts, need: str):
    return lambda: () if need in facts else ("винні",)


class Hands:

    def __init__(self, facts: Facts, gives: dict[str, str] | None = None) -> None:
        self.facts = facts
        self.gives = gives or {}
        self.runs: list[tuple[str, ...]] = []

    async def __call__(self, plan: Plan) -> Carried:
        names = plan.names()
        self.runs.append(names)
        for name in names:
            if name in self.gives:
                self.facts.put(self.gives[name], [1, 2, 3], step=name)
        return Carried(steps=len(names), seen=frozenset(names))


def owing(*what: str):
    left = list(what)

    def duties() -> tuple[str, ...]:
        return tuple(left)

    def pay() -> None:
        left.clear()

    duties.pay = pay  # type: ignore[attr-defined]
    return duties


def clean(_: Carried) -> None:
    return None


async def test_a_ceiling_of_zero_never_asks_the_model_at_all() -> None:
    script = Script(Batch(plan_of("slot.list")))
    facts = Facts()
    hands = Hands(facts)
    spun = await spin(
        plan=script, run=hands, facts=facts, duties=lambda: ("винні",), verdict=clean, ceiling=0
    )
    assert spun.reason is Halt.CEILING
    assert spun.calls == 0
    assert script.seen == []
    assert hands.runs == []


async def test_the_loop_turns_until_the_goal_is_paid_and_the_model_says_enough() -> None:
    facts = Facts()
    hands = Hands(facts, gives={"slot.list": "slots", "shelf.search": "candidates"})
    duties = owing("кошик порожній")

    async def script(ground: Ground) -> Batch:
        if ground.turn == 1:
            return Batch(plan_of("slot.list"), tokens=10)
        duties.pay()  # type: ignore[attr-defined]
        return Batch(plan_of("shelf.search"), stop=True, why="усе зроблено", tokens=7)

    spun = await spin(plan=script, run=hands, facts=facts, duties=duties, verdict=clean)
    assert spun.reason is Halt.DONE
    assert spun.calls == 2
    assert spun.tokens == 17
    assert hands.runs == [("slot.list",), ("shelf.search",)]


async def test_stop_before_the_goal_does_not_end_the_run() -> None:
    facts = Facts()
    hands = Hands(facts, gives={"slot.list": "slots", "shelf.search": "candidates"})
    duties = owing("намір «хліб» загублено")

    async def script(ground: Ground) -> Batch:
        if ground.turn == 1:
            return Batch(plan_of("slot.list"), stop=True, why="мені здається, досить")
        assert ground.unmet == ("намір «хліб» загублено",), "борг мусить доїхати до моделі"
        duties.pay()  # type: ignore[attr-defined]
        return Batch(plan_of("shelf.search"), stop=True, why="тепер справді")

    spun = await spin(plan=script, run=hands, facts=facts, duties=duties, verdict=clean)
    assert spun.reason is Halt.DONE
    assert spun.calls == 2


async def test_an_unclosed_write_keeps_the_loop_turning_too() -> None:
    facts = Facts()
    hands = Hands(facts, gives={"slot.list": "slots", "shelf.search": "candidates"})
    seen: list[str] = []

    def verdict(_: Carried) -> str | None:
        seen.append("питали")
        return "запис без перечитування" if len(seen) < 3 else None

    async def script(ground: Ground) -> Batch:
        return Batch(plan_of("slot.list" if ground.turn == 1 else "shelf.search"), stop=True)

    spun = await spin(plan=script, run=hands, facts=facts, duties=lambda: (), verdict=verdict)
    assert spun.reason is Halt.DONE
    assert spun.calls == 2


async def test_a_batch_over_the_cap_runs_its_head_and_names_the_tail_next_turn() -> None:
    long = ("place.address", "place.delivery_types", "place.cart", "place.decide", "slot.list")
    assert len(long) > BATCH_MAX
    facts = Facts()
    hands = Hands(facts, gives={"place.address": "address", "slot.list": "slots"})
    script = Script(Batch(plan_of(*long)), Batch(plan_of("slot.list"), stop=True))

    spun = await spin(
        plan=script, run=hands, facts=facts, duties=owed(facts, "slots"), verdict=clean
    )

    assert hands.runs[0] == long[:BATCH_MAX], "виконується лише голова пачки"
    assert spun.turns[0].cut == long[BATCH_MAX:]
    assert script.seen[1].cut == long[BATCH_MAX:], "хвіст доїхав до наступного переплану"


async def test_what_the_validator_dropped_reaches_the_next_turn_with_its_reason() -> None:
    facts = Facts()
    hands = Hands(facts, gives={"slot.list": "slots"})
    cut = (Dropped(name="cart.write", reason="запис без дозволу", position=1),)
    script = Script(
        Batch(plan_of("slot.list", dropped=cut)),
        Batch(plan_of("cart.write"), stop=True),
    )
    hands.gives["cart.write"] = "cart"

    await spin(plan=script, run=hands, facts=facts, duties=owed(facts, "cart"), verdict=clean)

    assert script.seen[1].dropped == ("cart.write: запис без дозволу",)
    assert "запис без дозволу" in script.seen[1].told()["зрізано валідатором"][0]


async def test_what_the_executor_refused_reaches_the_next_turn_with_its_reason() -> None:
    facts = Facts()
    hands = Hands(facts, gives={"slot.list": "slots", "cart.write": "cart"})
    script = Script(
        Batch(plan_of("slot.list")),
        Batch(plan_of("cart.write"), stop=True),
    )
    refusals: list[str] = []

    async def run(plan):
        refusals.append("shelf.by_article: артикул не з цього прогону")
        return await hands(plan)

    await spin(
        plan=script,
        run=run,
        facts=facts,
        duties=owed(facts, "cart"),
        verdict=clean,
        refused=lambda: tuple(refusals),
    )

    assert script.seen[0].refused == ()
    assert script.seen[1].told()["відкинуто виконавцем"] == [
        "shelf.by_article: артикул не з цього прогону"
    ]


async def test_two_turns_without_a_single_new_fact_stop_the_loop() -> None:
    facts = Facts()
    hands = Hands(facts)
    script = Script(*[Batch(plan_of("slot.list")) for _ in range(9)])

    spun = await spin(plan=script, run=hands, facts=facts, duties=lambda: ("винні",), verdict=clean)

    assert spun.reason is Halt.STUCK
    assert spun.calls == STUCK_TURNS


async def test_a_turn_that_relays_a_subset_of_a_fact_is_not_progress() -> None:
    facts = Facts()
    picked = {"молоко": {"chosen_id": "1"}, "хліб": {"chosen_id": "2"}}
    turns = iter(range(99))

    async def run(plan):
        chosen = picked if next(turns) == 0 else {"молоко": picked["молоко"]}
        facts.put("picks", dict(chosen), step="decide.pick")
        return Carried(steps=len(plan.names()), seen=frozenset(plan.names()))

    script = Script(*[Batch(plan_of("decide.pick")) for _ in range(9)])

    spun = await spin(plan=script, run=run, facts=facts, duties=lambda: ("винні",), verdict=clean)

    assert spun.reason is Halt.STUCK
    assert spun.calls == STUCK_TURNS + 1, "перший оберт справді дізнався, далі -- перекладання"


async def test_a_single_empty_turn_is_not_yet_stuck() -> None:
    facts = Facts()
    hands = Hands(facts, gives={"shelf.search": "candidates", "decide.pick": "picks"})
    script = Script(
        Batch(plan_of("slot.list")),
        Batch(plan_of("shelf.search")),
        Batch(plan_of("decide.pick"), stop=True),
    )
    spun = await spin(
        plan=script, run=hands, facts=facts, duties=owed(facts, "picks"), verdict=clean
    )
    assert spun.reason is Halt.DONE
    assert spun.calls == 3


async def test_a_broken_batch_stops_the_loop_and_runs_nothing() -> None:
    facts = Facts()
    hands = Hands(facts)
    script = Script(Batch(plan_of("slot.list", fatal="план не список кроків")))

    spun = await spin(plan=script, run=hands, facts=facts, duties=lambda: ("винні",), verdict=clean)

    assert spun.reason is Halt.BROKEN
    assert hands.runs == [], "зламану пачку не виконують"
    assert spun.calls == 1, "оберт лишається в трейсі: мовчазний відкат гірший"


async def test_the_ground_carries_sizes_and_never_bodies() -> None:
    facts = Facts()
    facts.put("candidates", {"хліб": [1, 2, 3], "молоко": [4]}, step="shelf.search")
    hands = Hands(facts)
    script = Script(Batch(plan_of(), stop=True))

    await spin(plan=script, run=hands, facts=facts, duties=owed(facts, "picks"), verdict=clean)

    told = script.seen[0].told()
    assert told["здобуто"] == {"candidates": "2 (shelf.search)"}
    assert "хліб" not in repr(told), "назви товарів у переплан не їдуть"


async def test_the_ground_says_how_many_turns_are_left() -> None:
    facts = Facts()
    hands = Hands(facts, gives={"slot.list": "slots"})
    script = Script(Batch(plan_of("slot.list")), Batch(plan_of(), stop=True))

    await spin(
        plan=script, run=hands, facts=facts, duties=owed(facts, "picks"), verdict=clean, ceiling=4
    )

    assert script.seen[0].left == 4
    assert script.seen[1].left == 3


@pytest.mark.parametrize(
    "field, value",
    [
        ("unmet", ("винні",)),
        ("cut", ("а",)),
        ("dropped", ("б: чому",)),
        ("refused", ("г: чому",)),
        ("done", ("в",)),
    ],
)
def test_an_empty_field_does_not_travel_into_the_prompt(field: str, value: tuple[str, ...]) -> None:
    assert field not in Ground(turn=1).told()
    filled = Ground(turn=1, **{field: value})  # type: ignore[arg-type]
    assert any(value[0] in str(said) for said in filled.told().values())


def test_the_turn_number_and_the_left_counter_are_always_told() -> None:
    told = Ground(turn=3, left=2).told()
    assert told["оберт"] == 3
    assert told["обертів лишилось"] == 2


async def test_a_run_with_nothing_owed_never_asks_the_model_at_all() -> None:
    facts = Facts()
    hands = Hands(facts)
    script = Script(Batch(plan_of("slot.list")))

    spun = await spin(plan=script, run=hands, facts=facts, duties=lambda: (), verdict=clean)

    assert spun.reason is Halt.DONE
    assert spun.turns == ()
    assert spun.calls == 0, "модель спитали про роботу, якої немає"
    assert hands.runs == []


@pytest.mark.anyio
async def test_a_turn_is_announced_before_the_next_one_starts():
    facts = Facts()
    hands = Hands(facts, gives={"slot.list": "slots", "shelf.search": "candidates"})
    order: list[str] = []

    async def run(plan: Plan) -> Carried:
        order.append("робота:" + ",".join(step.name for step in plan.steps))
        return await hands(plan)

    await spin(
        plan=Script(
            Batch(plan_of("slot.list")),
            Batch(plan_of("shelf.search")),
        ),
        run=run,
        facts=facts,
        duties=lambda: () if "candidates" in facts.names() else ("винні",),
        verdict=lambda _carried: None,
        on_turn=lambda turn: order.append(f"оберт:{turn.number}"),
    )

    assert order == [
        "робота:slot.list",
        "оберт:1",
        "робота:shelf.search",
        "оберт:2",
    ], f"оберт названий не тоді, коли скінчився: {order}"
