from __future__ import annotations


def plural(count: int, one: str, few: str, many: str) -> str:
    tail, hundred = abs(count) % 10, abs(count) % 100
    if tail == 1 and hundred != 11:
        return one
    if tail in (2, 3, 4) and hundred not in (12, 13, 14):
        return few
    return many


def rows(count: int) -> str:
    return plural(count, "рядок", "рядки", "рядків")


__all__ = ["plural", "rows"]
