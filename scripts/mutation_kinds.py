from __future__ import annotations

import argparse
import ast
import difflib
import json
import os
import random
import re
import subprocess
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MUTANTS = ROOT / "mutants"
STATS = MUTANTS / "mutmut-stats.json"
SNAPSHOT = ROOT / "docs" / "mutation_kinds.json"

ORIG = "__mutmut_orig"
MUTANT = re.compile(r"^(?P<function>.+)__mutmut_(?P<number>\d+)$")

TESTS_PER_MUTANT = 60


def _dotted(path: Path) -> str:
    return ".".join(path.relative_to(MUTANTS / "src").with_suffix("").parts)


def all_mutants() -> dict[str, str]:
    found: dict[str, str] = {}
    for path in sorted((MUTANTS / "src").rglob("*.py")):
        module = _dotted(path)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and MUTANT.match(node.name):
                found[f"{module}.{node.name}"] = str(path)
    return found


def not_killed() -> dict[str, str]:
    out = subprocess.run(
        ["mutmut", "results"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8"
    ).stdout
    rows: dict[str, str] = {}
    for line in out.splitlines():
        name, _, status = line.strip().partition(": ")
        if name and status:
            rows[name] = status
    return rows


@lru_cache(maxsize=1)
def _test_map() -> dict[str, list[str]]:
    return json.loads(STATS.read_text(encoding="utf-8"))["tests_by_mangled_function_name"]


def tests_for(mutant: str) -> list[str]:
    match = MUTANT.match(mutant)
    if match is None:
        return []
    return _test_map().get(match["function"], [])


ASSERT = "AssertionError"


def kill_kind(mutant: str, tests: list[str]) -> tuple[str, str]:
    env = {**os.environ, "MUTANT_UNDER_TEST": mutant, "PY_IGNORE_IMPORTMISMATCH": "1"}
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; sys.path.insert(0, 'mutants/src');"
            " import pytest; raise SystemExit(pytest.main(sys.argv[1:]))",
            "-x",
            "-q",
            "--no-header",
            "-p",
            "no:cacheprovider",
            *tests[:TESTS_PER_MUTANT],
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    if result.returncode == 0:
        return "не відтворилось", ""
    text = result.stdout + result.stderr
    first = next((line for line in text.splitlines() if line.startswith("E   ")), "")
    kind = first[4:].partition(":")[0].strip() or "невідомо"
    if kind.startswith("assert") or ASSERT in first:
        kind = ASSERT
    return ("асерт" if kind == ASSERT else "виняток"), first[4:][:120]


def module_of(mutant: str) -> str:
    return mutant.rsplit(".", 1)[0]


def by_module(killed: list[str], per_module: int, seed: int) -> list[str]:
    buckets: dict[str, list[str]] = {}
    for mutant in killed:
        buckets.setdefault(module_of(mutant), []).append(mutant)
    picked: list[str] = []
    for module in sorted(buckets):
        rows = sorted(buckets[module])
        random.Random(f"{seed}:{module}").shuffle(rows)
        picked.extend(rows[:per_module])
    return picked


def sample(size: int, seed: int, *, write: bool, per_module: int = 0, jobs: int = 1) -> int:
    live = not_killed()
    every = all_mutants()
    killed = sorted(set(every) - set(live))
    if not killed:
        raise SystemExit("вбитих мутантів немає — прогін не відбувся або дерево не те")

    random.seed(seed)
    picked = by_module(killed, per_module, seed) if per_module else random.sample(
        killed, min(size, len(killed))
    )
    kinds: Counter[str] = Counter()
    reasons: Counter[str] = Counter()
    per_place: dict[str, Counter[str]] = {}
    unmapped = 0

    def one(mutant: str) -> tuple[str, str, str]:
        tests = tests_for(mutant)
        if not tests:
            return mutant, "без тестів", ""
        kind, why = kill_kind(mutant, tests)
        return mutant, kind, why

    with ThreadPoolExecutor(max_workers=max(1, jobs)) as pool:
        for number, (mutant, kind, why) in enumerate(pool.map(one, picked), 1):
            if kind == "без тестів":
                unmapped += 1
                continue
            kinds[kind] += 1
            per_place.setdefault(module_of(mutant), Counter())[kind] += 1
            if kind not in ("асерт", "не відтворилось"):
                reasons[why.partition(":")[0][:60]] += 1
            print(f"  {number:4}/{len(picked)} {kind:14} {mutant}", flush=True)

    missed = kinds.pop("не відтворилось", 0)
    checked = sum(kinds.values())
    print()
    print(f"Вибірка {checked} з {len(killed)} убитих (сід {seed}).")
    for kind, count in kinds.most_common():
        print(f"  {kind:8} {count:4}  {100 * count / checked:5.1f}%")
    if missed:
        print(
            f"  не відтворилось {missed}: убивця лежить за стелею "
            f"{TESTS_PER_MUTANT} тестів на мутанта — у частки не входять"
        )
    if unmapped:
        print(f"  без тестів у мапі: {unmapped} — це вже не «вбито», а діра в доборі")
    if reasons:
        print("\nЧим падало, коли не асертом:")
        for why, count in reasons.most_common(10):
            print(f"  {count:4}  {why}")

    if per_place:
        print("\nПо модулях (частка асертів, найнижча згори):")
        rows = [
            (module, counts["асерт"], counts["асерт"] + counts["виняток"])
            for module, counts in per_place.items()
            if counts["асерт"] + counts["виняток"]
        ]
        for module, hits, seen in sorted(rows, key=lambda row: (row[1] / row[2], -row[2])):
            print(f"  {100 * hits / seen:5.0f}%  {hits:3}/{seen:<3}  {module}")

    if write:
        SNAPSHOT.write_text(
            json.dumps(
                {
                    "sample": checked,
                    "killed": len(killed),
                    "assert": kinds.get("асерт", 0),
                    "exception": kinds.get("виняток", 0),
                    "unreproduced": missed,
                    "share": round(100 * kinds.get("асерт", 0) / checked) if checked else 0,
                    "seed": seed,
                    "ran_at": datetime.now(UTC).strftime("%Y-%m-%d"),
                },
                ensure_ascii=False,
                indent=1,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"\nЗаписано {SNAPSHOT.relative_to(ROOT)}")
    return 0


def form_of(before: str, after: str) -> str:
    if "log." in before or "log." in after:
        return "журнал: назва події або її аргумент"
    if "XX" in after and "XX" not in before:
        return "рядковий літерал зрізано з країв"
    for pair in (("<=", "<"), (">=", ">"), ("==", "!="), ("is not", "is")):
        if any(sign in before for sign in pair) and any(sign in after for sign in pair):
            return "порівняння зсунуто"
    if re.search(r"\b(and|or)\b", before) and re.search(r"\b(and|or)\b", after):
        return "логічна зв'язка"
    if re.search(r"\b(True|False|None)\b", before) or re.search(r"\b(True|False|None)\b", after):
        return "булеве або None"
    if re.search(r"\d", before) and re.search(r"\d", after):
        return "число зсунуто"
    if "log." in before or "log." in after:
        return "аргумент журналу"
    return "інше"


def survivors() -> int:
    live = {name: status for name, status in not_killed().items() if status == "survived"}
    every = all_mutants()
    forms: Counter[str] = Counter()
    by_module: Counter[str] = Counter()
    cached: dict[str, dict[str, str]] = {}
    shown: dict[str, list[str]] = {}

    for mutant in sorted(live):
        path = every.get(mutant)
        if path is None:
            forms["мутанта немає в дереві"] += 1
            continue
        by_module[mutant.rsplit(".", 2)[0]] += 1
        match = MUTANT.match(mutant)
        bodies = cached.get(path)
        if bodies is None:
            source = Path(path).read_text(encoding="utf-8")
            bodies = cached[path] = {
                node.name: ast.get_source_segment(source, node) or ""
                for node in ast.walk(ast.parse(source))
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            }
        assert match is not None
        origin = bodies.get(f"{match['function'].rsplit('.', 1)[-1]}{ORIG}", "")
        changed = bodies.get(mutant.rsplit(".", 1)[-1], "")
        diff = [
            line
            for line in difflib.unified_diff(origin.splitlines(), changed.splitlines(), n=0)
            if line.startswith(("+", "-"))
            and not line.startswith(("+++", "---"))
            and "__mutmut_" not in line
        ]
        before = next((line[1:].strip() for line in diff if line.startswith("-")), "")
        after = next((line[1:].strip() for line in diff if line.startswith("+")), "")
        form = form_of(before, after)
        forms[form] += 1
        shown.setdefault(form, []).append(f"{mutant}: {before[:60]} -> {after[:60]}")

    print(f"Вижило {sum(forms.values())} мутантів. За формою:")
    for form, count in forms.most_common():
        print(f"  {count:4}  {form}")
        for line in shown.get(form, [])[:3]:
            print(f"          {line}")
    print("\nЗа модулем (перші десять):")
    for module, count in by_module.most_common(10):
        print(f"  {count:4}  {module}")
    print(
        "\nЕквівалентність цим не доводиться: автомат бачить ФОРМУ, а рівність\n"
        "семантики -- ні. Перелік каже, у якому кутку її шукати очима (#33)."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", type=int, default=0, help="скільки вбитих мутантів перевірити")
    parser.add_argument("--seed", type=int, default=326, help="сід вибірки: замір відтворюваний")
    parser.add_argument("--survivors", action="store_true", help="розкласти вижилих за формою")
    parser.add_argument("--snapshot", action="store_true", help="записати docs/mutation_kinds.json")
    parser.add_argument(
        "--per-module", type=int, default=0, help="брати до N убитих З КОЖНОГО модуля"
    )
    parser.add_argument("--jobs", type=int, default=1, help="скільки мутантів ганяти одночасно")
    args = parser.parse_args()

    if not STATS.exists():
        raise SystemExit(
            f"немає {STATS}: спершу `uv run mutmut run` (на Windows не працює, "
            "прогін іде на Федорі — docs/setup.md)"
        )
    if args.survivors:
        return survivors()
    if args.sample or args.per_module:
        return sample(
            args.sample,
            args.seed,
            write=args.snapshot,
            per_module=args.per_module,
            jobs=args.jobs,
        )
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
