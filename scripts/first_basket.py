from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from komora import runtime
from komora.agent.basket import (
    Assembled,
    assemble_list,
    receipts_phrase,
    terms_from_slot,
    to_cart_line,
)
from komora.agent.cart import assemble_cart
from komora.agent.checkout import hand_off
from komora.agent.llm import build_llm
from komora.api.schemas import BuildRequest, CarryOverState, CheckoutResult, ClarifyAnswer
from komora.config import settings
from komora.core.delivery import delivery_cost, shortfall_to_minimum
from komora.db.pool import get_pool, pool_lifespan
from komora.mcp.client import SilpoMCP

runtime.console()

KYIV = ZoneInfo("Europe/Kyiv")


def slot_phrase(slot: dict) -> str:
    try:
        start = datetime.fromisoformat(slot["start"]).astimezone(KYIV)
        end = datetime.fromisoformat(slot["end"]).astimezone(KYIV)
    except KeyError, TypeError, ValueError:
        return f"{slot.get('start')} — {slot.get('end')}"
    return f"{start:%d.%m %H:%M}–{end:%H:%M} (київський час)"


def print_plan(assembled: Assembled) -> None:
    slot = assembled.slot
    model = assembled.basket.stats.model
    print(f"\n══ План кошика · агент: {model} · слот {slot_phrase(slot)}")
    place_step = next((s for s in assembled.basket.trace if s.id == "step-place"), None)
    if place_step is not None:
        print(f"   {place_step.result_summary}")
    for line in assembled.lines:
        flags = []
        if line.from_history:
            flags.append(f"історія: {receipts_phrase(line.from_history.receipts)}")
        if line.risky:
            flags.append(f"залишок {line.product.get('stock')} — ризик")
        if line.needs_approval:
            flags.append("ПОТРЕБУЄ ПОГОДЖЕННЯ ЗАМІНИ")
        shown = to_cart_line(line)
        print(
            f"\n  [{line.intent}] {line.product['name']}"
            f"\n    артикул {line.product['externalProductId']} · {line.qty} {shown.unit} · "
            f"{line.price} грн · {' · '.join(flags) if flags else 'ок'}"
            f"\n    чому: {line.reason}"
        )
        if line.mandate:
            print(f"    мандат: {line.mandate}")
    for intent in assembled.unresolved:
        print(f"\n  [{intent}] НЕ РОЗВ'ЯЗАНО — нічого не знайшлось, скажи конкретніше")
    for intent in assembled.basket.not_collected:
        print(f"\n  [{intent}] НА ЦЕЙ СЛОТ НЕ ЗБИРАЮТЬ — асортимент залежить від вікна")
    for question in assembled.basket.questions:
        print(f"\n  [{question.intent}] ЧЕКАЄ НА УТОЧНЕННЯ: {question.question}")
        for option in question.options:
            price = ""
            if option.price_from is not None:
                unit = "/кг" if option.by_weight else ""
                price = f" · від {option.price_from} грн{unit}"
            print(f"      --answer {question.intent}={option.slug}   {option.title}{price}")
        print(f"      --answer {question.intent}=<свої слова> або =«не треба»")

    terms = terms_from_slot(slot)
    total = sum((line.total for line in assembled.lines), Decimal(0))
    gap = shortfall_to_minimum(terms, total)
    print(f"\n  Разом: {total} грн · доставка {delivery_cost(terms, total)} грн")
    if gap > 0:
        print(f"  До мінімуму замовлення ({terms.min_order_cost}) бракує {gap} грн")

    stats = assembled.basket.stats
    tokens = stats.tokens_in + stats.tokens_out
    print(
        f"  Прогін: {tokens} токенів ({stats.tokens_in} + {stats.tokens_out}) · "
        f"${stats.cost_usd} · {stats.duration_ms} мс"
    )


def print_checkout(result: CheckoutResult, assembled: Assembled) -> None:
    print(f"\n══ {result.summary}")
    if result.carry_over is not None:
        for line in result.carry_over.lines:
            print(f"   поза планом: {line.name} ×{line.qty} — {line.total} грн")
        if result.carry_over.state is CarryOverState.ASKING:
            print("   (не записано нічого: повтори з --existing kept або --existing removed)")
    for skip in result.skipped:
        print(f"   лишилось тут: {skip.name} — {skip.reason}")
    for code in result.blockers:
        print(f"   блокер кошика: {code}")
    if result.checkout_web_link:
        print(f"══ Оформлення (підтверджує гість сам): {result.checkout_web_link}")
    if not result.watched:
        print("(!) під нагляд крона кошик не взято — перед слотом його ніхто не перевірить")

    if assembled.run_log and assembled.run_log.exists():
        data = json.loads(assembled.run_log.read_text(encoding="utf-8"))
        data["checkout"] = result.model_dump(mode="json", by_alias=True)
        assembled.run_log.write_text(
            json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8"
        )


SKIP_WORDS = frozenset({"не треба", "не потрібно", "пропустити", "-"})


def parse_answers(raw: list[str]) -> list[ClarifyAnswer]:
    answers = []
    for item in raw:
        intent, _, value = item.partition("=")
        intent, value = intent.strip(), value.strip().strip("«»")
        if not intent or not value:
            raise ValueError(f"--answer очікує «намір=відповідь», прийшло: {item!r}")
        if value.lower() in SKIP_WORDS:
            answers.append(ClarifyAnswer(intent=intent, skip=True))
        elif re.fullmatch(r"[a-z0-9-]+", value):
            answers.append(ClarifyAnswer(intent=intent, slug=value))
        else:
            answers.append(ClarifyAnswer(intent=intent, text=value))
    return answers


async def main_async(
    intents: list[str],
    commit: bool,
    from_cart: bool,
    log: bool,
    answers: list[ClarifyAnswer] | None = None,
    delivery: str = "DeliveryHome",
    existing: str = "asking",
    budget: float | None = None,
    mode: str = "list",
    people: int | None = None,
    style: str | None = None,
) -> int:
    try:
        token, _ = settings.require_operator()
    except RuntimeError as exc:
        print(exc, file=sys.stderr)
        return 1

    cfg = settings.model_copy(update={"run_log": True}) if log else settings

    llm = build_llm(
        model=settings.bedrock_model_id,
        base_url=settings.bedrock_base_url,
        api_key=settings.bedrock_api_key or "",
    )
    async with pool_lifespan(wait=False), SilpoMCP(token=token, writes=commit) as mcp:
        if from_cart:
            run = await assemble_cart(
                mcp,
                llm,
                BuildRequest.model_validate({"source": "cart", "delivery": delivery, "mode": mode}),
                settings=cfg,
                pool=get_pool(),
            )
            assembled = run.assembled
        else:
            run = None
            assembled = await assemble_list(
                mcp,
                llm,
                BuildRequest.model_validate(
                    {
                        "shoppingList": intents,
                        "delivery": delivery,
                        "budget": budget,
                        "mode": mode,
                        "occasionPeople": people,
                        "eventStyle": style,
                        "answers": [answer.model_dump() for answer in answers or []],
                    }
                ),
                settings=cfg,
                pool=get_pool(),
            )
        print_plan(assembled)
        if assembled.run_log:
            print(f"\n(журнал прогону: {assembled.run_log})")
        if not commit:
            print("\n(dry-run: у кошик нічого не писалось — додай --commit)")
        else:
            print_checkout(
                await hand_off(mcp, run or assembled, existing=CarryOverState(existing)),
                assembled,
            )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Перша корзина: входи В і Б")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--list", help="вхід В — наміри через кому: «молоко, вода»")
    source.add_argument(
        "--from-cart",
        action="store_true",
        help="вхід Б — узяти кошик, наповнений кимось іншим, і довести до дверей",
    )
    parser.add_argument("--commit", action="store_true", help="справді записати в кошик")
    parser.add_argument(
        "--mode",
        choices=["list", "week", "event"],
        default="list",
        help="режим: list (лише список, за замовчуванням), week (комора і цикли), event (подія)",
    )
    parser.add_argument(
        "--people", type=int, default=None, help="скільки людей на подію (лише з --mode event)"
    )
    parser.add_argument(
        "--style",
        choices=["cooking", "ready"],
        default=None,
        help="подія: гість готує сам (cooking) чи бере готове (ready)",
    )
    parser.add_argument("--budget", type=float, default=None, help="ціль суми, грн (коридор ±10%%)")
    parser.add_argument(
        "--answer",
        action="append",
        default=[],
        metavar="НАМІР=ВІДПОВІДЬ",
        help="відповідь на уточнення: слаг вузла, свої слова або «не треба»",
    )
    parser.add_argument(
        "--delivery",
        default="DeliveryHome",
        help="спосіб отримання: DeliveryHome (за замовчуванням) або SelfPickup",
    )
    parser.add_argument(
        "--existing",
        choices=[state.value for state in CarryOverState],
        default=CarryOverState.ASKING.value,
        help="рядки в кошику поза планом: asking (спитати), kept (лишити), removed (зняти)",
    )
    parser.add_argument(
        "--log",
        action="store_true",
        help="лишити журнал прогону в runs/ — запит, кошик, трейс і вибори агента",
    )
    args = parser.parse_args()
    try:
        answers = parse_answers(args.answer)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 1
    intents = [part.strip() for part in (args.list or "").split(",") if part.strip()]
    if not args.from_cart and not intents and (args.mode == "list" or args.budget is None):
        print(
            "Порожній список: додай наміри, або --mode week з --budget",
            file=sys.stderr,
        )
        return 1
    return runtime.run(
        main_async(
            intents,
            args.commit,
            args.from_cart,
            args.log,
            answers,
            args.delivery,
            args.existing,
            args.budget,
            args.mode,
            args.people,
            args.style,
        )
    )


if __name__ == "__main__":
    sys.exit(main())
