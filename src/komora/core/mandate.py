from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, Decimal

from komora.core.substitution import Alternative

COMMENT_MAX = 200


def fit_comment(text: str) -> str:
    if len(text) <= COMMENT_MAX:
        return text
    head = text[:COMMENT_MAX]
    cut = max(head.rfind("; "), head.rfind(" — "), head.rfind(" -- "), head.rfind(", "))
    return (head[:cut] if cut > 40 else head).rstrip(" ,;—-")


DEFAULT_FORK_PERCENT = 10

FORK_STEP = Decimal("0.01")

FORK_CAP = Decimal(50)

_NO_SUBSTITUTE = "інакше не брати"


def money(value: Decimal) -> str:
    return format(value.normalize(), "f").replace(".", ",")


@dataclass(frozen=True, slots=True)
class Fork:

    low: Decimal
    high: Decimal
    per: str = ""

    @property
    def phrase(self) -> str:
        return f"у межах {money(self.low)}–{money(self.high)} грн" + (
            f"/{self.per}" if self.per else ""
        )


def price_fork(price: Decimal, *, percent: int = DEFAULT_FORK_PERCENT, per: str = "") -> Fork:
    if price <= 0:
        raise ValueError("ціна має бути додатною")
    if not 0 < percent < 100:
        raise ValueError("відсоток вилки має бути в межах (0, 100)")
    allowance = min(price * Decimal(percent) / 100, FORK_CAP)
    return Fork(
        low=(price - allowance).quantize(FORK_STEP, rounding=ROUND_FLOOR),
        high=(price + allowance).quantize(FORK_STEP, rounding=ROUND_CEILING),
        per=(per or "").strip(),
    )


@dataclass(frozen=True, slots=True)
class Mandate:
    comment: str
    dropped: tuple[str, ...] = ()


def chain_phrase(chain: Sequence[Alternative]) -> str | None:
    if not chain:
        return None

    names = [alternative.name for alternative in chain]
    head = names[0]
    tail = "".join(f", потім {name}" for name in names[1:])
    return f"якщо немає — {head}{tail}, {_NO_SUBSTITUTE}"


def empty_chain_phrase() -> str:
    return f"заміни не підбирати, {_NO_SUBSTITUTE}"


def _with_tails(text: str, tails: Sequence[str], *, max_length: int) -> str | None:
    if len(text) > max_length:
        return None
    kept = list(tails)
    while kept:
        full = "; ".join([text, *kept])
        if len(full) <= max_length:
            return full
        kept.pop()
    return text


def price_fork_comment(
    fork: Fork,
    *,
    kind: str | None = None,
    shelf_life: str | None = None,
    wish: str | None = None,
    max_length: int = COMMENT_MAX,
) -> str:
    axis = (kind or "").strip().rstrip(".,;")
    tails = [tail for tail in ((shelf_life or "").strip(), (wish or "").strip()) if tail]

    if axis and (
        named := _with_tails(
            f"якщо немає — {axis} {fork.phrase}, {_NO_SUBSTITUTE}", tails, max_length=max_length
        )
    ):
        return named
    neutral = f"якщо немає — рівноцінна заміна того самого виду {fork.phrase}, {_NO_SUBSTITUTE}"
    return _with_tails(neutral, tails, max_length=max_length) or neutral


def build_comment(
    *,
    chain: Sequence[Alternative] = (),
    shelf_life: str | None = None,
    wishes: str | None = None,
    max_length: int = COMMENT_MAX,
) -> Mandate:
    parts: list[str] = [chain_phrase(chain) or empty_chain_phrase()]
    if shelf_life:
        parts.append(shelf_life)
    if wishes:
        parts.append(wishes)

    dropped: list[str] = []

    while len("; ".join(parts)) > max_length and len(parts) > 1:
        dropped.append(parts.pop())

    trimmed_chain = list(chain)
    while len("; ".join(parts)) > max_length and trimmed_chain:
        removed = trimmed_chain.pop()
        dropped.append(removed.name)
        parts[0] = chain_phrase(trimmed_chain) or empty_chain_phrase()

    comment = "; ".join(parts)
    if len(comment) > max_length:
        comment = comment[:max_length].rstrip(" ,;")

    return Mandate(comment=comment, dropped=tuple(dropped))
