from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager, suppress
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import komora.config as config
from komora.agent.llm import Decision, Meter, Usage
from komora.api import quota
from komora.api.app import app
from komora.api.auth_routes import require_guest
from komora.core.quota import COUNTED_RUNS, OFF_DAY_BUDGET, day_start
from komora.db import spend

pytestmark = pytest.mark.anyio

ACCOUNT = "a" * 64
OTHER = "b" * 64
NOW = datetime(2026, 8, 24, 9, 0, tzinfo=UTC)
MODEL = "mistral.mistral-large-3-675b-instruct"
RUN_KINDS = sorted(COUNTED_RUNS)
OFFBUDGET_KINDS = sorted(OFF_DAY_BUDGET)


class _Rows:

    def __init__(self) -> None:
        self.rows: list[dict[str, Any]] = []

    def add(self, args: dict[str, Any]) -> None:
        self.rows.append(dict(args))

    def counters(self, args: dict[str, Any]) -> dict[str, Any]:
        account, owner, since = args["account"], args["owner"], args["since"]
        kinds, offbudget = args["kinds"], args["offbudget"]
        today = [row for row in self.rows if row["started_at"] >= since]
        ours = [row for row in today if row.get("payer", "project") == "project"]
        budgeted = [row for row in ours if row["kind"] not in offbudget]
        aside = [row for row in ours if row["kind"] in offbudget]
        theirs = [row for row in today if row.get("payer", "project") == "guest"]
        mine = [
            row
            for row in today
            if row["kind"] in kinds
            and (
                (account not in ("", None) and row["account"] == account)
                or (account == "" and row["owner"] == owner)
            )
        ]
        login = [row for row in self.rows if row["owner"] == owner]
        return {
            "day_runs": len(mine),
            "day_usd": sum((row["cost_usd"] or Decimal(0) for row in budgeted), Decimal(0)),
            "day_offbudget_usd": sum((row["cost_usd"] or Decimal(0) for row in aside), Decimal(0)),
            "day_guest_usd": sum((row["cost_usd"] or Decimal(0) for row in theirs), Decimal(0)),
            "total_usd": sum(
                (
                    row["cost_usd"] or Decimal(0)
                    for row in self.rows
                    if row.get("payer", "project") == "project"
                ),
                Decimal(0),
            ),
            "unpriced": sum(1 for row in self.rows if row["cost_usd"] is None),
            "login_runs": len(login),
            "login_usd": sum((row["cost_usd"] or Decimal(0) for row in login), Decimal(0)),
            "login_tokens_in": sum(row["tokens_in"] for row in login),
            "login_tokens_out": sum(row["tokens_out"] for row in login),
            "login_unpriced": sum(1 for row in login if row["cost_usd"] is None),
            "login_guest_usd": sum(
                (
                    row["cost_usd"] or Decimal(0)
                    for row in login
                    if row.get("payer", "project") == "guest"
                ),
                Decimal(0),
            ),
        }


class _Conn:
    def __init__(self, rows: _Rows) -> None:
        self.rows = rows
        self.result: dict[str, Any] | None = None

    async def execute(self, sql: str, args: dict[str, Any] | None = None) -> Any:
        args = args or {}
        if " ".join(sql.split()).startswith("insert"):
            self.rows.add(args)
            self.result = None
        else:
            self.result = self.rows.counters(args)
        return self

    async def fetchone(self) -> dict[str, Any] | None:
        return self.result


class _Pool:
    def __init__(self, rows: _Rows | None = None) -> None:
        self.rows = rows or _Rows()

    @asynccontextmanager
    async def connection(self, **_: Any):
        yield _Conn(self.rows)


class _DeadPool:

    def connection(self, **_: Any) -> Any:
        raise ConnectionError("лічильник не відповідає")


class _Guest:
    access = "живий-токен"
    refresh = None
    owner = "власник-сесії"
    account = ACCOUNT


def _priced() -> None:
    config.settings.bedrock_api_key = "ABSK-тест"


def _meter(input_tokens: int = 6000, output_tokens: int = 1500) -> Meter:
    meter = Meter()
    meter.add(
        Decision(
            data={},
            text="",
            model=MODEL,
            usage=Usage(input_tokens=input_tokens, output_tokens=output_tokens),
            duration_ms=1200,
        )
    )
    return meter


@pytest.fixture
def pool(monkeypatch: pytest.MonkeyPatch) -> _Pool:
    made = _Pool()
    monkeypatch.setattr("komora.api.quota.get_pool", lambda: made)
    return made


def test_the_session_counter_is_per_guest_not_per_process():
    quota.bump("перший")
    quota.bump("перший")
    quota.bump("другий")

    assert quota.seen("перший") == 2
    assert quota.seen("другий") == 1
    assert quota.seen("невідомий") == 0


def test_leaving_forgets_the_session_but_not_the_day():
    quota.bump("власник")
    quota.forget("власник")
    assert quota.seen("власник") == 0
    quota.forget("той, кого не було")


def test_the_floor_of_memory_holds_exactly_as_many_as_it_says():
    for index in range(quota.MAX_OWNERS):
        quota.bump(f"гість-{index}")
    assert quota.seen("гість-0") == 1


def test_the_oldest_session_leaves_first_when_memory_fills():
    for index in range(quota.MAX_OWNERS + 3):
        quota.bump(f"гість-{index}")
    quota.bump("гість-0")

    assert quota.seen("гість-0") >= 1
    assert quota.seen("гість-3") == 0


async def test_every_field_of_the_row_is_the_one_it_says(pool: _Pool):
    _priced()
    guest = _Guest()
    await quota.record(
        guest,
        kind="refill",
        meter=_meter(6000, 1500),
        duration_ms=4321,
        started_at=NOW,
    )

    row = pool.rows.rows[0]
    assert row["account"] == ACCOUNT
    assert row["owner"] == guest.owner
    assert row["kind"] == "refill"
    assert row["model"] == MODEL
    assert row["tokens_in"] == 6000
    assert row["tokens_out"] == 1500
    assert row["duration_ms"] == 4321
    assert row["started_at"] == NOW
    assert row["ok"] is True
    assert row["cost_usd"] == Decimal("0.005250")


async def test_the_gate_counts_attempts_not_successes(pool: _Pool):
    _priced()
    guest = _Guest()
    await quota.record(
        guest, kind="basket", meter=_meter(), duration_ms=900, started_at=NOW, ok=False
    )

    assert quota.seen(guest.owner) == 1
    assert len(pool.rows.rows) == 1
    assert pool.rows.rows[0]["ok"] is False


async def test_the_gate_refuses_with_numbers_and_an_action(pool: _Pool):
    _priced()
    guest = _Guest()
    for _ in range(config.settings.runs_per_session):
        await quota.record(guest, kind="basket", meter=_meter(), duration_ms=900, started_at=NOW)

    with pytest.raises(Exception) as caught:
        await quota.guard(guest, now=NOW)

    detail = str(caught.value.detail)  # type: ignore[attr-defined]
    assert "з 6" in detail
    assert "новій сесії" in detail
    assert config.settings.contact in detail


async def test_a_silent_counter_stops_the_live_run_instead_of_opening_it(
    monkeypatch: pytest.MonkeyPatch,
):
    _priced()
    monkeypatch.setattr("komora.api.quota.get_pool", _DeadPool)

    with pytest.raises(Exception) as caught:
        await quota.guard(_Guest(), now=NOW)

    assert caught.value.status_code == 503  # type: ignore[attr-defined]
    assert str(caught.value.detail) == (  # type: ignore[attr-defined]
        "Лічильник витрат не відповідає, тому жива збірка вимкнена — "
        "рахувати чужі гроші наосліп ми не будемо. Комора і решта "
        "екранів працюють."
    )


async def test_without_a_model_key_there_is_no_ceiling_at_all(pool: _Pool):
    config.settings.bedrock_api_key = None
    guest = _Guest()

    verdict = await quota.guard(guest, now=NOW)
    assert verdict.allowed
    assert verdict.headline == (
        "модель не налаштована — прогони нічого не коштують, стеля не рахується"
    )
    assert verdict.left == config.settings.runs_per_session

    await quota.record(guest, kind="basket", meter=_meter(), duration_ms=900, started_at=NOW)
    assert quota.seen(guest.owner) == 0
    assert pool.rows.rows == []


async def test_a_run_without_a_model_call_costs_zero_not_unknown(pool: _Pool):
    _priced()
    await quota.record(_Guest(), kind="pantry", meter=Meter(), duration_ms=120, started_at=NOW)
    assert pool.rows.rows[0]["cost_usd"] == Decimal(0)


async def test_a_model_without_a_price_writes_null_not_zero(pool: _Pool):
    _priced()
    meter = Meter()
    meter.add(
        Decision(
            data={},
            text="",
            model="openai.gpt-oss-120b",
            usage=Usage(input_tokens=5000, output_tokens=800),
            duration_ms=900,
        )
    )
    await quota.record(_Guest(), kind="basket", meter=meter, duration_ms=900, started_at=NOW)

    assert pool.rows.rows[0]["cost_usd"] is None
    assert pool.rows.rows[0]["tokens_in"] == 5000


async def test_the_counter_keeps_working_when_the_write_fails(
    monkeypatch: pytest.MonkeyPatch,
):
    _priced()
    monkeypatch.setattr("komora.api.quota.get_pool", _DeadPool)
    guest = _Guest()

    await quota.record(guest, kind="basket", meter=_meter(), duration_ms=900, started_at=NOW)
    assert quota.seen(guest.owner) == 1


async def test_one_guest_does_not_eat_the_day_of_another(pool: _Pool):
    _priced()
    guest = _Guest()
    await quota.record(guest, kind="basket", meter=_meter(), duration_ms=900, started_at=NOW)

    counted = await spend.counters(
        pool,
        account=OTHER,
        owner="інший",
        since=day_start(NOW),
        kinds=RUN_KINDS,
        offbudget=OFFBUDGET_KINDS,
    )
    assert counted.day_runs == 0
    assert counted.total_usd > 0


async def test_a_guest_without_a_profile_is_counted_by_session_not_by_nobody(
    pool: _Pool,
):
    _priced()

    class _Nameless(_Guest):
        account = ""
        owner = "сесія-без-профілю"

    guest = _Nameless()
    await quota.record(guest, kind="basket", meter=_meter(), duration_ms=900, started_at=NOW)

    mine = await spend.counters(
        pool,
        account="",
        owner=guest.owner,
        since=day_start(NOW),
        kinds=RUN_KINDS,
        offbudget=OFFBUDGET_KINDS,
    )
    assert mine.day_runs == 1
    stranger = await spend.counters(
        pool,
        account="",
        owner="хтось інший",
        since=day_start(NOW),
        kinds=RUN_KINDS,
        offbudget=OFFBUDGET_KINDS,
    )
    assert stranger.day_runs == 0


async def test_yesterday_does_not_count_toward_today(pool: _Pool):
    _priced()
    guest = _Guest()
    await quota.record(
        guest,
        kind="basket",
        meter=_meter(),
        duration_ms=900,
        started_at=NOW - timedelta(days=1),
    )

    counted = await spend.counters(
        pool,
        account=ACCOUNT,
        owner=guest.owner,
        since=day_start(NOW),
        kinds=RUN_KINDS,
        offbudget=OFFBUDGET_KINDS,
    )
    assert counted.day_runs == 0
    assert counted.total_usd > 0


async def test_the_screen_numbers_come_from_the_counter_not_from_nowhere(
    pool: _Pool,
):
    _priced()
    guest = _Guest()
    await quota.record(guest, kind="basket", meter=_meter(), duration_ms=900, started_at=NOW)
    await quota.record(guest, kind="basket", meter=_meter(), duration_ms=900, started_at=NOW)
    unpriced = Meter()
    unpriced.add(
        Decision(
            data={},
            text="",
            model="openai.gpt-oss-120b",
            usage=Usage(input_tokens=100, output_tokens=10),
            duration_ms=100,
        )
    )
    await quota.record(guest, kind="refill", meter=unpriced, duration_ms=100, started_at=NOW)

    result = await quota.look(guest, now=NOW)
    assert result.headline == (
        "прогонів: 3 з 6 у цій сесії, 3 з 12 за добу"
        " · 1 прогін на моделі без прайсу — гроші по них не рахувались"
    )
    assert result.left == 3


async def test_the_gate_asks_about_the_day_it_was_given(pool: _Pool):
    _priced()
    guest = _Guest()
    for _ in range(config.settings.runs_per_day):
        await quota.record(
            guest,
            kind="basket",
            meter=_meter(),
            duration_ms=900,
            started_at=NOW - timedelta(days=2),
        )
    quota.forget_all()

    assert (await quota.guard(guest, now=NOW)).allowed
    with pytest.raises(Exception) as caught:
        await quota.guard(guest, now=NOW - timedelta(days=2))
    assert caught.value.status_code == 429  # type: ignore[attr-defined]


async def test_insiders_are_counted_but_not_stopped(pool: _Pool):
    _priced()
    config.settings.insiders = ACCOUNT
    guest = _Guest()
    for _ in range(config.settings.runs_per_session + 2):
        await quota.record(guest, kind="basket", meter=_meter(), duration_ms=900, started_at=NOW)

    result = await quota.guard(guest, now=NOW)
    assert result.allowed
    assert "на своїх не діє" in result.headline
    assert len(pool.rows.rows) == config.settings.runs_per_session + 2


async def test_the_pantry_keeps_its_model_while_only_runs_are_spent(pool: _Pool):
    _priced()
    guest = _Guest()
    for _ in range(config.settings.runs_per_session + 1):
        await quota.record(guest, kind="basket", meter=_meter(), duration_ms=900, started_at=NOW)

    assert await quota.model_gate(guest, "клієнт-моделі") == "клієнт-моделі"


async def test_the_pantry_falls_back_to_words_when_the_money_runs_out(pool: _Pool):
    _priced()
    config.settings.budget_day_usd = Decimal("0.001")
    guest = _Guest()
    today = datetime.now(UTC)
    await quota.record(guest, kind="basket", meter=_meter(), duration_ms=900, started_at=today)

    assert await quota.model_gate(guest, "клієнт-моделі") is None


async def test_the_pantry_falls_silent_on_the_total_budget_too(pool: _Pool):
    _priced()
    config.settings.budget_total_usd = Decimal("0.001")
    guest = _Guest()
    await quota.record(guest, kind="basket", meter=_meter(), duration_ms=900, started_at=NOW)

    assert await quota.model_gate(guest, "клієнт-моделі") is None


async def test_the_pantry_does_not_eat_the_ceiling_it_is_exempt_from(pool: _Pool):
    _priced()
    guest = _Guest()
    for _ in range(config.settings.runs_per_session * 2):
        await quota.record(guest, kind="pantry", meter=_meter(), duration_ms=900, started_at=NOW)
        await quota.record(guest, kind="bar", meter=_meter(), duration_ms=900, started_at=NOW)

    state = await quota.look(guest, now=NOW)
    assert quota.seen(guest.owner) == 0
    assert state.headline.startswith(
        f"прогонів: 0 з {config.settings.runs_per_session} у цій сесії, "
        f"0 з {config.settings.runs_per_day} за добу"
    )
    assert (await quota.guard(guest, now=NOW)).allowed


async def test_the_money_of_the_pantry_is_counted_even_though_the_runs_are_not(
    pool: _Pool,
):
    _priced()
    guest = _Guest()
    await quota.record(guest, kind="pantry", meter=_meter(), duration_ms=900, started_at=NOW)

    state = await quota.look(guest, now=NOW)
    counted = await spend.counters(
        pool,
        account=ACCOUNT,
        owner=guest.owner,
        since=day_start(NOW),
        kinds=RUN_KINDS,
        offbudget=OFFBUDGET_KINDS,
    )
    assert counted.day_runs == 0
    assert counted.day_usd > 0
    assert counted.total_usd > 0
    assert state.allowed


async def test_the_warming_does_not_close_the_day_it_paid_for(pool: _Pool):
    _priced()
    config.settings.budget_day_usd = Decimal("0.10")
    guest = _Guest()
    await spend.record(
        pool,
        account="",
        owner="komora-warm",
        kind="warm",
        model=MODEL,
        tokens_in=900_000,
        tokens_out=300_000,
        cost_usd=Decimal("0.90"),
        duration_ms=151_000,
        started_at=NOW,
    )

    state = await quota.look(guest, now=NOW)
    assert state.allowed
    assert await quota.model_gate(guest, "клієнт-моделі") is not None


async def test_the_warming_still_counts_against_the_money_of_the_project(pool: _Pool):
    _priced()
    config.settings.budget_total_usd = Decimal("0.10")
    guest = _Guest()
    await spend.record(
        pool,
        account="",
        owner="komora-warm",
        kind="warm",
        model=MODEL,
        tokens_in=900_000,
        tokens_out=300_000,
        cost_usd=Decimal("0.90"),
        duration_ms=151_000,
        started_at=NOW,
    )

    counted = await spend.counters(
        pool,
        account=ACCOUNT,
        owner=guest.owner,
        since=day_start(NOW),
        kinds=RUN_KINDS,
        offbudget=OFFBUDGET_KINDS,
    )
    assert counted.day_usd == 0
    assert counted.day_offbudget_usd == Decimal("0.90")
    assert counted.total_usd == Decimal("0.90")

    state = await quota.look(guest, now=NOW)
    assert not state.allowed
    assert state.scope == "budget-total"


async def test_the_money_taken_out_of_the_day_says_so_on_the_screen(pool: _Pool):
    _priced()
    guest = _Guest()
    await spend.record(
        pool,
        account="",
        owner="komora-warm",
        kind="warm",
        model=MODEL,
        tokens_in=600_000,
        tokens_out=200_000,
        cost_usd=Decimal("0.60"),
        duration_ms=151_000,
        started_at=NOW,
    )

    state = await quota.look(guest, now=NOW)
    assert "$0.60" in state.headline
    assert "поза добовою стелею" in state.headline


async def test_a_refusal_of_the_project_model_pushes_the_guest_to_their_own_key(pool: _Pool):
    _priced()
    meter = _meter()
    meter.payer = "project"
    meter.down = "mistral: 402"
    with pytest.raises(HTTPException) as refused:
        async with quota.counted(_Guest(), kind="basket", meter=meter):
            pass
    assert refused.value.status_code == 402
    assert "ключ OpenAI" in str(refused.value.detail)


async def test_a_refusal_on_the_guests_own_key_is_the_guests_business(pool: _Pool):
    _priced()
    meter = _meter()
    meter.payer = "guest"
    meter.down = "luna: 401"
    async with quota.counted(_Guest(), kind="basket", meter=meter):
        pass


async def test_a_kind_the_ceiling_does_not_count_cannot_pass_the_gate(pool: _Pool):
    _priced()
    with pytest.raises(RuntimeError, match="COUNTED_RUNS"):
        async with quota.counted(_Guest(), kind="pantry", meter=_meter()):
            pass  # pragma: no cover — сюди не доходить


async def test_a_silent_counter_does_not_take_the_pantry_down_with_it(
    monkeypatch: pytest.MonkeyPatch,
):
    _priced()
    monkeypatch.setattr("komora.api.quota.get_pool", _DeadPool)
    assert await quota.model_gate(_Guest(), "клієнт-моделі") == "клієнт-моделі"


def _client(pool_obj: object) -> TestClient:
    app.dependency_overrides[require_guest] = _Guest
    return TestClient(app)


def test_the_screen_shows_the_numbers_before_the_ceiling_fires(
    monkeypatch: pytest.MonkeyPatch,
):
    _priced()
    made = _Pool()
    monkeypatch.setattr("komora.api.quota.get_pool", lambda: made)
    try:
        answer = _client(None).get("/api/quota").json()
    finally:
        app.dependency_overrides.clear()

    assert answer["blocked"] is False
    assert answer["scope"] is None
    assert "0 з 6" in answer["headline"]
    assert answer["left"] == 6
    assert answer["contact"] is None


def test_the_screen_carries_the_contact_only_when_it_is_needed(
    monkeypatch: pytest.MonkeyPatch,
):
    _priced()
    made = _Pool()
    monkeypatch.setattr("komora.api.quota.get_pool", lambda: made)
    for _ in range(config.settings.runs_per_session):
        quota.bump(_Guest.owner)

    try:
        answer = _client(None).get("/api/quota").json()
    finally:
        app.dependency_overrides.clear()

    assert answer["blocked"] is True
    assert answer["scope"] == "session"
    assert answer["action"]
    assert answer["contact"] == config.settings.contact


def test_a_silent_counter_says_so_instead_of_emptying_the_screen(
    monkeypatch: pytest.MonkeyPatch,
):
    _priced()
    monkeypatch.setattr("komora.api.quota.get_pool", _DeadPool)
    try:
        answer = _client(None).get("/api/quota").json()
    finally:
        app.dependency_overrides.clear()

    assert answer["blocked"] is False
    assert "не знаю" in answer["headline"] or "мовчить" in answer["headline"]


def test_the_basket_refuses_with_the_same_words_the_screen_shows(
    monkeypatch: pytest.MonkeyPatch,
):
    _priced()
    made = _Pool()
    monkeypatch.setattr("komora.api.quota.get_pool", lambda: made)
    for _ in range(config.settings.runs_per_session):
        quota.bump(_Guest.owner)

    try:
        client = _client(None)
        shown = client.get("/api/quota").json()
        refused = client.post("/api/basket", json={"source": "list"})
    finally:
        app.dependency_overrides.clear()

    assert refused.status_code == 429
    assert shown["headline"] in refused.json()["detail"]
    assert shown["action"] in refused.json()["detail"]


class _CrowdPool(_Pool):

    @asynccontextmanager
    async def connection(self, **_: Any):
        for _ in range(10):
            await asyncio.sleep(0)
        yield _Conn(self.rows)


@pytest.fixture
def crowd(monkeypatch: pytest.MonkeyPatch) -> _CrowdPool:
    made = _CrowdPool()
    monkeypatch.setattr("komora.api.quota.get_pool", lambda: made)
    return made


class _Waiting:

    def __init__(self) -> None:
        self.gate = asyncio.Event()
        self.admitted: list[int] = []
        self.refused: list[tuple[int, int]] = []

    @property
    def inside(self) -> int:
        return len(self.admitted)

    async def one(self, guest: object, tag: int = 0, *, boom: Exception | None = None) -> None:
        try:
            async with quota.counted(guest, kind="basket", meter=_meter()):  # type: ignore[arg-type]
                self.admitted.append(tag)
                await self.gate.wait()
                if boom is not None:
                    raise boom
        except HTTPException as exc:
            self.refused.append((tag, exc.status_code))

    async def all_at_once(self, *runs: Any) -> None:
        tasks = [asyncio.create_task(run) for run in runs]
        for _ in range(200):
            await asyncio.sleep(0)
            if self.inside + len(self.refused) == len(tasks):
                break
        self.gate.set()
        await asyncio.gather(*tasks)


async def test_parallel_builds_do_not_all_pass_on_the_same_numbers(crowd: _CrowdPool):
    _priced()
    guest = _Guest()
    places = config.settings.runs_per_session
    waiting = _Waiting()

    await waiting.all_at_once(*(waiting.one(guest, tag) for tag in range(places + 3)))

    assert waiting.admitted == list(range(places))
    assert waiting.refused == [(places, 429), (places + 1, 429), (places + 2, 429)]
    assert len(crowd.rows.rows) == places


async def test_the_last_place_goes_to_whoever_asked_first(crowd: _CrowdPool):
    _priced()
    config.settings.runs_per_session = 2
    guest = _Guest()
    await quota.record(guest, kind="basket", meter=_meter(), duration_ms=900, started_at=NOW)

    waiting = _Waiting()
    await waiting.all_at_once(*(waiting.one(guest, tag) for tag in range(3)))

    assert waiting.admitted == [0], "вільне місце було одне — воно й мало дістатись першому"
    assert waiting.refused == [(1, 429), (2, 429)]


async def test_the_gate_does_not_count_its_own_place_against_itself(pool: _Pool):
    _priced()
    config.settings.runs_per_session = 1
    guest = _Guest()

    async with quota.counted(guest, kind="basket", meter=_meter()):
        assert quota.flying(guest) == (1, 1)

    assert len(pool.rows.rows) == 1


async def test_the_place_is_freed_after_the_row_is_written_not_before(pool: _Pool):
    _priced()
    guest = _Guest()
    seen_while_writing: list[tuple[int, int]] = []
    real = spend.record

    async def watched(*args: Any, **kwargs: Any) -> None:
        seen_while_writing.append(quota.flying(guest))
        await real(*args, **kwargs)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr("komora.api.quota.spend.record", watched)
        async with quota.counted(guest, kind="basket", meter=_meter()):
            pass

    assert seen_while_writing == [(1, 1)]
    assert quota.flying(guest) == (0, 0)


async def test_a_refused_run_gives_its_place_back(pool: _Pool):
    _priced()
    config.settings.runs_per_session = 0
    guest = _Guest()

    with pytest.raises(HTTPException):
        async with quota.counted(guest, kind="basket", meter=_meter()):
            pass

    assert quota.flying(guest) == (0, 0)
    assert not pool.rows.rows, "відмова не прогін — рядка в базі бути не має"


async def test_a_crashed_run_gives_its_place_back_and_still_counts(pool: _Pool):
    _priced()
    guest = _Guest()
    waiting = _Waiting()

    with suppress(RuntimeError):
        await waiting.all_at_once(waiting.one(guest, boom=RuntimeError("MCP упав")))
    assert waiting.admitted == [0]

    assert quota.flying(guest) == (0, 0)
    assert len(pool.rows.rows) == 1
    assert pool.rows.rows[0]["ok"] is False


async def test_a_silent_counter_gives_the_place_back_too(
    monkeypatch: pytest.MonkeyPatch,
):
    _priced()
    monkeypatch.setattr("komora.api.quota.get_pool", _DeadPool)
    guest = _Guest()

    with pytest.raises(HTTPException) as caught:
        async with quota.counted(guest, kind="basket", meter=_meter()):
            pass

    assert caught.value.status_code == 503
    assert quota.flying(guest) == (0, 0)


async def test_without_a_model_key_no_place_is_taken_at_all(pool: _Pool):
    config.settings.bedrock_api_key = None
    guest = _Guest()

    async with quota.counted(guest, kind="basket", meter=_meter()) as verdict:
        assert quota.flying(guest) == (0, 0)

    assert verdict.allowed
    assert not pool.rows.rows


async def test_the_day_queue_is_keyed_by_the_account_not_by_the_session(pool: _Pool):
    _priced()

    class _Second(_Guest):
        owner = "друга-сесія"

    first, second = _Guest(), _Second()
    async with (
        quota.counted(first, kind="basket", meter=_meter()),
        quota.counted(second, kind="basket", meter=_meter()),
    ):
        assert quota.flying(first) == (1, 2), "доба в них спільна, сесії різні"
        assert quota.flying(second) == (1, 2)

    assert quota.flying(first) == (0, 0)


async def test_a_guest_without_a_profile_queues_by_session_not_by_nobody(pool: _Pool):
    _priced()

    class _Nameless(_Guest):
        account = ""

    class _AlsoNameless(_Nameless):
        owner = "інша-сесія-без-профілю"

    guest, other = _Nameless(), _AlsoNameless()
    async with quota.counted(guest, kind="basket", meter=_meter()):
        assert quota.flying(guest) == (1, 1)
        assert quota.flying(other) == (0, 0), "безакаунтні стоять у різних чергах"

    assert quota.flying(guest) == (0, 0)


async def test_the_day_counter_asks_about_the_session_when_there_is_no_account(
    pool: _Pool,
):
    _priced()

    class _Nameless(_Guest):
        account = ""

    guest = _Nameless()
    await quota.record(guest, kind="basket", meter=_meter(), duration_ms=900, started_at=NOW)

    state = await quota.look(guest, now=NOW)
    assert state.headline == "прогонів: 1 з 6 у цій сесії, 1 з 12 за добу"


async def test_a_freed_place_leaves_no_trace_in_memory(pool: _Pool):
    _priced()
    guest = _Guest()

    async with quota.counted(guest, kind="basket", meter=_meter()):
        assert quota._LIVE_SESSION and quota._LIVE_DAY

    assert quota._LIVE_SESSION == {}
    assert quota._LIVE_DAY == {}


def test_the_duration_of_a_run_is_written_in_milliseconds():
    started = NOW.replace(tzinfo=UTC)
    passed = quota.elapsed_ms(datetime.now(UTC) - timedelta(seconds=2))
    assert 1500 <= passed <= 4000
    assert quota.elapsed_ms(started) > 10**6, "давнє минуле не може бути кількома мс"


async def test_leaving_does_not_free_a_place_still_held(pool: _Pool):
    _priced()
    guest = _Guest()

    async with quota.counted(guest, kind="basket", meter=_meter()):
        quota.forget(guest.owner)
        assert quota.flying(guest) == (1, 1)

    assert quota.flying(guest) == (0, 0)


async def test_the_screen_counts_every_place_including_the_one_asking(pool: _Pool):
    _priced()
    guest = _Guest()

    async with quota.counted(guest, kind="basket", meter=_meter()):
        state = await quota.look(guest, now=NOW)
        assert state.headline == (
            "прогонів: 0 з 6 у цій сесії, 0 з 12 за добу · у роботі ще 1 прогін — місце вже зайняте"
        )
        assert state.left == 5


async def test_the_toll_counts_the_pantry_and_the_basket_as_one_wallet(pool: _Pool):
    _priced()
    for kind, tokens in (("pantry", 40_000), ("basket", 20_000)):
        await spend.record(
            pool,
            account=ACCOUNT,
            owner="власник-сесії",
            kind=kind,
            model=MODEL,
            tokens_in=tokens,
            tokens_out=1_000,
            cost_usd=Decimal("0.010000"),
            duration_ms=1_000,
            started_at=NOW,
        )

    answer = _client(pool).get("/api/quota").json()
    app.dependency_overrides.clear()

    toll = answer["toll"]
    assert toll["runs"] == 2
    assert toll["usd"] == pytest.approx(0.02)
    assert toll["tokensIn"] == 60_000
    assert toll["tokensOut"] == 2_000


async def test_the_toll_survives_a_day_boundary_because_its_axis_is_the_login(pool: _Pool):
    _priced()
    await spend.record(
        pool,
        account=ACCOUNT,
        owner="власник-сесії",
        kind="basket",
        model=MODEL,
        tokens_in=10_000,
        tokens_out=500,
        cost_usd=Decimal("0.005000"),
        duration_ms=1_000,
        started_at=NOW - timedelta(days=3),
    )

    answer = _client(pool).get("/api/quota").json()
    app.dependency_overrides.clear()

    assert answer["toll"]["runs"] == 1
    assert answer["toll"]["usd"] == pytest.approx(0.005)


async def test_the_toll_stays_silent_about_money_it_could_not_price(pool: _Pool):
    _priced()
    await spend.record(
        pool,
        account=ACCOUNT,
        owner="власник-сесії",
        kind="basket",
        model="модель-без-прайсу",
        tokens_in=7_000,
        tokens_out=800,
        cost_usd=None,
        duration_ms=1_000,
        started_at=NOW,
    )

    answer = _client(pool).get("/api/quota").json()
    app.dependency_overrides.clear()

    assert answer["toll"]["usd"] is None
    assert answer["toll"]["unpriced"] == 1
    assert answer["toll"]["tokensIn"] == 7_000


async def test_the_toll_names_the_money_the_day_ceiling_does_not_count(pool: _Pool):
    _priced()
    await spend.record(
        pool,
        account=ACCOUNT,
        owner="власник-сесії",
        kind="basket",
        model="gpt-5.6-luna",
        tokens_in=9_000,
        tokens_out=700,
        cost_usd=Decimal("0.004000"),
        duration_ms=1_000,
        started_at=NOW,
        payer="guest",
    )

    answer = _client(pool).get("/api/quota").json()
    app.dependency_overrides.clear()

    assert answer["toll"]["usd"] == pytest.approx(0.004)
    assert answer["toll"]["guestUsd"] == pytest.approx(0.004)


def test_the_toll_says_nothing_when_the_counter_is_down(monkeypatch: pytest.MonkeyPatch):
    _priced()
    monkeypatch.setattr("komora.api.quota.get_pool", lambda: _DeadPool())
    try:
        answer = _client(None).get("/api/quota").json()
    finally:
        app.dependency_overrides.clear()

    assert answer["toll"] is None


def test_the_login_sums_are_cut_by_the_login_and_by_nothing_else():
    lines = [
        line
        for line in spend._COUNTERS.splitlines()
        if "login_usd" in line or "login_tokens" in line or "login_runs" in line
    ]
    assert len(lines) == 4, "усі чотири суми входу мусять лишатись однорядковими"
    for line in lines:
        for narrower in ("since", "kind", "payer"):
            assert narrower not in line, (
                f"сума за вхід звужена по `{narrower}` — це вже інша вісь, "
                "а підпис на екрані лишився старим"
            )
