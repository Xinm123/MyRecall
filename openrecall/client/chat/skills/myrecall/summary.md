# Summary Node — `GET /v1/activity-summary`

**Purpose**: Broad overview of screen activity. Best starting point for almost every question.

## When to Use

- "What was I doing today/yesterday/recently?"
- "Which apps did I use?"
- "How long did I spend on X?"
- "Summarize my activity"
- "App usage stats"

## When to Escalate to Search

If the summary doesn't fully answer the user's question, or if they ask for more specific content:

- "Did I see anything about X?" → load `search.md`
- "Find frames with..." → load `search.md`
- "What did I code in VSCode?" → load `search.md` with `app_name=VSCode`

## Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `start_time` | ISO 8601 local | **Yes** | Start of time range (e.g. `2026-04-26T00:00:00`) |
| `end_time` | ISO 8601 local | **Yes** | End of time range (e.g. `2026-04-26T16:30:00`) |
| `app_name` | string | No | Filter by specific app name |
| `max_descriptions` | integer | No | Max AI frame descriptions to return. Default: **1000** when unspecified. Max: 1000. |

## Request Example

```bash
# Use local time directly from the injected header
# Date: 2026-04-26
# Local time now: 2026-04-26T16:30:00
START="2026-04-26T00:00:00"
END="2026-04-26T16:30:00"
curl "http://localhost:8083/v1/activity-summary?start_time=${START}&end_time=${END}"
```

## Response Format

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

## Key Fields

| Field | Description |
|-------|-------------|
| `apps` | List of apps used in the time range, ordered by `minutes` descending. Includes `frame_count`, accurate `minutes` (from timestamp gaps), `first_seen`, and `last_seen`. |
| `descriptions` | AI-generated frame descriptions (`summary`, `tags`, `timestamp`). Use `GET /v1/frames/{id}/context` for full `narrative`. |
| `total_frames` | Total completed screenshots in the time range |
| `audio_summary` | Currently empty (`segment_count: 0`). Audio is not yet supported. |

## Context Window Protection

- The `apps` array and a few `descriptions` entries are typically sufficient.
- Use `max_descriptions` to control response size.
- Write output to file and truncate if needed.

> **Note**: Only `queryable` frames are included. Frames still processing (`pending`/`processing`) or failed are excluded from the results.
