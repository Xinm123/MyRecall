# Frame Context Endpoint Simplification

> Date: 2026-04-09

## Overview

Simplify `GET /v1/frames/{id}/context` by removing query parameters and response fields that add complexity without proportional value.

## Changes

### Query Parameters Removed

| Parameter | Reason |
|-----------|--------|
| `max_text_length` | Server-side truncation with fixed default |
| `max_nodes` | `nodes` no longer returned |
| `include_nodes` | `nodes` no longer returned |

### Response Fields Removed

| Field | Reason |
|-------|--------|
| `nodes` | Structured AX tree data — not needed for MVP chat grounding |
| `nodes_truncated` | Tied to `nodes` |
| `description_status` | Redundant — `description != null` implies completed |

### Response Fields Kept

`frame_id`, `timestamp`, `app_name`, `window_name`, `description`, `text`, `text_source`, `urls`, `browser_url`, `status`

### Behavior Changes

- **Text truncation**: Always capped at **5000 characters**. If truncated, append `...` suffix.
- **URL extraction**: Unchanged — regex extraction from text (>10 chars, punctuation trimmed, deduplicated).
- **Description**: Always returned when available. Absent when `description_status != "completed"` (i.e., no `null` sentinel).

### Field Order

```json
{
  "frame_id": 42,
  "timestamp": "2026-03-26T14:32:05Z",
  "app_name": "Claude Code",
  "window_name": "Claude Code — ~/chat",
  "description": { "narrative": "...", "summary": "...", "tags": [] },
  "text": "...",
  "text_source": "accessibility",
  "urls": ["https://..."],
  "browser_url": null,
  "status": "completed"
}
```

Order logic: identity → capture context → AI summary → raw content → supplemental → state.

## Example Response

```json
{
  "frame_id": 42,
  "timestamp": "2026-03-26T14:32:05Z",
  "app_name": "Claude Code",
  "window_name": "Claude Code — ~/chat",
  "description": {
    "narrative": "The user is working on MyRecall v3 chat functionality in Claude Code.",
    "summary": "Working on API documentation",
    "tags": ["claude-code", "documentation"]
  },
  "text": "MyRecall v3 Chat API MyRecall Search Claude Code Today 14:32...",
  "text_source": "accessibility",
  "urls": ["https://github.com/anthropics/claude-code"],
  "browser_url": null,
  "status": "completed"
}
```

When `description` is absent (description not yet generated):

```json
{
  "frame_id": 43,
  "timestamp": "2026-03-26T14:30:00Z",
  "app_name": "Safari",
  "window_name": "GitHub",
  "description": null,
  "text": "...",
  "text_source": "accessibility",
  "urls": ["https://github.com"],
  "browser_url": "https://github.com",
  "status": "completed"
}
```

Note: `description` is returned as `null` (JSON null) when no AI description has been generated. There is no separate `description_status` field — consumers check `description != null` to determine if description is available.

## Files to Modify

| File | Change |
|------|--------|
| `openrecall/server/database/frames_store.py` | `get_frame_context()`: remove `include_nodes`, `max_nodes` params; add 5000-char truncation; remove nodes parsing logic |
| `openrecall/server/api_v1.py` | Remove query param parsing for `max_text_length`, `max_nodes`, `include_nodes`; remove `description_status` from response |
| `tests/test_chat_mvp_frame_context.py` | Remove `TestGetFrameContextTruncation`, `TestGetFrameContextIncludeNodes` classes; update other tests |
| `tests/test_chat_mvp_frame_context_api.py` | Update API tests to remove params; remove description_status assertions |
| `docs/v3/chat/api-fields-reference.md` | Update response fields table, remove nodes-related entries, update example JSON |
| `docs/v3/chat/mvp.md` | Update Frame Context Contract section |

## Testing

- Remove: `TestGetFrameContextTruncation` (6 tests), `TestGetFrameContextIncludeNodes` (8 tests)
- Keep: `TestGetFrameContext`, `TestGetFrameContextMetadataFields`, `TestGetFrameContextBoundsPrecision`
- Update: `TestGetFrameContext` — remove `include_nodes` args from all calls
- Add: 5000-char boundary test (text at exactly 5000, text at 5001)

## Rationale

- `nodes` is the richest structured data but adds token overhead and parsing complexity for marginal LLM grounding benefit
- Description provides semantic summarization that is more useful than raw AX tree for chat grounding
- Fixed 5000-char truncation is a reasonable default — long enough for meaningful context, short enough to protect LLM context windows
- Removing description_status reduces response redundancy — `description != null` is a sufficient indicator
