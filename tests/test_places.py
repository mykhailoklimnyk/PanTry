from __future__ import annotations

from typing import Any, ClassVar

import pytest
from fastapi import HTTPException

from komora.agent import place as place_chain
from komora.api import app as api
from komora.api import places
from komora.auth.session import GuestSession
from komora.core.location import Address, Location, Source, source_note
from komora.mcp.client import MCPCallError, TokenRejected

GUEST = GuestSession(access="токен-гостя")
OTHER = GuestSession(access="токен-сусіда")

HOME = Address(label="Вінниця, вулиця Соборна, 1", latitude=49.2, longitude=28.4, id="a-1")
WORK = Address(label="Вінниця, вулиця Пирогова, 2", latitude=49.3, longitude=28.5, id="a-2")

SAVED_ROW = {
    "id": "a-1",
    "city": "Вінниця",
    "street": "вулиця Соборна",
    "building": "1",
    "latitude": 49.2,
    "longitude": 28.4,
}
FOUND_ROW = {
    "address": "Київ, вулиця Хрещатик, 30/1",
    "latitude": 50.44,
    "longitude": 30.52,
}
TYPES = {
    "options": [
        {"deliveryType": "DeliveryHome", "branchId": "b-home"},
        {"deliveryType": "SelfPickup", "branchId": None},
    ]
}
DIRECTORY = {
    "branches": [{"branchId": "b-home", "city": "Вінниця", "address": "вулиця Соборна, 46"}]
}

CART = {"silpo_get_my_shopping_cart": {"shoppingCartId": "cart-1"}}
CART_BY_ID = {"silpo_get_shopping_cart_by_id": {"cart": {"shipments": [{"branchId": "b-cart"}]}}}

LIVE = {
    "silpo_get_my_delivery_addresses": {"addresses": [SAVED_ROW]},
    "silpo_get_available_delivery_types": TYPES,
    "silpo_find_address": {"addresses": [FOUND_ROW]},
    "silpo_list_branches": DIRECTORY,
}


class _FakeMCP:

    opened = 0
    calls: ClassVar[list[str]] = []
    payloads: ClassVar[dict[str, Any]] = {}
    fails: ClassVar[dict[str, Exception]] = {}

    def __init__(self, **kwargs: Any) -> None:
        type(self).opened += 1

    async def __aenter__(self) -> _FakeMCP:
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False

    async def call(self, tool: str, arguments: dict[str, Any] | None = None) -> Any:
        type(self).calls.append(tool)
        if tool in self.fails:
            raise self.fails[tool]
        payload = self.payloads.get(tool, {})
        return type("Outcome", (), {"payload_raw": payload, "payload": payload})()


@pytest.fixture(autouse=True)
def stand(monkeypatch):
    places.forget_all()
    place_chain.forget_directory()
    _FakeMCP.opened = 0
    _FakeMCP.calls = []
    _FakeMCP.payloads = dict(LIVE)
    _FakeMCP.fails = {}
    monkeypatch.setattr(api, "SilpoMCP", _FakeMCP)
    yield _FakeMCP
    places.forget_all()
    place_chain.forget_directory()


def test_place_is_remembered_per_guest():
    mine = places.Known(location=Location(branch_id="b-mine", source=Source.ADDRESS))
    places.remember(mine, owner=GUEST.owner)

    assert places.recall(GUEST.owner) is mine
    assert places.recall(OTHER.owner) is None, "сховище одне, адреси різні"


def test_forget_drops_only_that_guest():
    places.remember(places.Known(location=Location()), owner=GUEST.owner)
    places.remember(places.Known(location=Location()), owner=OTHER.owner)

    places.forget(GUEST.owner)

    assert places.recall(GUEST.owner) is None
    assert places.recall(OTHER.owner) is not None


def test_oldest_guests_fall_out_of_memory():
    owners = [f"гість-{n}" for n in range(places.MAX_PLACES + 2)]
    for owner in owners:
        places.remember(places.Known(location=Location()), owner=owner)

    alive = [owner for owner in owners if places.recall(owner) is not None]
    assert len(alive) == places.MAX_PLACES
    assert alive == owners[-places.MAX_PLACES :]


def test_active_guest_does_not_lose_the_place_to_newcomers():
    places.remember(places.Known(location=Location()), owner="старожил")
    for n in range(places.MAX_PLACES - 1):
        places.remember(places.Known(location=Location()), owner=f"новий-{n}")

    assert places.recall("старожил") is not None
    places.remember(places.Known(location=Location()), owner="ще-один")

    assert places.recall("старожил") is not None


def test_place_says_where_and_who_collects():
    known = places.Known(
        location=Location(
            branch_id="b-home",
            source=Source.ADDRESS,
            address=HOME,
            branches={"DeliveryHome": "b-home"},
            offered=frozenset({"SelfPickup", "DeliveryHome"}),
        ),
        saved=(HOME, WORK),
        branch="Вінниця, вулиця Соборна, 46",
    )
    shown = places.to_place(known)

    assert shown.address == HOME.label
    assert shown.branch == "Вінниця, вулиця Соборна, 46"
    assert shown.branch_id == "b-home"
    assert shown.source == "address"
    assert shown.note == source_note(Source.ADDRESS)
    assert shown.delivery_types == ["DeliveryHome", "SelfPickup"], "порядок сталий"
    assert [option.id for option in shown.saved] == ["a-1", "a-2"]


def test_place_without_an_address_says_so_instead_of_guessing():
    known = places.Known(location=Location(branch_id="b-cfg", source=Source.CONFIG))
    shown = places.to_place(known)

    assert shown.address is None and shown.branch is None
    assert shown.source == "config"
    assert shown.note == source_note(Source.CONFIG)
    assert shown.delivery_types == [], "не питали — не «нічим не возять»"


async def test_where_to_walks_the_chain_once(stand):
    shown = await api.where_to(GUEST)

    assert shown.address == "Вінниця, вулиця Соборна, 1"
    assert shown.branch == "Вінниця, вулиця Соборна, 46"
    assert shown.source == "address"
    assert stand.calls == [
        "silpo_get_my_delivery_addresses",
        "silpo_get_available_delivery_types",
        "silpo_list_branches",
    ]


async def test_second_look_costs_nothing(stand):
    await api.where_to(GUEST)
    stand.calls.clear()
    opened = stand.opened

    again = await api.where_to(GUEST)

    assert again.address == "Вінниця, вулиця Соборна, 1"
    assert stand.calls == [], "ланцюжок не ганяється на кожен опит"
    assert stand.opened == opened, "і сесія «Сільпо» вдруге не відкривається"


async def test_neighbour_gets_his_own_chain(stand):
    await api.where_to(GUEST)
    stand.payloads = {**LIVE, "silpo_get_my_delivery_addresses": {"addresses": []}}

    neighbour = await api.where_to(OTHER)

    assert neighbour.address is None, "чужа адреса не дістається сусідові"


async def test_guest_without_a_saved_address_is_asked(stand):
    stand.payloads = {**LIVE, "silpo_get_my_delivery_addresses": {"addresses": []}}

    shown = await api.where_to(GUEST)

    assert shown.address is None
    assert shown.source in {"config", "none"}
    assert "адрес" in shown.note, "екран мусить сказати, чого бракує"


async def test_a_guest_without_an_address_gets_the_branch_of_his_own_cart(stand):
    stand.payloads = {
        **LIVE,
        "silpo_get_my_delivery_addresses": {"addresses": []},
        **CART,
        **CART_BY_ID,
    }

    shown = await api.where_to(GUEST)

    assert shown.source == "cart"
    assert shown.branch_id == "b-cart"


async def test_a_guest_with_an_address_is_not_charged_for_the_cart(stand):
    shown = await api.where_to(GUEST)

    assert shown.source == "address"
    assert "silpo_get_my_shopping_cart" not in stand.calls


async def test_an_account_that_never_had_a_cart_still_gets_a_screen(stand):
    stand.payloads = {**LIVE, "silpo_get_my_delivery_addresses": {"addresses": []}}
    stand.fails = {
        "silpo_get_my_shopping_cart": MCPCallError("t", "Resource not found", attempts=1)
    }

    shown = await api.where_to(GUEST)

    assert shown.source in {"config", "none"}, "кошика немає -- порядок іде далі"
    assert "адрес" in shown.note, "порада лишається дією, а не констатацією"


async def test_a_broken_cart_read_does_not_break_the_screen_either(stand):
    stand.payloads = {**LIVE, "silpo_get_my_delivery_addresses": {"addresses": []}}
    stand.fails = {"silpo_get_my_shopping_cart": MCPCallError("t", "500", attempts=4)}

    shown = await api.where_to(GUEST)

    assert shown.source in {"config", "none"}, "не прочиталось -- теж не спиняє порядок"
    assert "адрес" in shown.note


async def test_a_named_address_without_delivery_still_reaches_the_cart(stand):
    from komora.api.schemas import PlaceChoice

    stand.payloads = {
        **LIVE,
        "silpo_get_available_delivery_types": {
            "options": [{"deliveryType": "SelfPickup", "branchId": None}]
        },
        **CART,
        **CART_BY_ID,
    }

    shown = await api.choose_place(
        PlaceChoice(label="Київ, вулиця Хрещатик, 30/1", latitude=50.44, longitude=30.52),
        GUEST,
    )

    assert shown.address == "Київ, вулиця Хрещатик, 30/1", "адреса -- інше питання"
    assert (shown.source, shown.branch_id) == ("cart", "b-cart")


async def test_a_dead_token_on_the_cart_is_not_swallowed(stand):
    calls = []

    class _Dead:
        async def call(self, tool: str, arguments: Any = None) -> Any:
            calls.append(tool)
            raise TokenRejected(tool, "токен відкликано", attempts=1)

    with pytest.raises(TokenRejected):
        await api.cart_branch(_Dead())  # type: ignore[arg-type]
    assert calls == ["silpo_get_my_shopping_cart"]


async def test_a_broken_cart_is_a_missing_source_not_a_refusal(stand):

    class _Broken:
        async def call(self, tool: str, arguments: Any = None) -> Any:
            raise MCPCallError(tool, "500", attempts=4)

    assert await api.cart_branch(_Broken()) is None  # type: ignore[arg-type]


async def test_search_gives_variants_not_a_guess(stand):
    from komora.api.schemas import PlaceQuery

    found = await api.search_place(PlaceQuery(text="Київ, Хрещатик, 1"), GUEST)

    assert [option.label for option in found] == ["Київ, вулиця Хрещатик, 30/1"]
    assert found[0].id is None, "знайдена адреса в акаунті не збережена"


async def test_chosen_address_is_remembered_for_the_session(stand):
    from komora.api.schemas import PlaceChoice

    shown = await api.choose_place(
        PlaceChoice(label="Київ, вулиця Хрещатик, 30/1", latitude=50.44, longitude=30.52),
        GUEST,
    )

    assert shown.address == "Київ, вулиця Хрещатик, 30/1"
    assert shown.source == "address" and shown.branch_id == "b-home"

    known = places.recall(GUEST.owner)
    assert known is not None and known.location.address is not None
    assert known.location.address.label == "Київ, вулиця Хрещатик, 30/1"


async def test_choosing_keeps_the_account_addresses_in_the_picker(stand):
    from komora.api.schemas import PlaceChoice

    await api.where_to(GUEST)
    shown = await api.choose_place(
        PlaceChoice(label="Київ, вулиця Хрещатик, 30/1", latitude=50.44, longitude=30.52),
        GUEST,
    )

    assert [option.label for option in shown.saved] == ["Вінниця, вулиця Соборна, 1"]


async def test_broken_chain_shows_an_honest_screen_not_a_crash(stand):
    stand.fails = {
        "silpo_get_my_delivery_addresses": MCPCallError("t", "500", attempts=4),
        "silpo_list_branches": MCPCallError("t", "500", attempts=4),
    }

    shown = await api.where_to(GUEST)

    assert shown.address is None and shown.branch is None
    assert shown.source != "address"


async def test_a_failed_search_is_a_refusal_not_an_empty_result(stand):
    from komora.api.schemas import PlaceQuery

    stand.fails = {"silpo_find_address": MCPCallError("t", "500", attempts=4)}

    with pytest.raises(HTTPException) as exc:
        await api.search_place(PlaceQuery(text="Київ"), GUEST)
    assert exc.value.status_code == 503
    assert "Сільпо" in str(exc.value.detail), "гість мусить знати, кому дзвонити"


async def test_address_survives_a_broken_branch_lookup(stand):
    from komora.api.schemas import PlaceChoice

    stand.fails = {"silpo_get_available_delivery_types": MCPCallError("t", "500", attempts=4)}
    shown = await api.choose_place(
        PlaceChoice(label="Київ, Хрещатик", latitude=50.44, longitude=30.52), GUEST
    )

    assert shown.address == "Київ, Хрещатик"
    assert shown.source != "address"


async def test_logout_forgets_where_we_were_taking_it():
    places.remember(places.Known(location=Location()), owner=GUEST.owner)
    places.forget(GUEST.owner)
    assert places.recall(GUEST.owner) is None


async def test_place_endpoints_need_a_guest():
    from komora.api.auth_routes import require_guest

    class _NoCookie:
        cookies: ClassVar[dict[str, str]] = {}

    with pytest.raises(HTTPException) as exc:
        await require_guest(_NoCookie())  # type: ignore[arg-type]
    assert exc.value.status_code == 401
