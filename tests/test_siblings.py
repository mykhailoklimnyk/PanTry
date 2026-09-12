from __future__ import annotations

from komora.agent.basket import HistoryItem, Naming, kind_key, siblings_of


def _item(lager: str, name: str, recent: int, receipts: int | None = None) -> HistoryItem:
    return HistoryItem(
        lager_id=lager,
        name=name,
        unit="шт",
        receipts=recent if receipts is None else receipts,
        recent_receipts=recent,
    )


PREMIA = _item("101", "Молоко «Премія» 2,5%", 3)
YAGOT = _item("303", "Молоко Яготинське 2,5%", 2)
PROSTO = _item("404", "Молоко Простонаше 2,5%", 5)
STALE = _item("505", "Молоко Селянське 2,5%", 0, receipts=6)
CHEESE = _item("202", "Сир Комо Гауда", 4)
HISTORY = [PREMIA, YAGOT, PROSTO, STALE, CHEESE]
NAMES = {
    **{kind_key(item.name): Naming(intent="молоко") for item in (PREMIA, YAGOT, PROSTO, STALE)},
    kind_key(CHEESE.name): Naming(intent="сир"),
}


def test_siblings_are_own_recent_articles_of_the_same_named_kind_freshest_first():
    kin = siblings_of(
        {kind_key(PREMIA.name): PREMIA, kind_key(CHEESE.name): CHEESE}, HISTORY, NAMES
    )
    assert kin == {kind_key(PREMIA.name): ["404", "303"]}


def test_the_ceiling_is_a_machine_ceiling_and_the_unnamed_have_no_siblings():
    kin = siblings_of({kind_key(PREMIA.name): PREMIA}, HISTORY, NAMES, take=1)
    assert kin == {kind_key(PREMIA.name): ["404"]}
    assert siblings_of({kind_key(PREMIA.name): PREMIA}, HISTORY, {}) == {}
