from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi import HTTPException

from komora.agent.llm import Meter
from komora.api import app as api
from komora.config import Settings
from komora.core import models

APP_SRC = Path(api.__file__).read_text(encoding="utf-8")


def test_bez_kliucha_model_hostia_vidmovliaie_sloavamy(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(HTTPException) as caught:
        api._run_llm(models.LUNA, api_key=None, meter=Meter())
    assert caught.value.status_code == 402
    assert "ключ" in caught.value.detail


def _root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "web" / "src" / "App.svelte").exists():
            return parent
    raise AssertionError("не знайшов корінь репозиторію")


def _key_refusal_text() -> str:
    tree = ast.parse(APP_SRC)
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "_run_llm":
            continue
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Call):
                continue
            words = {w.arg: w.value for w in inner.keywords}
            code = words.get("status_code")
            detail = words.get("detail")
            if (
                isinstance(code, ast.Constant)
                and code.value == 402
                and isinstance(detail, ast.Constant)
            ):
                return str(detail.value)
    raise AssertionError("у `_run_llm` немає відмови 402 з текстом")


def test_rechennia_vidmovy_odne_na_servi_i_na_ekrani() -> None:
    screen = (_root() / "web" / "src" / "App.svelte").read_text(encoding="utf-8")
    assert _key_refusal_text() in screen


def _refusals_with(code: int) -> set[str]:
    found: set[str] = set()
    for path in sorted(Path(api.__file__).parents[1].rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            for inner in ast.walk(node):
                if not isinstance(inner, ast.Call):
                    continue
                for word in inner.keywords:
                    if (
                        word.arg == "status_code"
                        and isinstance(word.value, ast.Constant)
                        and word.value.value == code
                    ):
                        found.add(node.name)
    return found


def test_402_u_produkti_odyn_i_tse_vorota_a_ne_perelik() -> None:
    assert _refusals_with(402) == {"_run_llm", "counted"}


def test_z_kliuchem_hostia_zapyt_ide_v_openai_a_ne_na_bedrock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: dict[str, str] = {}

    def fake(*, model: str, base_url: str, api_key: str, meter: Meter) -> str:
        seen.update(model=model, base_url=base_url, api_key=api_key)
        return "порт"

    monkeypatch.setattr(api, "build_llm", fake)
    monkeypatch.setattr(
        api, "settings", Settings(OPENAI_BASE_URL="https://api.openai.com", _env_file=None)
    )
    api._run_llm(models.LUNA, api_key="sk-гостя", meter=Meter())
    assert seen == {
        "model": models.LUNA,
        "base_url": "https://api.openai.com",
        "api_key": "sk-гостя",
    }


def test_nasha_model_kliucha_hostia_ne_torkaietsia(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, str] = {}

    def fake(*, model: str, base_url: str, api_key: str, meter: Meter) -> str:
        seen.update(api_key=api_key)
        return "порт"

    monkeypatch.setattr(api, "build_llm", fake)
    monkeypatch.setattr(
        api,
        "settings",
        Settings(ANTHROPIC_API_KEY="наш-ключ", _env_file=None),
    )
    api._run_llm(models.MISTRAL_LARGE, api_key="sk-гостя", meter=Meter())
    assert seen["api_key"] == "наш-ключ"


def test_bez_nashoho_kliucha_konveier_ide_bez_ahenta(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(api, "settings", Settings(ANTHROPIC_API_KEY=None, _env_file=None))
    assert api._run_llm(None, api_key=None, meter=Meter()) is None


def _handlers_calling(name: str) -> set[str]:
    tree = ast.parse(APP_SRC)
    found: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Name)
                and inner.func.id == name
            ):
                found.add(node.name)
    return found


def test_model_hostia_dokhodyt_lyshe_do_ioho_vlasnoho_prohonu() -> None:
    assert _handlers_calling("_run_llm") == {"build_basket", "refill_basket", "checkout"}


def test_nazyvannia_vydiv_ide_serverna_model() -> None:
    tree = ast.parse(APP_SRC)
    seen: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        source = ast.unparse(node)
        if "build_llm" not in source:
            continue
        seen.add(node.name)
        assert "settings.bedrock_model_id" in source, node.name

    assert seen == {
        "_pantry_now",
        "adjust_pantry",
        "_bar_now",
        "compose_next_list",
        "loop_pantry",
    }
