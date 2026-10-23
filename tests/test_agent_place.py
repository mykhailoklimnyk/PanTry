from __future__ import annotations

from typing import Any

import pytest
from structlog.testing import capture_logs

from komora.agent import place
from komora.config import Settings
from komora.core.location import Address, Source
from komora.mcp.client import MCPCallError, TokenRejected

SAVED = {
    "id": "4142a36a-ca2c-4fab-a9c4-5dc0be0b8eeb",
    "tag": None,
    "city": "Вінниця",
    "street": "вулиця Соборна",
    "building": "1",
    "apartment": "2",
    "floor": "3",
    "entrance": "2",
    "latitude": 49.2214923,
    "longitude": 28.45801761068094,
    "comment": "Соборна 1, кв 2",
}

FOUND = {
    "address": "Київ, вулиця Хрещатик, 30/1",
    "city": "Київ",
    "street": "вулиця Хрещатик",
    "houseNumber": "30/1",
    "district": "Центр",
    "latitude": 50.44747065,
    "longitude": 30.521505797601343,
}

TYPES = {
    "options": [
        {"deliveryType": "DeliveryHome", "branchId": "b-home", "description": "Regular delivery"},
        {"deliveryType": "NovaPoshta", "branchId": None, "description": "Nova Poshta"},
        {"deliveryType": "SelfPickup", "branchId": None, "description": "Self pickup"},
    ]
}

CONFIG = Settings(branch_id="b-config", _env_file=None)  # type: ignore[call-arg]

HERE = Address(label="дім", latitude=1.0, longitude=2.0)


class _FakeMCP:

    def __init__(
        self,
        payloads: dict[str, Any] | None = None,
        fails: dict[str, Exception] | None = None,
    ) -> None:
        self.payloads = payloads or {}
        self.fails = fails or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call(self, tool: str, arguments: dict[str, Any] | None = None) -> Any:
        self.calls.append((tool, arguments or {}))
        if tool in self.fails:
            raise self.fails[tool]
        payload = self.payloads.get(tool, {})
        return type("Outcome", (), {"payload_raw": payload, "payload": payload})()

    @property
    def tools(self) -> list[str]:
        return [name for name, _ in self.calls]


def _mcp(**payloads: Any) -> Any:
    return _FakeMCP(payloads)


@pytest.fixture(autouse=True)
def clean_directory():
    place.forget_directory()
    yield
    place.forget_directory()


def test_saved_address_keeps_building_and_apartment():
    address = place.address_from_saved(SAVED)
    assert address is not None
    assert address.label == "Вінниця, вулиця Соборна, 1, кв. 2"
    assert address.id == SAVED["id"]
    assert (address.latitude, address.longitude) == (SAVED["latitude"], SAVED["longitude"])


def test_saved_address_without_coordinates_is_not_an_address():
    assert place.address_from_saved({**SAVED, "latitude": None}) is None


def test_broken_coordinates_do_not_crash_the_chain():
    assert place.address_from_saved({**SAVED, "longitude": "не число"}) is None


def test_saved_address_survives_without_any_words():
    address = place.address_from_saved({"latitude": 1.0, "longitude": 2.0})
    assert address is not None and address.label == "адреса без назви"


def test_found_address_uses_the_ready_line():
    address = place.address_from_found(FOUND)
    assert address is not None and address.label == "Київ, вулиця Хрещатик, 30/1"
    assert address.id is None


def test_found_address_without_a_house_number_is_not_confirmed():
    street = place.address_from_found(
        {**FOUND, "address": "Київ, вулиця Хрещатик", "houseNumber": None}
    )
    assert street is not None and street.confirmed is False and street.house is None
    exact = place.address_from_found(FOUND)
    assert exact is not None and exact.confirmed is True and exact.house == "30/1"


def test_saved_address_is_confirmed_even_without_a_building():
    address = place.address_from_saved({**SAVED, "building": None})
    assert address is not None and address.confirmed is True


def test_found_address_falls_back_to_parts():
    address = place.address_from_found({**FOUND, "address": "  "})
    assert address is not None and address.label == "Київ, вулиця Хрещатик, 30/1"


def test_found_address_without_words_at_all_is_dropped():
    assert place.address_from_found({"latitude": 1.0, "longitude": 2.0}) is None


def test_found_address_without_coordinates_is_dropped_too():
    assert place.address_from_found({**FOUND, "latitude": None}) is None


async def test_saved_addresses_read_the_account():
    mcp = _mcp(silpo_get_my_delivery_addresses={"addresses": [SAVED]})
    found = await place.saved_addresses(mcp)
    assert [a.label for a in found] == ["Вінниця, вулиця Соборна, 1, кв. 2"]
    assert mcp.tools == [place.ADDRESSES_TOOL]


async def test_account_without_addresses_is_a_normal_state():
    assert await place.saved_addresses(_mcp(silpo_get_my_delivery_addresses={})) == []


async def test_garbage_rows_are_skipped_not_crashed_on():
    mcp = _mcp(silpo_get_my_delivery_addresses={"addresses": ["рядок", None, SAVED]})
    assert len(await place.saved_addresses(mcp)) == 1


async def test_failed_addresses_call_degrades_to_empty():
    mcp = _FakeMCP(fails={place.ADDRESSES_TOOL: MCPCallError("t", "500", attempts=4)})
    assert await place.saved_addresses(mcp) == []


async def test_dead_token_is_not_swallowed():
    mcp = _FakeMCP(fails={place.ADDRESSES_TOOL: TokenRejected("t", "401", attempts=1)})
    with pytest.raises(TokenRejected):
        await place.saved_addresses(mcp)


async def test_search_returns_all_variants():
    mcp = _mcp(silpo_find_address={"addresses": [FOUND, {**FOUND, "address": "Боярка, 1"}]})
    found = await place.search_addresses(mcp, "Київ, Хрещатик, 1")
    assert [a.label for a in found] == ["Київ, вулиця Хрещатик, 30/1", "Боярка, 1"]
    assert mcp.calls[0][1] == {"address": "Київ, Хрещатик, 1"}


async def test_empty_query_never_leaves_the_process():
    mcp = _mcp(silpo_find_address={"addresses": [FOUND]})
    assert await place.search_addresses(mcp, "   ") == []
    assert mcp.tools == []


async def test_failed_search_is_a_refusal_not_an_empty_list():
    mcp = _FakeMCP(fails={place.SEARCH_TOOL: MCPCallError("t", "500", attempts=4)})
    with pytest.raises(MCPCallError):
        await place.search_addresses(mcp, "Київ")


async def test_failed_search_still_reports_a_dead_token():
    mcp = _FakeMCP(fails={place.SEARCH_TOOL: TokenRejected("t", "401", attempts=1)})
    with pytest.raises(TokenRejected):
        await place.search_addresses(mcp, "Київ")


async def test_branches_come_per_delivery_type():
    mcp = _mcp(silpo_get_available_delivery_types=TYPES)
    branches, offered = await place.branches_at(mcp, HERE)
    assert branches == {"DeliveryHome": "b-home"}
    assert offered == frozenset({"DeliveryHome", "NovaPoshta", "SelfPickup"})
    assert mcp.calls[0][1] == {"latitude": 1.0, "longitude": 2.0}


async def test_null_branch_is_offered_but_not_chosen_for_the_guest():
    mcp = _mcp(silpo_get_available_delivery_types=TYPES)
    branches, offered = await place.branches_at(mcp, HERE)
    assert "SelfPickup" not in branches and "SelfPickup" in (offered or frozenset())


async def test_options_garbage_is_skipped():
    mcp = _mcp(
        silpo_get_available_delivery_types={
            "options": ["щось", {"branchId": "b"}, *TYPES["options"]]
        }
    )
    branches, offered = await place.branches_at(mcp, HERE)
    assert branches == {"DeliveryHome": "b-home"} and len(offered or ()) == 3


async def test_dead_token_on_types_is_not_swallowed_either():
    mcp = _FakeMCP(fails={place.TYPES_TOOL: TokenRejected("t", "401", attempts=1)})
    with pytest.raises(TokenRejected):
        await place.branches_at(mcp, HERE)


async def test_failed_types_call_says_unknown_not_nothing():
    mcp = _FakeMCP(fails={place.TYPES_TOOL: MCPCallError("t", "500", attempts=4)})
    branches, offered = await place.branches_at(mcp, HERE)
    assert branches == {} and offered is None


async def test_branch_comes_from_the_account_address():
    mcp = _mcp(
        silpo_get_my_delivery_addresses={"addresses": [SAVED]},
        silpo_get_available_delivery_types=TYPES,
    )
    location = await place.resolve(mcp, settings=CONFIG, cart_branch="b-cart")
    assert (location.branch_id, location.source) == ("b-home", Source.ADDRESS)
    assert location.address is not None and location.address.label.startswith("Вінниця")
    assert mcp.tools == [place.ADDRESSES_TOOL, place.TYPES_TOOL]


async def test_address_in_hand_saves_a_call():
    mcp = _mcp(silpo_get_available_delivery_types=TYPES)
    location = await place.resolve(mcp, settings=CONFIG, address=HERE)
    assert location.branch_id == "b-home"
    assert mcp.tools == [place.TYPES_TOOL]


async def test_guest_choice_among_saved_addresses_is_respected():
    second = {**SAVED, "id": "a-2", "street": "вулиця Пирогова", "building": "2", "apartment": None}
    mcp = _mcp(
        silpo_get_my_delivery_addresses={"addresses": [SAVED, second]},
        silpo_get_available_delivery_types=TYPES,
    )
    location = await place.resolve(mcp, settings=CONFIG, preferred_id="a-2")
    assert location.address is not None
    assert location.address.label == "Вінниця, вулиця Пирогова, 2"


async def test_without_address_the_cart_branch_is_next():
    mcp = _mcp(silpo_get_my_delivery_addresses={"addresses": []})
    location = await place.resolve(mcp, settings=CONFIG, cart_branch="b-cart")
    assert (location.branch_id, location.source) == ("b-cart", Source.CART)
    assert location.address is None
    assert mcp.tools == [place.ADDRESSES_TOOL]


async def test_without_anything_config_is_named_out_loud():
    mcp = _mcp(silpo_get_my_delivery_addresses={"addresses": []})
    location = await place.resolve(mcp, settings=CONFIG)
    assert (location.branch_id, location.source) == ("b-config", Source.CONFIG)


async def test_no_config_at_all_leaves_the_branch_unknown():
    mcp = _mcp(silpo_get_my_delivery_addresses={"addresses": []})
    location = await place.resolve(mcp, settings=Settings(branch_id=None, _env_file=None))  # type: ignore[call-arg]
    assert location.known is False and location.source is Source.NONE


async def test_the_cart_is_asked_only_when_the_address_gave_nothing():
    asked = 0

    async def cart() -> str | None:
        nonlocal asked
        asked += 1
        return "b-cart"

    mcp = _mcp(silpo_get_my_delivery_addresses={"addresses": []})
    location = await place.resolve(mcp, settings=CONFIG, ask_cart=cart)

    assert (location.branch_id, location.source) == ("b-cart", Source.CART)
    assert asked == 1


async def test_a_guest_with_an_address_never_pays_for_the_cart():
    asked = 0

    async def cart() -> str | None:
        nonlocal asked
        asked += 1
        return "b-cart"

    mcp = _mcp(
        silpo_get_my_delivery_addresses={"addresses": [SAVED]},
        silpo_get_available_delivery_types=TYPES,
    )
    location = await place.resolve(mcp, settings=CONFIG, ask_cart=cart)

    assert (location.branch_id, location.source) == ("b-home", Source.ADDRESS)
    assert asked == 0


async def test_a_cart_branch_in_hand_is_not_asked_for_twice():
    asked = 0

    async def cart() -> str | None:
        nonlocal asked
        asked += 1
        return "b-inne"

    mcp = _mcp(silpo_get_my_delivery_addresses={"addresses": []})
    location = await place.resolve(mcp, settings=CONFIG, cart_branch="b-cart", ask_cart=cart)

    assert location.branch_id == "b-cart"
    assert asked == 0


async def test_an_empty_cart_answer_falls_through_to_the_config():

    async def cart() -> str | None:
        return None

    mcp = _mcp(silpo_get_my_delivery_addresses={"addresses": []})
    location = await place.resolve(mcp, settings=CONFIG, ask_cart=cart)

    assert (location.branch_id, location.source) == ("b-config", Source.CONFIG)


async def test_an_address_that_only_offers_pickup_still_reaches_the_cart():
    asked = 0

    async def cart() -> str | None:
        nonlocal asked
        asked += 1
        return "b-cart"

    mcp = _mcp(
        silpo_get_my_delivery_addresses={"addresses": [SAVED]},
        silpo_get_available_delivery_types={
            "options": [{"deliveryType": "SelfPickup", "branchId": None}]
        },
    )
    location = await place.resolve(mcp, settings=CONFIG, ask_cart=cart)

    assert (location.branch_id, location.source) == ("b-cart", Source.CART)
    assert location.address is not None, "адреса лишається: це інше питання"
    assert asked == 1


async def test_address_survives_a_failed_types_call():
    mcp = _FakeMCP(
        payloads={place.ADDRESSES_TOOL: {"addresses": [SAVED]}},
        fails={place.TYPES_TOOL: MCPCallError("t", "500", attempts=4)},
    )
    location = await place.resolve(mcp, settings=CONFIG, cart_branch="b-cart")
    assert (location.branch_id, location.source) == ("b-cart", Source.CART)
    assert location.address is not None


DIRECTORY = {
    "branches": [
        {"branchId": "b-home", "city": "Вінниця", "address": "вулиця Соборна, 46"},
        {"branchId": "b-other", "city": "Київ", "address": "вулиця Хрещатик, 1"},
        {"city": "Львів", "address": "без id"},
    ],
    "meta": {"limit": 500, "offset": 0, "total": 3},
}


class _PagedBranches:

    def __init__(self, rows: list[dict[str, Any]], *, total: int | None = None) -> None:
        self.rows = rows
        self.total = len(rows) if total is None else total
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def call(self, tool: str, arguments: dict[str, Any] | None = None) -> Any:
        args = arguments or {}
        self.calls.append((tool, args))
        limit = int(args.get("limit", 50))
        offset = int(args.get("offset", 0))
        payload = {
            "branches": self.rows[offset : offset + limit],
            "meta": {"limit": limit, "offset": offset, "total": self.total},
        }
        return type("Outcome", (), {"payload_raw": payload, "payload": payload})()


def _rows(count: int) -> list[dict[str, Any]]:
    return [{"branchId": f"b-{i}", "city": "Київ", "address": f"вулиця {i}"} for i in range(count)]


async def test_the_directory_is_asked_with_the_ceiling_of_its_own_schema():
    mcp = _mcp(silpo_list_branches=DIRECTORY)
    await place.branch_label(mcp, "b-home")
    _, arguments = mcp.calls[0]
    assert arguments.get("limit") == place.BRANCH_PAGE


async def test_the_whole_directory_comes_back_page_by_page(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(place, "BRANCH_PAGE", 3)
    mcp = _PagedBranches(_rows(7))
    got = await place.all_branches(mcp)  # type: ignore[arg-type]

    assert [row["branchId"] for row in got] == [f"b-{i}" for i in range(7)]
    assert [args["offset"] for _, args in mcp.calls] == [0, 3, 6]


async def test_the_second_page_is_not_asked_blind():
    mcp = _PagedBranches(_rows(455))
    await place.all_branches(mcp)  # type: ignore[arg-type]
    assert len(mcp.calls) == 1


async def test_an_unreadable_row_does_not_shift_the_window():
    mcp = _PagedBranches([*_rows(2), "не рядок"])  # type: ignore[list-item]
    got = await place.all_branches(mcp)  # type: ignore[arg-type]

    assert [row["branchId"] for row in got] == ["b-0", "b-1"]
    assert len(mcp.calls) == 1


async def test_a_directory_that_does_not_fit_says_so():
    mcp = _PagedBranches(_rows(4), total=99)
    with capture_logs() as written:
        got = await place.all_branches(mcp)  # type: ignore[arg-type]

    assert len(got) == 4
    assert [line["event"] for line in written] == ["place.branches_capped"]
    assert [line["got"] for line in written] == [4]
    assert [line["total"] for line in written] == [99]


async def test_the_page_ceiling_stops_an_api_that_never_ends(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(place, "BRANCH_PAGE", 2)
    mcp = _PagedBranches(_rows(100), total=1000)
    with capture_logs() as written:
        got = await place.all_branches(mcp)  # type: ignore[arg-type]

    assert len(mcp.calls) == place.MAX_BRANCH_PAGES
    assert len(got) == 2 * place.MAX_BRANCH_PAGES
    assert [line["event"] for line in written] == ["place.branches_capped"]


async def test_branch_label_is_human():
    mcp = _mcp(silpo_list_branches=DIRECTORY)
    assert await place.branch_label(mcp, "b-home") == "Вінниця, вулиця Соборна, 46"


async def test_directory_is_fetched_once_per_process():
    mcp = _mcp(silpo_list_branches=DIRECTORY)
    await place.branch_label(mcp, "b-home")
    await place.branch_label(mcp, "b-other")
    assert mcp.tools == [place.BRANCHES_TOOL]


async def test_unknown_branch_has_no_name():
    mcp = _mcp(silpo_list_branches=DIRECTORY)
    assert await place.branch_label(mcp, "b-missing") is None


async def test_no_branch_no_call():
    mcp = _mcp(silpo_list_branches=DIRECTORY)
    assert await place.branch_label(mcp, None) is None
    assert mcp.tools == []


async def test_dead_token_on_the_directory_is_not_swallowed():
    mcp = _FakeMCP(fails={place.BRANCHES_TOOL: TokenRejected("t", "401", attempts=1)})
    with pytest.raises(TokenRejected):
        await place.branch_label(mcp, "b-home")


async def test_failed_directory_is_silent_and_not_cached():
    mcp = _FakeMCP(fails={place.BRANCHES_TOOL: MCPCallError("t", "500", attempts=4)})
    assert await place.branch_label(mcp, "b-home") is None

    working = _mcp(silpo_list_branches=DIRECTORY)
    assert await place.branch_label(working, "b-home") == "Вінниця, вулиця Соборна, 46"
