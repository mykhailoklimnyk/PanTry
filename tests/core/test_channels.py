from decimal import Decimal

from komora.core.channels import (
    BranchScope,
    Channel,
    admissible,
    is_admissible,
    needs_forecast,
)

EXPRESS = Channel(
    name="Експрес",
    lead_time_hours=1,
    scope=BranchScope.OWN,
    min_order_cost=Decimal(0),
    max_weight_kg=None,
    carries_perishables=True,
)
PICKUP = Channel(
    name="SelfPickup",
    lead_time_hours=2,
    scope=BranchScope.ANY,
    min_order_cost=Decimal(199),
    max_weight_kg=None,
    carries_perishables=True,
)
HOME = Channel(
    name="DeliveryHome",
    lead_time_hours=48,
    scope=BranchScope.OWN,
    min_order_cost=Decimal(599),
    max_weight_kg=Decimal(50),
    carries_perishables=True,
)
NOVA_POSHTA = Channel(
    name="NovaPoshta",
    lead_time_hours=72,
    scope=BranchScope.HUB,
    min_order_cost=Decimal(0),
    max_weight_kg=None,
    carries_perishables=False,
)

ALL = (NOVA_POSHTA, HOME, PICKUP, EXPRESS)


def test_channel_that_arrives_in_time_is_admissible():
    assert is_admissible(HOME, hours_until_runout=96) is True


def test_channel_that_is_too_slow_is_not():
    assert is_admissible(NOVA_POSHTA, hours_until_runout=24) is False


def test_buffer_is_counted_not_ignored():
    assert is_admissible(HOME, hours_until_runout=48) is False
    assert is_admissible(HOME, hours_until_runout=60) is True


def test_buffer_is_configurable():
    assert is_admissible(HOME, hours_until_runout=50, buffer_hours=0) is True


def test_nova_poshta_never_carries_perishables():
    assert is_admissible(NOVA_POSHTA, hours_until_runout=1000, perishable=True) is False
    assert is_admissible(NOVA_POSHTA, hours_until_runout=1000, perishable=False) is True


def test_unknown_deadline_does_not_reject_a_channel():
    assert is_admissible(NOVA_POSHTA, hours_until_runout=None) is True


def test_admissible_sorts_fastest_first():
    result = admissible(ALL, hours_until_runout=1000)
    assert [c.name for c in result] == ["Експрес", "SelfPickup", "DeliveryHome", "NovaPoshta"]


def test_admissible_filters_out_the_slow_ones():
    result = admissible(ALL, hours_until_runout=24)
    assert [c.name for c in result] == ["Експрес", "SelfPickup"]


def test_admissible_of_nothing_is_empty():
    assert admissible([], hours_until_runout=100) == ()


def test_perishable_filter_applies_to_the_whole_list():
    result = admissible(ALL, hours_until_runout=1000, perishable=True)
    assert "NovaPoshta" not in [c.name for c in result]


def test_slow_channels_exist_only_thanks_to_the_forecast():
    assert needs_forecast(NOVA_POSHTA) is True
    assert needs_forecast(HOME) is True
    assert needs_forecast(EXPRESS) is False
    assert needs_forecast(PICKUP) is False


def test_pickup_reaches_any_branch():
    assert PICKUP.scope is BranchScope.ANY
    assert HOME.scope is BranchScope.OWN
    assert NOVA_POSHTA.scope is BranchScope.HUB


def test_pickup_has_no_weight_limit():
    assert PICKUP.max_weight_kg is None
    assert HOME.max_weight_kg == Decimal(50)
