from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable, Coroutine, Iterable
from typing import Any

type LoopFactory = Callable[[], asyncio.AbstractEventLoop]


def loop_factory(platform: str = sys.platform) -> LoopFactory | None:
    return asyncio.SelectorEventLoop if platform == "win32" else None


def console(platform: str = sys.platform, streams: Iterable[object] | None = None) -> int:
    if platform != "win32":
        return 0
    fixed = 0
    for stream in (sys.stdout, sys.stderr) if streams is None else streams:
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        reconfigure(encoding="utf-8", errors="replace")
        fixed += 1
    return fixed


def run[T](coro: Coroutine[Any, Any, T], *, platform: str = sys.platform) -> T:
    console(platform)
    return asyncio.run(coro, loop_factory=loop_factory(platform))
