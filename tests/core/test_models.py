from __future__ import annotations

from komora.core import models


def test_luna_hodyt_na_kliuchi_hostia_a_mistral_na_nashomu() -> None:
    assert models.needs_guest_key(models.LUNA) is True
    assert models.needs_guest_key(models.MISTRAL_LARGE) is False


def test_nevidoma_model_vvazhaietsia_nashoiu() -> None:
    assert models.needs_guest_key("mistral.devstral-2-123b") is False
    assert models.payer_of("хтозна-що") == "project"


def test_platnyk_ie_funktsiieiu_vid_modeli() -> None:
    assert models.payer_of(models.LUNA) == "guest"
    assert models.payer_of(models.MISTRAL_LARGE) == "project"


def test_shvydkyi_rezhym_zamovchuietsia_po_riznomu_dvom_modeliam() -> None:
    assert models.fast_by_default(models.MISTRAL_LARGE) is True
    assert models.fast_by_default(models.LUNA) is True


def test_slovo_hostia_syl_nishe_za_zamovchuvannia_modeli() -> None:
    assert models.batches_for(models.MISTRAL_LARGE, fast=False, fallback=9) == 2
    assert models.batches_for(models.LUNA, fast=True, fallback=9) == 2


def test_ne_torkanyi_peremykach_bere_zamovchuvannia_modeli() -> None:
    assert models.batches_for(models.MISTRAL_LARGE, fast=None, fallback=9) == 2
    assert models.batches_for(models.LUNA, fast=None, fallback=9) == 2


def test_poza_zamiryanymy_vyrishuie_env_a_ne_my() -> None:
    assert models.supports_fast("anthropic.claude-opus-5") is False
    assert models.batches_for("anthropic.claude-opus-5", fast=True, fallback=3) == 3
    assert models.batches_for("anthropic.claude-opus-5", fast=None, fallback=1) == 1


def test_rekomendovani_ne_povtoriuiutsia_i_maiut_pidpysy() -> None:
    ids = [row.id for row in models.RECOMMENDED]
    assert len(ids) == len(set(ids))
    assert all(row.label and row.note for row in models.RECOMMENDED)


def test_haiku_v_rekomendovanykh_nemaie() -> None:
    assert not any("haiku" in row.id for row in models.RECOMMENDED)


def test_komora_slukhaie_toi_samyi_peremykach_ale_ne_te_same_chyslo() -> None:
    assert models.batches_for(models.LUNA, fast=None, fallback=2) == 2
    assert models.pantry_batches_for(models.LUNA, fast=None, fallback=2) == 2


def test_vymknenyi_peremykach_vymykaie_pachky_i_v_komori() -> None:
    assert models.pantry_batches_for(models.MISTRAL_LARGE, fast=False, fallback=2) == 2
    assert models.pantry_batches_for(models.MISTRAL_LARGE, fast=True, fallback=2) == 2
    assert models.pantry_batches_for(models.MISTRAL_LARGE, fast=None, fallback=2) == 2


def test_env_lyshaietsia_verkhnim_chyslom_a_ne_dviikoiu_v_kodi() -> None:
    assert models.pantry_batches_for(models.MISTRAL_LARGE, fast=True, fallback=3) == 3
    assert models.pantry_batches_for(models.MISTRAL_LARGE, fast=False, fallback=3) == 3
