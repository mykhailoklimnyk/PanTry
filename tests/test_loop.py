from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from komora.agent.basket import LOOP_PICK, assemble_list
from komora.agent.llm import Decision, ModelError, Usage
from komora.agent.loop import (
    ARGUMENTS_NOTE,
    FALLBACK_NOTE,
    LOOP_SCHEMA,
    LOOP_STEPS,
    REPEAT_WARNING,
    resolve_one,
    tools_note,
)
from komora.api.schemas import BuildRequest
from komora.core.instructions import Verdict, fingerprint
from komora.core.plan import PLAN_SCHEMA
from komora.mcp.client import SilpoMCP

ROOT = Path(__file__).resolve().parents[1]

NOW = datetime(2026, 9, 3, tzinfo=UTC)


def _card(pid: int, name: str, price: float = 50.0) -> dict:
    return {
        "id": f"00000000-0000-4000-8000-{pid:012d}",
        "name": name,
        "slug": f"slug-{pid}",
        "price": price,
        "oldPrice": None,
        "stock": 30,
        "available": True,
        "image": None,
        "weighted": False,
        "step": 1,
        "displayRatio": "1шт",
        "companyId": "00000000-0000-4000-8000-000000000001",
        "branchId": "00000000-0000-4000-8000-000000000002",
        "externalProductId": pid,
    }


class _Script:

    model = "fake-loop"

    def __init__(self, *answers: object) -> None:
        self.answers = list(answers)
        self.users: list[dict] = []
        self.systems: list[str] = []

    async def decide(self, *, system, user, schema, schema_name="decision", max_tokens=2048, **_):
        assert schema is LOOP_SCHEMA
        self.users.append(json.loads(user))
        self.systems.append(system)
        answer = (
            self.answers.pop(0)
            if self.answers
            else {"finish": "give_up", "give_up": "сценарій вичерпано"}
        )
        if isinstance(answer, Exception):
            raise answer
        return Decision(
            data=answer,
            text=json.dumps(answer),
            model=self.model,
            usage=Usage(20, 10),
            duration_ms=1,
        )


def _shelf(*cards: dict):
    async def search(queries: list[str]) -> dict[str, list[dict]]:
        return {
            q: [
                c
                for c in cards
                if q.casefold() in str(c["name"]).casefold() or q == str(c["externalProductId"])
            ]
            for q in queries
        }

    return search


async def _no_similar(slug: str) -> list[dict]:
    return []


@pytest.mark.anyio
async def test_a_search_step_then_a_choice_from_what_was_seen():
    llm = _Script(
        {"tool": "silpo_find_products_batch", "arguments": {"products": ["795319"]}},
        {"finish": "pick", "chosen_id": "795319", "why": "це твій артикул"},
    )
    loop = await resolve_one(
        llm,
        "Паляничка сирна",
        seen=[],
        own=[{"lagerId": "795319", "назва": "Паляничка сирна 100г", "чеків": 4}],
        tried=["Паляничка сирна"],
        search=_shelf(_card(795319, "Паляничка сирна 100г")),
        similar=_no_similar,
    )
    assert loop.found and loop.chosen["externalProductId"] == 795319
    assert loop.steps == 2 and loop.tokens == 60
    assert loop.calls == ["пошук 795319: +1"]
    assert "за 2 кроки" in loop.phrase()
    assert llm.users[1]["кандидати"][0]["id"] == "795319"


@pytest.mark.anyio
async def test_the_shelf_answer_reaches_the_next_step_as_text():
    llm = _Script(
        {"tool": "silpo_find_products_batch", "arguments": {"products": ["паляниця"]}},
        {"finish": "pick", "chosen_id": "707", "why": "той самий вид"},
    )
    loop = await resolve_one(
        llm,
        "Паляничка сирна",
        seen=[],
        own=[],
        tried=["Паляничка сирна"],
        search=_shelf(_card(707, "Паляниця Київхліб"), _card(708, "Паляниця Цар-Хліб")),
        similar=_no_similar,
    )
    assert loop.found
    assert llm.users[0]["фідбек"] == []
    assert llm.users[1]["фідбек"] == [
        "пошук: «паляниця»: +2, перші: Паляниця Київхліб, Паляниця Цар-Хліб"
    ]
    assert loop.turns[0].endswith("→ далі")
    assert "Паляниця Київхліб" in loop.turns[0]
    assert loop.turns[1] == "вибір 707 → Паляниця Київхліб → обрано"
    assert "1) пошук →" in loop.summary() and "2) вибір 707" in loop.summary()


@pytest.mark.anyio
async def test_an_empty_search_does_not_end_the_loop_and_says_zero_out_loud():
    llm = _Script(
        {"tool": "silpo_find_products_batch", "arguments": {"products": ["лопатка свиняча"]}},
        {"tool": "silpo_find_products_batch", "arguments": {"products": ["свинина"]}},
        {"finish": "pick", "chosen_id": "5", "why": "єдина свинина на полиці"},
    )
    loop = await resolve_one(
        llm,
        "Свинина лопатка",
        seen=[],
        own=[],
        tried=["Свинина лопатка"],
        search=_shelf(_card(5, "Свинина охолоджена")),
        similar=_no_similar,
    )
    assert loop.found and loop.steps == 3
    assert llm.users[1]["фідбек"] == ["пошук: «лопатка свиняча»: 0 товарів"]
    assert llm.users[2]["фідбек"][1].startswith("пошук: «свинина»: +1, перші: Свинина охолоджена")


@pytest.mark.anyio
async def test_a_foreign_article_is_feedback_and_the_loop_goes_on():
    llm = _Script(
        {"finish": "pick", "chosen_id": "999"},
        {"finish": "give_up", "give_up": "нічого схожого"},
    )
    loop = await resolve_one(
        llm,
        "Сендвіч",
        seen=[_card(1, "Сендвіч з куркою")],
        own=[],
        tried=["Сендвіч"],
        search=_shelf(),
        similar=_no_similar,
    )
    assert not loop.found and loop.gave_up == "нічого схожого"
    assert loop.steps == 2
    assert llm.users[1]["фідбек"] == [
        "вибір 999: цього артикула немає серед кандидатів; обирай лише з поля «кандидати»"
    ]


@pytest.mark.anyio
async def test_the_step_ceiling_ends_the_loop_out_loud():
    llm = _Script(
        *[
            {"tool": "silpo_find_products_batch", "arguments": {"products": [f"слово {i}"]}}
            for i in range(9)
        ]
    )
    loop = await resolve_one(
        llm, "Щось", seen=[], own=[], tried=[], search=_shelf(), similar=_no_similar
    )
    assert loop.steps == LOOP_STEPS
    assert loop.gave_up == f"стеля {LOOP_STEPS} кроків"


@pytest.mark.anyio
async def test_a_repeat_warns_first_and_stops_second():
    llm = _Script(
        {"tool": "silpo_find_products_batch", "arguments": {"products": ["Сендвіч"]}},
        {"tool": "silpo_find_products_batch", "arguments": {"products": ["  СЕНДВІЧ "]}},
    )
    loop = await resolve_one(
        llm, "Сендвіч", seen=[], own=[], tried=["Сендвіч"], search=_shelf(), similar=_no_similar
    )
    assert loop.gave_up == "повтор запиту"
    assert loop.steps == 2
    assert llm.users[1]["попередження"] == REPEAT_WARNING
    assert llm.users[1]["фідбек"] == [f"пошук «Сендвіч»: це вже пробували. {REPEAT_WARNING}"]
    assert loop.turns[-1].endswith("→ стоп")


@pytest.mark.anyio
async def test_a_foreign_tool_is_feedback_not_the_end():
    llm = _Script(
        {"tool": "silpo_clear_shopping_cart", "arguments": {}},
        {"finish": "give_up", "give_up": "більше нема чим шукати"},
    )
    loop = await resolve_one(
        llm, "Сендвіч", seen=[], own=[], tried=[], search=_shelf(), similar=_no_similar
    )
    assert loop.gave_up == "більше нема чим шукати" and loop.steps == 2
    assert "не з переліку" in llm.users[1]["фідбек"][0]
    assert "silpo_find_products_batch" in llm.users[1]["фідбек"][0]


@pytest.mark.anyio
async def test_only_finish_ends_the_loop_and_it_says_which_field_is_missing():
    llm = _Script(
        {"chosen_id": "1", "why": "схоже"},
        {"give_up": "та ну його"},
        {"finish": "pick", "chosen_id": "1", "why": "схоже"},
    )
    loop = await resolve_one(
        llm,
        "Сендвіч",
        seen=[_card(1, "Сендвіч з куркою")],
        own=[],
        tried=[],
        search=_shelf(),
        similar=_no_similar,
    )
    assert loop.found and loop.steps == 3
    assert llm.users[1]["фідбек"] == ["вибір 1: щоб обрати, постав finish=pick"]
    assert llm.users[2]["фідбек"][1] == "відмова: щоб відмовитись, постав finish=give_up"


@pytest.mark.anyio
async def test_finish_pick_without_an_article_burns_the_step_too():
    llm = _Script(
        {"finish": "pick"},
        {"finish": "give_up", "give_up": "нема чого брати"},
    )
    loop = await resolve_one(
        llm, "Сендвіч", seen=[], own=[], tried=[], search=_shelf(), similar=_no_similar
    )
    assert loop.gave_up == "нема чого брати"
    assert llm.users[1]["фідбек"] == ["вибір: finish=pick без chosen_id: назви артикул кандидата"]


@pytest.mark.anyio
async def test_finish_give_up_without_a_reason_still_names_itself():
    llm = _Script({"finish": "give_up"})
    loop = await resolve_one(
        llm, "Сендвіч", seen=[], own=[], tried=[], search=_shelf(), similar=_no_similar
    )
    assert loop.gave_up == "без причини" and loop.steps == 1
    assert loop.turns == ["відмова → без причини → стоп"]


@pytest.mark.anyio
async def test_similar_products_are_asked_only_for_a_seen_candidate():
    async def similar(slug: str) -> list[dict]:
        assert slug == "slug-1"
        return [_card(2, "Сендвіч з баликом")]

    llm = _Script(
        {"tool": "silpo_get_similar_products", "arguments": {"slug": "slug-1"}},
        {"finish": "pick", "chosen_id": "2", "why": "той самий вид"},
    )
    loop = await resolve_one(
        llm,
        "Сендвіч",
        seen=[_card(1, "Сендвіч з куркою")],
        own=[],
        tried=[],
        search=_shelf(),
        similar=similar,
    )
    assert loop.found and loop.chosen["externalProductId"] == 2
    assert loop.calls == ["схожі до slug-1: +1"]

    llm = _Script(
        {"tool": "silpo_get_similar_products", "arguments": {"slug": "slug-77"}},
        {"finish": "give_up", "give_up": "не знайшлось"},
    )
    loop = await resolve_one(
        llm,
        "Сендвіч",
        seen=[_card(1, "Сендвіч з куркою")],
        own=[],
        tried=[],
        search=_shelf(),
        similar=similar,
    )
    assert loop.gave_up == "не знайшлось" and loop.steps == 2
    assert llm.users[1]["фідбек"] == [
        "схожі до slug-77: такого кандидата не було; slug бери з поля «кандидати»"
    ]


@pytest.mark.anyio
async def test_the_same_slug_twice_is_a_repeat_too():
    async def similar(slug: str) -> list[dict]:
        return []

    llm = _Script(
        {"tool": "silpo_get_similar_products", "arguments": {"slug": "slug-1"}},
        {"tool": "silpo_get_similar_products", "arguments": {"slug": "slug-1"}},
        {"tool": "silpo_get_similar_products", "arguments": {"slug": "slug-1"}},
    )
    loop = await resolve_one(
        llm,
        "Сендвіч",
        seen=[_card(1, "Сендвіч з куркою")],
        own=[],
        tried=[],
        search=_shelf(),
        similar=similar,
    )
    assert loop.gave_up == "повтор запиту" and loop.steps == 3
    assert loop.calls == ["схожі до slug-1: +0"]


@pytest.mark.anyio
async def test_a_shelf_answer_of_known_cards_is_not_silence():

    async def similar(slug: str) -> list[dict]:
        return [_card(1, "Сендвіч з куркою")]

    llm = _Script(
        {"tool": "silpo_get_similar_products", "arguments": {"slug": "slug-1"}},
        {"finish": "give_up", "give_up": "нічого нового"},
    )
    await resolve_one(
        llm,
        "Сендвіч",
        seen=[_card(1, "Сендвіч з куркою")],
        own=[],
        tried=[],
        search=_shelf(),
        similar=similar,
    )
    assert llm.users[1]["фідбек"] == [
        "схожі до slug-1: 0 товарів (усе вже серед кандидатів: Сендвіч з куркою)"
    ]


@pytest.mark.anyio
async def test_a_silent_model_ends_the_loop_with_the_error_named():
    llm = _Script(ModelError("mantle: 503"))
    loop = await resolve_one(
        llm, "Сендвіч", seen=[], own=[], tried=[], search=_shelf(), similar=_no_similar
    )
    assert loop.gave_up is not None and loop.gave_up.startswith("модель не відповіла (mantle: 503)")


def test_live_descriptions_win_and_the_fallback_names_itself():
    judged = [
        Verdict(
            "silpo_find_products_batch",
            fingerprint("Шукайте lagerId числом."),
            "code",
            "виконує код",
        )
    ]
    text, source = tools_note(
        [
            {"name": "silpo_find_products_batch", "description": "  Шукайте   lagerId числом.  "},
            {"name": "silpo_clear_shopping_cart", "description": "не для петлі"},
        ],
        verdicts=judged,
    )
    assert source == "живі описи"
    assert "- silpo_find_products_batch: Шукайте lagerId числом." in text
    assert "silpo_clear_shopping_cart" not in text
    assert ARGUMENTS_NOTE in text

    assert tools_note([]) == (FALLBACK_NOTE, "запасний текст")
    assert tools_note([{"name": "silpo_find_products_batch", "description": ""}]) == (
        FALLBACK_NOTE,
        "запасний текст",
    )


def test_an_unjudged_description_falls_back_instead_of_going_to_the_model():
    text, source = tools_note(
        [{"name": "silpo_get_similar_products", "description": "NEW: щойно дописали."}]
    )
    assert (text, source) == (FALLBACK_NOTE, "запасний текст")


def test_the_real_register_feeds_the_loop_prompt():
    tools = json.loads((ROOT / "docs" / "mcp-tools.json").read_text(encoding="utf-8"))
    text, source = tools_note(tools)
    assert source == "живі описи"
    assert "- silpo_get_similar_products: " in text
    assert "silpo_get_time_slots" not in text


@pytest.mark.anyio
async def test_the_note_reaches_the_model_and_the_default_is_the_fallback():
    llm = _Script({"finish": "give_up", "give_up": "все"})
    await resolve_one(
        llm, "Сендвіч", seen=[], own=[], tried=[], search=_shelf(), similar=_no_similar
    )
    assert FALLBACK_NOTE in llm.systems[0]

    llm = _Script({"finish": "give_up", "give_up": "все"})
    await resolve_one(
        llm,
        "Сендвіч",
        seen=[],
        own=[],
        tried=[],
        search=_shelf(),
        similar=_no_similar,
        note="ЖИВИЙ ОПИС",
    )
    assert "ЖИВИЙ ОПИС" in llm.systems[0] and FALLBACK_NOTE not in llm.systems[0]


SLOT = {
    "start": "2026-09-03T11:30:00+00:00",
    "end": "2026-09-03T13:00:00+00:00",
    "available": True,
    "deliveryType": "DeliveryHome",
    "deliveryCost": 89,
    "deliveryCostMap": [{"cost": 59, "fromOrderCost": 1199}],
    "minOrderCost": 599,
    "maxWeight": 50,
}
MILK = "Молоко Ферма 2,5%"
PALIANYCHKA = "Паляничка"


class _Agent:

    model = "fake-agent"

    def __init__(self, loop_answers: list[dict]) -> None:
        self.loop_answers = list(loop_answers)

    async def decide(self, *, system, user, schema, schema_name="decision", max_tokens=2048, **_):
        if schema is PLAN_SCHEMA:
            data = {
                "steps": [
                    {"step": name}
                    for name in (
                        "history.receipts",
                        "history.model",
                        "intents.compose",
                        "shelf.search",
                        "decide.pick",
                        "decide.chain",
                        "decide.loop",
                        "economy.settle",
                    )
                ]
            }
        elif schema is LOOP_SCHEMA:
            data = self.loop_answers.pop(0) if self.loop_answers else {"give_up": "кінець"}
        else:
            raise ModelError("мовчу")
        return Decision(
            data=data, text=json.dumps(data), model=self.model, usage=Usage(5, 5), duration_ms=1
        )


def _stand(tmp_path, *, shelf: dict[str, list[dict]]) -> SilpoMCP:
    def bought(days_ago: int, lager: int, name: str) -> dict:
        return {
            "createdAt": (NOW - timedelta(days=days_ago)).strftime("%Y-%m-%d"),
            "products": [
                {"lagerId": lager, "name": name, "unit": "шт", "quantity": 1, "price": 50}
            ],
        }

    (tmp_path / "silpo_get_time_slots.json").write_text(
        json.dumps({"slots": [SLOT]}), encoding="utf-8"
    )
    (tmp_path / "silpo_get_my_offline_orders.json").write_text(
        json.dumps({"orders": [bought(day, 101, MILK) for day in (30, 23, 16, 9)]}),
        encoding="utf-8",
    )
    (tmp_path / "silpo_get_my_shopping_cart.json").write_text(
        json.dumps({"shoppingCartId": None}), encoding="utf-8"
    )
    (tmp_path / "silpo_find_products_batch.json").write_text(
        json.dumps({"queries": [{"query": q, "products": cards} for q, cards in shelf.items()]}),
        encoding="utf-8",
    )
    return SilpoMCP(fixtures_dir=tmp_path)


@pytest.mark.anyio
async def test_the_loop_rescues_a_guest_word_the_search_missed_and_names_itself(tmp_path):
    mcp = _stand(
        tmp_path,
        shelf={
            MILK: [_card(101, MILK, 53.49)],
            PALIANYCHKA: [],
            "паляничка сирна": [_card(707, "Паляничка сирна 100г", 29.0)],
        },
    )
    llm = _Agent(
        [
            {"tool": "silpo_find_products_batch", "arguments": {"products": ["паляничка сирна"]}},
            {"finish": "pick", "chosen_id": "707", "why": "та сама паляничка"},
        ]
    )
    request = BuildRequest.model_validate({"mode": "week", "shoppingList": [PALIANYCHKA]})
    assembled = await assemble_list(mcp, llm=llm, request=request, now=NOW)

    line = next(line for line in assembled.basket.lines if line.external_product_id == "707")
    assert (
        line.explanation_detail is not None
        and "агент дошукав за кілька кроків" in line.explanation_detail
    )
    assert PALIANYCHKA not in assembled.basket.unresolved
    step = next(s for s in assembled.basket.trace if s.id == "step-loop")
    assert step.tag == "+1"
    assert "дошукав 1 з 1 наміру за 2 кроки" in step.result_summary
    dialog = " ".join(step.args["діалог"])
    assert "«Паляничка» → Паляничка сирна 100г за 2 кроки" in dialog
    assert "«паляничка сирна»: +1, перші: Паляничка сирна 100г → далі" in dialog
    assert "2) вибір 707 → Паляничка сирна 100г → обрано" in dialog
    assert step.args["стеля"].startswith("3 намірів")
    assert step.args["описи"] == "запасний текст"


class _DecliningAgent(_Agent):

    def __init__(self, loop_answers: list[dict], *, intent: str, why: str) -> None:
        super().__init__(loop_answers)
        self.intent, self.why = intent, why

    async def decide(self, *, system, user, schema, schema_name="decision", max_tokens=2048, **_):
        if schema is not PLAN_SCHEMA and schema is not LOOP_SCHEMA:
            data = {"picks": [{"intent": self.intent, "chosen_id": "", "qty": 1, "swap": self.why}]}
            return Decision(
                data=data,
                text=json.dumps(data),
                model=self.model,
                usage=Usage(5, 5),
                duration_ms=1,
            )
        return await super().decide(
            system=system, user=user, schema=schema, schema_name=schema_name
        )


@pytest.mark.anyio
async def test_a_refusal_the_loop_rescued_leaves_the_declined_list(tmp_path):
    mcp = _stand(
        tmp_path,
        shelf={
            MILK: [_card(101, MILK, 53.49)],
            PALIANYCHKA: [_card(700, "Паляничка звичайна 500г", 40.0)],
            "паляничка сирна": [_card(707, "Паляничка сирна 100г", 29.0)],
        },
    )
    llm = _DecliningAgent(
        [
            {"tool": "silpo_find_products_batch", "arguments": {"products": ["паляничка сирна"]}},
            {"finish": "pick", "chosen_id": "707", "why": "та сама паляничка"},
        ],
        intent=PALIANYCHKA,
        why="500 г під намір «по 100 г» не підходить",
    )
    request = BuildRequest.model_validate({"shoppingList": [PALIANYCHKA]})
    assembled = await assemble_list(mcp, llm=llm, request=request, now=NOW)

    assert any(line.external_product_id == "707" for line in assembled.basket.lines)
    assert assembled.basket.declined == []
    assert PALIANYCHKA not in assembled.basket.unresolved
    step = next(s for s in assembled.basket.trace if s.id == "step-declined")
    assert step.args["відмов"] == 0


@pytest.mark.anyio
async def test_a_refusal_the_loop_could_not_rescue_keeps_its_reason(tmp_path):
    mcp = _stand(
        tmp_path,
        shelf={
            MILK: [_card(101, MILK, 53.49)],
            PALIANYCHKA: [_card(700, "Паляничка звичайна 500г", 40.0)],
        },
    )
    llm = _DecliningAgent(
        [{"finish": "give_up", "give_up": "іншої фасовки на полиці немає"}],
        intent=PALIANYCHKA,
        why="500 г під намір «по 100 г» не підходить",
    )
    request = BuildRequest.model_validate({"mode": "week", "shoppingList": [PALIANYCHKA]})
    assembled = await assemble_list(mcp, llm=llm, request=request, now=NOW)

    assert [(item.intent, item.why) for item in assembled.basket.declined] == [
        (PALIANYCHKA, "500 г під намір «по 100 г» не підходить")
    ]
    assert PALIANYCHKA not in assembled.basket.unresolved


@pytest.mark.anyio
async def test_when_the_loop_gives_up_the_word_stays_in_not_found_and_the_step_says_why(tmp_path):
    mcp = _stand(tmp_path, shelf={MILK: [_card(101, MILK, 53.49)], PALIANYCHKA: []})
    llm = _Agent([{"finish": "give_up", "give_up": "на полиці такого виду немає"}])
    request = BuildRequest.model_validate({"mode": "week", "shoppingList": [PALIANYCHKA]})
    assembled = await assemble_list(mcp, llm=llm, request=request, now=NOW)

    assert PALIANYCHKA in assembled.basket.unresolved
    step = next(s for s in assembled.basket.trace if s.id == "step-loop")
    assert step.tag == "не знайшлось"
    assert "дошукав 0 з 1 наміру" in step.result_summary
    assert any("відмова: на полиці такого виду немає" in said for said in step.args["діалог"])


@pytest.mark.anyio
async def test_without_the_step_in_the_plan_there_is_no_loop(tmp_path):
    mcp = _stand(tmp_path, shelf={MILK: [_card(101, MILK, 53.49)], PALIANYCHKA: []})

    class _NoLoop(_Agent):
        async def decide(self, *, system, user, schema, **kw):
            if schema is PLAN_SCHEMA:
                data = {
                    "steps": [
                        {"step": n}
                        for n in (
                            "history.receipts",
                            "history.model",
                            "intents.compose",
                            "shelf.search",
                            "decide.pick",
                            "economy.settle",
                        )
                    ]
                }
                return Decision(
                    data=data, text="", model=self.model, usage=Usage(1, 1), duration_ms=1
                )
            raise ModelError("мовчу")

    request = BuildRequest.model_validate({"mode": "week", "shoppingList": [PALIANYCHKA]})
    assembled = await assemble_list(mcp, llm=_NoLoop([]), request=request, now=NOW)
    assert all(s.id != "step-loop" for s in assembled.basket.trace)
    assert PALIANYCHKA in assembled.basket.unresolved
    assert LOOP_PICK == "петля"
