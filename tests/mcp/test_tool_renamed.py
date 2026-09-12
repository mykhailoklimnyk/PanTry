from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from mcp import types

from komora.mcp.client import MCPCallError, SilpoMCP


def _root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "docs" / "mcp-tools.json").is_file():
            return parent
    raise AssertionError("знімка описів не знайшлось: docs/mcp-tools.json")


SNAPSHOT = _root() / "docs" / "mcp-tools.json"


def real(name: str) -> str:
    tools = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    return next(tool["description"] for tool in tools if tool["name"] == name)


class Session:

    def __init__(self, live: dict[str, str]) -> None:
        self.live = live
        self.dialled: list[str] = []
        self.listed = 0

    async def call_tool(self, name: str, args: dict[str, Any]) -> types.CallToolResult:
        self.dialled.append(name)
        if name not in self.live:
            raise RuntimeError(f"Unknown tool: {name}")
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=json.dumps({"queries": []}))],
            isError=False,
        )

    async def list_tools(self) -> SimpleNamespace:
        self.listed += 1
        return SimpleNamespace(
            tools=[
                SimpleNamespace(name=name, description=body, inputSchema={})
                for name, body in self.live.items()
            ]
        )


def client(session: Session, *, writes: bool = False) -> SilpoMCP:
    mcp = SilpoMCP(token="t", writes=writes, max_attempts=1)
    mcp._session = session  # type: ignore[assignment]
    return mcp


@pytest.mark.anyio
async def test_a_renamed_read_tool_is_dialled_under_its_new_name():
    session = Session({"silpo_search_v2": real("silpo_find_products_batch")})
    mcp = client(session)
    got = await mcp.call("silpo_find_products_batch", {})
    assert session.dialled == ["silpo_find_products_batch", "silpo_search_v2"]
    assert got.tool == "silpo_find_products_batch"


@pytest.mark.anyio
async def test_the_rename_is_learnt_once_and_then_dialled_straight():
    session = Session({"silpo_search_v2": real("silpo_find_products_batch")})
    mcp = client(session)
    await mcp.call("silpo_find_products_batch", {})
    await mcp.call("silpo_find_products_batch", {})
    assert session.dialled == [
        "silpo_find_products_batch",
        "silpo_search_v2",
        "silpo_search_v2",
    ]
    assert session.listed == 1


@pytest.mark.anyio
async def test_a_write_tool_is_never_rebound():
    session = Session({"silpo_add_v2": real("silpo_add_or_update_cart_products")})
    mcp = client(session, writes=True)
    with pytest.raises(MCPCallError):
        await mcp.call("silpo_add_or_update_cart_products", {})
    assert session.dialled == ["silpo_add_or_update_cart_products"]
    assert session.listed == 0


@pytest.mark.anyio
async def test_a_plain_failure_does_not_become_a_rename():
    session = Session({"silpo_find_products_batch": real("silpo_find_products_batch")})
    mcp = client(session)
    with pytest.raises(MCPCallError):
        await mcp.call("silpo_get_time_slots", {})
    assert session.dialled == ["silpo_get_time_slots"]
    assert session.listed == 1
