from __future__ import annotations

from decimal import Decimal

from komora.agent.basket import HistoryItem, Tracer, build_lines
from komora.core.promo import Purchase

TOMATO = "Томат"
OWN_ID = "32589"
ESMIRA_ID = "455724"
ESMIRA = "Томат Есміра рожевий"


def _card(pid: str, name: str, price: float, *, old: float | None = None, weighed=False) -> dict:
    return {
        "id": f"00000000-0000-4000-8000-{int(pid):012d}",
        "name": name,
        "slug": f"slug-{pid}",
        "price": price,
        "oldPrice": old,
        "stock": 100,
        "available": True,
        "image": None,
        "weighted": weighed,
        "step": 0.25 if weighed else 1,
        "displayRatio": "100г" if weighed else "450г",
        "companyId": "00000000-0000-4000-8000-000000000001",
        "branchId": "00000000-0000-4000-8000-000000000002",
        "externalProductId": pid,
    }


def _own_card() -> dict:
    return _card(OWN_ID, TOMATO, 49.99, weighed=True)


def _esmira() -> dict:
    return _card(ESMIRA_ID, ESMIRA, 71.77, old=82.49)


def _item(
    lager: str,
    name: str,
    *,
    recent: int,
    total: int,
    unit: str = "кг",
    purchases: list[Purchase] | None = None,
) -> HistoryItem:
    return HistoryItem(
        lager_id=lager,
        name=name,
        unit=unit,
        receipts=total,
        qty_total=Decimal(total),
        recent_receipts=recent,
        qty_recent=Decimal(recent),
        purchases=purchases or [],
    )


def _mine(recent: int = 3, total: int = 6) -> dict[str, HistoryItem]:
    return {OWN_ID: _item(OWN_ID, TOMATO, recent=recent, total=total)}


def _built(
    *,
    options: list[dict] | None = None,
    owned: dict[str, HistoryItem] | None = None,
    hints: dict[str, HistoryItem] | None = None,
    pick: dict | None = None,
    auto: bool = True,
    rules_given: bool = False,
    intent: str = TOMATO,
) -> tuple[list, Tracer]:
    trace = Tracer()
    plan, _unresolved, _declined = build_lines(
        [intent],
        {intent: options if options is not None else [_own_card(), _esmira()]},
        hints or {},
        {intent: pick or {"intent": intent, "chosen_id": ESMIRA_ID, "qty": 1, "why": "акція"}},
        auto_intents=frozenset({intent} if auto else ()),
        owned=owned if owned is not None else _mine(),
        trace=trace,
        **({"rules_given": True} if rules_given else {}),
    )
    return plan, trace


def _step(trace: Tracer):
    return next(s for s in trace.steps if s.id == "step-own-promo")


def test_the_agents_foreign_promo_loses_to_the_guests_own_fresh_article():
    plan, trace = _built()

    assert [line.product["externalProductId"] for line in plan] == [OWN_ID]
    line = plan[0]
    assert line.reason.startswith("своє замість чужої акції: береш це останнім часом")
    assert "3 свіжих чеків із 6" in line.reason
    step = _step(trace)
    assert step.args["підмінено"] == 1
    assert step.tag == "-1 чужих акцій"
    taken = " ".join(step.args["взято"])
    assert ESMIRA in taken and TOMATO in taken and "3 свіжих чеків" in taken


def test_the_dropped_promo_article_stays_a_link_of_the_chain():
    plan, _trace = _built()

    assert ESMIRA_ID in [link.external_product_id for link in plan[0].chain]


def test_the_weighed_own_line_counts_its_quantity_by_the_shared_code():
    weighed = HistoryItem(
        lager_id=OWN_ID,
        name=TOMATO,
        unit="г",
        receipts=6,
        qty_total=Decimal(3000),
        recent_receipts=3,
        qty_recent=Decimal(1500),
    )
    plan, _trace = _built(hints={TOMATO: weighed}, owned={OWN_ID: weighed})

    assert plan[0].qty == Decimal("0.5")
    assert "вагове: звична вага з чеків" in plan[0].reason


def test_a_kind_with_a_promo_habit_keeps_the_agents_pick():
    habit = _item(
        OWN_ID,
        TOMATO,
        recent=3,
        total=3,
        unit="250г",
        purchases=[Purchase(paid=Decimal(100)), *[Purchase(paid=Decimal(50))] * 2],
    )
    assert habit.promo.mostly, "фікстура мусить справді нести акційну звичку"

    plan, trace = _built(hints={TOMATO: habit}, owned={OWN_ID: habit})

    assert [line.product["externalProductId"] for line in plan] == [ESMIRA_ID]
    assert _step(trace).args["підмінено"] == 0


def test_an_own_article_without_fresh_receipts_keeps_the_agents_pick():
    plan, trace = _built(owned=_mine(recent=0, total=6))

    assert [line.product["externalProductId"] for line in plan] == [ESMIRA_ID]
    assert _step(trace).args["підмінено"] == 0


def test_a_guests_own_word_keeps_the_agents_pick():
    plan, trace = _built(auto=False)

    assert [line.product["externalProductId"] for line in plan] == [ESMIRA_ID]
    assert _step(trace).args["підмінено"] == 0


def test_guest_rules_keep_the_agents_pick():
    plan, trace = _built(rules_given=True)

    assert [line.product["externalProductId"] for line in plan] == [ESMIRA_ID]
    assert _step(trace).args["підмінено"] == 0


def test_a_foreign_article_without_a_promo_keeps_the_agents_pick():
    plain = _card(ESMIRA_ID, ESMIRA, 71.77)
    plan, trace = _built(
        options=[_own_card(), plain],
        pick={"intent": TOMATO, "chosen_id": ESMIRA_ID, "qty": 1, "why": "під_намір"},
    )

    assert [line.product["externalProductId"] for line in plan] == [ESMIRA_ID]
    assert _step(trace).args["підмінено"] == 0


def test_the_model_saying_promo_is_enough_even_without_an_old_price():
    plan, trace = _built(options=[_own_card(), _card(ESMIRA_ID, ESMIRA, 71.77)])

    assert [line.product["externalProductId"] for line in plan] == [OWN_ID]
    assert _step(trace).args["підмінено"] == 1


def test_another_kind_on_promo_keeps_the_agents_pick():
    plum = "Слива чорна"
    nectarine = "Нектарин Іспанія"
    plan, trace = _built(
        intent=plum,
        options=[_card("802", nectarine, 99.0), _card(ESMIRA_ID, ESMIRA, 71.77, old=120.0)],
        owned={"802": _item("802", nectarine, recent=4, total=4, unit="250г")},
    )

    assert [line.product["externalProductId"] for line in plan] == [ESMIRA_ID]
    assert _step(trace).args["підмінено"] == 0


def test_the_step_stands_when_nothing_was_swapped():
    plan, trace = _built(
        options=[_own_card()],
        pick={"intent": TOMATO, "chosen_id": OWN_ID, "qty": 1, "why": "звичне"},
    )

    assert [line.product["externalProductId"] for line in plan] == [OWN_ID]
    step = _step(trace)
    assert step.args["підмінено"] == 0 and step.args["взято"] == []
    assert step.result_summary == "агент ніде не взяв чужу акцію замість свого"
    assert step.tag == "нічого не знято"
