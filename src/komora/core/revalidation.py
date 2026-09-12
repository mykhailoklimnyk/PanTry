from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from komora.core.substitution import Alternative


class Verdict(StrEnum):

    OK = "ok"
    """Залишку вистачає на всю кількість — рядок їде як є."""
    SHORT = "short"
    """На полиці менше, ніж замовлено: частина рядка закривається заміною."""
    GONE = "gone"
    """Рядка не буде взагалі — залишок нуль або API позначив його недоступним."""


@dataclass(frozen=True, slots=True)
class Line:

    external_product_id: str
    """Артикул — ключ матчингу з історією і з ланцюжками."""
    product_id: str
    """UUID: саме ним кошик адресує рядок при перезаписі."""
    name: str
    quantity: Decimal
    stock: Decimal | None = None
    """Залишок у філії кошика. None — невідомий, і це НЕ привід переписувати
    рядок: рішення тоді приймається лише за прапорцем від API."""
    flagged: bool = False
    """API сам позначив рядок у `validations[]` (`type: "product"`).

    Ставиться ТІЛЬКИ на валідації зі змістом «цього рядка не буде»: інакше
    ре-валідація почне переписувати рядки через підтвердження віку чи
    обмеження оплати, тобто через речі, до заміни товару не дотичні."""


@dataclass(frozen=True, slots=True)
class Rewrite:

    line: Line
    verdict: Verdict
    keep_quantity: Decimal
    """Скільки лишається оригіналу. Нуль — рядок знімається цілком."""
    replacement: Alternative | None
    replacement_quantity: Decimal
    link_index: int
    """Котра ланка ланцюжка спрацювала, з одиниці. Нуль — жодна."""
    needs_approval: bool
    """Плану Б немає: рішення за гостем, і рядок про це каже вголос."""
    note: str
    """Готовий людський рядок для трейсу і для звірки після доставки."""


def verdict_of(line: Line) -> Verdict:
    if line.stock is None:
        return Verdict.GONE if line.flagged else Verdict.OK
    if line.stock <= 0:
        return Verdict.GONE
    if line.stock < line.quantity:
        return Verdict.SHORT
    return Verdict.OK


def first_available(
    chain: Sequence[Alternative], *, needed: Decimal
) -> tuple[Alternative | None, int, Decimal]:
    for index, alternative in enumerate(chain, start=1):
        if not alternative.available:
            continue
        if alternative.stock is None:
            return alternative, index, needed
        stock = Decimal(alternative.stock)
        if stock > 0:
            return alternative, index, min(needed, stock)
    return None, 0, Decimal(0)


def _note(
    line: Line,
    verdict: Verdict,
    replacement: Alternative | None,
    link_index: int,
    covered: Decimal,
    missing: Decimal,
) -> str:
    if replacement is None:
        head = (
            "звичного не було"
            if verdict is Verdict.GONE
            else f"на полиці {_num(line.stock)} з {_num(line.quantity)}"
        )
        return f"{head}, погодженої заміни немає — потрібне рішення гостя"
    head = (
        "звичного не було"
        if verdict is Verdict.GONE
        else f"на полиці {_num(line.stock)} з {_num(line.quantity)}"
    )
    tail = (
        ""
        if covered >= missing
        else f" (закрито {_num(covered)} з {_num(missing)} — решти немає й у заміни)"
    )
    return f"{head} — поклав погоджену заміну №{link_index}: {replacement.name}{tail}"


def _num(value: Decimal | None) -> str:
    if value is None:
        return "?"
    normalized = value.normalize()
    return f"{normalized:f}"


def plan_rewrites(
    lines: Sequence[Line],
    chains: Mapping[str, Sequence[Alternative]],
) -> list[Rewrite]:
    plan: list[Rewrite] = []
    for line in lines:
        verdict = verdict_of(line)
        if verdict is Verdict.OK:
            continue
        keep = Decimal(0) if verdict is Verdict.GONE else (line.stock or Decimal(0))
        missing = line.quantity - keep
        replacement, link_index, covered = first_available(
            chains.get(line.external_product_id, ()), needed=missing
        )
        plan.append(
            Rewrite(
                line=line,
                verdict=verdict,
                keep_quantity=keep,
                replacement=replacement,
                replacement_quantity=covered,
                link_index=link_index,
                needs_approval=replacement is None,
                note=_note(line, verdict, replacement, link_index, covered, missing),
            )
        )
    return plan
