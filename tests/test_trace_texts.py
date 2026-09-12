from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

JARGON = re.compile(r"\b\d{2}\.\d{2}\b|\bAPI\b|\bкод\b|#\d{2,3}\b|замір")
FIELDS = {"why", "result_summary", "decision", "note", "summary"}


def _texts(node: object):
    if isinstance(node, dict):
        for key, value in node.items():
            if key in FIELDS and isinstance(value, str):
                yield value
            yield from _texts(value)
    elif isinstance(node, list):
        for item in node:
            yield from _texts(item)


@pytest.mark.parametrize("golden", ["basket_golden.json", "route_golden.json"])
def test_trace_texts_speak_to_the_guest(golden: str) -> None:
    data = json.loads((Path(__file__).parent / "fixtures" / golden).read_text(encoding="utf-8"))
    bad = sorted({text for text in _texts(data) if JARGON.search(text)})
    assert not bad, bad
