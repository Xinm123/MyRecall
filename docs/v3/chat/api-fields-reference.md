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
| `text` | `string \| null` | Yes | `accessibility_text` if AX-first succeeded, else `ocr_text`, truncated by `max_text_length` if specified |
| `text_source` | `string` | Yes | `"accessibility"` \| `"ocr"` \| `"hybrid"` (lowercase) |
| `urls` | `string[]` | Yes | Extracted URLs from AX link nodes + regex fallback on text. Deduplicated. |
| `browser_url` | `string \| null` | Yes | `browser_url` field from frames table |
| `status` | `string` | Yes | `processing_status` from frames table: `"pending"` \| `"processing"` \| `"completed"` \| `"failed"` |
| `nodes` | `object[]` | No | Parsed accessibility tree nodes. **Only included when `include_nodes=true`** |
| `nodes_truncated` | `int \| null` | No | Number of nodes skipped due to `max_nodes` limit. Only present when limit was exceeded. |
| `description_status` | `string \| null` | Yes | Status of AI description task: `"pending"` \| `"processing"` \| `"completed"` \| `"failed"` \| `null` (no description requested) |
| `description` | `object \| null` | No | AI-generated frame description. **Only present when `description_status == "completed"`** |

### Nodes Array (when `include_nodes=true`)

Each node object:

| Field | Type | Always Present | Description |
|-------|------|:--------------:|-------------|
| `role` | `string` | Yes | AX role (e.g., `"AXStaticText"`, `"AXButton"`, `"AXLink"`) |
| `text` | `string` | Yes | Text content of the node |
| `depth` | `int` | Yes | Depth in accessibility tree (0 = root) |
| `bounds` | `object \| null` | No | Bounding box relative to monitor |
| `bounds.left` | `number` | — | Left coordinate (pixels) |
| `bounds.top` | `number` | — | Top coordinate (pixels) |
| `bounds.width` | `number` | — | Width (pixels) |
| `bounds.height` | `number` | — | Height (pixels) |
| `properties` | `object \| null` | **No** | AX properties (automation_id, class_name, value, help_text, url, placeholder, role_description, subrole, is_enabled, is_focused, is_selected, is_expanded, is_password, is_keyboard_focusable, accelerator_key, access_key). **Currently not populated in MyRecall** — reserved for future. This field is **never included** in the response (not even as `null`). |

### Description Object (when `description_status == "completed"`)

| Field | Type | Always Present | Description |
|-------|------|:--------------:|-------------|
| `narrative` | `string` | Yes | AI-generated description of what the frame shows |
| `entities` | `string[]` | Yes | Extracted named entities (empty array if none) |
| `intent` | `string` | Yes | Detected user intent |
| `summary` | `string` | Yes | Short one-line summary |

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `include_nodes` | `boolean` | `false` | Whether to include parsed accessibility tree nodes |
| `max_text_length` | `int` | — | Truncate `text` field to this max length |
| `max_nodes` | `int` | — | Limit number of nodes returned (when `include_nodes=true`) |

### Example Response

```json
// GET /v1/frames/42/context
// (include_nodes=false, description_status="completed")

{
  "frame_id": 42,
  "text": "MyRecall v3 Chat API MyRecall Search Claude Code Today 14:32",
  "text_source": "accessibility",
  "urls": [
    "https://github.com/anthropics/claude-code"
  ],
  "browser_url": null,
  "status": "completed",
  "description_status": "completed",
  "description": {
    "narrative": "The user is working on MyRecall v3 chat functionality in Claude Code, reviewing the API fields reference documentation.",
    "entities": ["MyRecall v3", "Claude Code", "API"],
    "intent": "coding",
    "summary": "Working on API documentation in Claude Code"
  }
}
```

```json
// GET /v1/frames/42/context?include_nodes=true&max_nodes=5
// (with accessibility tree nodes, truncated)

{
  "frame_id": 42,
  "text": "MyRecall v3 Chat API MyRecall Search Claude Code Today 14:32",
  "text_source": "accessibility",
  "urls": [],
  "browser_url": "https://github.com/pyw/myrecall",
  "status": "completed",
  "nodes_truncated": 23,
  "description_status": "completed",
  "description": {
    "narrative": "...",
    "entities": ["MyRecall v3"],
    "intent": "coding",
    "summary": "..."
  },
  "nodes": [
    {
      "role": "AXWindow",
      "text": "Claude Code — ~/chat/MyRecall",
      "depth": 0,
      "bounds": { "left": 0, "top": 25, "width": 3024, "height": 1961 }
    },
    {
      "role": "AXStaticText",
      "text": "MyRecall v3 Chat API",
      "depth": 1,
      "bounds": { "left": 24, "top": 80, "width": 200, "height": 22 }
    },
    {
      "role": "AXButton",
      "text": "Search",
      "depth": 2,
      "bounds": { "left": 280, "top": 80, "width": 60, "height": 28 }
    },
    {
      "role": "AXLink",
      "text": "https://github.com/pyw/myrecall",
      "depth": 2,
      "bounds": { "left": 24, "top": 120, "width": 180, "height": 16 }
    },
    {
      "role": "AXStaticText",
      "text": "Claude Code — ~/chat/MyRecall",
      "depth": 1,
      "bounds": null
    }
  ]
}
```

### Known Gaps (vs screenpipe)

- ❌ `app_name` — not returned (present in DB but omitted from response)
- ❌ `window_name` — not returned (present in DB but omitted from response)
- ❌ `timestamp` — not returned (present in DB but omitted from response)
- ❌ `device_name` / `monitor_index` — not returned
- ❌ `capture_trigger` — not returned
- ❌ `nodes[].properties` — schema defined but not populated; field is **never present** in response (not even as `null`)

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

**Purpose:** Lightweight compressed activity overview for a time range (~200-500 tokens). Returns app usage, recent accessibility texts, and audio summary.

**Returns:** `application/json`

### Response Fields

| Field | Type | Always Present | Description |
|-------|------|:--------------:|-------------|
| `apps` | `object[]` | Yes | App usage statistics |
| `apps[].name` | `string` | Yes | Application name (`app_name`). Falls back to `"Unknown"` when `app_name` is NULL in DB. |
| `apps[].frame_count` | `int` | Yes | Number of frames captured for this app in the time range |
| `apps[].minutes` | `number` | Yes | Approximate usage in minutes. Calculated as `frame_count * 2 / 60`, rounded to 2 decimal places. |
| `total_frames` | `int` | Yes | Total frames in the time range |
| `time_range` | `object` | Yes | Requested time range |
| `time_range.start` | `string` | Yes | ISO8601 start time |
| `time_range.end` | `string` | Yes | ISO8601 end time |
| `recent_texts` | `object[]` | Yes | Recent accessibility texts (up to 10) |
| `recent_texts[].frame_id` | `int` | Yes | Frame identifier |
| `recent_texts[].text` | `string` | Yes | Text content from `AXStaticText` role elements |
| `recent_texts[].role` | `string` | Yes | Element role — currently only `"AXStaticText"` in MVP |
| `recent_texts[].app_name` | `string` | Yes | App name for the frame |
| `recent_texts[].timestamp` | `string` | Yes | ISO8601 timestamp |
| `audio_summary` | `object` | Yes | Audio transcription summary. **Currently empty shell in vision-only MVP.** |
| `audio_summary.segment_count` | `int` | Yes | Always `0` in MVP |
| `audio_summary.speakers` | `object[]` | Yes | Always `[]` in MVP |
| `descriptions` | `object[]` | Yes | AI-generated frame descriptions. Returns up to `max_descriptions` entries, sorted by frame timestamp descending. Returns `[]` when no frames in the time range have completed descriptions. |
| `descriptions[].frame_id` | `int` | Yes | Frame identifier |
| `descriptions[].narrative` | `string` | Yes | AI-generated narrative |
| `descriptions[].entities` | `string[]` | Yes | Extracted entities |
| `descriptions[].intent` | `string` | Yes | Detected intent |
| `descriptions[].summary` | `string` | Yes | Short summary |

### Query Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `start_time` | `string` | — | **Required.** ISO8601 start of time range |
| `end_time` | `string` | — | **Required.** ISO8601 end of time range |
| `app_name` | `string` | — | Optional app filter — returns only this app's stats |
| `max_descriptions` | `int` | `20` | Maximum number of `descriptions` entries to return. `recent_texts` is capped at a separate fixed limit (10 entries). Max 100. |

### Example Response

```json
// GET /v1/activity-summary?start_time=2026-03-26T09:00:00Z&end_time=2026-03-26T18:00:00Z&max_descriptions=3

{
  "apps": [
    {
      "name": "Claude Code",
      "frame_count": 180,
      "minutes": 6.0
    },
    {
      "name": "Chrome",
      "frame_count": 120,
      "minutes": 4.0
    },
    {
      "name": "Terminal",
      "frame_count": 60,
      "minutes": 2.0
    }
  ],
  "total_frames": 360,
  "time_range": {
    "start": "2026-03-26T09:00:00Z",
    "end": "2026-03-26T18:00:00Z"
  },
  "recent_texts": [
    {
      "frame_id": 108,
      "text": "docs/v3/chat/api-fields-reference.md",
      "role": "AXStaticText",
      "app_name": "Claude Code",
      "timestamp": "2026-03-26T17:58:05Z"
    },
    {
      "frame_id": 107,
      "text": "API Response Fields Reference",
      "role": "AXStaticText",
      "app_name": "Claude Code",
      "timestamp": "2026-03-26T17:55:22Z"
    },
    {
      "frame_id": 105,
      "text": "MyRecall openrecall MyRecall v3",
      "role": "AXStaticText",
      "app_name": "Chrome",
      "timestamp": "2026-03-26T17:50:11Z"
    }
  ],
  "audio_summary": {
    "segment_count": 0,
    "speakers": []
  },
  "descriptions": [
    {
      "frame_id": 108,
      "narrative": "The user is editing the API fields reference document in Claude Code, adding JSON examples for the activity-summary endpoint.",
      "entities": ["Claude Code", "API", "activity-summary"],
      "intent": "writing documentation",
      "summary": "Editing API reference docs"
    },
    {
      "frame_id": 95,
      "narrative": "GitHub repository page for openrecall/MyRecall project showing README and recent commits.",
      "entities": ["GitHub", "openrecall", "MyRecall"],
      "intent": "browsing",
      "summary": "Viewing GitHub repo README"
    },
    {
      "frame_id": 88,
      "narrative": "Terminal window running pytest with all tests passing.",
      "entities": ["pytest", "terminal"],
      "intent": "running tests",
      "summary": "Running test suite"
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
      "minutes": 4.0
    }
  ],
  "total_frames": 120,
  "time_range": {
    "start": "2026-03-26T09:00:00Z",
    "end": "2026-03-26T18:00:00Z"
  },
  "recent_texts": [
    {
      "frame_id": 105,
      "text": "MyRecall openrecall MyRecall v3",
      "role": "AXStaticText",
      "app_name": "Chrome",
      "timestamp": "2026-03-26T17:50:11Z"
    }
  ],
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
| `first_seen`/`last_seen` per app | ✅ `AppUsage` includes both | ❌ Missing | AI cannot determine app usage duration |
| `minutes` calculation | Uses frame-gap time delta | Uses `frame_count * 2 / 60` | Inaccurate for sparse/spammy captures |
| `window_name` per app | ❌ Not included | ❌ Not included | Same gap |
| `recent_texts` roles | `'AXStaticText', 'line', 'paragraph', 'block'` | `'AXStaticText'` only | OCR text elements not included |
| `focused` flag | ❌ Not included | ❌ Not included | Limited |
| `description` field in recent_texts | ✅ Includes full text | ❌ Not included | Less context for AI |

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
