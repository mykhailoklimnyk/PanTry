from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "protect_branches",
    Path(__file__).resolve().parents[1] / "scripts" / "protect_branches.py",
)
assert _SPEC and _SPEC.loader
protect_branches = importlib.util.module_from_spec(_SPEC)
sys.modules["protect_branches"] = protect_branches
_SPEC.loader.exec_module(protect_branches)


@pytest.mark.parametrize(
    "remote",
    [
        "https://github.com/mykhailoklimnyk/pantry.git",
        "https://github.com/mykhailoklimnyk/pantry",
        "git@github.com:mykhailoklimnyk/pantry.git",
        "mykhailoklimnyk/pantry",
    ],
)
def test_slug_is_read_from_any_form_of_origin(remote: str) -> None:
    assert protect_branches.slug_of(remote) == "mykhailoklimnyk/pantry"


def test_unparsable_origin_is_loud() -> None:
    with pytest.raises(ValueError):
        protect_branches.slug_of("хтозна-що")


def test_master_is_excluded_from_the_ban() -> None:
    condition = protect_branches.PAYLOAD["conditions"]["ref_name"]

    assert condition["include"] == ["~ALL"]
    assert condition["exclude"] == ["refs/heads/master"]


def test_only_creation_is_forbidden() -> None:
    assert [rule["type"] for rule in protect_branches.PAYLOAD["rules"]] == ["creation"]


def test_the_rule_is_enforced_not_advisory() -> None:
    assert protect_branches.PAYLOAD["enforcement"] == "active"
    assert protect_branches.PAYLOAD["target"] == "branch"
