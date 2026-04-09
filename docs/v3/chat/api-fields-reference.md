# API Response Fields Reference

> **Purpose:** Single source of truth for v1 API response contracts.
> All other documentation (mvp.md, skill definitions, HTTP contracts) must reference this document.
> Last updated: 2026-03-26

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

**Purpose:** Full-text search across frames with metadata filtering.

**Returns:** `application/json`

### Response Fields

| Field | Type | Always Present | Description |
|-------|------|:--------------:|-------------|
| `data` | `object[]` | Yes | Array of matching frames |
| `data[].type` | `string` | Yes | `"OCR"` or `"Accessibility"` (capitalized). Note: inconsistent with `text_source` in other endpoints. |
| `data[].content` | `object` | Yes | Frame content details |
| `data[].content.frame_id` | `int` | Yes | Frame identifier |
| `data[].content.text` | `string` | Yes | `full_text` from frames table (merged accessibility + OCR text) |
| `data[].content.text_source` | `string \| null` | Yes | `"ocr"` \| `"accessibility"` \| `"hybrid"` \| `null`. Maps to `data[].type` as follows: `"accessibility"`/`"hybrid"` → `"Accessibility"`, `"ocr"`/`null` → `"OCR"`. |
| `data[].content.timestamp` | `string` | Yes | ISO8601 UTC timestamp |
| `data[].content.file_path` | `string` | Yes | Filename only: `{timestamp}.jpg` |
| `data[].content.frame_url` | `string` | Yes | URL to fetch frame image: `/v1/frames/{frame_id}` |
| `data[].content.app_name` | `string \| null` | Yes | Application name |
| `data[].content.window_name` | `string \| null` | Yes | Window name |
| `data[].content.browser_url` | `string \| null` | Yes | Browser URL if applicable |
| `data[].content.focused` | `boolean \| null` | Yes | Whether this frame's app was focused |
| `data[].content.device_name` | `string` | Yes | Defaults to `"monitor_0"` |
| `data[].content.tags` | `string[]` | Yes | Reserved for future use — currently always `[]` |
| `data[].content.fts_rank` | `number \| null` | No | BM25 rank score when text query present. `null` for metadata-only queries. |
| `pagination` | `object` | Yes | Pagination info |
| `pagination.limit` | `int` | Yes | Requested page size |
| `pagination.offset` | `int` | Yes | Current offset |
| `pagination.total` | `int` | Yes | Total matching results |

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `q` | `string` | — | Text search query (FTS5) |
| `content_type` | `string` | `"all"` | Filter by text source: `"ocr"` \| `"accessibility"` \| `"all"`. **Deprecated** — ignored after FTS unification (migration 20260325120000). |
| `limit` | `int` | `20` | Max results per page (max 100) |
| `offset` | `int` | `0` | Pagination offset |
| `start_time` | `string` | — | ISO8601 start of time range |
| `end_time` | `string` | — | ISO8601 end of time range |
| `app_name` | `string` | — | Filter by app name |
| `window_name` | `string` | — | Filter by window name |
| `browser_url` | `string` | — | Filter by browser URL |
| `focused` | `boolean` | — | Filter by focus state |
| `min_length` | `int` | — | Minimum text length |
| `max_length` | `int` | — | Maximum text length |

### Example Response

```json
// GET /v1/search?q=claude+code&limit=2

{
  "data": [
    {
      "type": "Accessibility",
      "content": {
        "frame_id": 42,
        "text": "MyRecall v3 Chat API MyRecall Search Claude Code Today 14:32",
        "text_source": "accessibility",
        "timestamp": "2026-03-26T14:32:05Z",
        "file_path": "2026-03-26T14:32:05Z.jpg",
        "frame_url": "/v1/frames/42",
        "app_name": "Claude Code",
        "window_name": "Claude Code — ~/chat/MyRecall",
        "browser_url": null,
        "focused": true,
        "device_name": "monitor_0",
        "tags": [],
        "fts_rank": 0.82
      }
    },
    {
      "type": "OCR",
      "content": {
        "frame_id": 41,
        "text": "claude code --model opus thinking idle 30",
        "text_source": "ocr",
        "timestamp": "2026-03-26T14:31:05Z",
        "file_path": "2026-03-26T14:31:05Z.jpg",
        "frame_url": "/v1/frames/41",
        "app_name": "Terminal",
        "window_name": "zsh — 120×40",
        "browser_url": null,
        "focused": false,
        "device_name": "monitor_0",
        "tags": [],
        "fts_rank": 0.65
      }
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
// GET /v1/search?app_name=Chrome&start_time=2026-03-26T00:00:00Z&end_time=2026-03-26T23:59:59Z&limit=1
// (no text query — returns metadata-only results, no fts_rank)

{
  "data": [
    {
      "type": "Accessibility",
      "content": {
        "frame_id": 99,
        "text": "GitHub Dashboard Pull requests Issues Actions MyRecall openrecall MyRecall",
        "text_source": "accessibility",
        "timestamp": "2026-03-26T10:15:33Z",
        "file_path": "2026-03-26T10:15:33Z.jpg",
        "frame_url": "/v1/frames/99",
        "app_name": "Chrome",
        "window_name": "GitHub — MyRecall — openrecall — Dashboard",
        "browser_url": "https://github.com/pyw/openrecall",
        "focused": true,
        "device_name": "monitor_0",
        "tags": [],
        "fts_rank": null
      }
    }
  ],
  "pagination": {
    "limit": 1,
    "offset": 0,
    "total": 5
  }
}
```

### Field Naming Inconsistency

> **⚠️ Naming mismatch:** `/v1/search` uses `type: "OCR"|"Accessibility"` (capitalized, in `data[].type`) while `/v1/frames/{id}/context` uses `text_source: "ocr"|"accessibility"` (lowercase). This inconsistency should be resolved.

### Known Gaps (vs screenpipe)

- ❌ `tags` — reserved but always empty (`[]`)
- ❌ `frame_url` exists but no direct inline image URL (`frame` field in screenpipe)

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

### Known Naming Inconsistencies to Resolve

| Issue | Location | Should Be |
|-------|----------|-----------|
| `type` vs `text_source` | search returns `data[].type`, context returns `text_source` | Normalize to one format |
| Capitalization | search uses `"OCR"`/`"Accessibility"`, context uses `"ocr"`/`"accessibility"` | Pick one convention (recommend lowercase) |
| `minutes` field meaning | activity-summary: estimated; search: no equivalent | N/A — different endpoints |

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
