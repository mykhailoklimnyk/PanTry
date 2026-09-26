from __future__ import annotations

from decimal import Decimal
from typing import Any

from komora.agent import clarify
from komora.core.dictionary import Dictionary, Node

SLOT = {
    "start": "2026-08-17T07:00:00+00:00",
    "end": "2026-08-17T08:30:00+00:00",
    "deliveryType": "DeliveryHome",
}
BRANCH = "branch-1"

WATER_ASK = "Яку воду взяти: солодку, негазовану чи мінеральну?"
CHEESE_ASK = "Тобі сир твердий, кисломолочний чи з пліснявою?"
PORK_ASK = "Свинину брати сиру чи вже мариновану?"
SPRING_ASK = "Тобі яку джерельну воду?"

COFFEE_TREE = Dictionary(
    [
        Node("coffee", "Кава", None, "kava"),
        Node("beans", "Кава в зернах", "coffee", "kava-v-zernah"),
        Node("caps", "Кава в капсулах", "coffee", "kava-v-kapsulah"),
        Node("cava", "Кава (Cava)", None, "kava-cava"),
        Node("cold", "Холодні чаї та кава", None, "holodni-chai"),
    ]
)
COFFEE_ASK = "Яку каву вам взяти: розчинну, мелену чи зернову?"

TREE = Dictionary(
    [
        Node("water", "Вода", "drinks", "voda-5087"),
        Node("drinks", "Напої", None, "napoi"),
        Node("still", "Негазована вода", "water", "negazovana-voda"),
        Node("mineral", "Мінеральна вода", "water", "mineralna-voda"),
        Node("sweet", "Солодка вода", "drinks", "solodka-voda"),
    ]
)

CHEESE_TREE = Dictionary(
    [
        Node("cheese", "Сири", "milk", "syry"),
        Node("milk", "Молочні продукти", None, "molochni"),
        Node("hard", "Сири тверді", "cheese", "syry-tverdi"),
        Node("blue", "Сири з пліснявою", "cheese", "syry-plisniava"),
        Node("curd", "Сир кисломолочний", "milk", "syr-kyslomolochnyi"),
    ]
)


def product(pid: int, price: float, **extra: Any) -> dict[str, Any]:
    return {
        "externalProductId": pid,
        "name": f"Вода {pid}",
        "price": price,
        "available": True,
        "displayRatio": extra.pop("ratio", "1500мл"),
        "weighted": extra.pop("weighted", False),
        "step": 1,
        **extra,
    }


class _Outcome:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload_raw = payload
        self.duration_ms = 5


class _MCP:
    def __init__(self, by_slug: dict[str, list[dict[str, Any]]]) -> None:
        self._by_slug = by_slug
        self.calls: list[str] = []

    async def call(self, tool: str, arguments: dict[str, Any] | None = None) -> _Outcome:
        args = arguments or {}
        self.calls.append(args.get("category", ""))
        return _Outcome({"products": self._by_slug.get(args.get("category", ""), [])})


def _search(by_query: dict[str, list[dict[str, Any]]], *, calls: list[list[str]] | None = None):

    async def run(
        mcp: Any, queries: list[str], slot: dict[str, Any], branch_id: str | None
    ) -> tuple[dict[str, list[dict[str, Any]]], int]:
        if calls is not None:
            calls.append(list(queries))
        return {query: by_query.get(query, []) for query in queries}, 7

    return run


def test_readings_come_before_refinements() -> None:
    assert [node.id for node in clarify.option_nodes(TREE, "вода", WATER_ASK)] == [
        "sweet",
        "still",
        "mineral",
    ]


def test_the_node_that_repeats_the_word_is_not_an_answer() -> None:
    nodes, dropped, aside = clarify.tree_nodes(CHEESE_TREE, "сир", CHEESE_ASK)
    assert (dropped, aside) == (1, 0)
    assert [node.title for node in nodes] == [
        "Сир кисломолочний",
        "Сири тверді",
        "Сири з пліснявою",
    ]


def test_word_outside_the_tree_has_nothing_to_offer() -> None:
    assert clarify.option_nodes(TREE, "полуниця", "Полуницю свіжу чи заморожену?") == ()


def test_nodes_without_a_slug_are_not_offerable() -> None:
    tree = Dictionary([Node("water", "Вода", None, ""), Node("s", "Солодка вода", None, "")])
    assert clarify.option_nodes(tree, "вода", WATER_ASK) == ()


async def test_options_carry_live_prices_of_this_slot() -> None:
    mcp = _MCP(
        {
            "voda-5087": [product(1, 27.9), product(2, 19.5)],
            "solodka-voda": [product(3, 45.0)],
            "negazovana-voda": [product(4, 22.0)],
            "mineralna-voda": [product(5, 31.0)],
        }
    )
    asked = await clarify.options_for(
        mcp,
        "вода",
        ask=WATER_ASK,
        tree=TREE,
        slot=SLOT,
        branch_id=BRANCH,  # type: ignore[arg-type]
    )

    assert [item.title for item in asked.options] == [
        "Солодка вода",
        "Негазована вода",
        "Мінеральна вода",
    ]
    assert asked.options[0].price_from == Decimal("45.0")
    assert asked.source == "дерево"
    assert asked.from_tree == 3
    assert asked.tautology == 1
    assert asked.spent_ms == 15


async def test_empty_nodes_do_not_become_chips() -> None:
    mcp = _MCP({"voda-5087": [], "solodka-voda": [product(3, 45.0)]})
    asked = await clarify.options_for(
        mcp,
        "вода",
        ask=WATER_ASK,
        tree=TREE,
        slot=SLOT,
        branch_id=BRANCH,  # type: ignore[arg-type]
    )
    assert [item.title for item in asked.options] == ["Солодка вода"]
    assert asked.empty == 2


async def test_probing_is_capped() -> None:
    nodes = [Node("root", "Вода", None, "voda")]
    nodes += [Node(f"k{i}", f"Вода джерельна №{i}", "root", f"voda-{i}") for i in range(10)]
    mcp = _MCP({})
    await clarify.options_for(
        mcp,
        "вода",
        ask=SPRING_ASK,
        tree=Dictionary(nodes),
        slot=SLOT,
        branch_id=BRANCH,  # type: ignore[arg-type]
    )
    assert len(mcp.calls) == clarify.MAX_PROBES


async def test_enough_options_stop_the_calls() -> None:
    nodes = [Node("root", "Вода", None, "voda")]
    nodes += [Node(f"k{i}", f"Вода джерельна №{i}", "root", f"voda-{i}") for i in range(5)]
    mcp = _MCP({f"voda-{i}": [product(i + 1, 10.0 + i)] for i in range(5)})
    asked = await clarify.options_for(
        mcp,
        "вода",
        ask=SPRING_ASK,
        tree=Dictionary(nodes),
        slot=SLOT,
        branch_id=BRANCH,  # type: ignore[arg-type]
    )
    assert len(asked.options) == 4
    assert len(mcp.calls) == 4


async def test_model_phrases_win_over_the_tree() -> None:
    mcp = _MCP({"syr-kyslomolochnyi": [product(1, 49.99)]})
    queries: list[list[str]] = []
    asked = await clarify.options_for(
        mcp,  # type: ignore[arg-type]
        "сир",
        ask=CHEESE_ASK,
        tree=CHEESE_TREE,
        slot=SLOT,
        branch_id=BRANCH,
        wanted=["сир кисломолочний", "сир для сирників"],
        search=_search({"сир для сирників": [product(7, 39.99)]}, calls=queries),
    )
    assert [item.title for item in asked.options] == ["Сир кисломолочний", "сир для сирників"]
    assert [item.key for item in asked.options] == ["syr-kyslomolochnyi", "сир для сирників"]
    assert asked.source == "модель"
    assert asked.from_model == 2
    assert asked.by_search == 1
    assert queries == [["сир для сирників"]]
    assert mcp.calls == ["syr-kyslomolochnyi"]


async def test_a_phrase_that_repeats_the_word_is_dropped() -> None:
    mcp = _MCP({})
    asked = await clarify.options_for(
        mcp,  # type: ignore[arg-type]
        "свинина",
        ask=PORK_ASK,
        tree=Dictionary([Node("pork", "Свинина", None, "svynyna")]),
        slot=SLOT,
        branch_id=BRANCH,
        wanted=["свинина", "свинина лопатка"],
        search=_search({"свинина лопатка": [product(1, 199.0)]}),
    )
    assert [item.title for item in asked.options] == ["свинина лопатка"]
    assert asked.tautology == 1


async def test_a_node_that_repeats_the_word_sends_the_phrase_to_search() -> None:
    mcp = _MCP({"svynyna": [product(1, 272.0)]})
    asked = await clarify.options_for(
        mcp,  # type: ignore[arg-type]
        "свинина",
        ask=PORK_ASK,
        tree=Dictionary([Node("pork", "Свинина", None, "svynyna")]),
        slot=SLOT,
        branch_id=BRANCH,
        wanted=["свинина сира"],
        search=_search({"свинина сира": [product(2, 249.0)]}),
    )
    assert [item.title for item in asked.options] == ["свинина сира"]
    assert asked.by_search == 1
    assert mcp.calls == []


async def test_a_phrase_with_an_empty_shelf_falls_out_with_a_reason() -> None:
    mcp = _MCP({})
    asked = await clarify.options_for(
        mcp,  # type: ignore[arg-type]
        "свинина",
        ask=PORK_ASK,
        tree=Dictionary([Node("pork", "Свинина", None, "svynyna")]),
        slot=SLOT,
        branch_id=BRANCH,
        wanted=["свинина ошийок", "свинина лопатка"],
        search=_search({"свинина лопатка": [product(1, 199.0)]}),
    )
    assert [item.title for item in asked.options] == ["свинина лопатка"]
    assert asked.empty == 1


async def test_the_tree_is_the_fallback_when_nothing_of_the_model_survived() -> None:
    mcp = _MCP({"syr-kyslomolochnyi": [product(1, 49.99)]})
    asked = await clarify.options_for(
        mcp,  # type: ignore[arg-type]
        "сир",
        ask=CHEESE_ASK,
        tree=CHEESE_TREE,
        slot=SLOT,
        branch_id=BRANCH,
        wanted=["сир для запікання"],
        search=_search({}),
    )
    assert [item.title for item in asked.options] == ["Сир кисломолочний"]
    assert asked.source == "дерево"
    assert asked.empty == 3
    assert asked.tautology == 1


async def test_the_step_names_the_source_even_when_nothing_was_dropped() -> None:
    mcp = _MCP({})
    asked = await clarify.options_for(
        mcp,  # type: ignore[arg-type]
        "сир",
        ask=CHEESE_ASK,
        tree=CHEESE_TREE,
        slot=SLOT,
        branch_id=BRANCH,
        wanted=["сир твердий"],
        search=_search({"сир твердий": [product(1, 99.0)]}),
    )
    assert asked.note == (
        "1 від моделі (0 з дерева, 1 з пошуку), знято 0 повторів слова, "
        "0 не на осі питання, порожніх 0"
    )
    assert clarify.Asked().note == (
        "жодного: відповідають самі кандидати, знято 0 повторів слова, "
        "0 не на осі питання, порожніх 0"
    )


async def test_without_a_search_the_phrase_without_a_node_just_falls_out() -> None:
    mcp = _MCP({"syr-kyslomolochnyi": [product(1, 49.99)]})
    asked = await clarify.options_for(
        mcp,  # type: ignore[arg-type]
        "сир",
        ask=CHEESE_ASK,
        tree=CHEESE_TREE,
        slot=SLOT,
        branch_id=BRANCH,
        wanted=["сир для сирників"],
    )
    assert asked.source == "дерево"
    assert asked.empty == 3


async def test_the_tree_may_not_answer_on_an_axis_it_does_not_share() -> None:
    mcp = _MCP(
        {
            "kava-v-zernah": [product(1, 199.0)],
            "kava-v-kapsulah": [product(2, 154.0)],
            "kava-cava": [product(3, 369.0)],
            "holodni-chai": [product(4, 33.49)],
        }
    )
    asked = await clarify.options_for(
        mcp,  # type: ignore[arg-type]
        "кава",
        ask=COFFEE_ASK,
        tree=COFFEE_TREE,
        slot=SLOT,
        branch_id=BRANCH,
    )
    assert [item.title for item in asked.options] == ["Кава в зернах"]
    assert asked.off_axis == 3
    assert asked.tautology == 1
    assert asked.empty == 0
    assert mcp.calls == ["kava-v-zernah"]


async def test_a_question_that_names_no_axis_leaves_the_tree_nothing_to_say() -> None:
    mcp = _MCP({"kava-v-zernah": [product(1, 199.0)]})
    asked = await clarify.options_for(
        mcp,  # type: ignore[arg-type]
        "кава",
        ask="Кава?",
        tree=COFFEE_TREE,
        slot=SLOT,
        branch_id=BRANCH,
    )
    assert asked.options == ()
    assert asked.source == "нічого"
    assert asked.off_axis == 4
    assert mcp.calls == []
    assert "4 не на осі питання" in asked.note


async def test_the_axis_does_not_judge_the_phrases_of_the_model() -> None:
    mcp = _MCP({})
    asked = await clarify.options_for(
        mcp,  # type: ignore[arg-type]
        "кава",
        ask=COFFEE_ASK,
        tree=COFFEE_TREE,
        slot=SLOT,
        branch_id=BRANCH,
        wanted=["кава арабіка"],
        search=_search({"кава арабіка": [product(1, 249.0)]}),
    )
    assert [item.title for item in asked.options] == ["кава арабіка"]
    assert asked.from_model == 1
    assert asked.off_axis == 0


async def test_off_axis_and_empty_shelf_are_counted_apart() -> None:
    mcp = _MCP({"kava-v-zernah": []})
    asked = await clarify.options_for(
        mcp,  # type: ignore[arg-type]
        "кава",
        ask=COFFEE_ASK,
        tree=COFFEE_TREE,
        slot=SLOT,
        branch_id=BRANCH,
    )
    assert asked.options == ()
    assert (asked.off_axis, asked.empty) == (3, 1)
