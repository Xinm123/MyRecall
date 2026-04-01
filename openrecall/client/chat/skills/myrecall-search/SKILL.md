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
> Time range: 2026-04-01T16:00:00Z to 2026-04-02T15:59:59Z
> Date: 2026-04-02
> Timezone: CST (UTC+08:00)
> Local midnight today (UTC): 2026-04-01T16:00:00Z
> Local midnight yesterday (UTC): 2026-03-31T16:00:00Z
> ```
> Extract `Local midnight today (UTC)` and `Local midnight yesterday (UTC)` directly from
> the injected header — do not compute them yourself.

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
| `now` | Current moment | Current UTC time |

**Conversion workflow:**
1. Parse the user's time expression
2. Run `date -u +%Y-%m-%dT%H:%M:%SZ -d "<relative expression>"` to get start_time
3. Run `date -u +%Y-%m-%dT%H:%M:%SZ` for end_time (usually `now`)
4. Pass both as `start_time` and `end_time` query parameters

**Example — user asks "what was I doing today?":**
```bash
# The injected header (at top of message) contains:
#   Local midnight today (UTC): 2026-04-01T16:00:00Z
#   Local midnight yesterday (UTC): 2026-03-31T16:00:00Z
# Extract from the injected header above — do not compute.
START="2026-04-01T16:00:00Z"   # from injected header
END=$(date -u +%Y-%m-%dT%H:%M:%SZ)   # current UTC time
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
- `activity-summary`: ~200-500 tokens. Safe to include directly.
- `search`: Use `limit=5` initially, expand if needed. Each result is ~500-2000 tokens.
- `frame context`: The `nodes` array is only present when `include_nodes=true`. Use `max_nodes=20` if you only need top-level text.
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
| `max_descriptions` | integer | No | Max AI frame descriptions to return (default: 20, max: 100) |

### Response Format

```json
{
  "apps": [
    {"name": "Safari", "frame_count": 10, "minutes": 0.33},
    {"name": "VSCode", "frame_count": 5, "minutes": 0.17}
  ],
  "recent_texts": [
    {"frame_id": 1, "text": "Hello world", "role": "AXStaticText", "app_name": "Safari", "timestamp": "2026-03-25T10:00:00Z"}
  ],
  "audio_summary": {"segment_count": 0, "speakers": []},
  "total_frames": 15,
  "time_range": {"start": "2026-03-25T00:00:00Z", "end": "2026-03-25T12:00:00Z"},
  "descriptions": [
    {"frame_id": 42, "narrative": "User is reviewing a GitHub pull request...", "summary": "GitHub PR review", "entities": ["PR #123", "GitHub"], "intent": "code_review"}
  ]
}
```

### Key Fields

| Field | Description |
|-------|-------------|
| `apps` | List of apps used in the time range, with frame count and estimated active minutes |
| `recent_texts` | Recent screen texts captured. Each entry has `frame_id`, `text`, `role` (e.g. `AXStaticText`), `app_name`, `timestamp`. Deduplicated by text content. |
| `descriptions` | AI-generated frame descriptions (`narrative`, `entities`, `intent`, `summary`). Great for "what was I doing?" — check `description_status` first. |
| `total_frames` | Total screenshot count in the time range |
| `audio_summary` | Currently empty (`segment_count: 0`). Audio is not yet supported. |

### When to Use

- **"What was I doing today/yesterday/recently?"** → Step 1 only
- **"Which apps did I use?"** → Step 1 (`apps` array)
- **"What text did I see recently?"** → Step 1 (`recent_texts`)
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
# With nodes included (UI element tree):
curl "http://localhost:8083/v1/frames/42/context?include_nodes=true"
# With limits:
curl "http://localhost:8083/v1/frames/42/context?include_nodes=true&max_nodes=20&max_text_length=1000"
```

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `frame_id` | integer | **Yes** (path) | The frame ID from search results |
| `include_nodes` | boolean | No | Include parsed UI nodes from accessibility tree (default: **false** — omit for efficiency) |
| `max_text_length` | integer | No | Truncate `text` field to this length |
| `max_nodes` | integer | No | Limit number of nodes in the `nodes` array (only applies when `include_nodes=true`) |

### Response Format

**When `include_nodes=false` (default):**
```json
{
  "frame_id": 42,
  "timestamp": "2026-03-25T10:30:00Z",
  "app_name": "Claude Code",
  "window_name": "Claude Code — ~/chat/MyRecall",
  "text": "Reviewing pull request #123 in the GitHub web interface...",
  "text_source": "accessibility",
  "urls": ["https://github.com/pulls/123"],
  "browser_url": "https://github.com/",
  "status": "completed",
  "description_status": "completed",
  "description": {
    "narrative": "The user is reviewing pull request #123 on GitHub...",
    "entities": ["PR #123", "GitHub"],
    "intent": "code_review",
    "summary": "GitHub PR review"
  }
}
```

**When `include_nodes=true`:**
```json
{
  "frame_id": 42,
  "timestamp": "2026-03-25T10:30:00Z",
  "app_name": "Claude Code",
  "window_name": "Claude Code — ~/chat/MyRecall",
  "text": "Reviewing pull request #123 in the GitHub web interface...",
  "text_source": "accessibility",
  "urls": ["https://github.com/pulls/123"],
  "browser_url": "https://github.com/",
  "status": "completed",
  "nodes": [
    {"role": "AXStaticText", "text": "Reviewing pull request", "depth": 0},
    {"role": "AXButton", "text": "Approve", "depth": 1},
    {"role": "AXLink", "text": "View on GitHub", "url": "https://github.com/..."}
  ],
  "description_status": "completed",
  "description": {
    "narrative": "The user is reviewing pull request #123 on GitHub...",
    "entities": ["PR #123", "GitHub"],
    "intent": "code_review",
    "summary": "GitHub PR review"
  }
}
```

### Key Fields

| Field | Description |
|-------|-------------|
| `timestamp` | ISO8601 UTC capture time of the frame |
| `app_name` | Application name at capture time (e.g. "Claude Code", "Chrome") |
| `window_name` | Window title at capture time |
| `text` | Full text captured from the frame |
| `text_source` | `accessibility` (preferred) or `ocr` (fallback) |
| `nodes` | **Only present when `include_nodes=true`**. UI element tree with `role`, `text`, `depth`, and optional `url`. Nodes with empty text are filtered out. |
| `urls` | Extracted URLs from link-like nodes (via `AXLink` roles) and plain text regex |
| `browser_url` | Browser URL at capture time |
| `description_status` | `"completed"`, `"pending"`, `"processing"`, or `null` |
| `description` | **MyRecall unique feature**. AI-generated narrative, entities, intent, and summary. Available when `description_status == "completed"`. |
| `nodes_truncated` | Present only when `include_nodes=true` and `max_nodes` truncation was applied. Indicates how many nodes were omitted. |

> **Tip**: The `description.narrative` field is the most useful for answering
> "what was I doing in this frame?" questions. Check `description_status` first —
> if `"completed"`, the narrative is available.

### Common AX Roles (macOS)

| Concept | macOS Role |
|---------|------------|
| Button | `AXButton` |
| Static text | `AXStaticText` |
| Link | `AXLink` |
| Text field | `AXTextField` |
| Menu item | `AXMenuItem` |
| Checkbox | `AXCheckBox` |
| Web area | `AXWebArea` |
| Heading | `AXHeading` |

OCR-only roles (when `text_source=ocr`): `line`, `word`, `block`, `paragraph`, `page`

### When to Use

- **"What was I doing in this specific frame?"** → Step 3 (check `description.narrative`)
- **"What buttons/links were visible?"** → Step 3 with `include_nodes=true`, examine `nodes` array
- **"What URLs were open?"** → Step 3 (check `urls` array)
- **"Show me the full text of frame 42"** → Step 3

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
├─► "What was I doing in this specific frame?" / "What buttons/links were there?"
│    → Step 3: /frames/{id}/context (use include_nodes=true for UI structure)
│    → Check description.narrative first
│    → Check nodes array for UI elements (only with include_nodes=true)
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
| "What was that button text?" | `/search` → `/frames/{id}/context?include_nodes=true` | Get frame_id from search, check `nodes` array |
| "Show me a screenshot" | `/frames/{id}` | Describe verbally, don't include image data |
| "How long on Safari?" | `/activity-summary` | Check `apps` for Safari's `minutes` field |
| "What did I code in VSCode?" | `/search` with `app_name` | Use `window_name` for specific files |

### Critical Rules

1. **Always include `start_time` and `end_time`** in search requests — unbounded searches time out
2. **Start with narrow time ranges** (1-2 hours), expand only if no results
3. **Use `app_name` filter** when the user mentions a specific app
4. **Keep `limit` low** (5-10) initially — expand if needed
5. **`text_source` tells you quality**: `accessibility` > `ocr`. If results seem poor, they may be from OCR fallback
6. **`description.narrative` is the gold standard** for understanding activity — check if `description_status == "completed"` before relying on raw text
7. **Do NOT use `content_type` parameter** — it is deprecated and ignored
8. **Max 2-3 frames per response** — don't overwhelm the context with many frame details
9. **Use `include_nodes=true` only when you need UI structure** — the default (false) is more efficient

---

## Response Quality Guide

| Quality Issue | Likely Cause | Fix |
|---------------|-------------|-----|
| Empty `recent_texts` | Time range too narrow | Expand `start_time` |
| No search results | Query too specific | Try broader terms, check spelling |
| `text_source=ocr` everywhere | App lacks accessibility support (games, remote desktop, etc.) | Normal for some apps — use raw text |
| `description_status != "completed"` | AI description not yet generated | Use raw `text` and `nodes` instead |
| `audio_summary` is always empty | Audio not yet supported | Do not query or mention audio features |

---

## Out of Scope (Do NOT use)

These screenpipe endpoints do **not exist** in MyRecall:

| Screenpipe Endpoint | MyRecall Equivalent | Notes |
|---------------------|---------------------|-------|
| `GET /elements` | None | Not implemented. Use `/frames/{id}/context?include_nodes=true` instead |
| `POST /audio/retranscribe` | None | Audio not supported |
| `GET /meetings` | None | Not implemented |
| `POST /frames/export` | None | Not implemented |
| `POST /raw_sql` | None | Not exposed to agents |
| `screenpipe://` deeplinks | None | Not supported |
| `content_type=memory\|audio\|input` | `content_type` is deprecated | Ignored — always returns merged results |
