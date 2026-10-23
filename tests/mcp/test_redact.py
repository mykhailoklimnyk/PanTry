from __future__ import annotations

import json
import re

from komora.config import Settings
from komora.mcp.client import SilpoMCP
from komora.mcp.redact import (
    PLACEHOLDER,
    QUASI_IDENTIFIER_KEYS,
    SENSITIVE_KEYS,
    _mask_identifier,
    redact,
)


def test_sensitive_keys_replaced_with_placeholder():
    source = {"phone": "+380501234567", "email": "guest@example.com", "note": "лишити біля дверей"}
    cleaned = redact(source)
    assert cleaned["phone"] == PLACEHOLDER
    assert cleaned["email"] == PLACEHOLDER
    assert cleaned["note"] == "лишити біля дверей"


def test_every_sensitive_key_is_masked():
    source = {key: f"значення-{key}" for key in SENSITIVE_KEYS}
    cleaned = redact(source)
    assert all(value == PLACEHOLDER for value in cleaned.values())


def test_key_match_is_case_insensitive():
    source = {"Phone": "+380", "LOYALTYCARDNUMBER": "12345", "BranchId": "2043"}
    cleaned = redact(source)
    assert cleaned["Phone"] == PLACEHOLDER
    assert cleaned["LOYALTYCARDNUMBER"] == PLACEHOLDER
    assert cleaned["BranchId"].startswith("id:")


def test_nested_structures_are_cleaned_recursively():
    source = {
        "shipments": [
            {"address": {"street": "Хрещатик", "house": "1"}, "weight": 12.5},
            {"branchId": "2043", "items": ({"phone": "+380"},)},
        ]
    }
    cleaned = redact(source)
    first, second = cleaned["shipments"]
    assert first["address"] == PLACEHOLDER
    assert first["weight"] == 12.5
    assert second["branchId"].startswith("id:")
    assert second["items"][0]["phone"] == PLACEHOLDER


def test_address_parts_are_masked_in_both_shapes():
    saved = redact(
        {"city": "Вінниця", "street": "вулиця Соборна", "building": "1", "apartment": "2"}
    )
    found = redact({"city": "Київ", "street": "вулиця Хрещатик", "houseNumber": "30/1"})

    assert saved["street"] == saved["building"] == saved["apartment"] == PLACEHOLDER
    assert found["houseNumber"] == PLACEHOLDER
    assert saved["city"] == "Вінниця"


def test_quasi_identifiers_masked_but_stable():
    a = redact({"branchId": "2043"})
    b = redact({"branchId": "2043"})
    other = redact({"branchId": "777"})
    assert a["branchId"] == b["branchId"]
    assert a["branchId"] != other["branchId"]
    assert "2043" not in a["branchId"]


def test_every_quasi_identifier_key_is_masked():
    source = {key: "2043" for key in QUASI_IDENTIFIER_KEYS}
    cleaned = redact(source)
    assert all(value.startswith("id:") and "2043" not in value for value in cleaned.values())


def test_mask_is_deterministic_across_values():
    assert _mask_identifier("2043") == "id:45019027"
    assert redact({"branchId": "2043"})["branchId"] == "id:45019027"


BRANCHES = [str(2000 + n) for n in range(50)]


def test_mask_is_always_eight_digits():
    for branch in BRANCHES:
        masked = _mask_identifier(branch)
        assert re.fullmatch(r"id:\d{8}", masked), f"маска не за формою: {masked}"


def test_different_branches_get_different_masks():
    masked = {_mask_identifier(branch) for branch in BRANCHES}
    assert len(masked) == len(BRANCHES)


def test_redact_is_idempotent():
    source = {
        "phone": "+380501234567",
        "branchId": "2043",
        "shipments": [{"address": "Хрещатик 1", "lagerId": 123}],
    }
    once = redact(source)
    twice = redact(once)
    assert once == twice


def test_scalars_and_unknown_keys_pass_through():
    assert redact("молоко") == "молоко"
    assert redact(42) == 42
    assert redact(None) is None
    assert redact({"lagerId": 123, "quantity": 2}) == {"lagerId": 123, "quantity": 2}


def test_original_structure_is_not_mutated():
    source = {"phone": "+380", "items": [{"branchId": "2043"}]}
    redact(source)
    assert source["phone"] == "+380"
    assert source["items"][0]["branchId"] == "2043"


CANARY_PAYLOAD = {
    "phone": "+380501234567",
    "email": "family@example.com",
    "address": {"street": "Хрещатик", "house": "1", "latitude": 50.45, "longitude": 30.52},
    "loyaltyCardNumber": "9876543210",
    "branchId": "2043",
    "shipments": [{"address": "Хрещатик 1", "phone": "+380501234567"}],
    "items": [{"lagerId": 123, "quantity": 2}],
}

CANARY_VALUES = ("+380501234567", "family@example.com", "Хрещатик", "9876543210", "2043")


async def test_payload_holds_no_pii_from_fixture(tmp_path):
    (tmp_path / "silpo_get_my_profile.json").write_text(
        json.dumps(CANARY_PAYLOAD, ensure_ascii=False), encoding="utf-8"
    )
    async with SilpoMCP(settings=Settings.model_construct(), fixtures_dir=tmp_path) as mcp:
        outcome = await mcp.call("silpo_get_my_profile")

    flat = json.dumps(outcome.payload, ensure_ascii=False)
    for value in CANARY_VALUES:
        assert value not in flat, f"PII просочилось у payload: {value}"
    assert outcome.payload_raw["branchId"] == "2043"


async def test_pii_never_reaches_log_output(tmp_path, caplog):
    (tmp_path / "silpo_get_my_profile.json").write_text("{}", encoding="utf-8")

    with caplog.at_level("DEBUG"):
        async with SilpoMCP(settings=Settings.model_construct(), fixtures_dir=tmp_path) as mcp:
            await mcp.call("silpo_get_my_profile", {"phone": "+380501234567"})

    assert "+380501234567" not in caplog.text
