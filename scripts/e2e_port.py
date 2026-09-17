from __future__ import annotations

import argparse
import shutil
import subprocess
import sys

PORT = 4174


def holders(port: int = PORT) -> list[int]:
    if sys.platform != "win32":
        found = subprocess.run(
            ["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
        )
        return [int(line) for line in found.stdout.split() if line.strip().isdigit()]
    found = subprocess.run(["netstat", "-ano"], capture_output=True, text=True)
    pids: list[int] = []
    for line in found.stdout.splitlines():
        parts = line.split()
        if (
            len(parts) >= 5
            and parts[0] == "TCP"
            and parts[3] == "LISTENING"
            and parts[1].endswith(f":{port}")
            and parts[4].isdigit()
        ):
            pids.append(int(parts[4]))
    return sorted(set(pids))


def started(name: str) -> str | None:
    if sys.platform != "win32":
        found = subprocess.run(["pgrep", "-fao", name], capture_output=True, text=True)
        first = found.stdout.strip().splitlines()
        return first[0].split(" ", 1)[0] if first else None
    found = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "Get-CimInstance Win32_Process | "
            "Where-Object { $_.CommandLine -like '*" + name + "*' } | "
            "Sort-Object CreationDate | Select-Object -First 1 | "
            "ForEach-Object { $_.CreationDate.ToString('yyyy-MM-dd HH:mm') }",
        ],
        capture_output=True,
        text=True,
    )
    return found.stdout.strip() or None


def kill(pid: int) -> None:
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/PID", str(pid), "/F", "/T"], capture_output=True)
    elif shutil.which("kill"):
        subprocess.run(["kill", "-9", str(pid)], capture_output=True)


def check(port: int = PORT, *, sweep: bool = True) -> int:
    busy = holders(port)
    if not busy:
        return 0
    since = started("playwright test")
    if since is not None:
        print(f"e2e не запускаю: порт {port} тримає прогін (pid {busy[0]}, з {since}).")
        print("Тести гонить інший процес -- дочекайся його або спини сам.")
        print("Прогін триває хвилини: старий час означає осиротіле дерево, а не роботу.")
        return 1
    if not sweep:
        print(f"порт {port} зайнятий (pid {', '.join(map(str, busy))}), прогін не крутиться")
        return 1
    for pid in busy:
        kill(pid)
    left = holders(port)
    if left:
        print(f"порт {port} не звільнився: лишились pid {', '.join(map(str, left))}.")
        return 1
    print(f"прибрано осиротілий сервер e2e: порт {port}, pid {', '.join(map(str, busy))}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Порт e2e: чи вільний і чиє те, що його тримає")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument(
        "--look",
        action="store_true",
        help="лише подивитись, нічого не прибирати",
    )
    said = parser.parse_args()
    return check(said.port, sweep=not said.look)


if __name__ == "__main__":
    raise SystemExit(main())
