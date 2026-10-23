from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from komora import notify, runtime
from komora.config import settings
from komora.mcp import inventory
from komora.mcp.client import SilpoMCP

SNAPSHOT = Path(__file__).resolve().parents[1] / "docs" / "mcp-tools.json"


async def fetch() -> list[dict[str, Any]]:
    token, _ = settings.require_operator()
    if not token:
        raise SystemExit("немає токена оператора: див. docs/setup.md")
    async with SilpoMCP(token=token) as mcp:
        session = mcp._session
        assert session is not None
        listed = await session.list_tools()
    return [
        {
            "name": tool.name,
            "description": tool.description or "",
            "input_schema": getattr(tool, "input_schema", None) or getattr(tool, "inputSchema", {}),
        }
        for tool in listed.tools
    ]


def load_snapshot() -> list[dict[str, Any]]:
    if not SNAPSHOT.exists():
        return []
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


async def main(argv: list[str]) -> int:
    check = "--check" in argv or "--notify" in argv
    live = await fetch()
    known = load_snapshot()
    lines = inventory.diff(known, live)
    if not check:
        SNAPSHOT.write_text(inventory.dumps(live), encoding="utf-8")
        print(f"знімок: {len(live)} інструментів -> {SNAPSHOT.name}; змін: {len(lines)}")
        for line in lines:
            print(line)
        return 0
    if not lines:
        print(f"описи не змінились: {len(live)} інструментів")
        return 0
    print(f"описи змінились ({len(lines)}):")
    for line in lines:
        print(line)
    if "--notify" in argv:
        text = "Описи інструментів MCP «Сільпо» змінились:\n" + "\n".join(lines)
        sent = await notify.send(text)
        print("повідомлення: " + ("надіслано" if sent.ok else f"не надіслано ({sent.why})"))
        return 0 if sent.ok else 1
    return 1


if __name__ == "__main__":
    sys.exit(runtime.run(main(sys.argv[1:])))
