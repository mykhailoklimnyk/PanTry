from __future__ import annotations

import json

from komora.mcp import inventory


def _tool(name: str, description: str = "опис", schema: dict | None = None) -> dict:
    return {"name": name, "description": description, "input_schema": schema or {"type": "object"}}


def test_canonical_sorts_dedups_and_takes_camel_case_schema() -> None:
    tools = [
        {"name": "b", "description": "б", "inputSchema": {"type": "object", "required": ["x"]}},
        {"name": "", "description": "без імені не існує"},
        _tool("a"),
        {"name": "a", "description": "пізніший переписує"},
        {"name": "c"},
    ]
    got = inventory.canonical(tools)
    assert [t["name"] for t in got] == ["a", "b", "c"]
    assert got[0]["description"] == "пізніший переписує"
    assert got[0]["input_schema"] == {}
    assert got[1]["input_schema"] == {"type": "object", "required": ["x"]}
    assert got[2] == {"name": "c", "description": "", "input_schema": {}}, "без опису -- порожньо"


def test_dumps_is_deterministic_and_ends_with_newline() -> None:
    one = inventory.dumps([_tool("b"), _tool("a")])
    two = inventory.dumps([_tool("a"), _tool("b")])
    assert one == two
    assert [t["name"] for t in json.loads(one)] == ["a", "b"]
    head = (
        '[\n {\n  "description": "опис",\n  "input_schema": {\n   "type": "object"\n  },'
        '\n  "name": "a"\n }'
    )
    assert one.startswith(head)
    assert one.endswith("}\n]\n") and not one.endswith("\n\n")


def test_diff_is_empty_on_equal_snapshots() -> None:
    tools = [_tool("a"), _tool("b")]
    assert inventory.diff(tools, list(reversed(tools))) == []


def test_diff_names_removed_new_and_changed_fields() -> None:
    old = [_tool("gone"), _tool("same"), _tool("text"), _tool("schema"), _tool("both")]
    new = [
        _tool("same"),
        _tool("fresh"),
        _tool("text", description="інший опис"),
        _tool("schema", schema={"type": "object", "required": ["y"]}),
        _tool("both", description="інший", schema={"type": "array"}),
    ]
    assert inventory.diff(old, new) == [
        "- зник: gone",
        "+ новий: fresh",
        "~ змінено: both (description, input_schema)",
        "~ змінено: schema (input_schema)",
        "~ змінено: text (description)",
    ]


def test_diff_on_empty_snapshot_lists_everything_as_new() -> None:
    assert inventory.diff([], [_tool("a")]) == ["+ новий: a"]
