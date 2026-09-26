from __future__ import annotations

from typing import Any

from komora.agent.basket import (
    PlanLine,
    build_chain,
    collapse_split,
    name_matches,
)

PAPER = "Папір туалетний «Премія» білий 3-шаровий"


def _product(pid: str, name: str, price: float = 50.0) -> dict[str, Any]:
    return {
        "externalProductId": pid,
        "name": name,
        "price": price,
        "stock": 20,
        "available": True,
    }


CHOSEN = _product("1", PAPER)
SHELF = [
    CHOSEN,
    _product("2", "Папір пергаментний для випікання 30 см"),
    _product("3", "Папір подарунковий El Passo ретро"),
    _product("4", "Папір туалетний «Премія» білий котиковий"),
]


def test_the_node_listing_decides_what_may_be_promised():
    chain = build_chain("папір", CHOSEN, SHELF, proven=frozenset({"4"}))

    assert [link.name for link in chain] == ["Папір туалетний «Премія» білий котиковий"]


def test_without_the_tree_the_old_rule_stays():
    chain = build_chain("папір", CHOSEN, SHELF)

    assert len(chain) == 3, "усе, що назва не спростувала, лишається кандидатом"


def test_the_usual_from_receipts_survives_the_listing():
    chain = build_chain("папір", CHOSEN, SHELF, history_id="3", proven=frozenset({"4"}))

    assert {link.external_product_id for link in chain} == {"3", "4"}


def test_the_same_kind_from_both_sides_of_the_name():
    assert name_matches("туалетний папір", PAPER)
    assert name_matches("туалетний папір", "Туалетний папір Zewa Deluxe персик")
    assert not name_matches("туалетний папір", "Папір пергаментний для випікання")


def test_the_head_of_the_name_still_guards_against_chocolate():
    assert not name_matches("молоко", "Шоколад молочний з молоком")
    assert not name_matches("чай", "Фільтри для чаю")
    assert name_matches("молоко", "Молоко Селянське 2,5%")


def _line(intent: str, name: str, *, from_receipts: bool = False) -> PlanLine:
    return PlanLine(
        intent=intent,
        product=_product(name, name),
        qty=1,  # type: ignore[arg-type]
        reason="тест",
        from_history=None,
        history_matched=from_receipts,
    )


def test_two_words_of_one_phrase_do_not_make_two_rows():
    lines = [
        _line("туалетний", "Туалетний папір Zewa Deluxe персик"),
        _line("папір", PAPER),
        _line("молоко", "Молоко Селянське 2,5%"),
    ]

    dropped = collapse_split(lines, {"туалетний папір": ["туалетний", "папір"]})

    assert [line.intent for line in lines] == ["туалетний", "молоко"]
    assert dropped == [PAPER]


def test_the_usual_wins_the_survivor_seat():
    lines = [
        _line("туалетний", "Туалетний папір Zewa Deluxe персик"),
        _line("папір", PAPER, from_receipts=True),
    ]

    collapse_split(lines, {"туалетний папір": ["туалетний", "папір"]})

    assert [line.product["name"] for line in lines] == [PAPER]


def test_three_different_kinds_in_one_phrase_stay_three_rows():
    lines = [
        _line("хліб", "Хліб Київський"),
        _line("молоко", "Молоко Селянське 2,5%"),
        _line("чай", "Чай Ahmad чорний"),
    ]

    dropped = collapse_split(lines, {"хліб молоко чай": ["хліб", "молоко", "чай"]})

    assert dropped == []
    assert len(lines) == 3


def test_a_weighed_line_carries_the_measure_into_the_mandate():
    from decimal import Decimal

    from komora.agent.basket import build_lines

    roll = {
        **_product("9", "Рулет курячий домашній в/г", 719.0),
        "stock": 3,
        "weighted": True,
        "displayRatio": "100г",
        "step": 0.1,
        "oldPrice": None,
        "image": None,
        "companyId": "c",
        "branchId": "b",
    }
    lines, _, _ = build_lines(
        ["рулет"], {"рулет": [roll]}, {}, {}, auto_swap=True, auto_swap_percent=10
    )

    [line] = lines
    assert line.mandate is not None
    assert "грн/кг" in line.mandate
    assert line.qty < Decimal(1), "вагового беруть частками кроку, а не штуками"


FISH = "zamorozhena-ryba-4432"
SEAFOOD = "zamorozheni-moreprodukty-ta-moliusky-4451"
BOTH = "zamorozheni-moreprodukty-i-ryba-5181"
SEA_MAP = {
    "524086": frozenset({FISH, BOTH}),
    "1": frozenset({FISH, BOTH}),
    "437991": frozenset({SEAFOOD, BOTH}),
    "2": frozenset({SEAFOOD, BOTH}),
}
HAKE = _product("524086", "Хек північноамериканський свіжоморожений")
SEA_SHELF = [
    HAKE,
    _product("1", "Окунь морський без голови свіжоморожений"),
    _product("437991", "Кальмар туби чищені свіжоморожений"),
    _product("2", "Креветки «Премія» 70/90 варено-морожені"),
]


def test_the_squid_does_not_get_promised_under_the_hake():
    chain = build_chain("риба", HAKE, SEA_SHELF, kinds=SEA_MAP)

    assert [link.name for link in chain] == ["Окунь морський без голови свіжоморожений"]


def test_the_name_still_carries_what_the_node_no_longer_proves():
    chain = build_chain("кальмар", HAKE, SEA_SHELF, kinds=SEA_MAP)

    assert "Кальмар туби чищені свіжоморожений" in [link.name for link in chain]


def test_an_own_recent_article_of_the_kind_is_a_history_link_without_a_node_proof():
    from komora.core.substitution import Source

    chosen = _product("1", "Молоко «Премія» 2,5% пляшка 2 л", 65.0)
    other = _product("2", "Молоко Яготинське 2,5% 900 г", 49.0)
    stranger = _product("3", "Молоко Простонаше 2,5% 900 г", 45.0)
    chain = build_chain(
        "молоко премія",
        chosen,
        [chosen, other, stranger],
        kin=frozenset({"2"}),
        proven=frozenset({"3"}),
    )
    assert chain and chain[0].external_product_id == "2"
    assert chain[0].source is Source.HISTORY
    plain = build_chain("молоко премія", chosen, [chosen, other, stranger], proven=frozenset({"3"}))
    assert "2" not in [link.external_product_id for link in plain]


def test_a_link_outside_the_price_corridor_is_dropped_unless_it_is_own():
    chosen = _product("1", "Вода мінеральна Карпатська 0,5 л", 15.0)
    shelf = [
        chosen,
        _product("2", "Вода мінеральна VCH Barcelona 0,5 л", 45.0),
        _product("3", "Вода мінеральна Моршинська 0,5 л", 18.0),
        _product("4", "Вода мінеральна Поляна 0,5 л", 6.0),
    ]
    ids = [a.external_product_id for a in build_chain("вода", chosen, shelf)]
    assert ids == ["3"], ids
    own = [a.external_product_id for a in build_chain("вода", chosen, shelf, history_id="2")]
    assert own[0] == "2" and "4" not in own, own


def test_a_link_with_the_same_name_as_the_chosen_is_not_a_link():
    chosen = _product("1", "Перець помаранчевий", 60.0)
    twin = _product("2", "Перець помаранчевий", 58.0)
    other = _product("3", "Перець червоний", 55.0)
    bigger = {**_product("4", "Перець помаранчевий", 99.0), "displayRatio": "1кг"}
    ids = [
        a.external_product_id for a in build_chain("перець", chosen, [chosen, twin, other, bigger])
    ]
    assert "2" not in ids and "3" in ids, ids
    assert "4" in ids, "та сама назва в іншій фасовці -- інший товар, як пляшки віскі"


NECTAR = "Нектар Jaffa ананасовий"
NECTAR_SHELF = [
    _product("n1", NECTAR, price=42.0),
    _product("n2", "Нектар «Світанок» яблучний", price=30.0),
    _product("n3", "Нектар Jaffa вишневий", price=42.0),
]


def test_an_auto_need_keeps_the_chain_near_what_the_guest_buys():
    chain = build_chain(
        "Нектар",
        NECTAR_SHELF[0],
        NECTAR_SHELF,
    )

    assert [link.external_product_id for link in chain] == ["n3", "n2"]
