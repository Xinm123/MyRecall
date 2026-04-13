# Search API Optimization Design

**Date:** 2026-04-13
**Status:** Draft
**Target:** `GET /v1/search` API optimization

---

## Summary

Optimize the search API for better usability, cleaner interface, and improved search experience. Key changes include defaulting to hybrid search, removing deprecated fields, adding new capabilities, and simplifying the response structure.

---

## Input Parameters

### Final Input Fields

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `q` | string | "" | Search query for full-text / semantic search |
| `mode` | string | `"hybrid"` | Search mode: `fts` / `vector` / `hybrid` |
| `limit` | int | 20 | Max results to return (no max limit) |
| `offset` | int | 0 | Pagination offset |
| `start_time` | string | None | ISO8601 UTC start timestamp filter |
| `end_time` | string | None | ISO8601 UTC end timestamp filter |
| `app_name` | string | None | Filter by app name (exact match) |
| `window_name` | string | None | Filter by window name (exact match) |
| `browser_url` | string | None | Filter by browser URL |
| `focused` | bool | None | Filter by focused window state |
| `include_text` | bool | false | Whether to include `text` field in response |
| `max_text_length` | int | 1000 | Max characters for `text` field (middle-truncated) |

### Removed Input Fields

| Parameter | Reason |
|-----------|--------|
| `content_type` | Deprecated, accepted but ignored (already in place) |
| `min_length` | Low usage, users can filter via query |
| `max_length` | Low usage, users can filter via query |

---

## Output Fields

### Base Fields (all modes)

| Field | Type | Description |
|-------|------|-------------|
| `frame_id` | string | Unique frame identifier |
| `timestamp` | string | ISO8601 UTC capture timestamp |
| `text` | string | Frame text (only if `include_text=true`, truncated to `max_text_length`) |
| `text_source` | string | Text source: `ocr` / `accessibility` / `hybrid` |
| `app_name` | string | Application name |
| `window_name` | string | Window title |
| `browser_url` | string | Browser URL (if applicable) |
| `focused` | bool | Whether window was focused |
| `device_name` | string | Device/monitor name |
| `frame_url` | string | API path to fetch frame image |
| `embedding_status` | string | Embedding status: `completed` / `pending` / `failed` / empty |
| `description` | object | Description object if available: `{ narrative, summary, tags }` |

### Score Fields by Mode

**`mode=fts`:**

| Field | Type | Description |
|-------|------|-------------|
| `score` | float | BM25 relevance score (negative, lower = more relevant) |
| `fts_score` | float | Raw BM25 score (same as `score` in fts mode) |

**`mode=vector`:**

| Field | Type | Description |
|-------|------|-------------|
| `score` | float | Cosine similarity (0-1, higher = more similar) |
| `cosine_score` | float | Raw vector cosine similarity |

**`mode=hybrid`:**

| Field | Type | Description |
|-------|------|-------------|
| `score` | float | RRF fusion score |
| `fts_score` | float | BM25 relevance score |
| `cosine_score` | float | Vector cosine similarity |
| `fts_rank` | int | Rank in FTS results |
| `vector_rank` | int | Rank in vector results |
| `hybrid_rank` | int | Final fused rank |

### Removed Output Fields

| Field | Reason |
|-------|--------|
| `type` | Redundant with `text_source` |
| `tags` | Reserved field, always empty |
| `file_path` | Redundant with `frame_url` |

---

## Response Structure

```json
{
  "data": [
    {
      "frame_id": "abc123",
      "timestamp": "2026-04-13T10:30:00Z",
      "text": "Screenshot text content...",
      "text_source": "accessibility",
      "app_name": "Chrome",
      "window_name": "Google Search",
      "browser_url": "https://google.com",
      "focused": true,
      "device_name": "monitor_0",
      "frame_url": "/v1/frames/abc123",
      "embedding_status": "completed",
      "description": {
        "narrative": "User is searching for Python tutorials...",
        "summary": "Searching Python tutorials",
        "tags": ["search", "programming"]
      },
      "score": 0.85,
      "fts_score": -12.5,
      "cosine_score": 0.92,
      "fts_rank": 3,
      "vector_rank": 1,
      "hybrid_rank": 2
    }
  ],
  "pagination": {
    "limit": 20,
    "offset": 0,
    "total": 142
  }
}
```

---

## Changes Summary

### Input Changes

| Change | Before | After |
|--------|--------|-------|
| `mode` default | `"fts"` | `"hybrid"` |
| `limit` max | 100 | No limit |
| `min_length` | Supported | Removed |
| `max_length` | Supported | Removed |
| `include_text` | N/A | New, default `false` |
| `max_text_length` | N/A | New, default `1000` |

### Output Changes

| Change | Before | After |
|--------|--------|-------|
| `type` | Included | Removed |
| `tags` | Included (empty) | Removed |
| `file_path` | Included | Removed |
| `description` | N/A | New (when available) |
| `fts_rank` | BM25 score | Renamed to `fts_score` |
| `fts_result_rank` | FTS rank position | Renamed to `fts_rank` |
| Score fields | All returned | By mode |

---

## Implementation Notes

1. **Description Field**: Read from `frame_descriptions` table, only included when `description_status = 'completed'`

2. **Text Truncation**: Middle-truncation when exceeds `max_text_length`:
   - `"first_half...N chars...second_half"` (e.g., `"Hello worl...500 chars...orld Python"`)

3. **Score Normalization**:
   - `score` field provides unified relevance metric
   - Mode-specific scores available for debugging/analysis

4. **Backward Compatibility**:
   - `content_type` parameter accepted but ignored (existing behavior)
   - Old clients continue to work with reduced fields

---

## References

- Current implementation: `openrecall/server/api_v1.py`
- Search engine: `openrecall/server/search/engine.py`
- Hybrid engine: `openrecall/server/search/hybrid_engine.py`
- Frontend: `openrecall/client/web/templates/search.html`
- Screenpipe reference: `_ref/screenpipe/crates/screenpipe-engine/src/routes/search.rs`
