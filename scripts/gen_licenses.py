from __future__ import annotations

import argparse
import json
import sys
import tomllib
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "licenses.md"
NODE_LOCK = ROOT / "web" / "package-lock.json"

PROJECT_LICENSE = "Apache-2.0"

HEADER = f"""<!--
  ЗГЕНЕРОВАНО: scripts/gen_licenses.py — руками не правити.
  Джерело — lock-файли, а не встановлене середовище: воно залежить від ОС.
  Розділи «Моделі» і «Дані» задані в самому скрипті: це рішення проєкту,
  а не факт середовища.
-->

# Ліцензії

Перелік на виконання п. 8.6 умов хакатону: бібліотеки, open-source компоненти,
моделі, датасети.

Зібраний з `uv.lock` і `web/package-lock.json`, тому не залежить від того, на
якій ОС його згенерували, і охоплює всі платформозалежні збірки.

Сам проєкт — **{PROJECT_LICENSE}**, повний текст у [LICENSE](../LICENSE).
"""

MODELS = [
    (
        "Claude (Anthropic)",
        "через Amazon Bedrock",
        "комерційні умови постачальника; ваги не розповсюджуються",
    ),
    (
        "Mistral, OpenAI gpt-oss, Qwen та інші на Bedrock",
        "через Amazon Bedrock",
        "умови відповідних постачальників; використовуються як резерв і для розробки",
    ),
]

DATA = [
    (
        "Історія покупок гостя",
        "власні дані користувача через офіційний MCP «Сільпо»",
        "не розповсюджуються; у публічні фікстури йдуть лише анонімізовані похідні (ADR-03)",
    ),
    (
        "Каталог і слоти «Сільпо»",
        "офіційний MCP",
        "зображення товарів і бренд не хостимо — лише посилання на CDN; логотип не "
        "використовуємо; сам каталог у репозиторій не їде (нижче)",
    ),
]

CATALOG_NOTE = """### Каталог у репозиторій НЕ їде, і це рішення, а не пропуск

Щоб відрізнити «м'ясний рулет» від «рулета з маком», продукт будує мапу
артикул-вузол обходом каталогу (18 філій, 49 415 товарів, 52 хв). Три яруси
напрацювань, і вони різні за суттю:

- **орфографічний словник** (191 слово: `мясний` -> `м'ясний`) -- публікується.
  Це правопис української мови, а не дані «Сільпо»: той самий список будується
  з будь-якого українського корпусу, і замісної вартості для них не має;
- **перелік стилізованих брендів** (51 слово, які не зводяться до однієї
  абетки) -- публікується з описом походження. Це назви торгових марок
  рядками, без логотипів і без стилю;
- **сам каталог** (назви, `slug`, `id`, ціни, залишки) -- **не публікується.**
  Три причини, і кожної досить окремо: це суттєве вилучення з чужої бази, а не
  похідна ідея; ціни й залишки протухають за тиждень, а публічний репозиторій
  вічний -- вийшов би файл, який виглядає як факт про «Сільпо» і бреше; і
  хакатон проводить саме «Сільпо», тож вивантажений каталог у нашому
  публічному репозиторії читається як «ми вас спарсили», а не як продукт.

Тому мапа не є артефактом репозиторію ВЗАГАЛІ. Вона живе там само, де вже
живе дерево категорій, -- у Postgres, куди її кладе крон (`db/categories.py`,
`komora-categories`). У git їде код, який її будує; дані лишаються в базі.

А в «Ідеях» стоїть протилежний бік цього ж: дайте вузол і фасовку полями в
API -- і обходити 858 листків по 18 філіях не доведеться нікому. Обхідний
шлях ми лікуємо пропозицією, а не мовчанням."""

_LICENSE_FIELDS = ("License-Expression", "License")
_CLASSIFIER_PREFIX = "License :: "

_PYTHON_LICENSE_OVERRIDE = {
    "colorama": "BSD License",
    "pywin32": "PSF",
    "tzdata": "Apache-2.0",
    "httpx2-jsfetch": "BSD-3-Clause",
    "winloop": "MIT License",
}


def _normalise(name: str) -> str:
    return name.lower().replace("_", "-")


def python_packages() -> list[tuple[str, str, str]]:
    lock = tomllib.loads((ROOT / "uv.lock").read_text(encoding="utf-8"))

    installed = {}
    for dist in metadata.distributions():
        name = dist.metadata["Name"]
        if name:
            installed[_normalise(name)] = _python_license(dist)

    rows = []
    for package in lock.get("package", []):
        name = package.get("name")
        if not name:
            continue
        key = _normalise(name)
        lic = _PYTHON_LICENSE_OVERRIDE.get(key) or installed.get(key) or "не вказано"
        rows.append((name, package.get("version", "—"), lic))

    return sorted(rows, key=lambda row: row[0].lower())


def _python_license(dist: metadata.Distribution) -> str:
    for field in _LICENSE_FIELDS:
        value = dist.metadata.get(field)
        if value and len(value) < 60 and "\n" not in value:
            return value.strip()

    classifiers = dist.metadata.get_all("Classifier") or []
    named = [
        c.removeprefix(_CLASSIFIER_PREFIX)
        for c in classifiers
        if c.startswith(_CLASSIFIER_PREFIX)
    ]
    if named:
        return ", ".join(part.split(" :: ")[-1] for part in named)

    return "не вказано"


def node_packages() -> list[tuple[str, str, str]]:
    lock = json.loads(NODE_LOCK.read_text(encoding="utf-8"))

    rows: dict[str, tuple[str, str, str]] = {}
    for path, data in lock.get("packages", {}).items():
        if not path:
            continue
        name = path.rsplit("node_modules/", 1)[-1]
        version = data.get("version")
        if not version:
            continue
        rows[name] = (name, version, data.get("license") or "не вказано")

    return sorted(rows.values(), key=lambda row: row[0].lower())


def _table(rows: list[tuple[str, str, str]], headers: tuple[str, str, str]) -> list[str]:
    lines = [f"| {headers[0]} | {headers[1]} | {headers[2]} |", "| --- | --- | --- |"]
    lines += [f"| {a} | {b} | {c} |" for a, b, c in rows]
    return lines


def render() -> str:
    python = python_packages()
    node = node_packages()

    if not node:
        raise SystemExit(f"{NODE_LOCK} не дав жодного пакета — перевір lock-файл")
    if not python:
        raise SystemExit("uv.lock не дав жодного пакета — перевір lock-файл")

    lines = [HEADER, "\n## Python\n"]
    lines.append(f"Пакетів у `uv.lock`: **{len(python)}** (з транзитивними).\n")
    lines += _table(python, ("Пакет", "Версія", "Ліцензія"))

    lines.append("\n## Node (фронтенд)\n")
    lines.append(
        f"Пакетів у `web/package-lock.json`: **{len(node)}**. Перелік охоплює й "
        "платформозалежні збірки для інших ОС — вони можуть поставитись у CI "
        "або в іншого розробника.\n"
    )
    lines += _table(node, ("Пакет", "Версія", "Ліцензія"))

    lines.append("\n## Моделі\n")
    lines.append("Ваги не розповсюджуються: доступ виключно через API постачальника.\n")
    lines += _table(MODELS, ("Модель", "Доступ", "Умови"))

    lines.append("\n## Дані\n")
    lines.append("Публічних датасетів проєкт не використовує.\n")
    lines += _table(DATA, ("Джерело", "Звідки", "Умови"))
    lines.append("\n" + CATALOG_NOTE + "\n")

    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Згенерувати docs/licenses.md")
    parser.add_argument("--check", action="store_true", help="звірити, не переписувати")
    args = parser.parse_args()

    rendered = render()

    if args.check:
        current = OUTPUT.read_text(encoding="utf-8") if OUTPUT.exists() else ""
        if current != rendered:
            print("docs/licenses.md застарів — запусти scripts/gen_licenses.py", file=sys.stderr)
            return 1
        print("перелік ліцензій актуальний")
        return 0

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(rendered, encoding="utf-8")
    print(f"записано {OUTPUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
