from __future__ import annotations

import ast
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import publish  # noqa: E402

CI = ROOT / ".github" / "workflows" / "ci.yml"

NEEDS_DB = ("komora-migrate", "check_receipt_store.py")


def _ci() -> dict:
    return yaml.safe_load(CI.read_text(encoding="utf-8"))


def _backend_steps() -> list[dict]:
    return _ci()["jobs"]["backend"]["steps"]


def _index_of(fragment: str) -> int:
    for number, step in enumerate(_backend_steps()):
        if fragment in str(step.get("run", "")):
            return number
    raise AssertionError(f"кроку з «{fragment}» у job `backend` немає")


def test_migrations_run_before_anything_that_can_cancel_them() -> None:
    assert _index_of("komora-migrate") < _index_of("pytest")
    assert _index_of("komora-migrate") < _index_of("ruff check")
    assert _index_of("komora-migrate") < _index_of("ty check")


def test_the_live_store_check_follows_the_migrations_and_not_the_other_way() -> None:
    assert _index_of("komora-migrate") < _index_of("check_receipt_store.py")


def test_the_database_steps_are_the_first_named_ones() -> None:
    named = [step for step in _backend_steps() if "name" in step]
    first = [str(step.get("run", "")) for step in named[: len(NEEDS_DB)]]
    for needle in NEEDS_DB:
        assert any(needle in run for run in first), needle


def test_the_deploy_waits_for_ci_before_it_dispatches_anything() -> None:
    tree = ast.parse((ROOT / "scripts" / "publish.py").read_text(encoding="utf-8"))
    main = next(
        node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main"
    )

    def mentions(node: ast.AST, name: str) -> bool:
        return any(isinstance(inner, ast.Name) and inner.id == name for inner in ast.walk(node))

    waits = [i for i, stmt in enumerate(main.body) if mentions(stmt, "await_ci")]
    dispatches = [
        i
        for i, stmt in enumerate(main.body)
        if isinstance(stmt, ast.For) and mentions(stmt.iter, "DEPLOY_WORKFLOWS")
    ]

    assert waits, "деплой не чекає на CI взагалі -- це і є #321"
    assert dispatches, "диспатчу деплоїв у main() немає"
    assert max(waits) < min(dispatches)


def test_a_job_that_is_still_running_is_not_a_green_one() -> None:
    running = [{"name": "backend", "status": "in_progress", "conclusion": None}]
    assert publish.verdict(running).settled is False

    green = [{"name": "backend", "status": "completed", "conclusion": "success"}]
    answer = publish.verdict(green)
    assert answer.settled and answer.refusal is None


def test_an_empty_job_list_is_not_a_green_one() -> None:
    assert publish.verdict([]).settled is False


def test_a_red_job_refuses_the_deploy_and_names_itself() -> None:
    jobs = [
        {"name": "backend", "status": "completed", "conclusion": "failure"},
        {"name": "frontend", "status": "completed", "conclusion": "success"},
    ]
    answer = publish.verdict(jobs)

    assert answer.settled and answer.refusal
    assert "backend" in answer.refusal and "failure" in answer.refusal
    assert "frontend" not in answer.refusal


def test_only_success_counts_as_green() -> None:
    for conclusion in ("skipped", "cancelled", "timed_out", "action_required"):
        jobs = [{"name": "backend", "status": "completed", "conclusion": conclusion}]
        answer = publish.verdict(jobs)
        assert answer.settled and answer.refusal, conclusion


def test_a_red_job_refuses_before_the_slow_ones_finish() -> None:
    jobs = [
        {"name": "backend", "status": "completed", "conclusion": "failure"},
        {"name": "secrets", "status": "in_progress", "conclusion": None},
    ]
    assert publish.verdict(jobs).refusal


def test_e2e_is_the_only_job_the_deploy_does_not_wait_for() -> None:
    assert publish.CI_SKIP == ("e2e",)

    jobs = [
        {"name": "backend", "status": "completed", "conclusion": "success"},
        {"name": "e2e", "status": "in_progress", "conclusion": None},
    ]
    assert publish.verdict(jobs).settled is True


def test_the_skipped_names_are_real_jobs_of_this_ci() -> None:
    jobs = set(_ci()["jobs"])

    assert set(publish.CI_SKIP) <= jobs, publish.CI_SKIP
    assert jobs - set(publish.CI_SKIP), "чекати нема на що -- ворота порожні"


def test_a_new_ci_job_is_waited_for_without_anyone_remembering() -> None:
    jobs = [
        {"name": "backend", "status": "completed", "conclusion": "success"},
        {"name": "новий-невідомий", "status": "in_progress", "conclusion": None},
    ]
    assert publish.verdict(jobs).settled is False


def test_the_wait_keeps_asking_until_ci_settles() -> None:
    answers = [
        None,
        [{"name": "backend", "status": "in_progress", "conclusion": None}],
        [{"name": "backend", "status": "completed", "conclusion": "success"}],
    ]
    asked: list[str] = []

    def jobs(commit: str) -> list[dict] | None:
        asked.append(commit)
        return answers[len(asked) - 1]

    refusal = publish.await_ci(
        "abc", jobs=jobs, timeout_s=100.0, clock=lambda: 0.0, rest=lambda _: None
    )

    assert refusal is None
    assert asked == ["abc", "abc", "abc"]


def test_the_wait_gives_up_with_a_reason_instead_of_deploying() -> None:
    ticks = iter([0.0, 0.0, 999.0])

    refusal = publish.await_ci(
        "abc",
        jobs=lambda _: None,
        timeout_s=10.0,
        clock=lambda: next(ticks),
        rest=lambda _: None,
    )

    assert refusal and "CI" in refusal


def test_the_wait_asks_about_this_commit_and_not_the_latest_run() -> None:
    seen: list[str] = []
    publish.await_ci(
        "deadbeef",
        jobs=lambda commit: seen.append(commit) or [],  # type: ignore[func-returns-value]
        timeout_s=0.0,
        clock=lambda: 0.0,
        rest=lambda _: None,
    )
    assert seen == ["deadbeef"]


def test_a_skipped_freshness_gate_names_itself_out_loud():
    source = (ROOT / "scripts" / "publish.py").read_text(encoding="utf-8")

    assert "--stale" in source, "вимикача воріт свіжості немає"
    assert "if key in args.stale:" in source, "прапорець є, а ворота його не читають"
    skip = source[source.index("if key in args.stale:") :][:400]
    assert "ПРОПУЩЕНО" in skip, "пропуск мовчазний: на екрані він не відрізниться від перевірки"
    assert "перезамір" in skip, "пропуск не каже, чим саме за нього платять"
