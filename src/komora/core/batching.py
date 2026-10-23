from __future__ import annotations

from collections.abc import Sequence

from komora.core.queries import kind_words


def key(name: str) -> str:
    kind = kind_words(name)
    return (kind.split(" ")[0] if kind else name).strip().casefold()


def split(names: Sequence[str], parts: int) -> tuple[tuple[int, ...], ...]:
    if parts < 2 or len(names) < 2:
        return (tuple(range(len(names))),) if names else ()

    groups: dict[str, list[int]] = {}
    for index, name in enumerate(names):
        groups.setdefault(key(name), []).append(index)

    buckets: list[list[int]] = [[] for _ in range(min(parts, len(groups)))]
    for group in sorted(groups.values(), key=len, reverse=True):
        min(buckets, key=len).extend(group)

    return tuple(tuple(sorted(bucket)) for bucket in buckets)


def interleave[T](queues: Sequence[Sequence[T]]) -> tuple[T, ...]:
    return tuple(
        queue[rank]
        for rank in range(max((len(queue) for queue in queues), default=0))
        for queue in queues
        if rank < len(queue)
    )


__all__ = ["interleave", "key", "split"]
