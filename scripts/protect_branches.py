from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from komora import runtime

runtime.console()

ROOT = Path(__file__).resolve().parents[1]

RULESET_NAME = "Гілок, крім master, тут не буває"

PAYLOAD = {
    "name": RULESET_NAME,
    "target": "branch",
    "enforcement": "active",
    "conditions": {"ref_name": {"include": ["~ALL"], "exclude": ["refs/heads/master"]}},
    "rules": [{"type": "creation"}],
}


class Unavailable(RuntimeError):
    """GitHub не дає ruleset на цьому репозиторії — приватний і без Pro."""


def slug_of(remote_url: str) -> str:
    cleaned = remote_url.strip().removesuffix(".git")
    match = re.search(r"([^/:]+/[^/]+)$", cleaned)
    if match is None:
        raise ValueError(f"не розібрав адресу origin: {remote_url}")
    return match.group(1)


def _gh(*args: str, stdin: str | None = None) -> tuple[int, str]:
    done = subprocess.run(
        ["gh", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        input=stdin,
    )
    return done.returncode, (done.stdout + done.stderr).strip()


def _api(*args: str, stdin: str | None = None) -> str:
    code, out = _gh("api", *args, stdin=stdin)
    if code != 0:
        if "Upgrade to GitHub Pro" in out or "make this repository public" in out:
            raise Unavailable(out)
        raise RuntimeError(out)
    return out


def existing(slug: str) -> bool:
    listed = json.loads(_api(f"repos/{slug}/rulesets") or "[]")
    return any(item.get("name") == RULESET_NAME for item in listed)


def apply(slug: str) -> str:
    if existing(slug):
        return f"правило вже стоїть: «{RULESET_NAME}»"
    _api(
        f"repos/{slug}/rulesets",
        "--method",
        "POST",
        "--input",
        "-",
        stdin=json.dumps(PAYLOAD, ensure_ascii=False),
    )
    return f"правило поставлено: «{RULESET_NAME}»"


def ensure() -> str:
    try:
        return apply(slug_of(_api("repos/{owner}/{repo}", "--jq", ".full_name")))
    except Unavailable:
        return "недоступно, поки репозиторій приватний (GitHub дає ruleset публічним або Pro)"
    except (RuntimeError, ValueError) as exc:
        return f"не вдалося: {str(exc).splitlines()[0][:120]}"


def main() -> int:
    code, remote = _gh("repo", "view", "--json", "nameWithOwner", "--jq", ".nameWithOwner")
    if code != 0:
        print(f"не дістав репозиторій з gh: {remote}", file=sys.stderr)
        return 1
    try:
        print(apply(slug_of(remote)))
    except Unavailable:
        print(
            "Ruleset недоступний: репозиторій приватний, а GitHub дає це правило\n"
            "публічним репозиторіям або за Pro. Поставиться само при публікації —\n"
            "`publish.py` кличе цей скрипт після пуша.",
            file=sys.stderr,
        )
        return 2
    except (RuntimeError, ValueError) as exc:
        print(f"не вдалося: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
