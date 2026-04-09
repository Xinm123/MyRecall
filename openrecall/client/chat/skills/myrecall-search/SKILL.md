---
name: myrecall-search
description: Query the user's screen history via MyRecall API at http://localhost:8083. Use when the user asks about their recent screen activity, what they were doing, which apps they used, or what they saw on screen.
---

# MyRecall API

Local REST API at `http://localhost:8083`. Base URL for all endpoints below.

> **IMPORTANT — Port**: MyRecall runs on port **8083**, not 3030 (screenpipe uses 3030).

> **Timezone**: The user's local timezone context is injected at the start of every message.
> Use the values from that header to convert local time expressions to UTC.
>
> **Injected context format** (appears at the top of every message):
> ```
> Date: 2026-04-02
> Timezone: CST (UTC+08:00)
> Local midnight today (UTC): 2026-04-01T16:00:00Z
> Local midnight yesterday (UTC): 2026-03-31T16:00:00Z
> Now (UTC): 2026-04-02T08:30:00Z
> ```
> Extract `Local midnight today (UTC)`, `Local midnight yesterday (UTC)`, and `Now (UTC)`
> directly from the injected header — do not compute them yourself.

---

## Time Formatting Strategy

Use the timezone context injected at the start of each message to convert local time
expressions to UTC before calling the API.

| Expression | Meaning | How to compute |
|------------|---------|----------------|
| `today` | Since midnight LOCAL time | Use `Local midnight today (UTC)` from context above |
| `yesterday` | Yesterday's LOCAL full day | `Local midnight yesterday (UTC)` to `Local midnight today (UTC) - 1s` |
| `recent` | Last 30 minutes | Current UTC time - 30 minutes |
| `1h ago` | One hour ago | Current UTC time - 1 hour |
| `2d ago` | Two days ago | Current UTC time - 2 days |
| `now` | Current moment | Use `Now (UTC)` from context above |

**Conversion workflow:**
1. Parse the user's time expression
2. Run `date -u +%Y-%m-%dT%H:%M:%SZ -d "<relative expression>"` to get start_time
3. Run `date -u +%Y-%m-%dT%H:%M:%SZ` for end_time (usually `now`)
4. Pass both as `start_time` and `end_time` query parameters

**Example — user asks "what was I doing today?":**
```bash
# The injected header contains:
#   Local midnight today (UTC): 2026-04-01T16:00:00Z
#   Local midnight yesterday (UTC): 2026-03-31T16:00:00Z
#   Now (UTC): 2026-04-02T08:30:00Z
# Extract these values from the injected header above — do not compute.
START="$LOCAL_MIDNIGHT_TODAY_UTC"   # from injected header
END="$NOW_UTC"                       # from injected header
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
- `frame context`: Text is capped at 5000 characters. Use for specific frame details.
- `frame image`: Never include raw image data in context. Describe what you see verbally.

---

## 1. Activity Summary — `GET /v1/activity-summary`

**Purpose**: Broad overview of screen activity. Best starting point for almost every question.

```bash
START=$(date -u +%Y-%m-%dT00:00:00Z)   # today midnight
END=$(date -u +%Y-%m-%dT%H:%M:%SZ)      # now
curl "http://localhost:8083/v1/activity-summary?start_time=${START}&end_time=${END}"
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_time` | ISO 8601 | **Yes** | Start of time range (e.g. `2026-03-25T00:00:00Z`) |
| `end_time` | ISO 8601 | **Yes** | End of time range (e.g. `2026-03-25T12:00:00Z`) |
| `app_name` | string | No | Filter by specific app name |
| `max_descriptions` | integer | No | Max AI frame descriptions to return. No default — all available descriptions returned if unspecified. Max 1000. |

### Response Format

```json
{
  "apps": [
    {"name": "Safari", "frame_count": 10, "minutes": 0.33, "first_seen": "2026-03-25T10:00:00Z", "last_seen": "2026-03-25T10:05:00Z"},
    {"name": "VSCode", "frame_count": 5, "minutes": 0.17, "first_seen": "2026-03-25T09:30:00Z", "last_seen": "2026-03-25T10:02:00Z"}
  ],
  "audio_summary": {"segment_count": 0, "speakers": []},
  "total_frames": 15,
  "time_range": {"start": "2026-03-25T00:00:00Z", "end": "2026-03-25T12:00:00Z"},
  "descriptions": [
    {"frame_id": 42, "timestamp": "2026-03-25T10:00:00Z", "summary": "GitHub PR review", "tags": ["code_review", "github", "pr_123"]}
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

**Purpose**: Full-text search across all captured screen content.

```bash
# Search for "GitHub PR" in the last 2 hours
START=$(date -u +%Y-%m-%dT%H:%M:%SZ -d "2 hours ago")
END=$(date -u +%Y-%m-%dT%H:%M:%SZ)
curl "http://localhost:8083/v1/search?q=GitHub+PR&start_time=${START}&end_time=${END}&limit=10"
```

### ⚠️  `content_type` Parameter is Deprecated

> The `content_type` parameter (`ocr`, `accessibility`, `all`) is **deprecated** in MyRecall.
> It is ignored by the API — all searches return merged results from both OCR and
> accessibility text. Do NOT use this parameter to filter results; it has no effect.

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `q` | string | **Yes** | Search query. Matched against all screen text. |
| `limit` | integer | No | Max results (default: 20, max: 100) |
| `offset` | integer | No | Pagination offset (default: 0) |
| `start_time` | ISO 8601 | **Yes** | Start of time range |
| `end_time` | ISO 8601 | **Yes** | End of time range |
| `app_name` | string | No | Filter by exact app name |
| `window_name` | string | No | Filter by window title |
| `browser_url` | string | No | Filter by browser URL substring |
| `focused` | boolean | No | Only focused windows (`true`/`false`) |
| `min_length` | integer | No | Minimum text length |
| `max_length` | integer | No | Maximum text length |

> **Always include `start_time` and `end_time`**. Unbounded searches will return
> excessive results and may be slow.

### Response Format

```json
{
  "data": [
    {
      "type": "OCR",
      "content": {
        "frame_id": 42,
        "timestamp": "2026-03-25T10:30:00Z",
        "text": "Reviewing pull request #123...",
        "text_source": "accessibility",
        "app_name": "Safari",
        "window_name": "Pull Request #123 — GitHub",
        "browser_url": "https://github.com/...",
        "focused": true,
        "file_path": "/path/to/frame.jpg",
        "frame_url": "http://localhost:8083/v1/frames/42",
        "device_name": "monitor_0",
        "tags": [],
        "fts_rank": 0.123
      }
    },
    {
      "type": "Accessibility",
      "content": {
        "frame_id": 43,
        "timestamp": "2026-03-25T10:29:00Z",
        "text": "Click to merge",
        "text_source": "accessibility",
        "app_name": "Safari",
        "window_name": "Pull Request #123 — GitHub",
        "browser_url": "https://github.com/...",
        "focused": true,
        "file_path": "/path/to/frame43.jpg",
        "frame_url": "http://localhost:8083/v1/frames/43",
        "device_name": "monitor_0",
        "tags": [],
        "fts_rank": 0.456
      }
    }
  ],
  "pagination": {
    "limit": 20,
    "offset": 0,
    "total": 2
  }
}
```

### Content Fields

| Field | Description |
|-------|-------------|
| `type` | `"OCR"` or `"Accessibility"` — the text source of this result |
| `frame_id` | Unique frame ID — use with `/frames/{id}/context` for details |
| `text_source` | Either `accessibility` (from AX tree) or `ocr` (from OCR fallback) |
| `text` | Matched screen text |
| `fts_rank` | BM25 relevance score. Higher = more relevant. Useful for comparing result quality. |
| `browser_url` | Current browser URL at capture time (only for browser frames) |

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

**Purpose**: Detailed information about a specific frame. Returns text, UI structure,
browser URLs, and AI-generated description.

```bash
curl "http://localhost:8083/v1/frames/42/context"
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `frame_id` | integer | **Yes** (path) | The frame ID from search results |

> **Note**: This endpoint accepts no query parameters. Text is always truncated at 5000 characters.

### Response Format

```json
{
  "frame_id": 42,
  "timestamp": "2026-03-25T10:30:00Z",
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
  "status": "completed"
}
```

> **Note**: The response always includes `description` (null if not generated), `text` (capped at 5000 chars with "..." suffix if truncated), and `urls` extracted via regex. No query parameters are accepted.

### Key Fields

| Field | Description |
|-------|-------------|
| `timestamp` | ISO8601 UTC capture time of the frame |
| `app_name` | Application name at capture time (e.g. "Claude Code", "Chrome") |
| `window_name` | Window title at capture time |
| `description` | **MyRecall unique feature**. AI-generated description with `narrative`, `summary`, and `tags`. Returns `null` if not yet generated. |
| `text` | Full text captured from the frame (capped at 5000 chars) |
| `text_source` | `accessibility` (preferred) or `ocr` (fallback) |
| `urls` | Extracted URLs from text via regex |
| `browser_url` | Browser URL at capture time |
| `status` | Frame processing status (`completed`, `pending`, etc.) |

> **Tip**: The `description.narrative` field is the most useful for answering
> "what was I doing in this frame?" questions. If `description` is `null`, the AI
> description has not been generated yet — use the raw `text` field instead.

### When to Use

- **"What was I doing in this specific frame?"** → Step 3 (check `description.narrative`)
- **"What URLs were open?"** → Step 3 (check `urls` array)
- **"Show me the full text of frame 42"** → Step 3 (note: text is capped at 5000 chars)

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
- **"What UI elements were at what positions?"** → Rarely needed. The `nodes` array with
  `bounds` information provides spatial context.

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
7. **Do NOT use `content_type` parameter** — it is deprecated and ignored
8. **Max 2-3 frames per response** — don't overwhelm the context with many frame details
9. **Frame context text is capped at 5000 chars** — long content will be truncated with "..." suffix

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
| `/frames/{id}/context?include_nodes=true` | `/frames/{id}/context` | Query parameters not supported — simplified API always returns the same structure |
