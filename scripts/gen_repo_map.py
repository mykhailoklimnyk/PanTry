from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "komora"
OUTPUT = ROOT / "docs" / "repo-map.md"

HEADER = """<!--
  ЗГЕНЕРОВАНО автоматично: scripts/gen_repo_map.py
  Руками не правити — правки зникнуть при наступному прогоні.
  Застарілий граф гірший за його відсутність (ADR-09).
-->

# Карта репозиторію

Модулі, їхні публічні імена і залежності всередині `komora`.
"""


@dataclass
class Module:
    name: str
    doc: str
    exports: list[str] = field(default_factory=list)
    depends_on: set[str] = field(default_factory=set)


def first_line(text: str | None) -> str:
    if not text:
        return ""
    return text.strip().splitlines()[0].strip()


def analyse(path: Path) -> Module:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    relative = path.relative_to(PACKAGE.parent).with_suffix("")
    name = ".".join(relative.parts)

    module = Module(name=name, doc=first_line(ast.get_docstring(tree)))

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if not node.name.startswith("_"):
                suffix = "()" if not isinstance(node, ast.ClassDef) else ""
                module.exports.append(f"{node.name}{suffix}")
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.isupper():
                    module.exports.append(target.id)

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("komora."):
            if node.module != name:
                module.depends_on.add(node.module)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("komora.") and alias.name != name:
                    module.depends_on.add(alias.name)

    return module


def collect() -> list[Module]:
    paths = sorted(p for p in PACKAGE.rglob("*.py") if "__pycache__" not in p.parts)
    return [analyse(path) for path in paths]


def render(modules: list[Module]) -> str:
    lines = [HEADER]

    by_package: dict[str, list[Module]] = {}
    for module in modules:
        parts = module.name.split(".")
        package = parts[1] if len(parts) > 2 else "komora"
        by_package.setdefault(package, []).append(module)

    for package in sorted(by_package):
        lines.append(f"\n## `{package}/`\n")
        for module in by_package[package]:
            lines.append(f"### `{module.name}`\n")
            if module.doc:
                lines.append(f"{module.doc}\n")
            if module.exports:
                lines.append("**Експортує:** " + ", ".join(f"`{e}`" for e in module.exports) + "\n")
            if module.depends_on:
                deps = ", ".join(f"`{d}`" for d in sorted(module.depends_on))
                lines.append(f"**Залежить від:** {deps}\n")

    core_leaks = sorted(
        dep
        for module in modules
        if module.name.startswith("komora.core")
        for dep in module.depends_on
        if not dep.startswith("komora.core")
    )
    lines.append("\n## Межа ядра\n")
    if core_leaks:
        lines.append(f"⚠ `core/` тягне назовні: {', '.join(f'`{d}`' for d in core_leaks)}\n")
    else:
        lines.append(
            "`core/` не залежить ні від чого поза собою — умова тестованості тримається.\n"
        )

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Згенерувати docs/repo-map.md")
    parser.add_argument("--check", action="store_true", help="звірити, не переписувати")
    args = parser.parse_args()

    rendered = render(collect())

    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != rendered:
            print("docs/repo-map.md застарів — запусти scripts/gen_repo_map.py", file=sys.stderr)
            return 1
        print("repo-map актуальний")
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(rendered, encoding="utf-8")
    print(f"записано {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
