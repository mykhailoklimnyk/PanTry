from __future__ import annotations

import json
from pathlib import Path

import pytest

from komora.core import instructions


def _root() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "docs" / "mcp-tools.json").is_file():
            return parent
    raise AssertionError("знімка описів не знайшлось: docs/mcp-tools.json")


ROOT = _root()
SNAPSHOT = ROOT / "docs" / "mcp-tools.json"
REGISTER = ROOT / "src" / "komora" / "mcp" / "verdicts.json"


@pytest.fixture(scope="module")
def tools() -> list[dict[str, object]]:
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def rows() -> list[dict[str, object]]:
    return json.loads(REGISTER.read_text(encoding="utf-8"))


def test_every_instruction_has_a_verdict(
    tools: list[dict[str, object]], rows: list[dict[str, object]]
) -> None:
    report = instructions.audit(
        tools,
        [
            instructions.Verdict(
                tool=str(row["tool"]),
                sha=str(row["sha"]),
                kind=str(row["kind"]),
                verdict=str(row["verdict"]),
                where=str(row.get("where") or ""),
            )
            for row in rows
        ],
    )
    assert report.ok(), (
        "\n".join(report.lines()) + "\nзвести: python scripts/mcp_verdicts.py --sync"
    )
    assert report.judged == len(rows)


def test_quotes_in_the_register_are_the_real_text(
    tools: list[dict[str, object]], rows: list[dict[str, object]]
) -> None:
    live = {
        (str(tool["name"]), instructions.fingerprint(block)): block
        for tool in tools
        for block in instructions.blocks(str(tool["description"]))
    }
    for row in rows:
        block = live[(str(row["tool"]), str(row["sha"]))]
        assert block.startswith(str(row["quote"])), row["sha"]


def test_a_verdict_we_do_not_execute_names_where_it_is_written(
    rows: list[dict[str, object]],
) -> None:
    for row in rows:
        if row["kind"] == "open":
            assert row["where"], row["sha"]


def test_a_renamed_tool_still_carries_its_instructions_to_the_model(
    tools: list[dict[str, object]], rows: list[dict[str, object]]
) -> None:
    live = [{**tool, "name": str(tool["name"]) + "_v2"} for tool in tools]
    judged = [
        instructions.Verdict(
            tool=str(row["tool"]),
            sha=str(row["sha"]),
            kind=str(row["kind"]),
            verdict=str(row["verdict"]),
        )
        for row in rows
    ]
    said = instructions.digest(live, judged, wanted=["silpo_find_products_batch"])
    assert said.unjudged == 0
    assert said.rows[0].startswith(
        "- silpo_find_products_batch_v2 (був silpo_find_products_batch): "
    )
    assert "у Коморі інакше" in said.rows[0]
    assert len(instructions.audit(live, judged).renamed) == len(tools)


def test_a_new_instruction_is_invisible_until_someone_judges_it(
    tools: list[dict[str, object]], rows: list[dict[str, object]]
) -> None:
    block = (
        "REQUIRED FIRST STEP: before any name search you MUST first search by the "
        "numeric lagerId taken from the receipt line."
    )
    live = [
        {**tool, "description": str(tool["description"]) + "\n\n" + block}
        if tool["name"] == "silpo_find_products_batch"
        else tool
        for tool in tools
    ]
    judged = [
        instructions.Verdict(
            tool=str(row["tool"]),
            sha=str(row["sha"]),
            kind=str(row["kind"]),
            verdict=str(row["verdict"]),
        )
        for row in rows
    ]
    said = instructions.digest(live, judged, wanted=["silpo_find_products_batch"])
    assert said.unjudged == 1
    assert "REQUIRED FIRST STEP" not in said.text()

    verdict = instructions.Verdict(
        "silpo_find_products_batch", instructions.fingerprint(block), "code", "виконує код"
    )
    after = instructions.digest(live, [*judged, verdict], wanted=["silpo_find_products_batch"])
    assert after.unjudged == 0
    assert "REQUIRED FIRST STEP" in after.text()
