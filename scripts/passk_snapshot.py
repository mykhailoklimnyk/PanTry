from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "docs" / "passk.json"


def _registry() -> dict[str, str]:
    sys.path.insert(0, str(ROOT / "src"))
    from komora.agent import prompts

    prompts.load_all()
    return {name: prompt.digest for name, prompt in prompts.REGISTRY.items()}


def commit() -> str:
    return subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout.strip()


def write(*, runs: int, models: dict[str, dict[str, object]], prompts: dict[str, str]) -> Path:
    payload = {
        "date": datetime.now(UTC).strftime("%Y-%m-%d"),
        "commit": commit(),
        "runs": runs,
        "models": models,
        "prompts": dict(sorted(prompts.items())),
    }
    SNAPSHOT.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return SNAPSHOT


def check() -> int:
    if not SNAPSHOT.exists():
        print(
            "Знімка пасток немає -- число на сторінці «Якість» береться нізвідки.\n"
            "Зняти: uv run python scripts/compare_models.py --runs 5 --snapshot"
        )
        return 1

    saved = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    measured: dict[str, str] = saved.get("prompts") or {}
    if not measured:
        print(
            "У знімку немає жодного хеша промпта: числа ні до чого не прив'язані.\n"
            "Або сценарії не ходять продуктовим промптом узагалі -- і тоді "
            "pass^k міряє модель, а не Комору."
        )
        return 1

    live = _registry()
    moved = [
        f"{name}: {digest} -> {live.get(name, 'промпта більше немає')}"
        for name, digest in measured.items()
        if live.get(name) != digest
    ]
    where = (
        f"pass^{saved.get('runs')} від {saved.get('date')} на {saved.get('commit')}, "
        f"промптів під наглядом {len(measured)}"
    )
    if moved:
        print(
            f"Число пасток протухло: {where}.\n"
            "Ці промпти змінились після заміру:\n  " + "\n  ".join(moved) + "\n"
            "Числа описують текст, якого вже немає. Перезамір: "
            "uv run python scripts/compare_models.py --runs 5 --snapshot"
        )
        return 1

    print(f"Знімок пасток чинний: {where}.")
    unmeasured = sorted(set(live) - set(measured))
    if unmeasured:
        print("Пастками НЕ перевірені: " + ", ".join(unmeasured))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Знімок пасток і ворота його свіжості")
    parser.add_argument(
        "--check",
        action="store_true",
        help="чи не розійшовся знімок з промптами в коді (без викликів моделі)",
    )
    args = parser.parse_args()
    if not args.check:
        print(
            "Знімок пишеться самим прогоном:\n"
            "  uv run python scripts/compare_models.py --runs 5 --snapshot",
            file=sys.stderr,
        )
        return 1
    return check()


if __name__ == "__main__":
    sys.exit(main())
