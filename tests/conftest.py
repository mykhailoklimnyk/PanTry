import pytest

import komora.config as config
from komora.agent import aisle, basket, kinds, sanity
from komora.api import history, quota
from komora.core.trace import SUMMARY_CHARS, fits

_CLEAN = config.Settings.model_construct()


@pytest.fixture(autouse=True)
def _clean_settings():
    saved = dict(config.settings.__dict__)
    config.settings.__dict__.update(_CLEAN.__dict__)
    yield
    config.settings.__dict__.clear()
    config.settings.__dict__.update(saved)


@pytest.fixture(autouse=True)
def _clean_process_caches():
    kinds.forget_tree()
    quota.forget_all()
    basket._INTENT_CACHE.clear()
    basket.forget_keeps()
    sanity.forget_sense()
    aisle.forget_aisles()
    history.forget_all()
    yield
    kinds.forget_tree()
    quota.forget_all()
    basket._INTENT_CACHE.clear()
    basket.forget_keeps()
    sanity.forget_sense()
    aisle.forget_aisles()
    history.forget_all()


@pytest.fixture(autouse=True)
def _short_trace_phrases(request, monkeypatch):
    if request.node.get_closest_marker("long_summary"):
        return
    original = basket.Tracer.add

    def add(self, step_id, tool, args, summary, **kw):
        assert fits(summary), (
            f"крок {step_id}: фраза {len(summary)} символів при стелі "
            f"{SUMMARY_CHARS} -- перелік їде в args, у фразі лишаються числа "
            f"(#301): {summary}"
        )
        return original(self, step_id, tool, args, summary, **kw)

    monkeypatch.setattr(basket.Tracer, "add", add)
