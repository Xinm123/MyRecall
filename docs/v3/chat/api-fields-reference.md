# API Response Fields Reference

> **Purpose:** Single source of truth for v1 API response contracts.
> All other documentation (mvp.md, skill definitions, HTTP contracts) must reference this document.
> Last updated: 2026-04-13

---

## Table of Contents

- [GET /v1/frames/{id}](#get-v1framesid)
- [GET /v1/frames/{id}/context](#get-v1framesidcontext)
- [GET /v1/search](#get-v1search)
- [GET /v1/activity-summary](#get-v1activity-summary)

---

## GET /v1/frames/{id}

**Purpose:** Serve the JPEG snapshot for a frame.

**Returns:** `image/jpeg` (raw binary)

**Query Parameters:** None

**Error Responses:**

| Status | Condition | Body |
|--------|-----------|------|
| 404 | frame_id not in DB | `{"error": "frame not found", "code": "NOT_FOUND", "request_id": "<uuid>"}` |
| 404 | `snapshot_path` not set in DB | `{"error": "frame snapshot path not set", "code": "NOT_FOUND", "request_id": "<uuid>"}` |
| 404 | snapshot file missing on disk | `{"error": "frame snapshot file not found on disk", "code": "NOT_FOUND", "request_id": "<uuid>"}` |

**Notes:**
- Frame is served from the `snapshot_path` stored in the DB for the frame (typically `{frames_dir}/{capture_id}.jpg`)
- No JSON response — binary image data only

---

## GET /v1/frames/{id}/context

**Purpose:** Return frame context for chat grounding — text content, parsed accessibility tree, and extracted URLs.

**Returns:** `application/json`

### Response Fields

| Field | Type | Always Present | Description |
|-------|------|:--------------:|-------------|
| `frame_id` | `int` | Yes | Frame identifier |
| `timestamp` | `string \| null` | Yes | ISO8601 UTC capture timestamp, from `frames.timestamp` |
| `app_name` | `string \| null` | Yes | Application name at capture time, from `frames.app_name` |
| `window_name` | `string \| null` | Yes | Window title at capture time, from `frames.window_name` |
| `description` | `object \| null` | Yes | AI-generated frame description (object with `narrative`, `summary`, `tags`). Returns `null` when no description has been generated. |
| `text` | `string \| null` | Yes | `accessibility_text` if AX-first succeeded, else `ocr_text` |
| `text_source` | `string` | Yes | `"accessibility"` \| `"ocr"` \| `"hybrid"` (lowercase) |
| `urls` | `string[]` | Yes | Extracted URLs from text via regex. Deduplicated. |
| `browser_url` | `string \| null` | Yes | `browser_url` field from frames table |
| `status` | `string` | Yes | `processing_status` from frames table: `"pending"` \| `"processing"` \| `"completed"` \| `"failed"` |

### Description Object (when description is not null)

| Field | Type | Always Present | Description |
|-------|------|:--------------:|-------------|
| `narrative` | `string` | Yes | Human-readable description of what's happening in the frame |
| `summary` | `string` | Yes | Brief one-line summary |
| `tags` | `string[]` | Yes | Array of descriptive tags |

### Example Response

```json
// GET /v1/frames/42/context
// (description available)

{
  "frame_id": 42,
  "timestamp": "2026-03-26T14:32:05Z",
  "app_name": "Claude Code",
  "window_name": "Claude Code — ~/chat/MyRecall",
  "description": {
    "narrative": "The user is working on MyRecall v3 chat functionality in Claude Code, reviewing the API fields reference documentation.",
    "summary": "Working on API documentation in Claude Code",
    "tags": ["claude-code", "documentation", "api"]
  },
  "text": "MyRecall v3 Chat API MyRecall Search Claude Code Today 14:32",
  "text_source": "accessibility",
  "urls": [
    "https://github.com/anthropics/claude-code"
  ],
  "browser_url": null,
  "status": "completed"
}
```

```json
// GET /v1/frames/43/context
// (no description generated yet)

{
  "frame_id": 43,
  "timestamp": "2026-03-26T14:33:05Z",
  "app_name": "Terminal",
  "window_name": "zsh — 120×40",
  "description": null,
  "text": "ls -la\nopenrecall\nmyrecall\nscreenshots",
  "text_source": "ocr",
  "urls": [],
  "browser_url": null,
  "status": "completed"
}
```

### Known Gaps (vs screenpipe)

- ❌ `device_name` / `monitor_index` — not returned
- ❌ `capture_trigger` — not returned

---

## GET /v1/search

**Purpose:** Full-text and semantic search across frames with metadata filtering. Default mode is `hybrid` (combines FTS + vector search).

**Returns:** `application/json`

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `q` | `string` | `""` | Text search query. Empty query returns browse mode (recent frames). |
| `mode` | `string` | `"hybrid"` | Search mode: `"fts"` \| `"vector"` \| `"hybrid"` |
| `limit` | `int` | `20` | Max results per page (no max limit) |
| `offset` | `int` | `0` | Pagination offset |
| `start_time` | `string` | — | ISO8601 start of time range |
| `end_time` | `string` | — | ISO8601 end of time range |
| `app_name` | `string` | — | Filter by app name |
| `window_name` | `string` | — | Filter by window name |
| `browser_url` | `string` | — | Filter by browser URL |
| `focused` | `boolean` | — | Filter by focus state |
| `include_text` | `boolean` | `false` | Include `text` field in response |
| `max_text_length` | `int` | `200` | Max characters for `text` field (middle-truncated) |
| `content_type` | `string` | `"all"` | **Deprecated** — ignored. All searches return merged results. |

### Response Fields

| Field | Type | Always Present | Description |
|-------|------|:--------------:|-------------|
| `data` | `object[]` | Yes | Array of matching frames (flat structure, no wrapper) |
| `data[].frame_id` | `int` | Yes | Frame identifier |
| `data[].timestamp` | `string` | Yes | ISO8601 UTC timestamp |
| `data[].text_source` | `string \| null` | Yes | `"ocr"` \| `"accessibility"` \| `"hybrid"` \| `null` |
| `data[].text` | `string` | No | Frame text (only when `include_text=true`). Middle-truncated if exceeds `max_text_length`. |
| `data[].app_name` | `string \| null` | Yes | Application name |
| `data[].window_name` | `string \| null` | Yes | Window name |
| `data[].browser_url` | `string \| null` | Yes | Browser URL if applicable |
| `data[].focused` | `boolean \| null` | Yes | Whether this frame's app was focused |
| `data[].device_name` | `string` | Yes | Defaults to `"monitor_0"` |
| `data[].frame_url` | `string` | Yes | URL to fetch frame image: `/v1/frames/{frame_id}` |
| `data[].embedding_status` | `string` | Yes | `"completed"` \| `"pending"` \| `"failed"` \| `""` |
| `data[].description` | `object \| null` | No | AI-generated description (when available): `{narrative, summary, tags[]}` |
| `data[].score` | `number` | No | Unified relevance score (all modes) |
| `data[].fts_score` | `number \| null` | No | BM25 score (fts/hybrid modes). Negative, higher (closer to 0) = more relevant. |
| `data[].fts_rank` | `int \| null` | No | Position in FTS results (hybrid mode) |
| `data[].cosine_score` | `number \| null` | No | Vector cosine similarity 0-1, higher = more similar (vector/hybrid modes) |
| `data[].hybrid_rank` | `int \| null` | No | Final RRF fused rank (hybrid mode) |
| `data[].vector_rank` | `int \| null` | No | Position in vector results (hybrid mode) |
| `pagination` | `object` | Yes | Pagination info |
| `pagination.limit` | `int` | Yes | Requested page size |
| `pagination.offset` | `int` | Yes | Current offset |
| `pagination.total` | `int` | Yes | Total matching results |

### Score Fields by Mode

| Mode | Score Fields Returned |
|------|----------------------|
| `fts` | `score`, `fts_score` |
| `vector` | `score`, `cosine_score` |
| `hybrid` | `score`, `fts_score`, `fts_rank`, `cosine_score`, `hybrid_rank`, `vector_rank` |

### Description Object (when description is not null)

| Field | Type | Always Present | Description |
|-------|------|:--------------:|-------------|
| `narrative` | `string` | Yes | Human-readable description of what's happening in the frame |
| `summary` | `string` | Yes | Brief one-line summary |
| `tags` | `string[]` | Yes | Array of descriptive tags |

### Example Response

```json
// GET /v1/search?q=claude+code&limit=2
// Default mode=hybrid returns all score fields

{
  "data": [
    {
      "frame_id": 42,
      "timestamp": "2026-04-13T14:32:05Z",
      "text_source": "accessibility",
      "app_name": "Claude Code",
      "window_name": "Claude Code — ~/chat/MyRecall",
      "browser_url": null,
      "focused": true,
      "device_name": "monitor_0",
      "frame_url": "/v1/frames/42",
      "embedding_status": "completed",
      "description": {
        "narrative": "User is working on API documentation...",
        "summary": "Working on API docs in Claude Code",
        "tags": ["claude-code", "documentation"]
      },
      "score": 0.0082,
      "fts_score": -1.1317,
      "fts_rank": 1,
      "cosine_score": 0.95,
      "hybrid_rank": 1,
      "vector_rank": 2
    },
    {
      "frame_id": 41,
      "timestamp": "2026-04-13T14:31:05Z",
      "text_source": "ocr",
      "app_name": "Terminal",
      "window_name": "zsh — 120×40",
      "browser_url": null,
      "focused": false,
      "device_name": "monitor_0",
      "frame_url": "/v1/frames/41",
      "embedding_status": "completed",
      "description": null,
      "score": 0.0065,
      "fts_score": -1.5234,
      "fts_rank": 2,
      "cosine_score": 0.88,
      "hybrid_rank": 2,
      "vector_rank": 3
    }
  ],
  "pagination": {
    "limit": 2,
    "offset": 0,
    "total": 17
  }
}
```

```json
// GET /v1/search?app_name=Chrome&start_time=2026-04-13T00:00:00Z&end_time=2026-04-13T23:59:59Z&limit=1&include_text=true&max_text_length=50

{
  "data": [
    {
      "frame_id": 99,
      "timestamp": "2026-04-13T10:15:33Z",
      "text": "GitHub Dashboard Pull requests Issues...143 chars...openrecall MyRecall",
      "text_source": "accessibility",
      "app_name": "Chrome",
      "window_name": "GitHub — MyRecall — Dashboard",
      "browser_url": "https://github.com/pyw/openrecall",
      "focused": true,
      "device_name": "monitor_0",
      "frame_url": "/v1/frames/99",
      "embedding_status": "completed",
      "description": {
        "narrative": "User viewing GitHub repository dashboard...",
        "summary": "Browsing GitHub repo",
        "tags": ["github", "code"]
      },
      "score": 0.005,
      "fts_score": -2.1,
      "fts_rank": 1,
      "cosine_score": null,
      "hybrid_rank": 1,
      "vector_rank": null
    }
  ],
  "pagination": {
    "limit": 1,
    "offset": 0,
    "total": 5
  }
}
```

### Text Truncation Format

When `include_text=true` and text exceeds `max_text_length`:
```
"first_half...N chars...second_half"
```

Example: `"Hello world this is a...143 chars...the end of the document"`

### Known Gaps (vs screenpipe)

- ❌ `tags` at top level — removed; use `description.tags` instead
- ❌ `file_path` — removed; use `frame_url` to fetch image
- ❌ `type` field — removed; use `text_source` instead

---

## GET /v1/activity-summary

**Purpose:** Lightweight compressed activity overview for a time range. Returns app usage (with accurate time-based minutes), AI-generated descriptions, and audio summary.

**Returns:** `application/json`

### Response Fields

| Field | Type | Always Present | Description |
|-------|------|:--------------:|-------------|
| `apps` | `object[]` | Yes | App usage statistics, ordered by `minutes` descending |
| `apps[].name` | `string` | Yes | Application name (`app_name`). Falls back to `"Unknown"` when `app_name` is NULL in DB. |
| `apps[].frame_count` | `int` | Yes | Number of completed frames captured for this app in the time range |
| `apps[].minutes` | `number` | Yes | Accurate usage in minutes. Calculated from actual timestamp gaps between consecutive frames using SQLite LEAD() window function. Only gaps < 300 seconds (5 min) count, filtering out "away from computer" periods. |
| `apps[].first_seen` | `string` | Yes | ISO8601 timestamp of the first frame captured for this app in the range |
| `apps[].last_seen` | `string` | Yes | ISO8601 timestamp of the last frame captured for this app in the range |
| `total_frames` | `int` | Yes | Total completed frames in the time range |
| `time_range` | `object` | Yes | Requested time range |
| `time_range.start` | `string` | Yes | ISO8601 start time |
| `time_range.end` | `string` | Yes | ISO8601 end time |
| `audio_summary` | `object` | Yes | Audio transcription summary. **Currently empty shell in vision-only MVP.** |
| `audio_summary.segment_count` | `int` | Yes | Always `0` in MVP |
| `audio_summary.speakers` | `object[]` | Yes | Always `[]` in MVP |
| `descriptions` | `object[]` | Yes | AI-generated frame descriptions. Sorted by frame timestamp descending. Returns `[]` when no frames in range have completed descriptions. |
| `descriptions[].frame_id` | `int` | Yes | Frame identifier |
| `descriptions[].timestamp` | `string` | Yes | ISO8601 timestamp of the frame |
| `descriptions[].summary` | `string` | Yes | Short summary of activity |
| `descriptions[].intent` | `string` | Yes | Detected intent |
| `descriptions[].entities` | `string[]` | Yes | Extracted entities |

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `start_time` | `string` | — | **Required.** ISO8601 start of time range |
| `end_time` | `string` | — | **Required.** ISO8601 end of time range |
| `app_name` | `string` | — | Optional app filter — returns only this app's stats |
| `max_descriptions` | `int` | — | Maximum number of `descriptions` entries to return. No default — all available descriptions within time range are returned if unspecified. Max 1000. |

### Example Response

```json
// GET /v1/activity-summary?start_time=2026-03-26T09:00:00Z&end_time=2026-03-26T18:00:00Z&max_descriptions=3

{
  "apps": [
    {
      "name": "Claude Code",
      "frame_count": 180,
      "minutes": 42.5,
      "first_seen": "2026-03-26T10:05:22Z",
      "last_seen": "2026-03-26T11:32:08Z"
    },
    {
      "name": "Chrome",
      "frame_count": 120,
      "minutes": 28.0,
      "first_seen": "2026-03-26T09:15:00Z",
      "last_seen": "2026-03-26T10:03:00Z"
    }
  ],
  "total_frames": 360,
  "time_range": {
    "start": "2026-03-26T09:00:00Z",
    "end": "2026-03-26T18:00:00Z"
  },
  "audio_summary": {
    "segment_count": 0,
    "speakers": []
  },
  "descriptions": [
    {
      "frame_id": 108,
      "timestamp": "2026-03-26T17:58:05Z",
      "summary": "Editing API reference docs",
      "intent": "writing documentation",
      "entities": ["Claude Code", "API", "activity-summary"]
    },
    {
      "frame_id": 95,
      "timestamp": "2026-03-26T16:30:00Z",
      "summary": "Viewing GitHub repo README",
      "intent": "browsing",
      "entities": ["GitHub", "openrecall", "MyRecall"]
    }
  ]
}
```

```json
// GET /v1/activity-summary?start_time=2026-03-26T09:00:00Z&end_time=2026-03-26T18:00:00Z&app_name=Chrome
// (filtered by app_name — returns only Chrome stats)

{
  "apps": [
    {
      "name": "Chrome",
      "frame_count": 120,
      "minutes": 28.0,
      "first_seen": "2026-03-26T09:15:00Z",
      "last_seen": "2026-03-26T10:03:00Z"
    }
  ],
  "total_frames": 120,
  "time_range": {
    "start": "2026-03-26T09:00:00Z",
    "end": "2026-03-26T18:00:00Z"
  },
  "audio_summary": {
    "segment_count": 0,
    "speakers": []
  },
  "descriptions": []
}
```

### Known Gaps (vs screenpipe)

| Gap | screenpipe | MyRecall | Impact |
|-----|-----------|----------|--------|
| `window_name` per app | ❌ Not included | ❌ Not included | Limited |
| `focused` flag | ❌ Not included | ❌ Not included | Limited |

---

## Field Naming Authority

This document is the **authoritative reference** for field names. When adding, removing, or renaming fields:

1. Update this document first
2. Update affected endpoint implementations
3. Update test fixtures and contracts
4. Propagate changes to skill definitions and UI code

---

## Changelog

| Date | Change |
|------|--------|
| 2026-03-26 | Initial document. Documented all four v1 endpoints. Identified naming inconsistencies and gaps vs screenpipe. |
| 2026-03-26 | Fixed `descriptions[]` to include `narrative` and `entities` (was missing in `get_recent_descriptions`). Added error response body examples for `GET /v1/frames/{id}`. Clarified snapshot path source. Documented `minutes` rounding to 2 decimal places. Documented `null` text_source mapping to `"OCR"` type. |
| 2026-03-26 | Removed `properties` field from `nodes[]` example JSON (it is never included in response, not even as `null`). Clarified `nodes[].properties` description. Added `hybrid` to text_source description. |
| 2026-03-26 | Fixed three doc/code inconsistencies: (1) corrected `max_descriptions` description — it limits `descriptions` count, not `recent_texts` (which has a separate fixed cap of 10); (2) documented `apps[].name` fallback to `"Unknown"` when DB `app_name` is NULL; (3) documented that `descriptions` returns `[]` when no frames in range have completed descriptions. |
| 2026-03-26 | Added `timestamp`, `app_name`, `window_name` fields to `GET /v1/frames/{id}/context` response. Fixed bounds description: normalized 0.0–1.0 floats, rounded to 3 decimal places. Removed resolved gaps from Known Gaps table. |
| 2026-04-01 | Major activity-summary redesign: (1) removed `recent_texts` field entirely; (2) `apps[].minutes` now uses screenpipe LEAD() method with 5-min threshold; (3) added `apps[].first_seen` and `apps[].last_seen`; (4) `apps` ordered by `minutes DESC`; (5) `descriptions[]` now has `frame_id, timestamp, summary, intent, entities` (narrative removed); (6) `max_descriptions` has no default (returns all available); (7) Known Gaps table updated — first_seen/last_seen and minutes calculation gaps are now resolved. |
| 2026-04-13 | **Major search API optimization**: (1) Response structure flattened — removed `type` field and `content` wrapper; (2) Removed `tags` and `file_path` fields; (3) Default mode changed to `hybrid`; (4) Added `mode` parameter (`fts`/`vector`/`hybrid`); (5) Added `include_text` and `max_text_length` parameters; (6) Removed `min_length`/`max_length` parameters; (7) No limit max (was 100); (8) Added score fields: `score`, `fts_score`, `fts_rank`, `cosine_score`, `hybrid_rank`, `vector_rank`; (9) Added `description` and `embedding_status` fields; (10) Resolved naming inconsistency — now uses `text_source` consistently (removed `type`). |
