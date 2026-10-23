from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "docs" / "mutation.json"

STALE_LINES = 150

STATUS = {
    "killed": chr(0x1F389),
    "no_tests": chr(0x1FAE5),
    "timeout": chr(0x23F0),
    "suspicious": chr(0x1F914),
    "survived": chr(0x1F641),
    "skipped": chr(0x1F507),
    "type_checked": chr(0x1F9D9),
}
PROGRESS = re.compile(
    r"(?P<done>\d+)/(?P<total>\d+)\s+"
    + r"\s+".join(f"{glyph}\\s*(?P<{name}>\\d+)" for name, glyph in STATUS.items())
)


def parse(output: str) -> dict[str, int]:
    matches = list(PROGRESS.finditer(output.replace("\r", "\n")))
    if not matches:
        raise SystemExit(
            "У виводі mutmut немає рядка з підсумками. Прогін не дійшов до кінця "
            "або формат змінився — дивись вивід вище."
        )
    return {key: int(value) for key, value in matches[-1].groupdict().items()}


def run_mutmut() -> dict[str, int]:
    print("Прогін mutmut (на Windows не працює — потрібен Linux або WSL)...")
    result = subprocess.run(
        ["mutmut", "run"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    combined = result.stdout + result.stderr
    if "please use the WSL" in combined:
        raise SystemExit(
            "mutmut не запускається на Windows. Прогін іде на Федорі або в CI — "
            "команди в docs/setup.md, розділ «Мутації»."
        )
    return parse(combined)


def snapshot(counts: dict[str, int]) -> dict[str, object]:
    checked = counts["total"] - counts["skipped"]
    score = round(100 * counts["killed"] / checked) if checked else 0
    commit = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()
    return {
        "total": counts["total"],
        "killed": counts["killed"],
        "survived": counts["survived"],
        "timeout": counts["timeout"],
        "no_tests": counts["no_tests"],
        "suspicious": counts["suspicious"],
        "score": score,
        "ran_at": datetime.now(UTC).strftime("%Y-%m-%d"),
        "commit": commit,
    }


def circuit() -> list[str]:
    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    paths = config.get("tool", {}).get("mutmut", {}).get("only_mutate", [])
    if not paths:
        raise SystemExit("У pyproject немає [tool.mutmut] only_mutate — міряти нема що.")
    return list(paths)


def drift(commit: str) -> tuple[int, list[str]]:
    known = subprocess.run(
        ["git", "cat-file", "-e", f"{commit}^{{commit}}"], cwd=ROOT, capture_output=True
    )
    if known.returncode != 0:
        return -1, []

    result = subprocess.run(
        ["git", "diff", "--numstat", commit, "HEAD", "--", *circuit()],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    lines = 0
    files: list[str] = []
    for row in result.stdout.splitlines():
        parts = row.split("\t")
        if len(parts) < 3:
            continue
        added, removed, name = parts[0], parts[1], parts[2]
        lines += sum(int(n) for n in (added, removed) if n.isdigit())
        files.append(name)
    return lines, files


def check_drift() -> int:
    if not SNAPSHOT.exists():
        print("Знімка мутацій немає — цифра на сторінці «Якість» береться нізвідки.")
        return 1

    saved = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    commit = str(saved.get("commit") or "")
    if not commit:
        print("У знімку немає коміта — прив'язати цифру до коду нічим.")
        return 1

    moved, files = drift(commit)
    if moved < 0:
        print(
            f"Коміта {commit} у дереві немає: знімок ні до чого не прив'язаний.\n"
            "Перезамір: docs/setup.md, розділ «Мутації»."
        )
        return 1

    where = f"{saved.get('score')}% ({saved.get('killed')}/{saved.get('total')}), "
    where += f"замір {saved.get('ran_at')} на {commit}"
    if moved > STALE_LINES:
        print(
            f"Знімок протух: {where}.\n"
            f"Відтоді в контурі змінилось {moved} рядків (стеля {STALE_LINES}):\n  "
            + "\n  ".join(files)
            + "\nЦифра описує код, якого вже немає. Перезамір: docs/setup.md.",
        )
        return 1

    print(f"Знімок чинний: {where}; розходження {moved} рядків зі стелі {STALE_LINES}.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Знімок мутаційного прогону")
    parser.add_argument(
        "--drift",
        action="store_true",
        help="перевірити, чи не розійшовся знімок з кодом (без прогону мутантів)",
    )
    parser.add_argument(
        "--check", action="store_true", help="звірити збережений знімок з новим прогоном"
    )
    parser.add_argument(
        "--from-output",
        metavar="ФАЙЛ",
        help="взяти підсумки з готового виводу mutmut (прогін на іншій машині)",
    )
    args = parser.parse_args()

    if args.drift:
        return check_drift()

    if args.from_output:
        counts = parse(Path(args.from_output).read_text(encoding="utf-8", errors="replace"))
    else:
        counts = run_mutmut()
    fresh = snapshot(counts)

    if args.check:
        if not SNAPSHOT.exists():
            print("Знімка немає — прогони без --check.", file=sys.stderr)
            return 1
        saved = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
        keys = ("total", "killed", "survived", "timeout", "no_tests", "suspicious", "score")
        if {k: saved.get(k) for k in keys} != {k: fresh[k] for k in keys}:
            print(
                f"Знімок розійшовся з прогоном.\n  збережено: {saved}\n  зараз:     {fresh}\n"
                "Перезапиши: uv run python scripts/mutation_snapshot.py",
                file=sys.stderr,
            )
            return 1
        print(f"Знімок збігається: {fresh['score']}% ({fresh['killed']}/{fresh['total']})")
        return 0

    SNAPSHOT.write_text(json.dumps(fresh, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    where = SNAPSHOT.relative_to(ROOT)
    print(f"Записано {where}: {fresh['score']}% ({fresh['killed']} з {fresh['total']})")
    if fresh["no_tests"] or fresh["suspicious"]:
        print(
            f"УВАГА: без тестів {fresh['no_tests']}, підозрілих {fresh['suspicious']}. "
            "Це не «вижили» -- під ці мутанти тестів не знайшлось. "
            "Хто саме: uv run mutmut results | grep -v survived",
            file=sys.stderr,
        )
    print("Далі: uv run python scripts/gen_facts.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
