from __future__ import annotations

import os
from pathlib import Path

SHA_FILES = (
    Path(__file__).resolve().parents[2] / ".deployed-sha",
    Path(".deployed-sha"),
)


def deployed_sha(*, sha_file: Path | None = None, env: dict[str, str] | None = None) -> str | None:
    environ = os.environ if env is None else env

    from_env = (environ.get("KOMORA_COMMIT") or "").strip()
    if from_env:
        return from_env

    sources = SHA_FILES if sha_file is None else (sha_file,)
    for source in sources:
        try:
            sha = source.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if sha:
            return sha
    return None
