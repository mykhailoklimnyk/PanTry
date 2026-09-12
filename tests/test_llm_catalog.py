from komora.agent.llm.catalog import (
    NOTES,
    PINNED,
    SNAPSHOT,
    UNAVAILABLE,
    arrange,
    label_for,
)
from komora.api.app import list_models
from komora.config import Settings
from komora.core import models


def test_recommended_block_comes_first_and_in_its_own_order():
    ordered = arrange(SNAPSHOT)
    assert [m.id for m in ordered[:2]] == [row.id for row in models.RECOMMENDED]


def test_recommended_is_shown_even_when_bedrock_never_heard_of_it():
    ordered = {m.id: m for m in arrange(["mistral.devstral-2-123b"])}
    assert ordered[models.LUNA].available is True
    assert ordered[models.LUNA].note


def test_available_models_precede_unavailable():
    ordered = arrange(SNAPSHOT)
    flags = [m.available for m in ordered]
    assert flags == sorted(flags, reverse=True)


def test_claude_is_shown_but_unavailable():
    ordered = {m.id: m for m in arrange(SNAPSHOT)}
    claude = [m for m in ordered.values() if m.id.startswith("anthropic.")]
    assert claude, "Claude має бути в списку — показуємо, а не ховаємо"
    assert all(not m.available for m in claude)


def test_unknown_model_gets_its_id_without_provider_prefix():
    assert label_for("deepseek.v3.2") == "v3.2"
    assert label_for("qwen.qwen3-coder-next") == "qwen3-coder-next"


def test_duplicates_collapse():
    ordered = arrange([PINNED[0], PINNED[0], "deepseek.v3.2"])
    top = [row.id for row in models.RECOMMENDED]
    assert [m.id for m in ordered] == [*top, "deepseek.v3.2"]


def test_config_defaults_are_the_pinned_pair():
    defaults = Settings.model_construct()
    assert defaults.bedrock_model_id == PINNED[0]
    assert defaults.bedrock_model_cheap == PINNED[1]


def test_notes_never_dangle():
    assert set(NOTES) <= set(SNAPSHOT)


def test_unavailable_set_never_dangles():
    assert set(SNAPSHOT) >= UNAVAILABLE
    assert not UNAVAILABLE & set(PINNED)


def test_every_unavailable_model_explains_why():
    for entry in arrange(SNAPSHOT):
        if not entry.available:
            assert entry.note, entry.id


def test_snapshot_has_no_duplicates():
    assert len(SNAPSHOT) == len(set(SNAPSHOT))


async def test_endpoint_in_demo_serves_snapshot_with_active_default():
    options = await list_models()
    assert [o.id for o in options[:2]] == [row.id for row in models.RECOMMENDED]
    active = [o.id for o in options if o.active]
    assert active == [Settings.model_construct().bedrock_model_id]
    assert any(not o.available for o in options)
