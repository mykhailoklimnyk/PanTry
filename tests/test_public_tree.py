from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from public_tree import (  # noqa: E402
    AS_IS,
    CI_DROP_STEP,
    CI_WORKFLOW,
    LINE_COMMENT_NAMES,
    LINE_COMMENT_SUFFIXES,
    LOCAL_ONLY,
    PUBLIC_DOCS,
    PUBLIC_SCRIPTS,
    QUIET,
    QUIET_NAMES,
    README_REWRITES,
    WEB_SUFFIXES,
    Broken,
    bare_generator,
    broken_links,
    drop_ci_step,
    env_pairs,
    is_public,
    mute_docstrings,
    strip_html,
    strip_jsonc,
    strip_line_comments,
    strip_python,
    strip_sql,
    strip_yaml,
    tidy,
    verify_env,
    verify_python,
    verify_step_gone,
    verify_toml,
    verify_yaml,
)

MODULE_AND_FUNCTION = '"""Опис модуля."""\n\n\ndef f():\n    """Чому саме так."""\n    return 1\n'

HANDLED_HERE = frozenset({".py", ".yml", ".yaml", ".jsonc", ".sql", ".html"})

WORKING_TREE = (ROOT / "CLAUDE.md").exists()
only_working_tree = pytest.mark.skipif(
    not WORKING_TREE, reason="перевіряє робоче дерево; у публічному правила вже застосовані"
)


def test_docs_stay_home_except_those_with_an_outside_reader() -> None:
    assert not is_public("docs/measured.md")
    assert not is_public("docs/history.md")
    assert not is_public("CLAUDE.md")
    assert is_public("docs/licenses.md")
    assert is_public("docs/mutation.json")
    assert is_public("docs/passk.json")
    assert is_public("src/komora/core/cycles.py")


@only_working_tree
def test_the_defence_of_the_live_host_stays_home() -> None:
    for path in LOCAL_ONLY:
        assert (ROOT / path).exists(), f"{path} у списку є, у дереві немає"
        assert not is_public(path)


def test_comments_go_and_docstrings_stay() -> None:
    source = '"""Докстрінг лишається."""\n# ціле пояснення\nx = 1  # хвіст\n'
    text, count = strip_python(source)
    assert text == '"""Докстрінг лишається."""\nx = 1\n'
    assert count == 2
    verify_python(source, text)


def test_docstrings_go_where_they_are_a_working_journal() -> None:
    source = 'def f():\n    """Чому саме так (#47)."""\n    return 1\n'
    text, count = strip_python(source, docstrings=True)
    assert text == "def f():\n    return 1\n"
    assert count == 1
    verify_python(source, text, docstrings=True)


def test_a_docstring_that_is_the_whole_body_becomes_an_ellipsis() -> None:
    source = 'class Broken(Exception):\n    """Пояснення."""\n'
    text, count = strip_python(source, docstrings=True)
    assert text == "class Broken(Exception):\n    ...\n"
    assert count == 1
    verify_python(source, text, docstrings=True)


def test_attribute_docstrings_and_stray_strings_go_too() -> None:
    source = (
        "class Facts:\n"
        "    keeps: str | None = None\n"
        '    """Чому так -- довгий опис рішення."""\n'
        "    aisle: str | None = None\n"
        "\n"
        "\n"
        "def f():\n"
        "    x = 1\n"
        '    """Рядок замість коментаря."""\n'
        "    return x\n"
    )
    text, count = strip_python(source, docstrings=True)
    assert '"""' not in text
    assert count == 2
    verify_python(source, text, docstrings=True)


def test_a_module_that_is_only_a_description_becomes_empty() -> None:
    source = '"""Ручні джоби: нагрів кешу назв."""\n'
    text, count = strip_python(source, docstrings=True)
    assert text.strip() == ""
    assert count == 1
    verify_python(source, text, docstrings=True)


def test_a_one_line_definition_keeps_its_docstring() -> None:
    source = 'def f(): "doc"\n'
    text, count = strip_python(source, docstrings=True)
    assert text == source
    assert count == 0


def test_the_docstring_proof_still_catches_a_broken_strip() -> None:
    with pytest.raises(Broken):
        verify_python(
            'def f():\n    """d"""\n    return 1\n', "def f():\n    return 2\n", docstrings=True
        )


def test_docstrings_are_muted_everywhere_and_scripts_go_by_the_list() -> None:
    assert mute_docstrings("tests/test_runs.py")
    assert mute_docstrings("scripts/gen_facts.py")
    assert mute_docstrings("src/komora/api/schemas.py")
    assert is_public("scripts/public_tree.py")
    assert is_public("scripts/strip_web.mjs")
    assert not is_public("scripts/measure_touch.py")
    assert not is_public("scripts/probe_revocation.py")


def test_no_file_keeps_its_module_docstring() -> None:
    muted, count = strip_python(MODULE_AND_FUNCTION, docstrings=True)
    assert '"""' not in muted
    assert count == 2


def test_the_generator_switch_is_turned_off_in_the_public_copy(tmp_path: Path) -> None:
    generator = tmp_path / "gen_facts.py"
    generator.write_text("COMMENTS = True\nX = 1\n", encoding="utf-8")

    bare_generator(generator)

    assert generator.read_text(encoding="utf-8") == "COMMENTS = False\nX = 1\n"
    with pytest.raises(Broken):
        bare_generator(generator)


def test_a_hash_inside_a_string_is_not_a_comment() -> None:
    source = 'url = "https://silpo.ua/#кошик"  # чому саме так\n'
    text, _ = strip_python(source)
    assert text == 'url = "https://silpo.ua/#кошик"\n'


def test_directives_survive() -> None:
    source = "import json  # noqa: F401\nvalue = 1  # pragma: no cover\n"
    text, count = strip_python(source)
    assert text == source
    assert count == 0


def test_a_shebang_is_not_a_comment() -> None:
    source = "#!/usr/bin/env python\n# пояснення\nx = 1\n"
    text, _ = strip_python(source)
    assert text == "#!/usr/bin/env python\nx = 1\n"


def test_the_python_proof_catches_a_broken_strip() -> None:
    with pytest.raises(Broken):
        verify_python("x = 1\n", "x = 2\n")


@only_working_tree
def test_python_ast_survives_a_real_module() -> None:
    module = ROOT / "src" / "komora" / "core" / "cycles.py"
    source = module.read_text(encoding="utf-8")
    text, count = strip_python(source)
    assert count > 0
    assert ast.dump(ast.parse(source)) == ast.dump(ast.parse(text))


def test_only_whole_line_comments_go_from_configs() -> None:
    source = "# чому саме так\nExecStart=/usr/bin/komora  # хвіст\n"
    text, count = strip_line_comments(source)
    assert text == "ExecStart=/usr/bin/komora  # хвіст\n"
    assert count == 1


def test_a_comment_inside_a_heredoc_is_data() -> None:
    source = "# пояснення\ncat <<EOF > /etc/komora.conf\n# так і має лягти на сервер\nEOF\n"
    text, count = strip_line_comments(source, shell=True)
    assert "# так і має лягти на сервер" in text
    assert count == 1


def test_yaml_keeps_hashes_inside_a_block_scalar() -> None:
    source = (
        "jobs:\n  a:\n    steps:\n      # наше пояснення\n"
        "      - run: |\n          # крок\n          echo 1\n"
    )
    text, count = strip_yaml(source)
    assert count == 1
    assert "# крок" in text
    verify_yaml(source, text)


def test_the_yaml_proof_catches_a_lost_line() -> None:
    with pytest.raises(Broken):
        verify_yaml("a: 1\nb: 2\n", "a: 1\n")


def test_the_toml_proof_catches_a_lost_key() -> None:
    with pytest.raises(Broken):
        verify_toml('a = "1"\nb = "2"\n', 'a = "1"\n')


def test_jsonc_loses_only_whole_line_comments() -> None:
    source = '{\n  // чому\n  "main": "worker.js"\n}\n'
    text, count = strip_jsonc(source)
    assert text == '{\n  "main": "worker.js"\n}\n'
    assert count == 1


def test_sql_loses_its_own_comment_lines() -> None:
    source = "-- чому саме так\nCREATE TABLE t (id int);  -- хвіст\n"
    text, count = strip_sql(source)
    assert text == "CREATE TABLE t (id int);  -- хвіст\n"
    assert count == 1


def test_a_comment_inside_a_function_body_is_data() -> None:
    source = (
        "-- наше пояснення\n"
        "CREATE FUNCTION f() RETURNS int AS $$\n"
        "-- усередині тіла\n"
        "SELECT 1;\n"
        "$$ LANGUAGE sql;\n"
    )
    text, count = strip_sql(source)
    assert "-- усередині тіла" in text
    assert count == 1


def test_a_comment_inside_a_multiline_literal_is_data() -> None:
    source = "INSERT INTO t VALUES ('перший рядок\n-- другий\n');\n"
    text, count = strip_sql(source)
    assert count == 0
    assert text == source


def test_html_comments_go_but_not_from_script() -> None:
    source = "<!-- чому viewport-fit -->\n<body>\n<script>// інша мова</script>\n</body>\n"
    text, count = strip_html(source)
    assert count == 1
    assert "viewport-fit" not in text
    assert "// інша мова" in text


@only_working_tree
def test_every_kind_of_file_is_either_stripped_or_named_quiet() -> None:
    handled = WEB_SUFFIXES | LINE_COMMENT_SUFFIXES | QUIET | HANDLED_HERE
    unknown = {
        Path(path).suffix or Path(path).name
        for path in _tracked()
        if Path(path).suffix not in handled
        and Path(path).name not in (LINE_COMMENT_NAMES | QUIET_NAMES)
    }
    assert not unknown, f"тип файлу поза списками — вирішити, чистимо його чи ні: {unknown}"


def _tracked() -> list[str]:
    done = subprocess.run(
        ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8"
    )
    return done.stdout.split()


def test_blank_lines_do_not_pile_up() -> None:
    assert tidy("a\n\n\n\n\n\nb\n") == "a\n\n\nb\n"


@only_working_tree
def test_a_step_leaves_with_its_own_lines_only() -> None:
    workflow = (ROOT / CI_WORKFLOW).read_text(encoding="utf-8")
    patched = drop_ci_step(workflow, CI_DROP_STEP)
    verify_step_gone(workflow, patched)
    assert yaml.safe_load(patched)["jobs"].keys() == yaml.safe_load(workflow)["jobs"].keys()


def test_an_unknown_step_stops_the_publication() -> None:
    with pytest.raises(Broken):
        drop_ci_step((ROOT / CI_WORKFLOW).read_text(encoding="utf-8"), "такого кроку немає")


@only_working_tree
def test_the_rewrites_still_match_the_readme() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    missing = [old.splitlines()[0] for old, _ in README_REWRITES if old not in readme]
    assert not missing, f"README змінився, заміни в public_tree.py відстали: {missing}"


def test_files_named_as_untouchable_are_really_there() -> None:
    for path in AS_IS | PUBLIC_DOCS:
        assert (ROOT / path).exists(), f"{path} у списку є, у дереві немає"


def test_every_doc_the_facts_are_built_from_goes_public() -> None:
    source = (ROOT / "scripts" / "gen_facts.py").read_text(encoding="utf-8")
    needed = {f"docs/{name}" for name in re.findall(r'ROOT / "docs" / "([^"]+\.json)"', source)}
    assert needed, "gen_facts.py більше не читає знімків з docs/ — онови ворота"
    missing = sorted(needed - PUBLIC_DOCS)
    assert missing == [], (
        f"{missing} читає gen_facts.py, але назовні вони не їдуть: публічний CI "
        "впаде на вже опублікованому коміті."
    )


def test_every_doc_the_tests_actually_read_goes_public() -> None:
    reads = re.compile(r"read_text|read_bytes|\bopen\(|is_file\(|exists\(")
    named = re.compile(r'"docs"\s*/\s*"([\w.-]+)"|"docs/([\w.-]+\.\w+)"')
    homeless: dict[str, list[str]] = {}
    for path in sorted((ROOT / "tests").rglob("*.py")):
        rel = path.relative_to(ROOT).as_posix()
        public, _ = strip_python(path.read_text(encoding="utf-8"), docstrings=mute_docstrings(rel))
        rows = public.split("\n")
        for number, row in enumerate(rows, start=1):
            for match in named.finditer(row):
                near = "\n".join(rows[max(0, number - 3) : number + 2])
                if not reads.search(near):
                    continue
                doc = f"docs/{match.group(1) or match.group(2)}"
                if doc not in PUBLIC_DOCS:
                    homeless.setdefault(doc, []).append(f"{rel}:{number}")
    assert not homeless, (
        f"тести читають {sorted(homeless)}, а назовні воно не їде: на публічному "
        f"дереві падає ВЕСЬ збір тестів, тобто вже опублікований коміт. "
        f"Місця: {homeless}"
    )


def test_broken_links_see_what_is_missing(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("[є](b.md) і [немає](нема.md)", encoding="utf-8")
    (tmp_path / "b.md").write_text("тут", encoding="utf-8")
    assert broken_links(tmp_path) == ["a.md → нема.md"]


def test_outside_links_are_not_our_files(tmp_path: Path) -> None:
    (tmp_path / "a.md").write_text("[сайт](https://silpo.ua) і [якір](#розділ)", encoding="utf-8")
    assert broken_links(tmp_path) == []


def test_two_comment_blocks_do_not_leave_a_double_blank():
    got, _ = strip_python("from a import b\n\n#: перший\n#: блок\n\n#: другий\nX = 1\n")

    assert got == "from a import b\n\nX = 1\n"


def test_two_blank_lines_written_by_hand_survive():
    got, _ = strip_python("X = 1\n\n\n# нотатка\ndef f():\n    return 1\n")

    assert got == "X = 1\n\n\ndef f():\n    return 1\n"


def test_a_binary_file_in_the_tree_is_left_as_is(tmp_path) -> None:
    from public_tree import Report, strip_tree

    png = bytes([0x89]) + b"PNG" + bytes(range(256))
    (tmp_path / "logo.png").write_bytes(png)
    (tmp_path / "a.py").write_text("x = 1  # коментар" + chr(10), encoding="utf-8")
    report = Report()
    strip_tree(tmp_path, report)
    assert (tmp_path / "logo.png").read_bytes() == png
    assert "коментар" not in (tmp_path / "a.py").read_text(encoding="utf-8")


def test_readme_badges_take_their_numbers_from_where_the_numbers_live() -> None:
    from public_tree import FACT_MARKS, fact_badges

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    present = [mark for mark in FACT_MARKS if mark in readme]
    assert len(present) in (0, len(FACT_MARKS)), f"заглушки лише частково: {present}"
    if not present:
        assert "badge/pass%5E5-" in readme and "%2F" in readme, "бейджі без чисел"
    values = fact_badges(ROOT)
    assert set(values) == set(FACT_MARKS)
    assert values["__TESTS__"].isdigit()
    assert values["__MUTATION__"].endswith("%25")
    assert "%2F" in values["__PASSK__"], "pass^5 без дробу"


def test_every_script_a_test_loads_by_path_is_public() -> None:
    import re

    loaded: set[str] = set()
    for path in (ROOT / "tests").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        loaded.update(re.findall(r'"scripts" / "([a-z_]+)\.py"', source))
        loaded.update(re.findall(r"^(?:from|import) scripts\.([a-z_]+)", source, re.M))
    assert loaded, "жоден тест не вантажить скриптів -- перевір шаблони"
    missing = sorted(name for name in loaded if f"scripts/{name}.py" not in PUBLIC_SCRIPTS)
    assert not missing, f"тести вантажать скрипти, яких немає в PUBLIC_SCRIPTS: {missing}"


def test_the_public_env_example_keeps_every_key_and_no_notes():
    before = (ROOT / ".env.example").read_text(encoding="utf-8")

    after, _removed = strip_line_comments(before)

    assert not [line for line in after.splitlines() if line.strip().startswith("#")]
    assert env_pairs(after) == env_pairs(before)
    verify_env(before, after)


def test_a_changed_value_in_the_env_example_is_caught():
    with pytest.raises(Broken):
        verify_env("A=1\nB=\n", "A=1\nB=x\n")

