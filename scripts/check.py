from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

import e2e_port

from komora import runtime

runtime.console()

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class Gate:

    name: str
    command: tuple[str, ...]
    cwd: str = "."
    note: str = ""


PY = ("uv", "run")
NPM = ("npm",)
NPX = ("npx",)


def _touches(paths: Sequence[str], *prefixes: str) -> bool:
    return any(path.startswith(prefixes) for path in paths)


def _has_suffix(paths: Sequence[str], *suffixes: str) -> bool:
    return any(path.endswith(suffixes) for path in paths)


def plan(paths: Sequence[str], *, full: bool = False, e2e: bool = False) -> list[Gate]:
    py = full or _has_suffix(paths, ".py")
    src = full or _touches(paths, "src/")
    web = full or _touches(paths, "web/")
    gates = [Gate("текст", (*PY, "python", "scripts/text_lint.py"))]

    if py:
        gates.append(Gate("стиль (ruff)", (*PY, "ruff", "check", ".")))
    if src:
        gates.append(Gate("типи (ty)", (*PY, "ty", "check", "src")))
    if web:
        gates.append(Gate("токени теми", (*PY, "python", "scripts/css_tokens.py")))
        gates.append(Gate("кнопки без обробника", (*PY, "python", "scripts/dead_buttons.py")))
    if full or _has_suffix(paths, "api/schemas.py"):
        gates.append(Gate("types.ts", (*PY, "python", "scripts/gen_types.py", "--check")))
    if src:
        gates.append(Gate("repo-map", (*PY, "python", "scripts/gen_repo_map.py", "--check")))
    if full or _has_suffix(paths, "pyproject.toml", "uv.lock", "package-lock.json"):
        gates.append(Gate("ліцензії", (*PY, "python", "scripts/gen_licenses.py", "--check")))
    if py:
        gates.append(Gate("facts.ts", (*PY, "python", "scripts/gen_facts.py", "--check")))
        gates.append(Gate("тести", (*PY, "pytest", "-q")))
    if web:
        gates.append(Gate("типи фронта", (*NPM, "run", "check"), cwd="web"))
        if e2e:
            args = ("--reporter=line",) if full else ("--project=desktop", "--reporter=line")
            gates.append(
                Gate(
                    "e2e",
                    (*NPX, "playwright", "test", *args),
                    cwd="web",
                    note="" if full else "лише desktop",
                )
            )
    return gates


def changed(base: str) -> list[str]:
    seen: list[str] = []
    for args in (
        ["git", "diff", "--name-only", f"{base}...HEAD"],
        ["git", "diff", "--name-only", "HEAD"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ):
        done = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
        if done.returncode != 0:
            continue
        seen.extend(line.strip() for line in done.stdout.splitlines() if line.strip())
    return sorted(dict.fromkeys(seen))


def default_base() -> str:
    head = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return "HEAD~1" if head.stdout.strip() in {"master", "main"} else "master"


def resolve(command: Sequence[str]) -> list[str] | None:
    found = shutil.which(command[0])
    return None if found is None else [found, *command[1:]]


def run(gates: Sequence[Gate]) -> int:
    started = time.monotonic()
    for gate in gates:
        mark = time.monotonic()
        print(f"-> {gate.name}" + (f" ({gate.note})" if gate.note else ""))
        args = resolve(gate.command)
        if args is None:
            print()
            print(f"{gate.name}: НЕ ЗАПУСТИЛОСЬ -- немає «{gate.command[0]}» на цій машині.")
            return 127
        if gate.name == "e2e" and e2e_port.check() != 0:
            print()
            print(f"{gate.name}: НЕ ЗАПУСТИЛОСЬ -- порт зайнятий. Решту воріт не гнав.")
            return 1
        done = subprocess.run(args, cwd=ROOT / gate.cwd)
        spent = time.monotonic() - mark
        if done.returncode != 0:
            print(f"\n{gate.name}: ЧЕРВОНЕ ({spent:.0f} с). Решту воріт не гнав.")
            return done.returncode
        print(f"   {gate.name}: чисто ({spent:.0f} с)\n")
    print(f"Усе чисто. Разом {time.monotonic() - started:.0f} с.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Ворота під зміни в дереві")
    parser.add_argument("--base", default=None, help="з чим порівнювати (типово master)")
    parser.add_argument("--full", action="store_true", help="усе, як у CI, обидва проєкти e2e")
    parser.add_argument("--e2e", action="store_true", help="додати e2e (desktop)")
    parser.add_argument("--list", action="store_true", help="показати обране і вийти")
    args = parser.parse_args()

    base = args.base or default_base()
    paths = [] if args.full else changed(base)
    gates = plan(paths, full=args.full, e2e=args.e2e or args.full)

    if args.full:
        print("Повний набір (як у CI).")
    else:
        print(f"Змінених файлів проти {base}: {len(paths)}")
        chosen = {gate.name for gate in gates}
        skipped = [
            g.name
            for g in plan((), full=True, e2e=True)
            if g.name not in chosen and g.name != "e2e"
        ]
        if skipped:
            print(f"Пропущено (нічого відповідного не змінилось): {', '.join(skipped)}")
        if "e2e" not in chosen and any(path.startswith("web/") for path in paths):
            print("E2E не гнався (16 хв): `--e2e` для desktop, `--full` для обох ширин.")
        narrowed = ", ".join(f"{g.name} -- {g.note}" for g in gates if g.note)
        if narrowed:
            print(f"Звужено: {narrowed}. Повну ширину дає `--full` перед комітом.")
    print(f"Ворота: {', '.join(gate.name for gate in gates)}\n")

    return 0 if args.list else run(gates)


if __name__ == "__main__":
    sys.exit(main())
