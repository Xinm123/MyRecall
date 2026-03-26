# Phase 3: Web UI — Chat Interface Design

**Date:** 2026-03-26
**Status:** Approved
**Phase:** 3 of 4 (Chat Feature)

## Overview

Phase 3 implements the user-facing chat interface for MyRecall v3, building the `/chat` page and integrating it into the existing Web UI. The chat interface allows users to have natural language conversations about their screen activity, powered by the Pi coding agent with SSE streaming responses.

## Design Decisions

### Decision 1: Layout — Sidebar + Main Chat Area

| Choice | Decision |
|--------|----------|
| Layout | Left sidebar (conversation list) + Right main area (messages + input) |
| Pattern | ChatGPT/Claude-style classic chat layout |
| Sidebar width | Fixed ~280px, collapsible on mobile |
| Message area | Full-height scrollable area |

**Rationale:** Provides natural conversation management with history access. Matches established chat UX patterns. Enables quick switching between conversations.

### Decision 2: Navigation Entry Point

| Choice | Decision |
|--------|----------|
| Entry | Header navigation link "Chat" next to Grid/Search/Timeline |
| URL | `http://localhost:8883/chat` |
| Layout | Reuses existing `layout.html` base template |

**Rationale:** Consistent with existing UI. Users can discover chat from the main navigation.

### Decision 3: Markdown Rendering

| Choice | Decision |
|--------|----------|
| Library | marked.js (CDN) |
| Flavor | GFM (GitHub Flavored Markdown) |
| Implementation | `marked.parse()` on assistant message content before rendering |

**Rationale:** Lightweight, already CDN-available. GFM covers code blocks, tables, task lists needed for technical responses.

### Decision 4: SSE Event Handling

| Choice | Decision |
|--------|----------|
| Framework | Alpine.js (embedded in chat.html template) |
| SSE Client | Native `EventSource` API |
| State Management | Alpine.js reactive data (`messages`, `isStreaming`) |

**Rationale:** Consistent with existing MyRecall frontend pattern. All existing pages use Alpine.js. No build step needed.

### Decision 5: Tool Call Display

| Choice | Decision |
|--------|----------|
| Layout | Inline collapsible within assistant message |
| Default State | Collapsed (shows summary only) |
| Trigger | Click to expand/collapse |
| Summary Format | `{status_icon} {tool_name} {args_summary}` |
| Expanded Content | Full JSON args + result |
| Status Icons | `⏳` (running) / `✅` (done) / `❌` (error) |

**Rationale:** Keeps tool calls visible but unobtrusive. Inline placement maintains conversation flow. Collapsed by default avoids overwhelming the user.

### Decision 6: Input Behavior

| Choice | Decision |
|--------|----------|
| Input Field | Multi-line textarea, auto-resize |
| Send Trigger | Enter key (Shift+Enter for newline) |
| Post-Send | Clear input field |
| During Stream | Disable input until response completes |

**Rationale:** Standard chat UX. Multi-line support for detailed queries. Disabled input prevents double-sends.

### Decision 7: Loading State

| Choice | Decision |
|--------|----------|
| Indicator | "正在思考..." animated message bubble |
| Timing | Shown immediately after user sends, before first response event |
| Placement | In message flow as assistant bubble |

**Rationale:** Provides immediate feedback that the request was sent. Message appears instantly, content fills in as SSE events arrive.

### Decision 8: Error Display

| Choice | Decision |
|--------|----------|
| Format | Inline error card in message area |
| Style | Red/amber styling, dismissible |
| Content | Error type + brief description |
| Recovery | User can continue after seeing error |

**Rationale:** Non-blocking. Error is part of conversation history. User can retry or continue naturally.

## Page Structure

### URL
`http://localhost:8883/chat`

### Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│  Header (reused from layout.html)                                  │
│  [Grid] [Search] [Timeline] [Chat]                                  │
├──────────────────┬──────────────────────────────────────────────────┤
│  Sidebar         │  Main Chat Area                                 │
│  280px fixed     │                                                  │
│                  │  ┌────────────────────────────────────────┐    │
│  [+ New Chat]     │  │ Welcome message / conversation title    │    │
│                  │  └────────────────────────────────────────┘    │
│  Conversation 1  │                                                  │
│  Conversation 2  │  ┌────────────────────────────────────────┐    │
│  Conversation 3  │  │ [User message bubble]                  │    │
│  ...             │  └────────────────────────────────────────┘    │
│                  │                                                  │
│                  │  ┌────────────────────────────────────────┐    │
│                  │  │ [Assistant message bubble]             │    │
│                  │  │   ├── Markdown content (marked.js)     │    │
│                  │  │   └── Tool Calls (inline collapsible)  │    │
│                  │  └────────────────────────────────────────┘    │
│                  │                                                  │
│                  │  ┌────────────────────────────────────────┐    │
│                  │  │ [Loading: "正在思考..."]               │    │
│                  │  └────────────────────────────────────────┘    │
│                  │                                                  │
│                  ├──────────────────────────────────────────────────┤
│                  │  [Textarea input]                    [Send]     │
└──────────────────┴──────────────────────────────────────────────────┘
```

### Sidebar

- **New Chat button:** `POST /chat/api/conversations` → creates new conversation, selects it
- **Conversation list:** `GET /chat/api/conversations` → sorted by `updated_at DESC`
  - Each item: title (truncated to 30 chars), relative timestamp, delete icon
  - Click: loads conversation, calls `POST /chat/api/new-session` to reset Pi context
  - Active conversation: highlighted background
- **Conversation switch during streaming:** If a stream is active, clicking a different conversation should cancel the stream (abort the fetch ReadableStream reader) before switching. The frontend cancels via `reader.cancel()` and sets `isStreaming = false`.
- **Delete:** `DELETE /chat/api/conversations/{id}` with confirmation

### Message Display

**User messages:**
- Right-aligned bubble, light background
- User icon (simple SVG or text avatar)
- Content: plain text (no Markdown needed for user input)

**Assistant messages:**
- Left-aligned bubble, slightly different background
- Pi icon (simple SVG)
- Content: Markdown rendered via `marked.parse()`
- Tool Calls: inline collapsible sections within the bubble

**Loading state:**
- Left-aligned bubble with animated "..." or spinner
- Text: "正在思考..."
- Replaced by actual response when SSE events arrive

### Tool Call Inline Collapsible

```
✅ Read myrecall/config.py
  ▼ [click to expand]

Arguments:
{
  "path": "/Users/pyw/myrecall/config.py",
  "start_line": 1,
  "end_line": 50
}

Result:
# MyRecall Configuration
OPENRECALL_PORT=8083
...
```

- **Collapsed:** `{icon} {tool_name} {args_preview}`
- **Expanded:** Full JSON args + result (truncated at 500 chars with `...` suffix)
- **Toggle:** Click anywhere on the summary row

**Result truncation:** If `result.length > 500`, show first 500 chars + `\n... (truncated)`.

**Error code display:**

| Code | Display | Message |
|------|---------|---------|
| `BUSY` | Yellow card | "Another request is in progress." |
| `PI_CRASH` | Red card | "Pi crashed. Retrying..." |
| `TIMEOUT` | Orange card | "Response timed out." |
| `API_ERROR` | Red card | "{message}" |
| `INTERNAL_ERROR` | Red card | "Something went wrong." |

**Mobile sidebar:** Hamburger icon (☰) in header when viewport < 768px. Sidebar overlays content. Close on click outside or conversation selection.

### Input Area

- **Textarea:** Auto-growing height (max ~200px), placeholder "Ask about your screen activity..."
- **Send button:** Right side, disabled when empty or streaming
- **Keyboard:** Enter sends, Shift+Enter inserts newline
- **Disabled state:** During streaming, input is greyed out

## API Integration

### Endpoints Used

| Operation | Method | Endpoint | Description |
|-----------|--------|----------|-------------|
| List conversations | GET | `/chat/api/conversations` | Load sidebar list |
| Create conversation | POST | `/chat/api/conversations` | New chat |
| Get conversation | GET | `/chat/api/conversations/{id}` | Load message history |
| Delete conversation | DELETE | `/chat/api/conversations/{id}` | Remove from sidebar |
| Switch conversation | POST | `/chat/api/new-session` | Reset Pi context |
| Stream response | POST | `/chat/api/stream` | SSE streaming chat |
| Get Pi status | GET | `/chat/api/pi-status` | Show Pi running state |

### SSE Event Handling

> **Note:** Browser `EventSource` does not support POST requests. Use `fetch()` with `ReadableStream` for SSE over POST.

```javascript
// SSE stream handler using fetch + ReadableStream
// SSE format: lines like "event: message_update\ndata: {...}\n\n"
async function streamChat(conversationId, message) {
  const response = await fetch('/chat/api/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ conversation_id: conversationId, message })
    // Note: images field reserved for Phase 4 (screenshot attachment): { images: ["base64..."] }
  });

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let pendingEventType = 'message'; // default event type

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop(); // keep incomplete line in buffer

    for (const line of lines) {
      if (line.startsWith('event: ')) {
        // Track the event type for the next data: line
        pendingEventType = line.slice(7).trim();
      } else if (line.startsWith('data: ')) {
        const data = line.slice(6);
        if (!data) continue;
        const payload = JSON.parse(data);
        handleEvent(pendingEventType, payload);
      }
      // Ignore comment lines (": keepalive") and empty lines
    }
  }
}

// SSE event types from backend
// event: message_update  →  payload: {type, assistantMessageEvent: {type, delta}}
// event: tool_execution_start  →  payload: {type, toolCallId, toolName, args}
// event: tool_execution_end  →  payload: {type, toolCallId, result, isError}
// event: agent_end  →  payload: {type}
// event: error  →  payload: {type, message, code}

function handleEvent(eventType, payload) {
  if (eventType === 'message_update' || eventType === 'message') {
    // payload.assistantMessageEvent.delta contains the incremental text
    const delta = payload.assistantMessageEvent?.delta ?? '';
    // Accumulate delta into current assistant message's rawContent
  }

  if (eventType === 'tool_execution_start') {
    // payload.toolCallId, payload.toolName, payload.args
  }

  if (eventType === 'tool_execution_end') {
    // Update tool call status: payload.isError ? 'error' : 'done'
    // payload.result contains the result content
  }

  if (eventType === 'agent_end') {
    // Finalize message: apply marked.parse() to rawContent, enable input
  }

  if (eventType === 'error') {
    // payload.code: 'BUSY' | 'PI_CRASH' | 'TIMEOUT' | 'API_ERROR' | 'INTERNAL_ERROR'
    // Display error card with appropriate messaging
  }
}

// Cleanup: close reader and abort on page leave
window.addEventListener('beforeunload', () => reader.cancel());
```

### Message Object Shape (Alpine.js)

```javascript
{
  id: 'uuid',
  role: 'user' | 'assistant',
  rawContent: 'string',        // Original content (never modified after set)
  content: 'string',           // Rendered HTML (Markdown → HTML for assistant, plain for user)
  toolCalls: [
    {
      id: 'string',
      name: 'string',
      args: {},
      status: 'running' | 'done' | 'error',
      result: 'string' | null,
      expanded: false          // UI state for collapse
    }
  ],
}
```

**Content population rules:**
- **User messages:** `content = rawContent` (plain text, no Markdown)
- **New assistant messages (streaming):** accumulate `delta` into `rawContent` during SSE stream; apply `marked.parse(rawContent)` incrementally on each `message_update` event (marked.parse is idempotent — safe to call repeatedly); finalize by pushing to `messages` array on `agent_end`
- **Loaded from API:** `GET /chat/api/conversations/{id}` returns messages with raw content; apply `marked.parse()` to each assistant message's `content` field before adding to `messages` array

## File Deliverables

### New Files

| File | Description |
|------|-------------|
| `openrecall/client/web/templates/chat.html` | Main chat page template |
| `tests/test_chat_ui.py` | Basic UI rendering tests (optional Phase 3.5) |

### Modified Files

| File | Change |
|------|--------|
| `openrecall/client/web/templates/layout.html` | Add "Chat" nav link to header |
| `openrecall/client/web/app.py` | Already registers `chat_bp` (Phase 2) |

### Static Assets (CDN)

- marked.js: `https://cdn.jsdelivr.net/npm/marked/marked.min.js`

## Navigation Integration

In `layout.html`, add Chat to the toolbar-icons-container (next to the existing Grid and Timeline links):

```html
<div class="toolbar-icons-container">
  <a href="/" class="toolbar-icon-link" title="Grid View">
    {{ icons.icon_grid() }}
  </a>
  <a href="/timeline" class="toolbar-icon-link" title="Timeline View">
    {{ icons.icon_timeline() }}
  </a>
  <a href="/chat" class="toolbar-icon-link" title="Chat">
    {{ icons.icon_chat() }}
  </a>
</div>
```

Also add `icon_chat()` to `icons.html` and add the chat highlight CSS rule:
```css
html[data-current-view="chat"] a[href="/chat"] {
  background-color: rgba(0, 0, 0, 0.12);
  color: #1D1D1F;
}
```

## Acceptance Criteria

- [ ] `/chat` renders with sidebar + main chat area
- [ ] Sidebar shows conversation list from API
- [ ] New Chat button creates and selects a conversation
- [ ] Sending a message triggers SSE stream
- [ ] Assistant responses stream word-by-word
- [ ] Markdown content renders correctly (code blocks, bold, lists)
- [ ] Tool Calls appear inline and are collapsible
- [ ] Tool Call status icons show correctly (⏳/✅/❌)
- [ ] Loading state ("正在思考...") appears during stream
- [ ] Input clears after sending
- [ ] Input is disabled during streaming
- [ ] Error events show inline error cards with correct type-specific styling
- [ ] Clicking a conversation loads its history with Markdown rendered
- [ ] Switching conversations resets Pi context
- [ ] Deleting a conversation removes it from sidebar
- [ ] Header has working Chat navigation link
- [ ] Page works on mobile (hamburger → sidebar overlay)
- [ ] SSE connection is cleaned up on page navigation (beforeunload)

## Change History

| Date | Change |
|------|--------|
| 2026-03-26 | Initial design created |
| 2026-03-26 | Fix: SSE uses fetch+ReadableStream instead of EventSource POST; clarify event structure |
| 2026-03-26 | Fix: add Markdown rendering for pre-loaded messages; clarify rawContent/content rules |
| 2026-03-26 | Fix: add missing GET /chat/api/pi-status endpoint to table |
| 2026-03-26 | Fix: add error code display table, mobile sidebar guidance, SSE cleanup |
