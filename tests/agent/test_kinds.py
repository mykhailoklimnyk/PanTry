from __future__ import annotations

from typing import Any

import pytest

from komora.agent import kinds
from komora.core.dictionary import Dictionary, Node
from komora.mcp.client import MCPCallError, TokenRejected

SLOT = {
    "start": "2026-08-17T07:00:00+00:00",
    "end": "2026-08-17T08:30:00+00:00",
    "deliveryType": "DeliveryHome",
}
BRANCH = "branch-1"

TREE = Dictionary(
    [
        Node("meat", "М'ясо", None, "miaso-1"),
        Node("pork", "Свинина", "meat", "svynyna-4413"),
        Node("bbq", "М'ясо для шашлику та барбекю", "meat", "shashlyk-4414"),
        Node("water", "Мінеральна вода", None, "mineralna-voda-5091"),
    ]
)


def product(pid: int, name: str, *, available: bool = True) -> dict[str, Any]:
    return {
        "externalProductId": pid,
        "name": name,
        "price": 100.0,
        "stock": 5,
        "available": available,
    }


class _Outcome:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload_raw = payload
        self.duration_ms = 7


class _MCP:

    def __init__(
        self, by_slug: dict[str, list[dict[str, Any]]], *, fail: str | None = None
    ) -> None:
        self._by_slug = by_slug
        self._fail = fail
        self.calls: list[dict[str, Any]] = []

    async def call(self, tool: str, arguments: dict[str, Any] | None = None) -> _Outcome:
        args = arguments or {}
        self.calls.append(args)
        if self._fail == "dead":
            raise TokenRejected(tool, "токен відкликано", attempts=1)
        if self._fail == "flaky":
            raise MCPCallError(tool, "500", attempts=4)
        return _Outcome({"products": self._by_slug.get(args.get("category", ""), [])})


async def test_word_is_narrowed_to_its_kind():
    mcp = _MCP({"svynyna-4413": [product(1, "Свинячий ошийок")]})

    found, ms = await kinds.narrow(
        mcp, ["свинина"], slot=SLOT, branch_id=BRANCH, tree=TREE  # type: ignore[arg-type]
    )

    assert list(found) == ["свинина"]
    assert found["свинина"].title == "Свинина"
    assert [p["name"] for p in found["свинина"].products] == ["Свинячий ошийок"]
    assert ms == 14, "вид плюс сусідній вузол про готове — два виклики"


async def test_the_call_asks_by_slug_in_stock_and_by_popularity():
    mcp = _MCP({"svynyna-4413": []})
    await kinds.narrow(mcp, ["свинина"], slot=SLOT, branch_id=BRANCH, tree=TREE)  # type: ignore[arg-type]

    args = mcp.calls[0]
    assert args["category"] == "svynyna-4413", "categoryId цей tool не розуміє"
    assert args["inStock"] is True
    assert args["sortBy"] == "popularity", "рейтинг магазину всередині виду"
    assert args["branchId"] == BRANCH
    assert args["timeslotStart"] == SLOT["start"]


async def test_empty_kind_is_a_third_state_not_a_miss():
    mcp = _MCP({"svynyna-4413": []})
    found, _ = await kinds.narrow(mcp, ["свинина"], slot=SLOT, branch_id=BRANCH, tree=TREE)  # type: ignore[arg-type]

    assert found["свинина"].empty is True

    candidates: dict[str, list[dict[str, Any]]] = {}
    added, empty = kinds.merge(candidates, found)
    assert added == 0
    assert empty == ["свинина"]
    assert candidates == {}, "порожній вид не має створювати порожній намір"


async def test_unavailable_products_do_not_travel():
    mcp = _MCP({"svynyna-4413": [product(1, "Є"), product(2, "Нема", available=False)]})
    found, _ = await kinds.narrow(mcp, ["свинина"], slot=SLOT, branch_id=BRANCH, tree=TREE)  # type: ignore[arg-type]
    assert [p["name"] for p in found["свинина"].products] == ["Є"]


async def test_word_outside_the_tree_costs_no_call():
    mcp = _MCP({})
    found, ms = await kinds.narrow(
        mcp, ["полуниця"], slot=SLOT, branch_id=BRANCH, tree=TREE  # type: ignore[arg-type]
    )
    assert found == {} and ms == 0
    assert mcp.calls == [], "слова немає в дереві — питати нема про що"


async def test_number_of_kinds_is_capped():
    tree = Dictionary(
        [Node(f"n{i}", f"Вид{i}", None, f"vyd-{i}") for i in range(kinds.MAX_KINDS + 5)]
    )
    mcp = _MCP({f"vyd-{i}": [product(i, f"Товар {i}")] for i in range(kinds.MAX_KINDS + 5)})

    found, _ = await kinds.narrow(
        mcp,  # type: ignore[arg-type]
        [f"вид{i}" for i in range(kinds.MAX_KINDS + 5)],
        slot=SLOT,
        branch_id=BRANCH,
        tree=tree,
    )

    assert len(found) == kinds.MAX_KINDS
    assert len(mcp.calls) == kinds.MAX_KINDS


async def test_a_broken_listing_does_not_break_the_basket():
    mcp = _MCP({}, fail="flaky")
    found, _ = await kinds.narrow(mcp, ["свинина"], slot=SLOT, branch_id=BRANCH, tree=TREE)  # type: ignore[arg-type]
    assert found == {}, "перелік не відповів — збірка йде далі без звуження"


async def test_a_dead_token_is_not_swallowed():
    mcp = _MCP({}, fail="dead")
    with pytest.raises(TokenRejected):
        await kinds.narrow(mcp, ["свинина"], slot=SLOT, branch_id=BRANCH, tree=TREE)  # type: ignore[arg-type]


def test_merge_adds_and_never_replaces():
    candidates = {"свинина": [product(1, "Свинячі реберця в маринаді")]}
    kind = kinds.Kind(
        word="свинина",
        title="Свинина",
        slug="svynyna-4413",
        products=[product(2, "Свинячий ошийок")],
    )

    added, empty = kinds.merge(candidates, {"свинина": kind})

    assert added == 1 and empty == []
    names = [p["name"] for p in candidates["свинина"]]
    assert names == ["Свинячі реберця в маринаді", "Свинячий ошийок"], (
        "знайдене пошуком лишається: словник теж помиляється"
    )


def test_merge_does_not_duplicate_what_search_already_found():
    same = product(1, "Свинячий ошийок")
    candidates = {"свинина": [same]}
    kind = kinds.Kind("свинина", "Свинина", "svynyna-4413", [dict(same)])

    added, _ = kinds.merge(candidates, {"свинина": kind})

    assert added == 0
    assert len(candidates["свинина"]) == 1


class _TreeMCP:
    def __init__(self, *, fail: bool = False, nodes: int = 2) -> None:
        self.fail = fail
        self.nodes = nodes
        self.calls = 0

    async def call(self, tool: str, arguments: dict[str, Any] | None = None) -> _Outcome:
        self.calls += 1
        if self.fail:
            raise MCPCallError(tool, "500", attempts=4)
        return _Outcome(
            {
                "categories": [
                    {"id": f"c{i}", "title": f"Вид{i}", "slug": f"vyd-{i}"}
                    for i in range(self.nodes)
                ],
                "meta": {"total": self.nodes},
            }
        )


async def test_tree_is_fetched_once_per_process():
    mcp = _TreeMCP()
    first = await kinds.load_tree(mcp, branch_id=BRANCH)  # type: ignore[arg-type]
    second = await kinds.load_tree(mcp, branch_id=BRANCH)  # type: ignore[arg-type]

    assert first is second
    assert mcp.calls == 1, "дерево однакове на всіх філіях — двічі його не питають"

    kinds.forget_tree()
    await kinds.load_tree(mcp, branch_id=BRANCH)  # type: ignore[arg-type]
    assert mcp.calls == 2


async def test_no_tree_is_not_an_error():
    mcp = _TreeMCP(fail=True)
    assert await kinds.load_tree(mcp, branch_id=BRANCH) is None  # type: ignore[arg-type]


async def test_empty_tree_is_not_cached_as_a_tree():
    mcp = _TreeMCP(nodes=0)
    assert await kinds.load_tree(mcp, branch_id=BRANCH) is None  # type: ignore[arg-type]
    await kinds.load_tree(mcp, branch_id=BRANCH)  # type: ignore[arg-type]
    assert mcp.calls == 2, "порожнє не кешується: наступний прогін пробує знову"


async def test_prepared_is_taken_from_the_neighbour_node():
    ribs = product(1, "Свинячі реберця в маринаді")
    raw = product(2, "Свиняча грудинка охолоджена")
    mcp = _MCP({"svynyna-4413": [ribs, raw], "shashlyk-4414": [dict(ribs)]})

    found, _ = await kinds.narrow(
        mcp, ["свинина"], slot=SLOT, branch_id=BRANCH, tree=TREE  # type: ignore[arg-type]
    )

    assert found["свинина"].also_in == {"1": ("М'ясо для шашлику та барбекю",)}
    assert len(mcp.calls) == 2
    assert mcp.calls[1]["category"] == "shashlyk-4414"


async def test_asking_for_the_prepared_kind_costs_no_extra_call():
    mcp = _MCP({"shashlyk-4414": [product(1, "Шашлик свинячий")]})

    found, _ = await kinds.narrow(
        mcp, ["шашлику"], slot=SLOT, branch_id=BRANCH, tree=TREE  # type: ignore[arg-type]
    )

    assert found["шашлику"].also_in == {}
    assert len(mcp.calls) == 1


async def test_sibling_lookups_are_capped_per_run():
    nodes = [Node("root", "Корінь", None, "root-0")]
    for i in range(6):
        nodes.append(Node(f"raw{i}", f"Вид{i}", "root", f"vyd-{i}"))
        nodes.append(Node(f"prep{i}", f"Напівфабрикати {i}", "root", f"prep-{i}"))
    tree = Dictionary(nodes)
    mcp = _MCP({f"vyd-{i}": [product(i, f"Товар {i}")] for i in range(6)})

    await kinds.narrow(
        mcp,  # type: ignore[arg-type]
        [f"вид{i}" for i in range(6)],
        slot=SLOT,
        branch_id=BRANCH,
        tree=tree,
    )

    siblings = [c for c in mcp.calls if c["category"].startswith("prep-")]
    assert len(siblings) == kinds.MAX_PREPARED


async def test_empty_kind_does_not_ask_neighbours():
    mcp = _MCP({"svynyna-4413": []})
    await kinds.narrow(mcp, ["свинина"], slot=SLOT, branch_id=BRANCH, tree=TREE)  # type: ignore[arg-type]
    assert len(mcp.calls) == 1


READINGS = Dictionary(
    [
        Node("hard", "Сири", None, "syry"),
        Node("cream", "Крем-сири", "hard", "krem-syry"),
        Node("dairy", "Молочні продукти", None, "dairy"),
        Node("curd", "Сир кисломолочний", "dairy", "syr-kyslo"),
    ]
)


async def test_readings_travel_to_the_agent():
    mcp = _MCP({"syry": [product(1, "Сир Гауда")]})

    found, _ = await kinds.narrow(
        mcp, ["сир"], slot=SLOT, branch_id=BRANCH, tree=READINGS  # type: ignore[arg-type]
    )

    assert found["сир"].title == "Сири"
    assert found["сир"].readings == ("Сир кисломолочний",)
    assert "Крем-сири" not in found["сир"].readings, "діти вузла — уточнення, не прочитання"


async def test_empty_reading_gives_way_to_the_next_one():
    tree = Dictionary(
        [
            Node("cbd", "Олія CBD", None, "oliia-cbd"),
            Node("oil", "Олія та оцет", None, "oliia-ta-otset"),
        ]
    )
    mcp = _MCP({"oliia-cbd": [], "oliia-ta-otset": [product(7, "Олія соняшникова")]})

    found, _ = await kinds.narrow(
        mcp, ["олія"], slot=SLOT, branch_id=BRANCH, tree=tree  # type: ignore[arg-type]
    )

    assert found["олія"].title == "Олія та оцет"
    assert found["олія"].empty is False
    assert [c["category"] for c in mcp.calls] == ["oliia-cbd", "oliia-ta-otset"]


async def test_probing_the_next_reading_is_capped():
    tree = Dictionary(
        [Node(f"n{i}", f"Вода {i}" if i else "Вода", None, f"voda-{i}") for i in range(3)]
    )
    mcp = _MCP({})
    found, _ = await kinds.narrow(
        mcp, ["вода"], slot=SLOT, branch_id=BRANCH, tree=tree  # type: ignore[arg-type]
    )
    assert len(mcp.calls) == kinds.MAX_PROBES
    assert found["вода"].empty is True, "усі прочитання порожні — це справді порожньо"


async def test_silence_of_the_network_is_not_an_empty_kind():
    mcp = _MCP({}, fail="flaky")
    found, _ = await kinds.narrow(
        mcp, ["сир"], slot=SLOT, branch_id=BRANCH, tree=READINGS  # type: ignore[arg-type]
    )
    assert found == {}


async def test_the_answer_of_the_guest_ends_the_choice():
    mcp = _MCP({"syr-kyslo": [product(2, "Сир кисломолочний 5%")]})

    found, _ = await kinds.narrow(
        mcp,  # type: ignore[arg-type]
        ["сир"],
        slot=SLOT,
        branch_id=BRANCH,
        tree=READINGS,
        chosen={"сир": "syr-kyslo"},
    )

    assert found["сир"].title == "Сир кисломолочний"
    assert found["сир"].readings == ()
    assert [c["category"] for c in mcp.calls] == ["syr-kyslo"]


def test_an_unknown_slug_falls_back_to_the_usual_reading():
    assert [n.id for n in kinds.nodes_for(READINGS, "сир", {"сир": "немає-такого"})] == [
        "hard",
        "curd",
    ]
    assert [n.id for n in kinds.nodes_for(READINGS, "сир", {"інше": "syr-kyslo"})] == [
        "hard",
        "curd",
    ]
