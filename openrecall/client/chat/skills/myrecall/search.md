# Search Node — `GET /v1/search`

**Purpose**: Full-text and semantic search across all captured screen content. Default mode is `hybrid` (combines FTS + vector search with RRF fusion).

## When to Use

- "Did I see anything about X?"
- "Find frames with text Y"
- "What did I see in Chrome/Safari/VSCode?"
- Specific content search after summary doesn't answer the question

## When to Escalate to Content

If search returns relevant frames and the user wants details:

- "What was I doing in this specific frame?" → load `content.md` for frame context
- "What URLs were open?" → load `content.md`
- "Show me the screenshot" → load `content.md` for frame image

## ⚠️ `content_type` Parameter is Deprecated

> **IMPORTANT**: The `content_type` parameter (`ocr`, `accessibility`, `all`) is **deprecated**.
> Behavior is inconsistent — it is ignored in most cases but may log warnings. Do NOT use this
> parameter to filter results; it has no reliable effect.

## Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `q` | string | No | Search query. Matched against all screen text. Empty query returns browse mode. |
| `mode` | string | No | Search mode: `fts`, `vector`, `hybrid` (default: `hybrid`) |
| `limit` | integer | No | Max results (default: 20, no max limit) |
| `offset` | integer | No | Pagination offset (default: 0) |
| `start_time` | ISO 8601 local | Recommended | Start of time range (local time) |
| `end_time` | ISO 8601 local | Recommended | End of time range (local time) |
| `app_name` | string | No | Filter by exact app name |
| `window_name` | string | No | Filter by window title |
| `browser_url` | string | No | Filter by browser URL substring |
| `focused` | boolean | No | Only focused windows (`true`/`false`) |
| `include_text` | boolean | No | Include `text` field in response (default: `false`) |
| `max_text_length` | integer | No | Max characters for `text` field with middle-truncation (default: 200) |

> **`include_text`**: When `include_text=true`, text is truncated to `max_text_length` (default 200) in all modes.

> **Always include `start_time` and `end_time`**. Unbounded searches will return excessive results and may be slow.

## Request Examples

```bash
# Hybrid search (default) in the last 2 hours
START="2026-04-26T14:30:00"
END="2026-04-26T16:30:00"
curl "http://localhost:8083/v1/search?q=GitHub+PR&start_time=${START}&end_time=${END}&limit=10"

# FTS-only search (faster, keyword-based)
curl "http://localhost:8083/v1/search?q=GitHub+PR&mode=fts&start_time=${START}&end_time=${END}&limit=10"

# Vector-only search (semantic similarity)
curl "http://localhost:8083/v1/search?q=GitHub+PR&mode=vector&start_time=${START}&end_time=${END}&limit=10"
```

## Response Format

```json
{
  "data": [
    {
      "frame_id": 42,
      "timestamp": "2026-04-26T10:30:00",
      "text_source": "accessibility",
      "app_name": "Safari",
      "window_name": "Pull Request #123 — GitHub",
      "browser_url": "https://github.com/...",
      "focused": true,
      "device_name": "monitor_0",
      "frame_url": "/v1/frames/42",
      "embedding_status": "completed",
      "description": {
        "narrative": "The user is reviewing a pull request on GitHub...",
        "summary": "GitHub PR review",
        "tags": ["code_review", "github"]
      },
      "score": 0.0082,
      "fts_score": -1.1317,
      "fts_rank": 1,
      "cosine_score": 0.95,
      "hybrid_rank": 1,
      "vector_rank": 2
    }
  ],
  "pagination": {
    "limit": 20,
    "offset": 0,
    "total": 2
  }
}
```

## Key Response Fields

| Field | Description |
|-------|-------------|
| `frame_id` | Unique frame ID — use with `/frames/{id}/context` for details |
| `timestamp` | ISO8601 local capture time |
| `text_source` | `accessibility` (from AX tree), `ocr` (fallback), or `hybrid` |
| `text` | Screen text (only included when `include_text=true`, truncated to `max_text_length`) |
| `app_name` | Application name at capture time |
| `window_name` | Window title at capture time |
| `browser_url` | Browser URL at capture time (only for browser frames) |
| `focused` | Whether window was focused |
| `device_name` | Monitor/device name |
| `frame_url` | API path to fetch frame image |
| `embedding_status` | Vector embedding status: `""` (not queued), `pending`, `completed`, or `failed` |
| `description` | AI-generated description object with `narrative`, `summary`, `tags[]`. Omitted if `description_status` is not `completed`. |
| `score` | Unified relevance score (all modes) |
| `fts_score` | FTS5 BM25 score — typically negative, more negative = better match |
| `cosine_score` | Vector cosine similarity 0-1, higher = more similar |
| `fts_rank` | Position in FTS results (hybrid mode only) |
| `vector_rank` | Position in vector results (hybrid mode only) |
| `hybrid_rank` | Final RRF fused rank (hybrid mode only) |

## Score Fields by Mode

| Mode | Score Fields Returned |
|------|----------------------|
| `fts` | `score`, `fts_score` |
| `vector` | `score`, `cosine_score` |
| `hybrid` | `score`, `fts_score`, `fts_rank`, `cosine_score`, `hybrid_rank`, `vector_rank` |

## Context Window Protection

- Use `limit=5` initially, expand if needed.
- Each result is ~500-2000 tokens.
- Avoid `include_text=true` unless frame text is specifically needed.
- Write output to file and truncate if needed.
