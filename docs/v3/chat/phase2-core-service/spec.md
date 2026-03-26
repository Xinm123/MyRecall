# Phase 2: Core Service - Specification

## Overview

Phase 2 implements the Chat Service backend logic for MyRecall v3, enabling users to have natural language conversations about their screen activity using the Pi coding agent.

## Goals

1. Implement Pi RPC mode integration for long-running agent sessions
2. Build SSE streaming endpoint for real-time chat responses
3. Manage conversations with file-based storage
4. Provide a working backend that can be tested via curl

## Non-Goals

- Web UI implementation (Phase 3)
- Advanced conversation features like @mentions (Phase 4)
- Multi-session support (MVP uses single "chat" session)
- Historical message sync to Pi context

## Design Decisions

### Decision 1: Pi Process Lifecycle

| Choice | Rationale |
|--------|-----------|
| **RPC Mode** | Long-running process with stdin/stdout JSON communication |
| **Single Session** | Fixed `session_id="chat"` for MVP simplicity |
| **Auto-start** | Pi starts on first message if not running |
| **Auto-restart** | Pi restarts on crash with exponential backoff |

**Alignment**: Matches screenpipe's approach exactly.

### Decision 2: Conversation vs Session Mapping

| Aspect | Decision |
|--------|----------|
| Mapping | N:1 (multiple conversations share one Pi session) |
| Session ID | Fixed: `"chat"` |
| Workspace | Fixed: `~/MRC/chat-workspace/` |
| Conversation Storage | Separate: `~/MRC/chats/*.json` (UI layer only) |
| History Sync | Not synced to Pi context - each conversation starts fresh |

**Alignment**: Matches screenpipe's approach exactly.

When switching conversations:
1. UI loads conversation history from JSON file
2. Call `piNewSession` to reset Pi context
3. Pi starts with blank context for the new conversation

### Decision 3: SSE Event Format

| Choice | Rationale |
|--------|-----------|
| **Passthrough** | Directly forward Pi's raw JSON events to frontend |
| **No Transformation** | Reduces backend complexity, frontend handles parsing |

**Alignment**: Matches screenpipe's approach exactly.

### Decision 4: System Prompt Injection

| Content | Source | MVP Status |
|---------|--------|------------|
| API URL | Skill file (`SKILL.md`) | Hardcoded |
| API Usage Docs | Skill file | Full documentation |
| User Custom Prompt | Config | Phase 4 |
| Dynamic Content (time) | N/A | Use `date` command via bash tool |

**MVP Decision**: No `--append-system-prompt` injection. Rely entirely on skill file.

**Alignment**: Matches screenpipe's approach (skill file is primary knowledge source).

## Components

### 1. Pi RPC Manager

**File**: `openrecall/client/chat/pi_rpc.py`

**Responsibilities**:
- Manage Pi subprocess lifecycle (start, stop, restart)
- Communicate via stdin/stdout JSON RPC protocol
- Handle command queue with request IDs
- Emit events via callback mechanism

**Key Functions**:

```python
class PiRpcManager:
    def __init__(self, workspace_dir: Path, event_callback: Callable[[dict], None]):
        """Initialize with workspace directory and event callback."""

    async def start(self, provider: str, model: str) -> bool:
        """Start Pi process in RPC mode."""

    async def stop(self) -> None:
        """Stop Pi process gracefully."""

    async def send_prompt(self, content: str, images: list[str] | None = None) -> str:
        """Send prompt, return request_id."""

    async def new_session(self) -> None:
        """Reset Pi session (clear context)."""

    async def abort(self) -> None:
        """Abort current operation."""

    def is_running(self) -> bool:
        """Check if Pi process is alive."""
```

**RPC Protocol**:

Request format (stdin):
```json
{"type": "prompt", "id": "req-uuid", "content": "user message", "images": [...]}
{"type": "new_session"}
{"type": "abort"}
```

Response format (stdout, JSONL):
```json
{"type": "message_update", "assistantMessageEvent": {"type": "text_delta", "delta": "Hello"}}
{"type": "tool_execution_start", "toolCallId": "call-123", "toolName": "bash", "args": {...}}
{"type": "tool_execution_end", "toolCallId": "call-123", "result": {...}}
{"type": "agent_end"}
{"type": "response", "success": true}
```

### 2. Chat Service

**File**: `openrecall/client/chat/service.py`

**Responsibilities**:
- Coordinate Pi RPC Manager
- Handle SSE streaming
- Manage conversation persistence
- Error handling and recovery

**Key Functions**:

```python
class ChatService:
    def __init__(self, data_dir: Path):
        """Initialize with data directory."""

    async def stream_response(
        self,
        conversation_id: str,
        message: str,
        images: list[str] | None = None
    ) -> AsyncGenerator[dict, None]:
        """Stream response via SSE events."""

    async def ensure_pi_running(self) -> None:
        """Start Pi if not running."""

    async def switch_conversation(self, conversation_id: str) -> None:
        """Switch to different conversation (resets Pi context)."""

    def get_pi_status(self) -> PiStatus:
        """Get Pi process status."""
```

### 3. Conversation Manager

**File**: `openrecall/client/chat/conversation.py`

**Responsibilities**:
- CRUD operations for conversations
- File-based JSON storage
- Title generation from first message

**Data Model**:

```python
@dataclass
class Conversation:
    id: str
    title: str
    messages: list[Message]
    created_at: datetime
    updated_at: datetime

@dataclass
class Message:
    role: str  # "user" | "assistant"
    content: str
    tool_calls: list[ToolCall] | None
    created_at: datetime

@dataclass
class ToolCall:
    id: str
    name: str
    args: dict
    status: str  # "running" | "done" | "error"
    result: str | None
```

**Key Functions**:

```python
def create_conversation() -> Conversation:
    """Create new conversation with UUID."""

def load_conversation(conversation_id: str) -> Conversation | None:
    """Load conversation from JSON file."""

def save_conversation(conversation: Conversation) -> None:
    """Save conversation to JSON file."""

def list_conversations() -> list[ConversationMeta]:
    """List all conversations sorted by updated_at DESC."""

def delete_conversation(conversation_id: str) -> bool:
    """Delete conversation file."""
```

### 4. SSE Endpoint

**File**: `openrecall/client/chat/routes.py`

**Endpoints**:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/chat/api/stream` | POST (SSE) | Stream chat response |
| `/chat/api/conversations` | GET | List conversations |
| `/chat/api/conversations/{id}` | GET | Get conversation |
| `/chat/api/conversations/{id}` | DELETE | Delete conversation |
| `/chat/api/conversations` | POST | Create new conversation |
| `/chat/api/new-session` | POST | Reset Pi session |

**Stream Endpoint**:

```python
@blueprint.route("/api/stream", methods=["POST"])
async def stream():
    """
    Request:
        {
            "conversation_id": "uuid",
            "message": "user message",
            "images": ["base64..."]  // optional
        }

    Response (SSE):
        event: message_update
        data: {"type":"message_update",...}

        event: agent_end
        data: {"type":"agent_end"}
    """
```

## Directory Structure

```
openrecall/client/chat/
├── __init__.py
├── service.py           # ChatService - main orchestrator
├── pi_rpc.py            # PiRpcManager - subprocess communication
├── conversation.py      # Conversation CRUD
├── routes.py            # Flask routes for /chat/api/*
└── types.py             # Data classes (Conversation, Message, ToolCall)

~/MRC/
├── chats/               # Conversation JSON files
│   ├── conv-uuid-1.json
│   └── conv-uuid-2.json
└── chat-workspace/      # Pi workspace (fixed)
    └── .pi/
        └── sessions/    # Pi-managed session files
```

## Process Flow

### Stream Response Flow

```
POST /chat/api/stream
    │
    ├─► Validate request
    │
    ├─► Ensure Pi running
    │       └─► If not, start Pi with provider/model
    │
    ├─► Save user message to conversation
    │
    ├─► Send prompt to Pi
    │       └─► stdin: {"type":"prompt","id":"xxx","content":"..."}
    │
    ├─► Read Pi stdout (JSONL stream)
    │       │
    │       ├─► Parse each JSON line
    │       │
    │       ├─► Yield SSE event
    │       │
    │       └─► Accumulate assistant response
    │
    ├─► On agent_end:
    │       ├─► Save assistant message to conversation
    │       └─► Close SSE connection
    │
    └─► On error:
            ├─► Yield error event
            └─► Close SSE connection
```

### Switch Conversation Flow

```
User clicks different conversation in UI
    │
    ├─► POST /chat/api/new-session
    │
    ├─► Send {"type":"new_session"} to Pi stdin
    │
    └─► Pi context cleared, ready for new conversation
```

## Error Handling

| Error | Recovery |
|-------|----------|
| Pi not installed | Return error with installation instructions |
| Pi crash | Auto-restart with exponential backoff (max 3 retries) |
| Pi timeout | Abort and return timeout error |
| LLM API error | Forward error message to user |
| File I/O error | Log and return generic error |

## Acceptance Criteria

- [ ] `curl` can POST to `/chat/api/stream` and receive SSE events
- [ ] Pi process starts automatically on first message
- [ ] Conversation files are created and updated correctly
- [ ] Tool calls are displayed in the event stream
- [ ] `piNewSession` correctly resets Pi context
- [ ] Pi process is killed on service shutdown
- [ ] Error cases return meaningful error messages

## Dependencies

- **Phase 1**: Pi installation, skill file
- **bun**: JavaScript runtime (user-installed)
- **Edge Server**: Running on `localhost:8083` for API calls

## References

- **Screenpipe Pi RPC**: `_ref/screenpipe/apps/screenpipe-app-tauri/src-tauri/src/pi.rs`
- **Screenpipe Event Handler**: `_ref/screenpipe/apps/screenpipe-app-tauri/lib/pi-event-handler.ts`
- **Pi Session Format**: `_ref/pi-mono/packages/coding-agent/docs/session.md`
- **Pi README**: `_ref/pi-mono/packages/coding-agent/README.md`

## Risks

| Risk | Mitigation |
|------|------------|
| Pi RPC protocol changes | Pin Pi version, test before upgrade |
| Stdout buffer overflow | Use async reading with backpressure |
| Process orphan on crash | Use process groups, cleanup on startup |
| SSE connection timeout | Send keepalive events |
| Concurrent prompt requests | Queue prompts, reject when busy |

## Change History

| Date | Change |
|------|--------|
| 2026-03-26 | Initial spec created based on design discussion |
