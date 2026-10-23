from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from komora import runtime
from komora.core import instructions

runtime.console()

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "docs" / "mcp-tools.json"
REGISTER = ROOT / "src" / "komora" / "mcp" / "verdicts.json"

QUOTE_CHARS = 110


def load(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def verdicts(rows: list[dict[str, Any]]) -> list[instructions.Verdict]:
    return [
        instructions.Verdict(
            tool=str(row.get("tool") or ""),
            sha=str(row.get("sha") or ""),
            kind=str(row.get("kind") or ""),
            verdict=str(row.get("verdict") or ""),
            where=str(row.get("where") or ""),
        )
        for row in rows
    ]


def sync(tools: list[dict[str, Any]], rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    known = {(str(row.get("tool")), str(row.get("sha"))): row for row in rows}
    out: list[dict[str, Any]] = []
    for tool in tools:
        name = str(tool.get("name") or "")
        for block in instructions.blocks(str(tool.get("description") or "")):
            sha = instructions.fingerprint(block)
            row = known.get((name, sha), {})
            out.append(
                {
                    "tool": name,
                    "sha": sha,
                    "kind": str(row.get("kind") or ""),
                    "verdict": str(row.get("verdict") or ""),
                    "where": str(row.get("where") or ""),
                    "quote": block[:QUOTE_CHARS],
                }
            )
    out.sort(key=lambda row: (row["tool"], row["sha"]))
    return out


def main(argv: list[str]) -> int:
    tools = load(SNAPSHOT)
    if not tools:
        print(f"немає знімка описів: {SNAPSHOT.name} (див. scripts/mcp_tools_snapshot.py)")
        return 1
    rows = load(REGISTER)
    if "--sync" in argv:
        fresh = sync(tools, rows)
        gone = len(rows) - sum(1 for row in fresh if row["kind"] or row["verdict"])
        REGISTER.write_text(
            json.dumps(fresh, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
        )
        empty = [row for row in fresh if not row["kind"]]
        print(f"реєстр: {len(fresh)} інструкцій -> {REGISTER.name}; знято вироків: {max(0, gone)}")
        for row in empty:
            print(f"+ чекає на вирок: {row['tool']} [{row['sha']}] {row['quote']}")
        return 1 if empty else 0
    report = instructions.audit(tools, verdicts(rows))
    if report.ok():
        counts = {kind: 0 for kind in instructions.KINDS}
        for row in rows:
            counts[str(row.get("kind"))] = counts.get(str(row.get("kind")), 0) + 1
        said = ", ".join(f"{kind} {counts.get(kind, 0)}" for kind in instructions.KINDS)
        print(f"вироки на місці: {report.judged} інструкцій ({said})")
        return 0
    print(f"реєстр вироків розійшовся з описами ({len(report.lines())}):")
    for line in report.lines():
        print(line)
    print("що робити: --sync звести реєстр, потім написати вирок кожній новій інструкції")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
