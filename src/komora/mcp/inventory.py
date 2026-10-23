from __future__ import annotations

import json
from typing import Any

FIELDS = ("name", "description", "input_schema")


def canonical(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for tool in tools:
        name = str(tool.get("name") or "")
        if not name:
            continue
        seen[name] = {
            "name": name,
            "description": str(tool.get("description") or ""),
            "input_schema": tool.get("input_schema") or tool.get("inputSchema") or {},
        }
    return [seen[name] for name in sorted(seen)]


def dumps(tools: list[dict[str, Any]]) -> str:
    return json.dumps(canonical(tools), ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def diff(old: list[dict[str, Any]], new: list[dict[str, Any]]) -> list[str]:
    before = {t["name"]: t for t in canonical(old)}
    after = {t["name"]: t for t in canonical(new)}
    lines: list[str] = []
    for name in sorted(before.keys() - after.keys()):
        lines.append(f"- зник: {name}")
    for name in sorted(after.keys() - before.keys()):
        lines.append(f"+ новий: {name}")
    for name in sorted(before.keys() & after.keys()):
        changed = [f for f in ("description", "input_schema") if before[name][f] != after[name][f]]
        if changed:
            lines.append(f"~ змінено: {name} ({', '.join(changed)})")
    return lines


__all__ = ["FIELDS", "canonical", "diff", "dumps"]
