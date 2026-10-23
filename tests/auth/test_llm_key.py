from __future__ import annotations

import pytest

from komora.auth import llm_key
from komora.auth.crypto import SealError, generate_key


def test_kliuch_vertaietsia_z_cookie_tym_samym() -> None:
    secret = generate_key()
    sealed = llm_key.pack("sk-abc123", key=secret)
    assert llm_key.unpack(sealed, key=secret) == "sk-abc123"

def test_sam_kliuch_u_cookie_ne_vydno() -> None:
    secret = generate_key()
    assert "sk-abc123" not in llm_key.pack("sk-abc123", key=secret)

def test_chuzhym_kliuchem_ne_rozibraty() -> None:
    sealed = llm_key.pack("sk-abc123", key=generate_key())
    with pytest.raises(SealError):
        llm_key.unpack(sealed, key=generate_key())

def test_probily_z_bufera_znimaiutsia() -> None:
    assert llm_key.tidy("  sk-abc\n123 ") == "sk-abc123"

@pytest.mark.parametrize("bad", ["", "просто текст", "SK-abc", "sk-" + "x" * 600])
def test_ne_kliuch_ne_liahaie_v_cookie(bad: str) -> None:
    assert llm_key.looks_like_key(bad) is False

def test_obydvi_zhyvi_formy_kliucha_prokhodiat() -> None:
    assert llm_key.looks_like_key("sk-" + "a" * 45) is True
    assert llm_key.looks_like_key("sk-proj-" + "a" * 60) is True
