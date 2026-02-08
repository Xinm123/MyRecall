"""Regression tests for SearchEngine.search_debug rendering compatibility."""

from types import SimpleNamespace

from openrecall.server.search.engine import SearchEngine


def test_search_debug_handles_video_frame_only_rows():
    """search_debug should render rows even when snapshot is absent."""
    engine = SearchEngine.__new__(SearchEngine)

    def _fake_search_impl(user_query: str, limit: int = 50):
        return [
            {
                "snapshot": None,
                "source": "video_frame",
                "video_data": {
                    "frame_id": 12,
                    "timestamp": 1700000000.0,
                    "app_name": "Terminal",
                    "window_name": "bash",
                    "text_snippet": "git status",
                },
                "score": 0.42,
                "debug": {
                    "combined_rank": 0,
                    "vector_score": 0.0,
                    "fts_boost": 0.3,
                },
            }
        ]

    engine._search_impl = _fake_search_impl  # type: ignore[attr-defined]

    rows = engine.search_debug("git", limit=10)

    assert len(rows) == 1
    assert rows[0]["id"] == "vframe:12"
    assert rows[0]["image_url"] == "/api/v1/frames/12"
    assert rows[0]["description"] == "git status"


def test_search_impl_debug_logging_handles_video_only_candidates(monkeypatch):
    """_search_impl should not crash when only video-frame candidates exist."""
    import openrecall.server.search.engine as engine_module

    engine = SearchEngine.__new__(SearchEngine)
    engine.query_parser = SimpleNamespace(
        parse=lambda _q: SimpleNamespace(
            text="cursor",
            mandatory_keywords=[],
            start_time=None,
            end_time=None,
        )
    )
    engine.embedding_provider = SimpleNamespace(embed_text=lambda _q: [0.1, 0.2])
    engine.vector_store = SimpleNamespace(search=lambda *_a, **_k: [])
    engine.reranker = SimpleNamespace(compute_score=lambda _q, docs: [0.0] * len(docs))
    engine.sql_store = SimpleNamespace(
        search=lambda *_a, **_k: [],
        search_video_fts=lambda *_a, **_k: [
            {
                "frame_id": 101,
                "timestamp": 1700000000.0,
                "app_name": "Cursor",
                "window_name": "Editor",
                "text_snippet": "cursor settings",
                "score": -1.0,
            }
        ],
    )

    monkeypatch.setattr(engine_module.settings, "debug", True)
    results = engine._search_impl("cursor", limit=10)

    assert len(results) == 1
    assert results[0]["source"] == "video_frame"
    assert results[0]["video_data"]["frame_id"] == 101
