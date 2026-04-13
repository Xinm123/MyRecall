"""
Tests for score field renaming in HybridSearchEngine.

Task 2: Rename score fields
- hybrid_score -> score
- fts_rank (BM25) -> fts_score
- fts_result_rank -> fts_rank
- vector mode: add score = cosine_score
"""
from unittest.mock import patch, MagicMock

from openrecall.server.search.hybrid_engine import HybridSearchEngine


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_engine():
    """Create a HybridSearchEngine instance bypassing __init__."""
    with patch.object(HybridSearchEngine, "__init__", lambda _: None):
        engine = HybridSearchEngine()
    return engine


def _make_fts_result(frame_id, fts_score_value=-1.5):
    """Return a minimal FTS result dict (as returned by FTS engine)."""
    return {
        "frame_id": frame_id,
        "fts_score": fts_score_value,  # BM25 score (renamed in Task 3)
        "score": fts_score_value,  # unified score
        "timestamp": "2026-01-01T00:00:00Z",
        "text": "sample text",
        "text_source": "ocr",
        "app_name": "TestApp",
        "window_name": "TestWindow",
        "browser_url": None,
        "focused": True,
        "device_name": "monitor_0",
        "file_path": f"{frame_id}.jpg",
        "tags": [],
        "embedding_status": "completed",
    }


# ---------------------------------------------------------------------------
# _hybrid_search field rename tests
# ---------------------------------------------------------------------------

class TestHybridSearchFieldRenames:
    """Verify that _hybrid_search output dict uses the new field names."""

    def _run_hybrid(self, frame_ids=("f1", "f2")):
        """
        Run _hybrid_search with mocked sub-components and return first result.
        """
        engine = _make_engine()

        fts_results = [_make_fts_result(fid, fts_score_value=-1.0 * (i + 1))
                       for i, fid in enumerate(frame_ids)]

        # Mock FTS engine
        mock_fts = MagicMock()
        mock_fts.search.return_value = (fts_results, len(fts_results))
        engine._fts_engine = mock_fts

        # Mock embedding store — return no vector results to keep it simple
        mock_emb_store = MagicMock()
        mock_emb_store.search_with_distance.return_value = []
        engine._embedding_store = mock_emb_store

        # Mock FramesStore.get_frames_by_ids
        frame_data = {
            fid: {
                "timestamp": "2026-01-01T00:00:00Z",
                "full_text": "hello world",
                "text_source": "ocr",
                "app_name": "TestApp",
                "window_name": "Win",
                "browser_url": None,
                "focused": True,
                "device_name": "monitor_0",
                "file_path": f"{fid}.jpg",
                "embedding_status": "completed",
            }
            for fid in frame_ids
        }

        mock_provider = MagicMock()
        mock_provider.embed_text.return_value = MagicMock(tolist=lambda: [0.1, 0.2])

        with patch(
            "openrecall.server.database.frames_store.FramesStore"
        ) as mock_fs_cls, patch(
            "openrecall.server.ai.factory.get_multimodal_embedding_provider",
            return_value=mock_provider,
        ):
            mock_fs_cls.return_value.get_frames_by_ids.return_value = frame_data
            results, _ = engine._hybrid_search(
                q="hello", fts_weight=0.5, vector_weight=0.5,
                limit=10, offset=0
            )

        return results

    def test_hybrid_result_has_score_not_hybrid_score(self):
        results = self._run_hybrid()
        assert len(results) > 0
        first = results[0]
        assert "score" in first, "Expected 'score' field in hybrid result"
        assert "hybrid_score" not in first, "Field 'hybrid_score' must be renamed to 'score'"

    def test_hybrid_result_has_fts_score_for_bm25(self):
        results = self._run_hybrid()
        assert len(results) > 0
        first = results[0]
        assert "fts_score" in first, "Expected 'fts_score' field (BM25 score) in hybrid result"

    def test_hybrid_result_has_fts_rank_for_rank(self):
        results = self._run_hybrid()
        assert len(results) > 0
        first = results[0]
        assert "fts_rank" in first, "Expected 'fts_rank' (positional rank) in hybrid result"
        assert "fts_result_rank" not in first, "Field 'fts_result_rank' must be renamed to 'fts_rank'"

    def test_fts_rank_is_int_for_rank_not_score(self):
        """fts_rank should be an integer (position), fts_score should be a float (BM25)."""
        results = self._run_hybrid()
        assert len(results) > 0
        # Check all results that have fts_rank set
        for r in results:
            if r.get("fts_rank") is not None:
                assert isinstance(r["fts_rank"], int), (
                    f"fts_rank should be int (position), got {type(r['fts_rank'])}"
                )
            if r.get("fts_score") is not None:
                assert isinstance(r["fts_score"], float), (
                    f"fts_score should be float (BM25), got {type(r['fts_score'])}"
                )


# ---------------------------------------------------------------------------
# _vector_only_search: add score field
# ---------------------------------------------------------------------------

class TestVectorOnlySearchScoreField:
    """Verify _vector_only_search output includes a unified 'score' field."""

    def _run_vector(self, frame_id="v1"):
        engine = _make_engine()

        # Fake embedding result
        mock_embedding = MagicMock()
        mock_embedding.frame_id = frame_id
        mock_embedding.timestamp = "2026-01-01T00:00:00Z"
        mock_embedding.app_name = "App"
        mock_embedding.window_name = "Win"

        cosine_distance = 0.2  # cosine_score = 1 - 0.2 = 0.8
        mock_emb_store = MagicMock()
        mock_emb_store.search_with_distance.return_value = [
            (mock_embedding, cosine_distance)
        ]
        engine._embedding_store = mock_emb_store

        frame_data = {
            frame_id: {
                "timestamp": "2026-01-01T00:00:00Z",
                "full_text": "vector text",
                "text_source": "ocr",
                "app_name": "App",
                "window_name": "Win",
                "browser_url": None,
                "focused": True,
                "device_name": "monitor_0",
                "file_path": f"{frame_id}.jpg",
                "embedding_status": "completed",
            }
        }

        mock_fs = MagicMock()
        mock_fs.get_frames_by_ids.return_value = frame_data

        mock_provider = MagicMock()
        mock_provider.embed_text.return_value = MagicMock(tolist=lambda: [0.1, 0.2])

        with patch(
            "openrecall.server.database.frames_store.FramesStore"
        ) as mock_fs_cls, patch(
            "openrecall.server.ai.factory.get_multimodal_embedding_provider",
            return_value=mock_provider,
        ):
            mock_fs_cls.return_value = mock_fs
            results, _ = engine._vector_only_search(
                q="test query",
                limit=10,
                offset=0,
            )
        return results

    def test_vector_result_has_score_field(self):
        results = self._run_vector()
        assert len(results) > 0
        first = results[0]
        assert "score" in first, "Expected 'score' field in vector-only result"
        # score should equal cosine_score (1 - 0.2 = 0.8)
        assert abs(first["score"] - 0.8) < 1e-6, (
            f"Expected score=0.8, got {first['score']}"
        )


# ---------------------------------------------------------------------------
# Task 3: FTS engine score field renaming
# ---------------------------------------------------------------------------

class TestFTSEngineScoreRenaming:
    """Verify FTS-only search returns fts_score (BM25) and score fields.

    Task 3: Rename fts_rank -> fts_score in FTS engine output, add score field.
    """

    def test_fts_result_has_fts_score_not_fts_rank(self):
        """FTS-only result should have fts_score (BM25), not fts_rank."""
        from openrecall.server.search.engine import SearchEngine
        from unittest.mock import patch, MagicMock

        # Create engine with mocked database
        engine = SearchEngine()

        # Mock a database connection that returns FTS results
        mock_conn = MagicMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda _, key: {
            "frame_id": 123,
            "timestamp": "2026-01-01T00:00:00Z",
            "full_text": "hello world",
            "app_name": "TestApp",
            "window_name": "TestWindow",
            "browser_url": None,
            "focused": 1,
            "device_name": "monitor_0",
            "text_source": "ocr",
            "embedding_status": "completed",
            "fts_rank": -1.5,  # BM25 score (negative, lower is better)
        }.get(key)
        mock_row.keys.return_value = [
            "frame_id", "timestamp", "full_text", "app_name", "window_name",
            "browser_url", "focused", "device_name", "text_source",
            "embedding_status", "fts_rank"
        ]

        # Mock count result
        mock_count_row = MagicMock()
        mock_count_row.__getitem__ = lambda _, key: 1 if key == "total" else 0

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [mock_row]
        mock_cursor.fetchone.return_value = mock_count_row
        mock_conn.execute.return_value = mock_cursor
        mock_conn.__enter__ = lambda _: _
        mock_conn.__exit__ = lambda _, *__: None

        with patch.object(engine, "_connect", return_value=mock_conn):
            results, _ = engine.search(q="hello", limit=10)

        assert len(results) == 1
        first = results[0]
        assert "fts_score" in first, "Expected 'fts_score' field (BM25 score) in FTS result"
        assert "fts_rank" not in first, "Field 'fts_rank' should be renamed to 'fts_score'"

    def test_fts_result_has_score_field(self):
        """FTS-only result should have a unified 'score' field."""
        from openrecall.server.search.engine import SearchEngine
        from unittest.mock import patch, MagicMock

        engine = SearchEngine()

        # Mock a database connection that returns FTS results
        mock_conn = MagicMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda _, key: {
            "frame_id": 456,
            "timestamp": "2026-01-01T00:00:00Z",
            "full_text": "test query",
            "app_name": "TestApp",
            "window_name": "TestWindow",
            "browser_url": None,
            "focused": 1,
            "device_name": "monitor_0",
            "text_source": "ocr",
            "embedding_status": "completed",
            "fts_rank": -2.0,  # BM25 score
        }.get(key)
        mock_row.keys.return_value = [
            "frame_id", "timestamp", "full_text", "app_name", "window_name",
            "browser_url", "focused", "device_name", "text_source",
            "embedding_status", "fts_rank"
        ]

        mock_count_row = MagicMock()
        mock_count_row.__getitem__ = lambda _, key: 1 if key == "total" else 0

        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [mock_row]
        mock_cursor.fetchone.return_value = mock_count_row
        mock_conn.execute.return_value = mock_cursor
        mock_conn.__enter__ = lambda _: _
        mock_conn.__exit__ = lambda _, *__: None

        with patch.object(engine, "_connect", return_value=mock_conn):
            results, _ = engine.search(q="test", limit=10)

        assert len(results) == 1
        first = results[0]
        assert "score" in first, "Expected 'score' field in FTS result"
        # score should equal fts_score (both are BM25)
        assert first["score"] == first["fts_score"], (
            f"score ({first['score']}) should equal fts_score ({first['fts_score']})"
        )
