---
name: myrecall-search
description: Query the user's screen history via MyRecall API at http://localhost:8083. Use when the user asks about their recent screen activity, what they were doing, which apps they used, or what they saw on screen.
---

# MyRecall API

Local REST API at `http://localhost:8083`. Base URL for all endpoints below.

> **IMPORTANT — Port**: MyRecall runs on port **8083**, not 3030 (screenpipe uses 3030).

> **Timezone**: The user's local timezone context is injected at the start of every message.
> All timestamps are in **local time (UTC+8)**. Use local time directly in all API calls.
>
> **Injected context format** (appears at the top of every message):
> ```
> Date: 2026-04-26
> Local time now: 2026-04-26T16:30:00
> ```
> Use `Date` and `Local time now` directly from the injected header.

---

## Time Formatting Strategy

All timestamps are in **local time (UTC+8)**. The injected header shows the current local time.
Use local time directly in all API calls — no conversion needed.

| Expression | Meaning | How to compute |
|------------|---------|----------------|
| `today` | Since midnight local time | `Date` from header + `T00:00:00` |
| `yesterday` | Yesterday's full day | `Date` from header, minus 1 day |
| `recent` | Last 30 minutes | `Local time now` - 30 minutes |
| `1h ago` | One hour ago | `Local time now` - 1 hour |
| `2d ago` | Two days ago | `Local time now` - 2 days |
| `now` | Current moment | `Local time now` from header |

**Example — user asks "what was I doing today?":**
```bash
# Injected header:
#   Date: 2026-04-26
#   Local time now: 2026-04-26T16:30:00
#
START="2026-04-26T00:00:00"
END="2026-04-26T16:30:00"
curl "http://localhost:8083/v1/activity-summary?start_time=${START}&end_time=${END}"
```

---

## Context Window Protection

API responses can be large. Always write curl output to a file first, check size, and
truncate if needed before including in conversation context.

```bash
curl "..." -o /tmp/myrecall_result.json
wc -c /tmp/myrecall_result.json   # Check size
head -c 5120 /tmp/myrecall_result.json   # Truncate to ~5KB if too large
```

**Rules:**
- `activity-summary`: Compact overview. The `apps` array and a few `descriptions` entries are typically sufficient. Use `max_descriptions` to control size.
- `search`: Use `limit=5` initially, expand if needed. Each result is ~500-2000 tokens.
- `frame context`: Text is middle-truncated at 5000 characters. Use for specific frame details.
- `frame image`: Never include raw image data in context. Describe what you see verbally.

---

## 1. Activity Summary — `GET /v1/activity-summary`

**Purpose**: Broad overview of screen activity. Best starting point for almost every question.

```bash
# Use local time directly from the injected header
# Date: 2026-04-26
# Local time now: 2026-04-26T16:30:00
START="2026-04-26T00:00:00"
END="2026-04-26T16:30:00"
curl "http://localhost:8083/v1/activity-summary?start_time=${START}&end_time=${END}"
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_time` | ISO 8601 local | **Yes** | Start of time range (e.g. `2026-04-26T00:00:00`) |
| `end_time` | ISO 8601 local | **Yes** | End of time range (e.g. `2026-04-26T16:30:00`) |
| `app_name` | string | No | Filter by specific app name |
| `max_descriptions` | integer | No | Max AI frame descriptions to return. No default — all available descriptions returned if unspecified. Max 1000. |

### Response Format

```json
{
  "apps": [
    {"name": "Safari", "frame_count": 10, "minutes": 0.33, "first_seen": "2026-04-26T10:00:00", "last_seen": "2026-04-26T10:05:00"},
    {"name": "VSCode", "frame_count": 5, "minutes": 0.17, "first_seen": "2026-04-26T09:30:00", "last_seen": "2026-04-26T10:02:00"}
  ],
  "audio_summary": {"segment_count": 0, "speakers": []},
  "total_frames": 15,
  "time_range": {"start": "2026-04-26T00:00:00", "end": "2026-04-26T16:30:00"},
  "descriptions": [
    {"frame_id": 42, "timestamp": "2026-04-26T10:00:00", "summary": "GitHub PR review", "tags": ["code_review", "github", "pr_123"]}
  ]
}
```

### Key Fields

| Field | Description |
|-------|-------------|
| `apps` | List of apps used in the time range, ordered by `minutes` descending. Includes `frame_count`, accurate `minutes` (from timestamp gaps), `first_seen`, and `last_seen`. |
| `descriptions` | AI-generated frame descriptions (`summary`, `tags`, `timestamp`). Use `GET /v1/frames/{id}/context` for full `narrative`. |
| `total_frames` | Total completed screenshots in the time range |
| `audio_summary` | Currently empty (`segment_count: 0`). Audio is not yet supported. |

### When to Use

- **"What was I doing today/yesterday/recently?"** → Step 1 only
- **"Which apps did I use?"** → Step 1 (`apps` array)
- **"Give me a summary of my activity"** → Step 1 only

---

## 2. Search — `GET /v1/search`

**Purpose**: Full-text and semantic search across all captured screen content. Default mode is `hybrid` (combines FTS + vector search).

```bash
# Search for "GitHub PR" in the last 2 hours (default: hybrid mode)
# Use local time directly from the injected header
START="2026-04-26T14:30:00"
END="2026-04-26T16:30:00"
curl "http://localhost:8083/v1/search?q=GitHub+PR&start_time=${START}&end_time=${END}&limit=10"

# FTS-only search (faster, keyword-based)
curl "http://localhost:8083/v1/search?q=GitHub+PR&mode=fts&start_time=${START}&end_time=${END}&limit=10"

# Vector-only search (semantic similarity)
curl "http://localhost:8083/v1/search?q=GitHub+PR&mode=vector&start_time=${START}&end_time=${END}&limit=10"
```

### ⚠️  `content_type` Parameter is Deprecated

> **IMPORTANT**: The `content_type` parameter (`ocr`, `accessibility`, `all`) is **deprecated**.
> Behavior is inconsistent — it is ignored in most cases but may log warnings. Do NOT use this
> parameter to filter results; it has no reliable effect.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `q` | string | No | Search query. Matched against all screen text. Empty query returns browse mode. |
| `mode` | string | No | Search mode: `fts`, `vector`, `hybrid` (default: `hybrid`) |
| `limit` | integer | No | Max results (default: 20, no max limit) |
| `offset` | integer | No | Pagination offset (default: 0) |
| `start_time` | ISO 8601 local | Recommended | Start of time range (local time, e.g. `2026-04-26T08:00:00`) |
| `end_time` | ISO 8601 local | Recommended | End of time range (local time, e.g. `2026-04-26T23:59:59`) |
| `app_name` | string | No | Filter by exact app name |
| `window_name` | string | No | Filter by window title |
| `browser_url` | string | No | Filter by browser URL substring |
| `focused` | boolean | No | Only focused windows (`true`/`false`) |
| `include_text` | boolean | No | Include `text` field in response (default: `false`) |
| `max_text_length` | integer | No | Max characters for `text` field with middle-truncation (default: 200) |

> **`include_text`**: When `include_text=true`, text is truncated to `max_text_length` (default 200) in all modes.

> **Always include `start_time` and `end_time`**. Unbounded searches will return excessive results and may be slow.

### Response Format

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

### Response Fields

| Field | Description |
|-------|-------------|
| `frame_id` | Unique frame ID — use with `/frames/{id}/context` for details |
| `timestamp` | ISO8601 local capture time |
| `text_source` | `accessibility` (from AX tree), `ocr` (OCR fallback), or `hybrid` (both sources merged) |
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
| `fts_rank` | Position in FTS results (hybrid mode only) |
| `cosine_score` | Vector cosine similarity 0-1, higher = more similar (vector/hybrid modes) |
| `hybrid_rank` | Final RRF fused rank (hybrid mode only) |
| `vector_rank` | Position in vector results (hybrid mode only) |

### Score Fields by Mode

| Mode | Score Fields Returned |
|------|----------------------|
| `fts` | `score`, `fts_score` |
| `vector` | `score`, `cosine_score` |
| `hybrid` | `score`, `fts_score`, `fts_rank`, `cosine_score`, `hybrid_rank`, `vector_rank` |

### When to Use

- **"Did I see anything about X?"** → Step 2
- **"Find frames with text Y"** → Step 2
- **"What did I see in Chrome/Safari/VSCode?"** → Step 2 with `app_name` filter

### Progressive Disclosure — When NOT to Use Search

Do not use `/search` as the first step for broad questions. Use `/activity-summary` first.

| Wrong approach | Right approach |
|----------------|---------------|
| "What was I doing?" → search for "doing" | "What was I doing?" → `/activity-summary` |
| "Which apps?" → search for app names | "Which apps?" → `/activity-summary` |
| "Summarize my day" → paginate through 100 search results | "Summarize my day" → `/activity-summary` |

---

## 3. Frame Context — `GET /v1/frames/{id}/context`

**Purpose**: Detailed information about a specific frame. Returns text, browser URLs,
and AI-generated description.

```bash
curl "http://localhost:8083/v1/frames/42/context"
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `frame_id` | integer | **Yes** (path) | The frame ID from search results |

> **Note**: This endpoint accepts no query parameters. Text is always truncated at 5000 characters.

### Error Responses

| Status | Condition |
|--------|-----------|
| `404 NOT_READY` | Frame exists but `visibility_status` is not `queryable` (still processing or failed) |

### Response Format

```json
{
  "frame_id": 42,
  "timestamp": "2026-04-26T10:30:00",
  "app_name": "Claude Code",
  "window_name": "Claude Code — ~/chat/MyRecall",
  "description": {
    "narrative": "The user is reviewing pull request #123 on GitHub...",
    "summary": "GitHub PR review",
    "tags": ["code_review", "github"]
  },
  "text": "Reviewing pull request #123 in the GitHub web interface...",
  "text_source": "accessibility",
  "urls": ["https://github.com/pulls/123"],
  "browser_url": "https://github.com/",
  "status": "completed",
  "description_status": "completed"
}
```

> **Note**: The response always includes `description` (null if not generated), `text` (middle-truncated at 5000 chars), and `urls` extracted via regex. No query parameters are accepted.

### Key Fields

| Field | Description |
|-------|-------------|
| `timestamp` | ISO8601 local capture time of the frame |
| `app_name` | Application name at capture time (e.g. "Claude Code", "Chrome") |
| `window_name` | Window title at capture time |
| `description` | **MyRecall unique feature**. AI-generated description with `narrative`, `summary`, and `tags`. Returns `null` if not yet generated. |
| `text` | Full text captured from the frame (middle-truncated at 5000 chars) |
| `text_source` | `accessibility` (preferred), `ocr` (fallback), or `hybrid` (both merged) |
| `urls` | Extracted URLs from text via regex |
| `browser_url` | Browser URL at capture time |
| `status` | Frame processing status (`completed`, `pending`, etc.) |
| `description_status` | AI description generation status (`completed`, `pending`, `failed`, or `null` if not yet queued) |

> **Tip**: The `description.narrative` field is the most useful for answering
> "what was I doing in this frame?" questions. If `description` is `null`, the AI
> description has not been generated yet — use the raw `text` field instead.

### When to Use

- **"What was I doing in this specific frame?"** → Step 3 (check `description.narrative`)
- **"What URLs were open?"** → Step 3 (check `urls` array)
- **"Show me the full text of frame 42"** → Step 3 (note: text is middle-truncated at 5000 chars)

---

## 4. Frame Image — `GET /v1/frames/{id}`

**Purpose**: Retrieve the actual screenshot (JPEG) for a frame. Use sparingly — screenshots
are ~100-200 KB each and should not be included in context.

```bash
curl -o /tmp/frame.jpg "http://localhost:8083/v1/frames/42"
```

> Returns `image/jpeg`. **Never include image data in your response to the user.**
> Only describe what you observe verbally.

### When to Use

- **"What did the screenshot actually look like?"** → Rarely needed. Usually `description.narrative`
  from Step 3 is sufficient.

---

## Agent Policy — Progressive Disclosure

Use a **4-step escalation strategy**. Never jump to the heavy tools first.

### Step Decision Tree

```
User asks a question
│
├─► "What was I doing?" / "Summarize my activity"
│    → Step 1: /activity-summary
│
├─► "Did I see X?" / "Find frames about Y"
│    → Step 2: /search
│    → If results found → Step 3 for frame details
│
├─► "What was I doing in this specific frame?"
│    → Step 3: /frames/{id}/context
│    → Check description.narrative first, fall back to text if null
│
├─► "Show me the screenshot"
│    → Step 4: /frames/{id} (JPEG) — describe verbally only
│
└─► "How much time did I spend on X?" / "App usage stats"
     → Step 1: /activity-summary (apps array has frame_count + minutes)
```

### Common Scenario Mappings

| User Question | Tools to Use | Notes |
|---------------|-------------|-------|
| "What was I doing today?" | `/activity-summary` | Use `descriptions` for narratives |
| "Which apps did I use?" | `/activity-summary` | Check `apps` array |
| "Did I open GitHub today?" | `/activity-summary` + `/search` | Step 1 first, then Step 2 with `app_name` |
| "Find all frames with my password" | `/search` with `q=password` | Be careful about logging/securing password-related frames |
| "What did the screenshot show?" | `/frames/{id}/context` | Check `description.narrative` or `text` |
| "Show me a screenshot" | `/frames/{id}` | Describe verbally, don't include image data |
| "How long on Safari?" | `/activity-summary` | Check `apps` for Safari's `minutes` field |
| "What did I code in VSCode?" | `/search` with `app_name` | Use `window_name` for specific files |

### Critical Rules

1. **Always include `start_time` and `end_time`** in search requests — unbounded searches time out
2. **Start with narrow time ranges** (1-2 hours), expand only if no results
3. **Use `app_name` filter** when the user mentions a specific app
4. **Keep `limit` low** (5-10) initially — expand if needed
5. **`text_source` tells you quality**: `accessibility` > `ocr`. If results seem poor, they may be from OCR fallback
6. **`description.narrative` is the gold standard** for understanding activity — use it first, fall back to `text` if `description` is null
7. **Do NOT use `content_type` parameter** — it is deprecated and has inconsistent behavior
8. **Max 2-3 frames per response** — don't overwhelm the context with many frame details
9. **Frame context text is middle-truncated at 5000 chars** — long content will be truncated with "...N chars..." in the middle
10. **Use `include_text=true`** only when you need the frame text — default is `false` to reduce response size
11. **Default mode is `hybrid`** — combines FTS and vector search for best results

---

## Response Quality Guide

| Quality Issue | Likely Cause | Fix |
|---------------|-------------|-----|
| No search results | Query too specific | Try broader terms, check spelling |
| `text_source=ocr` everywhere | App lacks accessibility support (games, remote desktop, etc.) | Normal for some apps — use raw text |
| `description` is null | AI description not yet generated | Use raw `text` instead |
| `audio_summary` is always empty | Audio not yet supported | Do not query or mention audio features |

---

## Out of Scope (Do NOT use)

These screenpipe endpoints do **not exist** in MyRecall:

| Screenpipe Endpoint | MyRecall Equivalent | Notes |
|---------------------|---------------------|-------|
| `GET /elements` | None | Not implemented |
| `POST /audio/retranscribe` | None | Audio not supported |
| `GET /meetings` | None | Not implemented |
| `POST /frames/export` | None | Not implemented |
| `POST /raw_sql` | None | Not exposed to agents |
| `screenpipe://` deeplinks | None | Not supported |
| `content_type=memory\|audio\|input` | `content_type` is deprecated | Ignored — always returns merged results |
| `min_length` / `max_length` params | None | Removed — filter via query instead |
| `/frames/{id}/context?include_nodes=true` | `/frames/{id}/context` | Query parameters not supported — simplified API always returns the same structure |
