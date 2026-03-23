# Frame Description Design

**Date:** 2026-03-24
**Author:** Claude
**Status:** Approved

## Overview

Add a new `description` field to each frame that stores an AI-generated semantic description of the screen content. This enables chat agents to better understand frame semantics beyond fragmented OCR text, used in `/frames/<id>/context` and `/activity-summary` endpoints.

## Goals

- Provide structured, narrative-rich descriptions of screen content for AI agents
- Support both local (Qwen VL) and cloud (OpenAI-compatible, DashScope) AI providers
- Decouple description generation from the existing OCR pipeline via an independent worker
- Enable manual trigger, queue monitoring, and historical backfill

## Non-Goals

- FTS5 index on description (planned for v2, use independent FTS table)
- Batch processing of multiple frames (planned for v2)
- Caching layer (planned for v2)

---

## Data Model

### FrameDescription

```python
class FrameDescription(BaseModel):
    narrative: str          # Natural language description of screen content + user intent (max 512 chars)
    entities: List[str]    # Key entities extracted (max 10 items)
    intent: str             # User intent in natural language phrase (e.g., "authenticating to GitHub")
    summary: str            # One-sentence summary (max 50 words)
```

### Example

```json
{
  "frame_id": "f_01HXYZ...",
  "description": {
    "narrative": "用户正在 GitHub 登录页面，邮箱字段已填写，光标停留在密码输入框。页面上方有 'Sign in to GitHub' 标题，左侧有 GitHub logo，右侧表单包含用户名/邮箱、密码输入框及 'Sign in' 按钮。忘记密码链接可见。",
    "entities": ["GitHub", "Sign in to GitHub", "email field", "password field", "Remember me checkbox", "Forgot password link"],
    "intent": "authenticating to GitHub",
    "summary": "GitHub 登录表单，用户准备输入密码"
  }
}
```

---

## Database Schema

### New Table: `frame_descriptions`

```sql
CREATE TABLE frame_descriptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    frame_id INTEGER NOT NULL REFERENCES frames(id),
    narrative TEXT NOT NULL,
    entities_json TEXT NOT NULL,       -- JSON array
    intent TEXT NOT NULL,
    summary TEXT NOT NULL,
    description_model TEXT,            -- 'qwen3-vl', 'gpt-4o', 'qwen-vl-max', etc.
    generated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(frame_id)
);
CREATE INDEX idx_fd_frame_id ON frame_descriptions(frame_id);
```

### New Table: `description_tasks`

```sql
CREATE TABLE description_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    frame_id INTEGER NOT NULL REFERENCES frames(id),
    status TEXT DEFAULT 'pending',     -- pending / processing / completed / failed
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    next_retry_at TIMESTAMP,           -- For exponential backoff
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    UNIQUE(frame_id)
);
CREATE INDEX idx_dt_status ON description_tasks(status);
CREATE INDEX idx_dt_next_retry ON description_tasks(next_retry_at);
```

### Frames Table Alteration

```sql
ALTER TABLE frames ADD COLUMN description_status TEXT DEFAULT NULL;
  -- NULL = not yet queued
  -- 'pending' = queued for generation
  -- 'processing' = worker is processing
  -- 'completed' = description available
  -- 'failed' = generation failed after max retries
```

---

## Provider Architecture

### Protocol

```python
class DescriptionProvider(Protocol):
    def generate(self, image_path: str, context: FrameContext) -> FrameDescription:
        """Generate frame description.

        Args:
            image_path: Path to JPEG snapshot
            context: Frame metadata (app_name, window_title, browser_url) injected into prompt

        Returns:
            FrameDescription object
        """
        ...
```

### Implementations

| Class | Backend | SDK |
|---|---|---|
| `LocalDescriptionProvider` | Qwen3 VL (local) | `transformers` |
| `OpenAIDescriptionProvider` | OpenAI-compatible HTTP API | `requests` |
| `DashScopeDescriptionProvider` | 通义千问 API | `dashscope` SDK |

Note: DashScope is not OpenAI-compatible — it has its own SDK and message format, so it cannot be merged into `OpenAIDescriptionProvider`. Common logic (JSON parsing, error handling, timeout) is extracted into shared utility functions.

### Prompt

```
Analyze this screenshot and output a strictly valid JSON object:
{
  "narrative": "Detailed natural language description of the screen content and user intent (max 512 chars)",
  "entities": ["entity1", "entity2", ...],  // max 10 items
  "intent": "User intent in phrase form (e.g., 'authenticating to GitHub')",
  "summary": "One-sentence summary (max 50 words)"
}
Do not include markdown formatting.
```

The `context` (app_name, window_title, browser_url) is injected into the prompt as supplementary information to guide the model.

### Configuration

```python
# openrecall/shared/config.py
OPENRECALL_DESCRIPTION_PROVIDER: str = "local"  # local / openai / dashscope
OPENRECALL_DESCRIPTION_MODEL: str = ""         # Provider-specific model name
OPENRECALL_DESCRIPTION_ENABLED: bool = True      # Global toggle
```

---

## Worker Architecture

### Independent `DescriptionWorker` Process

```
ingest (POST /v1/ingest)
  → claim_frame() → finalize_claimed_frame()
  → insert_description_task()  [description_tasks: pending]
  → return frame_id

DescriptionWorker (independent process)
  → poll description_tasks WHERE status='pending' AND (next_retry_at IS NULL OR next_retry_at <= now)
  → update status='processing'
  → call DescriptionProvider.generate()
  → insert into frame_descriptions
  → update frames.description_status='completed'
  → update description_tasks.status='completed'

On failure:
  → retry_count++
  → if retry_count < 3: next_retry_at = now + backoff(1min, 5min, 15min), status='pending'
  → else: status='failed', frames.description_status='failed', error_message=...
```

### Retry Backoff

| Attempt | Delay |
|---|---|
| Retry 1 | 1 minute |
| Retry 2 | 5 minutes |
| Retry 3 | 15 minutes |
| After 3 | `status='failed'` (manual reset required) |

### Concurrency

Each frame is processed independently. A frame in retry backoff does not block other frames — the worker continues polling and processing other pending tasks.

---

## API Integration

### 1. `GET /v1/frames/<frame_id>/context`

**Response extension:**

```json
{
  "frame_id": 123,
  "timestamp": "2026-03-23T10:30:15Z",
  "app_name": "Chrome",
  "window_name": "Sign in - GitHub",
  "browser_url": "https://github.com/login",
  "text_source": "ocr",
  "text": "Remember me [ ] Sign in ...",
  "nodes": [...],
  "description_status": "completed",
  "description": {
    "narrative": "...",
    "entities": ["..."],
    "intent": "...",
    "summary": "..."
  }
}
```

**Status handling:**

| `description_status` | `description` field |
|---|---|
| `completed` | Full description object |
| `pending` / `processing` | `null` |
| `failed` | `null` |
| `NULL` (not queued) | `null` |

### 2. `GET /v1/activity-summary`

**Response extension:**

```json
{
  "apps": [{"name": "Chrome", "count": 45}],
  "recent_texts": ["Remember me [ ] Sign in ...", "..."],
  "total_frames": 120,
  "time_range": {"start": "...", "end": "..."},
  "descriptions": [
    {"frame_id": 123, "summary": "GitHub 登录表单", "intent": "authenticating to GitHub"},
    {"frame_id": 124, "summary": "Terminal 中运行测试", "intent": "running tests"}
  ]
}
```

- Default limit: 20 most recent frames with completed descriptions
- Query param: `max_descriptions=N` (default 20, max 100)

### 3. `POST /v1/frames/<frame_id>/description`

Manually trigger description generation for a single frame.

**Request:** No body required.

**Response (202 Accepted):**
```json
{
  "task_id": 456,
  "frame_id": 123,
  "status": "pending",
  "message": "Description generation queued"
}
```

**Behavior:**
- If `description_status` is `completed`, return 409 Conflict
- If `description_status` is `pending`/`processing`, return 409 Conflict
- If `description_status` is `failed`, reset to `pending` and re-insert into `description_tasks`
- If `description_status` is NULL, insert new task

### 4. `GET /v1/description/tasks/status`

Return queue statistics.

**Response:**
```json
{
  "pending": 15,
  "processing": 2,
  "completed": 1280,
  "failed": 3
}
```

### 5. `POST /v1/admin/description/backfill`

Trigger backfill for all historical frames without descriptions.

**Response (202 Accepted):**
```json
{
  "message": "Backfill started",
  "estimated_count": 5432
}
```

**Behavior:**
- Inserts `description_tasks` for all frames where `description_status IS NULL`
- Returns immediately (async processing by worker)

---

## File Structure

```
openrecall/
├── shared/
│   └── models.py                    # Add FrameDescription model
├── server/
│   ├── database/
│   │   ├── migrations/
│   │   │   └── YYYYMMDDHHMMSS_add_frame_description.sql
│   │   └── frames_store.py          # Add description CRUD methods
│   ├── ai/
│   │   ├── base.py                  # Add DescriptionProvider protocol
│   │   ├── providers.py              # LocalDescriptionProvider, OpenAIDescriptionProvider, DashScopeDescriptionProvider
│   │   └── engine.py                 # Provider factory / initialization
│   ├── worker/
│   │   └── description_worker.py     # New: Independent DescriptionWorker
│   ├── api_v1.py                    # Extend context, activity-summary; add new endpoints
│   └── description/
│       ├── service.py                # Description service (generate, enqueue, backfill)
│       └── router.py                 # FastAPI router for description endpoints
└── tests/
    ├── test_description_provider.py  # Unit tests for providers
    ├── test_description_worker.py    # Worker integration tests
    └── test_description_api.py       # API endpoint tests
```

---

## Implementation Order

1. **Database migration** — Add tables and columns
2. **Provider layer** — `DescriptionProvider` protocol + 3 implementations
3. **Service layer** — Description service (enqueue, generate, backfill)
4. **Worker** — `DescriptionWorker` process
5. **API endpoints** — Extend existing + add new
6. **Tests** — Unit + integration

---

## Open Questions

(None — all resolved during design discussion)
