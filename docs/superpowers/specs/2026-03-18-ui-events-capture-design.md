# UI Events Capture System Design

**Date**: 2026-03-18
**Status**: Draft
**Author**: Claude

## 1. Overview

### 1.1 Purpose

Capture user interaction events (clicks, text input, app switches, clipboard) to enable:
- Smart capture triggers (click-triggered screenshots)
- Future search enhancement ("find what I typed")

### 1.2 Scope

- Add `ui_events` table to Edge database
- Implement `UIEventWriter` to persist events
- Integrate with existing event tap infrastructure
- Maintain alignment with screenpipe's approach (no idempotency for events)

### 1.3 Out of Scope

- Exposing UI events via API (future phase)
- Search over UI events (future phase)
- Windows/Linux support (macOS only for P1)

## 2. Database Schema

### 2.1 Table Definition

> **Aligns with screenpipe `ui_events` table** (see `_ref/screenpipe/crates/screenpipe-db/src/migrations/20250202000000_add_accessibility_and_input_tables.sql`)

```sql
CREATE TABLE ui_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,           -- ISO8601 UTC
    session_id TEXT,                   -- Session identifier
    relative_ms INTEGER,               -- Milliseconds since session start
    event_type TEXT NOT NULL,          -- 'click', 'move', 'scroll', 'key', 'text', 'app_switch', 'window_focus', 'clipboard'

    -- Position (click, move, scroll)
    x INTEGER,
    y INTEGER,
    delta_x INTEGER,                   -- Scroll delta
    delta_y INTEGER,                   -- Scroll delta

    -- Mouse/Key
    button INTEGER,                    -- Mouse button (0=left, 1=right, 2=middle)
    click_count INTEGER,               -- Click count (1=single, 2=double)
    key_code INTEGER,                  -- Key code
    modifiers INTEGER,                 -- Modifier flags (cmd, shift, etc.)

    -- Text
    text_content TEXT,                 -- Text content (for 'text' and 'clipboard' events)
    text_length INTEGER,               -- Text length (for 'key' events when content disabled)

    -- Clipboard
    clipboard_op TEXT,                 -- 'copy' | 'cut' | 'paste'

    -- App context
    app_name TEXT,
    app_pid INTEGER,
    window_title TEXT,
    browser_url TEXT,

    -- Element context (accessibility)
    element_role TEXT,
    element_name TEXT,
    element_value TEXT,
    element_description TEXT,
    element_automation_id TEXT,
    element_bounds TEXT,               -- JSON: {"x":0,"y":0,"width":100,"height":50}

    -- Frame correlation
    frame_id INTEGER,                  -- Link to triggered frame
    FOREIGN KEY (frame_id) REFERENCES frames(id) ON DELETE SET NULL
);

CREATE INDEX idx_ui_events_timestamp ON ui_events(timestamp);
CREATE INDEX idx_ui_events_type ON ui_events(event_type);
CREATE INDEX idx_ui_events_app ON ui_events(app_name);
CREATE INDEX idx_ui_events_session ON ui_events(session_id);
```

> **Note**: Columns `delta_x`, `delta_y`, `key_code`, `modifiers` are reserved for P2+ event types (`scroll`, `move`, `key`). They are included in P1 schema for forward compatibility with screenpipe but not populated.

### 2.2 Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Idempotency | None | Aligns with screenpipe; local-only writes, no network retry risk |
| Primary key | Auto-increment INTEGER | Simple, matches screenpipe pattern |
| Schema structure | Flat columns (not JSON) | Aligns with screenpipe; easier indexing and querying |
| `session_id` | UUID v4 per Host process | A session = one Host process lifetime; generated on startup, groups events from same run |
| `relative_ms` | Milliseconds offset | Enables precise timing within session |
| `frame_id` | Nullable FK | Links event to triggered capture when applicable |
| `element_*` | Optional columns | Accessibility context for richer interaction data |
| `clipboard_op` | Independent column | Clearer semantics than screenpipe's `modifiers` reuse |

## 3. Event Types

> **P1 Scope**: Only 4 event types are implemented. Others (`move`, `scroll`, `key`, `window_focus`) are **not implemented** (not just disabled), deferred to P2+.

### 3.1 Event Type Enum (P1)

```python
class UiEventType(str, Enum):
    CLICK = "click"           # Mouse click
    TEXT = "text"             # Aggregated text input
    APP_SWITCH = "app_switch" # Application switch
    CLIPBOARD = "clipboard"   # Clipboard operation

    # P2+ (not implemented in P1):
    # MOVE = "move"
    # SCROLL = "scroll"
    # KEY = "key"
    # WINDOW_FOCUS = "window_focus"
```

### 3.2 Event Payloads (P1)

| event_type | event_data schema | Default |
|------------|-------------------|---------|
| `click` | `{"x": int, "y": int, "button": int, "click_count": int, "modifiers": int, "element_role": str, "element_name": str, ...}` | ✅ Enabled |
| `text` | `{"text_content": str, "text_length": int}` | ✅ Enabled |
| `app_switch` | `{"app_name": str, "app_pid": int, "window_title": str}` | ✅ Enabled |
| `clipboard` | `{"clipboard_op": str, "text_content": str}` | ✅ Enabled |

**Privacy approach** (per `chat-prerequisites.md`):
- **No content filtering**: text_content and clipboard content captured as-is
- **No password field skipping**: All input fields captured
- **User control via event type toggle**: Disable entire event type if privacy needed

### 3.3 Alignment with screenpipe

| Event Type | screenpipe | MyRecall P1 | Status |
|------------|-----------|-------------|--------|
| `click` | ✅ | ✅ | ✅ Aligned |
| `text` | ✅ | ✅ | ✅ Aligned |
| `app_switch` | ✅ | ✅ | ✅ Aligned |
| `clipboard` | ✅ | ✅ | ✅ Aligned |
| `move` | ✅ (disabled) | ❌ Not implemented | P2+ |
| `scroll` | ✅ (disabled) | ❌ Not implemented | P2+ |
| `key` | ✅ (disabled) | ❌ Not implemented | P2+ |
| `window_focus` | ✅ (disabled) | ❌ Not implemented | P2+ |

## 4. Architecture

> **Reference**: screenpipe `crates/screenpipe-accessibility/src/platform/macos.rs`

### 4.1 screenpipe Component Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Host Process (screenpipe)                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │ UiRecorder                                                       │   │
│   │ - start_internal() spawns two threads                            │   │
│   │ - crossbeam channel for event passing                            │   │
│   │ - RecordingHandle provides event receiver                        │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                              │                                           │
│              ┌───────────────┴───────────────┐                           │
│              ▼                               ▼                           │
│   ┌─────────────────────┐        ┌─────────────────────┐                │
│   │ Thread 1            │        │ Thread 2            │                │
│   │ CGEventTap          │        │ App Observer        │                │
│   │ (CFRunLoop)         │        │ (NSWorkspace)       │                │
│   │                     │        │                     │                │
│   │ - click/mouse       │        │ - app_switch        │                │
│   │ - key/text          │        │ - window_focus      │                │
│   │ - scroll/clipboard  │        │ - update shared     │                │
│   │                     │        │   app/window state  │                │
│   └──────────┬──────────┘        └──────────┬──────────┘                │
│              │                               │                           │
│              │ UiEvent                       │ UiEvent                   │
│              └───────────────┬───────────────┘                           │
│                              ▼                                           │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │ crossbeam channel<UiEvent> (bounded, default 1000)              │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                              │                                           │
│                              ▼                                           │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │ ui_recorder.rs (server layer)                                   │   │
│   │ - Batch insert to DB (batch_size=100, timeout=1000ms)           │   │
│   │ - Send capture_trigger to frame capture system                  │   │
│   │ - Storm protection: drop old events on DB contention           │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.2 MyRecall Adaptation

**Key difference**: MyRecall has Host/Edge separation, events need to be uploaded via HTTP.

**Design decision**: Extend existing `MacOSEventTap` and `MacOSAppSwitchMonitor` rather than creating parallel threads.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Host Process (MyRecall)                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │ SharedState (新增，Thread 1/2 共享)                              │   │
│   │ - current_app: str                                               │   │
│   │ - current_window: str                                            │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                              ▲                                           │
│              ┌───────────────┴───────────────┐                           │
│              │ 更新                          │ 读取                       │
│   ┌──────────┴──────────┐        ┌──────────┴──────────┐                │
│   │ Thread 2            │        │ Thread 1            │                │
│   │ MacOSAppSwitchMonitor│        │ MacOSEventTap       │                │
│   │ (扩展，复用现有)     │        │ (扩展，复用现有)     │                │
│   │                     │        │                     │                │
│   │ - 500ms polling     │        │ - CGEventTap        │                │
│   │ - 检测 app switch   │        │ - 现有: mouse up    │                │
│   │ - 更新 SharedState  │        │   → TriggerEvent    │                │
│   │ - 新增: app_switch  │        │ - 新增: key down    │                │
│   │   → UiEventChannel  │        │   → TextBuffer      │                │
│   └──────────┬──────────┘        │   → UiEventChannel  │                │
│              │                   │ - 新增: Cmd+C/X/V   │                │
│              │                   │   → TriggerEvent    │                │
│              │                   │   → UiEventChannel  │                │
│              │                   │ - 读取 SharedState  │                │
│              │                   └──────────┬──────────┘                │
│              │                              │                           │
│              └───────────────┬──────────────┘                           │
│                              ▼                                           │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │ UiEventChannel (新增，与 TriggerEventChannel 并行)               │   │
│   │ - queue.Queue with put_nowait (非阻塞)                           │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                              │                                           │
│              ┌───────────────┴───────────────┐                           │
│              ▼                               ▼                           │
│   ┌─────────────────────┐        ┌─────────────────────┐                │
│   │ TriggerEventChannel │        │ Thread 3            │                │
│   │ (现有)              │        │ UIEventsUploader    │                │
│   │ → 触发截图           │        │ (新增)              │                │
│   └─────────────────────┘        │ - 批量 POST /v1/events              │
│                                  │ - batch_size=100                    │
│                                  │ - timeout=1000ms                    │
│                                  └──────────┬──────────┘                │
│                                             │ HTTP                      │
│                                             ▼                           │
├─────────────────────────────────────────────────────────────────────────┤
│                         Edge Process (MyRecall)                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │ POST /v1/events (new endpoint)                                  │   │
│   │ - Batch insert to ui_events table                               │   │
│   │ - FTS trigger auto-updates ui_events_fts                        │   │
│   └─────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.3 Thread Architecture

| Thread | 名称 | 职责 | 状态 |
|--------|------|------|------|
| Thread 1 | MacOSEventTap | CGEventTap callback + CFRunLoop | 扩展现有 |
| Thread 2 | MacOSAppSwitchMonitor | Polling app/window 变化 | 扩展现有 |
| Thread 3 | UIEventsUploader | 批量上传 UiEvent 到 Edge | 🆕 新增 |

### 4.4 Event → Screenshot Trigger Mapping

| Event Type | 触发截图 (系统 1) | 记录 UiEvent (系统 2) | 说明 |
|------------|------------------|---------------------|------|
| `click` | ✅ TriggerEvent | ✅ UiEvent | 双系统并行 |
| `app_switch` | ✅ TriggerEvent | ✅ UiEvent | 双系统并行 |
| `clipboard` | ✅ TriggerEvent | ✅ UiEvent | 双系统并行 |
| `text` | ❌ | ✅ UiEvent | 只记录，不触发截图 |

> **双系统模式**：用户操作同时触发截图（系统 1）和事件记录（系统 2），与 screenpipe 架构对齐。

### 4.5 Integration Points

| Component | MyRecall Location | 状态 | 说明 |
|-----------|-------------------|------|------|
| MacOSEventTap | `openrecall/client/events/macos.py` | ✅ 扩展 | 添加 KEY_DOWN 监听 + UiEvent 输出 |
| MacOSAppSwitchMonitor | `openrecall/client/events/macos.py` | ✅ 扩展 | 添加 UiEvent 输出 + SharedState 更新 |
| TriggerEventChannel | `openrecall/client/events/base.py` | ✅ 现有 | 触发截图（保持不变） |
| UiEventChannel | `openrecall/client/events/base.py` | 🆕 新增 | UI 事件传递 |
| SharedState | `openrecall/client/events/base.py` | 🆕 新增 | Thread 1/2 共享 app/window |
| UIEventsUploader | `openrecall/client/events/uploader.py` | 🆕 新增 | 批量上传到 Edge |
| POST /v1/events | `openrecall/server/api_v1.py` | 🆕 新增 | Edge 端点 |
| UIEventStore | `openrecall/server/database/ui_events_store.py` | 🆕 新增 | 数据库操作 |

### 4.6 Event Processing Patterns

#### 4.6.1 Click Event (Split Pattern - B2 Decision)

```python
# Thread 1: CGEventTap callback
def on_click(x, y, button, click_count, modifiers):
    # 1. Send main click event immediately
    event = UiEvent.click(timestamp, x, y, button, click_count, modifiers)
    channel.try_send(event)

    # 2. Spawn background thread for element context
    threading.Thread(target=get_element_context, args=(x, y, event.timestamp)).start()

def get_element_context(x, y, timestamp):
    element = get_element_at_position(x, y)
    if element:
        # Send context-only event (click_count=0 as marker)
        ctx_event = UiEvent.click_context(timestamp, x, y, element)
        channel.try_send(ctx_event)
    # Silent drop on failure
```

#### 4.6.2 Text Aggregation

```python
class TextBuffer:
    def __init__(self, timeout_ms=300):
        self.chars = ""
        self.last_time = None
        self.timeout_ms = timeout_ms

    def push(self, char: str):
        if char == '\x08':  # Backspace
            self.chars = self.chars[:-1]
        else:
            self.chars += char
        self.last_time = time.time()

    def should_flush(self) -> bool:
        if not self.last_time:
            return False
        elapsed = (time.time() - self.last_time) * 1000
        return elapsed >= self.timeout_ms

    def flush(self) -> Optional[str]:
        if not self.chars:
            return None
        text = self.chars
        self.chars = ""
        self.last_time = None
        return text
```

#### 4.6.3 Clipboard Capture

```python
def on_key_down(keycode, modifiers):
    if modifiers.has_cmd() and not modifiers.has_ctrl():
        if keycode == KEY_C:  # Cmd+C
            threading.Thread(target=capture_clipboard, args=('copy',)).start()
        elif keycode == KEY_X:  # Cmd+X
            threading.Thread(target=capture_clipboard, args=('cut',)).start()
        elif keycode == KEY_V:  # Cmd+V
            content = get_clipboard()  # Immediate for paste
            event = UiEvent.clipboard('paste', content)
            channel.try_send(event)

def capture_clipboard(operation):
    time.sleep(0.05)  # Wait for clipboard to update
    content = get_clipboard()
    event = UiEvent.clipboard(operation, content)
    channel.try_send(event)
```

### 4.7 Shared State Between Threads

```python
# Thread-safe shared state
from threading import Lock

class SharedState:
    def __init__(self):
        self._lock = Lock()
        self._current_app: Optional[str] = None
        self._current_window: Optional[str] = None

    @property
    def current_app(self) -> Optional[str]:
        with self._lock:
            return self._current_app

    @current_app.setter
    def current_app(self, value: Optional[str]):
        with self._lock:
            self._current_app = value

    @property
    def current_window(self) -> Optional[str]:
        with self._lock:
            return self._current_window

    @current_window.setter
    def current_window(self, value: Optional[str]):
        with self._lock:
            self._current_window = value
```

### 4.8 Error Handling and Storm Protection

> **Addresses ADR-0001 risk**: "Edge 不可达导致 Host backlog 膨胀"

**Storm protection strategy** (aligns with chat-prerequisites.md B4):

```python
class UIEventsUploader:
    def __init__(self):
        self._buffer: queue.Queue = queue.Queue(maxsize=1000)
        self._drop_count = 0

    def try_send(self, event: UiEvent) -> bool:
        """Non-blocking send with storm protection."""
        try:
            self._buffer.put_nowait(event)
            return True
        except queue.Full:
            # Storm protection: drop oldest event
            try:
                self._buffer.get_nowait()
                self._buffer.put_nowait(event)
                self._drop_count += 1
            except queue.Empty:
                pass
            return False

    def _upload_batch(self) -> None:
        """Upload batch with retry and backoff."""
        retry_count = 0
        max_retries = 3
        base_delay = 1.0

        while retry_count < max_retries:
            try:
                response = requests.post(url, json=payload, timeout=5.0)
                if response.ok:
                    return
            except requests.RequestException:
                pass

            retry_count += 1
            time.sleep(base_delay * (2 ** retry_count))  # Exponential backoff

        # On final failure: drop batch (storm protection)
        logger.warning(f"Edge unavailable, dropping {len(batch)} events")
```

**Error handling policy**:

| Scenario | Behavior | Rationale |
|----------|----------|-----------|
| Edge unavailable | Drop oldest events, keep buffer bounded | Prevent memory exhaustion |
| POST timeout | Retry with exponential backoff (max 3) | Transient network issues |
| POST 4xx/5xx | Log and drop batch | No retry for server errors |
| Buffer overflow | Drop oldest event | Storm protection (B4) |

### 4.9 File Changes

| File | Change |
|------|--------|
| `openrecall/server/database/migrations/20260318120000_create_ui_events.sql` | 🆕 New migration |
| `openrecall/server/database/ui_events_store.py` | 🆕 New store class |
| `openrecall/server/api_v1.py` | ✏️ Add `POST /v1/events` endpoint |
| `openrecall/client/events/macos.py` | ✏️ Extend MacOSEventTap + MacOSAppSwitchMonitor |
| `openrecall/client/events/base.py` | ✏️ Add UiEventChannel, SharedState, UiEvent |
| `openrecall/client/events/uploader.py` | 🆕 New UIEventsUploader class |
| `openrecall/shared/config.py` | ✏️ Add UI events config options |

## 5. Privacy Safeguards

> **Alignment**: Follows `docs/v3/chat-prerequisites.md` § 隐私与安全决策: "透明捕获 + 用户自主" model.

### 5.1 Design Principles

1. **Transparent Capture**: All content is captured as-is, no filtering or redaction
2. **User Control**: Users can disable event types entirely via configuration
3. **Local-First**: All data stays local, no cloud sync required

### 5.2 Data Captured (P1)

| Event Type | Data Captured | Notes |
|------------|---------------|-------|
| `click` | x, y, button, click_count, element_* | Full element context |
| `text` | text_content, text_length | **No password field skipping** (A2) |
| `app_switch` | app_name, app_pid | Application metadata |
| `clipboard` | clipboard_op, text_content | **No PII redaction** (A1) |

### 5.3 Configuration Options

```bash
# Master toggle
export OPENRECALL_CAPTURE_UI_EVENTS=false      # Disable all UI event capture

# Individual event type toggles
export OPENRECALL_CAPTURE_CLICKS=true           # Click events
export OPENRECALL_CAPTURE_TEXT=true             # Text input events
export OPENRECALL_CAPTURE_APP_SWITCH=true       # App switch events
export OPENRECALL_CAPTURE_CLIPBOARD=true        # Clipboard events
```

**No fine-grained content toggles**: Per `chat-prerequisites.md` decisions A1/A2/A4, we don't provide options like `capture_text_content` or `capture_clipboard_content`. If a user wants privacy, they disable the entire event type.

### 5.4 Privacy Decision Alignment

| Decision ID | chat-prerequisites.md | This Spec | Status |
|-------------|----------------------|-----------|--------|
| A1 | PII 脱敏 → D 不处理 | clipboard 原样存储 | ✅ Aligned |
| A2 | 密码字段 → B 不跳过 | text 捕获所有输入 | ✅ Aligned |
| A3 | 应用黑名单 → C 不实现 | 不提供应用级过滤 | ✅ Aligned |
| A4 | element_value → C 捕获所有 | click 捕获完整 element | ✅ Aligned |

### 5.5 User Control

Users can:
1. Disable all UI event capture via `OPENRECALL_CAPTURE_UI_EVENTS=false`
2. Disable specific event types individually
3. Close the application for complete privacy

### 5.6 Data Retention

UI events follow the same retention policy as frames (configurable via `OPENRECALL_RETENTION_DAYS`).

## 6. API Contract

### 6.1 POST /v1/events

**Request:**

```json
POST /v1/events
Content-Type: application/json

{
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "events": [
    {
      "timestamp": "2026-03-18T12:00:00.000Z",
      "event_type": "click",
      "x": 100,
      "y": 200,
      "button": 0,
      "click_count": 1,
      "modifiers": 0,
      "app_name": "Safari",
      "window_title": "Google - Safari",
      "element_role": "button",
      "element_name": "Search"
    },
    {
      "timestamp": "2026-03-18T12:00:01.500Z",
      "event_type": "text",
      "text_content": "hello world",
      "text_length": 11,
      "app_name": "Safari"
    },
    {
      "timestamp": "2026-03-18T12:00:05.000Z",
      "event_type": "clipboard",
      "clipboard_op": "copy",
      "text_content": "selected text",
      "app_name": "Safari"
    }
  ]
}
```

**Response:**

```json
{
  "status": "ok",
  "inserted": 3
}
```

**Error Response:**

```json
{
  "status": "error",
  "message": "Invalid event_type: unknown"
}
```

### 6.2 Batch Semantics

- **Batch size**: Max 100 events per request
- **Idempotency**: None (per Section 2.2)
- **Ordering**: Events processed in order received
- **Partial failure**: Entire batch rejected on validation error

## 7. Migration

### 7.1 Migration File

**Path**: `openrecall/server/database/migrations/20260318120000_create_ui_events.sql`

```sql
-- UI Events table for capturing user interactions
-- Aligns with screenpipe ui_events schema
CREATE TABLE IF NOT EXISTS ui_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    session_id TEXT,
    relative_ms INTEGER,
    event_type TEXT NOT NULL,

    -- Position
    x INTEGER,
    y INTEGER,
    delta_x INTEGER,
    delta_y INTEGER,

    -- Mouse/Key
    button INTEGER,
    click_count INTEGER,
    key_code INTEGER,
    modifiers INTEGER,

    -- Text
    text_content TEXT,
    text_length INTEGER,

    -- Clipboard
    clipboard_op TEXT,               -- 'copy' | 'cut' | 'paste'

    -- App context
    app_name TEXT,
    app_pid INTEGER,
    window_title TEXT,
    browser_url TEXT,

    -- Element context
    element_role TEXT,
    element_name TEXT,
    element_value TEXT,
    element_description TEXT,
    element_automation_id TEXT,
    element_bounds TEXT,

    -- Frame correlation
    frame_id INTEGER,
    FOREIGN KEY (frame_id) REFERENCES frames(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_ui_events_timestamp ON ui_events(timestamp);
CREATE INDEX IF NOT EXISTS idx_ui_events_type ON ui_events(event_type);
CREATE INDEX IF NOT EXISTS idx_ui_events_app ON ui_events(app_name);
CREATE INDEX IF NOT EXISTS idx_ui_events_session ON ui_events(session_id);

-- FTS for ui_events (searchable text content)
CREATE VIRTUAL TABLE IF NOT EXISTS ui_events_fts USING fts5(
    text_content,
    app_name,
    window_title,
    element_name,
    content='ui_events',
    content_rowid='id',
    tokenize='unicode61'
);

-- Triggers for ui_events FTS
CREATE TRIGGER IF NOT EXISTS ui_events_ai AFTER INSERT ON ui_events
WHEN NEW.text_content IS NOT NULL OR NEW.element_name IS NOT NULL
BEGIN
    INSERT INTO ui_events_fts(rowid, text_content, app_name, window_title, element_name)
    VALUES (NEW.id, NEW.text_content, NEW.app_name, NEW.window_title, NEW.element_name);
END;

CREATE TRIGGER IF NOT EXISTS ui_events_ad AFTER DELETE ON ui_events BEGIN
    INSERT INTO ui_events_fts(ui_events_fts, rowid, text_content, app_name, window_title, element_name)
    VALUES('delete', OLD.id, OLD.text_content, OLD.app_name, OLD.window_title, OLD.element_name);
END;

CREATE TRIGGER IF NOT EXISTS ui_events_au AFTER UPDATE ON ui_events BEGIN
    INSERT INTO ui_events_fts(ui_events_fts, rowid, text_content, app_name, window_title, element_name)
    VALUES('delete', OLD.id, OLD.text_content, OLD.app_name, OLD.window_title, OLD.element_name);
    INSERT INTO ui_events_fts(rowid, text_content, app_name, window_title, element_name)
    VALUES (NEW.id, NEW.text_content, NEW.app_name, NEW.window_title, NEW.element_name);
END;
```

> **Note**: The INSERT trigger uses a WHEN clause to prevent indexing rows with no searchable content. This optimization differs from screenpipe's unconditional triggers, reducing FTS index size for events like `click` without element context.

### 7.2 Rollback

```sql
DROP TABLE IF EXISTS ui_events;
DROP TABLE IF EXISTS ui_events_fts;
```

## 8. Python Performance Considerations

### 7.1 GIL Impact Analysis

Python GIL (Global Interpreter Lock) affects multi-threaded performance, but for UI event capture:

| Thread | Activity | GIL Impact |
|--------|----------|------------|
| Thread 1 (CGEventTap) | Callback in CFRunLoop | Low (callback is brief) |
| Thread 2 (Polling) | 500ms sleep, brief checks | Minimal |
| Thread 3 (Uploader) | HTTP I/O bound | Low (releases GIL on I/O) |

**Conclusion**: GIL contention is minimal for this workload.

### 7.2 Callback Performance

**Critical principle**: CGEventTap callback must be non-blocking.

```python
# ✅ Good: Callback only updates state
def _handle_event(self, _proxy, event_type, event, _refcon):
    if event_type == KEY_DOWN:
        self._text_buffer_chars += char  # In-memory, fast
        self._text_buffer_last_time = time.time()
    return event

# ❌ Bad: Callback does I/O or heavy processing
def _handle_event(self, _proxy, event_type, event, _refcon):
    if event_type == KEY_DOWN:
        save_to_disk(...)  # BLOCKS!
```

### 7.3 TextBuffer Flush Strategy

Align with screenpipe: flush in main loop, not callback.

```python
def _run_event_tap(self) -> None:
    while not self._stop_event.is_set():
        run_loop_run_in_mode(0.05)

        # Flush TextBuffer in main loop (not callback)
        if self._text_buffer_chars:
            elapsed = (time.time() - self._text_buffer_last_time) * 1000
            if elapsed >= 300:  # 300ms timeout
                text = self._text_buffer_chars
                self._text_buffer_chars = ""
                self._ui_event_channel.put_nowait(UiEvent.text(text))
```

### 7.4 Performance Estimates

| Scenario | Event Rate | Python Processing | Status |
|----------|-----------|-------------------|--------|
| Normal typing | ~10 keys/s | < 1ms/key | ✅ OK |
| Fast typing | ~20 keys/s | < 1ms/key | ✅ OK |
| Mouse clicks | ~2 clicks/s | < 0.5ms/click | ✅ OK |
| Clipboard ops | Occasional | < 5ms | ✅ OK |

### 7.5 No Lock TextBuffer

TextBuffer can be lock-free since only Thread 1 accesses it:

```python
# Thread 1 is the only writer/reader of TextBuffer
# No need for threading.Lock
self._text_buffer_chars = ""  # Single-threaded access
self._text_buffer_last_time = 0
```

## 9. Testing Strategy

### 9.1 Unit Tests

- `test_ui_event_store_insert.py`: Verify insert operations
- `test_ui_event_data_serialization.py`: Verify JSON payload handling

### 9.2 Integration Tests

- `test_ui_events_capture_flow.py`: End-to-end event capture
- `test_ui_events_config_disable.py`: Verify config disables capture

### 9.3 Error Handling Tests

- `test_ui_events_storm_protection.py`: Verify buffer overflow drops oldest events
- `test_ui_events_edge_unavailable.py`: Verify exponential backoff and drop behavior

### 9.4 Acceptance Criteria

- [ ] `ui_events` table created successfully
- [ ] `click` events persisted with correct payload (x, y, button, click_count)
- [ ] `text` events persisted with `text_content` (content always captured when enabled per A2)
- [ ] `app_switch` events capture app_name, app_pid
- [ ] `clipboard` events capture operation and `text_content` (content always captured when enabled per A1)
- [ ] `OPENRECALL_CAPTURE_UI_EVENTS=false` disables capture
- [ ] No performance impact on capture pipeline

## 10. Future Considerations

### 10.1 API Exposure (P1-S5 or before Chat)

**Required for**: Chat grounding (chat needs to search UI events)

```
GET /v1/events?type=click&start_time=...&end_time=...
GET /v1/search?content_type=input&q=...
```

**screenpipe alignment**:
- `ContentType::Input` in search API
- `SearchResult::Input(UiEventRecord)` in response

### 10.2 Search Integration (P1-S5 or before Chat)

**Required for**: Chat grounding

- FTS index on `text_content`, `app_name`, `window_title`
- Support `content_type=input` in `/v1/search`
- Align with screenpipe's `search_input()` function

### 10.3 Cross-Platform (P2+)

- Windows: Raw Input API
- Linux: XInput / libinput

## 11. Alignment with screenpipe

| Aspect | screenpipe | MyRecall P1 | Aligned |
|--------|-----------|-------------|---------|
| UI event table | `ui_events` | `ui_events` | ✅ |
| Idempotency | None | None | ✅ |
| Event types (P1) | click, text, app_switch, clipboard | click, text, app_switch, clipboard | ✅ |
| Event types (P2+) | move, scroll, key, window_focus | Not implemented | Deferred |
| Search integration | `content_type=input` | P1-S5 (before Chat) | ✅ Planned |
| API exposure | `SearchResult::Input` | P1-S5 (before Chat) | ✅ Planned |

**Privacy differences** (intentional):

| Aspect | screenpipe | MyRecall | Reason |
|--------|-----------|----------|--------|
| PII redaction | Regex-based | None | Local-first, no cloud sync |
| Password fields | Skip by default | No skipping | User autonomy principle |
| App blacklist | Built-in + configurable | Not implemented | Simplified design |

**Schema differences** (intentional):

| Aspect | screenpipe | MyRecall | Reason |
|--------|-----------|----------|--------|
| `clipboard_op` column | ❌ (reuses `modifiers`) | ✅ Independent column | Clearer semantics |
| `sync_id`/`machine_id`/`synced_at` | ✅ | ❌ | MyRecall is local-only, no cloud sync |

**Key differences**:
1. **P1 scope**: Only 4 event types implemented; others deferred to P2+
2. **Privacy model**: "透明捕获 + 用户自主" per `chat-prerequisites.md`
3. **Search integration**: MyRecall needs this before Chat development (P1-S5)

## 12. References

- screenpipe `macos.rs`: UI event capture implementation
- screenpipe `events.rs`: Event types definition
- screenpipe `types.rs`: Database types and `UiEventRecord`
- MyRecall ADR-0005: Vision-Only Search
- MyRecall `openrecall/client/events/macos.py`: Existing event tap
- MyRecall `docs/v3/chat-prerequisites.md`: Privacy decisions
