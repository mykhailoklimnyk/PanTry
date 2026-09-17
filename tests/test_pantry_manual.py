from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from komora.agent.basket import (
    HistoryItem,
    Naming,
    assemble_list,
    kind_key,
    manual_item,
    manual_key,
    only_manual,
    receipts_pantry,
    untracked,
    with_manual,
)
from komora.api.schemas import BuildRequest
from komora.core.pantry import manual_id
from komora.mcp.client import SilpoMCP

NOW = datetime(2026, 8, 25, tzinfo=UTC)


def _item(name: str, lager: str, *, days: list[int]) -> HistoryItem:
    return HistoryItem(
        lager_id=lager,
        name=name,
        unit="шт",
        receipts=len(days),
        qty_total=Decimal(len(days)),
        recent_receipts=len(days),
        qty_recent=Decimal(len(days)),
        moments=[NOW - timedelta(days=day) for day in days],
    )


def test_the_stored_key_is_the_kind_not_the_wording():
    assert manual_key("  Молоко Ферма ") == manual_key("молоко ферма")


def test_a_written_kind_appears_even_without_a_single_receipt():
    rows = with_manual([], {"туалетний папір": "туалетний папір"}, history=[], now=NOW)

    assert [row.label for row in rows] == ["туалетний папір"]
    assert rows[0].source == "manual"
    assert rows[0].id == manual_id("туалетний папір")
    assert rows[0].state.endswith("беру в наступний кошик")


def test_a_written_kind_carries_no_invented_numbers():
    (row,) = with_manual([], {"васабі": "васабі"}, history=[], now=NOW)

    assert row.qty is None
    assert row.usual_qty is None
    assert row.unit == ""
    assert row.cycle_days is None
    assert row.left_ratio is None


def test_a_kind_the_pantry_already_counts_does_not_appear_twice():
    history = [_item("Молоко Ферма 2,5%", "42", days=[28, 21, 14, 7])]
    rows = receipts_pantry(history, now=NOW)
    assert len(rows) == 1

    merged = with_manual(rows, {"молоко ферма": "молоко"}, history=history, now=NOW)

    assert len(merged) == 1, "рядок з чеків сильніший за слово, а не додається до нього"
    assert merged[0].id == "42"


def test_the_agents_naming_is_used_on_both_sides_of_the_merge():
    history = [
        _item("Куряче філе охолоджене", "1", days=[34, 29]),
        _item("Філе куряче Наша Ряба", "2", days=[24, 19]),
    ]
    names = {
        "куряче філе": Naming("філе куряче"),
        "філе куряче": Naming("філе куряче"),
    }
    rows = receipts_pantry(history, now=NOW, names=names)
    assert len(rows) == 1, "чеки вже злиті в один вид"

    merged = with_manual(
        rows, {"філе куряче": "філе куряче"}, history=history, now=NOW, names=names
    )

    assert len(merged) == 1


def test_the_written_row_stands_after_what_is_running_out():
    running_out = _item("Хліб Київський", "10", days=[12, 9, 6, 3])
    calm = _item("Рис Преміа", "20", days=[55, 40, 25, 10])
    history = [running_out, calm]
    rows = receipts_pantry(history, now=NOW)
    assert rows[0].running_out, "перевіряємо саме порядок, тож термінове має бути"

    merged = with_manual(rows, {"васабі": "васабі"}, history=history, now=NOW)

    assert [row.source for row in merged] == ["receipts", "manual", "receipts"]


def test_without_a_written_list_the_pantry_is_untouched():
    history = [_item("Молоко Ферма", "42", days=[28, 21, 14, 7])]
    rows = receipts_pantry(history, now=NOW)

    assert with_manual(rows, {}, history=history, now=NOW) == rows


SLOT = {
    "start": "2026-08-25T11:30:00+00:00",
    "end": "2026-08-25T13:00:00+00:00",
    "available": True,
    "deliveryType": "DeliveryHome",
    "deliveryCost": 89,
    "deliveryCostMap": [{"cost": 59, "fromOrderCost": 1199}],
    "minOrderCost": 599,
    "maxWeight": 50,
}


def _card(pid: int, name: str) -> dict:
    return {
        "id": f"00000000-0000-4000-8000-{pid:012d}",
        "name": name,
        "slug": f"slug-{pid}",
        "price": 30.0,
        "oldPrice": None,
        "stock": 20,
        "available": True,
        "image": None,
        "weighted": False,
        "step": 1,
        "displayRatio": "1шт",
        "companyId": "00000000-0000-4000-8000-000000000001",
        "branchId": "00000000-0000-4000-8000-000000000002",
        "externalProductId": pid,
    }


def _stand(tmp_path, *, orders: list[dict]) -> SilpoMCP:
    (tmp_path / "silpo_get_time_slots.json").write_text(
        json.dumps({"slots": [SLOT]}), encoding="utf-8"
    )
    (tmp_path / "silpo_get_my_offline_orders.json").write_text(
        json.dumps({"orders": orders}), encoding="utf-8"
    )
    (tmp_path / "silpo_get_my_shopping_cart.json").write_text(
        json.dumps({"shoppingCartId": None}), encoding="utf-8"
    )
    (tmp_path / "silpo_find_products_batch.json").write_text(
        json.dumps(
            {
                "queries": [
                    {"query": "васабі", "products": [_card(301, "Соус Васабі Kikkoman")]},
                    {"query": "Хліб Київський", "products": [_card(101, "Хліб Київський")]},
                ]
            }
        ),
        encoding="utf-8",
    )
    return SilpoMCP(fixtures_dir=tmp_path)


BREAD_ORDERS = [
    {
        "createdAt": day,
        "products": [
            {"lagerId": 101, "name": "Хліб Київський", "unit": "шт", "quantity": 1, "price": 30}
        ],
    }
    for day in ("2026-07-22", "2026-07-29", "2026-08-05", "2026-08-12")
]


@pytest.mark.anyio
async def test_a_written_kind_reaches_the_basket(tmp_path):
    stand = _stand(tmp_path, orders=BREAD_ORDERS)

    built = await assemble_list(
        stand,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week"}),
        now=NOW,
        manual={"васабі": "васабі"},
    )

    assert "васабі" in {line.intent for line in built.lines}


@pytest.mark.anyio
async def test_the_written_row_explains_itself_with_the_guests_own_word(tmp_path):
    stand = _stand(tmp_path, orders=BREAD_ORDERS)

    built = await assemble_list(
        stand,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week"}),
        now=NOW,
        manual={"васабі": "васабі"},
    )
    row = next(line for line in built.basket.lines if line.name.endswith("Kikkoman"))

    assert row.explanation == "ти сам додав це в комору"


@pytest.mark.anyio
async def test_a_kind_the_pantry_already_tracks_is_left_to_the_cycle(tmp_path):
    stand = _stand(tmp_path, orders=BREAD_ORDERS)

    built = await assemble_list(
        stand,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week"}),
        now=NOW,
        manual={"хліб київський": "Хліб Київський"},
    )
    row = next(line for line in built.basket.lines if line.name == "Хліб Київський")

    assert row.explanation.startswith("закінчується за циклом")
    step = next(s for s in built.basket.trace if s.id == "step-manual")
    assert "комора вже веде" in step.result_summary


@pytest.mark.anyio
async def test_the_step_names_itself_even_when_it_added_nothing(tmp_path):
    stand = _stand(tmp_path, orders=BREAD_ORDERS)

    built = await assemble_list(
        stand,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week"}),
        now=NOW,
        manual={"хліб київський": "Хліб Київський"},
    )
    step = next(s for s in built.basket.trace if s.id == "step-manual")

    assert step.result_summary.startswith("нового немає")


@pytest.mark.anyio
async def test_without_a_written_list_the_step_is_absent(tmp_path):
    stand = _stand(tmp_path, orders=BREAD_ORDERS)

    built = await assemble_list(
        stand, llm=None, request=BuildRequest.model_validate({"mode": "week"}), now=NOW
    )

    assert not [s for s in built.basket.trace if s.id == "step-manual"]


@pytest.mark.anyio
async def test_a_written_kind_builds_a_basket_on_an_account_without_receipts(tmp_path):
    stand = _stand(tmp_path, orders=[])

    built = await assemble_list(
        stand,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week"}),
        now=NOW,
        manual={"васабі": "васабі"},
    )

    assert [line.intent for line in built.lines] == ["васабі"]


def test_a_word_swallowed_by_the_merge_says_where_it_went():
    history = [_item("Напій Sprite 0,5л", "42", days=[28, 21, 14, 7])]
    names = {"напій sprite": Naming("напій газований", "лимон-лайм")}
    rows = receipts_pantry(history, now=NOW, names=names)

    merged = with_manual(rows, {"спрайт": "Спрайт"}, history=history, now=NOW, names=names)

    assert len(merged) == 1, "близнюка немає -- і саме тому слово треба назвати"
    assert merged[0].label == "напій газований · лимон-лайм"
    assert merged[0].written_as == ["Спрайт"]


def test_a_word_that_survived_the_merge_stays_silent():
    (row,) = with_manual([], {"васабі": "васабі"}, history=[], now=NOW)

    assert row.written_as == []


def test_two_words_that_landed_in_one_row_are_both_named():
    history = [_item("Напій Sprite 0,5л", "42", days=[28, 21, 14, 7])]
    names = {"напій sprite": Naming("напій газований", "лимон-лайм")}
    rows = receipts_pantry(history, now=NOW, names=names)

    merged = with_manual(
        rows,
        {"спрайт": "Спрайт", "sprite": "sprite"},
        history=history,
        now=NOW,
        names=names,
    )

    assert len(merged) == 1
    assert merged[0].written_as == ["Спрайт", "sprite"]


def test_the_guest_mode_names_the_word_too():
    history = [_item("Напій Sprite 0,5л", "42", days=[28, 21, 14, 7])]
    names = {"напій sprite": Naming("напій газований", "лимон-лайм")}
    rows = receipts_pantry(history, now=NOW, names=names)

    items, _ = only_manual(rows, {"спрайт": "Спрайт"}, history=history, now=NOW, names=names)

    assert [row.written_as for row in items] == [["Спрайт"]]


def test_in_guest_mode_the_receipts_add_nothing():
    history = [_item("Молоко Ферма", "42", days=[28, 21, 14, 7])]
    rows = receipts_pantry(history, now=NOW)

    items, outside = only_manual(rows, {"васабі": "васабі"}, history=history, now=NOW)

    assert [row.label for row in items] == ["васабі"]
    assert len(outside) == 1, "молоко з чеків нікуди не зникло — воно ПОЗА списком"
    assert outside == ["Молоко Ферма"]


def test_the_numbers_stay_from_the_receipts():
    history = [_item("Молоко Ферма", "42", days=[28, 21, 14, 7])]
    rows = receipts_pantry(history, now=NOW)

    items, outside = only_manual(rows, {"молоко ферма": "молоко"}, history=history, now=NOW)

    assert len(items) == 1
    assert items[0].source == "receipts", "вид ведеться чеками — рядок справжній"
    assert items[0].cycle_days == 7
    assert outside == []


def test_an_empty_list_in_guest_mode_is_empty_and_names_what_is_outside():
    history = [_item("Молоко Ферма", "42", days=[28, 21, 14, 7])]
    rows = receipts_pantry(history, now=NOW)

    items, outside = only_manual(rows, {}, history=history, now=NOW)

    assert items == []
    assert outside == ["Молоко Ферма"]


def test_guest_mode_keeps_the_same_order_as_the_mixed_one():
    history = [
        _item("Хліб Київський", "1", days=[15, 12, 9, 6]),
        _item("Молоко Ферма", "2", days=[28, 21, 14, 7]),
    ]
    rows = receipts_pantry(history, now=NOW)
    assert next(row.running_out for row in rows) is True

    items, _ = only_manual(
        rows,
        {"молоко ферма": "молоко ферма", "хліб київський": "хліб київський"},
        history=history,
        now=NOW,
    )

    assert [row.running_out for row in items] == sorted(
        (row.running_out for row in items), reverse=True
    )


@pytest.mark.anyio
async def test_a_kind_bought_through_us_does_not_ride_into_the_next_basket(tmp_path):
    stand = _stand(tmp_path, orders=BREAD_ORDERS)

    built = await assemble_list(
        stand,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week"}),
        now=NOW,
        manual={"васабі": "васабі"},
        marks={manual_key("васабі"): NOW - timedelta(days=1)},
    )

    assert "васабі" not in {line.intent for line in built.lines}


@pytest.mark.anyio
async def test_a_kind_written_by_hand_still_rides(tmp_path):
    stand = _stand(tmp_path, orders=BREAD_ORDERS)

    built = await assemble_list(
        stand,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week"}),
        now=NOW,
        manual={"васабі": "васабі"},
        marks={},
    )

    assert "васабі" in {line.intent for line in built.lines}


@pytest.mark.anyio
async def test_the_step_says_how_many_were_just_bought(tmp_path):
    stand = _stand(tmp_path, orders=BREAD_ORDERS)

    built = await assemble_list(
        stand,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week"}),
        now=NOW,
        manual={"васабі": "васабі"},
        marks={manual_key("васабі"): NOW},
    )
    step = next(s for s in built.basket.trace if s.id == "step-manual")

    assert "щойно куплено" in step.result_summary


def test_the_row_says_it_was_bought_and_stops_promising_the_basket():
    fresh = manual_item(
        "васабі", [], now=NOW, marks={manual_key("васабі"): NOW - timedelta(days=2)}
    )
    plain = manual_item("васабі", [], now=NOW)

    assert "купив 2 дн тому зі списку" in fresh.state
    assert "беру в наступний кошик" not in fresh.state
    assert "беру в наступний кошик" in plain.state


def test_bought_today_is_said_with_a_word_not_a_zero():
    row = manual_item("васабі", [], now=NOW, marks={manual_key("васабі"): NOW})

    assert row.state.startswith("купив сьогодні зі списку")


def test_the_hints_come_from_kinds_the_pantry_does_not_lead_yet():
    kinds = [
        _item("Оцет бальзамічний", "7", days=[200]),
        _item("Мед акацієвий", "8", days=[3]),
        _item("Молоко Ферма", "42", days=[28, 21, 14, 7]),
    ]

    hints = untracked(kinds)

    assert hints == ["Оцет бальзамічний", "Мед акацієвий"] or hints == [
        "Мед акацієвий",
        "Оцет бальзамічний",
    ]
    assert hints[0] == "Мед акацієвий", "свіже першим — торішнє гість не згадає"
    assert "Молоко Ферма" not in hints, "вид, який комора веде, підказувати нема сенсу"


def test_a_hidden_kind_leaves_the_pantry_and_says_so():
    history = [
        _item("Молоко Ферма", "42", days=[28, 21, 14, 7]),
        _item("Корм Whiskas", "77", days=[27, 20, 13, 6]),
    ]
    rows = receipts_pantry(history, now=NOW)

    shown = [row for row in rows if kind_key(row.label) != "корм whiskas"]

    assert len(rows) == 2, "передумова: обидва види комора веде"
    assert [row.label for row in shown] == ["Молоко Ферма"]


def test_a_naming_label_resolves_to_its_own_kind_not_to_the_most_frequent_one():
    history = [
        _item("Ковбаса Докторська варена в/ґ", "1", days=[1, 3, 5, 8, 11, 14]),
        _item("Ковбаса Салямі сервірувальна", "2", days=[4, 20]),
        _item("Крупа пшенична Сквирянка 800г", "3", days=[9]),
    ]
    names = {
        "ковбаса докторська": Naming("ковбаса", "варена"),
        "ковбаса салямі": Naming("ковбаса", "сервірувальна"),
        "крупа пшенична": Naming("крупа", "пшенична"),
    }
    salami = manual_item("ковбаса · сервірувальна", history, names=names)
    assert "Салямі" in str(salami.model_dump()), "підпис мусить знайти СВІЙ вид, а не найчастіший"
    assert "Докторська" not in str(salami.model_dump())
    grain = manual_item("крупа · пшенична", history, names=names)
    assert "Сквирянка" in str(grain.model_dump()), "підпис з роздільником мусить збігтись із чеком"


@pytest.mark.anyio
async def test_a_row_written_into_the_pantry_gives_way_to_the_limit(tmp_path):
    stand = _stand(tmp_path, orders=BREAD_ORDERS)

    built = await assemble_list(
        stand,
        llm=None,
        request=BuildRequest.model_validate({"mode": "week", "budget": 40}),
        now=NOW,
        manual={"васабі": "васабі"},
    )

    assert "васабі" not in {line.intent for line in built.lines}
    cut = next(item for item in built.basket.trimmed if item.intent == "васабі")
    assert cut.reason == "дописано в комору без циклу — знімаю під межу після добору"


def test_a_spread_number_never_overwrites_a_word_said_about_that_very_row():
    from komora.db.pantry import _UPSERT_CYCLE

    where = _UPSERT_CYCLE[_UPSERT_CYCLE.index("do update") :]

    assert "where" in where, "розкладене перезаписує пряме слово гостя"
    assert "excluded.said" in where, "пряме слово мусить лишатись сильнішим"
    assert "not pantry_cycles.said" in where, "розкладене лягає лише на нічиє"
