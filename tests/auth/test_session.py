from __future__ import annotations

from base64 import urlsafe_b64encode
from datetime import UTC, datetime, timedelta

import pytest

from komora.auth.crypto import SealError, generate_key, seal
from komora.auth.session import (
    COOKIE_NAME,
    MAX_AGE_DAYS,
    GuestSession,
    expires_from,
    from_token_response,
    pack,
    unpack,
)

NOW = datetime(2026, 8, 15, 12, 0, tzinfo=UTC)
ACCESS = "5Zq8Xw-токен-гостя"
REFRESH = "rt-9f2-оновлення"


@pytest.fixture
def key() -> str:
    return generate_key()


def full() -> GuestSession:
    return GuestSession(
        access=ACCESS,
        refresh=REFRESH,
        expires_at=NOW + timedelta(days=30),
        issued_at=NOW,
        branch_id="2043",
    )


def test_session_survives_the_round_trip(key):
    restored = unpack(pack(full(), key=key), key=key)
    assert restored == full()


def test_cookie_shows_neither_token(key):
    cookie = pack(full(), key=key)
    assert ACCESS not in cookie
    assert REFRESH not in cookie
    assert "2043" not in cookie


def test_cookie_is_url_safe(key):
    cookie = pack(full(), key=key)
    assert cookie.isascii()
    assert not set(cookie) & set(' ,;"\\=')


def test_cookie_fits_with_room_to_spare(key):
    assert len(pack(full(), key=key)) < 1024


def test_a_forged_cookie_is_rejected(key):
    outsider = pack(full(), key=generate_key())
    with pytest.raises(SealError):
        unpack(outsider, key=key)


def test_a_tampered_cookie_is_rejected(key):
    cookie = pack(full(), key=key)
    broken = cookie[:-4] + ("AAAA" if cookie[-4:] != "AAAA" else "BBBB")
    with pytest.raises(SealError):
        unpack(broken, key=key)


def test_garbage_cookie_is_named_not_crashed(key):
    with pytest.raises(SealError, match="base64url"):
        unpack("це не cookie", key=key)


def test_valid_cipher_without_a_token_is_still_refused(key):
    empty = pack(GuestSession(access="x"), key=key)
    assert unpack(empty, key=key).access == "x"

    forged = seal('{"a": ""}', key=key)
    with pytest.raises(SealError, match="немає токена"):
        unpack(urlsafe_b64encode(forged).decode().rstrip("="), key=key)


def test_optional_fields_stay_optional(key):
    lean = GuestSession(access=ACCESS)
    restored = unpack(pack(lean, key=key), key=key)
    assert restored.refresh is None
    assert restored.expires_at is None
    assert restored.branch_id is None


def test_session_without_expiry_never_counts_as_expired():
    assert not GuestSession(access=ACCESS).expired(NOW)


def test_expiry_is_compared_against_the_moment_we_pass_in():
    session = GuestSession(access=ACCESS, expires_at=NOW)
    assert session.expired(NOW), "рівно в момент протухання токен уже не діє"
    assert not session.expired(NOW - timedelta(seconds=1))


def test_stale_turns_on_at_half_life_not_at_the_last_day():
    session = GuestSession(access=ACCESS, refresh=REFRESH, issued_at=NOW,
                           expires_at=NOW + timedelta(days=30))
    assert not session.stale(NOW + timedelta(days=14))
    assert session.stale(NOW + timedelta(days=15))
    assert session.stale(NOW + timedelta(days=28))


def test_stale_never_fires_without_both_moments():
    assert not GuestSession(access=ACCESS, expires_at=NOW + timedelta(days=30)).stale(NOW)
    assert not GuestSession(access=ACCESS, issued_at=NOW).stale(NOW)


def test_renewable_only_while_the_current_token_still_works():
    session = GuestSession(access=ACCESS, refresh=REFRESH, issued_at=NOW,
                           expires_at=NOW + timedelta(days=30))
    assert session.renewable(NOW + timedelta(days=20))
    assert not session.renewable(NOW + timedelta(days=1)), "ще рано"
    assert not session.renewable(NOW + timedelta(days=31)), "вже пізно, тут лише логін"


def test_renewable_needs_something_to_renew_with():
    without = GuestSession(access=ACCESS, issued_at=NOW, expires_at=NOW + timedelta(days=30))
    assert not without.renewable(NOW + timedelta(days=20))


def test_expires_from_turns_seconds_into_a_moment():
    assert expires_from(2592000, now=NOW) == NOW + timedelta(days=30)


def test_expires_from_keeps_silence_silent():
    assert expires_from(None, now=NOW) is None
    assert expires_from(0, now=NOW) is None


def test_cookie_name_is_host_locked():
    assert COOKIE_NAME.startswith("__Host-")


def test_cookie_does_not_outlive_the_token():
    assert MAX_AGE_DAYS <= 30


def test_token_response_becomes_a_session():
    session = from_token_response(
        {"access_token": ACCESS, "refresh_token": REFRESH, "expires_in": 2592000}, now=NOW
    )
    assert session.access == ACCESS
    assert session.refresh == REFRESH
    assert session.issued_at == NOW
    assert session.expires_at == NOW + timedelta(days=30)


def test_renewal_keeps_the_old_refresh_when_none_comes_back():
    before = GuestSession(access="старий", refresh=REFRESH, branch_id="2043", issued_at=NOW)
    after = from_token_response(
        {"access_token": "новий", "expires_in": 2592000},
        now=NOW + timedelta(days=20),
        previous=before,
    )
    assert after.access == "новий"
    assert after.refresh == REFRESH
    assert after.branch_id == "2043", "філія не має стосунку до токена"


def test_token_response_without_a_token_is_refused():
    with pytest.raises(SealError, match="немає access_token"):
        from_token_response({"error": "invalid_grant"}, now=NOW)


def test_owner_survives_a_renewal():
    first = from_token_response({"access_token": "t1", "expires_in": 60}, now=NOW)
    renewed = from_token_response(
        {"access_token": "t2", "expires_in": 60}, now=NOW + timedelta(days=15), previous=first
    )

    assert renewed.access != first.access
    assert renewed.owner == first.owner


def test_a_fresh_login_is_a_different_owner():
    one = from_token_response({"access_token": "t1"}, now=NOW)
    two = from_token_response({"access_token": "t1"}, now=NOW)

    assert one.owner != two.owner, "власник має бути випадковим, а не похідним від токена"


def test_owner_rides_the_cookie():
    key = generate_key()
    guest = from_token_response({"access_token": ACCESS, "expires_in": 60}, now=NOW)

    assert unpack(pack(guest, key=key), key=key).owner == guest.owner


def test_owner_is_never_empty():
    assert GuestSession(access="токен").owner
    assert GuestSession(access="токен").owner == GuestSession(access="токен").owner
    assert GuestSession(access="токен").owner != GuestSession(access="інший").owner
