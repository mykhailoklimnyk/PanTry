from __future__ import annotations

import re
from pathlib import Path

from komora import runtime

runtime.console()

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web" / "src"

_USED = re.compile(r"var\(\s*(--[a-z0-9-]+)\s*\)")
_DEFINED = re.compile(r"(--[a-z0-9-]+)\s*:")


def sources() -> list[Path]:
    return sorted(p for p in WEB.rglob("*") if p.suffix in {".css", ".svelte"})


def dead_tokens() -> dict[str, list[str]]:
    defined: set[str] = set()
    used: dict[str, list[str]] = {}
    for path in sources():
        text = path.read_text(encoding="utf-8")
        defined.update(_DEFINED.findall(text))
        for name in _USED.findall(text):
            used.setdefault(name, []).append(path.relative_to(ROOT).as_posix())
    return {name: places for name, places in used.items() if name not in defined}


def main() -> int:
    dead = dead_tokens()
    if not dead:
        return 0
    print("токени теми, яких немає (var() мовчки зніме властивість):")
    for name, places in sorted(dead.items()):
        for place in sorted(set(places)):
            print(f"  {name} — {place}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
