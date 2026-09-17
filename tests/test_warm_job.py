from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any

import pytest

from komora.agent.basket import forget_intents, forget_keeps
from komora.agent.llm import Meter
from komora.agent.sanity import forget_sense
from komora.core.dictionary import Node
from komora.core.facts_audit import audit
from komora.core.quota import counts_as_run
from komora.jobs import warm as job

BRANCH = "test-branch"
SLOT = {
    "deliveryType": "DeliveryHome",
    "start": "2026-08-29T08:00:00+00:00",
    "end": "2026-08-29T10:00:00+00:00",
    "available": True,
}


class _Outcome:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload_raw = payload


class _MCP:

    def __init__(self, shelf: dict[str, tuple[int, list[str]]]) -> None:
        self.shelf = shelf
        self.asked: list[str] = []

    async def call(self, tool: str, args: dict[str, Any]) -> _Outcome:
        if tool == "silpo_get_time_slots":
            return _Outcome({"slots": [SLOT]})
        self.asked.append(args["category"])
        total, names = self.shelf[args["category"]]
        return _Outcome(
            {
                "products": [{"name": name} for name in names],
                "meta": {"total": total},
            }
        )


class _Conn:
    def __init__(
        self,
        store: dict[str, dict[str, Any]],
        facts: dict[str, dict[str, Any]],
        spent: list[dict[str, Any]],
    ) -> None:
        self.store = store
        self.facts = facts
        self.spent = spent
        self.rows: list[dict[str, Any]] = []

    async def execute(self, sql: str, args: Any = None) -> Any:
        flat = " ".join(sql.split())
        if flat.startswith("insert into agent_runs"):
            self.spent.append(dict(args or {}))
            return self
        rows = self.facts if "intent_facts" in flat else self.store
        self.rows = [rows[sha] for sha in args["shas"] if sha in rows]
        return self

    async def fetchall(self) -> list[dict[str, Any]]:
        return self.rows

    @asynccontextmanager
    async def cursor(self):
        yield self

    async def executemany(self, sql: str, rows: Any) -> None:
        into_facts = "intent_facts" in " ".join(sql.split())
        for row in rows:
            if not into_facts:
                self.store[row["name_sha"]] = row
                continue
            kept = self.facts.setdefault(
                row["label_sha"],
                {
                    "label_sha": row["label_sha"],
                    "keeps": None,
                    "sanity": None,
                    "rhythm_lies": None,
                    "per_day": None,
                    "per_day_unit": None,
                    "aisle": None,
                },
            )
            kept.update({key: value for key, value in row.items() if value is not None})


class _Pool:

    def __init__(
        self,
        store: dict[str, dict[str, Any]] | None = None,
        facts: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self.store = store if store is not None else {}
        self.facts = facts if facts is not None else {}
        self.spent: list[dict[str, Any]] = []

    @asynccontextmanager
    async def connection(self, **_: Any):
        yield _Conn(self.store, self.facts, self.spent)


class _LLM:

    model = "mistral.mistral-large-3-675b-instruct"

    def __init__(self) -> None:
        self.batches: list[list[str]] = []
        self.facts: list[list[str]] = []
        self.meter = Meter()

    async def decide(self, *, user: str, schema_name: str = "naming", **_: Any) -> Any:
        import json

        from komora.agent.llm import Decision, Usage

        payload = json.loads(user)
        if schema_name in ("keeps", "sanity"):
            labels = payload["види"]
            self.facts.append(labels)
            answer = await self._facts(schema_name, labels)
            self.meter.add(answer)
            return answer

        asked = payload["назви"]
        self.batches.append(asked)
        decision = Decision(
            data={
                "kinds": [
                    {
                        "name": name,
                        "intent": name.split()[0].casefold(),
                        "subtype": None,
                        "drink": None,
                    }
                    for name in asked
                ]
            },
            text="",
            model=self.model,
            usage=Usage(10, 20),
            duration_ms=1,
        )
        self.meter.add(decision)
        return decision

    async def _facts(self, schema_name: str, labels: list[str]) -> Any:
        from komora.agent.llm import Decision, Usage

        kinds = [
            {"label": label, "keeps": "дні"}
            if schema_name == "keeps"
            else {
                "label": label,
                "sanity": "зникає за раз",
                "rhythm_lies": True,
                "per_day": 100,
                "per_day_unit": "г",
                "aisle": None,
            }
            for label in labels
        ]
        return Decision(
            data={"kinds": kinds},
            text="",
            model=self.model,
            usage=Usage(10, 20),
            duration_ms=1,
        )


@pytest.fixture(autouse=True)
def _clean_cache():
    def _forget() -> None:
        forget_intents()
        forget_keeps()
        forget_sense()

    _forget()
    yield
    _forget()


@pytest.fixture
def tree(monkeypatch: pytest.MonkeyPatch):
    def _nodes(slugs: list[str]):
        async def fetch(mcp: Any, *, branch_id: str) -> tuple[Node, ...]:
            return tuple(Node(id=slug, title=slug, parent_id=None, slug=slug) for slug in slugs)

        monkeypatch.setattr(job, "fetch_all", fetch)

    return _nodes


@pytest.mark.asyncio
async def test_the_whole_shelf_gets_named_once(tree) -> None:
    tree(["a", "b"])
    mcp = _MCP({"a": (5, ["Молоко Яготинське 2.5%"]), "b": (3, ["Хліб Київхліб"])})
    llm = _LLM()
    pool = _Pool()

    done = await job.warm(mcp, llm, pool, branch_id=BRANCH)  # type: ignore[arg-type]

    assert done.names == 2
    assert done.known == 0
    assert done.named == 2
    assert sorted(name for batch in llm.batches for name in batch) == [
        "Молоко Яготинське 2.5%",
        "Хліб Київхліб",
    ]


@pytest.mark.asyncio
async def test_a_second_run_asks_the_model_about_nothing(tree) -> None:
    tree(["a"])
    mcp = _MCP({"a": (5, ["Молоко Яготинське 2.5%"])})
    pool = _Pool()
    await job.warm(mcp, _LLM(), pool, branch_id=BRANCH)  # type: ignore[arg-type]

    forget_intents()
    second = _LLM()
    done = await job.warm(mcp, second, pool, branch_id=BRANCH)  # type: ignore[arg-type]

    assert second.batches == []
    assert done.known == 1
    assert done.named == 0


@pytest.mark.asyncio
async def test_a_warm_name_cache_still_gets_its_facts(tree) -> None:
    tree(["a"])
    mcp = _MCP({"a": (5, ["Молоко Яготинське 2.5%"])})
    pool = _Pool()
    await job.warm(mcp, _LLM(), pool, branch_id=BRANCH)  # type: ignore[arg-type]

    cold = _Pool(store=pool.store)
    forget_intents()
    forget_keeps()
    forget_sense()
    llm = _LLM()

    done = await job.warm(mcp, llm, cold, branch_id=BRANCH)  # type: ignore[arg-type]

    assert llm.batches == [], "назви вже названі -- питати про них нема чого"
    assert llm.facts, "а от факти на цій машині ще ніхто не питав"
    assert done.labels == 1
    assert done.facts == 1
    assert cold.facts, "нагріте мусить лежати в базі, а не лише в пам'яті процесу"


@pytest.mark.asyncio
async def test_a_label_with_only_a_shelf_life_does_not_count_as_warmed(tree) -> None:
    tree(["a"])
    mcp = _MCP({"a": (5, ["Молоко Яготинське 2.5%"])})

    class _OnlyKeeps(_LLM):
        async def _facts(self, schema_name: str, labels: list[str]) -> Any:
            from komora.agent.llm import Decision, Usage

            kinds = (
                [{"label": label, "keeps": "дні"} for label in labels]
                if schema_name == "keeps"
                else []
            )
            return Decision(
                data={"kinds": kinds},
                text="",
                model=self.model,
                usage=Usage(10, 20),
                duration_ms=1,
            )

    pool = _Pool()
    done = await job.warm(mcp, _OnlyKeeps(), pool, branch_id=BRANCH)  # type: ignore[arg-type]

    assert done.labels == 1
    assert done.facts == 0, "стеля без глузду -- це половина відповіді, а не мітка"
    assert "половина відповіді" in done.summary()


@pytest.mark.asyncio
async def test_the_busiest_nodes_are_named_first(tree) -> None:
    tree(["рідкісний", "ходовий"])
    mcp = _MCP({"рідкісний": (2, ["Каперси"]), "ходовий": (900, ["Молоко"])})
    llm = _LLM()

    await job.warm(mcp, llm, _Pool(), branch_id=BRANCH, limit=1)  # type: ignore[arg-type]

    assert llm.batches == [["Молоко"]]


@pytest.mark.asyncio
async def test_a_node_that_refuses_does_not_stop_the_walk(tree) -> None:
    from komora.mcp.client import MCPCallError

    tree(["зламаний", "цілий"])

    class _Broken(_MCP):
        async def call(self, tool: str, args: dict[str, Any]) -> _Outcome:
            if tool != "silpo_get_time_slots" and args["category"] == "зламаний":
                raise MCPCallError("silpo_get_products", "вузол не читається", attempts=1)
            return await super().call(tool, args)

    mcp = _Broken({"цілий": (5, ["Молоко"])})
    done = await job.warm(mcp, _LLM(), _Pool(), branch_id=BRANCH)  # type: ignore[arg-type]

    assert done.nodes == 1
    assert done.names == 1


@pytest.mark.asyncio
async def test_the_number_named_comes_from_the_database_not_from_our_intentions(
    tree,
) -> None:
    tree(["a"])
    mcp = _MCP({"a": (5, ["Молоко Яготинське 2.5%"])})

    class _Deaf(_Pool):
        @asynccontextmanager
        async def connection(self, **_: Any):
            yield _Conn({}, {}, self.spent)

    done = await job.warm(mcp, _LLM(), _Deaf(), branch_id=BRANCH)  # type: ignore[arg-type]

    assert done.names == 1
    assert done.named == 0


@pytest.mark.asyncio
async def test_without_a_slot_the_catalog_is_not_readable(tree) -> None:
    tree([])

    class _NoSlots(_MCP):
        async def call(self, tool: str, args: dict[str, Any]) -> _Outcome:
            return _Outcome({"slots": []})

    with pytest.raises(RuntimeError, match="слота"):
        await job.warm(_NoSlots({}), _LLM(), _Pool(), branch_id=BRANCH)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_the_warming_pays_into_the_same_counter_as_a_guest_run(tree) -> None:
    tree(["a"])
    mcp = _MCP({"a": (5, ["Молоко Яготинське 2.5%"])})
    pool = _Pool()

    done = await job.warm(mcp, _LLM(), pool, branch_id=BRANCH)  # type: ignore[arg-type]

    assert done.counted
    assert len(pool.spent) == 1
    row = pool.spent[0]
    assert row["kind"] == "warm"
    assert row["owner"] == job.OWNER, "питання «чиї це гроші» мусить мати відповідь у даних"
    assert row["tokens_in"] and row["tokens_out"], "нуль токенів -- це нуль грошей назавжди"
    assert row["cost_usd"] and row["cost_usd"] > 0
    assert row["cost_usd"] == done.cost_usd, "друковане і записане -- одне число"


@pytest.mark.asyncio
async def test_the_warming_does_not_eat_the_run_ceiling_of_guests(tree) -> None:
    tree(["a"])
    mcp = _MCP({"a": (5, ["Молоко Яготинське 2.5%"])})
    pool = _Pool()

    await job.warm(mcp, _LLM(), pool, branch_id=BRANCH)  # type: ignore[arg-type]

    assert not counts_as_run(pool.spent[0]["kind"])


@pytest.mark.asyncio
async def test_a_counter_that_did_not_take_the_money_says_so_in_the_summary(tree) -> None:
    tree(["a"])
    mcp = _MCP({"a": (5, ["Молоко Яготинське 2.5%"])})

    class _NoSpend(_Pool):
        @asynccontextmanager
        async def connection(self, **_: Any):
            conn = _Conn(self.store, self.facts, self.spent)
            original = conn.execute

            async def execute(sql: str, args: Any = None) -> Any:
                if " ".join(sql.split()).startswith("insert into agent_runs"):
                    raise ConnectionError("лічильник не відповідає")
                return await original(sql, args)

            conn.execute = execute  # type: ignore[method-assign]
            yield conn

    done = await job.warm(mcp, _LLM(), _NoSpend(), branch_id=BRANCH)  # type: ignore[arg-type]

    assert done.named == 1, "робота зроблена і мусить лишитись зробленою"
    assert not done.counted
    assert "НЕ ЛЯГЛО" in done.summary()


def test_the_summary_says_the_price_even_when_it_is_unknown() -> None:
    assert "невідомо" in job.Warmed(1, 2, 0, 2, 0, 0, 1, None, audit({})).summary()
