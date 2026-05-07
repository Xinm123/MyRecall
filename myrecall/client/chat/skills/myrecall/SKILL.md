---
name: myrecall
description: Use when the user asks about their MyRecall screen history, recent activity, app usage, or anything visible on their screen. Load this skill first, then load the appropriate node file based on the progressive disclosure strategy below.
---

# MyRecall

Query the user's screen history via local REST API at `http://localhost:8083`.

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

## Progressive Disclosure Strategy

Follow this escalation. Never jump to heavy tools first.

| User asks... | Load Node | Endpoint |
|-------------|-----------|----------|
| "What was I doing today?" / "Summarize my activity" / "Which apps did I use?" | `summary.md` | `GET /v1/activity-summary` |
| "Find frames about X" / "Did I see Y?" / "Search for Z" | `search.md` | `GET /v1/search` |
| "What was in this specific frame?" / "Show me the text" | `content.md` | `GET /v1/frames/{id}/context` |
| "Show me the screenshot" | `content.md` | `GET /v1/frames/{id}` |

**Escalation flow:**

```
User asks a question
│
├─► Broad overview question? → summary.md
│    → If summary answers it → Done
│    → If not → escalate to search.md
│
├─► Specific search question? → search.md
│    → If results found → escalate to content.md for details
│    → If no results → broaden query or check time range
│
├─► Specific frame question? → content.md (frame context)
│    → If need visual confirmation → content.md (frame image)
│
└─► App usage stats? → summary.md (apps array)
```

**Never call `/search` as the first step for broad questions.** Use `/activity-summary` first.

---

## Critical Rules (All Nodes)

1. **Always include `start_time` and `end_time`** — unbounded searches time out.
2. **Start with narrow time ranges** (1-2 hours), expand only if no results.
3. **Use `app_name` filter** when the user mentions a specific app.
4. **Keep `limit` low** (5-10) initially — expand if needed.
5. **`text_source` tells you quality**: `accessibility` > `ocr`. Poor results may be OCR fallback.
6. **`description.narrative` is the gold standard** — use it first, fall back to `text` if `description` is null.
7. **Do NOT use `content_type` parameter** — deprecated, has inconsistent behavior.
8. **Max 2-3 frames per response** — don't overwhelm the context with many frame details.
9. **Default search mode is `hybrid`** — combines FTS and vector search for best results.
10. **Never include raw image data** in your response to the user — describe verbally only.

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

## Node Files

| Node | File | Purpose |
|------|------|---------|
| Summary | `summary.md` | Activity overview, app usage, time stats |
| Search | `search.md` | Full-text and semantic search |
| Content | `content.md` | Frame details, text, screenshots |

Load the appropriate node file based on the progressive disclosure strategy above.

---

## Response Quality Guide

| Quality Issue | Likely Cause | Fix |
|---------------|-------------|-----|
| No search results | Query too specific | Try broader terms, check spelling |
| `text_source=ocr` everywhere | App lacks accessibility support | Normal for some apps — use raw text |
| `description` is null | AI description not yet generated | Use raw `text` instead |
| `audio_summary` is always empty | Audio not yet supported | Do not query or mention audio features |
| Slow or timeout on `/search` | Missing `start_time`/`end_time` | Always include both params |
| Poor search quality on broad questions | Used `/search` instead of `/activity-summary` | Start with `/activity-summary` for summaries |

---

## Out of Scope (Do NOT use)

These screenpipe endpoints do **not exist** in MyRecall:

| Screenpipe Endpoint | MyRecall Status | Notes |
|---------------------|-----------------|-------|
| `GET /elements` | Not implemented | — |
| `POST /audio/retranscribe` | Not supported | Audio not implemented |
| `GET /meetings` | Not implemented | — |
| `POST /frames/export` | Not implemented | — |
| `POST /raw_sql` | Not exposed | — |
| `screenpipe://` deeplinks | Not supported | — |
| `content_type=memory\|audio\|input` | Deprecated | Ignored — always returns merged results |
| `min_length` / `max_length` params | Removed | Filter via query instead |
| `/frames/{id}/context?include_nodes=true` | Query params not supported | Simplified API always returns same structure |
