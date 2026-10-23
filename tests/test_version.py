from __future__ import annotations

from pathlib import Path

from komora.version import deployed_sha


def test_sha_from_file(tmp_path: Path) -> None:
    sha = tmp_path / ".deployed-sha"
    sha.write_text("c5a42d8091f4\n", encoding="utf-8")
    assert deployed_sha(sha_file=sha, env={}) == "c5a42d8091f4"


def test_env_wins_over_file(tmp_path: Path) -> None:
    sha = tmp_path / ".deployed-sha"
    sha.write_text("з файлу", encoding="utf-8")
    assert deployed_sha(sha_file=sha, env={"KOMORA_COMMIT": "з оточення"}) == "з оточення"


def test_no_deploy_is_none(tmp_path: Path) -> None:
    assert deployed_sha(sha_file=tmp_path / "нема", env={}) is None


def test_empty_file_is_none(tmp_path: Path) -> None:
    sha = tmp_path / ".deployed-sha"
    sha.write_text("\n", encoding="utf-8")
    assert deployed_sha(sha_file=sha, env={}) is None


def test_blank_env_falls_through_to_file(tmp_path: Path) -> None:
    sha = tmp_path / ".deployed-sha"
    sha.write_text("з файлу", encoding="utf-8")
    assert deployed_sha(sha_file=sha, env={"KOMORA_COMMIT": "  "}) == "з файлу"


def test_directory_instead_of_file_is_none(tmp_path: Path) -> None:
    assert deployed_sha(sha_file=tmp_path, env={}) is None


def test_second_candidate_when_first_missing(tmp_path: Path, monkeypatch) -> None:
    second = tmp_path / ".deployed-sha"
    second.write_text("з робочого каталогу", encoding="utf-8")
    monkeypatch.setattr(
        "komora.version.SHA_FILES", (tmp_path / "нема", second)
    )
    assert deployed_sha(env={}) == "з робочого каталогу"
