from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from komora.agent.bar import bar_live, kinds_of, merge_said
from komora.agent.basket import MIN_RECEIPTS, HistoryItem, Naming, forget_intents
from komora.config import Settings
from komora.core.bar import DrinkKind, Shelf
from komora.core.location import HOME_DELIVERY, Location
from komora.core.said import SOURCE_RECEIPTS
from komora.mcp.client import SilpoMCP

pytestmark = pytest.mark.anyio

NOW = datetime(2026, 8, 25, tzinfo=UTC)
BRANCH = "00000000-0000-4000-8000-000000000002"
HERE = Location(branch_id=BRANCH, branches={HOME_DELIVERY: BRANCH})

SLOT = {
    "start": "2026-08-26T11:30:00+00:00",
    "end": "2026-08-26T13:00:00+00:00",
    "available": True,
    "deliveryType": "DeliveryHome",
    "deliveryCost": 89,
    "minOrderCost": 599,
    "maxWeight": 50,
}

BEER = {
    "lagerId": "781555",
    "name": "Пиво Hike Blanche світле з/б",
    "quantity": 1,
    "unit": "0,5л",
    "price": 50.99,
}
PACK = {
    "lagerId": "781556",
    "name": "Пиво Kronenbourg 1664 Blanc світле з/б",
    "quantity": 1,
    "unit": "4*0,5л",
    "price": 264,
}
BREAD = {
    "lagerId": "9",
    "name": "Лаваш грузинський із зеленню та цибулею",
    "quantity": 1,
    "unit": "шт",
    "price": 39,
}


def _receipt(day: int, *products: dict) -> dict:
    return {
        "createdAt": f"2026-08-{day:02d}T10:00:00",
        "sumReg": 100,
        "products": list(products),
    }


def _stand(tmp_path, *orders: dict) -> SilpoMCP:
    (tmp_path / "silpo_get_time_slots.json").write_text(
        json.dumps({"slots": [SLOT]}), encoding="utf-8"
    )
    (tmp_path / "silpo_get_my_offline_orders.json").write_text(
        json.dumps({"orders": list(orders), "meta": {"total": len(orders)}}), encoding="utf-8"
    )
    return SilpoMCP(settings=Settings.model_construct(), fixtures_dir=tmp_path)


class _NamingLLM:

    model = "fake-model"

    def __init__(self, drinks: dict[str, str | None]) -> None:
        self.drinks = drinks
        self.asked: list[list[str]] = []

    async def decide(self, *, system, user, schema, schema_name="decision", max_tokens=2048, **_):
        from komora.agent.llm import Decision, Usage

        asked = json.loads(user)["назви"]
        self.asked.append(asked)
        return Decision(
            data={
                "kinds": [
                    {
                        "name": name,
                        "intent": "пиво" if "Пиво" in name else "лаваш",
                        "subtype": None,
                        "drink": self.drinks.get(name),
                    }
                    for name in asked
                ]
            },
            text="",
            model=self.model,
            usage=Usage(1, 1),
            duration_ms=1,
        )


class _SilentLLM:

    model = "fake-model"

    async def decide(self, **_):
        raise RuntimeError("модель мовчить")


@pytest.fixture(autouse=True)
def _clean_cache():
    forget_intents()
    yield
    forget_intents()


async def test_a_habit_becomes_a_row_with_its_own_price_fork(tmp_path):
    mcp = _stand(
        tmp_path,
        _receipt(20, BEER, PACK, BREAD),
        _receipt(14, BEER, PACK),
        _receipt(8, BEER, PACK),
    )
    llm = _NamingLLM({BEER["name"]: "light", PACK["name"]: "light", BREAD["name"]: None})

    bar = await bar_live(mcp, llm=llm, now=NOW, place=HERE)

    (row,) = bar.items
    assert row.kind is DrinkKind.LIGHT
    assert row.times == 6, "дві марки з однією назвою виду — одна звичка"
    assert row.usual.external_product_id == BEER["lagerId"]
    assert (row.price_from, row.price_to) == (Decimal("45.89"), Decimal("56.09")), (
        "упаковка за 264 ₴ у вилку не входить"
    )
    assert bar.named == 2


async def test_bread_named_as_not_a_drink_never_reaches_the_bar(tmp_path):
    mcp = _stand(tmp_path, _receipt(20, BREAD), _receipt(14, BREAD), _receipt(8, BREAD))
    llm = _NamingLLM({BREAD["name"]: None})

    bar = await bar_live(mcp, llm=llm, now=NOW, place=HERE)

    assert bar.items == []
    assert bar.named == 1, "вид названий — просто це не напій"


async def test_no_receipts_says_there_are_no_receipts(tmp_path):
    bar = await bar_live(_stand(tmp_path), llm=_NamingLLM({}), now=NOW, place=HERE)

    assert (bar.receipts, bar.kinds, bar.named) == (0, 0, 0)
    assert bar.tracked_from == MIN_RECEIPTS


async def test_a_silent_model_is_not_the_same_as_no_alcohol(tmp_path):
    mcp = _stand(tmp_path, _receipt(20, BEER), _receipt(14, BEER), _receipt(8, BEER))

    bar = await bar_live(mcp, llm=_SilentLLM(), now=NOW, place=HERE)

    assert bar.items == []
    assert bar.named == 0
    assert bar.receipts == 3, "чеки прочитані, і мовчати про них не можна"
    assert bar.kinds == 1


async def test_only_the_pantrys_candidates_go_to_the_model(tmp_path):
    once = {"lagerId": "5", "name": "Лікер Baileys", "quantity": 1, "unit": "0,5л", "price": 499}
    mcp = _stand(
        tmp_path,
        _receipt(20, BEER, once),
        _receipt(14, BEER),
        _receipt(8, BEER),
    )
    llm = _NamingLLM({BEER["name"]: "light", once["name"]: "strong"})

    bar = await bar_live(mcp, llm=llm, now=NOW, place=HERE)

    assert llm.asked == [[BEER["name"]]], "про разову покупку модель не питають"
    assert [row.label for row in bar.items] == ["пиво"]
    assert bar.kinds == 2, "види історії рахуються всі, зрізає лише поріг"


def test_kinds_merge_by_what_the_agent_called_them():
    history = [
        HistoryItem(lager_id="1", name="Пиво Hike", unit="0,5л", receipts=3),
        HistoryItem(lager_id="2", name="Пиво Kronenbourg", unit="0,5л", receipts=2),
    ]
    names = {
        "пиво hike": Naming("пиво", None, DrinkKind.LIGHT, drink_known=True),
        "пиво kronenbourg": Naming("пиво", None, DrinkKind.LIGHT, drink_known=True),
    }

    (kind,) = kinds_of(history, names)

    assert len(kind.bottles) == 2
    assert kind.label == "пиво"


def test_a_kind_the_agent_called_not_a_drink_is_not_a_kind_of_the_bar():
    history = [HistoryItem(lager_id="1", name="Лаваш грузинський", unit="шт", receipts=3)]
    names = {"лаваш грузинський": Naming("лаваш", None, None, drink_known=True)}

    assert kinds_of(history, names) == ()


def test_the_guests_word_moves_the_kind_and_leaves_the_cache_alone():
    history = [HistoryItem(lager_id="1", name="Лікер Oakheart", unit="0,5л", receipts=4)]
    names = {"лікер oakheart": Naming("лікер", None, DrinkKind.WINE, drink_known=True)}
    before = dict(names)

    (kind,) = kinds_of(history, names, drinks={"лікер": DrinkKind.STRONG})

    assert kind.group is DrinkKind.STRONG
    assert kind.group_said is True
    assert kind.key == "strong|лікер"
    assert names == before, "кеш називання спільний: правка одного переписала б бар усім"


def test_the_moved_kind_merges_with_its_new_neighbour():
    history = [
        HistoryItem(lager_id="1", name="Ром Oakheart", unit="0,5л", receipts=4),
        HistoryItem(lager_id="2", name="Ром Bacardi", unit="0,5л", receipts=2),
    ]
    names = {
        "ром oakheart": Naming("ром", None, DrinkKind.WINE, drink_known=True),
        "ром bacardi": Naming("ром", None, DrinkKind.STRONG, drink_known=True),
    }

    (kind,) = kinds_of(history, names, drinks={"ром": DrinkKind.STRONG})

    assert len(kind.bottles) == 2, "той самий вид на тій самій полиці -- один рядок"
    assert kind.group_said is True


def test_a_word_about_a_neighbour_leaves_this_kind_where_it_was():
    history = [HistoryItem(lager_id="1", name="Пиво Hike", unit="0,5л", receipts=3)]
    names = {"пиво hike": Naming("пиво світле", None, DrinkKind.LIGHT, drink_known=True)}

    (kind,) = kinds_of(history, names, drinks={"віскі": DrinkKind.STRONG})

    assert kind.group is DrinkKind.LIGHT
    assert kind.group_said is False


def test_the_guest_can_pull_into_the_bar_what_the_model_called_no_drink():
    history = [HistoryItem(lager_id="1", name="Настоянка Nemiroff", unit="0,5л", receipts=3)]
    names = {"настоянка nemiroff": Naming("настоянка", None, None, drink_known=True)}

    assert kinds_of(history, names) == ()

    (kind,) = kinds_of(history, names, drinks={"настоянка": DrinkKind.STRONG})

    assert kind.group is DrinkKind.STRONG
    assert kind.group_said is True


def test_a_hand_written_row_takes_the_shelf_the_guest_named():
    shelf, unlisted = merge_said(
        Shelf((), 0),
        {"настоянка": "Настоянка"},
        names={},
        source=SOURCE_RECEIPTS,
        drinks={"настоянка": DrinkKind.STRONG},
    )

    assert unlisted == 0
    (row,) = shelf.rows
    assert row.group is DrinkKind.STRONG
    assert row.group_said is True


def test_a_hand_written_row_without_a_word_keeps_the_models_silence():
    shelf, _ = merge_said(
        Shelf((), 0), {"настоянка": "Настоянка"}, names={}, source=SOURCE_RECEIPTS
    )

    (row,) = shelf.rows
    assert row.group is None
    assert row.group_said is False


def _tree():
    from komora.core.bar import shelf_map
    from komora.core.dictionary import Node

    return shelf_map(
        [
            Node(id="1", title="Алкоголь", parent_id=None, slug="alkogol-4457"),
            Node(id="2", title="Міцний алкоголь", parent_id="1", slug="mitsnyi-alkogol-4458"),
            Node(id="3", title="Ром", parent_id="2", slug="rom-4468"),
        ]
    )


def test_the_tree_overrules_the_models_label_on_the_road_and_not_only_in_the_function():
    history = [
        HistoryItem(lager_id="532439", name="Напій на основі рому Oakheart", unit="1л", receipts=4)
    ]
    names = {"напій на основі рому": Naming("лікер", None, DrinkKind.STRONG, drink_known=True)}

    (kind,) = kinds_of(history, names, tree=_tree(), nodes={"532439": frozenset({"rom-4468"})})

    assert kind.label == "ром"
    assert kind.group is DrinkKind.STRONG


def test_where_the_tree_is_silent_the_model_still_names_the_kind():
    history = [
        HistoryItem(lager_id="000", name="Напій на основі рому Oakheart", unit="1л", receipts=4)
    ]
    names = {"напій на основі рому": Naming("лікер", None, DrinkKind.STRONG, drink_known=True)}

    (kind,) = kinds_of(history, names, tree=_tree(), nodes={})

    assert kind.label == "лікер"


def test_the_guest_word_still_beats_the_tree():
    history = [
        HistoryItem(lager_id="532439", name="Напій на основі рому Oakheart", unit="1л", receipts=4)
    ]
    names = {"напій на основі рому": Naming("лікер", None, DrinkKind.STRONG, drink_known=True)}

    (kind,) = kinds_of(
        history,
        names,
        drinks={"ром": DrinkKind.LIGHT},
        tree=_tree(),
        nodes={"532439": frozenset({"rom-4468"})},
    )

    assert kind.group is DrinkKind.LIGHT
    assert kind.group_said is True
