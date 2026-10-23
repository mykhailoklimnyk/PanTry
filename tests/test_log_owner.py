from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import structlog
from fastapi import HTTPException, Request
from structlog.testing import capture_logs

from komora.api.auth_routes import require_guest
from komora.auth import session
from komora.logging import get_logger

log = get_logger(__name__)

CONTEXT = [structlog.contextvars.merge_contextvars]


def _request(cookie: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/pantry",
            "headers": [(b"cookie", f"{session.COOKIE_NAME}={cookie}".encode())],
        }
    )


@pytest.fixture(autouse=True)
def clean() -> None:
    structlog.contextvars.clear_contextvars()
    yield
    structlog.contextvars.clear_contextvars()


def _packed(monkeypatch: pytest.MonkeyPatch, *, account: str) -> Request:
    guest = session.GuestSession(
        access="живий-токен",
        refresh="живий-refresh",
        owner="власник-сесії-довгий-рядок",
        account=account,
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    monkeypatch.setattr("komora.api.auth_routes.read_session", lambda _request: guest)
    return _request("байдуже")


async def test_the_log_line_carries_the_guest(monkeypatch: pytest.MonkeyPatch) -> None:
    await require_guest(_packed(monkeypatch, account="відбиток-акаунта"))

    with capture_logs(CONTEXT) as written:
        log.info("щось сталось")

    assert written[0]["owner"] == "власник-"
    assert written[0]["account"] == "відбиток"


async def test_no_secret_reaches_the_log(monkeypatch: pytest.MonkeyPatch) -> None:
    await require_guest(_packed(monkeypatch, account="відбиток-акаунта"))

    with capture_logs(CONTEXT) as written:
        log.info("щось сталось")

    line = written[0]
    assert "живий-токен" not in str(line)
    assert "живий-refresh" not in str(line)
    assert len(line["owner"]) == 8
    assert len(line["account"]) == 8


async def test_an_account_we_do_not_know_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    await require_guest(_packed(monkeypatch, account=""))

    with capture_logs(CONTEXT) as written:
        log.info("щось сталось")

    assert written[0]["account"] == "невідомий"


async def test_a_guest_who_did_not_pass_signs_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("komora.api.auth_routes.read_session", lambda _request: None)

    with pytest.raises(HTTPException):
        await require_guest(_request("зіпсована"))

    with capture_logs(CONTEXT) as written:
        log.info("щось сталось")

    assert "owner" not in written[0]
