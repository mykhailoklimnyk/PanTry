from __future__ import annotations

from komora import config
from komora.api.app import _cold_run
from komora.api.schemas import BuildRequest

ACCOUNT = "власник"


class _Guest:

    def __init__(self, account: str = ACCOUNT) -> None:
        self.account = account
        self.owner = account


def test_any_guest_who_asks_for_a_cold_run_gets_one(monkeypatch) -> None:
    monkeypatch.setattr(config.settings, "insiders", "")
    assert _cold_run(_Guest(), True) is True


def test_an_insider_who_asks_for_a_cold_run_gets_one(monkeypatch) -> None:
    monkeypatch.setattr(config.settings, "insiders", ACCOUNT)
    assert _cold_run(_Guest(), True) is True


def test_nobody_gets_a_cold_run_without_asking(monkeypatch) -> None:
    monkeypatch.setattr(config.settings, "insiders", ACCOUNT)
    assert _cold_run(_Guest(), False) is False


def test_an_anonymous_guest_who_asks_gets_a_cold_run_too(monkeypatch) -> None:
    monkeypatch.setattr(config.settings, "insiders", "")
    assert _cold_run(_Guest(account=""), True) is True


def test_the_build_request_carries_the_flag_and_defaults_to_warm() -> None:
    assert BuildRequest().cold is False
    assert BuildRequest(cold=True).cold is True


def test_the_gate_replaces_the_flag_rather_than_remembering_it_apart() -> None:
    asked = BuildRequest(cold=True)
    ran = asked.model_copy(update={"cold": False})
    assert ran.cold is False
    assert asked.cold is True


def test_the_config_branch_is_the_last_rung_and_it_names_itself() -> None:
    from komora.core.location import Source, decide, source_note

    branch, source = decide(from_address=None, from_cart=None, from_config="конфіг")
    assert (branch, source) == ("конфіг", Source.CONFIG)
    said = source_note(source)
    assert "не за твоєю адресою" in said
    assert "назви адресу" in said


def test_no_branch_at_all_is_a_named_state_and_not_a_guess() -> None:
    from komora.core.location import Source, decide, source_note

    branch, source = decide(from_address=None, from_cart=None, from_config=None)
    assert branch is None
    assert source is Source.NONE
    assert "назви адресу" in source_note(source)
