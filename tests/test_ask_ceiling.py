from __future__ import annotations

import re
from pathlib import Path

from komora.core.ambiguity import MAX_QUESTIONS


def _root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "web" / "src" / "lib" / "ui.ts").is_file():
            return parent
    raise AssertionError("не знайшлось web/src/lib/ui.ts")


def test_the_screen_asks_no_more_at_once_than_the_basket_does() -> None:
    text = (_root() / "web" / "src" / "lib" / "ui.ts").read_text(encoding="utf-8")
    found = re.search(r"export const ASK_AT_ONCE = (\d+)", text)
    assert found is not None, "ASK_AT_ONCE зник з ui.ts -- стеля питань комори знята"
    assert int(found.group(1)) == MAX_QUESTIONS, (
        "стеля питань комори розійшлась із стелею кошика: "
        f"на екрані {found.group(1)}, у коді {MAX_QUESTIONS}"
    )


def test_the_ceiling_is_small_enough_to_stay_a_dialogue() -> None:
    assert MAX_QUESTIONS <= 3
