from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal
from zoneinfo import ZoneInfo

KYIV = ZoneInfo("Europe/Kyiv")

MTOK = Decimal(1_000_000)

CENTS = Decimal("0.000001")


@dataclass(frozen=True, slots=True)
class Price:

    input_usd: Decimal
    output_usd: Decimal


PRICES: dict[str, Price] = {
    "mistral.mistral-large-3-675b-instruct": Price(Decimal("0.50"), Decimal("1.50")),
    "mistral.devstral-2-123b": Price(Decimal("0.40"), Decimal("2.00")),
    "gpt-5.6-luna": Price(Decimal("0.20"), Decimal("1.20")),
}


def cost_of(model: str, tokens_in: int, tokens_out: int) -> Decimal | None:
    price = PRICES.get(model)
    if price is None:
        return None
    total = (Decimal(tokens_in) * price.input_usd + Decimal(tokens_out) * price.output_usd) / MTOK
    return total.quantize(CENTS, rounding=ROUND_HALF_UP)


def run_cost(model: str, calls: int, tokens_in: int, tokens_out: int) -> Decimal | None:
    if not calls:
        return Decimal(0)
    return cost_of(model, tokens_in, tokens_out)


def day_start(now: datetime) -> datetime:
    local = now.astimezone(KYIV)
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)


def day_end(now: datetime) -> datetime:
    local = now.astimezone(KYIV)
    tomorrow = local + timedelta(days=1)
    return tomorrow.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)


COUNTED_RUNS = frozenset({"basket", "refill"})

OFF_DAY_BUDGET = frozenset({"warm"})


def counts_as_run(kind: str) -> bool:
    return kind in COUNTED_RUNS


@dataclass(frozen=True, slots=True)
class Limits:

    per_session: int
    per_day: int
    day_usd: Decimal
    total_usd: Decimal


@dataclass(frozen=True, slots=True)
class Spent:

    session_runs: int = 0
    day_runs: int = 0
    day_usd: Decimal = Decimal(0)
    total_usd: Decimal = Decimal(0)
    day_offbudget_usd: Decimal = Decimal(0)
    day_guest_usd: Decimal = Decimal(0)
    unpriced: int = 0
    session_flying: int = 0
    day_flying: int = 0
    login_runs: int = 0
    login_usd: Decimal = Decimal(0)
    login_tokens_in: int = 0
    login_tokens_out: int = 0
    login_unpriced: int = 0
    login_guest_usd: Decimal = Decimal(0)


Scope = Literal["session", "day", "budget-day", "budget-total"]


@dataclass(frozen=True, slots=True)
class Verdict:

    scope: Scope | None
    headline: str
    action: str | None
    left: int
    resets_at: datetime | None
    spent: Spent = field(default_factory=Spent)

    @property
    def allowed(self) -> bool:
        return self.scope is None


def runs_word(count: int) -> str:
    tail_two = abs(count) % 100
    tail = abs(count) % 10
    if 11 <= tail_two <= 14:
        return "прогонів"
    if tail == 1:
        return "прогін"
    if 2 <= tail <= 4:
        return "прогони"
    return "прогонів"


def in_words(now: datetime, when: datetime) -> str:
    minutes = max(0, int((when - now).total_seconds() // 60))
    if minutes < 60:
        return f"через {minutes} хв"
    return f"через {round(minutes / 60)} год"


def _both(done: int, flying: int) -> str:
    if not flying:
        return str(done)
    return f"{done + flying} ({done} + {flying} в роботі)"


def _waiting(flying: int, tail: str) -> str:
    return (
        f"місце зайняте: {flying} {runs_word(flying)} ще в роботі. Воно "
        f"звільниться саме, щойно збірка завершиться. {tail}"
    )


def _money(amount: Decimal) -> str:
    return f"${amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)}"


def _state_line(limits: Limits, spent: Spent) -> str:
    line = (
        f"прогонів: {spent.session_runs} з {limits.per_session} у цій сесії, "
        f"{spent.day_runs} з {limits.per_day} за добу"
    )
    if spent.day_flying:
        line += (
            f" · у роботі ще {spent.day_flying} {runs_word(spent.day_flying)} — місце вже зайняте"
        )
    if spent.unpriced:
        line += (
            f" · {spent.unpriced} {runs_word(spent.unpriced)} на моделі без прайсу — "
            "гроші по них не рахувались"
        )
    if spent.day_offbudget_usd:
        line += (
            f" · {_money(spent.day_offbudget_usd)} сьогодні поза добовою стелею: "
            "нагрів кешу назв платить проєкт, а не гість"
        )
    if spent.day_guest_usd:
        line += (
            f" · {_money(spent.day_guest_usd)} сьогодні на твоєму ключі — "
            "ці гроші не наші і в стелю не йдуть"
        )
    return line


def verdict(
    limits: Limits,
    spent: Spent,
    *,
    now: datetime,
    exempt: bool = False,
) -> Verdict:
    left = max(
        0,
        min(
            limits.per_session - spent.session_runs - spent.session_flying,
            limits.per_day - spent.day_runs - spent.day_flying,
        ),
    )
    state = _state_line(limits, spent)
    hit = _hit(limits, spent, now=now)

    if hit is None:
        return Verdict(
            scope=None, headline=state, action=None, left=left, resets_at=None, spent=spent
        )

    scope, headline, action, resets_at = hit
    if exempt:
        return Verdict(
            scope=None,
            headline=f"{state} · стеля спрацювала б тут, але на своїх не діє",
            action=None,
            left=left,
            resets_at=resets_at,
            spent=spent,
        )
    return Verdict(
        scope=scope, headline=headline, action=action, left=0, resets_at=resets_at, spent=spent
    )


def _hit(
    limits: Limits,
    spent: Spent,
    *,
    now: datetime,
) -> tuple[Scope, str, str, datetime | None] | None:
    if spent.total_usd >= limits.total_usd:
        return (
            "budget-total",
            f"бюджет моделі вичерпано: {_money(spent.total_usd)} з {_money(limits.total_usd)}",
            "сам він не поновиться. Комора, кошик у «Сільпо» і решта екранів "
            "працюють — вони рахуються з чеків, не з моделі. Потрібна жива "
            "збірка — напиши автору",
            None,
        )

    if spent.day_usd >= limits.day_usd:
        opens = day_end(now)
        return (
            "budget-day",
            f"денна межа витрат на модель вичерпана: {_money(spent.day_usd)} "
            f"з {_money(limits.day_usd)}",
            f"оновиться опівночі за Києвом, {in_words(now, opens)}. Комора і решта "
            "екранів працюють. Потрібно раніше — напиши автору",
            opens,
        )

    if spent.day_runs + spent.day_flying >= limits.per_day:
        opens = day_end(now)
        return (
            "day",
            "на сьогодні стеля прогонів вичерпана: "
            f"{_both(spent.day_runs, spent.day_flying)} з {limits.per_day}",
            _waiting(spent.day_flying, "До півночі чекати не треба")
            if spent.day_runs < limits.per_day
            else f"оновиться опівночі за Києвом, {in_words(now, opens)}. Комора і решта "
            "екранів працюють. Потрібно більше — напиши автору",
            opens,
        )

    if spent.session_runs + spent.session_flying >= limits.per_session:
        day_left = max(0, limits.per_day - spent.day_runs - spent.day_flying)
        return (
            "session",
            "стеля цієї сесії вичерпана: "
            f"{_both(spent.session_runs, spent.session_flying)} з {limits.per_session}",
            _waiting(
                spent.session_flying,
                "Новий вхід тут не допоможе: місце тримає робота, а не сесія",
            )
            if spent.session_runs < limits.per_session
            else f"за добу лишилось ще {day_left} {runs_word(day_left)} — вони відкриються "
            "в новій сесії: «Вийти» і підключитись знову. Стеля сесії ловить "
            "зациклений клієнт, а не тебе",
            None,
        )

    return None


__all__ = [
    "CENTS",
    "COUNTED_RUNS",
    "KYIV",
    "MTOK",
    "OFF_DAY_BUDGET",
    "PRICES",
    "Limits",
    "Price",
    "Scope",
    "Spent",
    "Verdict",
    "cost_of",
    "counts_as_run",
    "day_end",
    "day_start",
    "in_words",
    "run_cost",
    "runs_word",
    "verdict",
]
