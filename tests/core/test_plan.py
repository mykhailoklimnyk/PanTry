from __future__ import annotations

import json
from pathlib import Path

import pytest

from komora.agent.plan import dictionary_text
from komora.core.plan import (
    BEFORE_PANTRY,
    BY_NAME,
    MAX_STEPS,
    MAX_WRITES,
    PLAN_SCHEMA,
    STEPS,
    Aim,
    Carried,
    Did,
    Phase,
    Refusal,
    Refused,
    Report,
    code_plan,
    describe,
    facts_of,
    repair_note,
    report,
    validate,
    verdict,
)

FULL = [
    "place.address",
    "place.delivery_types",
    "place.cart",
    "place.decide",
    "slot.list",
    "slot.pick",
    "history.receipts",
    "history.orders",
    "history.model",
    "intents.compose",
    "shelf.search",
    "decide.pick",
    "decide.chain",
    "economy.settle",
    "cart.slot",
    "cart.write",
    "cart.reread",
]

PADDED = [
    *FULL[: FULL.index("decide.pick")],
    *["shelf.search"] * (MAX_STEPS + 5),
    *FULL[FULL.index("decide.pick") :],
]


def test_every_step_names_a_real_tool_or_code_and_the_names_are_unique():
    path = Path(__file__).resolve().parents[2] / "docs" / "mcp-tools.json"
    if not path.is_file():
        pytest.skip("знімок описів лишається вдома: у копії mutants/ його немає")
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    tools = {tool["name"] for tool in snapshot}
    for kind in STEPS:
        assert kind.tool in tools or kind.tool in {"code", "model"}, kind.name
    assert len({kind.name for kind in STEPS}) == len(STEPS)
    assert set(BY_NAME) == {kind.name for kind in STEPS}


def test_write_steps_are_exactly_the_writing_tools():
    writing = {kind.tool for kind in STEPS if kind.writes}
    assert writing == {
        "silpo_create_shopping_cart",
        "silpo_update_shopping_cart",
        "silpo_add_or_update_cart_products",
        "silpo_remove_cart_products",
    }
    assert all(kind.phase is Phase.CART for kind in STEPS if kind.writes)


def test_the_schema_enumerates_the_dictionary_and_salvages_by_step():
    assert set(PLAN_SCHEMA["properties"]["steps"]["items"]["properties"]["step"]["enum"]) == set(
        BY_NAME
    )
    assert PLAN_SCHEMA["properties"]["steps"]["salvage"] is True


def test_a_full_plan_passes_untouched():
    plan = validate(FULL, writes_allowed=True)
    assert plan.ok and plan.dropped == ()
    assert plan.names() == tuple(FULL)
    assert plan.writes == 2


def test_steps_come_as_objects_with_a_reason_or_as_bare_names():
    raw = {"steps": [{"step": "place.cart", "why": "кошик уже є"}, "place.decide", "slot.list"]}
    plan = validate(raw, writes_allowed=False)
    assert [s.name for s in plan.steps] == ["place.cart", "place.decide", "slot.list"]
    assert plan.steps[0].why == "кошик уже є"


def test_known_facts_from_the_session_let_the_plan_start_later():
    plan = validate(
        [
            "slot.list",
            "slot.pick",
            "history.receipts",
            "history.model",
            "intents.compose",
            "shelf.search",
            "decide.pick",
            "decide.chain",
            "economy.settle",
        ],
        writes_allowed=False,
        known=("branch", "delivery_type"),
    )
    assert plan.ok and plan.dropped == ()


def test_an_unknown_step_is_dropped_by_name_and_the_rest_survives():
    plan = validate(["place.cart", "cart.nuke", "place.decide"], writes_allowed=False)
    assert plan.names() == ("place.cart", "place.decide")
    assert [(d.name, d.reason, d.position) for d in plan.dropped] == [
        ("cart.nuke", "кроку немає в словнику", 1)
    ]


def test_a_step_without_its_input_is_dropped_and_says_what_is_missing():
    plan = validate(["slot.list", "place.cart", "place.decide", "slot.list"], writes_allowed=False)
    assert plan.names() == ("place.cart", "place.decide", "slot.list")
    assert plan.dropped[0].reason == "немає входу: branch, delivery_type"


def test_the_shelf_is_never_asked_before_the_slot():
    plan = validate(
        ["place.cart", "place.decide", "history.orders", "intents.compose"],
        writes_allowed=False,
        known=("history",),
    )
    assert "intents.compose" in plan.names()
    shelf = validate(["shelf.search"], writes_allowed=False, known=("branch", "intents"))
    assert shelf.steps == ()
    assert shelf.dropped[0].reason == "немає входу: slot"
    early = validate(["decide.pick"], writes_allowed=False, known=("intents", "candidates"))
    assert early.dropped[0].reason == "полиця до слота"


def test_a_write_without_the_clients_permission_is_dropped_not_executed():
    plan = validate(FULL, writes_allowed=False)
    assert plan.writes == 0
    assert {d.name for d in plan.dropped} == {"cart.slot", "cart.write"}
    assert all(d.reason == "запис без дозволу клієнта" for d in plan.dropped)
    assert plan.ok


def test_a_write_before_the_decision_is_dropped():
    early = [*FULL[:10], "cart.slot", *FULL[10:]]
    plan = validate(early, writes_allowed=True)
    dropped = [d for d in plan.dropped if d.name == "cart.slot"]
    assert dropped and dropped[0].reason.startswith("запис до рішення: бракує decide.pick")
    assert plan.names().count("cart.slot") == 1


def test_a_write_without_a_reread_after_it_kills_the_whole_plan():
    plan = validate(FULL[:-1], writes_allowed=True)
    assert plan.fatal == "запис у кошик без перечитування після нього"
    assert not plan.ok


def test_a_plan_without_a_decision_is_not_a_basket_plan():
    plan = validate(FULL[:11], writes_allowed=False)
    assert plan.fatal == "у плані немає рішення (decide.pick)"


def test_a_non_repeatable_step_is_dropped_on_its_second_appearance():
    plan = validate([*FULL, "history.receipts"], writes_allowed=True)
    assert plan.dropped[-1].reason == "повтор кроку, який не повторюється"
    again = validate([*FULL, "cart.write", "cart.reread"], writes_allowed=True)
    assert again.dropped == () and again.names().count("cart.write") == 2


def test_the_ceilings_name_themselves():
    plan = validate(PADDED, writes_allowed=True)
    assert any(d.reason == f"понад стелю {MAX_STEPS} кроків" for d in plan.dropped)
    writes = [*FULL[:-1], *["cart.write"] * (MAX_WRITES + 2), "cart.reread"]
    plan = validate(writes, writes_allowed=True)
    over = 2 + (MAX_WRITES + 2) - MAX_WRITES
    assert sum(1 for d in plan.dropped if d.reason == f"понад стелю {MAX_WRITES} записів") == over
    assert plan.writes == MAX_WRITES


@pytest.mark.parametrize("raw", [{"steps": "не список"}, "рядок", {"goal": "кошик"}, [], [{}]])
def test_garbage_is_a_fatal_not_a_crash(raw):
    plan = validate(raw, writes_allowed=False)
    assert not plan.ok and plan.fatal is not None


def test_a_step_without_a_name_is_dropped_with_its_position():
    plan = validate([{"why": "просто так"}, "place.cart"], writes_allowed=False)
    assert plan.dropped[0].reason == "крок без назви" and plan.dropped[0].position == 0


@pytest.mark.parametrize("source", ["list", "cart"])
@pytest.mark.parametrize("writes", [False, True])
@pytest.mark.parametrize("budget", [False, True])
def test_the_code_plan_always_passes_its_own_validator(source, writes, budget):
    plan = code_plan(source=source, writes=writes, budget=budget)
    assert plan.ok and plan.dropped == (), describe(plan)
    assert plan.source == "code"
    assert ("cart.write" in plan.names()) is writes
    assert plan.names()[-1] == ("cart.reread" if writes else plan.names()[-1])


def test_the_cart_source_plan_reads_the_cart_first_and_skips_the_address():
    plan = code_plan(source="cart", writes=False)
    assert plan.names()[0] == "place.cart"
    assert "place.address" not in plan.names()


def test_the_repair_note_quotes_every_dropped_step_and_the_fatal():
    plan = validate(["cart.nuke", *FULL[:-1]], writes_allowed=True)
    note = repair_note(plan)
    assert "«cart.nuke» (крок 1): кроку немає в словнику" in note
    assert "план цілком: запис у кошик без перечитування" in note
    assert repair_note(validate(FULL, writes_allowed=True)) == ""


def test_describe_lists_steps_with_arrows_and_names_the_dropped():
    plan = validate(["place.cart", "x.y", "place.decide"], writes_allowed=False)
    text = describe(plan)
    assert text.startswith("place.cart -> place.decide")
    assert "знято: x.y (кроку немає в словнику)" in text
    assert "не годиться: у плані немає рішення" in text


def test_the_step_builder_keeps_every_field_and_its_defaults():
    from komora.core.plan import _kind

    bare = _kind("x.y", Phase.SHELF, "silpo_get_products")
    assert (bare.name, bare.phase, bare.tool) == ("x.y", Phase.SHELF, "silpo_get_products")
    assert bare.needs == frozenset() and bare.gives == frozenset()
    assert bare.writes is False and bare.repeatable is False
    full = _kind(
        "a.b",
        Phase.CART,
        "code",
        needs=("cart", "lines"),
        gives=("written",),
        writes=True,
        repeatable=True,
    )
    assert full.needs == frozenset({"cart", "lines"}) and full.gives == frozenset({"written"})
    assert full.writes is True and full.repeatable is True


def test_garbage_names_its_exact_fatal_and_leaves_no_steps():
    for raw in ({"steps": "не список"}, "рядок", {"steps": 42}):
        plan = validate(raw, writes_allowed=False)
        assert plan.steps == () and plan.fatal == "план не список кроків", raw
    assert validate({"goal": "кошик"}, writes_allowed=False).fatal == "жодного кроку не лишилось"
    empty = validate([], writes_allowed=False)
    assert empty.fatal == "жодного кроку не лишилось" and empty.steps == ()


def test_every_drop_names_the_step_and_its_position():
    plan = validate(
        [
            {},
            "cart.nuke",
            "slot.pick",
            "slot.pick",
            "history.receipts",
            "shelf.search",
            "history.model",
            "intents.compose",
            "shelf.search",
            "cart.slot",
            "decide.pick",
        ],
        writes_allowed=False,
        known=("branch", "delivery_type", "slots", "cart"),
    )
    assert [(d.name, d.reason, d.position) for d in plan.dropped] == [
        ("{}", "крок без назви", 0),
        ("cart.nuke", "кроку немає в словнику", 1),
        ("slot.pick", "повтор кроку, який не повторюється", 3),
        ("shelf.search", "немає входу: intents", 5),
        ("cart.slot", "запис без дозволу клієнта", 9),
    ]
    assert plan.names() == (
        "slot.pick",
        "history.receipts",
        "history.model",
        "intents.compose",
        "shelf.search",
        "decide.pick",
    )


def test_a_drop_never_stops_the_steps_after_it():
    no_name = validate([{"why": "просто так"}, "place.cart"], writes_allowed=False)
    assert no_name.names() == ("place.cart",)
    dup = validate(["place.cart", "place.cart", "place.decide"], writes_allowed=False)
    assert dup.names() == ("place.cart", "place.decide")
    missing = validate(["slot.list", "place.cart"], writes_allowed=False)
    assert missing.names() == ("place.cart",)
    early = validate(
        ["decide.pick", "place.cart"], writes_allowed=False, known=("intents", "candidates")
    )
    assert early.names() == ("place.cart",)
    assert early.dropped[0].reason == "полиця до слота"


def test_the_ceiling_keeps_exactly_the_ceiling_and_drops_the_rest_by_name():
    plan = validate(PADDED, writes_allowed=True)
    assert len(plan.steps) == MAX_STEPS
    over = [d for d in plan.dropped if d.reason == f"понад стелю {MAX_STEPS} кроків"]
    assert len(over) == len(PADDED) - MAX_STEPS
    assert over[0].name == "shelf.search" and over[0].position == MAX_STEPS
    assert over[-1].name == "cart.reread" and over[-1].position == len(PADDED) - 1


def test_the_write_ceiling_names_the_step_and_position_too():
    writes = [*FULL[:-1], *["cart.write"] * (MAX_WRITES + 2), "cart.reread"]
    plan = validate(writes, writes_allowed=True)
    over = [d for d in plan.dropped if d.reason == f"понад стелю {MAX_WRITES} записів"]
    assert all(d.name == "cart.write" for d in over)
    assert [d.position for d in over] == list(
        range(len(FULL) - 1 + MAX_WRITES - 2, len(writes) - 1)
    )


def test_a_write_before_the_decision_names_everything_it_lacks():
    plan = validate(
        ["cart.slot"], writes_allowed=True, known=("cart", "slot", "lines", "economics")
    )
    assert [(d.name, d.reason, d.position) for d in plan.dropped] == [
        ("cart.slot", "запис до рішення: бракує decide.pick, economy.settle", 0)
    ]


def test_a_known_slot_lets_the_shelf_go_first():
    plan = validate(
        ["shelf.search", "decide.pick", "decide.chain", "economy.settle"],
        writes_allowed=False,
        known=("branch", "delivery_type", "slot", "intents"),
    )
    assert plan.ok and plan.dropped == ()


def test_only_the_slot_itself_opens_the_shelf_not_any_step_before_it():
    plan = validate(
        ["place.cart", "decide.pick"], writes_allowed=False, known=("intents", "candidates")
    )
    assert plan.names() == ("place.cart",)
    assert [(d.name, d.reason, d.position) for d in plan.dropped] == [
        ("decide.pick", "полиця до слота", 1)
    ]


def test_a_step_reads_its_name_from_name_too_and_bare_names_have_no_why():
    plan = validate(
        [{"name": "place.cart", "why": "так"}, "place.decide", {"step": "slot.list"}],
        writes_allowed=False,
        known=("branch", "delivery_type"),
    )
    assert [(s.name, s.why) for s in plan.steps] == [
        ("place.cart", "так"),
        ("place.decide", ""),
        ("slot.list", ""),
    ]
    long_item = {"why": "x" * 100}
    plan = validate([long_item], writes_allowed=False)
    assert plan.dropped[0].name == str(long_item)[:60] and len(plan.dropped[0].name) == 60


def test_the_code_plan_settles_once_without_a_budget():
    plan = code_plan(source="cart", writes=False)
    assert plan.names().count("economy.settle") == 1
    assert code_plan(source="list", writes=False, budget=True).names().count("economy.settle") == 2


def test_the_repair_note_is_exact_and_speaks_even_when_the_plan_is_fine_after_the_cut():
    plan = validate(["cart.nuke", *FULL], writes_allowed=True)
    assert plan.ok
    assert repair_note(plan) == (
        "Не пройшли перевірку: «cart.nuke» (крок 1): кроку немає в словнику. "
        "Перескладай план, лишаючи лише кроки зі словника."
    )


def test_describe_is_exact_for_the_empty_plan_and_for_two_dropped():
    assert describe(validate([], writes_allowed=False)) == (
        "порожньо; не годиться: жодного кроку не лишилось"
    )
    plan = validate(["a.b", "c.d", "place.cart"], writes_allowed=False)
    assert describe(plan) == (
        "place.cart; знято: a.b (кроку немає в словнику), c.d (кроку немає в словнику); "
        "не годиться: у плані немає рішення (decide.pick)"
    )


def test_the_facts_of_a_list_of_steps_are_their_promises_and_nothing_else():
    assert facts_of(["place.address"]) == ("address",)
    assert facts_of(["shelf.search", "shelf.by_article"]) == ("candidates", "intents")
    assert facts_of(["slot.pick", "place.decide"]) == ("branch", "delivery_type", "slot")
    assert facts_of([]) == ()


def test_the_facts_of_the_read_phase_name_the_history_the_code_already_has():
    read = [
        "place.address",
        "place.delivery_types",
        "place.cart",
        "place.decide",
        "slot.list",
        "slot.pick",
        "history.receipts",
        "history.orders",
        "history.model",
    ]

    assert "history" in facts_of(read)
    assert BY_NAME["intents.compose"].needs <= set(facts_of(read))


PANTRY_KNOWN = ("history", "orders", "pantry", "receipts")


def test_the_pantry_plan_passes_its_own_validator_and_writes_nothing():
    plan = code_plan(source="pantry", writes=False)

    assert plan.ok and plan.dropped == (), describe(plan)
    assert plan.source == "code"
    assert plan.names() == (
        "pantry.name",
        "pantry.rhythm",
        "pantry.keeps",
        "pantry.aisle",
        "pantry.ask",
    )
    assert plan.writes == 0


def test_the_pantry_plan_ignores_the_write_permission_it_does_not_use():
    assert code_plan(source="pantry", writes=True).names() == (
        code_plan(source="pantry", writes=False).names()
    )


def test_a_pantry_plan_is_not_broken_by_the_missing_basket_decision():
    names = ["pantry.name", "pantry.rhythm"]

    as_basket = validate(names, writes_allowed=False, known=PANTRY_KNOWN)
    as_pantry = validate(names, writes_allowed=False, known=PANTRY_KNOWN, aim=Aim.PANTRY)

    assert as_basket.fatal is not None
    assert {item.name for item in as_basket.dropped} == {"pantry.name", "pantry.rhythm"}
    assert all("фази" in item.reason for item in as_basket.dropped)
    assert as_pantry.fatal is None
    assert as_pantry.names() == ("pantry.name", "pantry.rhythm")


def test_the_basket_verdict_still_demands_the_pick_and_the_pantry_one_does_not():
    seen = Carried(steps=2, seen=frozenset({"shelf.search", "decide.chain"}))

    assert verdict(seen) == "у плані немає рішення (decide.pick)"
    assert verdict(seen, aim=Aim.PANTRY) is None


def test_an_empty_plan_is_fatal_for_the_basket_and_legal_for_the_pantry():
    assert verdict(Carried()) == "жодного кроку не лишилось"
    assert verdict(Carried(), aim=Aim.PANTRY) is None
    assert validate([], writes_allowed=False, aim=Aim.PANTRY).ok


def test_the_pantry_is_drawn_twice_and_named_once():
    plan = validate(
        ["pantry.draw", "pantry.name", "pantry.draw", "pantry.name"],
        writes_allowed=False,
        known=PANTRY_KNOWN,
        aim=Aim.PANTRY,
    )

    assert plan.names() == ("pantry.draw", "pantry.name", "pantry.draw")
    assert [(d.name, d.reason) for d in plan.dropped] == [
        ("pantry.name", "повтор кроку, який не повторюється")
    ]


def test_the_pantry_asks_the_model_after_the_label_not_before_it():
    plan = validate(
        ["pantry.rhythm", "pantry.keeps"],
        writes_allowed=False,
        known=PANTRY_KNOWN,
        aim=Aim.PANTRY,
    )

    assert plan.names() == ()
    assert [d.reason for d in plan.dropped] == ["немає входу: named", "немає входу: named"]


def test_the_pantry_does_not_wait_for_a_slot_it_never_asks_the_shelf():
    plan = validate(["pantry.name"], writes_allowed=False, known=("history",), aim=Aim.PANTRY)

    assert plan.names() == ("pantry.name",)
    assert plan.dropped == ()


def test_the_facts_before_the_pantry_loop_name_the_rows_the_code_already_drew():
    assert facts_of(BEFORE_PANTRY) == PANTRY_KNOWN
    assert (
        validate(
            ["pantry.name"], writes_allowed=False, known=facts_of(BEFORE_PANTRY), aim=Aim.PANTRY
        ).dropped
        == ()
    )


def test_a_step_the_aim_cannot_execute_is_cut_by_name_not_ignored():
    plan = validate(
        ["pantry.name", "intents.compose", "pantry.ask"],
        writes_allowed=False,
        known=PANTRY_KNOWN,
        aim=Aim.PANTRY,
    )

    assert plan.names() == ("pantry.name", "pantry.ask")
    assert [(d.name, d.reason) for d in plan.dropped] == [
        ("intents.compose", "крок фази «наміри» — ця мета його не виконує")
    ]


def test_the_basket_aim_narrows_no_phase_at_all():
    plan = validate(FULL, writes_allowed=True)

    assert plan.ok and plan.dropped == (), describe(plan)


def test_the_report_counts_occupancies_so_one_run_covers_one_place_in_the_plan():
    made = report(
        ["cart.write", "cart.reread", "cart.write", "cart.reread"],
        done=["cart.write", "cart.reread"],
    )

    assert made.done == ("cart.write", "cart.reread")
    assert made.later == ("cart.write", "cart.reread")
    assert made.tag == "2/4" and made.beyond == ()


def test_an_extra_run_of_a_planned_step_is_beyond_the_plan_not_invisible():
    made = report(
        ["cart.write", "cart.reread"],
        done=["cart.write", "cart.reread", "cart.reread"],
    )

    assert made.done == ("cart.write", "cart.reread")
    assert made.beyond == ("cart.reread",)


def test_the_beyond_list_is_sorted_and_keeps_every_repeat():
    made = report(
        ["intents.compose"],
        done=["shelf.search", "intents.compose", "cart.reread", "shelf.search"],
    )

    assert made.beyond == ("cart.reread", "shelf.search", "shelf.search")


def test_a_step_only_other_phases_reported_counts_once_and_not_as_beyond():
    made = report(["shelf.search", "shelf.search"], done=[], also={"shelf.search"})

    assert made.done == ("shelf.search",)
    assert made.unneeded == ("shelf.search",) and made.beyond == ()


def test_a_step_both_sides_report_is_not_counted_twice():
    both = report(["shelf.search"], done=["shelf.search"], also={"shelf.search"})

    assert both.done == ("shelf.search",) and both.beyond == ()


def test_a_refused_step_carries_its_reason_and_its_kind_not_a_bare_name():
    cut = Refused(name="shelf.by_article", why="немає входу: history", kind=Refusal.RULE)
    made = report(["shelf.by_article"], done=[], refused=[cut])

    assert made.refused == (cut,) and made.unneeded == ()
    assert made.of(Refusal.RULE) == (cut,) and made.of(Refusal.BROKE) == ()


def test_two_refusals_of_one_step_are_spent_in_the_order_they_happened():
    first = Refused(name="cart.write", why="збій кроку (мережа)", kind=Refusal.BROKE)
    second = Refused(name="cart.write", why="стеля записів: 2", kind=Refusal.RULE)
    made = report(["cart.write", "cart.write"], done=[], refused=[first, second])

    assert made.refused == (first, second)


def test_a_refusal_wins_over_the_checkout_bucket_for_the_same_step():
    cut = Refused(name="cart.write", why="збій кроку (мережа)", kind=Refusal.BROKE)
    made = report(["cart.write"], done=[], refused=[cut])

    assert made.refused == (cut,) and made.later == ()


def test_a_refusal_wins_over_the_missing_runner_too():
    cut = Refused(name="shelf.similar", why="збій кроку (мережа)", kind=Refusal.BROKE)
    made = report(["shelf.similar"], done=[], refused=[cut])

    assert made.refused == (cut,)
    assert made.of(Refusal.ORPHAN) == ()


def test_a_refusal_of_a_step_outside_the_plan_is_still_reported():
    cut = Refused(name="cart.reread", why="збій кроку (мережа)", kind=Refusal.BROKE)
    made = report(["intents.compose"], done=["intents.compose"], refused=[cut])

    assert made.refused == (cut,) and made.done == ("intents.compose",)


def test_a_step_the_pipeline_never_runs_says_so_and_is_not_unneeded():
    made = report(["shelf.card", "shelf.similar"], done=[])

    assert made.unneeded == ()
    assert [(r.name, r.kind) for r in made.refused] == [
        ("shelf.card", Refusal.ORPHAN),
        ("shelf.similar", Refusal.ORPHAN),
    ]
    assert made.refused[0].why == "конвеєр цього кроку не виконує"


def test_an_unrun_cart_step_waits_for_checkout_and_an_unrun_shelf_step_does_not():
    made = report(["cart.slot", "decide.loop"], done=[])

    assert made.later == ("cart.slot",) and made.unneeded == ("decide.loop",)


def test_a_step_a_phase_did_itself_fills_its_place_in_the_plan():
    made = report(
        ["economy.settle", "economy.settle"],
        done=["economy.settle"],
        did=[Did(name="economy.settle", why="різ під межу гостя: 2 поз.")],
    )

    assert made.done == ("economy.settle", "economy.settle")
    assert made.unneeded == () and made.beyond == ()


def test_a_step_a_phase_did_beyond_the_plan_names_its_reason_not_just_itself():
    made = report(
        ["economy.settle"],
        done=["economy.settle"],
        did=[Did(name="economy.settle", why="різ під вагу слота: 1 поз.")],
    )

    assert made.beyond == ("economy.settle",)
    assert made.args()["кроки"]["понад план"] == ["economy.settle — різ під вагу слота: 1 поз."]


def test_beyond_without_a_named_reason_stays_a_bare_name():
    made = report(["intents.compose"], done=["intents.compose", "slot.pick"])

    assert made.args()["кроки"]["понад план"] == ["slot.pick"]


def test_two_phases_that_did_the_same_step_do_not_share_one_reason():
    made = report(
        [],
        done=[],
        did=[
            Did(name="economy.settle", why="різ під межу гостя: 2 поз."),
            Did(name="economy.settle", why="різ під вагу слота: 1 поз."),
        ],
    )

    assert made.args()["кроки"]["понад план"] == [
        "economy.settle — різ під межу гостя: 2 поз.",
        "economy.settle — різ під вагу слота: 1 поз.",
    ]


def test_the_tag_counts_the_plan_not_the_work_done_beyond_it():
    made = report(["intents.compose"], done=["intents.compose", "cart.reread"])

    assert made.tag == "1/1"


@pytest.mark.parametrize("kind", [Refusal.RULE, Refusal.BROKE, Refusal.ORPHAN])
def test_a_broken_run_is_yellow_whatever_broke_it(kind):
    made = Report(
        total=1,
        done=(),
        later=(),
        unneeded=(),
        refused=(Refused(name="shelf.card", why="чому", kind=kind),),
        beyond=(),
    )

    assert made.tone == "warn"


def test_a_step_that_legally_gave_nothing_is_not_yellow():
    made = Report(
        total=1,
        done=(),
        later=(),
        unneeded=(),
        refused=(Refused(name="decide.pick", why="без моделі", kind=Refusal.EMPTY),),
        beyond=(),
    )

    assert made.tone == "muted"


def test_an_unneeded_step_is_muted_and_a_deferred_one_is_still_good():
    quiet = report(["decide.loop"], done=[])
    fine = report(["cart.slot"], done=[])

    assert quiet.tone == "muted"
    assert fine.tone == "good"


def test_a_plan_done_whole_is_good():
    assert report(["intents.compose"], done=["intents.compose"]).tone == "good"


def test_the_summary_names_only_the_buckets_that_happened():
    made = report(["intents.compose"], done=["intents.compose"])

    assert made.summary() == "виконано 1 з 1 кроків"


def test_the_summary_says_every_kind_of_refusal_by_its_own_words():
    made = report(
        ["cart.slot", "decide.loop", "shelf.card", "decide.pick", "shelf.by_article"],
        done=[],
        also={"cart.slot"},
        refused=[
            Refused(name="decide.pick", why="без моделі", kind=Refusal.EMPTY),
            Refused(name="shelf.by_article", why="немає входу", kind=Refusal.RULE),
        ],
    )

    assert made.summary() == (
        "виконано 1 з 5 кроків; не знадобилось 1; нема чого дати 1; без входу 1; без виконавця 1"
    )


def test_the_summary_counts_the_checkout_bucket_and_the_work_beyond_the_plan():
    made = report(["cart.write", "cart.reread"], done=["cart.reread", "decide.chain"])

    assert made.summary() == "виконано 1 з 2 кроків; на «Оформити» 1; понад план 1"


def test_the_args_keep_the_zeros_because_a_missing_key_reads_as_a_zero():
    args = report(["intents.compose"], done=["intents.compose"]).args()

    assert args["виконано"] == 1
    assert args["на оформлення"] == 0 and args["не знадобилось"] == 0
    assert args["понад план"] == 0
    assert [args[str(kind)] for kind in Refusal] == [0, 0, 0, 0]
    assert args["кроки"]["виконано"] == ["intents.compose"]


def test_the_args_carry_the_reason_together_with_the_name():
    args = report(
        ["shelf.by_article", "cart.slot"],
        done=[],
        refused=[Refused(name="shelf.by_article", why="немає входу: history", kind=Refusal.RULE)],
    ).args()

    assert args["кроки"][str(Refusal.RULE)] == ["shelf.by_article — немає входу: history"]
    assert args["кроки"]["на оформлення"] == ["cart.slot"]
    assert args[str(Refusal.RULE)] == 1


def test_the_refusal_words_are_the_report_and_they_are_four_different_answers():
    assert [str(kind) for kind in Refusal] == [
        "нема чого дати",
        "без входу",
        "збій",
        "без виконавця",
    ]


def test_an_empty_plan_reports_nothing_and_is_good():
    made = report([], done=[])

    assert made.tag == "0/0" and made.tone == "good"
    assert made.summary() == "виконано 0 з 0 кроків"


STAGED = ("branch", "slot", "history", "intents")

STAGED_WALK = (
    "address",
    "branch",
    "cart",
    "delivery_type",
    "delivery_types",
    "economics",
    "history",
    "lines",
    "orders",
    "receipts",
    "slot",
    "slots",
)


def test_a_producer_standing_after_its_reader_is_dropped_and_names_both():
    plan = validate(
        ["shelf.by_article", "decide.pick", "shelf.search", "decide.chain"],
        writes_allowed=False,
        known=STAGED,
    )

    assert plan.names() == ("shelf.by_article", "decide.pick", "decide.chain")
    assert plan.dropped[0].name == "shelf.search" and plan.dropped[0].position == 2
    assert plan.dropped[0].reason == (
        "запізнілий давач: candidates, intents уже прочитав decide.pick"
    )


def test_the_late_producer_costs_one_step_and_not_the_plan():
    plan = validate(
        ["shelf.by_article", "decide.pick", "shelf.search"],
        writes_allowed=False,
        known=STAGED,
    )

    assert plan.ok and plan.fatal is None
    assert "запізнілий давач" in repair_note(plan)


def test_a_reader_that_runs_again_later_sees_the_late_step_itself():
    plan = validate(
        ["shelf.search", "decide.pick", "shelf.search", "decide.pick"],
        writes_allowed=False,
        known=STAGED,
    )

    assert plan.dropped == () and plan.names().count("shelf.search") == 2


def test_a_fact_that_flows_back_up_the_pipeline_is_a_loop_and_not_a_mess():
    plan = validate(
        [*FULL, "cart.revalidate", "cart.reread"],
        writes_allowed=True,
    )

    assert plan.dropped == () and "cart.revalidate" in plan.names()


def test_a_step_that_reads_its_own_fact_is_never_late():
    plan = validate(
        ["shelf.search", "shelf.similar", "shelf.card", "decide.pick"],
        writes_allowed=False,
        known=STAGED,
    )

    assert plan.dropped == () and len(plan.steps) == 4


def test_a_producer_whose_facts_nobody_read_yet_passes():
    plan = validate(
        ["shelf.search", "decide.pick", "decide.clarify", "place.cart"],
        writes_allowed=False,
        known=STAGED,
    )

    assert plan.dropped == () and plan.names()[-1] == "place.cart"


def test_the_late_producer_is_not_the_missing_input_check_from_the_other_side():
    alone = validate(["decide.pick", "shelf.search"], writes_allowed=False, known=STAGED)
    assert alone.dropped[0].reason == "немає входу: candidates"

    paired = validate(
        ["shelf.by_article", "decide.pick", "shelf.search"],
        writes_allowed=False,
        known=STAGED,
    )
    assert paired.dropped[0].reason.startswith("запізнілий давач")


def test_a_second_settle_after_the_lines_changed_again_is_late_only_unrepaired():
    tail = ["intents.compose", "shelf.search", "decide.pick", "decide.chain", "economy.settle"]
    staged = ("branch", "slot", "history")
    unrepaired = validate([*tail, "decide.loop"], writes_allowed=False, known=staged)
    assert unrepaired.dropped[0].name == "decide.loop"
    assert unrepaired.dropped[0].reason == "запізнілий давач: lines уже прочитав economy.settle"

    repaired = validate(
        [*tail, "decide.loop", "economy.settle"], writes_allowed=False, known=staged
    )
    assert repaired.dropped == ()


def test_the_paired_walks_of_the_executor_can_never_trip_the_order_rule():
    walks = [
        ["place.address", "place.delivery_types"],
        ["slot.list", "slot.pick"],
        ["history.receipts", "history.orders", "history.model"],
        ["cart.write", "cart.reread"],
    ]
    for walk in walks:
        assert len({BY_NAME[name].phase for name in walk}) == 1, walk
        checked = validate(
            walk,
            writes_allowed=True,
            known=STAGED_WALK,
            carried=Carried(steps=1, seen=frozenset({"decide.pick", "economy.settle"})),
            whole=False,
        )
        assert checked.dropped == (), (walk, describe(checked))


def test_every_phase_has_a_place_in_the_pipeline():
    from komora.core.plan import _PIPELINE

    assert set(_PIPELINE) == set(Phase) and len(_PIPELINE) == len(set(_PIPELINE))


def test_the_core_names_the_steps_that_build_the_lines():
    from komora.core.plan import BY_NAME, CORE_AFTER_PLAN

    core = CORE_AFTER_PLAN[Aim.BASKET]
    gives = {name for step in core for name in BY_NAME[step].gives}
    for step in core:
        before = {"history", "slot", "place", "cart", "branch"}
        assert set(BY_NAME[step].needs) <= gives | before, (
            f"{step}: вхід не дає ні ядро, ні читання до плану"
        )
    assert "lines" in gives and "economics" in gives


def test_the_pantry_has_no_core_and_that_is_an_answer():
    from komora.core.plan import CORE_AFTER_PLAN

    assert CORE_AFTER_PLAN[Aim.PANTRY] == ()


def test_the_pantry_question_step_survives_a_plan_of_one_step():
    plan = validate(
        ["pantry.ask"], writes_allowed=False, known=facts_of(BEFORE_PANTRY), aim=Aim.PANTRY
    )

    assert plan.names() == ("pantry.ask",)
    assert plan.dropped == ()


def test_a_step_carries_its_address_and_a_stray_label_is_cut_by_itself():
    raw = [{"step": "pantry.shelf", "labels": ["молоко", "молоко", "єдиноріг"]}]
    judged = validate(
        raw,
        writes_allowed=False,
        known=("pantry", "history"),
        aim=Aim.PANTRY,
        labels=["молоко", "хліб"],
    )
    (step,) = judged.steps
    assert step.labels == ("молоко",) and step.stray == ("єдиноріг",)
    assert "[1]" in describe(judged) and "єдиноріг" in describe(judged)

    loose = validate(raw, writes_allowed=False, known=("pantry", "history"), aim=Aim.PANTRY)
    assert loose.steps[0].labels == ("молоко", "єдиноріг") and loose.steps[0].stray == ()


def test_the_shelf_step_needs_only_what_the_pantry_has():
    kind = BY_NAME["pantry.shelf"]
    assert kind.needs <= set(facts_of(BEFORE_PANTRY))
    assert kind.tool == "silpo_find_products_batch" and not kind.writes
    assert "pantry.shelf" in dictionary_text(Aim.PANTRY)
