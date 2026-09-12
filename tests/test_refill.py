from __future__ import annotations

import json
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import pytest
from fastapi import HTTPException

from komora.agent.basket import Receipts, assemble_list, load_history
from komora.agent.economics import ORDER_MIN
from komora.agent.refill import RefillError, pick_answer, refill, take_cheaper
from komora.agent.table import top_up_table
from komora.api import app as api
from komora.api import history as history_memory
from komora.api import runs
from komora.api.schemas import BuildRequest, Clarification, RefillRequest
from komora.auth.session import GuestSession
from komora.core.occasion import occasion_of
from komora.core.target import band as budget_band
from komora.mcp.client import SilpoMCP

pytestmark = pytest.mark.anyio

SLOT = {
    "start": "2026-08-21T11:30:00+00:00",
    "end": "2026-08-21T13:00:00+00:00",
    "available": True,
    "deliveryType": "DeliveryHome",
    "deliveryCost": 89,
    "deliveryCostMap": [{"cost": 59, "fromOrderCost": 1199}],
    "minOrderCost": 599,
    "maxWeight": 50,
}

NOW = datetime(2026, 8, 21, tzinfo=UTC)

KINDS = 9

GUEST = GuestSession(access="токен")
OTHER = GuestSession(access="чужий токен")


def _product(pid: int, name: str, price: float, stock: int = 20) -> dict[str, Any]:
    return {
        "id": f"00000000-0000-4000-8000-{pid:012d}",
        "name": name,
        "slug": f"slug-{pid}",
        "price": price,
        "oldPrice": None,
        "stock": stock,
        "available": True,
        "image": None,
        "weighted": False,
        "step": 1,
        "displayRatio": "1шт",
        "companyId": "00000000-0000-4000-8000-000000000001",
        "branchId": "00000000-0000-4000-8000-000000000002",
        "externalProductId": pid,
    }


def _names() -> list[tuple[int, str, float]]:
    return [(300 + i, f"Товар {i}", float(70 + i)) for i in range(KINDS)]


@pytest.fixture
def stand(tmp_path) -> SilpoMCP:
    (tmp_path / "silpo_get_time_slots.json").write_text(
        json.dumps({"slots": [SLOT]}), encoding="utf-8"
    )
    (tmp_path / "silpo_get_my_offline_orders.json").write_text(
        json.dumps(
            {
                "orders": [
                    {
                        "createdAt": day,
                        "products": [
                            {
                                "lagerId": lager,
                                "name": name,
                                "unit": "шт",
                                "quantity": 1,
                                "price": price,
                            }
                            for lager, name, price in _names()[start : start + 3]
                        ],
                    }
                    for start in (0, 3, 6)
                    for day in ("2026-07-18", "2026-07-25", "2026-08-01", "2026-08-08")
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "silpo_find_products_batch.json").write_text(
        json.dumps(
            {
                "queries": [
                    {"query": name, "products": [_product(lager, name, price)]}
                    for lager, name, price in _names()
                ]
                + [
                    {"query": "шафран", "products": []},
                    {
                        "query": "останнє",
                        "products": [_product(*_names()[KINDS - 1])],
                    },
                ]
                + [
                    {
                        "query": f"{name} вужче",
                        "products": [_product(900 + lager, f"Вужчий {name}", 55.0)],
                    }
                    for lager, name, _ in _names()
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "silpo_get_my_shopping_cart.json").write_text(
        json.dumps({"shoppingCartId": None}), encoding="utf-8"
    )
    return SilpoMCP(fixtures_dir=tmp_path)


async def _plan(stand: SilpoMCP, **request: Any):
    return await assemble_list(
        stand,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week"} | request),
        now=NOW,
    )


async def test_the_ceiling_leaves_something_to_close_the_week_with(stand):
    plan = await _plan(stand)

    assert len(plan.basket.postponed) == KINDS - len(plan.basket.lines)
    assert all(item.refillable for item in plan.basket.postponed)


async def test_refill_closes_the_rest_of_the_week(stand):
    plan = await _plan(stand)
    before = {line.intent for line in plan.lines}

    filled = await refill(stand, None, plan, RefillRequest(), now=NOW)

    assert len(filled.lines) == KINDS
    assert {line.intent for line in filled.lines} > before
    assert filled.basket.postponed == [], "докинуте не лишається «відкладеним»"


async def test_the_reason_for_the_headroom_survives_the_refill(stand):
    plan = await _plan(stand)
    before = plan.basket.cycles_note

    filled = await refill(stand, None, plan, RefillRequest(), now=NOW)

    assert filled.basket.postponed == [], "кнопки більше немає"
    assert before is not None and filled.basket.cycles_note == before


async def test_the_numbers_grow_with_the_list(stand):
    plan = await _plan(stand)
    filled = await refill(stand, None, plan, RefillRequest(), now=NOW)

    added = filled.lines[len(plan.lines) :]
    assert filled.basket.total == plan.basket.total + sum(
        (line.total for line in added), Decimal(0)
    )
    assert ORDER_MIN in plan.basket.blockers
    assert ORDER_MIN not in filled.basket.blockers


async def test_the_refill_is_written_into_the_trace_step_by_step(stand):
    plan = await _plan(stand)
    filled = await refill(stand, None, plan, RefillRequest(), now=NOW)

    added = [s for s in filled.basket.trace if s.id.startswith("step-refill")]
    assert [s.id for s in added] == [
        "step-refill-kinds",
        "step-refill-history",
        "step-refill-search",
        "step-refill",
    ]
    assert added[0].tag == "ярус не спрацював", "без бази крок мусить сказати це вголос"
    assert added[-1].tag == f"+{KINDS - len(plan.lines)} поз."
    assert added[-1].decision is not None and "докинуто" in added[-1].decision
    assert filled.basket.stats.mcp_calls > plan.basket.stats.mcp_calls
    assert filled.basket.stats.duration_ms == sum(
        step.duration_ms or 0 for step in filled.basket.trace
    )
    kinds = next(s for s in added if s.id == "step-refill-kinds")
    assert kinds.duration_ms is None, "без бази читання не було — це не нуль"


async def test_two_refills_in_a_row_keep_the_step_numbers_apart(stand):
    plan = await _plan(stand, shoppingList=["Товар 0"])
    once = await refill(stand, None, plan, RefillRequest(intents=["Товар 8"]), now=NOW)
    twice = await refill(stand, None, once, RefillRequest(), now=NOW)

    ids = [step.id for step in twice.basket.trace]
    assert ids.count("step-refill") == 2, "два добори -- два кроки з тим самим іменем"
    seqs = [step.seq for step in twice.basket.trace]
    assert len(set(seqs)) == len(seqs), "номер лишається унікальним на весь трейс"
    assert seqs == sorted(seqs), "продовжений трейс нумерується далі, а не з початку"


async def test_what_was_tried_and_not_found_stops_being_postponed(stand, tmp_path):
    plan = await _plan(stand)
    batch = json.loads((tmp_path / "silpo_find_products_batch.json").read_text(encoding="utf-8"))
    gone = f"Товар {KINDS - 1}"
    batch["queries"] = [q for q in batch["queries"] if q["query"] != gone]
    batch["queries"].append({"query": gone, "products": []})
    (tmp_path / "silpo_find_products_batch.json").write_text(json.dumps(batch), encoding="utf-8")

    filled = await refill(stand, None, plan, RefillRequest(), now=NOW)

    assert gone in filled.basket.unresolved
    assert gone not in [item.intent for item in filled.basket.postponed]


async def test_the_previous_run_survives_the_refill(stand):
    plan = await _plan(stand)
    before = [line.product["name"] for line in plan.lines]

    await refill(stand, None, plan, RefillRequest(), now=NOW)

    assert [line.product["name"] for line in plan.lines] == before
    assert plan.basket.postponed != []


async def test_the_guests_own_words_are_refilled_too(stand):
    plan = await _plan(stand, shoppingList=["Товар 0"])
    assert "Товар 8" not in {line.intent for line in plan.lines}

    filled = await refill(stand, None, plan, RefillRequest(intents=["Товар 8"]), now=NOW)

    names = [line.product["name"] for line in filled.lines]
    assert names[-1] == "Товар 8", "докинуте стає останнім рядком, а не переставляє кошик"


async def test_what_is_already_in_the_basket_is_not_doubled(stand):
    plan = await _plan(stand, shoppingList=["Товар 0"])

    with pytest.raises(RefillError, match="вже в кошику"):
        await refill(stand, None, plan, RefillRequest(intents=["Товар 0"]), now=NOW)


async def test_the_same_product_under_another_word_does_not_double_the_line(stand):
    plan = await _plan(stand, shoppingList=["Товар 8"])
    assert "Товар 8" in {line.product["name"] for line in plan.lines}

    with pytest.raises(RefillError, match="це вже в кошику: «Товар 8»"):
        await refill(stand, None, plan, RefillRequest(intents=["останнє"]), now=NOW)


async def test_an_answer_that_lands_on_an_existing_line_closes_it_instead_of_failing(stand):
    plan = await _plan(stand, shoppingList=["Товар 8"])
    same = next(line for line in plan.lines if line.product["name"] == "Товар 8")
    plan.basket.questions = [
        Clarification(intent="останнє", question="Які саме?", options=[], picks=[])
    ]

    filled = await refill(
        stand,
        None,
        plan,
        RefillRequest.model_validate(
            {"intents": ["останнє"], "answers": [{"intent": "останнє", "query": "останнє"}]}
        ),
        now=NOW,
    )

    assert len(filled.lines) == len(plan.lines), "рядок один, а не два"
    closed = next(line for line in filled.lines if line.product["name"] == "Товар 8")
    assert closed.qty == same.qty, "кількості не складаються: гість просив вид, а не подвоєння"
    assert filled.basket.questions == [], "питання зникає, інакше другий дотик веде в ту саму стіну"


async def test_nothing_to_refill_says_so_instead_of_returning_the_same_basket(stand):
    plan = await _plan(stand)
    filled = await refill(stand, None, plan, RefillRequest(), now=NOW)

    with pytest.raises(RefillError, match="добирати нема чого"):
        await refill(stand, None, filled, RefillRequest(), now=NOW)


async def test_a_word_that_is_not_on_the_shelf_is_named(stand):
    plan = await _plan(stand)

    result = await refill(stand, None, plan, RefillRequest(intents=["шафран"]), now=NOW)
    assert "шафран" in result.unresolved
    assert all(item.intent != "шафран" for item in result.basket.postponed)


async def test_the_refill_does_not_cut_itself_to_fit_the_limit(stand):
    plan = await _plan(stand, budget=500)
    assert plan.basket.total <= Decimal(500), "зібране в межу влізло"

    filled = await refill(stand, None, plan, RefillRequest(), now=NOW)

    assert filled.basket.total > Decimal(500)
    assert len(filled.lines) == KINDS
    assert filled.basket.trimmed == []
    assert filled.basket.budget == Decimal(500), "межа лишається видимою"


async def test_the_refill_hands_back_a_new_run_id(stand, monkeypatch):
    runs.forget_all()
    monkeypatch.setattr(api, "SilpoMCP", lambda **kwargs: stand)
    first = runs.remember(await _plan(stand), owner=GUEST.owner)

    second = await api.refill_basket(first.run_id, RefillRequest(), GUEST, None)

    assert second.run_id != first.run_id
    assert len(second.lines) > len(first.lines)
    assert runs.recall(first.run_id, owner=GUEST.owner) is not None


async def test_someone_elses_run_is_the_same_404_as_a_forgotten_one(stand, monkeypatch):
    runs.forget_all()
    monkeypatch.setattr(api, "SilpoMCP", lambda **kwargs: stand)
    mine = runs.remember(await _plan(stand), owner=GUEST.owner)

    with pytest.raises(HTTPException) as theirs:
        await api.refill_basket(mine.run_id, RefillRequest(), OTHER, None)
    with pytest.raises(HTTPException) as forgotten:
        await api.refill_basket("немає-такого", RefillRequest(), GUEST, None)

    assert theirs.value.status_code == forgotten.value.status_code == 404
    assert theirs.value.detail == forgotten.value.detail


async def test_a_refill_with_nothing_to_do_is_a_409_not_a_500(stand, monkeypatch):
    runs.forget_all()
    monkeypatch.setattr(api, "SilpoMCP", lambda **kwargs: stand)
    plan = await _plan(stand, shoppingList=["Товар 0"])
    kept = runs.remember(plan, owner=GUEST.owner)

    with pytest.raises(HTTPException) as exc:
        await api.refill_basket(kept.run_id, RefillRequest(intents=["Товар 0"]), GUEST, None)

    assert exc.value.status_code == 409
    assert "вже в кошику" in exc.value.detail


class _DecliningLLM:

    model = "fake-model"

    def __init__(self, why: str) -> None:
        self.why = why

    async def decide(self, *, system, user, schema, schema_name="decision", max_tokens=2048, **_):
        from komora.agent.llm import Decision, Usage

        asked = json.loads(user)
        return Decision(
            data={
                "picks": [
                    {"intent": row["намір"], "chosen_id": "", "qty": 1, "swap": self.why}
                    for row in asked["наміри"]
                ]
            },
            text="",
            model=self.model,
            usage=Usage(1, 1),
            duration_ms=1,
        )


async def test_an_answer_by_chip_is_not_a_dead_end_when_the_agent_declines(stand):
    plan = await _plan(stand)
    wanted = plan.basket.postponed[0].intent

    filled = await refill(
        stand,
        _DecliningLLM("інша фасовка цього виду"),
        plan,
        RefillRequest.model_validate({"answers": [{"intent": wanted, "query": f"{wanted} вужче"}]}),
        now=NOW,
    )

    added = filled.lines[-1]
    assert added.product["name"] == f"Вужчий {wanted}", "рядок зібрано з того, що назвав ГІСТЬ"
    assert wanted not in [item.intent for item in filled.basket.postponed]


async def test_a_picked_product_is_added_without_the_model(stand):
    plan = await _plan(stand)
    card = {
        "externalProductId": "9001",
        "name": "Томат Гордій Черрі",
        "price": Decimal("71.99"),
        "displayRatio": "250г",
        "stock": 12,
        "available": True,
        "step": 1,
        "weighted": False,
    }
    plan.swap_cards["9001"] = card
    before = len(plan.lines)

    filled = await pick_answer(plan, intent="томат черрі", article="9001")

    assert len(filled.lines) == before + 1
    added = filled.lines[-1]
    assert added.product["name"] == "Томат Гордій Черрі"
    assert filled.basket.total != plan.basket.total


async def test_an_answered_question_disappears_from_the_screen(stand):
    from komora.api.schemas import Clarification

    plan = await _plan(stand)
    plan.basket.questions = [
        Clarification(intent="томат черрі", question="який саме?"),
        Clarification(intent="молоко", question="яке саме?"),
    ]
    plan.swap_cards["9001"] = {
        "externalProductId": "9001",
        "name": "Томат Гордій Черрі",
        "price": Decimal("71.99"),
        "displayRatio": "250г",
        "stock": 12,
        "available": True,
        "step": 1,
        "weighted": False,
    }

    filled = await pick_answer(plan, intent="томат черрі", article="9001")

    assert [q.intent for q in filled.basket.questions] == ["молоко"]


async def test_a_pick_the_server_never_showed_is_refused(stand):
    plan = await _plan(stand)
    with pytest.raises(RefillError, match="не в пам'яті"):
        await pick_answer(plan, intent="томат", article="немає-такого")


async def test_a_pick_already_in_the_basket_closes_the_question_instead_of_failing(stand):
    plan = await _plan(stand)
    line = plan.lines[0]
    article = str(line.product["externalProductId"])
    plan.swap_cards[article] = line.product
    before = [(str(row.product["externalProductId"]), row.qty) for row in plan.lines]
    other = next(row.intent for row in plan.lines if row.intent != line.intent)
    plan.basket.questions = [
        Clarification(intent=line.intent, question="Які саме?"),
        Clarification(intent=other, question="А ці які?"),
    ]

    filled = await pick_answer(plan, intent=line.intent, article=article)

    assert [(str(row.product["externalProductId"]), row.qty) for row in filled.lines] == before
    assert [q.intent for q in filled.basket.questions] == [other]


async def test_a_cheaper_line_replaces_the_old_one_and_does_not_double_it(stand):
    plan = await _plan(stand)
    line = plan.lines[0]
    article = str(line.product["externalProductId"])
    plan.swap_cards["9002"] = {
        "externalProductId": "9002",
        "name": "Дешевший того ж виду",
        "price": Decimal("19.99"),
        "displayRatio": "250г",
        "stock": 8,
        "available": True,
        "step": 1,
        "weighted": False,
    }
    before = len(plan.lines)

    swapped = take_cheaper(plan, article=article, to="9002")

    assert len(swapped.lines) == before, "рядок замінено, а не додано"
    assert all(str(item.product["externalProductId"]) != article for item in swapped.lines), (
        "старого рядка більше немає"
    )
    assert any(item.product["name"] == "Дешевший того ж виду" for item in swapped.lines)
    assert swapped.basket.total != plan.basket.total, "сума перерахована"
    step = next(s for s in swapped.basket.trace if s.id == "step-cheaper")
    assert step.decision is not None and step.decision.startswith("замінено на дешевше")
    assert "докинуто" not in step.decision
    assert step.tag != "+1 поз."


async def test_a_cheaper_swap_keeps_the_terms_the_guest_set(stand):
    plan = await _plan(stand, autoSwap=True)
    article = str(plan.lines[0].product["externalProductId"])
    plan.swap_cards["9002"] = {
        "externalProductId": "9002",
        "name": "Дешевший того ж виду",
        "price": Decimal("19.99"),
        "displayRatio": "250г",
        "stock": 1,
        "available": True,
        "step": 1,
        "weighted": False,
    }

    swapped = take_cheaper(plan, article=article, to="9002", now=NOW)

    (added,) = [line for line in swapped.lines if line.product["externalProductId"] == "9002"]
    assert added.swap_fork is not None, "згода гостя доїхала: межі, а не питання"
    assert (added.swap_fork.low, added.swap_fork.high) == (Decimal("17.99"), Decimal("21.99"))
    assert not added.needs_approval


async def test_a_picked_product_keeps_the_terms_the_guest_set(stand):
    plan = await _plan(stand, autoSwap=True)
    plan.swap_cards["9001"] = {
        "externalProductId": "9001",
        "name": "Томат Гордій Черрі",
        "price": Decimal("71.99"),
        "displayRatio": "250г",
        "stock": 1,
        "available": True,
        "step": 1,
        "weighted": False,
    }

    filled = await pick_answer(plan, intent="томат черрі", article="9001", now=NOW)

    added = filled.lines[-1]
    assert added.swap_fork is not None, "згода гостя доїхала і сюди"
    assert (added.swap_fork.low, added.swap_fork.high) == (Decimal("64.79"), Decimal("79.19"))
    assert not added.needs_approval


async def test_a_cheaper_swap_into_a_line_that_is_gone_is_a_refusal(stand):
    plan = await _plan(stand)
    plan.swap_cards["9002"] = {"externalProductId": "9002", "name": "будь-що", "price": 1}

    with pytest.raises(RefillError, match="цього рядка"):
        take_cheaper(plan, article="немає-такого", to="9002")


async def test_a_cheaper_swap_without_a_card_says_so(stand):
    plan = await _plan(stand)
    article = str(plan.lines[0].product["externalProductId"])

    with pytest.raises(RefillError, match="пам'яті сервера"):
        take_cheaper(plan, article=article, to="9002")


async def test_an_answered_question_is_refilled_and_disappears(stand):
    plan = await _plan(stand)
    wanted = plan.basket.postponed[0].intent

    filled = await refill(
        stand,
        None,
        plan,
        RefillRequest.model_validate({"answers": [{"intent": wanted}]}),
        now=NOW,
    )

    assert wanted in {line.intent for line in filled.lines}, "намір доїхав у кошик"
    assert len(filled.lines) == len(plan.lines) + 1, "докинуто рівно один рядок"


async def test_the_answered_question_leaves_the_screen(stand):
    plan = await _plan(stand)
    wanted = plan.basket.postponed[0].intent
    plan.basket.questions = [
        Clarification(intent=wanted, question="Який саме?", options=[], picks=[])
    ]

    filled = await refill(
        stand,
        None,
        plan,
        RefillRequest.model_validate({"answers": [{"intent": wanted}]}),
        now=NOW,
    )

    assert filled.basket.questions == []


async def test_a_chip_without_a_node_narrows_the_set_not_just_the_word(stand):
    plan = await _plan(stand)
    wanted = plan.basket.postponed[0].intent

    filled = await refill(
        stand,
        None,
        plan,
        RefillRequest.model_validate({"answers": [{"intent": wanted, "query": f"{wanted} вужче"}]}),
        now=NOW,
    )

    line = next(line for line in filled.lines if line.intent == wanted)
    assert line.product["name"] == f"Вужчий {wanted}"
    step = next(s for s in filled.basket.trace if s.id == "step-refill-answer")
    assert "звужено фразою у 1 з 1" in step.result_summary


async def test_an_empty_shelf_under_the_phrase_keeps_the_set_that_was(stand):
    plan = await _plan(stand)
    wanted = plan.basket.postponed[0].intent

    filled = await refill(
        stand,
        None,
        plan,
        RefillRequest.model_validate({"answers": [{"intent": wanted, "query": "шафран"}]}),
        now=NOW,
    )

    line = next(line for line in filled.lines if line.intent == wanted)
    assert line.product["name"] == wanted
    step = next(s for s in filled.basket.trace if s.id == "step-refill-answer")
    assert "звужено фразою у 0 з 1" in step.result_summary


async def test_the_answer_names_itself_in_the_trace(stand):
    plan = await _plan(stand)
    wanted = plan.basket.postponed[0].intent

    filled = await refill(
        stand,
        None,
        plan,
        RefillRequest.model_validate({"answers": [{"intent": wanted, "text": "тільки без цукру"}]}),
        now=NOW,
    )

    step = next(s for s in filled.basket.trace if s.id == "step-refill-answer")
    assert "гість уточнив: 1 намір" in step.result_summary
    assert "тільки без цукру" in step.args["слова"].values()


async def test_the_refill_picks_on_the_guests_rules(stand):
    asked: list[str] = []

    class _Namer:
        model = "fake"

        async def decide(self, *, system, user, schema, **_):
            from komora.agent.llm import Decision, Usage

            asked.append(user)
            return Decision(
                data={"picks": []}, text="", model=self.model, usage=Usage(1, 1), duration_ms=1
            )

    plan = await _plan(stand, rules=["без лактози"])

    await refill(stand, _Namer(), plan, RefillRequest(), now=NOW)

    assert any("без лактози" in body for body in asked), (
        "добір ходить у модель тими самими умовами, що й збірка"
    )


async def test_the_refill_counts_the_slot_and_the_auto_swap_of_its_own_run(stand):
    plan = await _plan(stand, autoSwap=True, autoSwapPercent=15)

    filled = await refill(stand, None, plan, RefillRequest(), now=NOW)

    added = filled.lines[len(plan.lines) :]
    assert added, "передумова: добір щось докинув"
    assert not any(line.needs_approval and line.risky for line in added), (
        "згода на авто-заміну не доїхала до добраних рядків"
    )


async def test_a_remembered_history_spares_the_reread_on_the_same_branch(stand):
    plan = await _plan(stand)
    history, count, _, _, _ = await load_history(stand, plan.slot, plan.branch_id, now=NOW)
    seen = Receipts(slot=plan.slot, branch_id=plan.branch_id, history=history, count=count)

    fresh = await refill(stand, None, plan, RefillRequest(), now=NOW)
    warm = await refill(stand, None, plan, RefillRequest(), now=NOW, receipts=seen)

    assert [line.intent for line in warm.lines] == [line.intent for line in fresh.lines]
    assert warm.basket.stats.mcp_calls < fresh.basket.stats.mcp_calls
    step = next(s for s in warm.basket.trace if s.id == "step-refill-history")
    assert step.result_summary == f"{count} чеків з пам'яті сесії — правка не перечитує історію"
    assert step.duration_ms == 0
    assert step.args["з пам'яті сесії"] is True
    assert step.tool == "api.history", "крок без походу не рахується походом"

    elsewhere = Receipts(slot=plan.slot, branch_id="інша-філія", history=[], count=0)
    reread = await refill(stand, None, plan, RefillRequest(), now=NOW, receipts=elsewhere)
    assert [line.intent for line in reread.lines] == [line.intent for line in fresh.lines]
    assert reread.basket.stats.mcp_calls == fresh.basket.stats.mcp_calls
    step = next(s for s in reread.basket.trace if s.id == "step-refill-history")
    assert step.result_summary == f"{count} чеків перечитано під добір — ціни й залишки з них свіжі"
    assert step.args["з пам'яті сесії"] is False
    assert step.tool == "silpo_get_my_offline_orders"


async def test_the_endpoint_hands_the_remembered_history_to_the_refill(stand, monkeypatch):
    runs.forget_all()
    history_memory.forget_all()
    monkeypatch.setattr(api, "SilpoMCP", lambda **kwargs: stand)
    first = runs.remember(await _plan(stand), owner=GUEST.owner)
    handed: dict[str, Any] = {}

    async def spy(mcp, llm, run, request, **kwargs):
        handed.update(kwargs)
        return run

    monkeypatch.setattr(api, "refill", spy)
    await api.refill_basket(first.run_id, RefillRequest(), GUEST, None)
    assert handed["receipts"] is None, "нічого не читали — добір читає сам"

    seen = Receipts(slot={}, branch_id=None, history=[], count=0)
    history_memory.remember(seen, owner=GUEST.owner)
    await api.refill_basket(first.run_id, RefillRequest(), GUEST, None)
    assert handed["receipts"] is seen


async def test_an_answer_does_not_push_the_basket_over_the_corridor(stand):
    plan = await _plan(stand)
    card = {
        "externalProductId": "9001",
        "name": "Томат Гордій Черрі",
        "price": Decimal("71.99"),
        "displayRatio": "250г",
        "stock": 12,
        "available": True,
        "step": 1,
        "weighted": False,
    }
    plan.swap_cards["9001"] = card
    budget = (plan.basket.total - 1) / Decimal("1.1")
    plan = replace(
        plan,
        basket=plan.basket.model_copy(update={"budget": budget}),
        fill_intents=tuple(line.intent for line in plan.lines),
    )
    high = budget_band(budget).high

    filled = await pick_answer(plan, intent="томат черрі", article="9001")

    assert any(line.product["externalProductId"] == "9001" for line in filled.lines), (
        "відповідь гостя не ріжеться"
    )
    assert filled.basket.total <= high
    assert len(filled.lines) < len(plan.lines) + 1, "наш добір знято"
    step = next(s for s in reversed(filled.basket.trace) if s.id == "step-refill")
    assert step.args["знято під межу"], "зняте називає себе"
    assert "під межу знято наш добір" in step.result_summary


class _TableLLM:

    model = "fake-model"

    def __init__(self, add: list[str]) -> None:
        self.add = add
        self.prompts: list[str] = []
        self.payloads: list[dict] = []

    async def decide(self, *, system, user, schema, prompt="", max_tokens=2048, **_):
        from komora.agent.llm import Decision, Usage

        self.prompts.append(prompt)
        self.payloads.append(json.loads(user))
        data = (
            {"add": [{"intent": name, "why": "до столу"} for name in self.add]}
            if prompt.startswith("table")
            else {"picks": []}
        )
        return Decision(data=data, text="", model=self.model, usage=Usage(1, 1), duration_ms=1)


async def test_an_event_below_the_corridor_is_topped_up_to_the_table(stand):
    plan = await _plan(stand, mode="event", occasionPeople=4, budget=3000)
    assert Decimal(str(plan.basket.total)) < budget_band(Decimal(3000)).low
    before = {line.product["name"] for line in plan.lines}
    llm = _TableLLM(["Товар 7", "Товар 8"])

    filled = await top_up_table(stand, llm, plan, occasion_of("event", 4), now=NOW)

    step = next(s for s in filled.basket.trace if s.id == "step-table")
    assert step.args["докинути"] == ["Товар 7", "Товар 8"]
    assert llm.payloads[0]["бракує_грн"] and llm.payloads[0]["у_кошику"]
    names = {line.product["name"] for line in filled.lines}
    assert {"Товар 7", "Товар 8"} <= names and before <= names
    assert Decimal(str(filled.basket.total)) <= Decimal(3000)
    refill_step = next(s for s in filled.basket.trace if s.id == "step-refill")
    assert refill_step.result_summary.startswith("до столу: ")


async def test_the_table_top_up_is_cut_under_the_named_sum_from_the_tail(stand):
    plan = await _plan(stand, mode="event", occasionPeople=4, budget=3000)
    total = Decimal(str(plan.basket.total))
    named = (total + 100).quantize(Decimal("1"))
    assert total < budget_band(named).low, "стенд: кошик нижчий за коридор"
    plan = replace(plan, basket=plan.basket.model_copy(update={"budget": named}))

    filled = await top_up_table(
        stand, _TableLLM(["Товар 7", "Товар 8"]), plan, occasion_of("event", 4), now=NOW
    )

    names = [line.product["name"] for line in filled.lines]
    assert "Товар 7" in names and "Товар 8" not in names
    assert Decimal(str(filled.basket.total)) <= named
    refill_step = next(s for s in filled.basket.trace if s.id == "step-refill")
    assert refill_step.args["знято під межу"] == ["Товар 8"]


async def test_the_table_top_up_stays_out_of_the_week_and_out_of_a_full_basket(stand):
    plan = await _plan(stand, mode="week", budget=3000)
    same = await top_up_table(stand, _TableLLM(["Товар 7"]), plan, occasion_of("week", None))
    assert same is plan
    full = await _plan(stand, mode="event", occasionPeople=4, budget=300)
    assert Decimal(str(full.basket.total)) >= budget_band(Decimal(300)).low
    llm = _TableLLM(["Товар 7"])
    assert await top_up_table(stand, llm, full, occasion_of("event", 4)) is full
    assert llm.prompts == [], "модель не питається, коли столу досить"


async def test_the_table_is_topped_up_by_the_real_silpo_sum_after_the_write(stand):
    plan = await _plan(stand, mode="event", occasionPeople=4, budget=3000)
    total = Decimal(str(plan.basket.total))
    plan = replace(plan, basket=plan.basket.model_copy(update={"budget": total}))
    paid = (total * Decimal("0.8")).quantize(Decimal("0.01"))
    llm = _TableLLM(["Товар 7"])

    filled = await top_up_table(stand, llm, plan, occasion_of("event", 4), now=NOW, paid=paid)

    assert any(line.product["name"] == "Товар 7" for line in filled.lines)
    assert Decimal(str(filled.basket.budget)) == total, "названа сума лишилась словом гостя"
    step = next(s for s in filled.basket.trace if s.id == "step-table")
    assert Decimal(step.args["бракує_грн"]) > 0
    assert sum(1 for prompt in llm.prompts if prompt.startswith("table")) == 1, "один прохід"
    untouched = await top_up_table(
        stand, _TableLLM(["Товар 8"]), plan, occasion_of("event", 4), paid=total
    )
    assert untouched is plan, "до оплати в коридорі -- докидати нема чого"


async def test_a_second_pass_does_not_double_declined_or_unresolved_names(stand):
    plan = await _plan(stand, mode="event", occasionPeople=4, budget=3000)
    first = await top_up_table(stand, _TableLLM(["шафран"]), plan, occasion_of("event", 4), now=NOW)
    assert first.basket.unresolved.count("шафран") == 1
    again = await top_up_table(
        stand, _TableLLM(["шафран", "Товар 7"]), first, occasion_of("event", 4), now=NOW
    )
    assert again.basket.unresolved.count("шафран") == 1, "повтор не подвоює «не знайшлось»"
    assert any(line.product["name"] == "Товар 7" for line in again.lines)


async def test_two_intents_on_the_same_product_make_one_line_in_the_refill(stand):
    plan = await _plan(stand)
    filled = await refill(stand, None, plan, RefillRequest(intents=["Товар 8", "останнє"]), now=NOW)
    ids = [str(line.product["externalProductId"]) for line in filled.lines]
    assert ids.count("308") == 1
    assert len(ids) == len(set(ids))
    step = next(s for s in reversed(filled.basket.trace) if s.id == "step-refill")
    assert step.args["злито"] == ["Товар 8 (2)"]
