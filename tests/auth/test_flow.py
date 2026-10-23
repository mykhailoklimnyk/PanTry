from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from komora.auth.crypto import SealError, generate_key
from komora.auth.flow import COOKIE_NAME, TTL, pack, start, unpack, verify
from komora.auth.pkce import start as handshake

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)


@pytest.fixture
def key() -> str:
    return generate_key()


def make():
    return start(handshake(), return_to="/cart", now=NOW)


def test_flow_survives_the_round_trip(key):
    flow = make()
    assert unpack(pack(flow, key=key), key=key) == flow


def test_verifier_is_not_readable_in_the_cookie(key):
    flow = make()
    assert flow.verifier not in pack(flow, key=key)


def test_matching_state_passes(key):
    flow = make()
    verify(flow, state=flow.state, now=NOW)


def test_foreign_state_is_refused():
    flow = make()
    with pytest.raises(SealError, match="не на наш запит"):
        verify(flow, state="чужий", now=NOW)


def test_almost_right_state_is_refused_too():
    flow = make()
    with pytest.raises(SealError):
        verify(flow, state=flow.state[:-1], now=NOW)


def test_late_answer_is_refused():
    flow = make()
    with pytest.raises(SealError, match="час на вхід минув"):
        verify(flow, state=flow.state, now=NOW + TTL)


def test_expiry_is_checked_before_state():
    flow = make()
    with pytest.raises(SealError, match="час на вхід минув"):
        verify(flow, state="байдуже", now=NOW + TTL + timedelta(seconds=1))


def test_window_is_wide_enough_for_a_human_and_no_wider():
    assert timedelta(minutes=5) <= TTL <= timedelta(minutes=15)


def test_forged_flow_cookie_is_rejected(key):
    outsider = pack(make(), key=generate_key())
    with pytest.raises(SealError):
        unpack(outsider, key=key)


def test_incomplete_flow_cookie_is_rejected(key):
    from base64 import urlsafe_b64encode

    from komora.auth.crypto import seal

    lame = urlsafe_b64encode(seal('{"s":"st"}', key=key)).decode().rstrip("=")
    with pytest.raises(SealError, match="неповна"):
        unpack(lame, key=key)


def test_return_to_defaults_to_the_root(key):
    from base64 import urlsafe_b64encode

    from komora.auth.crypto import seal

    payload = '{"s":"st","v":"vr","e":"2026-08-15T12:10:00+00:00"}'
    cookie = urlsafe_b64encode(seal(payload, key=key)).decode().rstrip("=")
    assert unpack(cookie, key=key).return_to == "/"


def test_flow_cookie_is_a_different_one_from_the_session():
    from komora.auth.session import COOKIE_NAME as SESSION_COOKIE

    assert COOKIE_NAME != SESSION_COOKIE
    assert COOKIE_NAME.startswith("__Host-")
