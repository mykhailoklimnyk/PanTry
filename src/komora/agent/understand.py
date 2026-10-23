from __future__ import annotations

import json
import time
from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from komora.agent.prompts import register as register_prompt
from komora.agent.prompts import stamp as prompt_stamp
from komora.core.occasion import Occasion
from komora.core.understanding import (
    UNDERSTAND_ADD,
    UNDERSTAND_QUESTIONS,
    UNDERSTAND_SCHEMA,
    Question,
    Understanding,
    read,
)
from komora.logging import get_logger

log = get_logger(__name__)

UNDERSTAND_TOKENS = 1024

KNOWN_LIMIT = 40

UNDERSTAND_SYSTEM = (
    "Ти агент продуктового кошика «Комора». Перед тим як шукати товари, ти "
    "читаєш ЗАДАЧУ гостя цілком і вирішуєш, чи розумієш її досить, щоб "
    "збирати. У тебе рівно три права. "
    "ПЕРШЕ -- «cut»: прочитай «набране_гостем» (сирий текст гостя) і поверни "
    "ВИДИ ТОВАРІВ з нього, кожен окремим рядком. Кома межею наміру НЕ Є: "
    "«морозиво, хрещатик, фісташка» -- це ОДИН намір (вид, марка, смак), а "
    "«хліб молоко чай» -- ТРИ без жодної коми. Вітання, номер, підпис і "
    "кроки рецепта товаром не є -- не називай їх. Порожнє «набране_гостем» "
    "-- порожній «cut». "
    "ДРУГЕ -- «questions»: до "
    f"{UNDERSTAND_QUESTIONS} питань гостю, кожне з 2-4 варіантами відповіді. "
    "Питання ставиться ЛИШЕ тоді, коли відповідь справді змінить кошик, і "
    "НЕ ставиться про те, що вже відоме: режим, кількість людей, правила "
    "гостя і все, що назване в «наміри_зараз» чи «комора_знає», питати не "
    "можна -- це вже написано в задачі. Кожен варіант може нести «intents»: "
    "види товарів, які поїдуть у кошик, якщо гість обере саме його. "
    "ЯКЩО РЕЖИМ «подія» -- перше питання завжди одне й те саме: чи гість "
    "ГОТУЄ сам, чи БЕРЕ ГОТОВЕ; від цього залежить увесь стіл, а з задачі "
    "цього не видно. Варіант «готую» познач полем «style»: «cooking», "
    "варіант «беру готове» -- «ready»; більше це поле ніде не ставиться. "
    "ЯКЩО РЕЖИМ «зі списку» або «на тиждень» -- питань немає взагалі: у "
    "першому гість уже написав, що взяти, у другому кошик рахується з його "
    "покупок. Про готування там не питай: стола там ніхто не накриває. "
    "ДРУГЕ -- «add»: види, яких у списку немає, а задача їх просить. Для "
    "події це те, чим накривають стіл: розклади подію на страви подумки, а "
    "в кошик назви ВИДИ товарів («сир твердий», «ковбаса», «вино червоне»), "
    "не рецепт і не граматуру. Питання і «add» -- НЕ альтернативи: під "
    "подію ти і питаєш про стиль, і в тій самій відповіді докидаєш стіл; "
    "варіанти питання лише уточнюють, чим саме його накрити. "
    "ТРЕТЄ -- «drop»: наміри З ПОЛЯ «наміри_зараз», які під цю задачу не "
    "йдуть, з "
    "причиною. Слова самого гостя («слова_гостя») не чіпай узагалі: "
    "перегрупувати їх можна лише в «cut», зняти -- не можна ніде. "
    "І окремо «plan»: назви кроків прогону, які варто додати або зняти, з "
    "переліку «кроки_плану» -- інших назв не існує. "
    "Усі списки можуть бути порожні, і це нормальна відповідь: задача буває "
    "зрозуміла як є, і питати заради питання не треба. Відповідай ВИКЛЮЧНО "
    "українською, коротко: питання -- одне речення, варіант -- два-три слова."
)

register_prompt("understand", UNDERSTAND_SYSTEM)


def payload(
    occasion: Occasion,
    *,
    intents: Sequence[str],
    said: Sequence[str],
    typed: str,
    rules: Sequence[str],
    known: Sequence[str],
    tracked: int,
    wanted: Sequence[str],
    steps: Sequence[str],
) -> str:
    return json.dumps(
        {
            "режим": occasion.phrase(),
            "що_це_означає": occasion.task() or None,
            "людей": occasion.people,
            "наміри_зараз": list(intents),
            "слова_гостя": list(said) or None,
            "набране_гостем": typed or None,
            "правила_гостя": list(rules) or None,
            "список_на_потім": list(wanted) or None,
            "комора_знає": {
                "видів_під_наглядом": tracked,
                "закінчується": list(known[:KNOWN_LIMIT]) or None,
            },
            "кроки_плану": list(steps),
            "стеля_питань": UNDERSTAND_QUESTIONS,
            "стеля_докидання": UNDERSTAND_ADD,
        },
        ensure_ascii=False,
    )


async def understand(
    llm: Any,
    occasion: Occasion,
    *,
    intents: Sequence[str],
    said: Sequence[str],
    typed: str = "",
    rules: Sequence[str] = (),
    known: Sequence[str] = (),
    tracked: int = 0,
    wanted: Sequence[str] = (),
    steps: Sequence[str] = (),
) -> Understanding:
    if llm is None:
        return Understanding(failure="модель не підключена")
    started = time.perf_counter()
    try:
        decision = await llm.decide(
            system=UNDERSTAND_SYSTEM,
            prompt=prompt_stamp("understand", UNDERSTAND_SYSTEM),
            user=payload(
                occasion,
                intents=intents,
                said=said,
                typed=typed,
                rules=rules,
                known=known,
                tracked=tracked,
                wanted=wanted,
                steps=steps,
            ),
            schema=UNDERSTAND_SCHEMA,
            max_tokens=UNDERSTAND_TOKENS,
        )
    except Exception as exc:
        log.warning("understand.failed", error=str(exc)[:160])
        return Understanding(
            failure=str(exc)[:120],
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
    seen = read(decision.data, intents=intents, protected=said)
    return replace(
        seen,
        model=decision.model,
        duration_ms=int((time.perf_counter() - started) * 1000),
        tokens=decision.usage.input_tokens + decision.usage.output_tokens,
    )


def answered_note(question: Question, option_label: str) -> str:
    return f"гість відповів на «{question.ask}»: «{option_label}»"


__all__ = [
    "KNOWN_LIMIT",
    "UNDERSTAND_SYSTEM",
    "UNDERSTAND_TOKENS",
    "answered_note",
    "payload",
    "understand",
]
