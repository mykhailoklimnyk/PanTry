from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import check
import protect_branches
import public_tree

from komora import runtime

runtime.console()

ROOT = Path(__file__).resolve().parents[1]

PUBLIC_TITLE = "ПанTry: агент, який знає, що вдома, і доводить кошик до дверей"

DEPLOY_WORKFLOWS = ("deploy-cloudflare.yml", "deploy-fedora.yml")

CI_WORKFLOW = "ci.yml"

CI_SKIP = ("e2e",)

CI_WAIT_S = 900.0

FRESH = (
    ("мутації", "свіжість мутацій", "mutation_snapshot.py", "--drift"),
    ("пастки", "свіжість пасток", "passk_snapshot.py", "--check"),
)

STALE = tuple(key for key, *_ in FRESH)


@dataclass(frozen=True, slots=True)
class Verdict:

    settled: bool
    refusal: str | None = None


def verdict(jobs: Sequence[Mapping[str, Any]], skip: Sequence[str] = CI_SKIP) -> Verdict:
    watched = [job for job in jobs if job.get("name") not in skip]
    if not watched:
        return Verdict(settled=False)

    done = [job for job in watched if job.get("status") == "completed"]
    red = [job for job in done if job.get("conclusion") != "success"]
    if red:
        named = ", ".join(f"{job.get('name')} -- {job.get('conclusion')}" for job in red)
        return Verdict(settled=True, refusal=f"ворота CI не зелені: {named}")
    if len(done) < len(watched):
        return Verdict(settled=False)
    return Verdict(settled=True)


def _gh_json(*args: str) -> Any:
    done = subprocess.run(["gh", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if done.returncode != 0:
        return None
    try:
        return json.loads(done.stdout)
    except json.JSONDecodeError:
        return None


def ci_jobs(commit: str) -> list[dict[str, Any]] | None:
    runs = _gh_json(
        "run", "list", "--workflow", CI_WORKFLOW, "--limit", "20", "--json", "databaseId,headSha"
    )
    for run in runs or ():
        if run.get("headSha") == commit:
            view = _gh_json("run", "view", str(run["databaseId"]), "--json", "jobs")
            return None if view is None else list(view.get("jobs", ()))
    return None


def await_ci(
    commit: str,
    *,
    jobs: Callable[[str], list[dict[str, Any]] | None] = ci_jobs,
    timeout_s: float = CI_WAIT_S,
    pause_s: float = 10.0,
    clock: Callable[[], float] = time.monotonic,
    rest: Callable[[float], None] = time.sleep,
) -> str | None:
    deadline = clock() + timeout_s
    while True:
        seen = jobs(commit)
        if seen is not None:
            answer = verdict(seen)
            if answer.settled:
                return answer.refusal
        if clock() >= deadline:
            return f"CI не відповів за {timeout_s / 60:.0f} хв"
        rest(pause_s)


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode != 0:
        raise SystemExit(f"git {' '.join(args)}: {result.stderr.strip()}")
    return result.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description="Опублікувати HEAD одним комітом")
    parser.add_argument("--no-deploy", action="store_true", help="не запускати деплої")
    parser.add_argument("--no-tests", action="store_true", help="без pytest по публічному дереву")
    parser.add_argument(
        "--with-e2e",
        action="store_true",
        help="додати e2e до воріт публікації (типово вони йдуть окремо, раз на день)",
    )
    parser.add_argument(
        "--stale",
        nargs="+",
        choices=STALE,
        default=(),
        metavar="ВОРОТА",
        help=(
            "не перевіряти свіжість названих цифр (пастки, мутації): вони "
            "лікуються ПРОГОНОМ на пів години, а не правкою коду. Пропущене "
            "називає себе в журналі публікації, і перезамір перед подачею "
            "лишається обов'язковим"
        ),
    )
    parser.add_argument(
        "--keep-comments",
        action="store_true",
        help="не знімати коментарі з публічного дерева (репозиторій ще приватний)",
    )
    args = parser.parse_args()

    if _git("status", "--porcelain"):
        print(
            "Робоче дерево не чисте — спершу закоміть локально (повна історія "
            "лишається тут, публікується лише дерево HEAD).",
            file=sys.stderr,
        )
        return 1

    history = ROOT / "docs" / "history.md"
    if not history.exists():
        print("docs/history.md зник — літопис ведеться саме там.", file=sys.stderr)
        return 1
    if not _git("log", "-1", "--format=%H", "--", "docs/history.md"):
        print("docs/history.md не закомічений — літопис пишеться ДО публікації.", file=sys.stderr)
        return 1

    for key, label, script, flag in FRESH:
        if key in args.stale:
            print(
                f"ПРОПУЩЕНО: {label}. Цифра на сторінці «Якість» може описувати "
                "код, якого вже немає — перезамір перед подачею обов'язковий."
            )
            continue
        drift = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / script), flag],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if drift.returncode != 0:
            print(drift.stdout + drift.stderr, file=sys.stderr)
            print(
                f"{label}: цифра на сторінці «Якість» описує код, якого вже немає.\n"
                "Перезамір — docs/setup.md.",
                file=sys.stderr,
            )
            return 1

    if args.with_e2e:
        print("Ворота перед публікацією (повний набір, як у CI):")
    else:
        print("Ворота перед публікацією (БЕЗ e2e -- окремим прогоном, `--with-e2e` поверне):")
    if check.run(check.plan([], full=True, e2e=args.with_e2e)) != 0:
        print(
            "Ворота не пройдені -- публікації не було. CI впав би на вже "
            "опублікованому коміті, а force-пуш назад не відкотиш акуратно.",
            file=sys.stderr,
        )
        return 1

    tree_started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="komora-public-") as workspace:
        try:
            dest = Path(workspace) / "tree"
            report = public_tree.build(dest, tests=not args.no_tests, strip=not args.keep_comments)
            tree, executables = public_tree.write_tree(dest)
        except public_tree.Broken as error:
            print(f"Публічне дерево не зібралось:\n{error}", file=sys.stderr)
            return 1
    print(
        f"Публічне дерево ({time.monotonic() - tree_started:.0f} с): {public_tree.describe(report)}"
    )
    print(f"  виконуваних файлів: {executables}")

    head_date = _git("log", "-1", "--format=%cs")
    message = (
        f"{PUBLIC_TITLE}\n\n"
        f"Стан на {head_date}. Коментарі зняті на публікації, робочі нотатки\n"
        "і повна історія розробки лишаються в приватному репозиторії.\n\n"
        "Co-Authored-By: Claude Code <noreply@anthropic.com>"
    )
    commit = _git("commit-tree", tree, "-m", message)
    _git("push", "--force", "origin", f"{commit}:refs/heads/master")
    print(f"Опубліковано: origin/master → {commit[:9]} (публічне дерево, без історії)")
    repo_url = _git("remote", "get-url", "origin").removesuffix(".git")
    print(f"  версія: {repo_url}/commit/{commit}")
    print(f"  локальний HEAD: {_git('rev-parse', '--short', 'HEAD')} (історія лишається вдома)")
    print(f"  гілки: {protect_branches.ensure()}")

    if args.no_deploy:
        return 0

    print(f"Ворота CI на цьому коміті (крім: {', '.join(CI_SKIP)}), типово ~1 хв:")
    refusal = await_ci(commit)
    if refusal is not None:
        print(f"ДЕПЛОЮ НЕ БУЛО: {refusal}", file=sys.stderr)
        print(
            "Опубліковане нікуди не зникло -- на origin/master лежить новий",
            "коміт, а прод лишився на попередньому. Це безпечний бік:",
            "неперевірені міграції накочує саме деплой, і саме його ми не",
            "запустили. Полагодити і опублікувати знову -- або, коли CI",
            "позеленіє, руками:",
            "  gh workflow run deploy-fedora.yml && gh workflow run deploy-cloudflare.yml",
            sep="\n",
            file=sys.stderr,
        )
        return 1
    print("  CI: зелено")
    for workflow in DEPLOY_WORKFLOWS:
        run = subprocess.run(
            ["gh", "workflow", "run", workflow], cwd=ROOT, capture_output=True, text=True
        )
        status = "запущено" if run.returncode == 0 else f"не вдалося: {run.stderr.strip()}"
        print(f"  {workflow}: {status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
