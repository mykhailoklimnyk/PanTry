from __future__ import annotations

import pytest

from komora.config import Settings
from komora.mcp.client import READ_TOOLS, WRITE_TOOLS, MCPCallError, SilpoMCP, WriteBlocked


def plain() -> Settings:
    return Settings(_env_file=None)


def test_writes_are_off_unless_asked():
    assert SilpoMCP(token="x", settings=plain())._writes is False


async def test_write_is_blocked_before_any_network_call():
    client = SilpoMCP(token="not-used", settings=plain())

    with pytest.raises(WriteBlocked, match="змінює стан"):
        await client.call("silpo_add_or_update_cart_products", {"products": []})


async def test_unknown_tool_counts_as_a_write():
    client = SilpoMCP(token="not-used", settings=plain())

    with pytest.raises(WriteBlocked, match="змінює стан"):
        await client.call("silpo_brand_new_mutation", {})


async def test_writes_true_lets_the_write_through_to_the_transport():
    client = SilpoMCP(token="not-used", writes=True, settings=plain())

    with pytest.raises(RuntimeError, match="сесія не відкрита"):
        await client.call("silpo_add_or_update_cart_products", {"products": []})


def test_permission_belongs_to_the_client_not_the_process():
    reader = SilpoMCP(token="x", settings=plain())
    writer = SilpoMCP(token="x", writes=True, settings=plain())
    assert (reader._writes, writer._writes) == (False, True)


async def test_no_token_no_session_and_no_silent_fallback():
    cfg = plain().model_copy(update={"mcp_token": "токен-власника"})
    assert cfg.operator_token() == "токен-власника"

    with pytest.raises(RuntimeError, match="без токена"):
        async with SilpoMCP(settings=cfg):
            pass


def test_every_cart_mutating_tool_is_listed():
    for tool in WRITE_TOOLS:
        assert any(word in tool for word in ("add", "update", "remove", "clear", "create"))
    assert "silpo_get_my_shopping_cart" not in WRITE_TOOLS
    assert "silpo_get_time_slots" not in WRITE_TOOLS


def test_read_and_write_lists_do_not_overlap():
    assert READ_TOOLS.isdisjoint(WRITE_TOOLS)


async def test_fixture_stand_never_reaches_the_network(tmp_path):
    async with SilpoMCP(fixtures_dir=tmp_path, settings=plain()) as client:
        with pytest.raises(MCPCallError, match="стенд на фікстурах"):
            await client.call("silpo_get_time_slots", {})


async def test_fixture_stand_still_refuses_writes(tmp_path):
    client = SilpoMCP(fixtures_dir=tmp_path, settings=plain())

    with pytest.raises(WriteBlocked):
        await client.call("silpo_clear_shopping_cart", {})


def test_run_log_is_off_by_default():
    assert plain().run_log is False
    assert plain().model_copy(update={"run_log": True}).run_log is True
