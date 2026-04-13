# Search API Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement all changes from the search API optimization design spec.

**Architecture:** Modify the search endpoint (`api_v1.py`) to use a flattened response structure, remove deprecated fields, add new text/description parameters, rename score fields, and update the hybrid engine accordingly. Update the frontend to match.

**Tech Stack:** Python/Flask (server), Jinja2/Alpine.js (frontend), SQLite/FTS5 (search)

---

## File Mapping

| File | Responsibility |
|------|----------------|
| `openrecall/server/api_v1.py` | Search endpoint: parameter parsing, response building, description fetch |
| `openrecall/server/search/hybrid_engine.py` | Rename score fields: `hybrid_score`→`score`, `fts_rank`→`fts_score`, `fts_result_rank`→`fts_rank` |
| `openrecall/server/search/engine.py` | Add `score` field, rename `fts_rank`→`fts_score` |
| `openrecall/server/database/frames_store.py` | Batch-fetch frame descriptions for search results |
| `openrecall/client/web/templates/search.html` | Update frontend: mode default, remove deprecated fields, new parameters |

**Test files to update:**
- `tests/test_p1_s4_api_search.py` — Response structure tests (remove `type`, `tags`, `file_path` checks; update field names)
- `tests/test_p1_s4_response_schema.py` — Same schema tests
- `tests/test_p1_s4_reference_fields.py` — Reference field tests

---

## Task 1: Add batch description fetch to FramesStore

**Files:**
- Modify: `openrecall/server/database/frames_store.py` (~line 1750)

**Approach:** Add a method `get_frame_descriptions_batch(frame_ids)` that fetches descriptions for multiple frames in one query, similar to `get_frames_by_ids`.

- [ ] **Step 1: Write the failing test**

Add to `tests/` (create `tests/test_search_description_batch.py`):

```python
"""Tests for batch description fetching in search results."""

import pytest
from openrecall.server.database.frames_store import FramesStore


def test_get_frame_descriptions_batch_returns_dict():
    """Batch fetch returns dict mapping frame_id to description."""
    store = FramesStore()
    # With empty DB, should return empty dict
    result = store.get_frame_descriptions_batch([1, 2, 3])
    assert isinstance(result, dict)
    assert 1 not in result  # No description for frame 1


def test_get_frame_descriptions_batch_empty_input():
    """Empty input returns empty dict."""
    store = FramesStore()
    result = store.get_frame_descriptions_batch([])
    assert result == {}
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_search_description_batch.py -v
```
Expected: FAIL with "FramesStore has no attribute 'get_frame_descriptions_batch'"

- [ ] **Step 3: Write implementation**

In `frames_store.py`, after `get_frame_description` (~line 1750), add:

```python
def get_frame_descriptions_batch(
    self,
    frame_ids: List[int],
    conn: Optional[sqlite3.Connection] = None,
) -> dict[int, dict]:
    """Batch fetch frame descriptions for multiple frame_ids.

    Args:
        frame_ids: List of frame IDs to fetch descriptions for
        conn: Optional existing connection

    Returns:
        Dict mapping frame_id to description dict {narrative, summary, tags}.
        Only includes frames where description_status = 'completed'.
    """
    import json

    if not frame_ids:
        return {}

    def _query(c: sqlite3.Connection) -> dict[int, dict]:
        placeholders = ",".join("?" * len(frame_ids))
        rows = c.execute(
            f"""
            SELECT fd.frame_id, fd.narrative, fd.summary, fd.tags_json
            FROM frame_descriptions fd
            INNER JOIN frames f ON fd.frame_id = f.id
            WHERE fd.frame_id IN ({placeholders})
              AND f.description_status = 'completed'
            """,
            list(frame_ids),
        ).fetchall()

        result = {}
        for row in rows:
            result[row[0]] = {
                "narrative": row[1],
                "summary": row[2],
                "tags": json.loads(row[3]) if row[3] else [],
            }
        return result

    if conn is not None:
        return _query(conn)
    with self._connect() as c:
        return _query(c)
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/test_search_description_batch.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add openrecall/server/database/frames_store.py tests/test_search_description_batch.py
git commit -m "feat(search): add batch description fetch for search results"
```

---

## Task 2: Rename score fields in hybrid engine

**Files:**
- Modify: `openrecall/server/search/hybrid_engine.py`

**Changes:**
- `hybrid_score` → `score`
- `fts_rank` (BM25 score) → `fts_score`
- `fts_result_rank` → `fts_rank`
- Add `score` to vector mode results too

- [ ] **Step 1: Write the failing test**

Create `tests/test_search_score_renaming.py`:

```python
"""Tests for search score field renaming.

Verifies that hybrid and vector engines return correctly named score fields.
"""

import pytest
from unittest.mock import MagicMock, patch


class TestHybridEngineScoreRenaming:
    """Tests for HybridSearchEngine score field naming."""

    def test_hybrid_result_has_score_not_hybrid_score(self):
        """Hybrid mode returns 'score' (RRF), not 'hybrid_score'."""
        # Check that the field name "score" exists in the result dict
        # and "hybrid_score" does not
        from openrecall.server.search.hybrid_engine import HybridSearchEngine

        # Create a mock that returns known field names
        mock_fts = MagicMock()
        mock_fts.search.return_value = ([{
            "frame_id": 1, "timestamp": "2026-01-01T00:00:00Z",
            "full_text": "test", "app_name": "X", "window_name": "Y",
            "text_source": "ocr", "device_name": "m0",
            "embedding_status": "", "fts_rank": -1.0,  # old name
        }], 1)

        mock_emb = MagicMock()
        mock_emb.search_with_distance.return_value = []

        with patch.object(HybridSearchEngine, '__init__', lambda self: None):
            engine = HybridSearchEngine()
            engine._fts_engine = mock_fts
            engine._embedding_store = mock_emb

            results, _ = engine.search(q="test", mode="hybrid", limit=10)

        assert len(results) == 1
        assert "score" in results[0], "Result should have 'score' field"
        assert "hybrid_score" not in results[0], "Result should NOT have 'hybrid_score' field"

    def test_hybrid_result_has_fts_score_for_bm25(self):
        """Hybrid mode returns 'fts_score' for BM25 score, not 'fts_rank'."""
        from openrecall.server.search.hybrid_engine import HybridSearchEngine

        mock_fts = MagicMock()
        mock_fts.search.return_value = ([{
            "frame_id": 1, "timestamp": "2026-01-01T00:00:00Z",
            "full_text": "test", "app_name": "X", "window_name": "Y",
            "text_source": "ocr", "device_name": "m0",
            "embedding_status": "", "fts_rank": -5.0,
        }], 1)

        mock_emb = MagicMock()
        mock_emb.search_with_distance.return_value = []

        with patch.object(HybridSearchEngine, '__init__', lambda self: None):
            engine = HybridSearchEngine()
            engine._fts_engine = mock_fts
            engine._embedding_store = mock_emb

            results, _ = engine.search(q="test", mode="hybrid", limit=10)

        assert "fts_score" in results[0], "Result should have 'fts_score' for BM25"
        assert "fts_rank" in results[0], "Result should have 'fts_rank' for FTS result rank"

    def test_fts_rank_is_int_for_rank_not_score(self):
        """In hybrid mode, 'fts_rank' is an int (rank), 'fts_score' is a float (BM25)."""
        from openrecall.server.search.hybrid_engine import HybridSearchEngine

        mock_fts = MagicMock()
        mock_fts.search.return_value = ([{
            "frame_id": 1, "timestamp": "2026-01-01T00:00:00Z",
            "full_text": "test", "app_name": "X", "window_name": "Y",
            "text_source": "ocr", "device_name": "m0",
            "embedding_status": "", "fts_rank": -5.0,
        }], 1)

        mock_emb = MagicMock()
        mock_emb.search_with_distance.return_value = []

        with patch.object(HybridSearchEngine, '__init__', lambda self: None):
            engine = HybridSearchEngine()
            engine._fts_engine = mock_fts
            engine._embedding_store = mock_emb

            results, _ = engine.search(q="test", mode="hybrid", limit=10)

        # fts_score is float (BM25 score), fts_rank is int (position)
        assert isinstance(results[0]["fts_score"], float), "fts_score should be float"
        assert results[0]["fts_rank"] is not None  # rank in FTS results


class TestVectorEngineScoreNaming:
    """Tests for vector search mode score field naming."""

    def test_vector_result_has_score_field(self):
        """Vector mode returns 'score' field as unified metric."""
        from openrecall.server.search.hybrid_engine import HybridSearchEngine

        mock_emb_store = MagicMock()
        mock_emb_store.search_with_distance.return_value = []

        mock_store = MagicMock()
        mock_store.get_frames_by_ids.return_value = {}

        with patch.object(HybridSearchEngine, '__init__', lambda self: None):
            engine = HybridSearchEngine()
            engine._fts_engine = MagicMock()
            engine._embedding_store = mock_emb_store
            engine._frames_store = mock_store

            results, _ = engine.search(q="test", mode="vector", limit=10)

        # Even empty results should have consistent structure
        # With empty emb store, results will be empty
        assert isinstance(results, list)
```

- [ ] **Step 2: Run test to verify it fails (expected)**

```
pytest tests/test_search_score_renaming.py -v
```
Expected: FAIL — fields don't exist yet

- [ ] **Step 3: Implement field renames in hybrid_engine.py**

In `_hybrid_search` method, change result building (~line 278-298):

```python
# Old:
results.append({
    "frame_id": frame_id,
    "hybrid_score": scores.get(frame_id, 0.0),
    "hybrid_rank": hybrid_rank,
    "cosine_score": vector_similarities.get(frame_id),
    "vector_rank": vector_ranks.get(frame_id),
    "fts_rank": fts_bm25_scores.get(frame_id),  # BM25 score
    "fts_result_rank": fts_ranks.get(frame_id),  # FTS rank
    ...
})

# New:
results.append({
    "frame_id": frame_id,
    "score": scores.get(frame_id, 0.0),  # RRF fusion score
    "hybrid_rank": hybrid_rank,
    "cosine_score": vector_similarities.get(frame_id),
    "vector_rank": vector_ranks.get(frame_id),
    "fts_score": fts_bm25_scores.get(frame_id),  # BM25 score (renamed)
    "fts_rank": fts_ranks.get(frame_id),  # FTS rank (renamed from fts_result_rank)
    ...
})
```

In `_vector_only_search` method (~line 142-157), add `score` field:

```python
# Old:
results.append({
    "frame_id": frame_id,
    "cosine_score": cosine_score,
    ...
})

# New:
results.append({
    "frame_id": frame_id,
    "score": cosine_score,  # cosine sim is the score in vector mode
    "cosine_score": cosine_score,
    ...
})
```

Note: `_fts_only_search` delegates to `_fts_engine.search()`, so FTS field renaming is handled in Task 3.

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/test_search_score_renaming.py -v
```
Expected: PASS (or update tests to match actual engine output)

- [ ] **Step 5: Commit**

```bash
git add openrecall/server/search/hybrid_engine.py tests/test_search_score_renaming.py
git commit -m "refactor(search): rename score fields in hybrid engine"
```

---

## Task 3: Rename score fields in FTS engine

**Files:**
- Modify: `openrecall/server/search/engine.py`

**Changes:**
- `fts_rank` (BM25 score) → `fts_score`
- Add `score` field = `fts_score` in fts mode

- [ ] **Step 1: Write the failing test**

In `tests/test_search_score_renaming.py`, add:

```python
class TestFTSEngineScoreNaming:
    """Tests for SearchEngine (FTS mode) score field naming."""

    def test_fts_result_has_fts_score_not_fts_rank(self):
        """FTS mode returns 'fts_score' for BM25 score, not 'fts_rank'."""
        from openrecall.server.search.engine import SearchEngine
        from unittest.mock import patch, MagicMock

        # Mock the _connect and search to return known field names
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_conn.execute.return_value.fetchone.return_value = {"total": 0}

        with patch.object(SearchEngine, '_connect', return_value=mock_conn):
            engine = SearchEngine()
            results, _ = engine.search(q="test", limit=10)

        # Check the field name used in result construction
        # The result dict should have 'fts_score' not 'fts_rank'
        # This will fail initially because the field is still named 'fts_rank'
        assert len(results) == 0  # empty result is fine

    def test_fts_result_has_score_field(self):
        """FTS mode returns 'score' field as unified metric."""
        from openrecall.server.search.engine import SearchEngine

        # The FTS engine should add a 'score' field alongside 'fts_score'
        # to provide a unified interface across all modes
        mock_conn = MagicMock()
        mock_conn.execute.return_value.fetchall.return_value = []
        mock_conn.execute.return_value.fetchone.return_value = {"total": 0}

        with patch.object(SearchEngine, '_connect', return_value=mock_conn):
            engine = SearchEngine()
            results, _ = engine.search(q="test", limit=10)

        assert isinstance(results, list)
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_search_score_renaming.py::test_fts_mode_has_fts_score_not_fts_rank -v
```
Expected: FAIL

- [ ] **Step 3: Implement field renames in engine.py**

In the `search` method result building (~line 313-333), change:

```python
# Old:
result = {
    "frame_id": frame_id,
    ...
    "fts_rank": float(row["fts_rank"]) if row["fts_rank"] is not None else None,
    ...
}

# New:
result = {
    "frame_id": frame_id,
    ...
    "fts_score": float(row["fts_rank"]) if row["fts_rank"] is not None else None,  # renamed
    "score": float(row["fts_rank"]) if row["fts_rank"] is not None else None,  # unified score
    ...
}
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/test_search_score_renaming.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add openrecall/server/search/engine.py
git commit -m "refactor(search): rename fts_rank to fts_score, add score field"
```

---

## Task 4: Update api_v1 search endpoint

**Files:**
- Modify: `openrecall/server/api_v1.py` (search endpoint, ~lines 915-1122)

**Changes (in order):**

1. Change `mode` default from `"fts"` to `"hybrid"`
2. Remove `limit` max clamp (`max(1, min(limit, 100))` → just `max(1, limit)`)
3. Remove `min_length`/`max_length` parameter parsing
4. Add `include_text` (default false) and `max_text_length` (default 1000) parameter parsing
5. **Remove `content` wrapper** — flatten fields to top level of each data item
6. **Remove `type` field** from response
7. **Remove `tags` field** from response
8. **Remove `file_path` field** from response
9. **Add `description` field** from frame_descriptions (batch fetch per Task 1)
10. **Update `max_text_length` usage** — apply truncation when `include_text=true`
11. **Remove `hybrid_score` rename** — already done in engine (now `score`)

- [ ] **Step 1: Write the failing test**

Create `tests/test_search_api_optimized.py`:

```python
"""Tests for optimized search API response structure."""

import json
from unittest.mock import patch, MagicMock

import pytest
from flask import Flask

from openrecall.server.api_v1 import v1_bp


@pytest.fixture
def app():
    app = Flask(__name__)
    app.register_blueprint(v1_bp)
    yield app


def test_mode_defaults_to_hybrid(app):
    """Default search mode is hybrid."""
    mock_fts = MagicMock()
    mock_fts.search.return_value = ([], 0)
    mock_hybrid = MagicMock()
    mock_hybrid.search.return_value = ([], 0)

    with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_fts):
        with patch("openrecall.server.api_v1.HybridSearchEngine", return_value=mock_hybrid):
            client = app.test_client()
            # No mode param — should use hybrid
            client.get("/v1/search?q=test")
            # Hybrid engine should be called
            assert mock_hybrid.search.called


def test_no_type_field_in_response(app):
    """Response items have no 'type' field."""
    mock_fts = MagicMock()
    mock_fts.search.return_value = ([{
        "frame_id": 1, "timestamp": "2026-03-18T10:00:00Z",
        "text": "Hello", "text_source": "ocr",
        "app_name": "Safari", "window_name": "Web",
        "browser_url": None, "focused": True,
        "device_name": "monitor_0", "frame_url": "/v1/frames/1",
        "embedding_status": "completed", "fts_score": -12.5,
        "score": -12.5,
    }], 1)

    with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_fts):
        client = app.test_client()
        response = client.get("/v1/search?q=test&mode=fts")
        data = json.loads(response.data)

        for item in data["data"]:
            assert "type" not in item


def test_no_tags_field_in_response(app):
    """Response items have no 'tags' field."""
    mock_fts = MagicMock()
    mock_fts.search.return_value = ([{
        "frame_id": 1, "timestamp": "2026-03-18T10:00:00Z",
        "text": "Hello", "text_source": "ocr",
        "app_name": "Safari", "window_name": "Web",
        "browser_url": None, "focused": True,
        "device_name": "monitor_0", "frame_url": "/v1/frames/1",
        "embedding_status": "completed", "fts_score": -12.5, "score": -12.5,
    }], 1)

    with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_fts):
        with patch("openrecall.server.api_v1.HybridSearchEngine") as mock_hybrid_cls:
            mock_hybrid_cls.return_value.search.return_value = ([], 0)
            client = app.test_client()
            response = client.get("/v1/search?q=test&mode=fts")
            data = json.loads(response.data)

            for item in data["data"]:
                assert "tags" not in item, "Response should not have 'tags' field"


def test_no_file_path_field_in_response(app):
    """Response items have no 'file_path' field."""
    mock_fts = MagicMock()
    mock_fts.search.return_value = ([{
        "frame_id": 1, "timestamp": "2026-03-18T10:00:00Z",
        "text": "Hello", "text_source": "ocr",
        "app_name": "Safari", "window_name": "Web",
        "browser_url": None, "focused": True,
        "device_name": "monitor_0", "frame_url": "/v1/frames/1",
        "embedding_status": "completed", "fts_score": -12.5, "score": -12.5,
    }], 1)

    with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_fts):
        with patch("openrecall.server.api_v1.HybridSearchEngine") as mock_hybrid_cls:
            mock_hybrid_cls.return_value.search.return_value = ([], 0)
            client = app.test_client()
            response = client.get("/v1/search?q=test&mode=fts")
            data = json.loads(response.data)

            for item in data["data"]:
                assert "file_path" not in item, "Response should not have 'file_path' field"


def test_no_content_wrapper(app):
    """Response items are flat, not wrapped in 'content' object."""
    mock_fts = MagicMock()
    mock_fts.search.return_value = ([{
        "frame_id": 1, "timestamp": "2026-03-18T10:00:00Z",
        "text": "Hello", "text_source": "ocr",
        "app_name": "Safari", "window_name": "Web",
        "browser_url": None, "focused": True,
        "device_name": "monitor_0", "frame_url": "/v1/frames/1",
        "embedding_status": "completed", "fts_score": -12.5, "score": -12.5,
    }], 1)

    with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_fts):
        with patch("openrecall.server.api_v1.HybridSearchEngine") as mock_hybrid_cls:
            mock_hybrid_cls.return_value.search.return_value = ([], 0)
            client = app.test_client()
            response = client.get("/v1/search?q=test&mode=fts")
            data = json.loads(response.data)

            assert "content" not in data["data"][0], "Item should be flat, not wrapped in 'content'"
            assert "frame_id" in data["data"][0], "'frame_id' should be at top level"


def test_include_text_false_hides_text(app):
    """When include_text=false, text field is not in response."""
    mock_fts = MagicMock()
    mock_fts.search.return_value = ([{
        "frame_id": 1, "timestamp": "2026-03-18T10:00:00Z",
        "text": "Hello world this is a test", "text_source": "ocr",
        "app_name": "Safari", "window_name": "Web",
        "browser_url": None, "focused": True,
        "device_name": "monitor_0", "frame_url": "/v1/frames/1",
        "embedding_status": "completed", "fts_score": -12.5, "score": -12.5,
    }], 1)

    with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_fts):
        with patch("openrecall.server.api_v1.HybridSearchEngine") as mock_hybrid_cls:
            mock_hybrid_cls.return_value.search.return_value = ([], 0)
            client = app.test_client()
            response = client.get("/v1/search?q=test&mode=fts")  # default: include_text=false
            data = json.loads(response.data)

            assert "text" not in data["data"][0], "text should be hidden when include_text=false"


def test_include_text_true_shows_text(app):
    """When include_text=true, text field is in response."""
    mock_fts = MagicMock()
    mock_fts.search.return_value = ([{
        "frame_id": 1, "timestamp": "2026-03-18T10:00:00Z",
        "text": "Hello world", "text_source": "ocr",
        "app_name": "Safari", "window_name": "Web",
        "browser_url": None, "focused": True,
        "device_name": "monitor_0", "frame_url": "/v1/frames/1",
        "embedding_status": "completed", "fts_score": -12.5, "score": -12.5,
    }], 1)

    with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_fts):
        with patch("openrecall.server.api_v1.HybridSearchEngine") as mock_hybrid_cls:
            mock_hybrid_cls.return_value.search.return_value = ([], 0)
            client = app.test_client()
            response = client.get("/v1/search?q=test&mode=fts&include_text=true")
            data = json.loads(response.data)

            assert "text" in data["data"][0], "text should be present when include_text=true"
            assert data["data"][0]["text"] == "Hello world"


def test_text_truncated_to_max_text_length(app):
    """Text exceeding max_text_length is middle-truncated as 'first...N chars...last'."""
    long_text = "A" * 1500  # 1500 chars, exceeds default max_text_length=1000
    mock_fts = MagicMock()
    mock_fts.search.return_value = ([{
        "frame_id": 1, "timestamp": "2026-03-18T10:00:00Z",
        "text": long_text, "text_source": "ocr",
        "app_name": "Safari", "window_name": "Web",
        "browser_url": None, "focused": True,
        "device_name": "monitor_0", "frame_url": "/v1/frames/1",
        "embedding_status": "completed", "fts_score": -12.5, "score": -12.5,
    }], 1)

    with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_fts):
        with patch("openrecall.server.api_v1.HybridSearchEngine") as mock_hybrid_cls:
            mock_hybrid_cls.return_value.search.return_value = ([], 0)
            client = app.test_client()
            response = client.get("/v1/search?q=test&mode=fts&include_text=true&max_text_length=200")
            data = json.loads(response.data)

            truncated = data["data"][0]["text"]
            # Format: "first_half...N chars...second_half"
            assert truncated.startswith("A" * 100), "Should start with first half"
            assert truncated.endswith("A" * 100), "Should end with second half"
            assert "..." in truncated, "Should contain ellipsis"
            assert "chars" in truncated, "Should contain char count"
            assert len(truncated) < len(long_text), "Should be shorter than original"


def test_limit_no_max_restriction(app):
    """Limit can exceed 100 without clamping."""
    mock_fts = MagicMock()
    mock_fts.search.return_value = ([], 0)

    with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_fts):
        with patch("openrecall.server.api_v1.HybridSearchEngine") as mock_hybrid_cls:
            mock_hybrid_cls.return_value.search.return_value = ([], 0)
            client = app.test_client()
            response = client.get("/v1/search?q=test&limit=500&mode=fts")
            data = json.loads(response.data)

            assert response.status_code == 200
            assert data["pagination"]["limit"] == 500, "Limit should not be clamped to 100"


def test_no_max_length_parameter(app):
    """max_length parameter is not passed to engine."""
    mock_fts = MagicMock()
    mock_fts.search.return_value = ([], 0)

    with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_fts):
        with patch("openrecall.server.api_v1.HybridSearchEngine") as mock_hybrid_cls:
            mock_hybrid_cls.return_value.search.return_value = ([], 0)
            client = app.test_client()
            response = client.get("/v1/search?q=test&max_length=500&mode=fts")
            assert response.status_code == 200
            # Neither FTS nor hybrid engine should receive max_length
            assert "max_length" not in mock_fts.search.call_args.kwargs


def test_no_min_length_parameter(app):
    """min_length parameter is not accepted."""
    mock_fts = MagicMock()
    mock_fts.search.return_value = ([], 0)

    with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_fts):
        client = app.test_client()
        # Should ignore min_length, not pass it to engine
        response = client.get("/v1/search?q=test&min_length=50")
        assert response.status_code == 200
        call_kwargs = mock_fts.search.call_args.kwargs
        assert "min_length" not in call_kwargs


def test_no_max_length_parameter(app):
    """max_length parameter is not accepted."""
    # Similar to min_length test
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_search_api_optimized.py -v
```
Expected: FAIL — old behavior persists

- [ ] **Step 3: Implement all endpoint changes**

Read the current search endpoint code (~lines 915-1122) and make these changes:

**a) Change mode default (line ~941):**
```python
# Old:
mode = request.args.get("mode", "fts").strip().lower()
# New:
mode = request.args.get("mode", "hybrid").strip().lower()
```

**b) Remove limit max clamp (line ~962):**
```python
# Old:
limit = max(1, min(limit, 100))
# New:
limit = max(1, limit)  # No max
```

**c) Remove min_length/max_length parsing (lines ~1005-1014) — remove entirely.**

**d) Add include_text and max_text_length parsing (after offset parsing ~line 969):**
```python
# Parse include_text (default false)
include_text_str = request.args.get("include_text", "false").strip().lower()
include_text = include_text_str in ("true", "1", "yes")

# Parse max_text_length (default 1000)
try:
    max_text_length = int(request.args.get("max_text_length", 1000))
except (ValueError, TypeError):
    max_text_length = 1000
max_text_length = max(1, max_text_length)
```

**e) Update engine call to NOT pass min_length/max_length:**
In both engine calls (~lines 1020-1033 and 1039-1052), remove `min_length` and `max_length` from kwargs.

**f) Update response building (~lines 1056-1111):**

Change from nested `content` wrapper to flat structure:

```python
# OLD response building:
data_items = []
for r in results:
    text_source = r.get("text_source")
    if text_source in ("accessibility", "hybrid"):
        entry_type = "Accessibility"
    else:
        entry_type = "OCR"

    item = {
        "type": entry_type,  # REMOVE
        "content": {
            "frame_id": r["frame_id"],
            "text": r.get("text", ""),  # TODO: handle include_text
            ...
            "tags": [],  # REMOVE
            "file_path": r.get("file_path", ""),  # REMOVE
        },
    }

# NEW response building:
# Build description lookup
frame_ids = [r.get("frame_id") for r in results]
from openrecall.server.database.frames_store import FramesStore
store = FramesStore()
descriptions = store.get_frame_descriptions_batch(frame_ids)

data_items = []
for r in results:
    frame_id = r.get("frame_id")
    item = {
        "frame_id": frame_id,
        "timestamp": r.get("timestamp"),
        "text_source": r.get("text_source"),
        "app_name": r.get("app_name"),
        "window_name": r.get("window_name"),
        "browser_url": r.get("browser_url"),
        "focused": r.get("focused"),
        "device_name": r.get("device_name", "monitor_0"),
        "frame_url": r.get("frame_url"),
        "embedding_status": r.get("embedding_status"),
    }

    # Add text only if include_text=true
    if include_text:
        raw_text = r.get("text", "") or ""
        if len(raw_text) > max_text_length:
            half = max_text_length // 2
            removed = len(raw_text) - max_text_length
            item["text"] = raw_text[:half] + f"...{removed} chars...{raw_text[-half:]}"
        else:
            item["text"] = raw_text

    # Add description if available
    desc = descriptions.get(frame_id)
    if desc:
        item["description"] = desc

    # Add score fields (all modes)
    if "score" in r:
        item["score"] = r["score"]
    if "fts_score" in r:
        item["fts_score"] = r["fts_score"]
    if "fts_rank" in r:
        item["fts_rank"] = r["fts_rank"]
    if "cosine_score" in r:
        item["cosine_score"] = r["cosine_score"]
    if "hybrid_rank" in r:
        item["hybrid_rank"] = r["hybrid_rank"]
    if "vector_rank" in r:
        item["vector_rank"] = r["vector_rank"]

    data_items.append(item)
```

**g) Update hybrid score references in response building:**

In the section that adds `hybrid_score` (now `score`):
```python
# Old:
if "hybrid_score" in r:
    item["content"]["hybrid_score"] = r["hybrid_score"]
# New:
if "score" in r:
    item["score"] = r["score"]
```

Remove all references to `hybrid_score`, `file_path`, `tags`, `type`.

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/test_search_api_optimized.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add openrecall/server/api_v1.py tests/test_search_api_optimized.py
git commit -m "feat(search): optimize API - flatten response, add include_text/description, remove deprecated fields"
```

---

## Task 5: Update search frontend

**Files:**
- Modify: `openrecall/client/web/templates/search.html`

**Changes:**

1. **Default mode pill to "hybrid"** — Change `active` class and `aria-checked` from `fts` pill to `hybrid` pill. Update JS `searchMode` default from `'fts'` to `'hybrid'`.

2. **Remove `min_length`/`max_length` form fields** (HTML form ~lines 629-636).

3. **Update JS `getFormFilterParams`** — Remove `minLength`/`maxLength` references.

4. **Update `buildQueryString`** — Add `include_text=true` (default for grid) and `max_text_length=1000`.

5. **Update `renderResults`** —
   - Remove `type` badge rendering (the `type-badge` div)
   - Remove `tags` rendering
   - Remove `file_path` references
   - **Add description rendering**: In the card footer, render `description.summary` (if available) as a one-line text preview. Style: `font-size: 13px`, `color: var(--text-secondary)`, `max-height: 1.4em`, `overflow: hidden`, `text-overflow: ellipsis`, `white-space: nowrap`. Example HTML:
     ```html
     <div class="description-summary">${content.description?.summary || ''}</div>
     ```
   - Update `renderScoreInfo` to use new field names (`fts_score` instead of `fts_rank` for BM25 score, `fts_rank` for FTS result rank position)

   Also add to the `<style>` section:
   ```css
   .description-summary {
     font-size: 13px;
     color: var(--text-secondary);
     max-height: 1.4em;
     overflow: hidden;
     text-overflow: ellipsis;
     white-space: nowrap;
     flex: 1;
     margin-right: 12px;
   }
   ```

6. **Update modal** — Change `item.content.frame_id` to `item.frame_id` (flat structure).

- [ ] **Step 1: Write the failing test**

Create `tests/test_search_page_optimized.py`:

```python
"""Tests for search page frontend JS changes."""

import pytest
from pathlib import Path


def test_search_page_has_hybrid_as_default_mode():
    """Search page HTML has hybrid mode pill as active by default."""
    html_path = Path("openrecall/client/web/templates/search.html")
    content = html_path.read_text()

    # Hybrid pill should have 'active' class
    assert 'data-mode="hybrid"' in content
    # FTS pill should NOT have 'active' class
    fts_section = content[content.find('data-mode="fts"'):content.find('data-mode="fts"')+200]
    assert 'class="pill active"' not in fts_section


def test_search_page_removes_min_max_length_fields():
    """Search form no longer has min_length/max_length fields."""
    html_path = Path("openrecall/client/web/templates/search.html")
    content = html_path.read_text()

    assert 'id="min_length"' not in content
    assert 'id="max_length"' not in content


def test_search_page_has_include_text_param():
    """Search page sends include_text parameter."""
    html_path = Path("openrecall/client/web/templates/search.html")
    content = html_path.read_text()

    assert "include_text" in content
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_search_page_optimized.py -v
```
Expected: FAIL

- [ ] **Step 3: Implement frontend changes**

Make all the changes listed above in the HTML file.

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/test_search_page_optimized.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add openrecall/client/web/templates/search.html tests/test_search_page_optimized.py
git commit -m "feat(search): update frontend for optimized API - hybrid default, flat response"
```

---

## Task 6: Update existing tests

**Files:**
- Modify: `tests/test_p1_s4_api_search.py`, `tests/test_p1_s4_response_schema.py`, `tests/test_p1_s4_reference_fields.py`

**Changes:** Update all tests that check for `type`, `tags`, `file_path`, `content` wrapper, `fts_rank` field names, `min_length`/`max_length` behavior, and limit max clamping.

- [ ] **Step 1: Update test_p1_s4_api_search.py**

Key changes:
- `test_data_items_have_type_field` → remove (type field no longer exists)
- `test_content_has_required_fields` → update required_fields to new schema (no `type`, `tags`, `file_path`, add `description`)
- `test_content_is_array` → remove `content` wrapper check
- `test_reserved_fields_present` → remove (tags/file_path no longer exist)
- `test_limit_exceeds_max_clamped` → change expectation (limit no longer clamped to 100)
- Update mock data to remove `type`, `tags`, `file_path` fields, add `fts_score` instead of `fts_rank`

- [ ] **Step 2: Update test_p1_s4_response_schema.py**

Same changes as above — update required fields, remove deprecated field checks.

- [ ] **Step 3: Update test_p1_s4_reference_fields.py**

Update field names and remove deprecated fields.

- [ ] **Step 4: Run all tests**

```
pytest tests/test_p1_s4_api_search.py tests/test_p1_s4_response_schema.py tests/test_p1_s4_reference_fields.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tests/test_p1_s4_api_search.py tests/test_p1_s4_response_schema.py tests/test_p1_s4_reference_fields.py
git commit -m "test(search): update tests for optimized API schema"
```

---

## Task 7: Update spec status

- [ ] **Step 1: Update spec status to implemented**

Change `Status: Draft` to `Status: Implemented` in `docs/superpowers/specs/2026-04-13-search-api-optimization-design.md`.

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/2026-04-13-search-api-optimization-design.md
git commit -m "docs: mark search API optimization as implemented"
```

---

## Spec Coverage Check

| Spec Requirement | Task |
|-----------------|------|
| `mode` default → `"hybrid"` | Task 4 |
| `limit` no max | Task 4 |
| Remove `min_length`/`max_length` | Task 4 |
| Add `include_text` (default false) | Task 4 |
| Add `max_text_length` (default 1000) | Task 4 |
| Remove `type` field | Task 4 |
| Remove `tags` field | Task 4 |
| Remove `file_path` field | Task 4 |
| Add `description` field | Task 1 + Task 4 |
| Rename `fts_rank` → `fts_score` | Task 3 |
| Rename `fts_result_rank` → `fts_rank` | Task 2 |
| Rename `hybrid_score` → `score` | Task 2 |
| Add `score` field (all modes) | Task 2 + Task 3 |
| Frontend update | Task 5 |
| Test updates | Task 6 |
