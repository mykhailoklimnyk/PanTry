from __future__ import annotations

import importlib.util
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
TARGET = ROOT / "web" / "src" / "lib" / "facts.ts"
MUTATION = ROOT / "docs" / "mutation.json"
KINDS = ROOT / "docs" / "mutation_kinds.json"
PASSK = ROOT / "docs" / "passk.json"


def mutation() -> dict[str, object]:
    if not MUTATION.exists():
        raise SystemExit(
            "Немає docs/mutation.json. Прогони мутантів там, де вони працюють "
            "(Федора чи CI): uv run python scripts/mutation_snapshot.py. "
            "Деталі — docs/setup.md, розділ «Мутації»."
        )
    return json.loads(MUTATION.read_text(encoding="utf-8"))


def circuit() -> list[str]:
    import mutation_snapshot

    return [path.removeprefix("src/komora/") for path in mutation_snapshot.circuit()]


def kinds() -> dict[str, Any]:
    if not KINDS.exists():
        raise SystemExit(
            "Немає docs/mutation_kinds.json. Замір іде там, де мутанти: "
            "uv run python scripts/mutation_kinds.py --sample 120 --snapshot "
            "(docs/setup.md, розділ «Мутації»)."
        )
    return json.loads(KINDS.read_text(encoding="utf-8"))


def passk() -> dict[str, Any]:
    if not PASSK.exists():
        raise SystemExit(
            "Немає docs/passk.json. Прожени пастки на живій моделі: "
            "uv run python scripts/compare_models.py --runs 5 --snapshot"
        )
    return json.loads(PASSK.read_text(encoding="utf-8"))


def passk_line(snapshot: dict[str, Any]) -> str:
    from komora.core import models

    labels = {row.id: row.label for row in models.RECOMMENDED}
    return "; ".join(
        f"{labels.get(name, name)} — {row['passk']}/{row['total']}"
        for name, row in snapshot["models"].items()
    )


def traps_total(snapshot: dict[str, Any]) -> int:
    return max(int(row["total"]) for row in snapshot["models"].values())


def count_tests() -> int:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )
    counts = re.findall(r"^\S+\.py: (\d+)$", result.stdout or "", flags=re.MULTILINE)
    total = sum(int(n) for n in counts)
    if total == 0:
        raise SystemExit(
            f"pytest не зібрав жодного тесту (код {result.returncode}):\n"
            f"{(result.stdout or '')[-2000:]}\n{(result.stderr or '')[-2000:]}"
        )
    return total


def stale_lines() -> int:
    spec = importlib.util.spec_from_file_location(
        "mutation_snapshot", ROOT / "scripts" / "mutation_snapshot.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return int(module.STALE_LINES)


COMMENTS = False

_BLOCK = re.compile(r"^[ \t]*/\*.*?\*/[ \t]*\n", re.M | re.S)


def bare(text: str) -> str:
    return text if COMMENTS else _BLOCK.sub("", text).lstrip("\n")


def render() -> str:
    from komora.agent.llm.catalog import SNAPSHOT, UNAVAILABLE
    from komora.core.cycles import ASK_NOTE
    from komora.core.mandate import FORK_CAP

    tests = count_tests()
    mut = mutation()
    kind = kinds()
    stale = stale_lines()
    traps = passk()
    circuit_json = "[" + ", ".join(f"'{path}'" for path in circuit()) + "]"
    return f"""/*
  ЗГЕНЕРОВАНО scripts/gen_facts.py — руками не правити.

  Числа, які сторінки меню показують журі. Рукописний лічильник тестів
  протухає в день, коли додали тест; цей звіряє CI.
*/

/** Скільки тестів збирає pytest (разом з умовно пропущеними). */
export const TEST_COUNT = {tests}

/** Моделей у знімку каталога Bedrock. */
export const MODELS_TOTAL = {len(SNAPSHOT)}

/** Скільки з них справді відповідають — виміряно по одному виклику на кожну. */
export const MODELS_AVAILABLE = {len(SNAPSHOT) - len(UNAVAILABLE)}

/** Мутантів згенеровано за контуром з pyproject. */
export const MUTANTS_TOTAL = {mut["total"]}

/** Скільки з них завалили хоча б один тест — тобто були помічені. */
export const MUTANTS_KILLED = {mut["killed"]}

/** Скільки пережили прогін: питання до тестів, а не обов'язково дефект. */
export const MUTANTS_SURVIVED = {mut["survived"]}

/**
 * Не влізли в час. Рахуються ОКРЕМО від убитих, і це не дрібниця:
 * найпоширеніший спосіб роздути показник -- зарахувати таймаут у детекцію.
 */
export const MUTANTS_TIMEOUT = {mut["timeout"]}

/**
 * Мутанти, під які тестів не знайшлось узагалі. Не «вижили»: перевірку
 * навіть не пробували, і саме тому вони мусять стояти на екрані окремо --
 * вижилий каже «тут діра», а цей каже «сюди не дивились».
 */
export const MUTANTS_NO_TESTS = {mut["no_tests"]}

/**
 * mutmut 3 сам добирає тести під мутанта. Збитий мапінг тест-функція дає
 * ФАЛЬШИВЕ «вижив»: перевірка була можлива, просто її не запустили. Тому
 * підозрілі стоять окремим числом -- нуль тут щось означає лише тоді, коли
 * видно, що його рахували.
 */
export const MUTANTS_SUSPICIOUS = {mut["suspicious"]}

/** На скількох мутантах міряли частку «вбито асертом». */
export const MUTATION_SAMPLE = {kind["sample"]}

/**
 * Модулі контуру -- читаються з `only_mutate` у pyproject. Перелік, набраний
 * на сторінці руками, розходиться з контуром мовчки і саме тоді, коли туди
 * щось додали.
 */
export const MUTATION_CIRCUIT = {circuit_json}

/** Відсоток убитих від перевірених. */
export const MUTATION_SCORE = {mut["score"]}

/**
 * Частка вбивств, у яких мутанта спіймала перевірка ЗНАЧЕННЯ, а не виняток.
 *
 * Виміряно вибіркою ({kind["sample"]} мутантів, сід {kind["seed"]}): кожен
 * прогнано окремо тими самими тестами, які під нього відібрав mutmut, і
 * записано, ЧИМ саме впав перший тест. Виняток доводить, що мутант не
 * проходить мовчки, і не доводить, що результат перевірено.
 */
export const MUTATION_ASSERT_SHARE = {kind["share"]}

/** Коли прогін справді відбувся: мутації йдуть окремим контуром, не в CI на пуш. */
export const MUTATION_RAN_AT = '{mut["ran_at"]}'

/**
 * Стеля розходження: скільки рядків КОНТУРУ дозволено змінити, перш ніж
 * цифра визнається протухлою (`mutation_snapshot.py --drift`).
 *
 * Ворота стоять на ПУБЛІКАЦІЇ, не в CI (#66): у CI вони червонили б кожен
 * пуш після великого рефактора — доти, доки хтось не прожене мутації годину.
 *
 * Це і є максимальна відстань між відсотком вище і кодом, який зараз у гілці.
 * Саме число, а не «замір свіжий»: дата поруч із цифрою робить видимим лише
 * те, що на неї дивляться, — і одного разу вже не спрацювала.
 */
export const MUTATION_STALE_LINES = {stale}

/** Скільки разів поспіль мусив пройти сценарій, щоб зарахуватись (pass^k). */
export const PASSK_RUNS = {traps["runs"]}

/** Сценаріїв з пастками в наборі: правильна відповідь суперечить найочевиднішій. */
export const TRAPS_TOTAL = {traps_total(traps)}

/** Хто скільки з них тримає в УСІХ k прогонах, поіменно по моделях. */
export const PASSK_BY_MODEL = '{passk_line(traps)}'

/** Коли пастки справді ганялись: живий прогін моделі, не CI на пуш. */
export const PASSK_RAN_AT = '{traps["date"]}'

/**
 * Скільки промптів прив'язано до цього числа хешем (`agent/prompts.py`).
 *
 * Мутаційна цифра протухає від змін у КОНТУРІ й міряється рядками; ця — від
 * зміни самого ПРОМПТА, і рядки цього не бачать. Змінився текст — ворота
 * публікації спиняться, поки пастки не проженуть заново.
 */
export const PASSK_PROMPTS = {len(traps["prompts"])}

/**
 * Стеля цінової вилки авто-заміни в гривнях (`core.mandate.FORK_CAP`).
 *
 * Їде сюди, а не літералом у розмітці: гість читає це число в правилі, а
 * збирач -- у мандаті, і рахує його ОДИН модуль. Другий дім цьому числу
 * розійшовся б мовчки саме там, де його ніхто не звіряє (#90, #158).
 */
export const AUTO_SWAP_CAP_UAH = {int(FORK_CAP)}

/**
 * Фраза, з якої екран робить кнопку фокуса на поле «Додати ще»
 * (`core.cycles.ASK_NOTE`).
 *
 * Їде сюди, а не літералом у розмітці: підрядок шукається в реченні, яке
 * написав СЕРВЕР, і розбіжність на одну кому мовчки перетворює кнопку на
 * звичайний текст -- дорога в нікуди від зламаного інтерфейсу не
 * відрізняється (#364, #38, #158).
 */
export const ASK_PHRASE = {json.dumps(ASK_NOTE, ensure_ascii=False)}
"""


def main() -> int:
    content = bare(render())
    if "--check" in sys.argv:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if current != content:
            print(
                "facts.ts відстав від репозиторію. Перегенеруй: uv run python scripts/gen_facts.py",
                file=sys.stderr,
            )
            return 1
        print("facts.ts синхронний з репозиторієм")
        return 0
    TARGET.write_text(content, encoding="utf-8", newline="\n")
    print(f"записано {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
