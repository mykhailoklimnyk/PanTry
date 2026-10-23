from __future__ import annotations

import hmac
from collections import OrderedDict
from dataclasses import dataclass, replace
from uuid import uuid4

from komora.agent.basket import Assembled
from komora.agent.cart import CartRun
from komora.api.schemas import Basket

MAX_RUNS = 8

MAX_TOTAL = MAX_RUNS * 32


@dataclass(frozen=True, slots=True)
class _Kept:
    owner: str
    run: Assembled | CartRun


_RUNS: OrderedDict[str, _Kept] = OrderedDict()


def remember(run: Assembled | CartRun, *, owner: str) -> Basket:
    plan = run.assembled if isinstance(run, CartRun) else run
    run_id = uuid4().hex
    _RUNS[run_id] = _Kept(owner=owner, run=run)
    _evict(owner)
    return plan.basket.model_copy(update={"run_id": run_id})


def _evict(owner: str) -> None:
    mine = [run_id for run_id, kept in _RUNS.items() if kept.owner == owner]
    for run_id in mine[: max(0, len(mine) - MAX_RUNS)]:
        del _RUNS[run_id]
    while len(_RUNS) > MAX_TOTAL:
        _RUNS.popitem(last=False)


def recall(run_id: str, *, owner: str) -> Assembled | CartRun | None:
    kept = _RUNS.get(run_id)
    if kept is None or not hmac.compare_digest(kept.owner, owner):
        return None
    _RUNS.move_to_end(run_id)
    return _unshared(kept.run)


def _unshared(run: Assembled | CartRun) -> Assembled | CartRun:
    plan = run.assembled if isinstance(run, CartRun) else run
    copied = replace(plan, lines=[replace(line) for line in plan.lines])
    return replace(run, assembled=copied) if isinstance(run, CartRun) else copied


def forget(owner: str) -> None:
    for run_id in [run_id for run_id, kept in _RUNS.items() if kept.owner == owner]:
        del _RUNS[run_id]


def forget_all() -> None:
    _RUNS.clear()
