from __future__ import annotations

from decimal import Decimal
from typing import Any

from komora.agent.basket import build_chain


def _bottle(
    pid: str, ratio: str, price: float, name: str = "Віскі Jack Daniel's"
) -> dict[str, Any]:
    return {
        "externalProductId": pid,
        "name": name,
        "price": price,
        "displayRatio": ratio,
        "stock": 20,
        "available": True,
    }


MINI = _bottle("716864", "0,05л", 77.49)
CHOSEN = _bottle("32967", "0,5л", 689.0)
SEVEN = _bottle("374122", "0,7л", 899.0)
LITRE = _bottle("4103", "1л", 1199.0, name="Віскі Jack Daniels")
THREE = _bottle("590067", "3л", 4099.0)
SHELF = [MINI, CHOSEN, SEVEN, LITRE, THREE]

USUAL = Decimal(500)


def _chain() -> list[str]:
    chain = build_chain("Віскі", CHOSEN, SHELF, usual_pack=USUAL)
    return [alternative.external_product_id for alternative in chain]


def test_the_miniature_is_no_longer_the_head_of_the_chain():
    assert _chain()[0] != MINI["externalProductId"]


def test_the_head_delivers_at_least_what_was_ordered():
    assert _chain()[0] == SEVEN["externalProductId"]


def test_a_pack_bigger_than_the_guest_ever_buys_yields_to_a_closer_one():
    order = _chain()
    assert order[0] == SEVEN["externalProductId"], order
    assert THREE["externalProductId"] not in order and MINI["externalProductId"] not in order


def test_the_miniature_leaves_the_chain_by_the_price_corridor():
    chain = build_chain("Віскі", CHOSEN, [CHOSEN, MINI], usual_pack=USUAL)
    assert [a.external_product_id for a in chain] == []


def test_without_the_guests_usual_pack_the_floor_still_holds():
    chain = build_chain("Віскі", CHOSEN, SHELF, usual_pack=None)
    assert next(a.external_product_id for a in chain) != MINI["externalProductId"]
