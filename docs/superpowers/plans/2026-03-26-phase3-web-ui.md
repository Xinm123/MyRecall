# Phase 3: Web UI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the `/chat` page with sidebar + main chat area, SSE streaming, Markdown rendering, inline collapsible Tool Calls, and navigation integration.

**Architecture:** Jinja2 template + Alpine.js (inline in template). SSE via fetch+ReadableStream. Markdown via marked.js CDN. All state managed by Alpine.js reactive data.

**Tech Stack:** Python (Flask), Jinja2 templates, Alpine.js (CDN), marked.js (CDN), CSS (inline or inline-block).

---

## Component Map

```
openrecall/client/web/
├── templates/
│   ├── layout.html          [Modify] Add Chat nav link
│   └── chat.html            [Create] Main chat page
└── app.py                   [Modify] Add /chat route

tests/
└── test_chat_ui.py         [Create] Template rendering tests
```

---

## Task 1: Add `/chat` Route

**Files:**
- Modify: `openrecall/client/web/app.py:27-29`

- [ ] **Step 1: Add /chat route to app.py**

Modify `openrecall/client/web/app.py` — add after the `/timeline` route:

```python
@client_app.route("/chat")
def chat():
    return render_template("chat.html")
```

- [ ] **Step 2: Add Chat to current view detection**

Modify the JavaScript section at the bottom of `layout.html` (around line 603-610) — add `/chat` detection:

```javascript
const currentPath = window.location.pathname;
let currentView = 'grid'; // default
if (currentPath === '/timeline') {
  currentView = 'timeline';
} else if (currentPath === '/search') {
  currentView = 'search';
} else if (currentPath === '/chat') {
  currentView = 'chat';
}
document.documentElement.setAttribute('data-current-view', currentView);
```

- [ ] **Step 3: Add Chat highlight CSS**

Modify `layout.html` — add after the existing `html[data-current-view="search"]` rule:

```css
html[data-current-view="chat"] a[href="/chat"] {
  background-color: rgba(0, 0, 0, 0.12);
  color: #1D1D1F;
}
```

- [ ] **Step 4: Add Chat nav link**

Modify `layout.html` — in the toolbar-icons-container (around line 416-422), add Chat link:

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

- [ ] **Step 5: Check if icon_chat() exists**

Run: `grep -n "def icon_chat\|def icon_" openrecall/client/web/templates/icons.html`
If it doesn't exist, add to `icons.html`:

```html
{% macro icon_chat() %}
<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
</svg>
{% endmacro %}
```

- [ ] **Step 6: Test route**

Run: `python -c "from openrecall.client.web.app import client_app; print([r.rule for r in client_app.url_map.iter_rules()])"`
Expected: `/chat` is listed

- [ ] **Step 7: Commit**

```bash
git add openrecall/client/web/app.py openrecall/client/web/templates/layout.html openrecall/client/web/templates/icons.html
git commit -m "feat(chat): add /chat route and navigation integration"
```

---

## Task 2: Create chat.html Template — Skeleton + Sidebar

**Files:**
- Create: `openrecall/client/web/templates/chat.html`

- [ ] **Step 1: Create the template file**

Create `openrecall/client/web/templates/chat.html`:

```html
{% extends "layout.html" %}

{% block title %}Chat — MyRecall{% endblock %}

{% block extra_head %}
<style>
  /* === Chat Page Layout === */
  .chat-layout {
    display: flex;
    height: calc(100vh - 52px);
    overflow: hidden;
  }

  /* === Sidebar === */
  .chat-sidebar {
    width: 280px;
    min-width: 280px;
    background: var(--bg-card);
    border-right: 1px solid var(--border-color);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }

  .chat-sidebar-header {
    padding: 16px;
    border-bottom: 1px solid var(--border-color);
  }

  .chat-sidebar-header h2 {
    font-size: 16px;
    font-weight: 600;
    margin: 0;
  }

  .new-chat-btn {
    width: 100%;
    padding: 10px 16px;
    margin-top: 12px;
    background: var(--accent-color);
    color: white;
    border: none;
    border-radius: 8px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    transition: background-color 0.2s;
  }

  .new-chat-btn:hover {
    background-color: #005bb5;
  }

  .conversation-list {
    flex: 1;
    overflow-y: auto;
    padding: 8px;
  }

  .conversation-item {
    display: flex;
    align-items: center;
    padding: 10px 12px;
    border-radius: 8px;
    cursor: pointer;
    transition: background-color 0.15s;
    margin-bottom: 2px;
    position: relative;
  }

  .conversation-item:hover {
    background-color: rgba(0, 0, 0, 0.05);
  }

  .conversation-item.active {
    background-color: rgba(0, 122, 255, 0.1);
  }

  .conversation-item-info {
    flex: 1;
    min-width: 0;
  }

  .conversation-item-title {
    font-size: 14px;
    font-weight: 500;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 160px;
  }

  .conversation-item-time {
    font-size: 12px;
    color: var(--text-secondary);
    margin-top: 2px;
  }

  .conversation-delete-btn {
    opacity: 0;
    background: none;
    border: none;
    padding: 4px;
    cursor: pointer;
    color: var(--text-secondary);
    border-radius: 4px;
    transition: opacity 0.15s;
  }

  .conversation-item:hover .conversation-delete-btn {
    opacity: 1;
  }

  .conversation-delete-btn:hover {
    background-color: rgba(255, 59, 48, 0.1);
    color: #ff3b30;
  }

  /* === Main Chat Area === */
  .chat-main {
    flex: 1;
    display: flex;
    flex-direction: column;
    overflow: hidden;
    background: var(--bg-body);
  }

  .chat-messages {
    flex: 1;
    overflow-y: auto;
    padding: 24px;
    display: flex;
    flex-direction: column;
    gap: 16px;
  }

  .chat-welcome {
    text-align: center;
    padding: 48px 24px;
    color: var(--text-secondary);
  }

  .chat-welcome h3 {
    font-size: 24px;
    font-weight: 600;
    color: var(--text-primary);
    margin: 0 0 8px 0;
  }

  .chat-welcome p {
    font-size: 14px;
    margin: 0;
  }

  /* === Input Area === */
  .chat-input-area {
    padding: 16px 24px 24px;
    background: var(--bg-body);
  }

  .chat-input-container {
    display: flex;
    gap: 12px;
    align-items: flex-end;
    max-width: 800px;
    margin: 0 auto;
  }

  .chat-input {
    flex: 1;
    padding: 12px 16px;
    border: 1px solid var(--border-color);
    border-radius: 12px;
    font-size: 14px;
    font-family: var(--font-stack);
    background: var(--bg-card);
    color: var(--text-primary);
    resize: none;
    min-height: 48px;
    max-height: 200px;
    line-height: 1.5;
    overflow-y: auto;
  }

  .chat-input:focus {
    outline: none;
    border-color: var(--accent-color);
  }

  .chat-input:disabled {
    opacity: 0.6;
    cursor: not-allowed;
  }

  .chat-send-btn {
    padding: 12px 20px;
    background: var(--accent-color);
    color: white;
    border: none;
    border-radius: 12px;
    font-size: 14px;
    font-weight: 500;
    cursor: pointer;
    transition: background-color 0.2s;
    white-space: nowrap;
  }

  .chat-send-btn:hover:not(:disabled) {
    background-color: #005bb5;
  }

  .chat-send-btn:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }

  /* === Mobile === */
  @media (max-width: 768px) {
    .chat-sidebar {
      position: fixed;
      left: 0;
      top: 52px;
      height: calc(100vh - 52px);
      z-index: 500;
      transform: translateX(-100%);
      transition: transform 0.3s;
      box-shadow: 2px 0 8px rgba(0, 0, 0, 0.1);
    }

    .chat-sidebar.open {
      transform: translateX(0);
    }

    .mobile-chat-toggle {
      display: flex;
    }
  }

  @media (min-width: 769px) {
    .mobile-chat-toggle {
      display: none;
    }
  }
</style>
{% endblock %}

{% block content %}
<div class="chat-layout" x-data="chatApp()">
  <!-- Sidebar Toggle (mobile) -->
  <button @click="sidebarOpen = !sidebarOpen" class="mobile-chat-toggle toolbar-icon-link" style="position:fixed;bottom:24px;right:24px;z-index:600;width:48px;height:48px;border-radius:50%;background:var(--accent-color);color:white;box-shadow:0 4px 12px rgba(0,0,0,0.2);" title="Toggle sidebar">
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/></svg>
  </button>

  <!-- Sidebar -->
  <aside class="chat-sidebar" :class="{ 'open': sidebarOpen }">
    <div class="chat-sidebar-header">
      <h2>Conversations</h2>
      <button @click="createNewChat()" class="new-chat-btn">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        New Chat
      </button>
    </div>
    <div class="conversation-list">
      <template x-for="conv in conversations" :key="conv.id">
        <div class="conversation-item"
             :class="{ 'active': conv.id === currentConvId }"
             @click="selectConversation(conv.id)">
          <div class="conversation-item-info">
            <div class="conversation-item-title" x-text="conv.title || 'New conversation'"></div>
            <div class="conversation-item-time" x-text="formatRelativeTime(conv.updated_at)"></div>
          </div>
          <button class="conversation-delete-btn"
                  @click.stop="deleteConversation(conv.id)"
                  title="Delete">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
      </template>
    </div>
  </aside>

  <!-- Main Chat Area -->
  <main class="chat-main">
    <div class="chat-messages" id="chat-messages">
      <!-- Welcome state (no conversation selected) -->
      <template x-if="messages.length === 0 && !currentConvId">
        <div class="chat-welcome">
          <h3>MyRecall Chat</h3>
          <p>Ask questions about your recent screen activity</p>
        </div>
      </template>

      <!-- Messages -->
      <template x-for="msg in messages" :key="msg.id">
        <div class="chat-message-row" :class="msg.role">
          <!-- User message -->
          <div class="message-bubble user-bubble" x-show="msg.role === 'user'">
            <div class="message-content" x-html="msg.content"></div>
          </div>

          <!-- Assistant message -->
          <div class="message-bubble assistant-bubble" x-show="msg.role === 'assistant'">
            <!-- Markdown content -->
            <div class="message-content markdown-body" x-html="msg.content"></div>

            <!-- Tool Calls -->
            <template x-if="msg.toolCalls && msg.toolCalls.length > 0">
              <div class="tool-calls-container">
                <template x-for="tc in msg.toolCalls" :key="tc.id">
                  <div class="tool-call-item" :class="'tool-' + tc.status">
                    <div class="tool-call-summary" @click="tc.expanded = !tc.expanded">
                      <span class="tool-call-icon" x-text="getToolIcon(tc.status)"></span>
                      <span class="tool-call-name" x-text="tc.name"></span>
                      <span class="tool-call-args-preview" x-text="getToolArgsPreview(tc.args)"></span>
                      <svg class="tool-call-chevron" :class="{ 'expanded': tc.expanded }" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
                    </div>
                    <div class="tool-call-detail" x-show="tc.expanded">
                      <div class="tool-call-args">
                        <div class="tool-call-section-label">Arguments:</div>
                        <pre class="tool-call-code" x-text="JSON.stringify(tc.args, null, 2)"></pre>
                      </div>
                      <template x-if="tc.result">
                        <div class="tool-call-result">
                          <div class="tool-call-section-label">Result:</div>
                          <pre class="tool-call-code" x-text="truncateResult(tc.result)"></pre>
                        </div>
                      </template>
                    </div>
                  </div>
                </template>
              </div>
            </template>
          </div>
        </div>
      </template>

      <!-- Loading indicator -->
      <div class="message-bubble assistant-bubble" x-show="isStreaming && !currentAssistantId">
        <div class="message-content">
          <span class="loading-dots">正在思考<span>.</span><span>.</span><span>.</span></span>
        </div>
      </div>

      <!-- Current streaming assistant message -->
      <template x-if="currentAssistantMsg">
        <div class="message-bubble assistant-bubble">
          <div class="message-content markdown-body" x-html="currentAssistantMsg.content"></div>
          <template x-if="currentAssistantMsg.toolCalls && currentAssistantMsg.toolCalls.length > 0">
            <div class="tool-calls-container">
              <template x-for="tc in currentAssistantMsg.toolCalls" :key="tc.id">
                <div class="tool-call-item" :class="'tool-' + tc.status">
                  <div class="tool-call-summary" @click="tc.expanded = !tc.expanded">
                    <span class="tool-call-icon" x-text="getToolIcon(tc.status)"></span>
                    <span class="tool-call-name" x-text="tc.name"></span>
                    <span class="tool-call-args-preview" x-text="getToolArgsPreview(tc.args)"></span>
                    <svg class="tool-call-chevron" :class="{ 'expanded': tc.expanded }" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"/></svg>
                  </div>
                  <div class="tool-call-detail" x-show="tc.expanded">
                    <div class="tool-call-args">
                      <div class="tool-call-section-label">Arguments:</div>
                      <pre class="tool-call-code" x-text="JSON.stringify(tc.args, null, 2)"></pre>
                    </div>
                    <template x-if="tc.result">
                      <div class="tool-call-result">
                        <div class="tool-call-section-label">Result:</div>
                        <pre class="tool-call-code" x-text="truncateResult(tc.result)"></pre>
                      </div>
                    </template>
                  </div>
                </div>
              </template>
            </div>
          </template>
        </div>
      </template>
    </div>

    <!-- Input Area -->
    <div class="chat-input-area">
      <div class="chat-input-container">
        <textarea
          class="chat-input"
          x-model="inputText"
          @keydown.enter.prevent="handleEnter"
          :disabled="isStreaming"
          placeholder="Ask about your screen activity..."
          rows="1"
        ></textarea>
        <button
          class="chat-send-btn"
          @click="sendMessage()"
          :disabled="!inputText.trim() || isStreaming"
        >Send</button>
      </div>
    </div>
  </main>
</div>
{% endblock %}
```

- [ ] **Step 2: Add message bubble and tool call styles**

Add to the `<style>` block in `chat.html` (append after the existing styles):

```css
  /* === Message Bubbles === */
  .message-bubble {
    max-width: 700px;
    padding: 12px 16px;
    border-radius: 16px;
    line-height: 1.6;
    font-size: 14px;
  }

  .chat-message-row.user {
    display: flex;
    justify-content: flex-end;
  }

  .chat-message-row.assistant {
    display: flex;
    justify-content: flex-start;
  }

  .user-bubble {
    background: var(--accent-color);
    color: white;
    border-bottom-right-radius: 4px;
  }

  .assistant-bubble {
    background: var(--bg-card);
    color: var(--text-primary);
    border-bottom-left-radius: 4px;
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
  }

  /* Markdown in assistant messages */
  .markdown-body {
    font-size: 14px;
    line-height: 1.6;
  }

  .markdown-body p {
    margin: 0 0 8px 0;
  }

  .markdown-body p:last-child {
    margin-bottom: 0;
  }

  .markdown-body code {
    padding: 2px 5px;
    background: rgba(0, 0, 0, 0.06);
    border-radius: 4px;
    font-family: 'SF Mono', Monaco, 'Courier New', monospace;
    font-size: 13px;
  }

  .markdown-body pre {
    background: rgba(0, 0, 0, 0.06);
    border-radius: 8px;
    padding: 12px;
    overflow-x: auto;
    margin: 8px 0;
  }

  .markdown-body pre code {
    padding: 0;
    background: none;
  }

  .markdown-body ul, .markdown-body ol {
    margin: 8px 0;
    padding-left: 24px;
  }

  .markdown-body strong {
    font-weight: 600;
  }

  .markdown-body a {
    color: var(--accent-color);
  }

  /* === Loading Animation === */
  .loading-dots span {
    animation: blink 1.4s infinite both;
  }

  .loading-dots span:nth-child(2) {
    animation-delay: 0.2s;
  }

  .loading-dots span:nth-child(3) {
    animation-delay: 0.4s;
  }

  @keyframes blink {
    0%, 80%, 100% { opacity: 0; }
    40% { opacity: 1; }
  }

  /* === Tool Calls === */
  .tool-calls-container {
    margin-top: 12px;
    border-top: 1px solid var(--border-color);
    padding-top: 8px;
  }

  .tool-call-item {
    margin-top: 8px;
  }

  .tool-call-summary {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 6px 8px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
    transition: background-color 0.15s;
  }

  .tool-call-summary:hover {
    background: rgba(0, 0, 0, 0.05);
  }

  .tool-call-icon {
    font-size: 14px;
  }

  .tool-call-name {
    font-weight: 500;
    color: var(--text-primary);
  }

  .tool-call-args-preview {
    color: var(--text-secondary);
    font-size: 12px;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    max-width: 200px;
  }

  .tool-call-chevron {
    margin-left: auto;
    transition: transform 0.2s;
    color: var(--text-secondary);
  }

  .tool-call-chevron.expanded {
    transform: rotate(180deg);
  }

  .tool-call-detail {
    padding: 8px 8px 8px 24px;
  }

  .tool-call-section-label {
    font-size: 11px;
    font-weight: 600;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 4px;
  }

  .tool-call-code {
    font-family: 'SF Mono', Monaco, 'Courier New', monospace;
    font-size: 12px;
    white-space: pre-wrap;
    word-break: break-all;
    margin: 0;
    background: rgba(0, 0, 0, 0.04);
    padding: 8px;
    border-radius: 6px;
  }

  .tool-call-args {
    margin-bottom: 8px;
  }

  /* Tool call status colors */
  .tool-running .tool-call-icon {
    animation: spin 1s linear infinite;
  }

  .tool-error .tool-call-summary {
    color: #ff3b30;
  }

  @keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
  }

  /* === Error Card === */
  .error-card {
    background: rgba(255, 59, 48, 0.08);
    border: 1px solid rgba(255, 59, 48, 0.3);
    border-radius: 8px;
    padding: 10px 14px;
    font-size: 13px;
    color: #ff3b30;
    margin-top: 8px;
  }

  .error-card.busy {
    background: rgba(255, 149, 0, 0.08);
    border-color: rgba(255, 149, 0, 0.3);
    color: #ff9500;
  }

  .error-card.timeout {
    background: rgba(255, 149, 0, 0.08);
    border-color: rgba(255, 149, 0, 0.3);
    color: #ff9500;
  }
```

- [ ] **Step 3: Add Alpine.js chatApp() function and marked.js CDN**

Add before `{% endblock %}` in `{% block content %}`:

```html
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script>
  function chatApp() {
    return {
      // State
      conversations: [],
      messages: [],           // Committed messages
      currentConvId: null,
      inputText: '',
      isStreaming: false,
      sidebarOpen: false,
      currentAssistantMsg: null,  // In-progress streaming message
      streamReader: null,         // SSE fetch reader for cancellation

      // Helpers
      _msgIdCounter: 0,
      nextId() { return 'msg-' + (++this._msgIdCounter); },

      init() {
        // Load conversations
        this.loadConversations();
        // Auto-select first conversation if any
        this.$watch('conversations', () => {
          if (!this.currentConvId && this.conversations.length > 0) {
            this.selectConversation(this.conversations[0].id);
          }
        });
        // Cleanup on page leave
        window.addEventListener('beforeunload', () => {
          if (this.streamReader) this.streamReader.cancel();
        });
      },

      // --- Conversations ---
      async loadConversations() {
        try {
          const resp = await fetch('/chat/api/conversations');
          const data = await resp.json();
          this.conversations = data.conversations;
        } catch (e) {
          console.error('Failed to load conversations:', e);
        }
      },

      async createNewChat() {
        try {
          const resp = await fetch('/chat/api/conversations', { method: 'POST' });
          const conv = await resp.json();
          this.conversations.unshift(conv);
          this.selectConversation(conv.id);
          this.sidebarOpen = false;
        } catch (e) {
          console.error('Failed to create conversation:', e);
        }
      },

      async selectConversation(id) {
        // Cancel any ongoing stream
        if (this.streamReader) {
          this.streamReader.cancel();
          this.streamReader = null;
          this.isStreaming = false;
        }
        this.currentConvId = id;
        this.messages = [];
        this.currentAssistantMsg = null;
        this.sidebarOpen = false;

        try {
          const resp = await fetch(`/chat/api/conversations/${id}`);
          if (resp.status === 200) {
            const conv = await resp.json();
            // Render pre-existing messages
            for (const m of conv.messages || []) {
              this.messages.push({
                id: this.nextId(),
                role: m.role,
                rawContent: m.content,
                content: m.role === 'assistant' ? marked.parse(m.content) : this.escapeHtml(m.content),
                toolCalls: m.tool_calls ? m.tool_calls.map(tc => ({ ...tc, expanded: false })) : [],
              });
            }
          }
        } catch (e) {
          console.error('Failed to load conversation:', e);
        }

        // Reset Pi context
        try {
          await fetch('/chat/api/new-session', { method: 'POST' });
        } catch (e) {
          // Non-fatal
        }

        this.scrollToBottom();
      },

      async deleteConversation(id) {
        if (!confirm('Delete this conversation?')) return;
        try {
          await fetch(`/chat/api/conversations/${id}`, { method: 'DELETE' });
          this.conversations = this.conversations.filter(c => c.id !== id);
          if (this.currentConvId === id) {
            this.currentConvId = null;
            this.messages = [];
            if (this.conversations.length > 0) {
              this.selectConversation(this.conversations[0].id);
            }
          }
        } catch (e) {
          console.error('Failed to delete conversation:', e);
        }
      },

      // --- Sending ---
      handleEnter(e) {
        if (e.shiftKey) return; // Shift+Enter = newline
        this.sendMessage();
      },

      async sendMessage() {
        const text = this.inputText.trim();
        if (!text || this.isStreaming) return;

        // Ensure we have a conversation
        if (!this.currentConvId) {
          await this.createNewChat();
        }

        const convId = this.currentConvId;

        // Add user message
        this.messages.push({
          id: this.nextId(),
          role: 'user',
          content: this.escapeHtml(text),
          toolCalls: [],
        });

        this.inputText = '';
        this.isStreaming = true;
        this.currentAssistantMsg = {
          id: this.nextId(),
          role: 'assistant',
          rawContent: '',
          content: '',
          toolCalls: [],
        };

        this.scrollToBottom();

        try {
          await this.streamChat(convId, text);
        } catch (e) {
          console.error('Stream error:', e);
        } finally {
          this.isStreaming = false;
          this.streamReader = null;
        }
      },

      async streamChat(convId, message) {
        const response = await fetch('/chat/api/stream', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ conversation_id: convId, message }),
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        this.streamReader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';
        let pendingEventType = 'message';

        try {
          while (true) {
            const { done, value } = await this.streamReader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop();

            for (const line of lines) {
              if (line.startsWith('event: ')) {
                pendingEventType = line.slice(7).trim();
              } else if (line.startsWith('data: ')) {
                const data = line.slice(6);
                if (!data) continue;
                const payload = JSON.parse(data);
                this.handleStreamEvent(pendingEventType, payload);
              }
            }
          }
        } finally {
          this.streamReader = null;
        }
      },

      handleStreamEvent(eventType, payload) {
        if (eventType === 'keepalive') return;

        if (eventType === 'message_update' || eventType === 'message') {
          const delta = payload.assistantMessageEvent?.delta ?? '';
          if (!delta) return;
          this.currentAssistantMsg.rawContent += delta;
          this.currentAssistantMsg.content = marked.parse(this.currentAssistantMsg.rawContent);
          this.scrollToBottom();
        }

        if (eventType === 'tool_execution_start') {
          this.currentAssistantMsg.toolCalls.push({
            id: payload.toolCallId,
            name: payload.toolName,
            args: payload.args || {},
            status: 'running',
            result: null,
            expanded: false,
          });
        }

        if (eventType === 'tool_execution_end') {
          const tc = this.currentAssistantMsg.toolCalls.find(t => t.id === payload.toolCallId);
          if (tc) {
            tc.status = payload.isError ? 'error' : 'done';
            // Extract result text from payload.result
            if (payload.result) {
              if (typeof payload.result === 'string') {
                tc.result = payload.result;
              } else if (payload.result.content) {
                tc.result = payload.result.content.map(c => c.text || '').join('\n');
              }
            }
          }
        }

        if (eventType === 'agent_end') {
          // Finalize the streaming message
          this.messages.push({ ...this.currentAssistantMsg });
          this.currentAssistantMsg = null;
          this.scrollToBottom();
        }

        if (eventType === 'error') {
          this.currentAssistantMsg = null;
          this.isStreaming = false;
          const msg = this.getErrorMessage(payload);
          this.messages.push({
            id: this.nextId(),
            role: 'assistant',
            content: `<div class="error-card ${payload.code?.toLowerCase()}">${msg}</div>`,
            toolCalls: [],
          });
          this.scrollToBottom();
        }
      },

      // --- Helpers ---
      escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
      },

      getToolIcon(status) {
        if (status === 'running') return '⏳';
        if (status === 'error') return '❌';
        return '✅';
      },

      getToolArgsPreview(args) {
        if (!args || typeof args !== 'object') return '';
        const keys = Object.keys(args);
        if (keys.length === 0) return '';
        const first = args[keys[0]];
        if (typeof first === 'string') {
          const val = first.length > 30 ? first.slice(0, 30) + '…' : first;
          return `${keys[0]}: ${val}`;
        }
        return keys.slice(0, 2).join(', ');
      },

      truncateResult(result) {
        if (!result) return '';
        const str = typeof result === 'string' ? result : JSON.stringify(result);
        return str.length > 500 ? str.slice(0, 500) + '\n… (truncated)' : str;
      },

      getErrorMessage(payload) {
        const messages = {
          BUSY: 'Another request is in progress.',
          PI_CRASH: 'Pi agent crashed. Retrying…',
          TIMEOUT: 'Response timed out.',
          API_ERROR: payload.message || 'API error.',
          INTERNAL_ERROR: 'Something went wrong.',
        };
        return messages[payload.code] || payload.message || 'Unknown error.';
      },

      scrollToBottom() {
        this.$nextTick(() => {
          const el = document.getElementById('chat-messages');
          if (el) el.scrollTop = el.scrollHeight;
        });
      },

      formatRelativeTime(isoString) {
        if (!isoString) return '';
        const date = new Date(isoString);
        const now = new Date();
        const diff = (now - date) / 1000;
        if (diff < 60) return 'just now';
        if (diff < 3600) return Math.floor(diff / 60) + 'm ago';
        if (diff < 86400) return Math.floor(diff / 3600) + 'h ago';
        if (diff < 604800) return Math.floor(diff / 86400) + 'd ago';
        return date.toLocaleDateString();
      },
    };
  }
</script>
```

- [ ] **Step 4: Verify template renders**

Run: `python -c "from openrecall.client.web.app import client_app; rv = client_app.test_client().get('/chat'); print(rv.status_code, len(rv.data))"`
Expected: `200 <large number>` (page renders without errors)

- [ ] **Step 5: Commit**

```bash
git add openrecall/client/web/templates/chat.html
git commit -m "feat(chat): create chat.html template with sidebar, SSE streaming, tool calls"
```

---

## Task 3: Write Basic UI Tests

**Files:**
- Create: `tests/test_chat_ui.py`

- [ ] **Step 1: Write the test file**

```python
"""Tests for Chat UI page rendering."""
import pytest


@pytest.fixture
def client():
    """Create test client."""
    from openrecall.client.web.app import client_app as app
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestChatPage:
    def test_chat_page_renders(self, client):
        """GET /chat returns 200 and contains chat layout."""
        resp = client.get("/chat")
        assert resp.status_code == 200
        data = resp.data.decode("utf-8")
        assert "chat-layout" in data
        assert "chat-sidebar" in data
        assert "chat-main" in data
        assert "conversation-list" in data

    def test_chat_page_has_input_area(self, client):
        """Chat page has a message input area."""
        resp = client.get("/chat")
        assert resp.status_code == 200
        data = resp.data.decode("utf-8")
        assert 'class="chat-input"' in data
        assert 'class="chat-send-btn"' in data

    def test_chat_page_has_alpine_app(self, client):
        """Chat page initializes Alpine.js chatApp."""
        resp = client.get("/chat")
        data = resp.data.decode("utf-8")
        assert "chatApp()" in data
        assert "x-data" in data
        assert "conversations" in data

    def test_chat_page_has_marked_js(self, client):
        """Chat page loads marked.js from CDN."""
        resp = client.get("/chat")
        data = resp.data.decode("utf-8")
        assert "marked" in data

    def test_chat_page_has_tool_call_styles(self, client):
        """Chat page includes tool call styling."""
        resp = client.get("/chat")
        data = resp.data.decode("utf-8")
        assert "tool-call" in data
        assert "tool-calls-container" in data

    def test_chat_page_has_error_card_styles(self, client):
        """Chat page includes error card styling."""
        resp = client.get("/chat")
        data = resp.data.decode("utf-8")
        assert "error-card" in data
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_chat_ui.py -v`
Expected: All 6 tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_chat_ui.py
git commit -m "test(chat): add Phase 3 UI rendering tests"
```

---

## Task 4: Navigation Integration — Verify and Fix

**Files:**
- Modify: `openrecall/client/web/templates/layout.html`

- [ ] **Step 1: Verify Chat nav link appears in layout**

Run: `grep -n "chat" openrecall/client/web/templates/layout.html`
Expected: Chat href and CSS rules are present

- [ ] **Step 2: Verify current view detection**

Run: `grep -n "chat" openrecall/client/web/app.py`
Expected: `/chat` route is registered

- [ ] **Step 3: Commit if not already done**

---

## Definition of Done

- [ ] `curl http://localhost:8883/chat` returns 200 with chat HTML
- [ ] Sidebar shows conversation list
- [ ] New Chat button creates a conversation
- [ ] Sending a message triggers SSE stream
- [ ] Assistant responses stream with Markdown rendering
- [ ] Tool Calls appear inline and are collapsible
- [ ] Error events show inline error cards
- [ ] Header has working Chat navigation link with active highlight
- [ ] All `pytest tests/test_chat_ui.py` pass
- [ ] All `pytest tests/test_chat*.py -v -m "not integration"` pass

---

## Implementation Order

```
Task 1 (Route + Nav) ──► Task 2 (chat.html template)
                                    │
                                    └──► Task 3 (UI tests)
                                             │
                                             └──► Task 4 (Verify nav)
```

---

## References

- **Spec**: `docs/superpowers/specs/2026-03-26-chat-phase3-web-ui-design.md`
- **Phase 2 Plan**: `docs/superpowers/plans/2026-03-26-phase2-core-service.md`
- **Phase 2 Spec**: `docs/v3/chat/phase2-core-service/spec.md`
- **Layout Template**: `openrecall/client/web/templates/layout.html`
- **Chat Routes**: `openrecall/client/chat/routes.py`
- **Screenpipe Standalone Chat**: `_ref/screenpipe/apps/screenpipe-app-tauri/components/standalone-chat.tsx`
- **Screenpipe Pi Event Handler**: `_ref/screenpipe/apps/screenpipe-app-tauri/lib/pi-event-handler.ts`
