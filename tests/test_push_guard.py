from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / ".githooks" / "pre-push"
ZERO = "0" * 40


def _shell() -> str:
    found = shutil.which("sh")
    if found:
        return found
    git = shutil.which("git")
    if git:
        candidate = Path(git).resolve().parents[1] / "usr" / "bin" / "sh.exe"
        if candidate.exists():
            return str(candidate)
    raise RuntimeError("немає `sh` -- хук пушу нічим прогнати, а мовчки пропустити не можна")


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", *args], cwd=repo, capture_output=True, text=True, encoding="utf-8"
    )
    assert done.returncode == 0, done.stderr
    return done.stdout.strip()


def _push(repo: Path, line: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [_shell(), str(HOOK)],
        cwd=repo,
        input=line,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _git(tmp_path, "init", "-q", "-b", "master")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "f.txt").write_text("перший", encoding="utf-8")
    _git(tmp_path, "add", "f.txt")
    _git(tmp_path, "commit", "-qm", "без батьків")
    (tmp_path / "f.txt").write_text("другий", encoding="utf-8")
    _git(tmp_path, "commit", "-qam", "з батьком")
    return tmp_path


def test_commit_without_parents_goes_out(repo: Path) -> None:
    orphan = _git(repo, "rev-list", "--max-parents=0", "HEAD")

    done = _push(repo, f"refs/heads/master {orphan} refs/heads/master {ZERO}\n")

    assert done.returncode == 0, done.stderr


def test_history_on_master_is_stopped(repo: Path) -> None:
    head = _git(repo, "rev-parse", "HEAD")

    done = _push(repo, f"refs/heads/master {head} refs/heads/master {ZERO}\n")

    assert done.returncode == 1
    assert "коміт з батьками" in done.stderr


def test_history_on_any_other_branch_is_stopped_too(repo: Path) -> None:
    head = _git(repo, "rev-parse", "HEAD")

    done = _push(repo, f"HEAD {head} refs/heads/чернетка {ZERO}\n")

    assert done.returncode == 1, "історія поїхала повз хук під іншою назвою"


def test_deleting_a_ref_is_not_a_publication(repo: Path) -> None:
    done = _push(repo, f"(delete) {ZERO} refs/heads/старе {ZERO}\n")

    assert done.returncode == 0, done.stderr


def test_every_ref_of_the_push_is_checked(repo: Path) -> None:
    orphan = _git(repo, "rev-list", "--max-parents=0", "HEAD")
    head = _git(repo, "rev-parse", "HEAD")

    done = _push(
        repo,
        f"refs/heads/master {orphan} refs/heads/master {ZERO}\n"
        f"HEAD {head} refs/heads/чернетка {ZERO}\n",
    )

    assert done.returncode == 1, "перший чистий ref не має пропускати другий"
