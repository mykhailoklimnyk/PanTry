from __future__ import annotations

import hashlib
import re
from base64 import urlsafe_b64encode

from komora.auth.pkce import (
    ENTROPY_BYTES,
    challenge_for,
    fingerprint,
    random_token,
    same_secret,
    start,
)

RFC_VERIFIER = re.compile(r"^[A-Za-z0-9\-._~]{43,128}$")


def test_verifier_matches_the_rfc_alphabet_and_length():
    assert RFC_VERIFIER.fullmatch(start().verifier)


def test_state_is_the_same_shape():
    assert RFC_VERIFIER.fullmatch(start().state)


def test_no_padding_leaks_into_the_url():
    handshake = start()
    assert "=" not in handshake.verifier + handshake.state + handshake.challenge


def test_every_handshake_is_new():
    states = {start().state for _ in range(100)}
    assert len(states) == 100


def test_verifier_and_state_are_not_the_same_secret():
    handshake = start()
    assert handshake.verifier != handshake.state


def test_challenge_is_sha256_not_the_verifier_itself():
    handshake = start()
    assert handshake.challenge != handshake.verifier

    expected = urlsafe_b64encode(hashlib.sha256(handshake.verifier.encode()).digest())
    assert handshake.challenge == expected.decode().rstrip("=")


def test_challenge_is_stable_for_the_same_verifier():
    assert challenge_for("abc") == challenge_for("abc")


def test_challenge_changes_with_the_verifier():
    assert challenge_for("abc") != challenge_for("abd")


def test_entropy_is_not_quietly_lowered():
    assert ENTROPY_BYTES >= 32
    assert len(random_token()) == 43


def test_fingerprint_hides_the_secret_it_covers():
    secret = random_token()
    assert secret not in fingerprint(secret)


def test_fingerprint_is_stable_and_distinguishing():
    a, b = random_token(), random_token()
    assert fingerprint(a) == fingerprint(a)
    assert fingerprint(a) != fingerprint(b)


def test_secret_comparison_accepts_equal_and_rejects_near_miss():
    value = random_token()
    assert same_secret(value, value)
    assert not same_secret(value, value[:-1] + ("A" if value[-1] != "A" else "B"))


def test_comparison_survives_non_ascii_input():
    assert not same_secret(random_token(), "чужий стан")
    assert same_secret("той самий", "той самий")
