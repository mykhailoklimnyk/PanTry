from __future__ import annotations

import sys
from pathlib import Path

from komora.db.canonical import canonical

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from public_tree import strip_sql  # noqa: E402

MIGRATIONS = sorted((ROOT / "db" / "migrations").glob("*.sql"))


def test_the_publication_cannot_change_a_checksum() -> None:
    assert MIGRATIONS, "міграцій не знайдено — перевір шлях"
    for path in MIGRATIONS:
        source = path.read_text(encoding="utf-8")
        stripped, _ = strip_sql(source)
        assert canonical(source) == canonical(stripped), path.name


def test_comments_do_not_count() -> None:
    assert canonical("-- чому\nselect 1;") == canonical("select 1;")
    assert canonical("select /* чому */ 1;") == "select 1;"


def test_a_block_comment_can_nest() -> None:
    assert canonical("select /* а /* вкладений */ ще */ 1;") == "select 1;"


def test_a_dash_inside_a_literal_is_data() -> None:
    assert canonical("insert into t values ('a -- не коментар');") == (
        "insert into t values ('a -- не коментар');"
    )


def test_a_dollar_quoted_body_survives_whole() -> None:
    source = "create function f() returns int as $$\n-- усередині\nselect 1;\n$$ language sql;"
    assert "-- усередині" in canonical(source)


def test_a_quoted_identifier_is_not_touched() -> None:
    assert canonical('select "дивна--назва" from t;') == 'select "дивна--назва" from t;'


def test_spaces_collapse_but_meaning_does_not() -> None:
    assert canonical("select\n\n   1,\t2;") == "select 1, 2;"
    assert canonical("select 'два  пробіли';") == "select 'два  пробіли';"


def test_a_real_change_still_changes_the_canon() -> None:
    assert canonical("alter table t add column a int;") != canonical(
        "alter table t add column b int;"
    )
