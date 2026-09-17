"""Публічне дерево: те, що їде на GitHub, — не дерево HEAD.

    uv run python scripts/public_tree.py --out ../komora-public   # подивитись
    uv run python scripts/public_tree.py --out ... --no-graph     # швидко, без схеми
    uv run python scripts/public_tree.py --out ... --write-tree   # ще й записати в git

Три перетворення, і кожне має причину, яку видно з наслідку:

* **Коментарі і докстрінги знято** скрізь (рішення власника 12.09: журнал
  рішень живе вдома). `types.ts` через це перегенеровується НА ДЕРЕВІ, бо
  JSDoc у ньому будується з докстрінгів схем, а публічний CI звіряє файл з
  генератором на публічному коді.
* **Скрипти назовні -- лише за переліком** (`PUBLIC_SCRIPTS`): ворота CI,
  генератори, публікація, знімки чисел. Заміри лишаються вдома разом з
  `docs/`, які вони наповнюють.
* **`docs/` лишається вдома.** Там живі виклики чужого API, внутрішні заміри
  і хронологія роботи. Виняток — `licenses.md` (п. 8.6 умов хакатону) та
  `mutation.json`, `mutation_kinds.json` і `passk.json` (з них CI будує числа
  сторінки «Якість»).
* **Схема репозиторію їде свіжою.** `graphify` будується НА ЦЬОМУ ж дереві,
  а не на локальному, тож описує рівно те, що опубліковано: карта, у якій
  половина вузлів веде в неопубліковані файли, гірша за її відсутність.

Правило, на якому все тримається: **перетворення мусить бути доведеним, а не
правдоподібним.** Мовчки зламаний публічний код виглядає точно так само, як
робочий, і знайдеться він не в нас. Тому доказ на кожну мову свій:

* Python — рівність AST (`ast.dump`) до і після;
* TypeScript, Svelte, CSS — `scripts/strip_web.mjs`: друк AST, компіляція
  компонента і мініфікація стилів обабіч;
* YAML, TOML, JSONC — рівність РОЗІБРАНИХ даних;
* SQL — рівність КАНОНІЧНОГО вигляду (`komora.db.canonical`), тобто рівно
  того, з чого `komora-migrate` рахує контрольну суму міграції;
* решта (`.sql`, `.sh`, `.service`, `.conf`, хук) — зрізаються тільки рядки,
  які ЦІЛКОМ коментар, тож жодного рядка з даними не торкаємось у принципі.
  Місця, де такий рядок БУВАЄ даними, названі окремо: heredoc у shell,
  блоковий скаляр у YAML, доларові лапки і багаторядковий літерал у SQL.

Плюс ворота, які інакше спрацювали б уже в публічному CI: ruff, text_lint,
css_tokens, звірка згенерованого, pytest, збірка і типи фронта. Усі вони
ганяються по ПУБЛІЧНОМУ дереву, а не по локальному: перевіряти треба те, що
поїде, а поїде інше.
"""

from __future__ import annotations

import argparse
import ast
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tokenize
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote

import yaml

from komora import runtime
from komora.db.canonical import canonical

runtime.console()

ROOT = Path(__file__).resolve().parents[1]

PUBLIC_DOCS = frozenset(
    {
        "docs/licenses.md",
        "docs/mutation.json",
        "docs/mutation_kinds.json",
        "docs/passk.json",
        "docs/mcp-tools.json",
    }
)

LOCAL_ONLY = frozenset(
    {
        "CLAUDE.md",
        "deploy/nginx-komora-live.klimnyk.dev.conf",
        "video-pitch.md",
    }
)

AS_IS = frozenset(
    {
        "web/src/lib/types.ts",
        "web/src/lib/facts.ts",
        "docs/licenses.md",
        ".env.example",
    }
)

GRAPH_REPORT = "docs/graph-report.md"

GRAPH_HEADER = """# Карта репозиторію

Вузли — модулі, класи і функції, ребра — зв'язки між ними. Схему будує
`graphify` на ЦЬОМУ ж дереві перед кожною публікацією, тож вона описує рівно
те, що тут лежить, а не сусідню версію коду.

Витяг локальний (`--code-only`): без ключа до моделі, без мережі, без
здогадів — звідси «Token cost: 0» нижче. Ціна названа теж: спільноти
лишаються з номерами замість назв (назви дає модель), а `.md`-файли в граф
не потрапляють. Хаби нижче — справжні імена з коду, за ними й орієнтуватись.

Робочі нотатки і повна історія розробки лишаються в приватному репозиторії;
коментарі з коду зняті на публікації — `scripts/public_tree.py`.

"""

CI_WORKFLOW = ".github/workflows/ci.yml"
CI_DROP_STEP = "repo-map актуальний"

README_REWRITES = (
    (
        """## Ліцензія

Проєкт під [Apache-2.0](LICENSE).""",
        """## Документація

- [`docs/graph-report.md`](docs/graph-report.md) — карта репозиторію: спільноти,
  хаби, аудит витягу. Будується заново перед кожною публікацією, тож описує
  рівно це дерево, а не сусіднє
- [`docs/licenses.md`](docs/licenses.md) — перелік ліцензій, збирається з
  реально встановлених пакетів і звіряється в CI

Робочі нотатки (`mcp-facts.md`, `measured.md`, `setup.md`, `deploy.md`,
`history.md`) лишаються в приватному репозиторії: там живі виклики чужого API,
внутрішні заміри і хронологія роботи.

Коментарі і докстрінги з коду зняті механічно на публікації
(`scripts/public_tree.py`); `types.ts` перегенеровано на цьому ж дереві.
Чим доведено, що зняття нічого не зламало, написано в докстрінгу того ж
скрипта.

## Ліцензія

Проєкт під [Apache-2.0](LICENSE).""",
    ),
)

KEEP_PY = re.compile(r"#\s*(noqa|type:|ty:|pragma:|ruff:|isort:|fmt:|mypy:|nosec|pylint:)")

CACHES = frozenset({"__pycache__", ".pytest_cache", ".ruff_cache", ".svelte-check"})
WEB_SUFFIXES = frozenset({".ts", ".js", ".mjs", ".svelte", ".css"})
LINE_COMMENT_SUFFIXES = frozenset({".sh", ".service", ".timer", ".conf", ".toml"})
LINE_COMMENT_NAMES = frozenset({".gitignore", "pre-push"})
SHELL = frozenset({".sh"})
LINK = re.compile(r"\]\((?!https?:|mailto:|#)([^)#]+)")

QUIET = frozenset({".md", ".json", ".lock", ".example", ".png"})
BINARY = frozenset({".png"})
QUIET_NAMES = frozenset({"LICENSE"})

HTML_PROTECTED = re.compile(r"<(script|style|pre|textarea)\b.*?</\1\s*>", re.DOTALL | re.IGNORECASE)
HTML_COMMENT = re.compile(r"[ \t]*<!--.*?-->\n?", re.DOTALL)


def strip_html(source: str) -> tuple[str, int]:
    protected = [(m.start(), m.end()) for m in HTML_PROTECTED.finditer(source)]
    removed = 0

    def cut(match: re.Match[str]) -> str:
        nonlocal removed
        if any(start <= match.start() < end for start, end in protected):
            return match.group()
        removed += 1
        return ""

    return tidy(HTML_COMMENT.sub(cut, source)), removed


class Broken(Exception):
    """Доказ не зійшовся: файл лишається як був, публікація не їде."""


@dataclass
class Report:
    files: int = 0
    dropped: list[str] = field(default_factory=list)
    stripped: int = 0
    comments: int = 0
    graph: str = "не будувалась"
    gates: list[str] = field(default_factory=list)


def is_public(path: str) -> bool:
    if path in LOCAL_ONLY:
        return False
    if path.startswith("docs/"):
        return path in PUBLIC_DOCS
    if path.startswith("scripts/"):
        return path in PUBLIC_SCRIPTS
    return True


def tidy(text: str) -> str:
    return re.sub(r"\n{4,}", "\n\n\n", text).lstrip("\n")


def docstring_lines(source: str, *, keep_module: bool = False) -> tuple[set[int], int]:
    holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    lines = source.splitlines()
    taken: set[int] = set()
    count = 0
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, holders) or not ast.get_docstring(node):
            continue
        if len(node.body) == 1:
            continue
        if keep_module and isinstance(node, ast.Module):
            continue
        doc = node.body[0]
        before = lines[doc.lineno - 1][: doc.col_offset]
        after = lines[doc.end_lineno - 1][doc.end_col_offset :]
        if before.strip() or after.strip():
            continue
        taken.update(range(doc.lineno, doc.end_lineno + 1))
        count += 1
    return taken, count


def _scars(lines: list[str], gone: set[int]) -> set[int]:
    scars: set[int] = set()
    for number in sorted(gone):
        if number - 1 in gone or number - 1 < 1:
            continue
        end = number
        while end + 1 in gone:
            end += 1
        before, after = number - 1, end + 1
        if after > len(lines):
            continue
        if not lines[before - 1].strip() and not lines[after - 1].strip():
            scars.add(after)
    return scars


def strip_python(
    source: str, *, docstrings: bool = False, keep_module: bool = False
) -> tuple[str, int]:
    lines = source.splitlines(keepends=True)
    whole: set[int] = set()
    tails: dict[int, int] = {}
    taken, docs = docstring_lines(source, keep_module=keep_module) if docstrings else (set(), 0)
    for token in tokenize.generate_tokens(io.StringIO(source).readline):
        if token.type != tokenize.COMMENT:
            continue
        row, column = token.start
        if row <= 2 and (token.string.startswith("#!") or "coding" in token.string):
            continue
        if KEEP_PY.match(token.string):
            continue
        if lines[row - 1][:column].strip():
            tails[row] = column
        else:
            whole.add(row)

    gone = whole | taken
    scars = _scars(lines, gone)
    out = []
    for number, line in enumerate(lines, start=1):
        if number in gone or number in scars:
            continue
        if number in tails:
            ending = "\n" if line.endswith("\n") else ""
            line = line[: tails[number]].rstrip() + ending
        out.append(line)
    return tidy("".join(out)), len(whole) + len(tails) + docs


def _undocumented(source: str) -> str:
    holders = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, holders) and ast.get_docstring(node) and len(node.body) > 1:
            node.body = node.body[1:]
    return ast.dump(tree)


def verify_python(before: str, after: str, *, docstrings: bool = False) -> None:
    if docstrings:
        if _undocumented(before) != _undocumented(after):
            raise Broken("AST розійшовся (звірка без докстрінгів)")
        return
    if ast.dump(ast.parse(before)) != ast.dump(ast.parse(after)):
        raise Broken("AST розійшовся")


def _heredocs(line: str) -> str | None:
    match = re.search(r"<<-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?", line)
    return match.group(1) if match else None


def strip_line_comments(source: str, *, shell: bool = False) -> tuple[str, int]:
    out: list[str] = []
    removed = 0
    terminator: str | None = None
    for number, line in enumerate(source.splitlines(keepends=True), start=1):
        stripped = line.strip()
        if terminator is not None:
            out.append(line)
            if stripped == terminator:
                terminator = None
            continue
        if shell and (opened := _heredocs(line)):
            terminator = opened
            out.append(line)
            continue
        if stripped.startswith("#") and not (number == 1 and stripped.startswith("#!")):
            removed += 1
            continue
        out.append(line)
    return tidy("".join(out)), removed


DOLLAR = re.compile(r"\$[A-Za-z_]*\$")


def strip_sql(source: str) -> tuple[str, int]:
    out: list[str] = []
    removed = 0
    tag: str | None = None
    quoted = False
    for line in source.splitlines(keepends=True):
        if tag is None and not quoted and line.strip().startswith("--"):
            removed += 1
            continue
        for match in DOLLAR.finditer(line):
            if tag is None:
                tag = match.group()
            elif tag == match.group():
                tag = None
        if tag is None and line.count("'") % 2:
            quoted = not quoted
        out.append(line)
    return tidy("".join(out)), removed


def strip_jsonc(source: str) -> tuple[str, int]:
    out: list[str] = []
    removed = 0
    for line in source.splitlines(keepends=True):
        if line.lstrip().startswith("//"):
            removed += 1
            continue
        out.append(line)
    return tidy("".join(out)), removed


def _yaml_block_indent(line: str) -> int | None:
    if re.search(r":\s*[|>][+-]?\d*\s*$", line.rstrip()):
        return len(line) - len(line.lstrip())
    return None


def strip_yaml(source: str) -> tuple[str, int]:
    out: list[str] = []
    removed = 0
    block: int | None = None
    for line in source.splitlines(keepends=True):
        indent = len(line) - len(line.lstrip())
        if block is not None:
            if line.strip() and indent <= block:
                block = None
            else:
                out.append(line)
                continue
        if line.strip().startswith("#"):
            removed += 1
            continue
        block = _yaml_block_indent(line)
        out.append(line)
    return tidy("".join(out)), removed


def verify_yaml(before: str, after: str) -> None:
    if list(yaml.safe_load_all(before)) != list(yaml.safe_load_all(after)):
        raise Broken("розібраний YAML розійшовся")


def verify_toml(before: str, after: str) -> None:
    if tomllib.loads(before) != tomllib.loads(after):
        raise Broken("розібраний TOML розійшовся")


def verify_json(before: str, after: str) -> None:
    json.loads(after)


def verify_sql(before: str, after: str) -> None:
    if canonical(before) != canonical(after):
        raise Broken("канонічний SQL розійшовся")


def drop_ci_step(text: str, name: str) -> str:
    lines = text.splitlines(keepends=True)
    start = next((i for i, line in enumerate(lines) if line.strip() == f"- name: {name}"), None)
    if start is None:
        raise Broken(f"крок «{name}» не знайдено — CI змінився, звір {CI_WORKFLOW}")
    indent = _indent(lines[start])
    end = start + 1
    while end < len(lines) and not (lines[end].strip() and _indent(lines[end]) <= indent):
        end += 1
    return "".join(lines[:start] + lines[end:])


def _indent(line: str) -> int:
    body = line.rstrip("\n")
    return len(body) - len(body.lstrip())


def broken_links(tree: Path) -> list[str]:
    broken = []
    for path in sorted(tree.rglob("*.md")):
        for target in LINK.findall(path.read_text(encoding="utf-8")):
            if not (path.parent / target.strip()).exists():
                broken.append(f"{path.relative_to(tree).as_posix()} → {target.strip()}")
    return broken


def export_head(dest: Path) -> None:
    archive = subprocess.run(
        ["git", "archive", "--format=tar", "HEAD"], cwd=ROOT, stdout=subprocess.PIPE, check=True
    )
    with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
        tar.extractall(dest, filter="data")


MUTE_DOCSTRINGS = ("src/komora/", "tests/", "scripts/")

PUBLIC_SCRIPTS = frozenset(
    {
        "scripts/aws_budget.py",
        "scripts/check.py",
        "scripts/check_receipt_store.py",
        "scripts/compare_models.py",
        "scripts/css_tokens.py",
        "scripts/dead_buttons.py",
        "scripts/e2e_port.py",
        "scripts/first_basket.py",
        "scripts/gen_facts.py",
        "scripts/gen_licenses.py",
        "scripts/gen_repo_map.py",
        "scripts/gen_types.py",
        "scripts/mcp_login.py",
        "scripts/mcp_tools_snapshot.py",
        "scripts/mcp_verdicts.py",
        "scripts/mutation_kinds.py",
        "scripts/mutation_snapshot.py",
        "scripts/passk_snapshot.py",
        "scripts/protect_branches.py",
        "scripts/public_tree.py",
        "scripts/publish.py",
        "scripts/strip_web.mjs",
        "scripts/text_lint.py",
    }
)

KEEP_MODULE_DOCSTRING = frozenset({"scripts/public_tree.py"})


def mute_docstrings(path: str) -> bool:
    return path.startswith(MUTE_DOCSTRINGS)


def strip_tree(tree: Path, report: Report) -> None:
    verifiers = {
        ".yml": verify_yaml,
        ".yaml": verify_yaml,
        ".toml": verify_toml,
        ".jsonc": verify_json,
        ".sql": verify_sql,
    }
    web: list[dict[str, str]] = []
    for path in sorted(tree.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(tree).as_posix()
        if relative in AS_IS or path.suffix in BINARY:
            continue
        if path.suffix in WEB_SUFFIXES:
            web.append({"path": str(path), "rel": relative})
            continue

        before = path.read_text(encoding="utf-8")
        docstrings = mute_docstrings(relative)
        keep_module = relative in KEEP_MODULE_DOCSTRING
        if path.suffix == ".py":
            after, count = strip_python(before, docstrings=docstrings, keep_module=keep_module)
        elif path.suffix in (".yml", ".yaml"):
            after, count = strip_yaml(before)
        elif path.suffix == ".html":
            after, count = strip_html(before)
        elif path.suffix == ".sql":
            after, count = strip_sql(before)
        elif path.suffix == ".jsonc":
            after, count = strip_jsonc(before)
        elif path.suffix in LINE_COMMENT_SUFFIXES or path.name in LINE_COMMENT_NAMES:
            shell = path.suffix in SHELL or path.name == "pre-push"
            after, count = strip_line_comments(before, shell=shell)
        else:
            continue
        if not count:
            continue
        try:
            if path.suffix == ".py":
                verify_python(before, after, docstrings=docstrings)
            elif verify := verifiers.get(path.suffix):
                verify(before, after)
        except Broken as error:
            raise Broken(f"{relative}: {error}") from error
        path.write_text(after, encoding="utf-8", newline="")
        report.stripped += 1
        report.comments += count

    if web:
        strip_web(web, report)


def strip_web(files: list[dict[str, str]], report: Report) -> None:
    done = subprocess.run(
        ["node", str(ROOT / "scripts" / "strip_web.mjs")],
        input=json.dumps({"files": files}),
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=ROOT,
    )
    if not done.stdout:
        raise Broken(f"strip_web.mjs не відповів: {done.stderr.strip()[:400]}")
    answer = json.loads(done.stdout)
    if answer["errors"]:
        raise Broken("\n".join(answer["errors"]))
    report.stripped += answer["changed"]
    report.comments += answer["removed"]


FACT_MARKS = ("__TESTS__", "__MUTATION__", "__PASSK__")


def fact_badges(tree: Path) -> dict[str, str]:
    facts = (tree / "web/src/lib/facts.ts").read_text(encoding="utf-8")
    tests = re.search(r"TEST_COUNT = (\d+)", facts)
    passk = re.search(r"PASSK_BY_MODEL = '([^']*)'", facts)
    mutation = json.loads((tree / "docs/mutation.json").read_text(encoding="utf-8"))
    if not tests or not passk:
        raise Broken("facts.ts без TEST_COUNT або PASSK_BY_MODEL -- бейджам нема з чого рахуватись")
    scores = re.findall(r"(\d+)/(\d+)", passk.group(1))
    passk_text = ", ".join(f"{a}/{b}" for a, b in scores) or "немає"
    return {
        "__TESTS__": tests.group(1),
        "__MUTATION__": f"{mutation['score']}%25",
        "__PASSK__": quote(passk_text, safe=""),
    }


def rewrite(tree: Path) -> None:
    readme = tree / "README.md"
    text = readme.read_text(encoding="utf-8")
    for old, new in README_REWRITES:
        if old not in text:
            raise Broken(f"README змінився — правило заміни не спрацювало:\n{old[:80]}")
        text = text.replace(old, new)
    for mark, value in fact_badges(tree).items():
        if mark not in text:
            raise Broken(f"README без заглушки {mark}: бейдж лишився б без числа")
        text = text.replace(mark, value)
    readme.write_text(text, encoding="utf-8", newline="")

    workflow = tree / CI_WORKFLOW
    before = workflow.read_text(encoding="utf-8")
    after = drop_ci_step(before, CI_DROP_STEP)
    verify_step_gone(before, after)
    workflow.write_text(after, encoding="utf-8", newline="")


def _step_names(workflow: str) -> list[str]:
    document = yaml.safe_load(workflow)
    return [step.get("name") for job in document["jobs"].values() for step in job.get("steps", [])]


def verify_step_gone(before: str, after: str) -> None:
    gone = [name for name in _step_names(before) if name not in _step_names(after)]
    if gone != [CI_DROP_STEP]:
        raise Broken(f"з CI зникло не те: {gone}")


def build_graph(tree: Path, report: Report) -> None:
    for step in (["graphify", ".", "--no-viz", "--code-only"], ["graphify", "cluster-only", "."]):
        done = subprocess.run(
            step, cwd=tree, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
        if done.returncode != 0:
            raise Broken(f"{' '.join(step)}: {(done.stdout + done.stderr)[-600:]}")

    out = tree / "graphify-out"
    made = out / "GRAPH_REPORT.md"
    if not made.exists():
        raise Broken("graphify відпрацював, але звіту не лишив")
    text = made.read_text(encoding="utf-8")
    (tree / GRAPH_REPORT).write_text(GRAPH_HEADER + _retitle(text), encoding="utf-8", newline="")
    size = (tree / GRAPH_REPORT).stat().st_size // 1024
    shutil.rmtree(out)
    report.graph = f"{GRAPH_REPORT}, {size} КБ"


def _retitle(report: str) -> str:
    first, _, rest = report.partition("\n")
    date = first[first.rfind("(") + 1 : first.rfind(")")] if "(" in first else ""
    return f"## Що порахувалось{f' ({date})' if date else ''}\n{rest}"


def gates(tree: Path, report: Report, *, tests: bool, graph: bool) -> None:
    checks: list[tuple[str, list[str]]] = [
        ("ruff", [sys.executable, "-m", "ruff", "check", "."]),
        ("text_lint", [sys.executable, str(tree / "scripts" / "text_lint.py")]),
        ("css_tokens", [sys.executable, str(tree / "scripts" / "css_tokens.py")]),
        ("types.ts", [sys.executable, str(tree / "scripts" / "gen_types.py"), "--check"]),
        ("facts.ts", [sys.executable, str(tree / "scripts" / "gen_facts.py"), "--check"]),
        ("ліцензії", [sys.executable, str(tree / "scripts" / "gen_licenses.py"), "--check"]),
    ]
    env = dict(os.environ, PYTHONPATH=str(tree / "src"))
    for generator in ("gen_types.py", "gen_facts.py"):
        regenerate = subprocess.run(
            [sys.executable, str(tree / "scripts" / generator)],
            cwd=tree,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if regenerate.returncode != 0:
            tail = (regenerate.stdout + regenerate.stderr)[-800:]
            raise Broken(f"{generator} на публічному дереві не спрацював: {tail}")
    if tests:
        where = subprocess.run(
            [sys.executable, "-c", "import komora, sys; sys.stdout.write(komora.__file__)"],
            cwd=tree,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if not where.stdout.startswith(str(tree)):
            source = where.stdout or where.stderr
            raise Broken(f"pytest узяв би не публічний код: komora з {source}")
        checks.append(("pytest", [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"]))

    for label, command in checks:
        done = subprocess.run(
            command,
            cwd=tree,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if done.returncode != 0:
            raise Broken(f"{label} на публічному дереві: {(done.stdout + done.stderr)[-1500:]}")
        report.gates.append(label)

    web_gates(tree, report)

    broken = broken_links(tree)
    if not graph:
        broken = [link for link in broken if not link.endswith(GRAPH_REPORT)]
    if broken:
        raise Broken("посилання в нікуди: " + ", ".join(broken))
    report.gates.append("посилання" if graph else "посилання (крім схеми)")


def web_gates(tree: Path, report: Report) -> None:
    source = ROOT / "web" / "node_modules"
    npm = shutil.which("npm")
    if not source.is_dir() or not npm:
        report.gates.append("фронт (пропущено: немає node_modules)")
        return

    link = tree / "web" / "node_modules"
    if sys.platform == "win32":
        subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(source)], capture_output=True)
    else:
        os.symlink(source, link, target_is_directory=True)
    if not link.is_dir():
        raise Broken(f"посилання на node_modules не постало: {link}")

    try:
        for label, script in (("збірка фронта", "build"), ("типи фронта", "check")):
            done = subprocess.run(
                [npm, "run", script],
                cwd=tree / "web",
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if done.returncode != 0:
                raise Broken(f"{label}: {(done.stdout + done.stderr)[-1500:]}")
            report.gates.append(label)
    finally:
        os.rmdir(link) if sys.platform == "win32" else link.unlink()
        shutil.rmtree(tree / "web" / "dist", ignore_errors=True)


def sweep(tree: Path) -> int:
    swept = 0
    for path in sorted(tree.rglob("*"), reverse=True):
        if path.name in CACHES and path.is_dir():
            shutil.rmtree(path)
            swept += 1
        elif path.name == ".coverage" and path.is_file():
            path.unlink()
            swept += 1
    return swept


def _git(*args: str, cwd: Path = ROOT, env: dict[str, str] | None = None) -> str:
    done = subprocess.run(
        ["git", "-c", "core.quotepath=false", *args],
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    if done.returncode != 0:
        raise Broken(f"git {' '.join(args)}: {done.stderr.strip()}")
    return done.stdout.strip()


def _executables(tree: Path, env: dict[str, str]) -> list[str]:
    wanted = [
        line.split("	", 1)[1]
        for line in _git("ls-tree", "-r", "HEAD").splitlines()
        if line.startswith("100755")
    ]
    present = [path for path in wanted if (tree / path).exists()]
    if present:
        _git("update-index", "--chmod=+x", "--", *present, cwd=tree, env=env)
    modes = {
        line.split("	", 1)[1]: line.split()[0]
        for line in _git("ls-files", "-s", cwd=tree, env=env).splitlines()
    }
    if wrong := [path for path in present if modes.get(path) != "100755"]:
        raise Broken(f"виконуваний біт не переставився: {wrong}")
    return present


def write_tree(tree: Path) -> tuple[str, int]:
    with tempfile.TemporaryDirectory(prefix="komora-index-") as folder:
        env = dict(
            os.environ,
            GIT_INDEX_FILE=str(Path(folder) / "index"),
            GIT_DIR=str(ROOT / ".git"),
            GIT_WORK_TREE=str(tree),
        )
        _git("add", "-A", ".", cwd=tree, env=env)
        executables = _executables(tree, env)
        listed = sorted(_git("ls-files", cwd=tree, env=env).splitlines())
        on_disk = sorted(
            path.relative_to(tree).as_posix() for path in tree.rglob("*") if path.is_file()
        )
        if listed != on_disk:
            lost = sorted(set(on_disk) - set(listed))
            raise Broken(f"в індекс не потрапило {len(lost)} файлів: {lost[:5]}")
        return _git("write-tree", cwd=tree, env=env), len(executables)


def build(dest: Path, *, graph: bool = True, tests: bool = False, strip: bool = True) -> Report:
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    report = Report()
    export_head(dest)
    for path in sorted(dest.rglob("*")):
        if path.is_file() and not is_public(path.relative_to(dest).as_posix()):
            report.dropped.append(path.relative_to(dest).as_posix())
            path.unlink()
    for folder in sorted(dest.rglob("*"), reverse=True):
        if folder.is_dir() and not any(folder.iterdir()):
            folder.rmdir()

    report.files = sum(1 for path in dest.rglob("*") if path.is_file())
    if strip:
        strip_tree(dest, report)
    rewrite(dest)
    if graph:
        build_graph(dest, report)
    gates(dest, report, tests=tests, graph=graph)
    sweep(dest)
    return report


def describe(report: Report) -> str:
    took = (
        f"  коментарів знято: {report.comments} у {report.stripped} файлах\n"
        if report.stripped or report.comments
        else "  коментарі НЕ знімались (репозиторій ще приватний)\n"
    )
    return (
        f"файлів: {report.files} (лишились удома: {len(report.dropped)})\n"
        f"{took}"
        f"  схема: {report.graph}\n"
        f"  ворота: {', '.join(report.gates)}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Зібрати публічне дерево і перевірити його")
    parser.add_argument("--out", required=True, type=Path, help="куди покласти дерево")
    parser.add_argument("--no-graph", action="store_true", help="без схеми graphify")
    parser.add_argument("--tests", action="store_true", help="ще й прогнати pytest по дереву")
    parser.add_argument(
        "--keep-comments",
        action="store_true",
        help="не знімати коментарі (репозиторій ще приватний)",
    )
    parser.add_argument(
        "--write-tree", action="store_true", help="ще й записати дерево в git і назвати sha"
    )
    args = parser.parse_args()

    try:
        report = build(
            args.out.resolve(),
            graph=not args.no_graph,
            tests=args.tests,
            strip=not args.keep_comments,
        )
    except Broken as error:
        print(f"Публічне дерево не зібралось:\n{error}", file=sys.stderr)
        return 1
    print(f"Публічне дерево: {args.out}")
    print(describe(report))
    if args.write_tree:
        try:
            tree, executables = write_tree(args.out.resolve())
        except Broken as error:
            print(f"Дерево не записалось у git: {error}", file=sys.stderr)
            return 1
        print(f"  git tree: {tree} (виконуваних: {executables})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
