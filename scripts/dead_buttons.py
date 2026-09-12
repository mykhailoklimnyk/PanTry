from __future__ import annotations

import re
from pathlib import Path

from komora import runtime

runtime.console()

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web" / "src"

_HANDLER = re.compile(r"(?:^|[\s{])on[a-z]+\s*=|(?:^|[\s{])on:[a-z]+|\{on[a-z]+\}")
_SUBMIT = re.compile(r"""\btype\s*=\s*["']submit["']""")
_SKIP = re.compile(r"<style[\s>].*?</style>|<script[\s>].*?</script>|<!--.*?-->", re.DOTALL)


def _blank(text: str) -> str:
    return _SKIP.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


def _attrs(text: str, start: int) -> str:
    depth = 0
    quote = ""
    i = start
    while i < len(text):
        ch = text[i]
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        elif ch == ">" and depth == 0:
            break
        i += 1
    return text[start:i]


def _forms(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for open_tag in re.finditer(r"<form[\s>]", text):
        close = text.find("</form>", open_tag.end())
        spans.append((open_tag.start(), len(text) if close < 0 else close))
    return spans


def dead(path: Path) -> list[tuple[int, str]]:
    text = _blank(path.read_text(encoding="utf-8"))
    forms = _forms(text)
    found: list[tuple[int, str]] = []
    for tag in re.finditer(r"<button(?![\w-])", text):
        attrs = _attrs(text, tag.end())
        if _HANDLER.search(attrs) or "{..." in attrs:
            continue
        if _SUBMIT.search(attrs) and any(lo < tag.start() < hi for lo, hi in forms):
            continue
        line = text.count("\n", 0, tag.start()) + 1
        found.append((line, " ".join(f"<button{attrs}>".split())))
    return found


def main() -> int:
    bad = {p: rows for p in sorted(WEB.rglob("*.svelte")) if (rows := dead(p))}
    if not bad:
        return 0
    print("кнопки без обробника (клік проходить і не робить нічого):")
    for path, rows in bad.items():
        for line, tag in rows:
            print(f"  {path.relative_to(ROOT).as_posix()}:{line} — {tag}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
