from __future__ import annotations

import json
from decimal import Decimal
from typing import Any

from komora.agent.basket import HistoryItem, agent_picks, history_matches
from komora.agent.llm import Decision, Usage
from komora.core.promo import Purchase


def _product(article: int, name: str, price: float, ratio: str, old: float | None = None) -> dict:
    return {
        "id": f"00000000-0000-4000-8000-{article:012d}",
        "name": name,
        "slug": f"slug-{article}",
        "price": price,
        "oldPrice": old,
        "stock": 30.0,
        "available": True,
        "image": None,
        "weighted": ratio == "100г",
        "step": 1,
        "displayRatio": ratio,
        "companyId": "00000000-0000-4000-8000-000000000001",
        "branchId": "00000000-0000-4000-8000-000000000002",
        "externalProductId": article,
    }


def _bought(times: int, paid: float, seen: float) -> list[Purchase]:
    return [
        Purchase(qty=Decimal(1), paid=Decimal(str(paid)), seen=Decimal(str(seen)))
        for _ in range(times)
    ]


OWN = HistoryItem(
    lager_id="32589",
    name="Томат",
    unit="кг",
    receipts=6,
    recent_receipts=3,
    qty_total=Decimal(6),
)

NEIGHBOUR = HistoryItem(
    lager_id="411223",
    name="Томат Гордій Черрі",
    unit="шт",
    receipts=6,
    recent_receipts=5,
    qty_total=Decimal(6),
    purchases=_bought(5, 59.99, 89.99) + _bought(1, 89.99, 89.99),
)

ASKED = HistoryItem(
    lager_id="778899",
    name="Томат Azura Черрі сливка",
    unit="шт",
    receipts=4,
    recent_receipts=4,
    qty_total=Decimal(4),
)

CANDIDATES = [
    _product(605375, "Томат черрі", 72.49, "250г"),
    _product(872222, "Томат Green Agro чорний", 82.49, "450г"),
    _product(32589, "Томат", 49.99, "100г"),
    _product(572755, "Томат мікс", 174.0, "100г"),
    _product(1022653, "Томат Green Agro сливка червоний", 68.52, "500г"),
    _product(455724, "Томат Есміра рожевий", 71.77, "100г", old=82.49),
]


class _Fake:

    def __init__(self) -> None:
        self.seen: dict[str, Any] = {}

    async def decide(self, *, system, user, schema, max_tokens, **_):
        self.seen = json.loads(user)
        return Decision(data={"picks": []}, text="", model="fake", usage=Usage(1, 1), duration_ms=1)


async def _prompt(history: list[HistoryItem]) -> dict[str, Any]:
    llm = _Fake()
    matches = history_matches("Томат", history)
    await agent_picks(
        llm,
        ["Томат"],
        {"Томат": CANDIDATES},
        {"Томат": matches} if matches else {},
        rules=[],
        owned={item.lager_id: item for item in history},
    )
    return llm.seen["наміри"][0]


async def test_the_guest_own_article_leads_the_candidates_and_names_itself():
    intent = await _prompt([OWN, NEIGHBOUR, ASKED])

    assert intent["кандидати"][0]["id"] == "32589", (
        "свій артикул гостя мусить стояти першим кандидатом"
    )
    assert "32589" in {str(hint["артикул"]) for hint in intent["з_історії"]}, (
        "«з_історії» мусить назвати артикул, за яким модель упізнає своє"
    )


async def test_a_neighbour_habit_brings_the_promo_condition_to_a_stranger():
    intent = await _prompt([OWN, NEIGHBOUR, ASKED])
    promo = {
        str(hint["артикул"]): hint for hint in intent["з_історії"] if hint.get("акційна_звичка")
    }
    shelf = {card["id"] for card in intent["кандидати"]}

    assert set(promo) == {"411223"}, "акційну звичку під цим наміром має лише сусідній вид"
    assert "411223" not in shelf, "а самого сусіднього артикула серед кандидатів немає"
    assert "32589" not in promo, "у свого вагового артикула акційної звички немає за побудовою"
    assert {card["id"] for card in intent["кандидати"] if card.get("стара_ціна")} == {"455724"}, (
        "знижка на полиці стоїть на ЧУЖОМУ товарі"
    )


async def test_a_fourth_kind_pushes_the_own_article_out_of_the_history_block():
    crowd = HistoryItem(
        lager_id="990001",
        name="Томат чері жовтий",
        unit="шт",
        receipts=5,
        recent_receipts=4,
        qty_total=Decimal(5),
    )
    intent = await _prompt([OWN, NEIGHBOUR, ASKED, crowd])

    assert "32589" not in {str(hint["артикул"]) for hint in intent["з_історії"]}
    assert intent["кандидати"][0]["id"] == "32589"
