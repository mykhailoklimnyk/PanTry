from __future__ import annotations

import pytest

from komora.auth.crypto import KEY_BYTES, NONCE_BYTES, SealError, generate_key, seal, unseal

TOKEN = "eyJhbGciOiJI.токен-гостя.підпис"


@pytest.fixture
def key() -> str:
    return generate_key()


def test_sealed_token_round_trips(key):
    assert unseal(seal(TOKEN, key=key), key=key) == TOKEN


def test_plaintext_does_not_show_through(key):
    sealed = seal(TOKEN, key=key)
    assert b"guest" not in sealed
    assert "токен-гостя".encode() not in sealed


def test_same_token_seals_differently_every_time(key):
    first, second = seal(TOKEN, key=key), seal(TOKEN, key=key)
    assert first != second
    assert unseal(first, key=key) == unseal(second, key=key) == TOKEN


def test_tampered_ciphertext_raises_instead_of_returning_garbage(key):
    sealed = bytearray(seal(TOKEN, key=key))
    sealed[-1] ^= 0x01
    with pytest.raises(SealError, match="не розшифровується"):
        unseal(bytes(sealed), key=key)


def test_tampered_nonce_raises_too(key):
    sealed = bytearray(seal(TOKEN, key=key))
    sealed[0] ^= 0x01
    with pytest.raises(SealError):
        unseal(bytes(sealed), key=key)


def test_another_key_cannot_open_it(key):
    with pytest.raises(SealError, match="змінився KOMORA_SESSION_KEY"):
        unseal(seal(TOKEN, key=key), key=generate_key())


def test_truncated_record_is_named_not_indexed(key):
    with pytest.raises(SealError, match="коротший за nonce"):
        unseal(seal(TOKEN, key=key)[:NONCE_BYTES], key=key)


def test_key_of_wrong_length_is_refused():
    with pytest.raises(SealError, match=str(KEY_BYTES)):
        seal(TOKEN, key="c2hvcnQ")


def test_key_that_is_not_base64_is_refused():
    with pytest.raises(SealError, match="base64url"):
        seal(TOKEN, key="це точно не base64!!")


def test_generated_key_is_usable_as_is():
    fresh = generate_key()
    assert unseal(seal("x", key=fresh), key=fresh) == "x"


def test_two_generated_keys_differ():
    assert generate_key() != generate_key()


def test_empty_token_still_round_trips(key):
    assert unseal(seal("", key=key), key=key) == ""
