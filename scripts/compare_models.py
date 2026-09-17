from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from pathlib import Path

import passk_snapshot

from komora import runtime
from komora.agent import prompts
from komora.agent.basket import pick_schema, pick_system
from komora.agent.llm import ModelError, build_llm
from komora.agent.nextlist import NEXT_SCHEMA, NEXT_SYSTEM
from komora.agent.occasion import OCCASION_SCHEMA, OCCASION_SYSTEM
from komora.agent.occasion import payload as occasion_payload
from komora.agent.plan import system_text as plan_system
from komora.agent.sanity import SANITY_SCHEMA, SANITY_SYSTEM
from komora.agent.skills import block
from komora.agent.understand import UNDERSTAND_SYSTEM
from komora.agent.understand import payload as understand_payload
from komora.config import settings
from komora.core.labels import labels, resolve
from komora.core.models import LUNA
from komora.core.occasion import occasion_of
from komora.core.plan import PLAN_SCHEMA, Aim
from komora.core.prompt import prune
from komora.core.skills import select
from komora.core.understanding import (
    PLAN_GATED,
    UNDERSTAND_QUESTIONS,
    UNDERSTAND_SCHEMA,
)

runtime.console()

SCHEMA = {
    "type": "object",
    "properties": {
        "chosen_id": {"type": "string"},
        "reason": {"type": "string"},
        "ask": {"type": ["string", "null"]},
    },
    "required": ["chosen_id", "reason"],
    "additionalProperties": False,
}

SYSTEM = (
    "Ти агент продуктового кошика. Відповідай ВИКЛЮЧНО українською. "
    "Поле chosen_id — САМЕ ЛИШЕ число артикулу, без префіксів і лапок. "
    "Поле reason — одне речення по суті. Ціни порівнюй полем «за_100г» — "
    "воно вже зведене до спільної одиниці; «ціна» у різних фасовках "
    "непорівнянна. Поле «прочитання» показує ІНШІ види, на які лягає те саме "
    "слово. Якщо прочитання справді різні наміри, історії гостя немає і його "
    "правила мовчать — постав питання: «ask» — одне коротке речення гостю, і "
    "тоді chosen_id лиши порожнім рядком. Не питай, коли вибір очевидний, коли "
    "є звичне з історії або коли намір гостя ВЖЕ називає вид («шашлик», «сир "
    "кисломолочний»): прочитання уточнює лише те, чого гість не сказав. "
    "Питання — це пауза в збірці."
)


@dataclass(frozen=True, slots=True)
class Scenario:
    key: str
    prompt: str
    check: Callable[[str, str], bool]
    note: str
    system: str | None = None
    schema: dict | None = None
    verdict: Callable[[dict], bool] | None = None
    marks: dict[str, str] | None = None
    shown: Callable[[dict], str] | None = None
    said: Callable[[dict], str] | None = None


def _digits(value: str) -> str:
    return "".join(c for c in value if c.isdigit())


BUDGET_PRICES = {
    "610001": 62.99,
    "610002": 38.99,
    "610003": 78.50,
    "610004": 319.00,
    "610005": 149.00,
    "610006": 159.00,
}

BUDGET_NAMED = ("молоко", "хліб", "яйця")

BUDGET_LIMIT = 500.0


def _labelled(asked: dict) -> tuple[dict, dict[str, str]]:
    marks = labels([str(intent["намір"]) for intent in asked["наміри"]])
    for intent in asked["наміри"]:
        intent["ключ"] = marks[str(intent["намір"])]
    return asked, {mark: name for name, mark in marks.items()}


def _by_intent(data: dict, of: dict[str, str]) -> dict[str, dict]:
    picked: dict[str, dict] = {}
    for pick in data.get("picks") or []:
        name = resolve(str(pick.get("intent", "")), of)
        if name is not None:
            picked[name] = pick
    return picked


def _budget_ok(data: dict) -> bool:
    picks = {
        intent: pick
        for intent, pick in _by_intent(data, BUDGET_MARKS).items()
        if str(pick.get("chosen_id") or "").strip()
    }
    if not set(BUDGET_NAMED) <= set(picks):
        return False

    def cost(intent: str) -> float:
        pick = picks[intent]
        price = BUDGET_PRICES.get(_digits(str(pick.get("chosen_id"))), 0.0)
        return price * max(1, int(pick.get("qty") or 1))

    kept = set(picks)
    total = sum(cost(intent) for intent in kept)
    for item in data.get("expendable") or []:
        if total <= BUDGET_LIMIT:
            break
        intent = resolve(str(item.get("intent", "")), BUDGET_MARKS)
        if intent is None or intent not in kept or intent in BUDGET_NAMED:
            continue
        kept.discard(intent)
        total -= cost(intent)
    return total <= BUDGET_LIMIT and "кава" in kept


def _budget_intent(
    name: str,
    source: str,
    pid: str,
    title: str,
    per_100g: float | None,
    stock: int,
    receipts: int | None = None,
    recent: int = 0,
) -> dict:
    return {
        "намір": name,
        "ключ": "",
        "джерело": source,
        "кандидати": [
            {
                "id": pid,
                "назва": title,
                "ціна": BUDGET_PRICES[pid],
                "стара_ціна": None,
                "залишок": stock,
                "за_100г": per_100g,
                "оброблене": None,
            }
        ],
        "з_історії": None
        if receipts is None
        else [
            {
                "назва": title,
                "артикул": pid,
                "чеків_усього": receipts,
                "чеків_за_90_днів": recent,
                "звична_кількість": 1,
            }
        ],
    }


BUDGET_ASKED, BUDGET_MARKS = _labelled(
    {
        "правила_гостя": None,
        "межа_кошика": BUDGET_LIMIT,
        "наміри": [
            _budget_intent(
                "молоко",
                "список гостя",
                "610001",
                "Молоко Ферма 2,5% 900 г",
                7.0,
                20,
                receipts=12,
                recent=5,
            ),
            _budget_intent(
                "хліб",
                "список гостя",
                "610002",
                "Хліб Рум'янець цільнозерновий 400 г",
                9.75,
                15,
            ),
            _budget_intent("яйця", "список гостя", "610003", "Яйця курячі С0, 10 шт", None, 30),
            _budget_intent(
                "кава",
                "потреби з циклів",
                "610004",
                "Кава в зернах Lavazza Crema e Gusto 1 кг",
                31.9,
                6,
                receipts=14,
                recent=6,
            ),
            _budget_intent(
                "сир", "потреби з циклів", "610005", "Сир Гауда 45% 250 г", 59.6, 8, receipts=2
            ),
            _budget_intent(
                "оливкова олія",
                "потреби з циклів",
                "610006",
                "Олія оливкова Monini Classico 500 мл",
                31.8,
                4,
                receipts=1,
            ),
        ],
    }
)


_EVENT_PRICES = {"701": 2299.0, "702": 419.0, "703": 189.0}


def _event_candidate(pid: str, title: str, per_100g: float) -> dict:
    return {
        "id": pid,
        "назва": title,
        "ціна": _EVENT_PRICES[pid],
        "стара_ціна": None,
        "залишок": 12,
        "фасовка": "0.75л",
        "за_100г": per_100g,
    }


def _event_budget_asked(limit: float | None) -> dict:
    return {
        "правила_гостя": None,
        "межа_кошика": limit,
        "привід": "гості, 6 людей",
        "що_означає_привід": (
            "До гостей: докинь закуски, напої і більше хліба. Швидкопсувне з "
            "потреб лишається як є — гості його і з'їдять."
        ),
        "наміри": [
            {
                "намір": "шампанське",
                "ключ": "",
                "джерело": "привід",
                "кандидати": [
                    _event_candidate("701", "Шампанське Prestige des Sacres Brut", 306.5),
                    _event_candidate("702", "Шампанське Canard-Duchene Authentic Brut", 55.9),
                    _event_candidate("703", "Шампанське Veuve Doussot Tradition Brut", 25.2),
                ],
            }
        ],
    }


def _event_budget_ok(data: dict) -> bool:
    picks = data.get("picks") or []
    if len(picks) != 1:
        return False
    return _digits(str(picks[0].get("chosen_id"))) in {"702", "703"}


def _event_free_ok(data: dict) -> bool:
    picks = data.get("picks") or []
    if len(picks) != 1 or picks[0].get("ask"):
        return False
    return _digits(str(picks[0].get("chosen_id"))) in _EVENT_PRICES


KIND_ASKED, KIND_MARKS = _labelled(
    {
        "правила_гостя": None,
        "наміри": [
            {
                "намір": "Рулет курячий домашній в/с Алан",
                "джерело": "потреби з циклів",
                "кандидати": [
                    {
                        "id": "901",
                        "назва": "Рулет Делікатесний рибний холодного копчення",
                        "ціна": 479.7,
                        "залишок": 12,
                        "фасовка": "300г",
                        "за_100г": 159.9,
                    },
                    {
                        "id": "902",
                        "назва": "Рулет бісквітний Полуниця з вершками",
                        "ціна": 64.99,
                        "залишок": 30,
                        "фасовка": "200г",
                        "за_100г": 32.5,
                    },
                    {
                        "id": "903",
                        "назва": "Рулет вафельний з какао",
                        "ціна": 39.99,
                        "залишок": 40,
                        "фасовка": "180г",
                        "за_100г": 22.2,
                    },
                ],
                "з_історії": [
                    {
                        "назва": "Рулет курячий домашній в/с Алан",
                        "артикул": "700900",
                        "чеків_усього": 6,
                        "чеків_за_90_днів": 2,
                        "звична_кількість": 1,
                    }
                ],
            }
        ],
    }
)
KIND_PROMPT = json.dumps(prune(KIND_ASKED), ensure_ascii=False)


def _kind_ok(data: dict) -> bool:
    picks = list(_by_intent(data, KIND_MARKS).values())
    if not picks:
        return not (data.get("picks") or [])
    return not str(picks[0].get("chosen_id") or "").strip()


BRAND_SPRITE = "802"
BRAND_TRAPS = {"801": "кола", "803": "вода"}

BRAND_ASKED, BRAND_MARKS = _labelled(
    {
        "правила_гостя": None,
        "межа_кошика": None,
        "наміри": [
            {
                "намір": "Спрайт",
                "джерело": "список гостя",
                "кандидати": [
                    {
                        "id": "801",
                        "назва": "Напій Coca-Cola Classic з/б 0,33 л",
                        "ціна": 29.99,
                        "стара_ціна": 34.99,
                        "залишок": 40,
                        "за_100г": 9.09,
                        "оброблене": None,
                    },
                    {
                        "id": BRAND_SPRITE,
                        "назва": "Напій Sprite 0,5 л",
                        "ціна": 32.99,
                        "стара_ціна": None,
                        "залишок": 12,
                        "за_100г": 6.60,
                        "оброблене": None,
                    },
                    {
                        "id": "803",
                        "назва": "Вода Bonaqua негазована 1,5 л",
                        "ціна": 24.99,
                        "стара_ціна": None,
                        "залишок": 50,
                        "за_100г": 1.67,
                        "оброблене": None,
                    },
                ],
                "з_історії": None,
            }
        ],
    }
)
BRAND_PROMPT = json.dumps(prune(BRAND_ASKED), ensure_ascii=False)


def _brand_ok(data: dict) -> bool:
    by_intent = _by_intent(data, BRAND_MARKS)
    if len(by_intent) != 1:
        return False
    pick = next(iter(by_intent.values()))
    if _digits(str(pick.get("chosen_id") or "")) != BRAND_SPRITE:
        return False
    axis = str(pick.get("swap") or "").casefold()
    return not any(trap in axis for trap in BRAND_TRAPS.values())


PORK_RAW = "350487"
PORK_ASKED, PORK_MARKS = _labelled(
    {
        "правила_гостя": None,
        "наміри": [
            {
                "намір": "свинина",
                "джерело": "список гостя",
                "кандидати": [
                    {
                        "id": "350001",
                        "назва": "Свинячі реберця PREMIA в маринаді",
                        "ціна": 249.0,
                        "залишок": 8,
                        "фасовка": "1000г",
                        "за_100г": 24.9,
                        "оброблене": ["М'ясо для шашлику та барбекю"],
                    },
                    {
                        "id": "350002",
                        "назва": "Шашличні ковбаски гриль",
                        "ціна": 199.0,
                        "залишок": 5,
                        "фасовка": "400г",
                        "за_100г": 49.7,
                        "оброблене": ["Другі страви"],
                    },
                    {
                        "id": PORK_RAW,
                        "назва": "Свинячий окіст для шніцеля охолоджений",
                        "ціна": 272.0,
                        "залишок": 6,
                        "фасовка": "1000г",
                        "за_100г": 27.2,
                    },
                ],
                "з_історії": None,
            }
        ],
    }
)
PORK_PROMPT = json.dumps(prune(PORK_ASKED), ensure_ascii=False)

RAW_ASKED, RAW_MARKS = _labelled(
    {
        "правила_гостя": None,
        "наміри": [
            {
                "намір": "свинина",
                "джерело": "список гостя",
                "уточнення_гостя": "свинина сира",
                "кандидати": [
                    {
                        "id": "351001",
                        "назва": "Шашлик зі свинини Соковитий у маринаді",
                        "ціна": 199.0,
                        "залишок": 8,
                        "фасовка": "1000г",
                        "за_100г": 19.9,
                        "оброблене": ["М'ясо для шашлику та барбекю"],
                    },
                    {
                        "id": "351002",
                        "назва": "Сало свиняче бутербродне з часником",
                        "ціна": 149.0,
                        "залишок": 12,
                        "фасовка": "300г",
                        "за_100г": 49.6,
                        "оброблене": ["Другі страви"],
                    },
                    {
                        "id": "351003",
                        "назва": "Ковбаски шашличні гриль зі свинини",
                        "ціна": 189.0,
                        "залишок": 5,
                        "фасовка": "400г",
                        "за_100г": 47.2,
                        "оброблене": ["Другі страви"],
                    },
                ],
                "з_історії": None,
            }
        ],
    }
)
RAW_PROMPT = json.dumps(prune(RAW_ASKED), ensure_ascii=False)


def _raw_ok(data: dict) -> bool:
    picks = list(_by_intent(data, RAW_MARKS).values())
    if not picks:
        return not (data.get("picks") or [])
    return not str(picks[0].get("chosen_id") or "").strip()


OPTIONS_ASKED, OPTIONS_MARKS = _labelled(
    {
        "правила_гостя": None,
        "наміри": [
            {
                "намір": "сир",
                "джерело": "список гостя",
                "прочитання": ["Сири", "Сир кисломолочний"],
                "кандидати": [
                    {
                        "id": "410001",
                        "назва": "Сир Гауда 45%",
                        "ціна": 99.0,
                        "залишок": 12,
                        "фасовка": "100г",
                        "за_100г": 99.0,
                    },
                    {
                        "id": "410002",
                        "назва": "Сир кисломолочний Яготинський 5%",
                        "ціна": 49.99,
                        "залишок": 20,
                        "фасовка": "180г",
                        "за_100г": 27.8,
                    },
                ],
                "з_історії": None,
            }
        ],
    }
)
OPTIONS_PROMPT = json.dumps(prune(OPTIONS_ASKED), ensure_ascii=False)


def _options_ok(data: dict) -> bool:
    picks = list(_by_intent(data, OPTIONS_MARKS).values())
    if len(picks) != 1 or not str(picks[0].get("ask") or "").strip():
        return False
    options = [" ".join(str(item).split()).casefold() for item in picks[0].get("ask_options") or []]
    if not 2 <= len(options) <= 4:
        return False
    return all(option and option != "сир" for option in options)


def _skill_case(
    asked: dict, *, occasion_mode: str = "", with_queue: bool = False
) -> tuple[str, str, dict[str, str]]:
    labelled, marks = _labelled(asked)
    intents = [str(intent["намір"]) for intent in labelled["наміри"]]
    own = {
        str(hint["артикул"])
        for intent in labelled["наміри"]
        for hint in intent.get("з_історії") or []
    }
    chosen = select(
        [str(rule) for rule in (labelled.get("правила_гостя") or [])],
        occasion_mode=occasion_mode,
        occasion_phrase=str(labelled.get("привід") or ""),
        intents=intents,
        promo_kinds=sum(
            1
            for intent in labelled["наміри"]
            for hint in intent.get("з_історії") or []
            if hint.get("акційна_звичка")
        ),
        promo_on_shelf=any(
            card.get("стара_ціна") and str(card["id"]) in own
            for intent in labelled["наміри"]
            for card in intent.get("кандидати") or []
        ),
        shelf={
            str(intent["намір"]): [str(card["назва"]) for card in intent.get("кандидати") or []]
            for intent in labelled["наміри"]
        },
    )
    return (
        json.dumps(prune(labelled), ensure_ascii=False),
        pick_system(with_queue=with_queue, skills=block(chosen.skills)),
        marks,
    )


EVENT_BUDGET_PROMPT, EVENT_BUDGET_SYSTEM, EVENT_BUDGET_MARKS = _skill_case(
    _event_budget_asked(1500.0), occasion_mode="event", with_queue=True
)
EVENT_FREE_PROMPT, EVENT_FREE_SYSTEM, EVENT_FREE_MARKS = _skill_case(
    _event_budget_asked(None), occasion_mode="event"
)

BUDGET_PROMPT, BUDGET_SYSTEM, _BUDGET_SKILL_MARKS = _skill_case(BUDGET_ASKED, with_queue=True)


def _chose(data: dict, marks: dict[str, str], intent: str) -> str:
    picks = _by_intent(data, marks)
    return _digits(str((picks.get(intent) or {}).get("chosen_id") or ""))


PROMO_PICK = "950001"
PROMO_ASKED = {
    "правила_гостя": None,
    "наміри": [
        {
            "намір": "пиво світле",
            "джерело": "потреби з циклів",
            "кандидати": [
                {
                    "id": "950002",
                    "назва": "Пиво Оболонь Світле 0,5 л",
                    "ціна": 32.99,
                    "стара_ціна": None,
                    "залишок": 25,
                    "фасовка": "0.5л",
                    "за_100г": 6.60,
                },
                {
                    "id": PROMO_PICK,
                    "назва": "Пиво Hike Світле 0,5 л",
                    "ціна": 41.99,
                    "стара_ціна": 61.99,
                    "залишок": 30,
                    "фасовка": "0.5л",
                    "за_100г": 8.40,
                },
            ],
            "з_історії": [
                {
                    "назва": "Пиво Оболонь Світле 0,5 л",
                    "артикул": "950002",
                    "чеків_усього": 9,
                    "чеків_за_90_днів": 4,
                    "звична_кількість": 1,
                    "акційна_звичка": None,
                },
                {
                    "назва": "Пиво Hike Світле 0,5 л",
                    "артикул": PROMO_PICK,
                    "чеків_усього": 5,
                    "чеків_за_90_днів": 2,
                    "звична_кількість": 6,
                    "акційна_звичка": "береш по акції: 4 з 5, зазвичай по 6",
                },
            ],
        }
    ],
}
PROMO_PROMPT, PROMO_SYSTEM, PROMO_MARKS = _skill_case(PROMO_ASKED)

PROMO_WAIT_ASKED = {
    "правила_гостя": None,
    "наміри": [
        {
            "намір": "пиво світле",
            "джерело": "потреби з циклів",
            "кандидати": [
                {
                    "id": PROMO_PICK,
                    "назва": "Пиво Hike Світле 0,5 л",
                    "ціна": 61.99,
                    "стара_ціна": None,
                    "залишок": 30,
                    "фасовка": "0.5л",
                    "за_100г": 12.40,
                },
                {
                    "id": "950002",
                    "назва": "Пиво Оболонь Світле 0,5 л",
                    "ціна": 32.99,
                    "стара_ціна": None,
                    "залишок": 25,
                    "фасовка": "0.5л",
                    "за_100г": 6.60,
                },
            ],
            "з_історії": [
                {
                    "назва": "Пиво Hike Світле 0,5 л",
                    "артикул": PROMO_PICK,
                    "чеків_усього": 5,
                    "чеків_за_90_днів": 2,
                    "звична_кількість": 6,
                    "акційна_звичка": "береш по акції: 4 з 5, зазвичай по 6",
                }
            ],
        }
    ],
}
PROMO_WAIT_PROMPT, PROMO_WAIT_SYSTEM, PROMO_WAIT_MARKS = _skill_case(PROMO_WAIT_ASKED)

PACK_ASKED = {
    "правила_гостя": ["тільки упаковка 100 г"],
    "наміри": [
        {
            "намір": "сир твердий",
            "джерело": "список гостя",
            "кандидати": [
                {
                    "id": "960001",
                    "назва": "Сир Гауда 45% нарізка",
                    "ціна": 169.00,
                    "залишок": 12,
                    "фасовка": "250г",
                    "за_100г": 67.60,
                },
                {
                    "id": "960002",
                    "назва": "Сир Гауда 45%",
                    "ціна": 79.99,
                    "залишок": 20,
                    "фасовка": "100г",
                    "за_100г": 79.99,
                },
                {
                    "id": "960003",
                    "назва": "Сир Гауда 45% брусок",
                    "ціна": 249.00,
                    "залишок": 6,
                    "фасовка": "400г",
                    "за_100г": 62.25,
                },
            ],
            "з_історії": None,
        },
        {
            "намір": "масло",
            "джерело": "список гостя",
            "кандидати": [
                {
                    "id": "960011",
                    "назва": "Масло солодковершкове 82%",
                    "ціна": 109.00,
                    "залишок": 15,
                    "фасовка": "200г",
                    "за_100г": 54.50,
                },
                {
                    "id": "960012",
                    "назва": "Масло селянське 73%",
                    "ціна": 199.00,
                    "залишок": 8,
                    "фасовка": "400г",
                    "за_100г": 49.75,
                },
            ],
            "з_історії": None,
        },
    ],
}
PACK_PROMPT, PACK_SYSTEM, PACK_MARKS = _skill_case(PACK_ASKED)

CONTAINER_GLASS = "970002"
CONTAINER_ASKED = {
    "правила_гостя": ["пиво тільки в скляній пляшці"],
    "наміри": [
        {
            "намір": "пиво",
            "джерело": "список гостя",
            "кандидати": [
                {
                    "id": "970001",
                    "назва": "Пиво Стела Артуа світле з/б 0,5 л",
                    "ціна": 39.99,
                    "залишок": 40,
                    "фасовка": "0.5л",
                    "за_100г": 8.00,
                },
                {
                    "id": CONTAINER_GLASS,
                    "назва": "Пиво Стела Артуа світле скляна пляшка 0,5 л",
                    "ціна": 44.99,
                    "залишок": 18,
                    "фасовка": "0.5л",
                    "за_100г": 9.00,
                },
                {
                    "id": "970003",
                    "назва": "Пиво Чернігівське світле ПЕТ 1 л",
                    "ціна": 34.99,
                    "залишок": 25,
                    "фасовка": "1л",
                    "за_100г": 3.50,
                },
            ],
            "з_історії": None,
        },
        {
            "намір": "яйця",
            "джерело": "список гостя",
            "кандидати": [
                {
                    "id": "970011",
                    "назва": "Яйця курячі С0",
                    "ціна": 78.50,
                    "залишок": 30,
                    "фасовка": "10шт",
                },
                {
                    "id": "970012",
                    "назва": "Яйця курячі С1",
                    "ціна": 68.50,
                    "залишок": 22,
                    "фасовка": "10шт",
                },
            ],
            "з_історії": None,
        },
    ],
}
CONTAINER_PROMPT, CONTAINER_SYSTEM, CONTAINER_MARKS = _skill_case(CONTAINER_ASKED)

EVENT_READY = "700002"
EVENT_ASKED = {
    "правила_гостя": None,
    "привід": "гості, 6 людей",
    "що_означає_привід": (
        "До гостей: докинь закуски, напої і більше хліба. Швидкопсувне з "
        "потреб лишається як є — гості його і з'їдять."
    ),
    "наміри": [
        {
            "намір": "закуски до столу",
            "джерело": "привід",
            "кандидати": [
                {
                    "id": "700001",
                    "назва": "Сир камамбер для запікання",
                    "ціна": 149.00,
                    "залишок": 9,
                    "фасовка": "125г",
                    "за_100г": 119.20,
                },
                {
                    "id": EVENT_READY,
                    "назва": "Сет снеків до пива: чипси, сухарики, арахіс",
                    "ціна": 189.00,
                    "залишок": 14,
                    "фасовка": "300г",
                    "за_100г": 63.00,
                    "оброблене": ["Готові страви"],
                },
                {
                    "id": "700003",
                    "назва": "Картопля молода",
                    "ціна": 39.99,
                    "залишок": 50,
                    "фасовка": "1кг",
                    "за_100г": 4.00,
                },
            ],
            "з_історії": [
                {
                    "назва": "Піца Rimini Пепероні",
                    "артикул": "700900",
                    "чеків_усього": 6,
                    "чеків_за_90_днів": 3,
                    "звична_кількість": 2,
                },
                {
                    "назва": "Чипси Lay's з сіллю",
                    "артикул": "700901",
                    "чеків_усього": 9,
                    "чеків_за_90_днів": 5,
                    "звична_кількість": 2,
                },
            ],
        }
    ],
}
EVENT_PROMPT, EVENT_SYSTEM, EVENT_MARKS = _skill_case(EVENT_ASKED, occasion_mode="event")

KIDS_JUICE = "800002"
KIDS_ASKED = {
    "правила_гостя": ["купи щось смачненьке для дитини"],
    "наміри": [
        {
            "намір": "напій",
            "джерело": "список гостя",
            "кандидати": [
                {
                    "id": "800001",
                    "назва": "Напій енергетичний Burn Original",
                    "ціна": 45.99,
                    "залишок": 30,
                    "фасовка": "0.5л",
                    "за_100г": 9.20,
                },
                {
                    "id": KIDS_JUICE,
                    "назва": "Сік Sandora яблучний для дітей",
                    "ціна": 24.99,
                    "залишок": 40,
                    "фасовка": "0.2л",
                    "за_100г": 12.50,
                },
                {
                    "id": "800003",
                    "назва": "Кава холодна Nescafe Latte",
                    "ціна": 39.99,
                    "залишок": 20,
                    "фасовка": "0.25л",
                    "за_100г": 16.00,
                },
            ],
            "з_історії": [
                {
                    "назва": "Кава холодна Nescafe Latte",
                    "артикул": "800003",
                    "чеків_усього": 12,
                    "чеків_за_90_днів": 6,
                    "звична_кількість": 2,
                }
            ],
        }
    ],
}
KIDS_PROMPT, KIDS_SYSTEM, KIDS_MARKS = _skill_case(KIDS_ASKED)

LIMITS_SAFE = "410009"
LIMITS_ASKED = {
    "правила_гостя": ["без лактози"],
    "наміри": [
        {
            "намір": "сир",
            "джерело": "список гостя",
            "кандидати": [
                {
                    "id": "410002",
                    "назва": "Сир кисломолочний Яготинський 5%",
                    "ціна": 49.99,
                    "залишок": 20,
                    "фасовка": "180г",
                    "за_100г": 27.77,
                },
                {
                    "id": LIMITS_SAFE,
                    "назва": "Продукт сирний рослинний безлактозний",
                    "ціна": 89.99,
                    "залишок": 7,
                    "фасовка": "200г",
                    "за_100г": 45.00,
                },
            ],
            "з_історії": [
                {
                    "назва": "Сир кисломолочний Яготинський 5%",
                    "артикул": "410002",
                    "чеків_усього": 14,
                    "чеків_за_90_днів": 6,
                    "звична_кількість": 1,
                }
            ],
        },
        {
            "намір": "молоко",
            "джерело": "список гостя",
            "кандидати": [
                {
                    "id": "410021",
                    "назва": "Молоко Ферма 2,5%",
                    "ціна": 53.49,
                    "залишок": 30,
                    "фасовка": "900г",
                    "за_100г": 5.94,
                },
                {
                    "id": "410022",
                    "назва": "Молоко Селянське 1%",
                    "ціна": 47.99,
                    "залишок": 25,
                    "фасовка": "900г",
                    "за_100г": 5.33,
                },
            ],
            "з_історії": None,
        },
    ],
}
LIMITS_PROMPT, LIMITS_SYSTEM, LIMITS_MARKS = _skill_case(LIMITS_ASKED)

BRAND_NAMED = "830002"
BRAND_SKILL_ASKED = {
    "правила_гостя": None,
    "наміри": [
        {
            "намір": "Моршинська",
            "джерело": "список гостя",
            "кандидати": [
                {
                    "id": "830001",
                    "назва": "Вода Bonaqua негазована",
                    "ціна": 24.99,
                    "стара_ціна": 34.99,
                    "залишок": 50,
                    "фасовка": "1.5л",
                    "за_100г": 1.67,
                },
                {
                    "id": BRAND_NAMED,
                    "назва": "Вода Моршинська негазована",
                    "ціна": 21.99,
                    "стара_ціна": None,
                    "залишок": 16,
                    "фасовка": "0.5л",
                    "за_100г": 4.40,
                },
            ],
            "з_історії": None,
        }
    ],
}
BRAND_SKILL_PROMPT, BRAND_SKILL_SYSTEM, BRAND_SKILL_MARKS = _skill_case(BRAND_SKILL_ASKED)

THRIFT_PICK = "840201"
THRIFT_OLIVE = (THRIFT_PICK, "840203")
THRIFT_ASKED = {
    "правила_гостя": ["бери дешевше"],
    "наміри": [
        {
            "намір": "оливкова олія",
            "джерело": "список гостя",
            "кандидати": [
                {
                    "id": THRIFT_PICK,
                    "назва": "Олія оливкова Monini Classico",
                    "ціна": 319.00,
                    "залишок": 12,
                    "фасовка": "500мл",
                    "за_100г": 63.80,
                },
                {
                    "id": "840202",
                    "назва": "Олія соняшникова Олейна рафінована",
                    "ціна": 89.99,
                    "залишок": 40,
                    "фасовка": "900мл",
                    "за_100г": 10.00,
                },
                {
                    "id": "840203",
                    "назва": "Олія оливкова Ideal Extra Virgin",
                    "ціна": 189.00,
                    "залишок": 8,
                    "фасовка": "250мл",
                    "за_100г": 75.60,
                },
            ],
            "з_історії": None,
        }
    ],
}
THRIFT_PROMPT, THRIFT_SYSTEM, THRIFT_MARKS = _skill_case(THRIFT_ASKED)


EVENT_REGULAR = ("корм", "папір", "порошок")
EVENT_TABLE = ("сир твердий", "ковбаса")
EVENT_NEEDS = [
    "Корм для котів Whiskas з куркою",
    "Папір туалетний Zewa Deluxe",
    "Порошок пральний Ariel Color",
    "Сир твердий Гауда",
    "Ковбаса салямі Фінська",
]
EVENT_HABITS = [
    ("Корм для котів Whiskas з куркою", 14),
    ("Папір туалетний Zewa Deluxe", 9),
    ("Сир твердий Гауда", 7),
    ("Чипси Lays з паприкою", 5),
    ("Вино червоне сухе", 4),
    ("Порошок пральний Ariel Color", 3),
]
OCCASION_PROMPT = occasion_payload(
    occasion_of("event", 4),
    intents=EVENT_NEEDS,
    habits=EVENT_HABITS,
)


def _named(data: dict, field: str) -> list[str]:
    return [str(item.get("intent") or "").casefold() for item in data.get(field) or []]


def _event_ok(data: dict) -> bool:
    skipped = _named(data, "skip")
    return all(any(word in name for name in skipped) for word in EVENT_REGULAR) and not any(
        any(word in name for word in EVENT_TABLE) for name in skipped
    )


UNDERSTAND_REGULAR = ("корм", "папір", "порошок")


def _understand(occasion, *, intents, said=(), typed="", known=(), tracked=0):
    return understand_payload(
        occasion,
        intents=list(intents),
        said=list(said),
        typed=typed,
        rules=(),
        known=list(known),
        tracked=tracked,
        wanted=(),
        steps=sorted(PLAN_GATED),
    )


def _asks(data: dict) -> list[str]:
    return [str(item.get("ask") or "").casefold() for item in data.get("questions") or []]


def _cuts(data: dict) -> list[str]:
    return [name.casefold() for value in (data.get("cut") or []) if (name := str(value).strip())]


def _cut_said(data: dict) -> str:
    return " | ".join(_cuts(data))


def _adds(data: dict) -> list[str]:
    return [str(item.get("intent") or "").casefold() for item in data.get("add") or []]


def _styles(data: dict) -> set[str]:
    return {
        str(option.get("style") or "")
        for item in data.get("questions") or []
        for option in item.get("options") or []
    }


def _shown(data: dict) -> str:
    asked = "; ".join(_asks(data)) or "нічого"
    styles = ", ".join(sorted(_styles(data) - {""})) or "немає"
    return f"стилі: {styles} | докидає: {', '.join(_adds(data)) or 'нічого'} | питає: {asked}"


def _said(data: dict) -> str:
    return " ".join(
        [str(item.get("why") or "") for item in (data.get("add") or []) + (data.get("drop") or [])]
        + [
            f"{item.get('ask') or ''} "
            + " ".join(str(o.get("label") or "") for o in item.get("options") or [])
            for item in data.get("questions") or []
        ]
    )


EVENT_TABLE_INTENTS = [
    "Корм для котів Whiskas з куркою",
    "Папір туалетний Zewa Deluxe",
    "Сир твердий Гауда",
]
UNDERSTAND_EVENT = _understand(
    occasion_of("event", 4),
    intents=EVENT_TABLE_INTENTS,
    known=EVENT_TABLE_INTENTS,
    tracked=18,
)


def _event_dialog_ok(data: dict) -> bool:
    asks = _asks(data)
    adds = _adds(data)
    return (
        {"cooking", "ready"} <= _styles(data)
        and not any("скільки" in ask and "люд" in ask for ask in asks)
        and bool(adds)
        and not any(word in name for name in adds for word in UNDERSTAND_REGULAR)
    )


UNDERSTAND_LIST = _understand(
    occasion_of("list", None),
    intents=["молоко", "хліб", "яйця"],
    said=["молоко", "хліб", "яйця"],
)

UNDERSTAND_KNOWN = _understand(
    occasion_of("week", None),
    intents=["Хліб Київський", "Молоко Ферма 2,5%"],
    known=["Хліб Київський", "Молоко Ферма 2,5%"],
    tracked=24,
)

UNDERSTAND_CUT_ONE = _understand(
    occasion_of("list", None),
    intents=["морозиво", "хрещатик", "фісташка"],
    said=["морозиво", "хрещатик", "фісташка"],
    typed="морозиво, хрещатик, фісташка",
)

UNDERSTAND_CUT_MANY = _understand(
    occasion_of("list", None),
    intents=["хліб молоко чай"],
    said=["хліб молоко чай"],
    typed="хліб молоко чай",
)

UNDERSTAND_CUT_JUNK = _understand(
    occasion_of("list", None),
    intents=["привіт", "купи будь ласка молока і хліба", "0501234567", "дякую"],
    said=["привіт", "купи будь ласка молока і хліба", "0501234567", "дякую"],
    typed="Привіт! Купи, будь ласка, молока і хліба. 0501234567. Дякую",
)

UNDERSTAND_MANY = _understand(
    occasion_of("event", 6),
    intents=["сир", "риба", "рулет", "сендвіч", "філе"],
    known=["сир", "риба", "рулет", "сендвіч", "філе"],
    tracked=31,
)


NEXT_LIST_ROWS = {
    "хліб": "закінчилось сьогодні",
    "молоко": "закінчиться за 2 дн — до наступного походу",
    "сир твердий гауда": "майже закінчилось: лишилось ~1 дн",
    "сир твердий едам": "майже закінчилось: лишилось ~1 дн",
    "пиво": "береш це по акції — без знижки не бери",
}
NEXT_LIST_PROMPT = json.dumps(
    {
        "види": [
            {"key": key, "назва": key.capitalize(), "підстава": why}
            for key, why in NEXT_LIST_ROWS.items()
        ]
    },
    ensure_ascii=False,
)


SENSE_LABELS: dict[str, dict[str, object]] = {
    "морозиво": {"lies": True, "unit": "г", "low": 10, "high": 600},
    "порошок пральний": {"lies": False, "unit": "г", "low": 1, "high": 300},
    "паляничка": {"unit": "г", "low": 30, "high": 800},
    "вода питна": {"unit": "г", "low": 300, "high": 5000},
}
SENSE_PROMPT = json.dumps({"види": list(SENSE_LABELS)}, ensure_ascii=False)


def _sense_rows(data: dict) -> list[dict]:
    return [item for item in (data.get("kinds") or []) if isinstance(item, dict)]


def _sense_ok(data: dict) -> bool:
    said = {str(item.get("label") or ""): item for item in _sense_rows(data)}
    if set(said) != set(SENSE_LABELS):
        return False
    for label, want in SENSE_LABELS.items():
        item = said[label]
        if not str(item.get("sanity") or "").strip():
            return False
        if "lies" in want and bool(item.get("rhythm_lies")) is not want["lies"]:
            return False
        if item.get("per_day_unit") != want["unit"]:
            return False
        try:
            per_day = float(item.get("per_day"))
        except TypeError, ValueError:
            return False
        if not (float(want["low"]) <= per_day <= float(want["high"])):
            return False
    return True


def _sense_shown(data: dict) -> str:
    return (
        ", ".join(
            f"{item.get('label') or '?'}={item.get('per_day')}{item.get('per_day_unit') or '?'}"
            f"/{'бреше' if item.get('rhythm_lies') else 'рівно'}"
            for item in _sense_rows(data)
        )
        or "нічого"
    )


def _sense_said(data: dict) -> str:
    return " ".join(str(item.get("sanity") or "") for item in _sense_rows(data))


def _next_list_rows(data: dict) -> list[dict]:
    return [item for item in (data.get("list") or []) if isinstance(item, dict)]


def _next_list_ok(data: dict) -> bool:
    rows = _next_list_rows(data)
    keys = [str(item.get("key") or "") for item in rows]
    if not keys or any(key not in NEXT_LIST_ROWS for key in keys):
        return False
    if any(need not in keys for need in ("хліб", "молоко", "пиво")):
        return False
    beer = next(item for item in rows if item.get("key") == "пиво")
    if "акці" not in str(beer.get("why") or "").casefold():
        return False
    return sum(1 for key in keys if key.startswith("сир твердий")) <= 1


def _next_list_shown(data: dict) -> str:
    return ", ".join(str(item.get("key") or "?") for item in _next_list_rows(data)) or "нічого"


def _next_list_said(data: dict) -> str:
    return " ".join(str(item.get("why") or "") for item in _next_list_rows(data))


@cache
def _tools_snapshot() -> tuple[dict, ...]:
    path = Path(__file__).resolve().parents[1] / "docs" / "mcp-tools.json"
    return tuple(json.loads(path.read_text(encoding="utf-8"))) if path.is_file() else ()


def _pantry_system(state: dict[str, int]) -> str:
    return plan_system(aim=Aim.PANTRY, tools=_tools_snapshot(), state=state)[1]


def _pantry_task(state: dict[str, int]) -> str:
    return json.dumps(
        {
            "задача": "доведи стан дому: кожен рядок каже число або речення",
            "джерело": "наміри (список, чеки, комора)",
            "записати в кошик": False,
            "є межа суми": False,
            "уже відомо": ["history", "orders", "pantry", "receipts"],
            "стан": state,
        },
        ensure_ascii=False,
    )


PANTRY_STATES: dict[str, dict[str, int]] = {
    "COLD": {
        "рядків": 40,
        "без мітки виду": 40,
        "міток виду": 0,
        "без числа і без речення": 31,
        "без вироку про ритм": 0,
        "без стелі зберігання": 0,
        "просять слова гостя": 0,
        "дописано руками": 0,
        "чеків прочитано": 118,
    },
    "WARM": {
        "рядків": 40,
        "без мітки виду": 0,
        "міток виду": 40,
        "без числа і без речення": 0,
        "без вироку про ритм": 0,
        "без стелі зберігання": 0,
        "просять слова гостя": 0,
        "дописано руками": 0,
        "чеків прочитано": 118,
    },
    "EMPTY": {
        "рядків": 0,
        "без мітки виду": 0,
        "міток виду": 0,
        "без числа і без речення": 0,
        "без вироку про ритм": 0,
        "без стелі зберігання": 0,
        "просять слова гостя": 0,
        "дописано руками": 0,
        "чеків прочитано": 0,
    },
    "MUTE": {
        "рядків": 40,
        "без мітки виду": 0,
        "міток виду": 40,
        "без числа і без речення": 26,
        "без вироку про ритм": 26,
        "без стелі зберігання": 0,
        "просять слова гостя": 12,
        "дописано руками": 0,
        "чеків прочитано": 118,
    },
}

PANTRY_COLD = _pantry_task(PANTRY_STATES["COLD"])
PANTRY_WARM = _pantry_task(PANTRY_STATES["WARM"])
PANTRY_MUTE = _pantry_task(PANTRY_STATES["MUTE"])
PANTRY_EMPTY = _pantry_task(PANTRY_STATES["EMPTY"])


def _plan_steps(data: dict) -> list[str]:
    rows = data.get("steps") or []
    return [str(row.get("step") or row) for row in rows if isinstance(row, dict | str)]


def _plans(data: dict, *names: str) -> bool:
    return any(name in _plan_steps(data) for name in names)


def _plan_shown(data: dict) -> str:
    return " -> ".join(_plan_steps(data)) or "порожньо"


def _plan_said(data: dict) -> str:
    rows = data.get("steps") or []
    return " ".join(str(row.get("why") or "") for row in rows if isinstance(row, dict))


SCENARIOS = (
    Scenario(
        key="комора_холодна",
        prompt=PANTRY_COLD,
        system=_pantry_system(PANTRY_STATES["COLD"]),
        schema=PLAN_SCHEMA,
        check=lambda v, ask: False,
        verdict=lambda data: _plans(data, "pantry.name"),
        shown=_plan_shown,
        said=_plan_said,
        note="пастка: не названо ЖОДНОГО виду -- називання мусить бути в плані",
    ),
    Scenario(
        key="комора_тепла",
        prompt=PANTRY_WARM,
        system=_pantry_system(PANTRY_STATES["WARM"]),
        schema=PLAN_SCHEMA,
        check=lambda v, ask: False,
        verdict=lambda data: not _plan_steps(data),
        shown=_plan_shown,
        said=_plan_said,
        note="пастка: бракує НІЧОГО -- порожній план це відповідь, а не відмова",
    ),
    Scenario(
        key="комора_ритм",
        prompt=PANTRY_MUTE,
        system=_pantry_system(PANTRY_STATES["MUTE"]),
        schema=PLAN_SCHEMA,
        check=lambda v, ask: False,
        verdict=lambda data: _plans(data, "pantry.rhythm", "pantry.ask"),
        shown=_plan_shown,
        said=_plan_said,
        note="пастка: рядки мовчать -- лікує це вирок або питання гостю",
    ),
    Scenario(
        key="комора_нова",
        prompt=PANTRY_EMPTY,
        system=_pantry_system(PANTRY_STATES["EMPTY"]),
        schema=PLAN_SCHEMA,
        check=lambda v, ask: False,
        verdict=lambda data: not _plan_steps(data),
        shown=_plan_shown,
        said=_plan_said,
        note="пастка: гість без чеків і без рядків -- називати і судити НЕМА ЧОГО",
    ),
    Scenario(
        key="комора_зайве",
        prompt=PANTRY_MUTE,
        system=_pantry_system(PANTRY_STATES["MUTE"]),
        schema=PLAN_SCHEMA,
        check=lambda v, ask: False,
        verdict=lambda data: not _plans(data, "pantry.name"),
        shown=_plan_shown,
        said=_plan_said,
        note="пастка: мітку виду мають усі -- називати нема кого, крок зайвий",
    ),
    Scenario(
        key="розум_подія",
        prompt=UNDERSTAND_EVENT,
        system=UNDERSTAND_SYSTEM,
        schema=UNDERSTAND_SCHEMA,
        check=lambda v, ask: False,
        verdict=_event_dialog_ok,
        shown=_shown,
        said=_said,
        note="пастка: питати треба про готове-чи-сире, а не про кількість людей, яку вже сказали",
    ),
    Scenario(
        key="розум_список",
        prompt=UNDERSTAND_LIST,
        system=UNDERSTAND_SYSTEM,
        schema=UNDERSTAND_SCHEMA,
        check=lambda v, ask: False,
        verdict=lambda data: not _asks(data) and not _adds(data),
        shown=_shown,
        said=_said,
        note="дзеркало: три слова гостя -- задача зрозуміла, питати і докидати нема чого",
    ),
    Scenario(
        key="розум_відоме",
        prompt=UNDERSTAND_KNOWN,
        system=UNDERSTAND_SYSTEM,
        schema=UNDERSTAND_SCHEMA,
        check=lambda v, ask: False,
        verdict=lambda data: not any("хліб" in ask for ask in _asks(data)),
        shown=_shown,
        said=_said,
        note="пастка: хліб уже в намірах з комори -- питання про нього це питання про відоме",
    ),
    Scenario(
        key="розум_стеля",
        prompt=UNDERSTAND_MANY,
        system=UNDERSTAND_SYSTEM,
        schema=UNDERSTAND_SCHEMA,
        check=lambda v, ask: False,
        verdict=lambda data: len(_asks(data)) <= UNDERSTAND_QUESTIONS,
        shown=_shown,
        said=_said,
        note="стеля: п'ять двояких намірів -- і все одно не більше двох питань",
    ),
    Scenario(
        key="переріз_один",
        prompt=UNDERSTAND_CUT_ONE,
        system=UNDERSTAND_SYSTEM,
        schema=UNDERSTAND_SCHEMA,
        check=lambda v, ask: False,
        verdict=lambda data: (
            len(_cuts(data)) == 1
            and all(word in _cuts(data)[0] for word in ("морозиво", "хрещатик", "фісташка"))
        ),
        shown=_shown,
        said=_cut_said,
        note="пастка: кома розділяє вид, марку і смак ОДНОГО наміру, а не три товари",
    ),
    Scenario(
        key="переріз_кілька",
        prompt=UNDERSTAND_CUT_MANY,
        system=UNDERSTAND_SYSTEM,
        schema=UNDERSTAND_SCHEMA,
        check=lambda v, ask: False,
        verdict=lambda data: len(_cuts(data)) == 3,
        shown=_shown,
        said=_cut_said,
        note="дзеркало: без коми тут ТРИ наміри -- переріз, який завжди склеює, гірший за кому",
    ),
    Scenario(
        key="переріз_сміття",
        prompt=UNDERSTAND_CUT_JUNK,
        system=UNDERSTAND_SYSTEM,
        schema=UNDERSTAND_SCHEMA,
        check=lambda v, ask: False,
        verdict=lambda data: (
            1 <= len(_cuts(data)) <= 2
            and not any("050" in name or "дяк" in name or "привіт" in name for name in _cuts(data))
        ),
        shown=_shown,
        said=_cut_said,
        note="пастка: вітання, номер і підпис товаром не є -- у наміри вони не йдуть",
    ),
    Scenario(
        key="подія_регулярне",
        prompt=OCCASION_PROMPT,
        system=OCCASION_SYSTEM,
        schema=OCCASION_SCHEMA,
        check=lambda v, ask: False,
        verdict=_event_ok,
        shown=lambda data: "зняв: " + (", ".join(_named(data, "skip")) or "нічого"),
        said=lambda data: " ".join(
            str(item.get("why") or "")
            for field in ("add", "skip")
            for item in data.get(field) or []
        ),
        note="пастка: корм, папір і порошок гість бере частіше за все — і в подію не йдуть",
    ),
    Scenario(
        key="заміна",
        prompt="""Немає: Молоко ультрапастеризоване Селянське Особливе 1%, 67.99 грн.

Альтернативи:
  id=920436   Корм для котів Whiskas з куркою, 19.99 грн, залишок 17
  id=67803    Вода мінеральна Карпатська Джерельна, 28.99 грн, залишок 18
  id=1025388  Молоко ультрапастеризоване Feels good Protein 2%, 74.90 грн, залишок 35
  id=1025400  Молоко пастеризоване Ферма 2.5%, 45.50 грн, залишок 22

Гість купує це молоко щотижня. Обери заміну.""",
        check=lambda v, ask: not ask and _digits(v) in {"1025388", "1025400"},
        note="базова: молоко замінюють молоком, і не першим у списку",
    ),
    Scenario(
        key="виключення",
        prompt="""Гість УВІМКНУВ виключення «без молочки» на цей тиждень.

Молоко зі списку прибрано, і воно давало білок. Треба компенсувати білок
з іншої категорії. Доступне:
  id=1025388  Молоко Feels good Protein 2%, 74.90 грн — МОЛОЧНЕ
  id=310277   Сир кисломолочний 9%, 89.90 грн — МОЛОЧНЕ
  id=445120   Яйця курячі С0, 10 шт, 74.50 грн
  id=67803    Вода мінеральна Карпатська Джерельна, 28.99 грн

Обери, чим компенсувати білок.""",
        check=lambda v, ask: not ask and _digits(v) == "445120",
        note="пастка: найсхоже рішення порушує щойно задане обмеження",
    ),
    Scenario(
        key="термін",
        prompt="""Позиція закінчиться ЗАВТРА. Треба обрати, чим замінити.

  id=777001  Ідеальний аналог, той самий бренд — доступний ЛИШЕ Новою Поштою,
             доставка 3 доби
  id=777002  Прийнятний аналог, інший бренд — є у своїй філії сьогодні,
             залишок 12

Обери варіант, який реально встигне.""",
        check=lambda v, ask: not ask and _digits(v) == "777002",
        note="пастка: найкращий за якістю не встигає за строком",
    ),
    Scenario(
        key="обробка",
        prompt=PORK_PROMPT,
        system=pick_system(with_queue=False),
        schema=pick_schema(with_queue=False),
        check=lambda v, ask: False,
        verdict=lambda data: _chose(data, PORK_MARKS, "свинина") == PORK_RAW,
        marks=PORK_MARKS,
        note="пастка: намір без слів про обробку означає сире",
    ),
    Scenario(
        key="шашлик",
        prompt="""Намір гостя: «шашлик». Історії покупок по цьому виду немає.

Поле «оброблене» — назви ІНШИХ видів, у яких товар теж лежить. Поля з
порожнім значенням у запиті немає взагалі.

  id=350487  Свинячий окіст для шніцеля охолоджений, 272 грн, залишок 6
  id=962492  Шашлик із свинини Соковитий напівфабрикат, 199 грн, залишок 4,
             оброблене: ["М'ясо для шашлику та барбекю"]

Обери товар під намір.""",
        check=lambda v, ask: not ask and _digits(v) == "962492",
        note="дзеркало: намір ПРО обробку означає оброблене",
    ),
    Scenario(
        key="історія",
        prompt="""Намір гостя: «сир». Правила гостя мовчать.

Поле «прочитання»: ["Сири" (тверді), "Сир кисломолочний"].
З ІСТОРІЇ гостя: «Сир кисломолочний Яготинський 5%», 14 чеків, з них 6 за
останні 90 днів, звична кількість 1.

  id=410001  Сир Гауда 45%, 99 грн за 100 г, залишок 12
  id=410002  Сир кисломолочний Яготинський 5%, 49.99 грн за 180 г, залишок 20

Обери товар під намір.""",
        check=lambda v, ask: not ask and _digits(v) == "410002",
        note="дзеркало: історія знімає двоякість — питати нема про що",
    ),
    Scenario(
        key="одиниця",
        prompt="""Намір гостя: «молоко». Правило гостя: «бери дешевше».
Історії покупок немає.

  id=520001  Молоко Селянське 2,5%, ціна 39.99 грн, фасовка 300г, за_100г 13.33
  id=520002  Молоко Ферма 2,5%, ціна 53.49 грн, фасовка 900г, за_100г 5.94

Обери товар під намір.""",
        check=lambda v, ask: not ask and _digits(v) == "520002",
        note="пастка: менша ціна не означає дешевше — фасовки різні",
    ),
    Scenario(
        key="межа",
        prompt=BUDGET_PROMPT,
        system=BUDGET_SYSTEM,
        schema=pick_schema(with_queue=True),
        check=lambda v, ask: False,
        verdict=_budget_ok,
        marks=BUDGET_MARKS,
        note="пастка: у чергу на зняття має піти рідке, а не хвіст списку",
    ),
    Scenario(
        key="привід_межа",
        prompt=EVENT_BUDGET_PROMPT,
        system=EVENT_BUDGET_SYSTEM,
        schema=pick_schema(with_queue=True),
        check=lambda v, ask: False,
        verdict=_event_budget_ok,
        marks=EVENT_BUDGET_MARKS,
        note="пастка: пляшка за 153% усієї межі -- не вибір під названу суму "
        "(усі три одного виду: інакше міряється вид, а не межа)",
    ),
    Scenario(
        key="привід_без_межі",
        prompt=EVENT_FREE_PROMPT,
        system=EVENT_FREE_SYSTEM,
        schema=pick_schema(with_queue=False),
        check=lambda v, ask: False,
        verdict=_event_free_ok,
        marks=EVENT_FREE_MARKS,
        note="дзеркало: без названої межі дорогий вибір законний -- пастка не вчить ощадливості",
    ),
    Scenario(
        key="глузд",
        prompt=SENSE_PROMPT,
        system=SANITY_SYSTEM,
        schema=SANITY_SCHEMA,
        check=lambda v, ask: False,
        verdict=_sense_ok,
        shown=_sense_shown,
        said=_sense_said,
        note="пастка: сезон -- вирок, решта -- норма числом у дозволеній одиниці",
    ),
    Scenario(
        key="список",
        prompt=NEXT_LIST_PROMPT,
        system=NEXT_SYSTEM,
        schema=NEXT_SCHEMA,
        check=lambda v, ask: False,
        verdict=_next_list_ok,
        shown=_next_list_shown,
        said=_next_list_said,
        note="пастка: не вигадувати видів, лишити позначку акції, не брати два сири одразу",
    ),
    Scenario(
        key="чужий_вид",
        prompt=KIND_PROMPT,
        system=pick_system(with_queue=False),
        schema=pick_schema(with_queue=False),
        check=lambda v, ask: False,
        verdict=_kind_ok,
        marks=KIND_MARKS,
        note="пастка: на полиці немає ЖОДНОГО кандидата того виду — не обирати",
    ),
    Scenario(
        key="сира",
        prompt=RAW_PROMPT,
        system=pick_system(with_queue=False),
        schema=pick_schema(with_queue=False),
        check=lambda v, ask: False,
        verdict=_raw_ok,
        note="пастка: гість сказав «сира», а сирого немає -- не обирати",
    ),
    Scenario(
        key="варіанти",
        prompt=OPTIONS_PROMPT,
        system=pick_system(with_queue=False),
        schema=pick_schema(with_queue=False),
        check=lambda v, ask: False,
        verdict=_options_ok,
        note="питання без варіантів -- глухий кут, а варіант зі слова гостя -- повтор",
    ),
    Scenario(
        key="бренд",
        prompt=BRAND_PROMPT,
        system=pick_system(with_queue=True),
        schema=pick_schema(with_queue=True),
        check=lambda v, ask: False,
        verdict=_brand_ok,
        marks=BRAND_MARKS,
        note="пастка: назване гостем слово не міняється ні на смак, ні на вид",
    ),
    Scenario(
        key="скіл_акція",
        prompt=PROMO_PROMPT,
        system=PROMO_SYSTEM,
        schema=pick_schema(with_queue=False),
        check=lambda v, ask: False,
        verdict=lambda data: _chose(data, PROMO_MARKS, "пиво світле") == PROMO_PICK,
        marks=PROMO_MARKS,
        note="пастка: звичніше і дешевше -- Оболонь, а гість без акції бере Hike",
    ),
    Scenario(
        key="скіл_акція_без",
        prompt=PROMO_WAIT_PROMPT,
        system=PROMO_WAIT_SYSTEM,
        schema=pick_schema(with_queue=False),
        check=lambda v, ask: False,
        verdict=lambda data: _chose(data, PROMO_WAIT_MARKS, "пиво світле") in ("", PROMO_PICK),
        marks=PROMO_WAIT_MARKS,
        note="дзеркало: акції на його товарі немає -- або він, або нічого, але не сусід",
    ),
    Scenario(
        key="скіл_фасовка",
        prompt=PACK_PROMPT,
        system=PACK_SYSTEM,
        schema=pick_schema(with_queue=False),
        check=lambda v, ask: False,
        verdict=lambda data: (
            _chose(data, PACK_MARKS, "сир твердий") == "960002"
            and _chose(data, PACK_MARKS, "масло") == ""
        ),
        marks=PACK_MARKS,
        note="пастка: названа фасовка є під один намір і немає під сусідній",
    ),
    Scenario(
        key="скіл_тара",
        prompt=CONTAINER_PROMPT,
        system=CONTAINER_SYSTEM,
        schema=pick_schema(with_queue=False),
        check=lambda v, ask: False,
        verdict=lambda data: (
            _chose(data, CONTAINER_MARKS, "пиво") == CONTAINER_GLASS
            and _chose(data, CONTAINER_MARKS, "яйця") != ""
        ),
        marks=CONTAINER_MARKS,
        note="пастка: скло найдорожче, а там, де тари не видно, відмовлятись не можна",
    ),
    Scenario(
        key="скіл_подія",
        prompt=EVENT_PROMPT,
        system=EVENT_SYSTEM,
        schema=pick_schema(with_queue=False),
        check=lambda v, ask: False,
        verdict=lambda data: _chose(data, EVENT_MARKS, "закуски до столу") == EVENT_READY,
        marks=EVENT_MARKS,
        note="пастка: чеки кажуть «накриває готовим», а базове правило -- «бери сире»",
    ),
    Scenario(
        key="скіл_дитяче",
        prompt=KIDS_PROMPT,
        system=KIDS_SYSTEM,
        schema=pick_schema(with_queue=False),
        check=lambda v, ask: False,
        verdict=lambda data: _chose(data, KIDS_MARKS, "напій") == KIDS_JUICE,
        marks=KIDS_MARKS,
        note="пастка: звичне з історії -- кава, а напій просять дитині",
    ),
    Scenario(
        key="скіл_обмеження",
        prompt=LIMITS_PROMPT,
        system=LIMITS_SYSTEM,
        schema=pick_schema(with_queue=False),
        check=lambda v, ask: False,
        verdict=lambda data: (
            _chose(data, LIMITS_MARKS, "сир") == LIMITS_SAFE
            and _chose(data, LIMITS_MARKS, "молоко") == ""
        ),
        marks=LIMITS_MARKS,
        note="пастка: безлактозне є під сир і немає під молоко -- там відмова",
    ),
    Scenario(
        key="скіл_бренд",
        prompt=BRAND_SKILL_PROMPT,
        system=BRAND_SKILL_SYSTEM,
        schema=pick_schema(with_queue=False),
        check=lambda v, ask: False,
        verdict=lambda data: _chose(data, BRAND_SKILL_MARKS, "Моршинська") == BRAND_NAMED,
        marks=BRAND_SKILL_MARKS,
        note="пастка: сусідка дешевша, більша і по акції -- але назвали не її",
    ),
    Scenario(
        key="скіл_економія",
        prompt=THRIFT_PROMPT,
        system=THRIFT_SYSTEM,
        schema=pick_schema(with_queue=False),
        check=lambda v, ask: False,
        verdict=lambda data: _chose(data, THRIFT_MARKS, "оливкова олія") in THRIFT_OLIVE,
        marks=THRIFT_MARKS,
        note="пастка: соняшникова вп'ятеро дешевша за 100 мл і не є дешевшою оливковою",
    ),
)

DEFAULT_MODELS = (
    "mistral.mistral-large-3-675b-instruct",
    LUNA,
)

LUNA_BASE_URL = "https://api.openai.com"
LUNA_KEY_ENV = "OPENAI_API_KEY"

ROOT = Path(__file__).resolve().parents[1]


def luna_key() -> str:
    said = os.environ.get(LUNA_KEY_ENV, "").strip()
    if said:
        return said
    env = ROOT / ".env"
    if not env.exists():
        return ""
    for line in env.read_text(encoding="utf-8").splitlines():
        name, _, value = line.partition("=")
        if name.strip() == LUNA_KEY_ENV:
            return value.strip()
    return ""


def route(model: str, base_url: str, api_key: str) -> tuple[str, str]:
    if model == LUNA and base_url == settings.bedrock_base_url:
        return LUNA_BASE_URL, luna_key()
    return base_url, api_key


PAUSE_S = 3.0

UKRAINIAN_ONLY = set("іїєґІЇЄҐ")
RUSSIAN_ONLY = set("ыэъёЫЭЪЁ")


def _has_cjk(text: str) -> bool:
    return any("一" <= c <= "鿿" or "぀" <= c <= "ヿ" or "가" <= c <= "힯" for c in text)


def language_verdict(text: str) -> str:
    if not text:
        return "порожньо"
    if _has_cjk(text):
        return "ІЄРОГЛІФИ"
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return "без літер"
    share = sum(1 for c in letters if "Ѐ" <= c <= "ӿ") / len(letters)
    if share < 0.5:
        return f"не кирилиця ({share:.0%})"
    if set(text) & RUSSIAN_ONLY:
        return "РОСІЙСЬКА"
    if set(text) & UKRAINIAN_ONLY:
        return "українська"
    return "кирилиця без ознак укр."


async def probe(model: str, scenario: Scenario, base_url: str, api_key: str) -> dict:
    where, key = route(model, base_url, api_key)
    if not key:
        return {"scenario": scenario.key, "error": f"немає ключа для {model}"}
    llm = build_llm(
        model=model,
        base_url=where,
        api_key=key,
    )
    try:
        decision = await llm.decide(
            system=scenario.system or SYSTEM,
            user=scenario.prompt,
            schema=scenario.schema or SCHEMA,
            prompt=prompts.stamp("pick" if scenario.system else "trap", scenario.system or SYSTEM),
            schema_name="decision",
            max_tokens=2048 if scenario.verdict else 1200,
        )
    except ModelError as exc:
        return {"scenario": scenario.key, "error": str(exc)[:160]}

    if scenario.verdict is not None:
        marks = scenario.marks or BUDGET_MARKS
        queue = [
            resolve(str(item.get("intent", "")), marks) or str(item.get("intent", ""))
            for item in decision.data.get("expendable") or []
        ]
        picked = "; ".join(
            f"{name}={pick.get('chosen_id') or 'порожньо'}"
            for name, pick in _by_intent(decision.data, marks).items()
        )
        return {
            "scenario": scenario.key,
            "chosen": (
                scenario.shown(decision.data)
                if scenario.shown is not None
                else "→".join(queue) or picked or "нічого"
            ),
            "correct": scenario.verdict(decision.data),
            "language": language_verdict(
                scenario.said(decision.data)
                if scenario.said is not None
                else " ".join(
                    str(item.get("why") or "") for item in decision.data.get("expendable") or []
                )
                or " ".join(
                    f"{pick.get('swap') or ''} {pick.get('ask') or ''} {pick.get('reason') or ''}"
                    for pick in decision.data.get("picks") or []
                )
            ),
            "reason": "черга: "
            + "; ".join(
                f"{resolve(str(item.get('intent', '')), marks) or item.get('intent')}"
                f" — {item.get('why')}"
                for item in decision.data.get("expendable") or []
            )
            if decision.data.get("expendable")
            else "; ".join(
                f"id={pick.get('chosen_id') or '-'}"
                f" ask={pick.get('ask') or '-'}"
                f" options={pick.get('ask_options') or '-'}"
                for pick in decision.data.get("picks") or []
            ),
            "out_tokens": decision.usage.output_tokens,
            "ms": decision.duration_ms,
        }

    chosen = str(decision.data.get("chosen_id", ""))
    reason = str(decision.data.get("reason", ""))
    ask = str(decision.data.get("ask") or "").strip()
    return {
        "scenario": scenario.key,
        "chosen": f"?{ask[:40]}" if ask else chosen,
        "correct": scenario.check(chosen, ask),
        "language": language_verdict(reason or ask),
        "reason": reason,
        "out_tokens": decision.usage.output_tokens,
        "ms": decision.duration_ms,
    }


def measured_prompts() -> dict[str, str]:
    seen: dict[str, str] = {}
    for scenario in SCENARIOS:
        for name in prompts.parts_in(scenario.system or SYSTEM):
            seen[name] = prompts.digest_of(name)
    return seen


async def main_async(
    models: list[str], runs: int, base_url: str, api_key: str, *, snapshot: bool = False
) -> int:
    print(f"\nСценаріїв: {len(SCENARIOS)}, прогонів на кожен: {runs}\n")
    for scenario in SCENARIOS:
        print(f"  {scenario.key:<12} {scenario.note}")
    print()

    header = f"{'модель':<40}" + "".join(f"{s.key:>13}" for s in SCENARIOS)
    print(header + f"{'мова':>10}{'сер.мс':>9}")
    print("-" * len(header + "          " + "        "))

    problems: list[str] = []

    passk: dict[str, tuple[int, int, float, list[str]]] = {}
    for model in models:
        cells, langs, times = [], [], []
        solid, shaky, shares = 0, [], []
        for scenario in SCENARIOS:
            attempts = []
            for _ in range(runs):
                attempts.append(await probe(model, scenario, base_url, api_key))
                await asyncio.sleep(PAUSE_S)
            ok = [a for a in attempts if "error" not in a]
            for a in attempts:
                if "error" in a:
                    problems.append(f"  {model} / {scenario.key}: {a['error']}")
            hits = sum(1 for a in ok if a["correct"])
            cells.append(f"{hits}/{len(ok) or runs}")
            if len(ok) == runs and hits == runs:
                solid += 1
            else:
                shaky.append(f"{scenario.key} {hits}/{len(ok) or runs}")
            shares.append(hits / runs)
            langs += [a["language"] for a in ok]
            times += [a["ms"] for a in ok]

            for a in ok:
                if not a["correct"] or a["language"] != "українська":
                    chosen = a["chosen"] if len(a["chosen"]) <= 40 else a["chosen"][:40] + "…"
                    problems.append(
                        f"  {model} / {scenario.key}: вибір={chosen!r} [{a['language']}]\n"
                        f"      {a['reason'][:140]}"
                    )

        clean = sum(1 for lang in langs if lang == "українська")
        avg = sum(times) // len(times) if times else 0
        language = f"{clean}/{len(langs)}"
        print(f"{model:<40}" + "".join(f"{c:>13}" for c in cells) + f"{language:>10}{avg:>9}")
        passk[model] = (solid, len(SCENARIOS), sum(shares) / len(shares), shaky)

    print(f"\npass^{runs} (усі {runs} прогонів поспіль) проти pass@1 (середня частка):")
    for model, (solid, total, share, shaky) in passk.items():
        line = f"  {model:<40} pass^{runs} {solid}/{total}   pass@1 {share:.0%}"
        print(line + (f"   не тримають: {', '.join(shaky)}" if shaky else ""))

    print("\nЗбої:\n" + ("\n".join(problems) if problems else "  немає"))
    if snapshot:
        where = passk_snapshot.write(
            runs=runs,
            models={
                model: {
                    "passk": solid,
                    "total": total,
                    "pass1": round(100 * share),
                    "shaky": shaky,
                }
                for model, (solid, total, share, shaky) in passk.items()
            },
            prompts=measured_prompts(),
        )
        print(
            f"\nЗаписано {where.relative_to(passk_snapshot.ROOT)}. "
            "Далі: uv run python scripts/gen_facts.py"
        )
    print()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Порівняти моделі на задачах агента")
    parser.add_argument("--models", nargs="+", default=list(DEFAULT_MODELS))
    parser.add_argument("--scenarios", nargs="+", default=None, help="ключі сценаріїв")
    parser.add_argument(
        "--runs", type=int, default=5, help="повторів: один прогін нічого не доводить"
    )
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--key-env", default=None, help="імʼя змінної середовища з ключем")
    parser.add_argument(
        "--snapshot",
        action="store_true",
        help="записати docs/passk.json (числа + хеші промптів, на яких їх зняли)",
    )
    args = parser.parse_args()

    base_url = args.base_url or settings.bedrock_base_url
    api_key = os.environ.get(args.key_env, "") if args.key_env else settings.bedrock_api_key or ""
    if not api_key:
        print("Немає ключа — нічим ходити в модель", file=sys.stderr)
        return 1

    global SCENARIOS
    if args.scenarios:
        SCENARIOS = tuple(s for s in SCENARIOS if s.key in set(args.scenarios))
        if not SCENARIOS:
            print("Немає таких сценаріїв", file=sys.stderr)
            return 1
        if args.snapshot:
            print(
                "Знімок з підмножини сценаріїв описував би не те, що стоїть на "
                "сторінці «Якість»: прожени без --scenarios",
                file=sys.stderr,
            )
            return 1

    return runtime.run(
        main_async(args.models, args.runs, base_url, api_key, snapshot=args.snapshot)
    )


if __name__ == "__main__":
    sys.exit(main())
