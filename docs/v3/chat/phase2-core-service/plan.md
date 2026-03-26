# Phase 2: Core Service - Implementation Plan

> **Detailed TDD Plan**: `docs/superpowers/plans/2026-03-26-phase2-core-service.md`
> This document provides the design specification. For step-by-step TDD implementation, see the plan linked above.

## Overview

This plan outlines the implementation steps for Phase 2, building the Chat Service backend logic for MyRecall v3 chat functionality.

## Prerequisites

- [x] Phase 1 completed (Pi installation, skill file, config manager)
- [x] MyRecall Edge server running on `localhost:8083`
- [x] API endpoints implemented: `/v1/activity-summary`, `/v1/search`, `/v1/frames/{id}/context`, `/v1/frames/{id}`
- [x] bun installed on development machine
- [x] `MINIMAX_CN_API_KEY` or `KIMI_API_KEY` environment variable set

## Task Breakdown

### Task 2.1: Types and Data Models

**File**: `openrecall/client/chat/types.py`

**Estimated effort**: Small

**Steps**:

1. Define `Conversation` dataclass
   - `id: str` (UUID)
   - `title: str`
   - `messages: list[Message]`
   - `created_at: datetime`
   - `updated_at: datetime`

2. Define `Message` dataclass
   - `role: str` ("user" | "assistant")
   - `content: str`
   - `tool_calls: list[ToolCall] | None`
   - `created_at: datetime`

3. Define `ToolCall` dataclass
   - `id: str`
   - `name: str`
   - `args: dict`
   - `status: str` ("running" | "done" | "error")
   - `result: str | None`

4. Define `PiStatus` dataclass
   - `running: bool`
   - `pid: int | None`
   - `session_id: str | None`

5. Define `ConversationMeta` dataclass (for listing)
   - `id: str`
   - `title: str`
   - `created_at: datetime`
   - `updated_at: datetime`
   - `message_count: int`

6. Add JSON serialization helpers (to_dict, from_dict)

**Deliverables**:
- `openrecall/client/chat/types.py`

**Validation**:
```bash
python -c "
from openrecall.client.chat.types import Conversation, Message
c = Conversation(id='test', title='Test', messages=[], created_at=None, updated_at=None)
print(c.to_dict())
"
```

---

### Task 2.2: Conversation Manager

**File**: `openrecall/client/chat/conversation.py`

**Estimated effort**: Medium

**Steps**:

1. Define storage path: `~/MRC/chats/`
   - Use `OPENRECALL_CLIENT_DATA_DIR` if set, else `~/MRC`

2. Implement `ensure_chats_dir() -> Path`
   - Create `chats/` directory if not exists

3. Implement `create_conversation() -> Conversation`
   - Generate UUID for id
   - Set created_at, updated_at to now
   - Empty messages list
   - Save to file

4. Implement `load_conversation(conversation_id: str) -> Conversation | None`
   - Read `{chats_dir}/{conversation_id}.json`
   - Parse JSON to Conversation object
   - Return None if not found

5. Implement `save_conversation(conversation: Conversation) -> None`
   - Update `updated_at`
   - Write to `{chats_dir}/{conversation.id}.json`
   - Atomic write (temp file + rename)

6. Implement `list_conversations() -> list[ConversationMeta]`
   - Read all JSON files
   - Extract metadata
   - Sort by `updated_at` DESC

7. Implement `delete_conversation(conversation_id: str) -> bool`
   - Delete JSON file
   - Return True if deleted, False if not found

8. Implement `add_message(conversation: Conversation, role: str, content: str, tool_calls: list | None = None) -> Message`
   - Create Message object
   - Append to conversation.messages
   - Update conversation.updated_at
   - Auto-generate title from first user message if title is empty

9. Write unit tests

**Deliverables**:
- `openrecall/client/chat/conversation.py`
- `tests/test_chat_conversation.py`

**Validation**:
```bash
python -c "
from openrecall.client.chat.conversation import create_conversation, list_conversations
c = create_conversation()
print(f'Created: {c.id}')
print(f'List: {len(list_conversations())} conversations')
"
```

---

### Task 2.3: Pi RPC Manager

**File**: `openrecall/client/chat/pi_rpc.py`

**Estimated effort**: Large

**Steps**:

1. Define `PiRpcManager` class
   - `workspace_dir: Path` - Pi working directory
   - `event_callback: Callable[[dict], None]` - Called for each Pi event
   - `process: subprocess.Popen | None` - Child process
   - `stdin: IO | None` - For writing commands
   - `pending_requests: dict[str, Future]` - Request ID to response future

2. Implement `__init__(workspace_dir, event_callback)`
   - Create workspace directory if not exists
   - Ensure skill is installed in workspace

3. Implement `start(provider: str, model: str) -> bool` (sync)
   - Find Pi executable via `pi_manager.find_pi_executable()`
   - Build command:
     ```bash
     pi --mode rpc --provider {provider} --model {model}
     ```
   - Set working directory to `workspace_dir`
   - Set environment variables (API keys)
   - Spawn process with piped stdin/stdout/stderr
   - Start stdout reader thread
   - Return True on success

4. Implement stdout reader thread
   - Read lines from Pi stdout (JSONL)
   - Parse each line as JSON
   - Dispatch events via `event_callback`
   - Handle `response` type to resolve pending requests
   - Handle partial/incomplete lines gracefully

5. Implement `stop() -> None`
   - Send `{"type": "abort"}` to stdin
   - Wait for process to exit (with timeout)
   - Kill process if needed
   - Clean up resources

6. Implement `send_prompt(content: str, images: list | None = None) -> str`
   - Generate unique request ID
   - Build JSON command:
     ```json
     {"type": "prompt", "id": "req-uuid", "content": "...", "images": [...]}
     ```
   - Write to stdin
   - Return request ID

7. Implement `new_session() -> None`
   - Write `{"type": "new_session"}` to stdin
   - Wait for acknowledgment

8. Implement `abort() -> None`
   - Write `{"type": "abort"}` to stdin
   - Wait for acknowledgment

9. Implement `is_running() -> bool`
   - Check if process is alive via `poll()`

10. Add error handling
    - Handle process crash
    - Handle stdin write errors
    - Handle stdout parse errors

11. Write unit tests (mocked subprocess)

**Deliverables**:
- `openrecall/client/chat/pi_rpc.py`
- `tests/test_chat_pi_rpc.py`

**Validation**:
```bash
# Requires API key
export MINIMAX_CN_API_KEY=your_key

python -c "
import asyncio
from openrecall.client.chat.pi_rpc import PiRpcManager
from pathlib import Path

events = []
def on_event(e): events.append(e)

mgr = PiRpcManager(Path('~/MRC/chat-workspace').expanduser(), on_event)
mgr.start('minimax-cn', 'MiniMax-M2.7')
print(f'Running: {mgr.is_running()}')
mgr.stop()
"
```

---

### Task 2.4: Chat Service

**File**: `openrecall/client/chat/service.py`

**Estimated effort**: Large

**Steps**:

1. Define `ChatService` class
   - `data_dir: Path`
   - `pi_manager: PiRpcManager`
   - `conversation_manager: ConversationManager`

2. Implement `__init__(data_dir: Path)`
   - Initialize conversation manager
   - Create Pi RPC manager (lazy - don't start yet)

3. Implement `ensure_pi_running() -> None` (async)
   - Check if Pi is running
   - If not, start with default provider/model
   - Handle startup errors

4. Implement `stream_response(conversation_id: str, message: str, images: list | None) -> AsyncGenerator[dict, None]`
   - Load or create conversation
   - Ensure Pi is running
   - Save user message to conversation
   - Create queue for SSE events
   - Set up event callback to put events in queue
   - Send prompt to Pi
   - Yield events from queue until `agent_end`
   - Accumulate assistant response
   - Save assistant message to conversation
   - Clean up

5. Implement `switch_conversation(conversation_id: str) -> None` (async)
   - Call `pi_manager.new_session()`
   - Update internal state

6. Implement `get_pi_status() -> PiStatus`
   - Return current Pi process status

7. Implement `create_conversation() -> Conversation`
   - Delegate to conversation manager
   - Reset Pi session

8. Implement error recovery
   - Auto-restart Pi on crash (max 3 retries)
   - Exponential backoff between retries
   - Emit error events to SSE stream

9. Write unit tests

**Deliverables**:
- `openrecall/client/chat/service.py`
- `tests/test_chat_service.py`

**Validation**:
```bash
# Requires running Edge server and API key
pytest tests/test_chat_service.py -v -k "test_stream"
```

---

### Task 2.5: SSE Routes

**File**: `openrecall/client/chat/routes.py`

**Estimated effort**: Medium

**Steps**:

1. Create Flask Blueprint `chat_bp`
   - URL prefix: `/chat`

2. Implement `POST /chat/api/stream` (SSE endpoint)
   - Parse JSON body: `{conversation_id, message, images?}`
   - Validate required fields
   - Get or create ChatService instance
   - Return `text/event-stream` response
   - Yield events from `service.stream_response()`
   - Handle errors gracefully
   - Send keepalive comments (`: keepalive`) every 15 seconds to prevent timeout

3. Implement `GET /api/conversations`
   - Return list of conversation metadata
   - JSON response: `{conversations: [ConversationMeta...]}`

4. Implement `GET /api/conversations/<id>`
   - Load conversation
   - Return full conversation JSON
   - 404 if not found

5. Implement `POST /api/conversations`
   - Create new conversation
   - Return created conversation

6. Implement `DELETE /api/conversations/<id>`
   - Delete conversation
   - Return 204 on success, 404 if not found

7. Implement `POST /api/new-session`
   - Reset Pi session
   - Return 200 on success

8. Implement `GET /api/pi-status`
   - Return Pi process status

9. Register blueprint with Flask app in `openrecall/client/web/app.py`

10. Write integration tests

**Deliverables**:
- `openrecall/client/chat/routes.py`
- Update `openrecall/client/web/app.py`
- `tests/test_chat_routes.py`

**Validation**:
```bash
# Start client web server
./run_client.sh --debug

# Test stream endpoint
curl -X POST http://localhost:8883/chat/api/stream \
  -H "Content-Type: application/json" \
  -d '{"conversation_id":"test","message":"hello"}' \
  --no-buffer

# Test list conversations
curl http://localhost:8883/chat/api/conversations

# Test create conversation
curl -X POST http://localhost:8883/chat/api/conversations

# Test new session
curl -X POST http://localhost:8883/chat/api/new-session
```

---

### Task 2.6: Integration Tests

**File**: `tests/test_chat_integration.py`

**Estimated effort**: Medium

**Steps**:

1. Create test fixtures
   - Mock Pi subprocess for unit-like tests
   - Real Pi for integration tests (marked)

2. Test conversation CRUD
   - Create, load, save, delete, list

3. Test Pi RPC manager
   - Start/stop lifecycle
   - Prompt sending and response handling
   - New session

4. Test chat service
   - Stream response flow
   - Error handling
   - Auto-restart on crash

5. Test SSE endpoints
   - Stream endpoint returns events
   - Conversation endpoints work

6. Test with real Pi (marked `@pytest.mark.integration`)
   - Requires running Edge server
   - Requires API key
   - Tests actual LLM responses

**Deliverables**:
- `tests/test_chat_integration.py`

**Validation**:
```bash
# Start Edge server
./run_server.sh --debug

# Run all chat tests
pytest tests/test_chat*.py -v

# Run only integration tests (requires API key)
export MINIMAX_CN_API_KEY=your_key
pytest tests/test_chat_integration.py -v -m integration
```

---

## Implementation Order

```
Task 2.1 (Types) ──────────────────────┐
                                       │
Task 2.2 (Conversation) ◄── depends ───┤
                                       │
Task 2.3 (Pi RPC) ◄── depends ─────────┤
                                       │
                                       └──► Task 2.4 (Chat Service) ──► Task 2.5 (Routes)
                                                   │
                                                   └──► Task 2.6 (Integration Tests)
```

**Parallel opportunities**:
- Task 2.1 must complete first (foundation types)
- Tasks 2.2 and 2.3 can run in parallel after 2.1
- Task 2.4 depends on 2.1, 2.2, 2.3
- Task 2.5 depends on 2.4
- Task 2.6 runs after all others

## Timeline

| Task | Dependencies | Parallel? | Estimated Effort |
|------|--------------|-----------|------------------|
| 2.1 Types | None | No (foundation) | Small |
| 2.2 Conversation | 2.1 | Yes (with 2.3) | Medium |
| 2.3 Pi RPC | 2.1 | Yes (with 2.2) | Large |
| 2.4 Chat Service | 2.1, 2.2, 2.3 | No | Large |
| 2.5 Routes | 2.4 | No | Medium |
| 2.6 Integration | 2.5 | No | Medium |

**Suggested order**:
1. Day 1: Task 2.1 (Types) - foundation for all others
2. Day 2-3: Tasks 2.2 and 2.3 in parallel
3. Day 4-5: Task 2.4 (Chat Service)
4. Day 6: Task 2.5 (Routes)
5. Day 7: Task 2.6 (Integration Tests)

## File Checklist

```
openrecall/client/chat/
├── __init__.py              [✅] Exists (Phase 1)
├── pi_manager.py            [✅] Exists (Phase 1)
├── config_manager.py        [✅] Exists (Phase 1)
├── models.py                [✅] Exists (Phase 1)
├── types.py                 [ ] Create (Task 2.1)
├── conversation.py          [ ] Create (Task 2.2)
├── pi_rpc.py                [ ] Create (Task 2.3)
├── service.py               [ ] Create (Task 2.4)
├── routes.py                [ ] Create (Task 2.5)
└── skills/
    └── myrecall-search/
        └── SKILL.md         [✅] Exists (Phase 1)

openrecall/client/web/
└── app.py                   [ ] Update to register chat blueprint

tests/
├── test_chat_pi_manager.py      [✅] Exists (Phase 1)
├── test_chat_config_manager.py  [✅] Exists (Phase 1)
├── test_chat_pi_integration.py  [✅] Exists (Phase 1)
├── test_chat_types.py           [ ] Create (Task 2.1)
├── test_chat_conversation.py    [ ] Create (Task 2.2)
├── test_chat_pi_rpc.py          [ ] Create (Task 2.3)
├── test_chat_service.py         [ ] Create (Task 2.4)
├── test_chat_routes.py          [ ] Create (Task 2.5)
└── test_chat_integration.py     [ ] Create (Task 2.6)

~/MRC/
├── chats/                       [ ] Created at runtime
└── chat-workspace/              [ ] Created at runtime
    └── .pi/
        └── sessions/            [ ] Created by Pi
```

## Definition of Done

- [ ] All files created and implemented
- [ ] Unit tests pass: `pytest tests/test_chat*.py -v -m "not integration"`
- [ ] Integration tests pass: `pytest tests/test_chat_integration.py -v -m integration`
- [ ] `curl` can POST to `/chat/api/stream` and receive SSE events
- [ ] Pi process starts automatically on first message
- [ ] Pi process restarts on crash (with backoff)
- [ ] Conversation files are created in `~/MRC/chats/`
- [ ] Conversation listing returns results sorted by updated_at DESC
- [ ] `POST /chat/api/new-session` resets Pi context
- [ ] Error cases return meaningful JSON errors
- [ ] SSE connection handles keepalive and timeout
- [ ] Pi process is killed on service shutdown

## Open Questions

> See `docs/superpowers/plans/2026-03-26-phase2-core-service.md` for resolved open questions.

## Notes

### SSE Event Format

Pi events are passed through directly:

```
event: message_update
data: {"type":"message_update","assistantMessageEvent":{"type":"text_delta","delta":"Hello"}}

event: tool_execution_start
data: {"type":"tool_execution_start","toolCallId":"xxx","toolName":"bash","args":{}}

event: agent_end
data: {"type":"agent_end"}
```

**Keepalive**: Send SSE comment lines (`: keepalive\n\n`) every 15 seconds to prevent connection timeout.

### Error Event Format

```json
{
  "type": "error",
  "message": "Human-readable error message",
  "code": "PI_CRASH" | "TIMEOUT" | "API_ERROR" | "INTERNAL_ERROR"
}
```

### Pi RPC Command Format

```json
// Prompt
{"type": "prompt", "id": "req-uuid", "content": "user message", "images": ["base64..."]}

// New session (reset context)
{"type": "new_session"}

// Abort current operation
{"type": "abort"}
```

### Process Management

Following screenpipe's approach:
- Use process groups on Unix (`setsid()`) for clean termination
- On Windows, use `CREATE_NO_WINDOW` flag
- Kill entire process group on stop to catch child processes

## References

- **Phase 2 Spec**: `docs/v3/chat/phase2-core-service/spec.md`
- **Phase 1 Plan**: `docs/v3/chat/phase1-foundation/plan.md`
- **MyRecall MVP**: `docs/v3/chat/mvp.md`
- **MyRecall Overview**: `docs/v3/chat/overview.md`
- **Screenpipe Pi RPC**: `_ref/screenpipe/apps/screenpipe-app-tauri/src-tauri/src/pi.rs`
- **Screenpipe Event Handler**: `_ref/screenpipe/apps/screenpipe-app-tauri/lib/pi-event-handler.ts`
- **Screenpipe Chat Storage**: `_ref/screenpipe/apps/screenpipe-app-tauri/lib/chat-storage.ts`
- **Pi Session Format**: `_ref/pi-mono/packages/coding-agent/docs/session.md`

## Change History

| Date | Change |
|------|--------|
| 2026-03-26 | Initial plan created |
| 2026-03-26 | Added SSE keepalive specification, streamlined Open Questions |
| 2026-03-26 | Fixed task dependency diagram: Tasks 2.2 and 2.3 depend on 2.1, not fully parallel |
| 2026-03-26 | 文档一致性修正：SSE 端点描述统一为 `/chat/api/stream` |
| 2026-03-26 | Phase 2 验收完成，所有验收标准通过 |
