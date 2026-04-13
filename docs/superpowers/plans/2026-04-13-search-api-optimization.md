# Search API Optimization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Optimize GET /v1/search API with cleaner interface, new capabilities, and improved defaults.

**Architecture:** Modify API endpoint, search engines, and frontend. Changes are backward-compatible except for removed fields. Implementation follows TDD with unit tests for each change.

**Tech Stack:** Python, Flask, SQLite, FTS5, LanceDB

---

## File Structure

| File | Responsibility |
|------|----------------|
| `openrecall/server/api_v1.py` | API endpoint parameter handling, response building |
| `openrecall/server/search/engine.py` | FTS search engine, result structure |
| `openrecall/server/search/hybrid_engine.py` | Hybrid/vector search, description fetching |
| `openrecall/client/web/templates/search.html` | Frontend search page |
| `tests/test_p1_s4_api_search.py` | API unit tests |
| `tests/test_search_api.py` | Search counts tests |
| `tests/test_hybrid_search.py` | Hybrid search tests |

---

### Task 1: Update Input Parameter Defaults and Limits

**Files:**
- Modify: `openrecall/server/api_v1.py:940-962`
- Test: `tests/test_p1_s4_api_search.py`

- [ ] **Step 1: Write failing test for hybrid default mode**

```python
# In tests/test_p1_s4_api_search.py, add to TestSearchAPIBasic class:

def test_search_default_mode_is_hybrid(self, app_with_search_route, mock_search_engine):
    """Search endpoint defaults to hybrid mode."""
    with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_search_engine):
        with patch("openrecall.server.api_v1.HybridSearchEngine") as mock_hybrid:
            mock_hybrid.return_value.search.return_value = ([], 0)
            client = app_with_search_route.test_client()
            client.get("/v1/search?q=test")

            # HybridSearchEngine.search should be called with mode='hybrid'
            mock_hybrid.return_value.search.assert_called_once()
            call_kwargs = mock_hybrid.return_value.search.call_args.kwargs
            assert call_kwargs.get("mode") == "hybrid"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_p1_s4_api_search.py::TestSearchAPIBasic::test_search_default_mode_is_hybrid -v`
Expected: FAIL (mode defaults to 'fts')

- [ ] **Step 3: Update mode default to hybrid**

In `openrecall/server/api_v1.py`, change line ~941:

```python
# Before:
mode = request.args.get("mode", "fts").strip().lower()

# After:
mode = request.args.get("mode", "hybrid").strip().lower()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_p1_s4_api_search.py::TestSearchAPIBasic::test_search_default_mode_is_hybrid -v`
Expected: PASS

- [ ] **Step 5: Remove limit max restriction**

In `openrecall/server/api_v1.py`, change lines ~958-962:

```python
# Before:
try:
    limit = int(request.args.get("limit", 20))
except (ValueError, TypeError):
    limit = 20
limit = max(1, min(limit, 100))

# After:
try:
    limit = int(request.args.get("limit", 20))
except (ValueError, TypeError):
    limit = 20
limit = max(1, limit)  # Remove max 100 restriction
```

Also update `openrecall/server/search/engine.py` lines ~227-228:

```python
# Before:
limit = min(max(1, params.limit), self.MAX_LIMIT)

# After:
limit = max(1, params.limit)
```

- [ ] **Step 6: Write test for no limit max**

```python
# In tests/test_p1_s4_api_search.py:

def test_search_accepts_large_limit(self, app_with_search_route, mock_search_engine):
    """Search endpoint accepts limit > 100."""
    with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_search_engine):
        client = app_with_search_route.test_client()
        response = client.get("/v1/search?q=test&limit=500")
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data["pagination"]["limit"] == 500
```

- [ ] **Step 7: Run tests**

Run: `pytest tests/test_p1_s4_api_search.py::TestSearchAPIBasic::test_search_accepts_large_limit -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add openrecall/server/api_v1.py openrecall/server/search/engine.py tests/test_p1_s4_api_search.py
git commit -m "feat(search): change default mode to hybrid, remove limit max restriction"
```

---

### Task 2: Remove min_length and max_length Parameters

**Files:**
- Modify: `openrecall/server/api_v1.py:1004-1014`
- Modify: `openrecall/server/search/engine.py:54-55, 165-170, 244-245, 294-295, 375-376`
- Modify: `openrecall/server/search/hybrid_engine.py`
- Modify: `openrecall/client/web/templates/search.html:629-636, 925-926, 934-935`
- Test: `tests/test_search_api.py`

- [ ] **Step 1: Write failing test that min_length/max_length are ignored**

```python
# In tests/test_search_api.py, modify test_search_counts_endpoint_passes_text_length_filters:

def test_search_counts_endpoint_ignores_text_length_filters(self, app_with_search_counts_route, mock_search_engine):
    """Test /v1/search/counts ignores min_length and max_length params (deprecated)."""
    with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_search_engine):
        client = app_with_search_counts_route.test_client()
        response = client.get("/v1/search/counts?q=test&min_length=10&max_length=1000")

        assert response.status_code == 200
        # min_length and max_length should NOT be passed to search engine
        call_args = mock_search_engine.count_by_type.call_args
        assert call_args.kwargs.get("min_length") is None
        assert call_args.kwargs.get("max_length") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_search_api.py::TestSearchCountsAPI::test_search_counts_endpoint_ignores_text_length_filters -v`
Expected: FAIL

- [ ] **Step 3: Remove min_length/max_length from API endpoint**

In `openrecall/server/api_v1.py`, remove lines ~1004-1014:

```python
# DELETE these lines:
# Parse text length
min_length = None
max_length = None
try:
    min_length = int(request.args.get("min_length", 0)) or None
except (ValueError, TypeError):
    pass
try:
    max_length = int(request.args.get("max_length", 0)) or None
except (ValueError, TypeError):
    pass
```

Also remove `min_length` and `max_length` from the `engine.search()` and `hybrid_engine.search()` calls (~lines 1029-1031, 1049-1051).

- [ ] **Step 4: Remove from SearchEngine**

In `openrecall/server/search/engine.py`:

1. Remove from `SearchParams` dataclass (lines ~54-55):
```python
# DELETE:
min_length: Optional[int] = None
max_length: Optional[int] = None
```

2. Remove from `_build_where_clause` (lines ~165-170):
```python
# DELETE:
if params.min_length is not None:
    where_parts.append("LENGTH(frames.full_text) >= ?")
    params_list.append(params.min_length)
if params.max_length is not None:
    where_parts.append("LENGTH(frames.full_text) <= ?")
    params_list.append(params.max_length)
```

3. Remove from `search()` method signature (lines ~244-245)
4. Remove from `count()` method signature (lines ~375-376)
5. Remove from `count_by_type()` method signature

- [ ] **Step 5: Remove from HybridSearchEngine**

In `openrecall/server/search/hybrid_engine.py`, remove min_length/max_length kwargs from `search()` method and pass-through calls.

- [ ] **Step 6: Remove from frontend**

In `openrecall/client/web/templates/search.html`, remove lines ~629-636:
```html
<!-- DELETE: -->
<div class="form-group">
  <label for="min_length">Min Text Length</label>
  <input type="number" id="min_length" name="min_length" placeholder="0" min="0" value="{{ request.args.get('min_length', '') }}">
</div>
<div class="form-group">
  <label for="max_length">Max Text Length</label>
  <input type="number" id="max_length" name="max_length" placeholder="∞" min="0" value="{{ request.args.get('max_length', '') }}">
</div>
```

And remove from `getFormFilterParams()` in JavaScript (lines ~925-926, 934-935):
```javascript
// DELETE:
const minLength = document.getElementById('min_length').value;
const maxLength = document.getElementById('max_length').value;
// DELETE:
if (minLength) params.set('min_length', minLength);
if (maxLength) params.set('max_length', maxLength);
```

- [ ] **Step 7: Run tests**

Run: `pytest tests/test_search_api.py tests/test_p1_s4_api_search.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add openrecall/server/api_v1.py openrecall/server/search/engine.py openrecall/server/search/hybrid_engine.py openrecall/client/web/templates/search.html tests/test_search_api.py
git commit -m "refactor(search): remove deprecated min_length/max_length parameters"
```

---

### Task 3: Add include_text and max_text_length Parameters

**Files:**
- Modify: `openrecall/server/api_v1.py`
- Modify: `openrecall/server/search/engine.py`
- Modify: `openrecall/server/search/hybrid_engine.py`
- Test: `tests/test_p1_s4_api_search.py`

- [ ] **Step 1: Write failing test for include_text=false**

```python
# In tests/test_p1_s4_api_search.py, add new test class:

class TestSearchAPITextControl:
    """Tests for include_text and max_text_length parameters."""

    def test_search_exclude_text_by_default(self, app_with_search_route, mock_search_engine):
        """Text field is excluded by default."""
        with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_search_engine):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=test")
            data = json.loads(response.data)

            for item in data.get("data", []):
                content = item.get("content", {})
                assert "text" not in content or content.get("text") is None

    def test_search_include_text_when_requested(self, app_with_search_route, mock_search_engine):
        """Text field is included when include_text=true."""
        with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_search_engine):
            client = app_with_search_route.test_client()
            response = client.get("/v1/search?q=test&include_text=true")
            data = json.loads(response.data)

            for item in data.get("data", []):
                content = item.get("content", {})
                assert "text" in content
                assert content.get("text") is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_p1_s4_api_search.py::TestSearchAPITextControl -v`
Expected: FAIL

- [ ] **Step 3: Add include_text parameter parsing**

In `openrecall/server/api_v1.py`, add after limit/offset parsing (~line 970):

```python
# Parse include_text (default false)
include_text = request.args.get("include_text", "false").strip().lower() in ("true", "1", "yes")

# Parse max_text_length (default 1000)
try:
    max_text_length = int(request.args.get("max_text_length", 1000))
except (ValueError, TypeError):
    max_text_length = 1000
max_text_length = max(1, max_text_length)
```

- [ ] **Step 4: Pass include_text to search engines**

Modify the search engine calls in `api_v1.py`:

```python
# For FTS mode:
results, total = engine.search(
    q=q,
    limit=limit,
    offset=offset,
    start_time=start_time,
    end_time=end_time,
    app_name=app_name,
    window_name=window_name,
    browser_url=browser_url,
    focused=focused,
    include_text=include_text,
    max_text_length=max_text_length,
)

# For hybrid/vector mode:
results, total = hybrid_engine.search(
    q=q,
    mode=mode,
    limit=limit,
    offset=offset,
    start_time=start_time,
    end_time=end_time,
    app_name=app_name,
    window_name=window_name,
    browser_url=browser_url,
    focused=focused,
    include_text=include_text,
    max_text_length=max_text_length,
)
```

- [ ] **Step 5: Update SearchEngine.search() to handle include_text**

In `openrecall/server/search/engine.py`, modify the `search()` method:

```python
def search(
    self,
    q: str = "",
    limit: int = DEFAULT_LIMIT,
    offset: int = 0,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    app_name: Optional[str] = None,
    window_name: Optional[str] = None,
    focused: Optional[bool] = None,
    browser_url: Optional[str] = None,
    content_type: str = "all",
    include_text: bool = False,
    max_text_length: int = 1000,
) -> tuple[list[dict[str, Any]], int]:
```

And in the result building section (~line 313-332), conditionally include text:

```python
result = {
    "frame_id": frame_id,
    "timestamp": ts,
    "text_source": row["text_source"],
    "app_name": row["app_name"],
    "window_name": row["window_name"],
    "browser_url": row["browser_url"],
    "focused": bool(row["focused"]) if row["focused"] is not None else None,
    "device_name": row["device_name"] or "monitor_0",
    "frame_url": f"/v1/frames/{frame_id}",
    "fts_score": float(row["fts_rank"]) if row["fts_rank"] is not None else None,
    "embedding_status": row["embedding_status"] or "",
}
# Conditionally include text
if include_text:
    full_text = row["full_text"] or ""
    if len(full_text) > max_text_length:
        # Middle truncation
        keep_start = max_text_length // 2
        keep_end = max_text_length - keep_start
        removed = len(full_text) - max_text_length
        result["text"] = full_text[:keep_start] + f"...(truncated {removed} chars)..." + full_text[-keep_end:]
    else:
        result["text"] = full_text
```

- [ ] **Step 6: Update HybridSearchEngine.search() similarly**

In `openrecall/server/search/hybrid_engine.py`, add `include_text` and `max_text_length` parameters and implement same conditional text logic.

- [ ] **Step 7: Run tests**

Run: `pytest tests/test_p1_s4_api_search.py::TestSearchAPITextControl -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add openrecall/server/api_v1.py openrecall/server/search/engine.py openrecall/server/search/hybrid_engine.py tests/test_p1_s4_api_search.py
git commit -m "feat(search): add include_text and max_text_length parameters"
```

---

### Task 4: Add description Field to Results

**Files:**
- Modify: `openrecall/server/search/engine.py`
- Modify: `openrecall/server/search/hybrid_engine.py`
- Modify: `openrecall/server/database/frames_store.py`
- Test: `tests/test_search_engine.py`

- [ ] **Step 1: Write failing test for description field**

```python
# In tests/test_search_engine.py, add:

def test_search_result_includes_description_when_available(tmp_path, test_db_with_description):
    """Search result includes description field when available."""
    from openrecall.server.search.engine import SearchEngine

    engine = SearchEngine(db_path=test_db_with_description)
    results, total = engine.search(q="test", include_text=True)

    assert total > 0
    result = results[0]
    assert "description" in result
    assert result["description"] is not None
    assert "narrative" in result["description"]
    assert "summary" in result["description"]
    assert "tags" in result["description"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_search_engine.py::test_search_result_includes_description_when_available -v`
Expected: FAIL

- [ ] **Step 3: Add helper method to fetch descriptions**

In `openrecall/server/database/frames_store.py`, add a method to batch fetch descriptions:

```python
def get_frame_descriptions_batch(
    self,
    conn: sqlite3.Connection,
    frame_ids: list[int],
) -> dict[int, dict]:
    """Get descriptions for multiple frames.

    Returns:
        Dict mapping frame_id to description dict with keys:
        narrative, summary, tags
    """
    if not frame_ids:
        return {}

    import json
    placeholders = ",".join("?" * len(frame_ids))
    cursor = conn.execute(
        f"""
        SELECT frame_id, narrative, summary, tags_json
        FROM frame_descriptions
        WHERE frame_id IN ({placeholders})
        """,
        frame_ids,
    )

    result = {}
    for row in cursor:
        result[row[0]] = {
            "narrative": row[1],
            "summary": row[2],
            "tags": json.loads(row[3]) if row[3] else [],
        }
    return result
```

- [ ] **Step 4: Update SearchEngine to fetch descriptions**

In `openrecall/server/search/engine.py`, modify the search method to fetch descriptions after getting frame IDs:

```python
# After fetching results, get descriptions
frame_ids = [row["frame_id"] for row in rows]
descriptions = {}  # Will be fetched below

# Fetch descriptions if there are frames
if frame_ids:
    from openrecall.server.database.frames_store import FramesStore
    store = FramesStore()
    with store._connect() as desc_conn:
        descriptions = store.get_frame_descriptions_batch(desc_conn, frame_ids)

# In the result building loop:
result = {
    # ... existing fields ...
    "description": descriptions.get(frame_id),  # None if not available
}
```

- [ ] **Step 5: Update HybridSearchEngine similarly**

In `openrecall/server/search/hybrid_engine.py`, add description fetching in `_hybrid_search`, `_vector_only_search`, and `_get_recent_embedded_frames` methods.

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_search_engine.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add openrecall/server/database/frames_store.py openrecall/server/search/engine.py openrecall/server/search/hybrid_engine.py tests/test_search_engine.py
git commit -m "feat(search): add description field to search results"
```

---

### Task 5: Remove Deprecated Output Fields (type, tags, file_path)

**Files:**
- Modify: `openrecall/server/api_v1.py:1066-1083`
- Modify: `openrecall/server/search/engine.py`
- Modify: `openrecall/server/search/hybrid_engine.py`
- Test: `tests/test_p1_s4_api_search.py`

- [ ] **Step 1: Update test for removed fields**

In `tests/test_p1_s4_api_search.py`, modify `test_data_items_have_type_field` and `test_reserved_fields_present`:

```python
def test_data_items_have_no_type_field(self, app_with_search_route, mock_search_engine):
    """Type field is removed from response."""
    with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_search_engine):
        client = app_with_search_route.test_client()
        response = client.get("/v1/search?q=hello")
        data = json.loads(response.data)

        for item in data.get("data", []):
            # Response items are flat, not wrapped in content with type
            assert "type" not in item

def test_removed_fields_not_present(self, app_with_search_route, mock_search_engine):
    """Removed fields (tags, file_path) are not in response."""
    with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_search_engine):
        client = app_with_search_route.test_client()
        response = client.get("/v1/search?q=hello")
        data = json.loads(response.data)

        for item in data.get("data", []):
            assert "tags" not in item
            assert "file_path" not in item
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_p1_s4_api_search.py::TestSearchAPIResponseSchema -v`
Expected: FAIL

- [ ] **Step 3: Remove type wrapper and deprecated fields from API response**

In `openrecall/server/api_v1.py`, modify the response building section (~lines 1056-1111):

```python
# Build response - flat structure, no type wrapper
data_items = []
for r in results:
    item = {
        "frame_id": r["frame_id"],
        "timestamp": r.get("timestamp"),
        "text_source": r.get("text_source"),
        "app_name": r.get("app_name"),
        "window_name": r.get("window_name"),
        "browser_url": r.get("browser_url"),
        "focused": r.get("focused"),
        "device_name": r.get("device_name", "monitor_0"),
        "frame_url": r.get("frame_url", ""),
        "embedding_status": r.get("embedding_status", ""),
        "description": r.get("description"),
    }

    # Add text if include_text=True and present
    if r.get("text") is not None:
        item["text"] = r["text"]

    # Add mode-specific score fields
    if mode == "fts":
        item["score"] = r.get("fts_score")
        item["fts_score"] = r.get("fts_score")
    elif mode == "vector":
        item["score"] = r.get("cosine_score")
        item["cosine_score"] = r.get("cosine_score")
    elif mode == "hybrid":
        item["score"] = r.get("hybrid_score")
        item["fts_score"] = r.get("fts_score")
        item["cosine_score"] = r.get("cosine_score")
        item["fts_rank"] = r.get("fts_rank")
        item["vector_rank"] = r.get("vector_rank")
        item["hybrid_rank"] = r.get("hybrid_rank")

    data_items.append(item)
```

- [ ] **Step 4: Remove tags and file_path from SearchEngine results**

In `openrecall/server/search/engine.py`, remove `tags` and `file_path` from result dict.

- [ ] **Step 5: Remove tags and file_path from HybridSearchEngine results**

In `openrecall/server/search/hybrid_engine.py`, remove `tags` and `file_path` from all result building locations.

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_p1_s4_api_search.py -v`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add openrecall/server/api_v1.py openrecall/server/search/engine.py openrecall/server/search/hybrid_engine.py tests/test_p1_s4_api_search.py
git commit -m "refactor(search): remove type wrapper, tags, and file_path fields"
```

---

### Task 6: Rename fts_rank to fts_score and fts_result_rank to fts_rank

**Files:**
- Modify: `openrecall/server/api_v1.py`
- Modify: `openrecall/server/search/engine.py`
- Modify: `openrecall/server/search/hybrid_engine.py`
- Modify: `openrecall/client/web/templates/search.html`
- Test: `tests/test_p1_s4_api_search.py`

- [ ] **Step 1: Update tests for renamed fields**

```python
# In tests/test_p1_s4_api_search.py:

def test_fts_mode_returns_fts_score(self, app_with_search_route, mock_search_engine):
    """FTS mode returns fts_score (renamed from fts_rank)."""
    mock_search_engine.search.return_value = (
        [{"frame_id": 1, "fts_score": -12.5, "timestamp": "2026-01-01T00:00:00Z"}],
        1
    )
    with patch("openrecall.server.api_v1._get_search_engine", return_value=mock_search_engine):
        client = app_with_search_route.test_client()
        response = client.get("/v1/search?q=test&mode=fts")
        data = json.loads(response.data)

        item = data["data"][0]
        assert "fts_score" in item
        assert item["fts_score"] == -12.5

def test_hybrid_mode_returns_renamed_rank_fields(self, app_with_search_route, mock_search_engine):
    """Hybrid mode returns fts_rank (position) and fts_score (BM25 value)."""
    with patch("openrecall.server.api_v1.HybridSearchEngine") as mock_hybrid:
        mock_hybrid.return_value.search.return_value = (
            [{"frame_id": 1, "fts_score": -12.5, "fts_rank": 3, "vector_rank": 1,
              "hybrid_rank": 2, "hybrid_score": 0.85, "cosine_score": 0.92,
              "timestamp": "2026-01-01T00:00:00Z"}],
            1
        )
        client = app_with_search_route.test_client()
        response = client.get("/v1/search?q=test&mode=hybrid")
        data = json.loads(response.data)

        item = data["data"][0]
        # fts_score is the BM25 score value
        assert "fts_score" in item
        # fts_rank is the position in FTS results
        assert "fts_rank" in item
        # Old names should not be present
        assert "fts_result_rank" not in item
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_p1_s4_api_search.py -k "fts_score or fts_rank" -v`
Expected: FAIL

- [ ] **Step 3: Rename fields in SearchEngine**

In `openrecall/server/search/engine.py`, change:

```python
# In result dict, change:
"fts_rank": float(row["fts_rank"]) if row["fts_rank"] is not None else None,

# To:
"fts_score": float(row["fts_rank"]) if row["fts_rank"] is not None else None,
```

- [ ] **Step 4: Rename fields in HybridSearchEngine**

In `openrecall/server/search/hybrid_engine.py`, change:

```python
# In _hybrid_search result building, change:
"fts_rank": fts_bm25_scores.get(frame_id),  # BM25 score
"fts_result_rank": fts_ranks.get(frame_id),  # Rank in FTS results

# To:
"fts_score": fts_bm25_scores.get(frame_id),  # BM25 score value
"fts_rank": fts_ranks.get(frame_id),  # Rank position in FTS results
```

- [ ] **Step 5: Update API response building**

In `openrecall/server/api_v1.py`, the field names already come from the engine, but ensure the response uses the correct names.

- [ ] **Step 6: Update frontend**

In `openrecall/client/web/templates/search.html`, update `renderScoreInfo` function (~line 1015-1081):

```javascript
function renderScoreInfo(content, idx, pagination) {
    const offset = pagination.offset;
    const rank = offset + idx + 1;

    if (searchMode === 'fts') {
      return `<div class="score-display">
        <div class="score-item">
          <span class="score-label">BM25:</span>
          <span class="score-value">${content.fts_score !== null && content.fts_score !== undefined && !isNaN(Number(content.fts_score)) ? Number(content.fts_score).toFixed(4) : '—'}</span>
        </div>
        <span class="score-separator">|</span>
        <div class="score-item">
          <span class="score-label">Rank:</span>
          <span class="score-value">#${rank}</span>
        </div>
      </div>`;
    } else if (searchMode === 'vector') {
      // ... unchanged ...
    } else if (searchMode === 'hybrid') {
      // Use renamed fields
      const ftsRank = content.fts_rank;  // Changed from fts_result_rank
      const vectorRank = content.vector_rank;
      const hybridRank = content.hybrid_rank || rank;
      return `<div class="score-display score-display-vertical">
        <div class="score-row">
          <div class="score-item">
            <span class="score-label">BM25:</span>
            <span class="score-value">${content.fts_score !== null && content.fts_score !== undefined && !isNaN(Number(content.fts_score)) ? Number(content.fts_score).toFixed(4) : '—'}</span>
          </div>
          <div class="score-item score-rank">
            <span class="score-label">Rank:</span>
            <span class="score-value">#${ftsRank || '—'}</span>
          </div>
        </div>
        <!-- ... rest unchanged ... -->
      </div>`;
    }
    return '';
}
```

Also update the type badge rendering (~line 1174) to handle flat structure:

```javascript
// The item is now flat, not wrapped in content
const frameId = item.frame_id;
const timestamp = formatTimestamp(item.timestamp);
// etc.
```

- [ ] **Step 7: Run tests**

Run: `pytest tests/test_p1_s4_api_search.py tests/test_hybrid_search.py -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add openrecall/server/api_v1.py openrecall/server/search/engine.py openrecall/server/search/hybrid_engine.py openrecall/client/web/templates/search.html tests/test_p1_s4_api_search.py
git commit -m "refactor(search): rename fts_rank to fts_score, fts_result_rank to fts_rank"
```

---

### Task 7: Update Frontend for Flat Response Structure

**Files:**
- Modify: `openrecall/client/web/templates/search.html`

- [ ] **Step 1: Update renderResults for flat structure**

In `openrecall/client/web/templates/search.html`, update the `renderResults` function (~line 1099-1180) to handle flat response items instead of `{ type, content }` wrapper:

```javascript
function renderResults(data, pagination) {
    currentResults = data;
    currentPagination = pagination;

    // ... existing code for embedding count ...

    if (!data || data.length === 0) {
      // ... existing empty state ...
      return;
    }

    const html = data.map((item, idx) => {
      // Item is now flat, not wrapped in content
      const frameId = item.frame_id;
      const timestamp = formatTimestamp(item.timestamp);
      const relativeTime = formatRelativeTime(item.timestamp);
      const appName = item.app_name || 'Unknown';
      const windowName = item.window_name || '';
      const text = item.text || '';

      return `
        <article class="memory-card">
          <div class="card-header-v2">
            <div class="header-row context-row">
              <div class="context-left">
                <span class="app-name" title="${windowName.replace(/"/g, '&quot;')}">${appName}</span>
              </div>
              <span class="relative-time">${relativeTime}</span>
            </div>
            <div class="header-row window-row">
              <span class="window-name">${windowName}</span>
            </div>
            <div class="header-row time-row">
              <span class="timestamp">${timestamp}</span>
              <span class="device-name">${item.device_name || 'monitor_0'}</span>
            </div>
          </div>
          <div class="card-image-wrapper">
            <img
              src="${EDGE_BASE_URL}/v1/frames/${frameId}"
              alt="Screenshot"
              class="card-image js-open-modal"
              loading="lazy"
              data-index="${idx}"
            >
          </div>
          <div class="card-footer">
            <div class="score-display">${renderScoreInfo(item, idx, pagination)}</div>
            ${renderEmbeddingBadge(item)}
            <div class="result-position">#${idx + 1} / ${pagination.total}</div>
          </div>
        </article>
      `;
    }).join('');

    // ... rest unchanged ...
}
```

- [ ] **Step 2: Update modal and other references**

Update `updateModalImage` and other functions that reference `item.content`:

```javascript
function updateModalImage() {
    if (!currentResults.length) return;
    currentIndex = normalizeIndex(currentIndex);
    const item = currentResults[currentIndex];
    modalImage.src = `${EDGE_BASE_URL}/v1/frames/${item.frame_id}`;
    modalCount.textContent = `${currentIndex + 1} / ${currentResults.length}`;
    modalApp.textContent = item.app_name || 'Unknown';
    modalTime.textContent = formatTimestamp(item.timestamp);
}
```

- [ ] **Step 3: Update renderEmbeddingBadge**

```javascript
function renderEmbeddingBadge(item) {
    const status = item.embedding_status;
    const hasEmbedding = status === 'completed' ||
                         (item.cosine_score !== null && item.cosine_score !== undefined);
    // ... rest unchanged ...
}
```

- [ ] **Step 4: Remove type badge rendering**

Remove the type badge from the footer since `type` field no longer exists:

```javascript
// Remove this from the card footer template:
// <span class="type-badge type-${item.type.toLowerCase()}">${item.type === 'Accessibility' ? 'AX' : item.type}</span>
```

- [ ] **Step 5: Test manually**

Open browser to search page and verify:
- Results render correctly
- Score info displays properly
- Modal opens and navigates

- [ ] **Step 6: Commit**

```bash
git add openrecall/client/web/templates/search.html
git commit -m "refactor(search): update frontend for flat response structure"
```

---

### Task 8: Update Hybrid Search Tests

**Files:**
- Modify: `tests/test_hybrid_search.py`

- [ ] **Step 1: Update test expectations for renamed fields**

Run existing tests to identify failures:

Run: `pytest tests/test_hybrid_search.py -v`

- [ ] **Step 2: Fix any failing tests**

Update test assertions to use new field names (`fts_score`, `fts_rank` instead of old names).

- [ ] **Step 3: Run all search tests**

Run: `pytest tests/test_search_api.py tests/test_p1_s4_api_search.py tests/test_hybrid_search.py tests/test_search_engine.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_hybrid_search.py
git commit -m "test(search): update hybrid search tests for renamed fields"
```

---

### Task 9: Final Integration Test and Documentation

**Files:**
- Modify: `docs/superpowers/specs/2026-04-13-search-api-optimization-design.md`

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -k search -v`
Expected: All tests pass

- [ ] **Step 2: Manual API test**

```bash
# Start server
./run_server.sh --mode local &

# Test default mode is hybrid
curl "http://localhost:8083/v1/search?q=test" | jq '.data[0] | keys'

# Test include_text
curl "http://localhost:8083/v1/search?q=test&include_text=true" | jq '.data[0].text'

# Test large limit
curl "http://localhost:8083/v1/search?q=test&limit=500" | jq '.pagination.limit'
```

- [ ] **Step 3: Update spec with final status**

Change spec status from "Draft" to "Implemented".

- [ ] **Step 4: Final commit**

```bash
git add docs/superpowers/specs/2026-04-13-search-api-optimization-design.md
git commit -m "docs: mark search API optimization spec as implemented"
```
