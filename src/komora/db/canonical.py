from __future__ import annotations

import re

DOLLAR = re.compile(r"\$[A-Za-z_]*\$")


def canonical(sql: str) -> str:
    out: list[str] = []
    index = 0
    end = len(sql)

    def space() -> None:
        if out and out[-1] != " ":
            out.append(" ")

    while index < end:
        char = sql[index]

        if sql.startswith("--", index):
            line = sql.find("\n", index)
            index = end if line == -1 else line
            space()
            continue

        if sql.startswith("/*", index):
            depth = 1
            index += 2
            while index < end and depth:
                if sql.startswith("/*", index):
                    depth += 1
                    index += 2
                elif sql.startswith("*/", index):
                    depth -= 1
                    index += 2
                else:
                    index += 1
            space()
            continue

        if char in "'\"":
            stop = index + 1
            while stop < end:
                if sql[stop] == char:
                    if stop + 1 < end and sql[stop + 1] == char:
                        stop += 2
                        continue
                    stop += 1
                    break
                stop += 1
            out.append(sql[index:stop])
            index = stop
            continue

        if char == "$" and (opening := DOLLAR.match(sql, index)):
            tag = opening.group()
            closing = sql.find(tag, opening.end())
            stop = end if closing == -1 else closing + len(tag)
            out.append(sql[index:stop])
            index = stop
            continue

        if char.isspace():
            space()
            index += 1
            continue

        out.append(char)
        index += 1

    return "".join(out).strip()
