from __future__ import annotations

import pytest

from komora.core import orders
from komora.core.orders import Stage


@pytest.mark.parametrize(
    ("status", "stage"),
    [
        ("new", Stage.NEW),
        ("collecting", Stage.COLLECTING),
        ("collected", Stage.COLLECTED),
        ("delivery_in_progress", Stage.DELIVERING),
        ("received", Stage.RECEIVED),
        ("canceled", Stage.CANCELED),
    ],
)
def test_every_status_seen_alive_has_its_step(status: str, stage: Stage):
    assert orders.stage_of(status) is stage


@pytest.mark.parametrize("status", ["cancelled", "packing", "", None, "  "])
def test_a_status_we_never_saw_stays_unknown(status: str | None):
    assert orders.stage_of(status) is Stage.UNKNOWN


def test_case_and_spaces_do_not_invent_a_new_status():
    assert orders.stage_of(" Collecting ") is Stage.COLLECTING
