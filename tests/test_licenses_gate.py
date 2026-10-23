from __future__ import annotations

import sys
from collections.abc import Iterator
from importlib import metadata
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import gen_licenses  # noqa: E402


@pytest.fixture
def without_platform_packages() -> Iterator[None]:
    hidden = set(gen_licenses._PYTHON_LICENSE_OVERRIDE)
    real = metadata.distributions

    def cross_platform_only():
        for dist in real():
            name = dist.metadata["Name"]
            if name and gen_licenses._normalise(name) in hidden:
                continue
            yield dist

    metadata.distributions = cross_platform_only
    try:
        yield
    finally:
        metadata.distributions = real


def test_the_list_is_the_same_without_the_platform_packages(
    without_platform_packages: None,
) -> None:
    current = (ROOT / "docs" / "licenses.md").read_text(encoding="utf-8")
    assert gen_licenses.render() == current


def test_nothing_falls_back_to_unknown(without_platform_packages: None) -> None:
    missing = [name for name, _, lic in gen_licenses.python_packages() if lic == "не вказано"]
    assert not missing, (
        f"{missing} лишаються без ліцензії там, де їх не встановлено. "
        "Додай їх у _PYTHON_LICENSE_OVERRIDE — інакше CI впаде на чужій ОС."
    )
