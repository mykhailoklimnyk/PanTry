from decimal import Decimal

from komora.core.channels import BranchScope, Channel
from komora.core.sourcing import BranchStock, Resolution, resolve
from komora.core.substitution import Alternative, Source

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

HERE = "branch-home"
THERE = "branch-neighbour"

CHAIN = (
    Alternative(
        external_product_id="1025388",
        name="Молоко Feels good Protein",
        source=Source.HISTORY,
    ),
)


def test_in_stock_here_wins():
    plan = resolve(home_branch=BranchStock(HERE, stock=59, available=True))
    assert plan.resolution is Resolution.IN_STOCK
    assert plan.branch_id == HERE
    assert "59" in plan.reason


def test_low_stock_is_flagged_but_still_taken_here():
    plan = resolve(home_branch=BranchStock(HERE, stock=4, available=True))
    assert plan.resolution is Resolution.IN_STOCK
    assert "мало" in plan.reason


def test_open_branch_with_nothing_on_the_shelf_is_not_a_source():
    plan = resolve(
        home_branch=BranchStock(HERE, stock=0, available=True),
        other_branches=[BranchStock(THERE, stock=40, available=True)],
        channels=[PICKUP],
        hours_until_runout=72,
    )
    assert plan.resolution is Resolution.OTHER_BRANCH
    assert plan.branch_id == THERE


def test_stock_in_a_branch_that_does_not_serve_us_is_not_a_source():
    plan = resolve(
        home_branch=BranchStock(HERE, stock=59, available=False),
        other_branches=[BranchStock(THERE, stock=7, available=False)],
    )
    assert plan.resolution is not Resolution.IN_STOCK
    assert plan.branch_id != THERE


def test_neighbour_branch_beats_substitution():
    plan = resolve(
        home_branch=BranchStock(HERE, stock=0, available=False),
        other_branches=[BranchStock(THERE, stock=149, available=True)],
        channels=[PICKUP, HOME],
        chain=CHAIN,
        hours_until_runout=72,
    )
    assert plan.resolution is Resolution.OTHER_BRANCH
    assert plan.branch_id == THERE
    assert plan.channel is not None and plan.channel.name == "SelfPickup"


def test_the_richest_neighbour_is_chosen():
    plan = resolve(
        home_branch=BranchStock(HERE, stock=0, available=False),
        other_branches=[
            BranchStock("branch-a", stock=4, available=True),
            BranchStock("branch-b", stock=149, available=True),
        ],
        channels=[PICKUP],
        hours_until_runout=72,
    )
    assert plan.branch_id == "branch-b"


def test_pickup_out_of_reach_falls_to_another_channel():
    slow_pickup = Channel(
        name="SelfPickup",
        lead_time_hours=100,
        scope=BranchScope.ANY,
        min_order_cost=Decimal(199),
        max_weight_kg=None,
        carries_perishables=True,
    )
    plan = resolve(
        home_branch=BranchStock(HERE, stock=0, available=False),
        other_branches=[BranchStock(THERE, stock=20, available=True)],
        channels=[slow_pickup, HOME],
        chain=CHAIN,
        hours_until_runout=72,
    )
    assert plan.resolution is Resolution.OTHER_CHANNEL
    assert plan.channel is not None and plan.channel.name == "DeliveryHome"


def test_substitution_is_the_last_resort_not_the_first():
    plan = resolve(
        home_branch=BranchStock(HERE, stock=0, available=False),
        other_branches=[],
        channels=[PICKUP, HOME],
        chain=CHAIN,
        hours_until_runout=72,
    )
    assert plan.resolution is Resolution.SUBSTITUTE
    assert plan.substitute is not None
    assert plan.substitute.name == "Молоко Feels good Protein"


def test_nothing_at_all_is_said_plainly():
    plan = resolve(home_branch=BranchStock(HERE, stock=0, available=False))
    assert plan.resolution is Resolution.UNAVAILABLE
    assert plan.substitute is None


def test_urgent_item_cannot_use_a_slow_channel():
    plan = resolve(
        home_branch=BranchStock(HERE, stock=0, available=False),
        other_branches=[BranchStock(THERE, stock=30, available=True)],
        channels=[HOME],
        chain=CHAIN,
        hours_until_runout=6,
    )
    assert plan.resolution is Resolution.SUBSTITUTE


def test_every_plan_carries_a_human_reason():
    plans = [
        resolve(home_branch=BranchStock(HERE, stock=5, available=True)),
        resolve(home_branch=BranchStock(HERE, stock=0, available=False)),
        resolve(
            home_branch=BranchStock(HERE, stock=0, available=False),
            other_branches=[BranchStock(THERE, stock=9, available=True)],
            channels=[PICKUP],
            hours_until_runout=72,
        ),
    ]
    assert all(plan.reason for plan in plans)
