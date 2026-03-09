import pytest

from openrecall.server import api


@pytest.mark.unit
def test_get_search_engine_rejects_noop_mode(monkeypatch):
    monkeypatch.setattr(api.settings, "processing_mode", "noop")
    if hasattr(api, "_search_engine"):
        monkeypatch.setattr(api, "_search_engine", None)

    with pytest.raises(RuntimeError):
        api.get_search_engine()


@pytest.mark.unit
def test_get_search_engine_lazy_singleton(monkeypatch):
    monkeypatch.setattr(api.settings, "processing_mode", "active")
    created = {"count": 0}

    class FakeSearchEngine:
        def __init__(self):
            created["count"] += 1

    monkeypatch.setattr(api, "SearchEngine", FakeSearchEngine)
    if hasattr(api, "_search_engine"):
        monkeypatch.setattr(api, "_search_engine", None)

    first = api.get_search_engine()
    second = api.get_search_engine()

    assert created["count"] == 1
    assert first is second
