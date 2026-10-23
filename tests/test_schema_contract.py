from __future__ import annotations

import inspect
import json
from decimal import Decimal

import pytest
from pydantic import BaseModel

from komora.api import schemas

RESPONSE_MODELS = [
    model
    for _, model in inspect.getmembers(schemas, inspect.isclass)
    if issubclass(model, BaseModel)
    and model is not BaseModel
    and not model.__name__.endswith("Request")
    and model.__name__ != "PantryAdjustment"
]


def _serialized_names(model: type[BaseModel]) -> set[str]:
    return {field.serialization_alias or name for name, field in model.model_fields.items()}


def test_response_models_found() -> None:
    assert len(RESPONSE_MODELS) >= 10


@pytest.mark.parametrize("model", RESPONSE_MODELS, ids=lambda m: m.__name__)
def test_no_snake_case_leaks_to_frontend(model: type[BaseModel]) -> None:
    leaked = sorted(name for name in _serialized_names(model) if "_" in name)
    assert not leaked, (
        f"{model.__name__} віддає {leaked} у snake_case — фронт читає camelCase. "
        "Потрібен serialization_alias."
    )


CRITICAL = {
    "CartLine": {
        "externalProductId",
        "basePrice",
        "saleNote",
        "weightKg",
        "imageUrl",
        "explanationDetail",
        "atRisk",
        "consideredTotal",
    },
    "Basket": {
        "runId",
        "declined",
        "baseTotal",
        "deliveryCost",
        "totalWeightKg",
        "topUp",
        "checkoutWebLink",
        "stats",
    },
    "RunStats": {"mcpCalls", "durationMs", "costUsd"},
    "TraceStep": {"durationMs", "resultSummary", "tagTone", "externalProductId"},
    "DeliveryOption": {"minOrder", "threshold", "maxWeightKg", "unavailableReason"},
    "ProductPick": {"externalProductId", "share"},
    "BarItem": {"daysSince", "usual", "priceFrom", "priceTo", "forkNote"},
    "PantryItem": {"usual", "state"},
    "Bar": {"items", "receipts", "kinds", "named", "trackedFrom"},
    "Place": {"branchId", "deliveryTypes", "note", "source", "saved"},
}


def test_place_source_mirrors_the_core_rule() -> None:
    from typing import get_args

    from komora.core.location import Source

    declared = set(get_args(schemas.Place.model_fields["source"].annotation))
    assert declared == {source.value for source in Source}


def test_decimal_reaches_frontend_as_json_number() -> None:
    pick = schemas.ProductPick(
        external_product_id="123", name="Молоко", share="4 з 4", price=Decimal("12.50")
    )
    dumped = json.loads(pick.model_dump_json())
    assert dumped["price"] == 12.5
    assert isinstance(dumped["price"], float), "Decimal поїхав рядком — фронт побачить NaN"


def test_all_decimal_fields_use_json_number() -> None:
    for model in RESPONSE_MODELS:
        for name, field in model.model_fields.items():
            blob = repr(field.annotation) + repr(field.metadata)
            if "Decimal" not in blob:
                continue
            assert "PlainSerializer" in blob, (
                f"{model.__name__}.{name}: Decimal без PlainSerializer — "
                "у JSON поїде рядком. Використай JsonNumber."
            )


@pytest.mark.parametrize("name, expected", sorted(CRITICAL.items()))
def test_critical_keys_exist(name: str, expected: set[str]) -> None:
    model = getattr(schemas, name)
    missing = expected - _serialized_names(model)
    assert not missing, (
        f"{name} більше не віддає {sorted(missing)}. "
        "Якщо поле перейменували — оновити web/src/lib/types.ts у тій самій правці."
    )


def test_an_unmeasured_step_is_null_and_a_measured_zero_stays_zero() -> None:
    common = {"id": "step-weight", "seq": 1, "tool": "core.weight", "args": {}}

    silent = schemas.TraceStep(**common, result_summary="вага кошика 3,2 кг")
    assert silent.duration_ms is None
    assert json.loads(silent.model_dump_json(by_alias=True))["durationMs"] is None

    fast = schemas.TraceStep(**common, duration_ms=0, result_summary="вага кошика 3,2 кг")
    assert json.loads(fast.model_dump_json(by_alias=True))["durationMs"] == 0


def test_a_refusal_is_a_separate_list_from_what_was_never_found() -> None:
    empty = schemas.Basket(
        run_id="live",
        lines=[],
        total=Decimal(0),
        delivery_cost=Decimal(0),
        total_weight_kg=Decimal(0),
        stats=schemas.RunStats(
            receipts=0,
            cycled=0,
            mcp_calls=0,
            duration_ms=0,
            cost_usd=Decimal(0),
            model="без агента",
        ),
    )
    assert empty.declined == []
    assert json.loads(empty.model_dump_json(by_alias=True))["declined"] == []

    said = schemas.Declined(intent="масло", why="фасовки 100 г під цей намір немає")
    dumped = json.loads(said.model_dump_json(by_alias=True))
    assert dumped == {"intent": "масло", "why": "фасовки 100 г під цей намір немає"}


def test_a_twin_the_agent_folded_names_itself_on_the_screen() -> None:
    empty = schemas.Basket(
        run_id="live",
        lines=[],
        total=Decimal(0),
        delivery_cost=Decimal(0),
        total_weight_kg=Decimal(0),
        stats=schemas.RunStats(
            receipts=0,
            cycled=0,
            mcp_calls=0,
            duration_ms=0,
            cost_usd=Decimal(0),
            model="без агента",
        ),
    )
    assert json.loads(empty.model_dump_json(by_alias=True))["twinsDropped"] == []

    folded = schemas.TwinsDropped(
        name="Томат Есміра рожевий",
        kept_name="Томат",
        why="агент каже: це одна потреба вдома",
    )
    assert json.loads(folded.model_dump_json(by_alias=True)) == {
        "name": "Томат Есміра рожевий",
        "keptName": "Томат",
        "why": "агент каже: це одна потреба вдома",
    }
