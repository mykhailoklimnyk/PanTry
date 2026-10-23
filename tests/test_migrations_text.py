from __future__ import annotations

import re
from pathlib import Path

MIGRATIONS = Path(__file__).resolve().parents[1] / "db" / "migrations"
_CREATE = re.compile(r"^\s*create\s+table\s+(?:if\s+not\s+exists\s+)?(\w+)", re.I | re.M)
_DROP = re.compile(r"^\s*drop\s+table\s+(?:if\s+exists\s+)?(\w+)", re.I | re.M)


def _without_comments(sql: str) -> str:
    return "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))


def test_a_table_name_is_created_again_only_after_an_explicit_drop() -> None:
    owner: dict[str, str] = {}
    for path in sorted(MIGRATIONS.glob("*.sql")):
        sql = _without_comments(path.read_text(encoding="utf-8"))
        events = sorted(
            [(m.start(), "create", m.group(1).lower()) for m in _CREATE.finditer(sql)]
            + [(m.start(), "drop", m.group(1).lower()) for m in _DROP.finditer(sql)]
        )
        for _, kind, name in events:
            if kind == "drop":
                owner.pop(name, None)
                continue
            assert name not in owner, (
                f"{path.name}: `create table {name}` уже було в {owner[name]} і не знято "
                "явним `drop table` -- `if not exists` лишить стару форму мовчки"
            )
            owner[name] = path.name


def test_the_receipts_rewrite_is_guarded_by_the_drop() -> None:
    sql = _without_comments((MIGRATIONS / "0001_init.sql").read_text(encoding="utf-8"))
    drop = sql.index("drop table receipts")
    assert drop < sql.index("create table if not exists receipts")
    assert "raise exception" in sql[:drop], "непорожню попередницю міграція не чіпає"
