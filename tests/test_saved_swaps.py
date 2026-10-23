from __future__ import annotations

from decimal import Decimal

from komora.agent.basket import _kept_chain, build_lines, kind_key
from komora.core.levels import Seen
from komora.core.substitution import Source


def _card(article: str, name: str, price: float = 30.0) -> dict:
    return {
        "id": f"uuid-{article}",
        "externalProductId": article,
        "name": name,
        "price": price,
        "stock": 20,
        "available": True,
        "step": 1,
        "displayRatio": "1шт",
        "weighted": False,
        "companyId": "company",
        "branchId": "branch",
        "slug": f"slug-{article}",
    }


MILK = _card("101", "Молоко Простонаше 2,5%")
OTHER = _card("102", "Молоко Яготинське 2,5%", 32.0)
THIRD = _card("103", "Молоко Ферма 2,5%", 34.0)


def _lines(saved: dict[str, tuple[str, ...]] | None, *, options=None, trace=None):
    lines, unresolved, _ = build_lines(
        ["молоко"],
        {"молоко": options if options is not None else [MILK, OTHER, THIRD]},
        {},
        {"молоко": {"chosen_id": "101", "qty": 1}},
        saved_chains=saved,
        trace=trace,
    )
    return lines, unresolved


def test_a_chain_agreed_earlier_reaches_the_next_basket():
    lines, _ = _lines({kind_key("молоко"): ("103", "102")})

    (line,) = lines
    assert [alt.external_product_id for alt in line.chain] == ["103", "102"]


def test_the_guests_order_is_not_reshuffled():
    lines, _ = _lines({kind_key("молоко"): ("103", "102")})

    (line,) = lines
    assert all(alt.source is Source.MANUAL for alt in line.chain)


def test_a_link_that_left_the_shelf_does_not_reach_the_mandate():
    lines, _ = _lines({kind_key("молоко"): ("999", "102")}, options=[MILK, OTHER])

    (line,) = lines
    assert [alt.external_product_id for alt in line.chain] == ["102"]


def test_a_saved_chain_that_died_entirely_falls_back_to_the_computed_one():
    lines, _ = _lines({kind_key("молоко"): ("999",)})

    (line,) = lines
    assert line.chain, "порожній ланцюжок тут читався б як відмова гостя"


def test_a_kind_without_a_saved_chain_is_counted_as_before():
    lines, _ = _lines(None)

    (line,) = lines
    assert line.chain
    assert not all(alt.source is Source.MANUAL for alt in line.chain)


def test_the_step_stands_even_when_nothing_matched():
    from komora.agent.basket import Tracer

    trace = Tracer()
    _lines({kind_key("хліб"): ("102",)}, trace=trace)
    step = next(s for s in trace.steps if s.id == "step-saved-swaps")

    assert "жоден намір" in step.result_summary


def test_without_saved_chains_the_step_is_absent():
    from komora.agent.basket import Tracer

    trace = Tracer()
    _lines(None, trace=trace)

    assert not [s for s in trace.steps if s.id == "step-saved-swaps"]


def test_the_kept_chain_keeps_the_price_of_this_slot():
    chain = _kept_chain(("102",), {"102": OTHER})

    (link,) = chain
    assert link.price == Decimal("32.0")


def test_the_kept_chain_drops_what_the_guest_stopped_buying():
    cards = {
        "101": _card("101", "Морозиво Tonitto тірамісу"),
        "102": _card("102", "Морозиво Ласка"),
    }
    seen = [
        Seen(label="Морозиво Tonitto", unit="шт", receipts=2, days_since=458, article="101"),
        Seen(label="Морозиво Ласка", unit="шт", receipts=3, days_since=12, article="102"),
    ]

    chain = _kept_chain(("101", "102"), cards, seen)

    assert [one.external_product_id for one in chain] == ["102"]
