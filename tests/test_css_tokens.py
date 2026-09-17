from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from css_tokens import _DEFINED, _USED, dead_tokens


def test_the_tree_has_no_dead_tokens() -> None:
    assert dead_tokens() == {}


def test_the_check_catches_a_typo() -> None:
    assert _USED.findall("color: var(--ink-soft);") == ["--ink-soft"]
    assert "--ink-soft" not in _DEFINED.findall("color: var(--ink-soft);")


def test_a_fallback_is_not_a_dead_token() -> None:
    assert _USED.findall("padding: var(--gap, 12px);") == []


def test_a_definition_counts_wherever_it_lives() -> None:
    assert _DEFINED.findall(".row { --col: 3; }") == ["--col"]
