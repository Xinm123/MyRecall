---
name: myrecall-search
description: Use when the user asks about their recent screen activity, app usage, or anything visible on their screen.
---

# MyRecall Search

Query screen history via local REST API at `http://localhost:8083`.
Use a **4-step progressive disclosure** strategy: summary → search → context → image.
Never jump to heavy tools first.

> **Port**: MyRecall runs on **8083**, not 3030 (screenpipe uses 3030).

> **Timezone**: All timestamps are **local time (UTC+8)**. The user's local timezone context is injected at the start of every message.
>
> **Injected format**:
> ```
> Date: 2026-04-26
> Local time now: 2026-04-26T16:30:00
> ```
> Use `Date` and `Local time now` directly from the injected header.

---

## When to Use

- "What was I doing today / yesterday / recently?"
- "Which apps did I use?"
- "How long did I spend on X?"
- "Did I see anything about Y?"
- "Find frames with..."
- Specific frame or screenshot questions

Do NOT use for: audio, elements (`/elements`), meetings (`/meetings`), exports, raw SQL, screenpipe deeplinks, or the deprecated `content_type` parameter.

---

## Agent Policy — Progressive Disclosure

### Step Decision Tree

```
User asks a question
│
├─► "What was I doing?" / "Summarize my activity" / "Which apps?"
│    → Step 1: GET /v1/activity-summary
│
├─► "Did I see X?" / "Find frames about Y"
│    → Step 2: GET /v1/search
│    → If results found → Step 3 for frame details
│
├─► "What was I doing in this specific frame?"
│    → Step 3: GET /v1/frames/{id}/context
│    → Check description.narrative first, fall back to text if null
│
├─► "Show me the screenshot"
│    → Step 4: GET /v1/frames/{id} (JPEG) — describe verbally only
│
└─► "How much time on X?" / "App usage stats"
     → Step 1: /activity-summary (apps array has frame_count + minutes)
```

### Question-to-Endpoint Map

| User asks... | Endpoint | Notes |
|-------------|----------|-------|
| "What was I doing today?" | `/activity-summary` | Use `descriptions` for narratives |
| "Which apps did I use?" | `/activity-summary` | Check `apps` array |
| "Did I open GitHub today?" | `/activity-summary` then `/search` | Step 1 first, then Step 2 with `app_name` filter |
| "Find the PR I was reviewing" | `/search?q=PR` | Go directly, do NOT call summary first |
| "Did I see anything about AI?" | `/search?q=AI` | Go directly, do NOT call summary first |
| "What did I code in VSCode?" | `/search` with `app_name=VSCode` | Use `window_name` for specific files |
| "What was I doing in frame 42?" | `/frames/42/context` | Check `description.narrative` first |
| "Show me the screenshot" | `/frames/{id}` | Describe verbally, never include image data |
| "How long on Safari?" | `/activity-summary` | Check `apps` for Safari's `minutes` field |

### Anti-patterns

| User asks... | Wrong approach | Right approach |
|-------------|---------------|----------------|
| "What was I doing today?" | Search for "today" (too broad for FTS) | `/activity-summary` |
| "Find the PR I was reviewing" | Call `/activity-summary` first, then `/search` | Go directly to `/search?q=PR` |
| "Did I see anything about AI?" | Check summary first to see if AI was mentioned | Go directly to `/search?q=AI` |
| "Show me a screenshot" | Search for the frame first | If user already gave a frame ID, call `/frames/{id}` directly |
| "Summarize my day" | Paginate through 100 search results | `/activity-summary` |

### Critical Rules

1. **Always include `start_time` and `end_time`** — unbounded searches time out.
2. **Start with narrow time ranges** (1-2 hours), expand only if no results.
3. **Use `app_name` filter** when the user mentions a specific app.
4. **Keep `limit` low** (5-10) initially — expand if needed.
5. **`text_source` tells you quality**: `accessibility` > `ocr`. Poor results may be OCR fallback.
6. **`description.narrative` is the gold standard** — use it first, fall back to `text` if `description` is null.
7. **Do NOT use `content_type` parameter** — deprecated, has inconsistent behavior.
8. **Max 2-3 frames per response** — don't overwhelm the context with many frame details.
9. **Frame context text is middle-truncated at 5000 chars** when exceeding the limit.
10. **Default mode is `hybrid`** — combines FTS and vector search for best results.

---

## Time Formatting

Use local time directly from the injected header (no conversion needed).

| Expression | Meaning | How to compute |
|------------|---------|----------------|
| `today` | Since midnight local time | `Date` from header + `T00:00:00` |
| `yesterday` | Yesterday's full day | `Date` from header, minus 1 day |
| `recent` | Last 30 minutes | `Local time now` - 30 minutes |
| `1h ago` | One hour ago | `Local time now` - 1 hour |
| `2d ago` | Two days ago | `Local time now` - 2 days |
| `now` | Current moment | `Local time now` from header |

**Example**: Injected header says `Date: 2026-04-26`, `Local time now: 2026-04-26T16:30:00`
```bash
START="2026-04-26T00:00:00"
END="2026-04-26T16:30:00"
curl "http://localhost:8083/v1/activity-summary?start_time=${START}&end_time=${END}"
```

---

## Context Window Protection

API responses can be large. Always write curl output to a file first, check size, and truncate if needed.

```bash
curl "..." -o /tmp/myrecall_result.json
wc -c /tmp/myrecall_result.json        # Check size
head -c 5120 /tmp/myrecall_result.json # Truncate to ~5KB if too large
```

**Rules:**
- `activity-summary`: Compact overview. The `apps` array and a few `descriptions` entries are typically sufficient. Use `max_descriptions` to control size.
- `search`: Use `limit=5` initially, expand if needed. Each result is ~500-2000 tokens.
- `frame context`: Text is middle-truncated at 5000 characters. Use for specific frame details.
- `frame image`: Never include raw image data in context. Describe what you see verbally.

---

## API Quick Reference

| Endpoint | Purpose | Key Params |
|----------|---------|-----------|
| `GET /v1/activity-summary` | Broad activity overview | `start_time`, `end_time`, `app_name`, `max_descriptions` (optional, max: 1000, no default — returns up to 1000 when unspecified) |
| `GET /v1/search` | Full-text + semantic search | `q`, `mode` (fts/vector/hybrid), `limit` (default: 20, no max), `start_time`, `end_time`, `app_name`, `window_name`, `browser_url`, `focused`, `include_text`, `max_text_length` (default: 200) |
| `GET /v1/frames/{id}/context` | Detailed frame info + text | `frame_id` (path only, no query params) |
| `GET /v1/frames/{id}` | Screenshot JPEG | `frame_id` (path) — save to file, never include in response |

> **⚠️ `content_type` is deprecated.** Do not use. It is ignored and may log warnings.

> **`include_text`**: When `include_text=true`, text is truncated to `max_text_length` (default 200) in all modes.

---

## Endpoint Details

### 1. Activity Summary — `GET /v1/activity-summary`

Best starting point for almost every broad question.

```bash
START="2026-04-26T00:00:00"
END="2026-04-26T16:30:00"
curl "http://localhost:8083/v1/activity-summary?start_time=${START}&end_time=${END}"
```

**Response:**
```json
{
  "apps": [
    {"name": "Safari", "frame_count": 10, "minutes": 0.33, "first_seen": "...", "last_seen": "..."}
  ],
  "total_frames": 15,
  "time_range": {"start": "...", "end": "..."},
  "descriptions": [
    {"frame_id": 42, "timestamp": "...", "summary": "GitHub PR review", "tags": ["code_review", "github"]}
  ]
}
```

| Field | Description |
|-------|-------------|
| `apps` | Ordered by `minutes` desc. Includes `frame_count`, `first_seen`, `last_seen`. |
| `descriptions` | AI-generated descriptions (`summary`, `tags`). Use `/frames/{id}/context` for full `narrative`. |
| `total_frames` | Total completed screenshots in range |
| `audio_summary` | Always empty — audio not supported |

---

### 2. Search — `GET /v1/search`

Default mode: `hybrid` (FTS + vector with RRF fusion).

```bash
# Hybrid search (default)
curl "http://localhost:8083/v1/search?q=GitHub+PR&start_time=${START}&end_time=${END}&limit=10"

# FTS-only (faster, keyword-based)
curl "http://localhost:8083/v1/search?q=GitHub+PR&mode=fts&start_time=${START}&end_time=${END}&limit=10"

# Vector-only (semantic similarity)
curl "http://localhost:8083/v1/search?q=GitHub+PR&mode=vector&start_time=${START}&end_time=${END}&limit=10"
```

**Key response fields:**

| Field | Description |
|-------|-------------|
| `frame_id` | Use with `/frames/{id}/context` for details |
| `timestamp` | ISO8601 local capture time |
| `text_source` | `accessibility` (AX tree), `ocr` (fallback), or `hybrid` |
| `app_name`, `window_name`, `browser_url` | Capture-time metadata |
| `embedding_status` | Vector embedding status: `""` (not queued), `pending`, `completed`, or `failed` |
| `description` | AI description: `{narrative, summary, tags[]}` — only present when `description_status='completed'` |
| `score` | Unified relevance score (all modes) |
| `fts_score` | FTS5 BM25 — typically negative, more negative = better |
| `cosine_score` | Vector similarity 0-1, higher = more similar |
| `fts_rank` | Position in FTS results (hybrid mode only) |
| `vector_rank` | Position in vector results (hybrid mode only) |
| `hybrid_rank` | Final RRF fused rank (hybrid mode only) |

**Score fields by mode:**

| Mode | Returned |
|------|----------|
| `fts` | `score`, `fts_score` |
| `vector` | `score`, `cosine_score` |
| `hybrid` | `score`, `fts_score`, `fts_rank`, `cosine_score`, `hybrid_rank`, `vector_rank` |

---

### 3. Frame Context — `GET /v1/frames/{id}/context`

Detailed info for a specific frame. No query parameters accepted.

```bash
curl "http://localhost:8083/v1/frames/42/context"
```

**Response:**
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
  "text": "Reviewing pull request #123...",
  "text_source": "accessibility",
  "urls": ["https://github.com/pulls/123"],
  "browser_url": "https://github.com/",
  "status": "completed",
  "description_status": "completed"
}
```

| Field | Description |
|-------|-------------|
| `description` | AI-generated description. **Most useful field** for "what was I doing?" Check `narrative` first. Null if not yet generated. |
| `text` | Full captured text, middle-truncated at 5000 chars |
| `urls` | Extracted URLs from text via regex |
| `status` | Frame processing status |
| `description_status` | AI description status: `completed`, `pending`, `failed`, or `null` |

**Error:** `404 NOT_READY` — frame exists but `visibility_status` is not `queryable`.

---

### 4. Frame Image — `GET /v1/frames/{id}`

Retrieve screenshot JPEG. **Never include image data in your response** — describe verbally only.

```bash
curl -o /tmp/frame.jpg "http://localhost:8083/v1/frames/42"
```

---

## Common Mistakes

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| No search results | Query too specific | Try broader terms, check spelling |
| `text_source=ocr` everywhere | App lacks accessibility support (games, remote desktop) | Normal for some apps — use raw text |
| `description` is null | AI description not yet generated | Use raw `text` instead |
| `audio_summary` is always empty | Audio not yet supported | Do not query or mention audio |
| Slow or timeout on `/search` | Missing `start_time`/`end_time` | Always include both params |
| Poor search quality on broad questions | Used `/search` instead of `/activity-summary` | Start with `/activity-summary` for summaries |

---

## Out of Scope (Do NOT use)

| Screenpipe Endpoint | MyRecall Status | Notes |
|---------------------|-----------------|-------|
| `GET /elements` | Not implemented | — |
| `POST /audio/retranscribe` | Not supported | Audio not implemented |
| `GET /meetings` | Not implemented | — |
| `POST /frames/export` | Not implemented | — |
| `POST /raw_sql` | Not exposed | — |
| `screenpipe://` deeplinks | Not supported | — |
| `content_type=memory|audio|input` | Deprecated | Ignored — always returns merged results |
| `min_length` / `max_length` params | Removed | Filter via query instead |
| `/frames/{id}/context?include_nodes=true` | Query params not supported | Simplified API always returns same structure |
