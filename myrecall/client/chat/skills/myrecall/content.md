# Content Node — Frame Details and Images

## 1. Frame Context — `GET /v1/frames/{id}/context`

**Purpose**: Detailed information about a specific frame. Returns text, browser URLs, and AI-generated description.

### When to Use

- "What was I doing in this specific frame?"
- "What URLs were open?"
- "Show me the full text of frame 42"
- After `search.md` returns relevant `frame_id`s

### Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `frame_id` | integer | **Yes** (path) | The frame ID from search results |

> **Note**: This endpoint accepts no query parameters. Text is always truncated at 5000 characters.

### Request Example

```bash
curl "http://localhost:8083/v1/frames/42/context"
```

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
    "tags": ["code_review", "github"],
    "model": "qwen-vl",
    "generated_at": "2026-04-26T10:31:00.123Z"
  },
  "text": "Reviewing pull request #123 in the GitHub web interface...",
  "text_source": "accessibility",
  "urls": ["https://github.com/pulls/123"],
  "browser_url": "https://github.com/",
  "status": "completed",
  "description_status": "completed"
}
```

### Key Fields

| Field | Description |
|-------|-------------|
| `timestamp` | ISO8601 local capture time of the frame |
| `app_name` | Application name at capture time (e.g. "Claude Code", "Chrome") |
| `window_name` | Window title at capture time |
| `description` | **MyRecall unique feature**. AI-generated description with `narrative`, `summary`, `tags`, `model` (which AI model generated it), and `generated_at` (UTC timestamp). Returns `null` if not yet generated. |
| `text` | Full text captured from the frame (middle-truncated at 5000 chars) |
| `text_source` | `accessibility` (preferred), `ocr` (fallback), or `hybrid` (both merged) |
| `urls` | Extracted URLs from text via regex |
| `browser_url` | Browser URL at capture time |
| `status` | Frame processing status (`completed`, `pending`, etc.) |
| `description_status` | AI description generation status (`completed`, `pending`, `failed`, or `null` if not yet queued) |

> **Tip**: The `description.narrative` field is the most useful for answering "what was I doing in this frame?" questions. If `description` is `null`, the AI description has not been generated yet — use the raw `text` field instead.

---

## 2. Frame Image — `GET /v1/frames/{id}`

**Purpose**: Retrieve the actual screenshot (JPEG) for a frame.

### When to Use

- "Show me the screenshot" — only when user explicitly asks
- "What did the screenshot actually look like?" — rarely needed

### Request Example

```bash
curl -o /tmp/frame.jpg "http://localhost:8083/v1/frames/42"
```

> Returns `image/jpeg`.

### ⚠️ Critical Rule

**Never include raw image data in your response to the user.**
Only describe what you observe verbally.

---

## Context Window Protection

- Frame context text is middle-truncated at 5000 characters.
- Frame images are ~100-200 KB each and should not be included in context.
- Max 2-3 frames per response — don't overwhelm the context with many frame details.
