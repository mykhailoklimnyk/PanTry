from __future__ import annotations

from decimal import Decimal

import pytest

from komora.agent.checkout import SKIP_THROTTLED, write_rows
from komora.mcp.client import MCPCallError


class _Line:

    def __init__(self, name: str) -> None:
        self.product = {
            "id": f"id-{name}",
            "companyId": "company",
            "branchId": "branch",
            "name": name,
        }
        self.qty = Decimal(1)
        self.intent = name
        self.mandate = ""


class _Cart:

    def __init__(self, *, throttle: set[str], broken: set[str], relent: bool) -> None:
        self.throttle = throttle
        self.broken = broken
        self.relent = relent
        self.seen: list[str] = []

    async def call(self, tool: str, args: dict) -> None:
        rows = args["products"]
        if len(rows) > 1:
            raise MCPCallError(tool, "API returned 400 Bad Request", attempts=1)
        name = rows[0]["productId"].removeprefix("id-")
        self.seen.append(name)
        if name in self.broken:
            raise MCPCallError(tool, "API returned 400 Bad Request", attempts=1)
        if name in self.throttle:
            if self.relent:
                self.throttle = self.throttle - {name}
            raise MCPCallError(tool, "Rate limit exceeded. Please wait and try again.", attempts=1)


@pytest.fixture(autouse=True)
def _no_real_waiting(monkeypatch):
    import komora.agent.checkout as checkout

    async def _instant(_seconds: float) -> None:
        return None

    monkeypatch.setattr(checkout.asyncio, "sleep", _instant)


@pytest.mark.anyio
async def test_a_throttled_row_is_written_on_the_second_try():
    lines = [_Line("хліб"), _Line("молоко")]
    cart = _Cart(throttle={"молоко"}, broken=set(), relent=True)

    written, rejected = await write_rows(cart, "кошик", lines)

    assert [line.intent for line in written] == ["хліб", "молоко"]
    assert rejected == []
    assert cart.seen.count("молоко") == 2, "повтору не було -- пауза нічого не змінила"


@pytest.mark.anyio
async def test_a_row_that_stays_throttled_says_WAIT_and_not_REFUSED():
    cart = _Cart(throttle={"молоко"}, broken=set(), relent=False)

    written, rejected = await write_rows(cart, "кошик", [_Line("хліб"), _Line("молоко")])

    assert [line.intent for line in written] == ["хліб"]
    assert [skip.reason for skip in rejected] == [SKIP_THROTTLED]
    assert "не прийняло" not in SKIP_THROTTLED


@pytest.mark.anyio
async def test_a_genuinely_bad_row_is_still_refused_and_does_not_wait():
    cart = _Cart(throttle=set(), broken={"морозиво"}, relent=False)

    written, rejected = await write_rows(cart, "кошик", [_Line("хліб"), _Line("морозиво")])

    assert [line.intent for line in written] == ["хліб"]
    assert "не прийняло" in rejected[0].reason
    assert cart.seen.count("морозиво") == 1


@pytest.mark.anyio
async def test_one_bad_row_no_longer_costs_the_whole_basket():
    lines = [_Line(name) for name in ("хліб", "сир", "йогурт", "кукурудза", "морозиво")]
    cart = _Cart(throttle={"сир", "йогурт", "кукурудза"}, broken={"морозиво"}, relent=True)

    written, rejected = await write_rows(cart, "кошик", lines)

    assert [line.intent for line in written] == ["хліб", "сир", "йогурт", "кукурудза"]
    assert [skip.name for skip in rejected] == ["морозиво"]
