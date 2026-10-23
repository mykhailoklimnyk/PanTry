from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "web" / "src" / "lib" / "types.ts"

SKIP = {"HTTPValidationError", "ValidationError"}

HEADER = """\
/**
 * ЗГЕНЕРОВАНО з `api/schemas.py` через `scripts/gen_types.py`. Руками не правити:
 * CI звіряє цей файл `--check`-ом, а правки все одно перезапише наступний прогін.
 * Міняти контракт — у schemas.py, докстрінги полів приїдуть сюди як JSDoc.
 */
"""


COMMENTS = False

_BLOCK = re.compile(r"^[ \t]*/\*.*?\*/[ \t]*\n", re.M | re.S)


def bare(text: str) -> str:
    return text if COMMENTS else _BLOCK.sub("", text).lstrip("\n")


def _quoted_union(values: list[Any]) -> str:
    return " | ".join(f"'{value}'" for value in values)


def ts_type(schema: dict[str, Any], defs: dict[str, Any]) -> str:
    if "$ref" in schema:
        return schema["$ref"].rsplit("/", 1)[-1]

    if "const" in schema:
        return f"'{schema['const']}'"

    if "enum" in schema:
        return _quoted_union(schema["enum"])

    if "anyOf" in schema:
        parts = [ts_type(variant, defs) for variant in schema["anyOf"]]
        if set(parts) >= {"number", "string"}:
            parts = ["number" if p in {"number", "string"} else p for p in parts]
        seen: list[str] = []
        for part in parts:
            if part not in seen:
                seen.append(part)
        return " | ".join(seen)

    if "allOf" in schema and len(schema["allOf"]) == 1:
        return ts_type(schema["allOf"][0], defs)

    match schema.get("type"):
        case "string":
            return "string"
        case "number" | "integer":
            return "number"
        case "boolean":
            return "boolean"
        case "null":
            return "null"
        case "array":
            item = ts_type(schema.get("items", {}), defs)
            return f"({item})[]" if " " in item else f"{item}[]"
        case "object":
            additional = schema.get("additionalProperties")
            if isinstance(additional, dict):
                return f"Record<string, {ts_type(additional, defs)}>"
            return "Record<string, unknown>"

    return "unknown"


def jsdoc(text: str, indent: str = "") -> str:
    lines = text.strip().splitlines()
    if len(lines) == 1:
        return f"{indent}/** {lines[0]} */\n"
    body = "\n".join(f"{indent} * {line}".rstrip() for line in lines)
    return f"{indent}/**\n{body}\n{indent} */\n"


def render_schema(name: str, schema: dict[str, Any], defs: dict[str, Any]) -> str:
    out = ""
    if description := schema.get("description"):
        out += jsdoc(description)

    if "enum" in schema:
        return out + f"export type {name} = {_quoted_union(schema['enum'])}\n"

    out += f"export interface {name} {{\n"
    for prop, prop_schema in schema.get("properties", {}).items():
        if description := prop_schema.get("description"):
            out += jsdoc(description, indent="  ")
        out += f"  {prop}: {ts_type(prop_schema, defs)}\n"
    out += "}\n"
    return out


def generate() -> str:
    from komora.api.app import app

    defs: dict[str, Any] = app.openapi()["components"]["schemas"]
    blocks = [
        render_schema(name, schema, defs)
        for name, schema in defs.items()
        if name not in SKIP
    ]
    return HEADER + "\n" + "\n".join(blocks)


def main() -> int:
    fresh = bare(generate())
    if "--check" in sys.argv:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if current != fresh:
            print(
                "types.ts розійшовся зі schemas.py. "
                "Перегенеруй: uv run python scripts/gen_types.py",
                file=sys.stderr,
            )
            return 1
        print("types.ts синхронний зі schemas.py")
        return 0

    TARGET.write_text(fresh, encoding="utf-8", newline="\n")
    print(f"записано {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
