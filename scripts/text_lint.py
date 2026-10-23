from __future__ import annotations

import argparse
import ast
import io
import re
import tokenize
import unicodedata
from pathlib import Path

from komora import runtime
from komora.core.homoglyphs import (
    APOSTROPHES,
    DIRECT,
    ESCAPE,
    WORD,
    fix_word,
    is_mixed,
    mixed_words,
    script_of,
    stray_chars,
)

runtime.console()

ROOT = Path(__file__).resolve().parents[1]

SCAN_DIRS = ("src", "tests", "scripts", "web/src", "web/e2e", "docs", "db")
SCAN_FILES = ("CLAUDE.md", "README.md")
SCAN_SUFFIXES = {".py", ".ts", ".svelte", ".md", ".css", ".sql"}

SKIP = {
    Path("docs/repo-map.md"),
    Path("docs/licenses.md"),
    Path("docs/graph-report.md"),
    Path("web/src/lib/types.ts"),
    Path("web/src/lib/facts.ts"),
    Path("scripts/text_lint.py"),
    Path("tests/test_text_hygiene.py"),
    Path("scripts/compare_models.py"),
    Path("src/komora/core/homoglyphs.py"),
    Path("tests/core/test_homoglyphs.py"),
    Path("tests/mcp/test_query_apostrophes.py"),
    Path("tests/test_llm_validation.py"),
}

BRAND = frozenset({"ПанTry"})

MIXED_SCRIPT_OK = {
    Path("src/komora/core/packaging.py"),
    Path("src/komora/core/allergens.py"),
}

LONELY_HYPHEN = re.compile(r"(?<=\S) - (?=\S)")

SVELTE_BLOCK = re.compile(r"<(script|style)\b[^>]*>(.*?)</\1\s*>", re.DOTALL | re.IGNORECASE)

LINE_COMMENTS = {".ts": ("//",), ".sql": ("--",), ".css": (), ".svelte": ("//",)}


def _skip_braces(text: str, start: int) -> int:
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return len(text)


def _string_span(text: str, start: int, spans: list[tuple[int, int]]) -> int:
    quote = text[start]
    i = at = start + 1
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            i += 2
        elif ch == quote:
            spans.append((at, i))
            return i + 1
        elif ch == "\n" and quote != "`":
            spans.append((at, i))
            return i
        elif quote == "`" and text.startswith("${", i):
            spans.append((at, i))
            i = at = _skip_braces(text, i + 1)
        else:
            i += 1
    spans.append((at, len(text)))
    return len(text)


def _code_spans(text: str, *, line_comments: tuple[str, ...]) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    i = 0
    while i < len(text):
        marker = next((m for m in line_comments if text.startswith(m, i)), None)
        if text.startswith("/*", i):
            close = text.find("*/", i + 2)
            spans.append((i + 2, len(text) if close < 0 else close))
            i = len(text) if close < 0 else close + 2
        elif marker:
            close = text.find("\n", i)
            end = len(text) if close < 0 else close
            spans.append((i + len(marker), end))
            i = end
        elif text[i] in "'\"`":
            i = _string_span(text, i, spans)
        else:
            i += 1
    return spans


def _python_spans(text: str) -> list[tuple[int, int]]:
    starts = [0]
    for line in text.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    kinds = {tokenize.STRING, tokenize.COMMENT, getattr(tokenize, "FSTRING_MIDDLE", -1)}
    spans = []
    try:
        for token in tokenize.generate_tokens(io.StringIO(text).readline):
            if token.type in kinds:
                spans.append(
                    (
                        starts[token.start[0] - 1] + token.start[1],
                        starts[token.end[0] - 1] + token.end[1],
                    )
                )
    except tokenize.TokenError, IndentationError, SyntaxError:
        return []
    return spans


def _tag_end(text: str, start: int) -> int:
    i = start + 1
    while i < len(text):
        if text[i] == "{":
            i = _skip_braces(text, i)
        elif text[i] in "\"'":
            close = text.find(text[i], i + 1)
            i = len(text) if close < 0 else close + 1
        elif text[i] == ">":
            return i + 1
        else:
            i += 1
    return len(text)


def _markup_spans(text: str, offset: int = 0) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    i = at = 0
    while i < len(text):
        if text.startswith("<!--", i):
            close = text.find("-->", i + 4)
            spans.append((at, i))
            spans.append((i + 4, len(text) if close < 0 else close))
            i = at = len(text) if close < 0 else close + 3
        elif text[i] == "<":
            spans.append((at, i))
            i = at = _tag_end(text, i)
        elif text[i] == "{":
            spans.append((at, i))
            i = at = _skip_braces(text, i)
        else:
            i += 1
    spans.append((at, len(text)))
    return [(start + offset, end + offset) for start, end in spans]


def _svelte_spans(text: str) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    at = 0
    for block in SVELTE_BLOCK.finditer(text):
        spans += _markup_spans(text[at : block.start()], at)
        comments = ("//",) if block.group(1).lower() == "script" else ()
        body = block.start(2)
        spans += [
            (start + body, end + body)
            for start, end in _code_spans(block.group(2), line_comments=comments)
        ]
        at = block.end()
    return spans + _markup_spans(text[at:], at)


def _text_spans(path: Path, text: str) -> list[tuple[int, int]]:
    if path.suffix == ".py":
        return _python_spans(text)
    if path.suffix == ".svelte":
        return _svelte_spans(text)
    return _code_spans(text, line_comments=LINE_COMMENTS.get(path.suffix, ("//",)))


def _dash_targets(path: Path, text: str) -> str:
    if path.suffix == ".md":
        return LONELY_HYPHEN.sub(" — ", text)

    out = []
    at = 0
    for start, end in _text_spans(path, text):
        if start < at or end <= start:
            continue
        out.append(text[at:start])
        out.append(LONELY_HYPHEN.sub(" — ", text[start:end]))
        at = end
    out.append(text[at:])
    return "".join(out)


SINGLE_QUOTED = re.compile(r"'([^'\"\n]*[’ʼ‘´][^'\"\n]*)'")


def replace_apostrophes(path: Path, line: str) -> str:
    if not any(ch in line for ch in APOSTROPHES):
        return line

    if path.suffix == ".md" or "'" not in line:
        for bad, good in APOSTROPHES.items():
            line = line.replace(bad, good)
        return line

    def requote(match: re.Match[str]) -> str:
        inner = match.group(1)
        for bad, good in APOSTROPHES.items():
            inner = inner.replace(bad, good)
        return f'"{inner}"'

    return SINGLE_QUOTED.sub(requote, line)


def clean(path: Path, text: str) -> str:
    for bad, good in DIRECT.items():
        text = text.replace(bad, good)
    text = "".join(replace_apostrophes(path, line) for line in text.splitlines(keepends=True))

    if path not in MIXED_SCRIPT_OK:
        out = []
        for line in text.splitlines(keepends=True):
            script = script_of(ESCAPE.sub(" ", line))

            def repair(match: re.Match[str], script: str = script) -> str:
                word = match.group(0)
                if word in BRAND or not is_mixed(word):
                    return word
                fixed = fix_word(word, script)
                return fixed if not is_mixed(fixed) else word

            out.append(WORD.sub(repair, line))
        text = "".join(out)

    return _dash_targets(path, text)


def targets() -> list[Path]:
    seen: list[Path] = []
    for name in SCAN_FILES:
        if (ROOT / name).exists():
            seen.append(ROOT / name)
    for folder in SCAN_DIRS:
        for path in sorted((ROOT / folder).rglob("*")):
            if not path.is_file() or path.suffix not in SCAN_SUFFIXES:
                continue
            if "node_modules" in path.parts or "__pycache__" in path.parts:
                continue
            if path.relative_to(ROOT) in SKIP:
                continue
            seen.append(path)
    return seen


def report(rel: Path, text: str) -> list[str]:
    problems = []
    for ch in stray_chars(text):
        try:
            name = unicodedata.name(ch)
        except ValueError:
            name = "невідомий"
        problems.append(f"{rel}: символ {ch!r} (U+{ord(ch):04X}, {name})")
    if rel not in MIXED_SCRIPT_OK:
        for word, fixed, healed in mixed_words(text):
            if word in BRAND:
                continue
            problems.append(
                f"{rel}: дві абетки в слові {word!r} -> {fixed!r}"
                if healed
                else f"{rel}: дві абетки в слові {word!r} — двійника немає, полагодь руками"
            )
    hyphens = len(LONELY_HYPHEN.findall(text)) - len(
        LONELY_HYPHEN.findall(_dash_targets(rel, text))
    )
    if hyphens > 0:
        problems.append(f"{rel}: дефіс замість тире, разів: {hyphens}")
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description="Гігієна тексту: гомогліфи й чужі символи")
    parser.add_argument("--fix", action="store_true", help="виправити на місці")
    args = parser.parse_args()

    problems: list[str] = []
    fixed = 0
    for path in targets():
        try:
            text = path.read_text(encoding="utf-8")
        except OSError, UnicodeDecodeError:
            continue
        rel = path.relative_to(ROOT)
        if args.fix:
            cleaned = clean(rel, text)
            if cleaned == text:
                continue
            if rel.suffix == ".py":
                try:
                    ast.parse(cleaned)
                except SyntaxError as exc:
                    print(f"ПРОПУЩЕНО {rel}: правка зламала б синтаксис ({exc.msg})")
                    continue
            path.write_text(cleaned, encoding="utf-8", newline="")
            fixed += 1
            print(f"виправлено: {rel}")
            continue
        problems.extend(report(rel, text))

    if args.fix:
        print(f"\nфайлів виправлено: {fixed}")
        return 0
    if problems:
        print("\n".join(problems))
        print(f"\nзнахідок: {len(problems)} — виправити: uv run python scripts/text_lint.py --fix")
        return 1
    print("текст чистий: чужих символів і мішаних абеток немає")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
