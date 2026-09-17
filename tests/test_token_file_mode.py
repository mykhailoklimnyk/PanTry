from __future__ import annotations

import importlib.util
import stat
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_mcp_login():
    spec = importlib.util.spec_from_file_location("mcp_login", ROOT / "scripts" / "mcp_login.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.skipif(sys.platform == "win32", reason="на Windows POSIX-біти нічого не захищають")
def test_token_file_is_created_owner_only(tmp_path):
    mcp_login = _load_mcp_login()
    token_file = tmp_path / ".mcp-token.json"

    storage = mcp_login.FileTokenStorage(token_file)
    storage._write({"tokens": {"access_token": "не-справжній"}})

    mode = stat.S_IMODE(token_file.stat().st_mode)
    assert mode == 0o600, f"токен створено з правами {oct(mode)} — читаний не лише власником"


@pytest.mark.skipif(sys.platform == "win32", reason="на Windows POSIX-біти нічого не захищають")
def test_rewrite_keeps_owner_only(tmp_path):
    mcp_login = _load_mcp_login()
    token_file = tmp_path / ".mcp-token.json"

    storage = mcp_login.FileTokenStorage(token_file)
    storage._write({"tokens": {"access_token": "перший"}})
    storage._write({"tokens": {"access_token": "другий"}})

    mode = stat.S_IMODE(token_file.stat().st_mode)
    assert mode == 0o600
