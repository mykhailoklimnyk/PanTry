from __future__ import annotations

import asyncio
import re
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from komora.api.schemas import TraceQuestion, TraceStep

MAX_CHANNELS = 64
DONE_TTL = timedelta(minutes=1)
STALE_TTL = timedelta(minutes=15)

KEY = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


@dataclass(slots=True)
class Asked:

    question: TraceQuestion
    event: asyncio.Event
    chosen: str | None = None


@dataclass(slots=True)
class Channel:
    owner: str
    opened_at: datetime
    steps: list[TraceStep] = field(default_factory=list)
    done: bool = False
    done_at: datetime | None = None
    asked: dict[str, Asked] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Progress:
    steps: tuple[TraceStep, ...]
    done: bool


_channels: OrderedDict[str, Channel] = OrderedDict()


def valid_key(key: str | None) -> bool:
    return bool(key) and KEY.match(key or "") is not None


def open_channel(key: str, *, owner: str, now: datetime | None = None) -> None:
    moment = now or datetime.now(UTC)
    _sweep(moment)
    _channels.pop(key, None)
    _channels[key] = Channel(owner=owner, opened_at=moment)
    while len(_channels) > MAX_CHANNELS:
        _channels.popitem(last=False)


def push(key: str, step: TraceStep) -> None:
    channel = _channels.get(key)
    if channel is None or channel.done:
        return
    channel.steps.append(step)
    if step.question is not None:
        channel.asked[step.question.id] = Asked(question=step.question, event=asyncio.Event())


def answer(key: str, *, owner: str, question_id: str, option_id: str) -> bool:
    channel = _channels.get(key)
    if channel is None or channel.owner != owner:
        return False
    asked = channel.asked.get(question_id)
    if asked is None or asked.chosen is not None:
        return False
    if not any(option.id == option_id for option in asked.question.options):
        return False
    asked.chosen = option_id
    asked.event.set()
    return True


async def wait(key: str, question_id: str, *, seconds: float) -> str | None:
    channel = _channels.get(key)
    asked = channel.asked.get(question_id) if channel is not None else None
    if asked is None:
        return None
    try:
        await asyncio.wait_for(asked.event.wait(), timeout=seconds)
    except TimeoutError:
        return None
    return asked.chosen


def finish(key: str, *, now: datetime | None = None) -> None:
    channel = _channels.get(key)
    if channel is not None:
        channel.done = True
        channel.done_at = now or datetime.now(UTC)


def read(key: str, *, owner: str, now: datetime | None = None) -> Progress | None:
    _sweep(now or datetime.now(UTC))
    channel = _channels.get(key)
    if channel is None or channel.owner != owner:
        return None
    return Progress(steps=tuple(channel.steps), done=channel.done)


def forget_all() -> None:
    _channels.clear()


def _sweep(now: datetime) -> None:
    dead = [
        key
        for key, channel in _channels.items()
        if (channel.done and channel.done_at is not None and now - channel.done_at > DONE_TTL)
        or (not channel.done and now - channel.opened_at > STALE_TTL)
    ]
    for key in dead:
        _channels.pop(key, None)


__all__ = [
    "DONE_TTL",
    "MAX_CHANNELS",
    "STALE_TTL",
    "Asked",
    "Progress",
    "answer",
    "finish",
    "forget_all",
    "open_channel",
    "push",
    "read",
    "valid_key",
    "wait",
]
