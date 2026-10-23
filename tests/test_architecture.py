from __future__ import annotations

import ast
import pathlib
import re
from pathlib import Path

import pytest

from komora.agent import basket

CORE = Path(__file__).resolve().parents[1] / "src" / "komora" / "core"

FORBIDDEN_MODULES = {
    "komora.mcp",
    "komora.agent",
    "komora.api",
    "komora.db",
    "komora.jobs",
    "komora.ingest",
    "psycopg",
    "psycopg_pool",
    "httpx",
    "httpx2",
    "anthropic",
    "fastapi",
    "boto3",
}

FORBIDDEN_CALLS = {
    "datetime.now",
    "datetime.today",
    "date.today",
    "time.time",
    "random.random",
    "random.choice",
}


def core_modules() -> list[Path]:
    return sorted(CORE.glob("*.py"))


def test_core_has_modules_to_check():
    assert core_modules(), "не знайдено модулів core/ — перевір шлях"


@pytest.mark.parametrize("path", core_modules(), ids=lambda p: p.name)
def test_core_imports_nothing_with_side_effects(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))

    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    for module in imported:
        blocked = any(
            module == banned or module.startswith(banned + ".") for banned in FORBIDDEN_MODULES
        )
        assert not blocked, f"{path.name} імпортує {module}"

        if module == "komora" or module.startswith("komora."):
            assert module == "komora.core" or module.startswith("komora.core."), (
                f"{path.name} імпортує {module} — core/ імпортує лише komora.core"
            )


@pytest.mark.parametrize("path", core_modules(), ids=lambda p: p.name)
def test_core_does_not_read_the_clock(path: Path):
    tree = ast.parse(path.read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        target = ast.unparse(node.func)
        assert target not in FORBIDDEN_CALLS, (
            f"{path.name} викликає {target}() — передавай значення параметром"
        )


ROOT = Path(__file__).resolve().parents[1]

MCP_CLIENT = ROOT / "src" / "komora" / "mcp" / "client.py"
MCP_LOGIN = ROOT / "scripts" / "mcp_login.py"


def python_sources() -> list[Path]:
    files = [*(ROOT / "src").rglob("*.py"), *(ROOT / "scripts").rglob("*.py")]
    return sorted(path for path in files if "__pycache__" not in path.parts)


def test_client_session_exists_only_in_mcp_client():
    offenders = []
    for path in python_sources():
        if path in (MCP_CLIENT, MCP_LOGIN):
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                names = {alias.name for alias in node.names}
                if "ClientSession" in names and node.module.startswith("mcp"):
                    offenders.append(path)
            elif isinstance(node, ast.Import):
                if any(alias.name.startswith("mcp") for alias in node.names):
                    offenders.append(path)
    assert not offenders, (
        f"{[str(p.relative_to(ROOT)) for p in offenders]} відкривають власну MCP-сесію. "
        "Єдиний шлях — komora/mcp/client.py: інакше блок записів і редакція обходяться."
    )


DEPLOY_SCRIPT = ROOT / "deploy" / "deploy-fedora.sh"


def _deploy_array(name: str) -> set[str]:
    body = DEPLOY_SCRIPT.read_text(encoding="utf-8")
    inside = body.partition(f"{name}=(")[2].partition(")")[0]
    assert inside.strip(), f"у скрипті немає масиву {name}"
    return {word for line in inside.splitlines() for word in line.split("#", 1)[0].split()}


def _deploy_units(suffix: str) -> set[str]:
    return {path.name for path in (ROOT / "deploy").glob(f"komora-*{suffix}")}


SYSTEM_ONLY_KEYS = ("User=", "Group=", "DynamicUser=", "WantedBy=multi-user.target")

UNIT_SECTION_KEYS = ("StartLimitBurst=", "StartLimitIntervalSec=")


def _unit_section(unit: pathlib.Path, section: str) -> list[str]:
    out: list[str] = []
    here = False
    for raw in unit.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line.startswith("#") or not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            here = line == section
            continue
        if here:
            out.append(line)
    return out


def _unit_files() -> list[pathlib.Path]:
    return sorted((ROOT / "deploy").glob("komora-*.service")) + sorted(
        (ROOT / "deploy").glob("komora-*.timer")
    )


def test_no_unit_of_ours_carries_a_key_that_needs_root():
    for unit in _unit_files():
        lines = [
            line
            for section in ("[Unit]", "[Service]", "[Timer]", "[Install]")
            for line in _unit_section(unit, section)
        ]
        for key in SYSTEM_ONLY_KEYS:
            bad = [line for line in lines if line.startswith(key)]
            assert not bad, f"{unit.name}: {bad} працює лише в системному юніті"


def test_restart_limits_stand_where_systemd_reads_them():
    for unit in _unit_files():
        service = _unit_section(unit, "[Service]")
        for key in UNIT_SECTION_KEYS:
            bad = [line for line in service if line.startswith(key)]
            assert not bad, f"{unit.name}: {bad} стоїть у [Service], а читається з [Unit]"


def test_every_unit_of_ours_says_when_it_falls():
    for unit in _unit_files():
        if unit.name.endswith("@.service"):
            continue
        if unit.name.endswith(".timer"):
            continue
        hooks = [line for line in _unit_section(unit, "[Unit]") if line.startswith("OnFailure=")]
        assert hooks == ["OnFailure=komora-notify@%n.service"], (
            f"{unit.name}: падіння нікому не сказати ({hooks})"
        )


def test_mcp_login_never_calls_tools():
    tree = ast.parse(MCP_LOGIN.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            target = ast.unparse(node.func)
            assert not target.endswith("call_tool"), (
                "scripts/mcp_login.py викликає call_tool — це другий шлях до MCP "
                "повз блок записів. Логін відкриває сесію, але tools не чіпає."
            )


RUNTIME = ROOT / "src" / "komora" / "runtime.py"


def test_no_entry_point_creates_its_own_loop():
    offenders = []
    for path in python_sources():
        if path == RUNTIME:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and ast.unparse(node.func) == "asyncio.run":
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not offenders, (
        f"{offenders} кличуть asyncio.run повз komora/runtime.py. "
        "На Windows це Proactor-петля, на якій psycopg в async-режимі не працює: "
        "вхід зламається аж на машині розробника. Правильно — runtime.run()."
    )


def test_no_entry_point_fixes_the_console_on_its_own():
    offenders = []
    for path in python_sources():
        if path == RUNTIME:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and ast.unparse(node.func).endswith(".reconfigure"):
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not offenders, (
        f"{offenders} переставляють кодовку потоку самі. Єдине місце — "
        "komora/runtime.py: інакше наступний вхід копії не зробить і впаде на «→»."
    )


POOL_OWNERS = {
    ROOT / "src" / "komora" / "db" / "pool.py",
    ROOT / "src" / "komora" / "api" / "app.py",
}


def test_pool_is_opened_by_the_process_owner_only():
    offenders = []
    for path in python_sources():
        if path in POOL_OWNERS or path.parent.name == "jobs" or path.parent.name == "scripts":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and ast.unparse(node.func).endswith("pool_lifespan"):
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not offenders, (
        f"{offenders} відкривають pool_lifespan посеред живого процесу. Він у "
        "finally ЗАКРИВАЄ пул і гасить синглтон — тобто забирає базу в усіх, "
        "хто працює поруч. Споживачеві потрібен get_pool()."
    )


QUOTA = ROOT / "src" / "komora" / "api" / "quota.py"


def test_the_run_ceiling_is_taken_whole_not_as_a_pair_of_calls():
    offenders = []
    for path in python_sources():
        if path == QUOTA:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and ast.unparse(node.func).endswith("quota.guard"):
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
            if isinstance(node, ast.ImportFrom) and node.module == "komora.api.quota":
                offenders += [
                    f"{path.relative_to(ROOT)}:{node.lineno}"
                    for alias in node.names
                    if alias.name == "guard"
                ]
    assert not offenders, (
        f"{offenders} кличуть ворота стелі окремо від `quota.counted`. Між "
        "воротами і записом лежить уся збірка, і всі ці секунди місце в черзі "
        "не тримає ніхто — паралельні запити проходять на старих числах."
    )


ETERNAL_CACHES = ("intent_names", "intent_keeps", "intent_sense", "intent_aisles")


def test_every_step_that_knows_about_cold_hands_the_flag_to_all_its_caches():
    steps = sorted((ROOT / "src" / "komora" / "agent" / "steps").rglob("*.py"))
    assert steps, "кроків не знайдено -- ворота міряли б порожнечу"
    offenders = []
    for path in steps:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not ast.unparse(node.func).endswith(ETERNAL_CACHES):
                continue
            asked = node.args[0] if node.args else None
            if isinstance(asked, ast.Constant) and asked.value is None:
                continue
            if not any(kw.arg == "use_cache" for kw in node.keywords):
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not offenders, (
        f"{offenders} питають вічний кеш моделлю без `use_cache=`. Холодний "
        "прогін там мовчки лишиться теплим, а перемикач керуватиме не тим, "
        "про що каже."
    )


def test_every_caller_of_agent_picks_hands_it_the_kind_map():
    offenders = []
    for path in python_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not ast.unparse(node.func).endswith("agent_picks"):
                continue
            if not any(kw.arg == "kinds" for kw in node.keywords):
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not offenders, (
        f"{offenders} кличуть `agent_picks` без `kinds=`. Ярус вузла там мовчки "
        "не спрацює, а кошик буде інакший, ніж на сусідньому шляху."
    )


def test_every_path_into_the_model_gets_the_skills_of_this_run():
    watched = ("agent_picks", "resolve_one")
    offenders = []
    for path in python_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = ast.unparse(node.func)
            if not any(called.endswith(name) for name in watched):
                continue
            if not any(kw.arg == "skills" for kw in node.keywords):
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} {called}")
    assert not offenders, (
        f"{offenders} ходять у модель без `skills=`. Інструкція за тригером там "
        "мовчки не спрацює, і кошик з одного прогону буде зібраний двома різними правилами."
    )


def test_every_caller_of_build_chain_hands_it_the_usual_pack():
    offenders = []
    for path in python_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not ast.unparse(node.func).endswith("build_chain"):
                continue
            if not any(kw.arg == "usual_pack" for kw in node.keywords):
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not offenders, (
        f"{offenders} кличуть `build_chain` без `usual_pack=`. Стеля фасовки "
        "там мовчки не спрацює, і збирачу поїде інша обіцянка, ніж із сусіднього входу."
    )


def test_every_caller_hands_over_the_guests_own_articles():
    offenders = []
    for path in python_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = ast.unparse(node.func)
            if not (name.endswith("build_lines") or name.endswith("agent_picks")):
                continue
            if not any(kw.arg == "owned" for kw in node.keywords):
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} ({name})")
    assert not offenders, (
        f"{offenders} обирають товар без `owned=`. Артикул, який гість БЕРЕ, "
        "там мовчки не важитиме нічого, і рядок поїде головою чужої видачі."
    )


def test_every_reader_of_the_history_hands_over_the_catalogue_pool():
    offenders = []
    for path in python_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = ast.unparse(node.func)
            if not (name.endswith("load_history") or name.endswith("read_receipts")):
                continue
            if not any(kw.arg == "pool" for kw in node.keywords):
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} ({name})")
    assert not offenders, (
        f"{offenders} читають історію без `pool=`. Онлайн-покупки приїдуть без "
        "артикула, і кошик візьме голову чужої видачі замість звичного гостя."
    )


def test_every_builder_of_the_mandate_asks_about_the_shelf_life():
    builders = ("build_comment", "price_fork_comment", "mandate_for_decision")
    offenders = []
    for path in python_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = ast.unparse(node.func)
            if not any(name.endswith(builder) for builder in builders):
                continue
            if not any(kw.arg == "shelf_life" for kw in node.keywords):
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} ({name})")
    assert not offenders, (
        f"{offenders} складають мандат без `shelf_life=`. Вимога до терміну "
        "зникне з поля `comment`, а на екрані рядок лишиться погодженим."
    )


def test_every_reader_of_the_history_inside_the_product_names_the_account():
    offenders = []
    for path in python_sources():
        if "src" not in path.parts or "komora" not in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = ast.unparse(node.func)
            if not (name.endswith("load_history") or name.endswith("read_receipts")):
                continue
            if not any(kw.arg == "account" for kw in node.keywords):
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} ({name})")
    assert not offenders, (
        f"{offenders} читають історію без `account=`. Сховище чеків там мовчки "
        "вимкнене: те саме, тільки повільно і щоразу заново."
    )


def test_no_second_home_for_the_off_day_budget_rule():
    offenders = []
    for path in python_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef):
                continue
            body = ast.unparse(node)
            if "OFF_DAY_BUDGET" in body and node.name != "spent":
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} ({node.name})")
    assert not offenders, (
        f"{offenders} виражають правило `OFF_DAY_BUDGET` окремою функцією. "
        "Набір читає SQL у `db/spend.py`; другий вираз того самого рішення "
        "розійдеться з ним мовчки."
    )


def test_the_front_filter_never_lets_through_what_the_back_would_stop():
    front = ROOT / "web" / "src" / "lib" / "list.ts"
    source = front.read_text(encoding="utf-8")
    block = source[source.index("const CONNECTORS") : source.index("const NUMERALS")]
    words = {match.group(1) for match in re.finditer(r"'([^']+)'", block)}
    assert words, "перелік стоп-слів фронта не прочитався — ворота стали б порожніми"

    missing = sorted(words - basket.STOP_WORDS)
    assert not missing, (
        "фронт вважає ці слова службовими, а бекенд — ні: "
        f"{', '.join(missing)} (додай їх у agent/basket.STOP_WORDS)"
    )


def _pantry_empty_note_body() -> str:
    source = (ROOT / "web" / "src" / "lib" / "ui.ts").read_text(encoding="utf-8")
    start = source.index("export function pantryEmptyNote")
    end = source.index("\nexport ", start + 1)
    return source[start:end]


def test_the_empty_pantry_note_cannot_blame_receipts_in_the_mode_that_ignores_them():
    body = _pantry_empty_note_body()
    assert "trackedFrom" in body, (
        "речення про поріг не знайшлось у `pantryEmptyNote` — ворота стали б порожніми"
    )
    guard = body.find("'manual'")
    assert guard != -1, (
        "`pantryEmptyNote` не питає про режим: у режимі «веду сам» він скаже "
        "гостю про пороги його чеків, яких у цьому шляху ніхто не рахував (#363)"
    )
    threshold = body.index("trackedFrom")
    assert guard < threshold and "return" in body[guard:threshold], (
        "розвилка за режимом стоїть ПІСЛЯ речення про поріг або нічого не "
        "повертає — тобто режим «веду сам» усе одно доходить до тексту про чеки"
    )


def test_the_empty_pantry_note_has_a_single_home():
    screens = sorted((ROOT / "web" / "src" / "lib" / "screens").glob("*.svelte"))
    assert screens, "екранів не знайшлось — ворота стали б порожніми"
    offenders = [
        f"{path.name} ({match.group(1)})"
        for path in screens
        for match in re.finditer(r"function (\w*EmptyNote)\b", path.read_text(encoding="utf-8"))
    ]
    assert not offenders, (
        f"{offenders} тримають власну копію правила про порожню комору. "
        "Дім у нього один — `web/src/lib/ui.ts`, інакше наступний екран "
        "успадкує текст, який до нього не доїхав (#363)"
    )


PATIENT_DB = {
    "catalog.save": "обхід каталогу: урваний запис лишає півкарти",
    "catalog.sweep": "той самий обхід, друга половина -- позначити зникле",
    "categories.load": "дерево категорій читає лише крон (`jobs/categories.py`)",
    "categories.save": "той самий крон, запис",
}


def test_every_guest_path_query_has_a_ceiling():
    naked: list[str] = []
    for path in sorted((ROOT / "src" / "komora" / "db").glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for inner in ast.walk(node):
                if not isinstance(inner, ast.Call):
                    continue
                func = inner.func
                if not (isinstance(func, ast.Attribute) and func.attr == "connection"):
                    continue
                if any(word.arg == "timeout" for word in inner.keywords):
                    continue
                where = f"{path.stem}.{node.name}"
                if where not in PATIENT_DB:
                    naked.append(where)

    assert not naked, (
        "похід у базу без стелі на шляху гостя: "
        + ", ".join(sorted(set(naked)))
        + " — додай `timeout=DB_TIMEOUT` або назви причину в PATIENT_DB"
    )


OWN_SLOT_QUERY = {"measure_delivery"}


def test_no_measuring_script_builds_the_slot_window_by_hand():
    by_hand = [
        path.stem
        for path in sorted((ROOT / "scripts").glob("*.py"))
        if '"deliveryTypes"' in path.read_text(encoding="utf-8") and path.stem not in OWN_SLOT_QUERY
    ]

    assert not by_hand, (
        "скрипт будує вікно слотів руками: "
        + ", ".join(by_hand)
        + " — клич `agent.basket.slots_query(...)`, інакше замір стоїть на "
        "вікні, яке вже минуло"
    )


TOOLS_THAT_CUT_SILENTLY = {
    "silpo_list_branches": "50 рядків з 455",
}

OWN_FOREIGN_DEFAULT = {"measure_branches"}


def _tool_of(node: ast.Call) -> str | None:
    if not node.args:
        return None
    first = node.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value if first.value in TOOLS_THAT_CUT_SILENTLY else None
    name = ast.unparse(first)
    return "silpo_list_branches" if name.endswith("BRANCHES_TOOL") else None


def test_no_call_takes_a_foreign_default_for_the_whole_answer():
    offenders = []
    for path in python_sources():
        if path.stem in OWN_FOREIGN_DEFAULT:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            tool = _tool_of(node)
            if tool is None:
                continue
            arguments = node.args[1] if len(node.args) > 1 else None
            for keyword in node.keywords:
                if keyword.arg == "arguments":
                    arguments = keyword.value
            named = isinstance(arguments, ast.Dict) and any(
                isinstance(key, ast.Constant) and key.value == "limit" for key in arguments.keys
            )
            if not named:
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno} ({tool})")

    assert not offenders, (
        f"{offenders} кличуть інструмент без стелі, а чуже замовчування там -- "
        + "; ".join(f"{tool}: {cut}" for tool, cut in sorted(TOOLS_THAT_CUT_SILENTLY.items()))
        + ". Клич `agent.place.all_branches(...)` або назви `limit` у самому виклику."
    )


def test_the_script_allowed_to_ask_bare_still_asks_bare():
    missing = []
    for stem in sorted(OWN_FOREIGN_DEFAULT):
        found = [path for path in python_sources() if path.stem == stem]
        if not found:
            if not (ROOT / "CLAUDE.md").exists():
                pytest.skip("публічне дерево без замірів")
            missing.append(f"{stem}: файла немає")
            continue
        tree = ast.parse(found[0].read_text(encoding="utf-8"))
        bare = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and _tool_of(node) is not None
            and not any(
                isinstance(key, ast.Constant) and key.value == "limit"
                for argument in node.args[1:2]
                if isinstance(argument, ast.Dict)
                for key in argument.keys
            )
        ]
        if not bare:
            missing.append(f"{stem}: голого виклику вже немає, виняток зайвий")

    assert not missing, (
        f"{missing} -- виняток воріт про чуже замовчування описує замір, "
        "якого немає. Прибери рядок або поверни виклик."
    )


FIELDS_WITHOUT_A_READER = {
    "exclusions": "слова обмежень їдуть усередині `rules`; id ніде не беруться",
}


def test_no_field_of_the_build_request_dies_silently():
    from komora.api.schemas import BuildRequest

    parts = [
        ROOT / "src" / "komora" / part
        for part in ("agent/basket.py", "agent/cart.py", "agent/refill.py", "api/app.py")
    ] + sorted((ROOT / "src" / "komora" / "agent" / "steps").glob("*.py"))
    readers = "\n".join(part.read_text(encoding="utf-8") for part in parts)
    dead = [
        name
        for name in BuildRequest.model_fields
        if name not in FIELDS_WITHOUT_A_READER and name not in readers
    ]

    assert not dead, (
        "поле запиту не читає ніхто: "
        + ", ".join(sorted(dead))
        + " — або підключи його до збірки, або назви причину у "
        "FIELDS_WITHOUT_A_READER разом з тим, ЧИМ ефект досягається"
    )


BEFORE_THE_STAGE = (
    "place.cart",
    "place.decide",
    "intents.compose",
    "shelf.search",
    "decide.pick",
    "decide.chain",
    "decide.twins",
    "economy.settle",
)


def test_the_stage_may_move_only_the_steps_the_executor_actually_gates():
    from komora.core.understanding import PLAN_GATED

    source = (ROOT / "src" / "komora" / "agent" / "basket.py").read_text(encoding="utf-8")
    gated = set(re.findall(r'\.run\(\s*"([a-z_.]+)"', source))

    assert gated == set(PLAN_GATED) | set(BEFORE_THE_STAGE), (
        f"збірка гейтить планом {sorted(gated)}, а етап розуміння вміє рухати "
        f"{sorted(PLAN_GATED)} — розходження мовчазне в обидва боки"
    )


def test_every_step_without_a_runner_is_named_in_the_dictionary():
    from komora.core.plan import NO_RUNNER, STEPS, Phase

    agent = ROOT / "src" / "komora" / "agent"
    source = "".join(path.read_text(encoding="utf-8") for path in sorted(agent.rglob("*.py")))
    nameless = {step.name for step in STEPS if f'"{step.name}"' not in source}
    at_checkout = {step.name for step in STEPS if step.phase is Phase.CART}

    assert nameless - at_checkout == set(NO_RUNNER), (
        f"конвеєр не виконує {sorted(nameless - at_checkout)}, а `NO_RUNNER` знає "
        f"{sorted(NO_RUNNER)} — розходження мовчазне в обидва боки: зайве ім'я "
        "робить робочий крок «без виконавця», забуте ховає діру в «не знадобилось»"
    )


PLAN_RULES = (
    "MAX_STEPS",
    "MAX_WRITES",
    "_WRITES_NEED_REREAD",
    "_ESSENTIAL_BEFORE_WRITE",
    "_BEFORE_SLOT_OK",
    "cart.write",
    "cart.remove",
    "decide.pick",
    "decide.chain",
    "economy.settle",
)


def test_the_executor_keeps_no_second_copy_of_the_plan_rules():
    source = (ROOT / "src" / "komora" / "agent" / "executor.py").read_text(encoding="utf-8")
    copied = [rule for rule in PLAN_RULES if rule in source]

    assert not copied, (
        "виконавець носить копію правил плану: "
        + ", ".join(copied)
        + " — суди їх `core.plan.validate`, інакше копія розійдеться зі словником мовчки"
    )
    assert "validate(" in source, (
        "виконавець не кличе `core.plan.validate` — тоді правила він або не "
        "перевіряє взагалі, або перевіряє своєю копією"
    )


def test_every_chain_the_agent_builds_knows_the_guests_rules():
    offenders = []
    for path in python_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not ast.unparse(node.func).endswith("agent_chains"):
                continue
            if not any(kw.arg == "rules" for kw in node.keywords):
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert not offenders, (
        f"{offenders} кличуть `agent_chains` без `rules=`. Ланцюжок тоді "
        "складається без обмежень гостя і їде збирачу від його імені."
    )


def test_every_line_built_after_the_assembly_keeps_the_terms_the_guest_set():
    path = ROOT / "src" / "komora" / "agent" / "refill.py"
    tree = ast.parse(path.read_text("utf-8"))
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and ast.unparse(node.func).endswith("build_lines")
    ]
    assert len(calls) >= 3, "виклики `build_lines` у доборі зникли — онови ворота"

    def carries_terms(node: ast.Call) -> bool:
        spread = any(
            keyword.arg is None
            and isinstance(keyword.value, ast.Call)
            and ast.unparse(keyword.value.func).endswith("guest_terms")
            for keyword in node.keywords
        )
        named = {keyword.arg for keyword in node.keywords}
        return spread or {"auto_swap", "auto_swap_percent", "hours_to_slot"} <= named

    missing = [f"refill.py:{node.lineno}" for node in calls if not carries_terms(node)]
    assert not missing, (
        f"{missing}: рядок будується НЕ тими умовами, що збірка — гість зі "
        "згодою на авто-заміну дістане питання замість вилки, і виглядати це "
        "буде як його ж рішення"
    )


def test_every_call_into_the_model_names_its_prompt():
    offenders = []
    for path in (ROOT / "src").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not ast.unparse(node.func).endswith(".decide"):
                continue
            if ast.unparse(node.func) == "self._inner.decide":
                continue
            if not any(kw.arg == "prompt" for kw in node.keywords):
                offenders.append(f"{path.relative_to(ROOT)}:{node.lineno}")
    assert offenders == [], (
        f"{offenders} ходять у модель без `prompt=`. У журналі й трейсі не буде "
        "видно, яким текстом питали, — а число пасток заміряне саме на текстах."
    )


def test_every_prompt_of_ours_is_in_the_registry():
    from komora.agent import prompts, skills
    from komora.core import skills as core_skills

    prompts.load_all()
    by_text = {prompt.text: name for name, prompt in prompts.REGISTRY.items()}

    unregistered = []
    for path in (ROOT / "src" / "komora").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.Assign) or not isinstance(node.value, ast.Constant):
                continue
            names = [target.id for target in node.targets if isinstance(target, ast.Name)]
            if not any(name.endswith("_SYSTEM") for name in names):
                continue
            if node.value.value not in by_text:
                unregistered.append(f"{path.relative_to(ROOT)}:{node.lineno} {names[0]}")
    assert unregistered == [], (
        f"{unregistered} не зареєстровані (`agent/prompts.register`). Правка "
        "такого промпта не спинить публікацію, тобто ворота свіжості пасток "
        "мовчки його не бачать."
    )

    skills_dir = ROOT / "src" / "komora" / "agent" / "skills"
    stems = sorted(path.stem for path in skills_dir.glob("*.md"))
    assert stems, "у agent/skills/ немає жодного .md — онови ворота"
    missing = [stem for stem in stems if f"skill.{stem}" not in prompts.REGISTRY]
    assert missing == [], (
        f"скіли {missing} лежать файлами, але не в реєстрі: їхня правка не "
        "перезамірить власну пастку"
    )

    every = tuple(core_skills.Skill(name=name, why="") for name in core_skills.ORDER)
    composed = {
        "pick без межі": basket.pick_system(with_queue=False),
        "pick з межею": basket.pick_system(with_queue=True),
        "pick зі скілами": basket.pick_system(with_queue=True, skills=skills.block(every)),
    }
    leaked = {}
    for label, text in composed.items():
        rest = text
        for name in prompts.parts_in(text):
            rest = rest.replace(prompts.REGISTRY[name].text, "", 1)
        if rest.strip():
            leaked[label] = rest.strip()[:120]
    assert leaked == {}, (
        f"у складеному промпті є шматки повз реєстр: {leaked}. Їхня правка не "
        "змінить жодного хеша, тобто поїде в модель, не перезамірявши пасток."
    )


def _said_of_builder() -> ast.Call:
    tree = ast.parse((ROOT / "src/komora/api/app.py").read_text(encoding="utf-8"))
    builder = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "_said_of"
    )
    return next(
        node
        for node in ast.walk(builder)
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "Said"
    )


def test_the_guest_word_travels_whole_and_is_built_in_one_place():
    calls, built = [], []
    for path in python_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = ast.unparse(node.func).rsplit(".", 1)[-1]
            if name in ("pantry_live", "bar_live") and not any(
                kw.arg == "said" for kw in node.keywords
            ):
                calls.append(f"{path.relative_to(ROOT).as_posix()}:{node.lineno}")
            if name == "Said" and (node.keywords or node.args):
                built.append(f"{path.relative_to(ROOT).as_posix()}:{node.lineno}")
    assert not calls, (
        f"{calls} збирають комору без слів гостя. Позначки, названі цикли і "
        "список гостя мовчки не доїдуть -- рівно так і жив #300."
    )
    assert built == [f"src/komora/api/app.py:{_said_of_builder().lineno}"], (
        f"`Said` збирається не лише в `_said_of`: {built}. Другий збирач "
        "розійдеться з першим тихо, і побачити це можна буде лише на екрані."
    )


def test_only_the_builder_reads_the_axes_of_the_guest_word():
    axes = (
        "_marks_of",
        "_cycles_of",
        "_hidden_of",
        "_source_of",
        "_manual_of",
        "_apart_of",
        "_drinks_of",
    )
    app = ROOT / "src/komora/api/app.py"
    tree = ast.parse(app.read_text(encoding="utf-8"))

    named = {
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    assert set(axes) <= named, (
        f"осей {sorted(set(axes) - named)} у `api/app.py` немає: ці ворота "
        "стережуть ім'я, якого нема кому зламати. Перейменували читача -- "
        "перейменуйте і тут, інакше вісь лишиться без нагляду мовчки."
    )

    home: dict[int, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            for inner in ast.walk(node):
                home.setdefault(id(inner), node.name)

    outside = [
        f"{app.relative_to(ROOT).as_posix()}:{node.lineno} ({home.get(id(node), '?')})"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and ast.unparse(node.func) in axes
        and home.get(id(node)) != "_said_of"
    ]
    assert not outside, (
        f"{outside} читають вісь слова гостя повз збирача. Прочитана поруч із "
        "`said=`, вона знову стає окремим аргументом -- і саме так жив #300."
    )


def test_the_one_builder_fills_every_axis_of_the_guest_word():
    said = ast.parse((ROOT / "src/komora/core/said.py").read_text(encoding="utf-8"))
    shape = next(
        node for node in ast.walk(said) if isinstance(node, ast.ClassDef) and node.name == "Said"
    )
    axes = {
        node.target.id
        for node in shape.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
    }
    filled = {kw.arg for kw in _said_of_builder().keywords}

    assert axes <= filled, (
        f"збирач не читає осей {sorted(axes - filled)}: гість про них сказав, "
        "а продукт мовчатиме -- і виглядатиме це як «він нічого не казав»."
    )


_DRINK_CACHE_WRITER = "_drink_word"


def test_every_reader_of_the_models_drink_guess_lets_the_guest_overrule_it():
    seen: list[str] = []
    for path in sorted((ROOT / "src" / "komora").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))

        overruled: set[int] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and ast.unparse(node.func).endswith("said_group"):
                for arg in [*node.args, *(kw.value for kw in node.keywords)]:
                    overruled |= {id(inner) for inner in ast.walk(arg)}

        home: dict[int, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                for inner in ast.walk(node):
                    home.setdefault(id(inner), node.name)

        seen += [
            f"{path.relative_to(ROOT).as_posix()}:{node.lineno} ({home.get(id(node), '?')})"
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute)
            and node.attr == "drink"
            and id(node) not in overruled
            and home.get(id(node)) != _DRINK_CACHE_WRITER
        ]

    assert not seen, (
        f"{seen} читають здогад моделі про полицю повз `said_group`: слово гостя "
        "про свій бар туди не доїде, і рядок мовчки повернеться до замерзлого "
        "здогаду (#261). Читати здогад сирим можна лише тому, хто кладе його "
        f"в кеш назв (`{_DRINK_CACHE_WRITER}`)."
    )


JOIN_IN_PHRASE_OK = {
    "step-risk": "склеюються дві числові клаузи, а не перелік рядків",
}


def test_no_step_of_the_trace_glues_a_list_into_its_phrase():
    glued: list[str] = []
    for path in sorted((ROOT / "src/komora").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or len(node.args) < 4:
                continue
            called = node.func
            if not (isinstance(called, ast.Attribute) and called.attr == "add"):
                continue
            owner = called.value
            if not (isinstance(owner, ast.Name) and owner.id in {"trace", "tracer"}):
                continue
            step = ast.literal_eval(node.args[0]) if isinstance(node.args[0], ast.Constant) else "?"
            if step in JOIN_IN_PHRASE_OK:
                continue
            joins = [
                inner
                for inner in ast.walk(node.args[3])
                if isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Attribute)
                and inner.func.attr == "join"
            ]
            if joins:
                glued.append(f"{path.name}:{node.lineno} {step}")

    assert not glued, (
        "фраза кроку склеює перелік: "
        + ", ".join(glued)
        + " — перелік їде в args (під дебагом його видно розгортанням), "
        "а у фразі лишаються числа (#301)"
    )


def test_the_verdict_of_sense_travels_to_both_sides_of_the_product():
    tree = ast.parse((ROOT / "src" / "komora" / "agent" / "basket.py").read_text("utf-8"))
    holders = (ast.FunctionDef, ast.AsyncFunctionDef)

    def callers(name: str) -> set[str]:
        return {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, holders)
            for call in ast.walk(node)
            if isinstance(call, ast.Call) and ast.unparse(call.func).endswith(name)
        }

    keeps, sense = callers("apply_keeps"), callers("apply_sense")
    assert keeps, "`apply_keeps` більше ніхто не кличе — онови ворота"
    assert keeps == sense, (
        f"стеля зберігання і глузд розійшлись домами: keeps у {sorted(keeps)}, "
        f"sense у {sorted(sense)} — половина без вето означає, що рядок комори "
        "і рядок кошика кажуть про той самий вид різне"
    )


def _mutmut_config() -> dict[str, list[str]]:
    import tomllib

    config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    return config.get("tool", {}).get("mutmut", {})


def _circuit_modules() -> list[str]:
    found: list[str] = []
    for pattern in _mutmut_config()["only_mutate"]:
        for path in sorted(ROOT.glob(pattern)):
            if path.suffix != ".py" or path.name == "__init__.py":
                continue
            found.append(".".join(path.relative_to(ROOT / "src").with_suffix("").parts))
    assert found, "у контурі мутацій немає жодного модуля — міряти нема що"
    return found


def _selected_test_files() -> set[Path]:
    picked: set[Path] = set()
    for entry in _mutmut_config()["pytest_add_cli_args_test_selection"]:
        target = ROOT / entry
        picked |= set(target.rglob("test_*.py")) if target.is_dir() else {target}
    return picked


def _imported_modules(path: Path) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            names |= {alias.name for alias in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            names |= {f"{node.module}.{alias.name}" for alias in node.names}
    return names


def test_every_module_of_the_mutation_circuit_is_covered_by_a_test_inside_the_selection():
    selected = _selected_test_files()
    tests = {path: _imported_modules(path) for path in ROOT.glob("tests/**/test_*.py")}

    blind: list[str] = []
    for module in _circuit_modules():
        seen = [path for path, names in tests.items() if module in names]
        if not any(path in selected for path in seen):
            blind.append(
                f"{module}: тестів у вибірці немає"
                + (f", а поза нею є — {', '.join(p.name for p in seen)}" if seen else " взагалі")
            )

    assert not blind, (
        "модуль контуру, який ганяється без своїх тестів, віддає ФАЛЬШИВОГО вижилого:\n"
        + "\n".join(blind)
        + "\nабо додай тести у вибірку `pytest_add_cli_args_test_selection`, "
        "або напиши їх поруч із модулем"
    )


def _is_fact_read(node: ast.expr, name: str) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "facts"
        and bool(node.args)
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == name
    )


def _edits_the_list(node: ast.Call) -> bool:
    func = node.func
    return (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id == "intents"
        and func.attr in {"append", "remove", "extend", "insert", "clear", "pop"}
    )


def _lays_the_fact(node: ast.Call, publishers: set[str]) -> bool:
    func = node.func
    if not isinstance(func, ast.Attribute) or not node.args:
        return False
    named = node.args[0]
    if not isinstance(named, ast.Constant):
        return False
    if func.attr == "put" and isinstance(func.value, ast.Name) and func.value.id == "facts":
        return named.value == "intents"
    return func.attr in {"run", "run_all"} and named.value in publishers


def test_the_fact_is_re_laid_after_the_list_of_intents_changes():
    from komora.core.plan import STEPS

    publishers = {kind.name for kind in STEPS if "intents" in kind.gives}
    source = pathlib.Path(basket.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "assemble_list"
    )

    changed: list[int] = []
    laid: list[int] = []
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "intents" for target in node.targets
        ):
            if not _is_fact_read(node.value, "intents"):
                changed.append(node.lineno)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "intents":
                changed.append(node.lineno)
        elif isinstance(node, ast.Call):
            if _edits_the_list(node):
                changed.append(node.lineno)
            elif _lays_the_fact(node, publishers):
                laid.append(node.lineno)

    assert changed, "перелік намірів у збірці не міняється — ворота втратили предмет"
    assert laid, (
        "`intents` міняється в `assemble_list`, а факт не перекладається жодного разу: "
        "крок, який зв'яже цей вхід, дістане список, якого вже немає"
    )
    assert max(laid) > max(changed), (
        f"остання правка переліку намірів — рядок {max(changed)}, останній "
        f"запис факту — рядок {max(laid)}: факт лишається старішим за список"
    )


def test_every_quantity_written_to_the_cart_knows_its_unit():
    calls: list[tuple[str, ast.Call]] = []
    for path in (ROOT / "src" / "komora").rglob("*.py"):
        tree = ast.parse(path.read_text("utf-8"))
        calls += [
            (str(path.relative_to(ROOT)).replace("\\", "/"), node)
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and ast.unparse(node.func).endswith("qty_for_api")
        ]
    assert len(calls) >= 2, "виклики `qty_for_api` зникли — онови ворота разом з кодом"

    blind = [
        f"{where}:{node.lineno}"
        for where, node in calls
        if len(node.args) < 2 and not any(keyword.arg == "product" for keyword in node.keywords)
    ]
    assert not blind, (
        f"{blind}: кількість їде в кошик без картки товару — «штучне» від "
        "«вагового» не відрізнити, і 1.3 шт з чужого клієнта поїдуть у "
        "замовлення під нашим іменем (#317)"
    )


SPEECH_FAILURES_REQUIRED = {
    "not-allowed",
    "service-not-allowed",
    "network",
    "no-speech",
    "audio-capture",
    "aborted",
}


def speech_source() -> str:
    return (ROOT / "web" / "src" / "lib" / "speech.ts").read_text(encoding="utf-8")


def mic_screens() -> list[Path]:
    web = ROOT / "web" / "src"
    return sorted(
        path
        for path in web.rglob("*.svelte")
        if path.name != "MicButton.svelte" and "<MicButton" in path.read_text(encoding="utf-8")
    )


def test_every_microphone_asks_the_one_home_about_voice():
    screens = mic_screens()
    assert len(screens) >= 5, (
        "точок мікрофона знайшлось менше, ніж їх є, -- ворота стали б порожніми: "
        f"{[path.name for path in screens]}"
    )

    silent = []
    bare = []
    for path in screens:
        source = path.read_text(encoding="utf-8")
        if "voiceAvailable()" not in source:
            silent.append(path.name)
        body = "\n".join(
            line for line in source.splitlines() if "from '" not in line and 'from "' not in line
        )
        if re.search(r"voiceAvailable(?!\s*\()", body):
            bare.append(path.name)

    assert not silent, (
        f"{silent}: мікрофон стоїть, а дім рішення не питається -- своя умова тут "
        "розійдеться з рештою мовчки (#158)"
    )
    assert not bare, (
        f"{bare}: `voiceAvailable` без дужок істинне завжди -- кнопка з'явиться "
        "там, де двигуна немає"
    )


def test_only_the_speech_port_names_the_browser_engine():
    web = ROOT / "web" / "src"
    port = web / "lib" / "speech.ts"
    reach = re.compile(r"""(?:new\s+|\.|\[['"])(?:webkit)?SpeechRecognition""")
    guilty = sorted(
        path.relative_to(ROOT).as_posix()
        for path in list(web.rglob("*.svelte")) + list(web.rglob("*.ts"))
        if path != port and reach.search(path.read_text(encoding="utf-8"))
    )
    assert not guilty, (
        f"{guilty}: двигун браузера називається поза портом -- ознака є, а "
        "можливості може не бути (Brave), і кожна копія судитиме по-своєму"
    )


def test_every_failure_code_of_the_microphone_has_words():
    source = speech_source()
    start = source.index("const FAILURES")
    block = source[start : source.index("}", start)]
    codes = set(re.findall(r"^\s*'?([a-z-]+)'?:", block, re.MULTILINE))

    missing = sorted(SPEECH_FAILURES_REQUIRED - codes)
    assert not missing, (
        f"{missing}: код відмови без свого тексту -- гість бачить «щось пішло не так» "
        "замість причини і поради"
    )
    assert "failureText" in source, (
        "текст причини мусить мати одну функцію-читача: другий словник поруч "
        "розійшовся б з цим мовчки (#158)"
    )


_PLACE_WITHOUT_GUEST = {
    "src/komora/agent/steps/place.py",
    "src/komora/agent/bar.py",
    "src/komora/agent/basket.py",
    "src/komora/agent/spending.py",
}


def test_every_guest_path_asks_all_three_sources_of_the_branch():
    offenders = []
    for path in (ROOT / "src" / "komora").rglob("*.py"):
        where = str(path.relative_to(ROOT)).replace("\\", "/")
        if where in _PLACE_WITHOUT_GUEST:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = ast.unparse(node.func)
            if not (name.endswith("resolve_place") or name.endswith("place.resolve")):
                continue
            if not any(kw.arg in {"ask_cart", "cart_branch"} for kw in node.keywords):
                offenders.append(f"{where}:{node.lineno} ({name})")
    assert not offenders, (
        f"{offenders} шукають філію гостя без `ask_cart=`/`cart_branch=`. "
        "Кошик -- ДРУГЕ джерело порядку #47, і без нього гість без адреси "
        "дістане нашу філію: чужа полиця, чужі ціни, і рядок поруч скаже про "
        "це рівно те, що ми його навчили, тобто неправду."
    )


def test_the_places_named_as_guestless_still_resolve_the_branch():
    missing = []
    for where in sorted(_PLACE_WITHOUT_GUEST):
        path = ROOT / where
        if not path.exists():
            missing.append(f"{where}: файла немає")
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and (
                ast.unparse(node.func).endswith("resolve_place")
                or ast.unparse(node.func).endswith("place.resolve")
            )
        ]
        if not calls:
            missing.append(f"{where}: ланцюжок філії тут більше не кличеться")
    assert not missing, (
        f"{missing} -- виняток воріт про джерела філії описує код, якого немає. "
        "Прибери рядок або поверни виклик: дозвіл, виданий у порожнечу, "
        "прикриє наступний забутий кошик."
    )


def _place_fallbacks() -> set[str]:
    found: set[str] = set()
    for path in (ROOT / "src" / "komora" / "agent").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.AsyncFunctionDef | ast.FunctionDef):
                continue
            args = node.args
            names = [arg.arg for arg in args.kwonlyargs]
            defaults = args.kw_defaults
            for name, default in zip(names, defaults, strict=True):
                if name == "place" and isinstance(default, ast.Constant) and default.value is None:
                    found.add(node.name)
    return found


def _api_aliases(tree: ast.Module) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for name in node.names:
                aliases[name.asname or name.name] = name.name
    return aliases


def test_no_guest_endpoint_lets_the_pipeline_look_for_the_branch_itself():
    fallbacks = _place_fallbacks()
    assert fallbacks, "жодної функції із запасним шляхом філії -- обхід зламався"

    offenders = []
    for path in sorted((ROOT / "src" / "komora" / "api").rglob("*.py")):
        where = str(path.relative_to(ROOT)).replace("\\", "/")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        aliases = _api_aliases(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            called = ast.unparse(node.func).split(".")[-1]
            if aliases.get(called, called) not in fallbacks:
                continue
            if not any(kw.arg == "place" for kw in node.keywords):
                offenders.append(f"{where}:{node.lineno} ({called})")

    assert not offenders, (
        f"{offenders} пускають конвеєр шукати філію самостійно. Передай "
        "`place=` з `place_of`: там живе і пам'ять сесії, і названа руками "
        "адреса, і кошик як друге джерело порядку #47."
    )


def test_no_fact_is_left_stale_by_a_rebinding_of_the_name_that_holds_it():
    bag_puts: list[tuple[str, str, int]] = []
    rebinds: dict[tuple[str, str], list[int]] = {}
    reads: set[tuple[str, str, int]] = set()

    for path in sorted((ROOT / "src" / "komora").rglob("*.py")):
        tree = ast.parse(path.read_text("utf-8"))
        for func in ast.walk(tree):
            if not isinstance(func, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            where = f"{path.relative_to(ROOT).as_posix()}:{func.name}"
            for node in ast.walk(func):
                if (
                    isinstance(node, ast.Call)
                    and ast.unparse(node.func).endswith(".put")
                    and len(node.args) == 2
                    and isinstance(node.args[1], ast.Name)
                ):
                    bag_puts.append((where, node.args[1].id, node.lineno))
                if (
                    isinstance(node, ast.keyword)
                    and node.arg == "facts"
                    and isinstance(node.value, ast.Dict)
                ):
                    for value in node.value.values:
                        if isinstance(value, ast.Name):
                            bag_puts.append((where, value.id, node.value.lineno))
                if isinstance(node, ast.Assign):
                    from_bag = ".get(" in ast.unparse(node.value)
                    for target in node.targets:
                        if not isinstance(target, ast.Name):
                            continue
                        rebinds.setdefault((where, target.id), []).append(node.lineno)
                        if from_bag:
                            reads.add((where, target.id, node.lineno))

    assert bag_puts, "жодного `facts.put` у src/komora — ворота осліпли, онови їх"

    stale: list[str] = []
    for where, name, put_at in bag_puts:
        later_puts = [line for w, n, line in bag_puts if (w, n) == (where, name) and line > put_at]
        for line in rebinds.get((where, name), []):
            if line <= put_at or (where, name, line) in reads:
                continue
            if any(line < again for again in later_puts):
                continue
            stale.append(f"{where}: `{name} = ...` у рядку {line} після put у {put_at}")

    assert not stale, (
        f"{stale}: мішок лишається зі СТАРИМ об'єктом, а крок, який читає цей "
        "факт, рахує вчорашній стан — правити треба НА МІСЦІ (`x[:] = ...`) "
        "або перекласти факт другим `put`"
    )


def test_every_postponed_intent_carries_the_action_that_frees_it():
    tagged: set[int] = set()
    calls: list[tuple[Path, ast.Call]] = []
    for path in python_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Tuple) and len(node.elts) == 2:
                mark, made = node.elts
                if (
                    isinstance(mark, ast.Attribute)
                    and ast.unparse(mark).startswith("Remedy.")
                    and isinstance(made, ast.Call)
                    and ast.unparse(made.func).endswith("Postponed")
                ):
                    tagged.add(id(made))
            if isinstance(node, ast.Call) and ast.unparse(node.func).endswith("Postponed"):
                calls.append((path, node))
    offenders = [
        f"{path.relative_to(ROOT)}:{node.lineno}" for path, node in calls if id(node) not in tagged
    ]
    assert not offenders, (
        f"{offenders} кладуть намір у відкладене без мітки `Remedy`. Порада "
        "гостю стане в чергу за порядком фаз, а не за тим, що її зрушить."
    )


def test_the_postponed_block_leaves_the_assembly_in_fix_order():
    tree = ast.parse((ROOT / "src" / "komora" / "agent" / "basket.py").read_text(encoding="utf-8"))
    ordered = {
        target.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Call)
        and ast.unparse(node.value.func).endswith("in_fix_order")
        for target in node.targets
        if isinstance(target, ast.Name)
    }
    handed: list[str] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and ast.unparse(node.func).endswith("Basket")):
            continue
        for kw in node.keywords:
            if kw.arg != "postponed":
                continue
            value = ast.unparse(kw.value)
            handed.append(value)
            assert value in ordered or value.startswith("in_fix_order("), (
                f"`Basket(postponed={value})` на рядку {node.lineno} обходить "
                "`in_fix_order`: черга порад знову стане чергою фаз."
            )
    assert handed, "збірка більше не віддає `postponed` -- ворота осиротіли"


def test_every_workflow_publish_dispatches_still_exists_by_that_name():
    source = (ROOT / "scripts" / "publish.py").read_text(encoding="utf-8")
    match = re.search(r"DEPLOY_WORKFLOWS = \(([^)]*)\)", source)
    assert match is not None, "у publish.py немає переліку DEPLOY_WORKFLOWS"
    named = re.findall(r'"([^"]+\.yml)"', match.group(1))
    assert named, "перелік порожній: деплої не запускаються ніким"
    for name in named:
        assert (ROOT / ".github" / "workflows" / name).is_file(), (
            f"publish.py диспатчить {name}, а такого воркфлоу немає -- "
            "публікація дійде до пуша і мовчки не задеплоїть"
        )
