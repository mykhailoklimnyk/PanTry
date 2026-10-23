from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from komora.agent.bar import bar_live
from komora.agent.basket import forget_intents
from komora.config import Settings
from komora.core.bar import DrinkKind
from komora.core.location import HOME_DELIVERY, Location
from komora.core.pantry import is_manual
from komora.core.said import SOURCE_MANUAL, SOURCE_RECEIPTS, Said
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


@pytest.fixture(autouse=True)
def _clean_cache():
    forget_intents()
    yield
    forget_intents()


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


class _LLM:

    model = "fake-model"

    def __init__(self, drinks: dict[str, str | None], labels: dict[str, str]) -> None:
        self.drinks = drinks
        self.labels = labels
        self.asked: list[list[str]] = []

    async def decide(self, *, system, user, schema, schema_name="decision", **_):
        from komora.agent.llm import Decision, Usage

        asked = json.loads(user)["назви"]
        self.asked.append(asked)
        return Decision(
            data={
                "kinds": [
                    {
                        "name": name,
                        "intent": self.labels.get(name, name.casefold()),
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


def _beer_history(tmp_path):
    return _stand(tmp_path, _receipt(20, BEER), _receipt(14, BEER), _receipt(8, BEER))


def _llm(extra: dict[str, str | None] | None = None) -> _LLM:
    drinks: dict[str, str | None] = {BEER["name"]: "light"}
    drinks.update(extra or {})
    return _LLM(drinks, {BEER["name"]: "пиво"})


async def test_a_written_kind_becomes_a_row_the_receipts_never_saw(tmp_path):
    bar = await bar_live(
        _beer_history(tmp_path),
        llm=_llm({"віскі": "strong"}),
        now=NOW,
        place=HERE,
        said=Said(listed={"віскі": "віскі"}),
    )

    said = next(row for row in bar.items if row.source == SOURCE_MANUAL)
    assert said.label == "віскі"
    assert said.kind is DrinkKind.STRONG
    assert is_manual(said.id), "прибрати можна лише те, що гість написав сам (#126)"


async def test_a_written_kind_gets_no_invented_fork(tmp_path):
    bar = await bar_live(
        _beer_history(tmp_path),
        llm=_llm({"віскі": "strong"}),
        now=NOW,
        place=HERE,
        said=Said(listed={"віскі": "віскі"}),
    )

    said = next(row for row in bar.items if row.source == SOURCE_MANUAL)
    assert said.price_from is None and said.price_to is None
    assert said.fork_note == ""
    assert said.usual is None
    assert said.days_since is None
    assert said.times == 0


async def test_a_kind_the_receipts_track_comes_back_as_its_real_row(tmp_path):
    bar = await bar_live(
        _beer_history(tmp_path),
        llm=_llm(),
        now=NOW,
        place=HERE,
        said=Said(listed={"пиво": "пиво"}),
    )

    assert len(bar.items) == 1, "дописане слово не заводить близнюка своєму ж рядку"
    (row,) = bar.items
    assert row.source == SOURCE_RECEIPTS
    assert row.price_from is not None, "числа лишаються з чеків"


async def test_guest_mode_shows_only_the_list_and_counts_the_rest(tmp_path):
    bar = await bar_live(
        _beer_history(tmp_path),
        llm=_llm({"віскі": "strong"}),
        now=NOW,
        place=HERE,
        said=Said(listed={"віскі": "віскі"}, source=SOURCE_MANUAL),
    )

    assert [row.label for row in bar.items] == ["віскі"]
    assert bar.unlisted == 1, "пиво з чеків нікуди не зникло -- воно поза списком"
    assert bar.source == SOURCE_MANUAL


async def test_receipts_mode_adds_the_written_kind_to_what_was_counted(tmp_path):
    bar = await bar_live(
        _beer_history(tmp_path),
        llm=_llm({"віскі": "strong"}),
        now=NOW,
        place=HERE,
        said=Said(listed={"віскі": "віскі"}),
    )

    assert {row.label for row in bar.items} == {"пиво", "віскі"}
    assert bar.unlisted == 0, "у режимі чеків поза списком немає нічого за побудовою"


async def test_a_kind_the_model_did_not_call_a_drink_still_belongs_to_the_guest(tmp_path):
    bar = await bar_live(
        _beer_history(tmp_path),
        llm=_llm({"компот": None}),
        now=NOW,
        place=HERE,
        said=Said(listed={"компот": "компот"}),
    )

    said = next(row for row in bar.items if row.source == SOURCE_MANUAL)
    assert said.label == "компот"
    assert said.kind is None


async def test_the_written_kind_rides_the_same_naming_call(tmp_path):
    llm = _llm({"віскі": "strong"})
    await bar_live(
        _beer_history(tmp_path),
        llm=llm,
        now=NOW,
        place=HERE,
        said=Said(listed={"віскі": "віскі"}),
    )

    assert len(llm.asked) == 1
    assert "віскі" in llm.asked[0]


async def test_two_words_about_one_kind_do_not_become_two_rows(tmp_path):
    bar = await bar_live(
        _beer_history(tmp_path),
        llm=_llm({"віскі": "strong", "віскі бленд": "strong"}),
        now=NOW,
        place=HERE,
        said=Said(listed={"віскі": "віскі", "віскі бленд": "віскі бленд"}),
    )

    assert sum(1 for row in bar.items if row.source == SOURCE_MANUAL) == 1


async def test_an_empty_list_in_guest_mode_is_an_empty_bar(tmp_path):
    bar = await bar_live(
        _beer_history(tmp_path),
        llm=_llm(),
        now=NOW,
        place=HERE,
        said=Said(listed={}, source=SOURCE_MANUAL),
    )

    assert bar.items == []
    assert bar.unlisted == 1
