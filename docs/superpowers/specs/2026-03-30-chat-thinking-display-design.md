# Chat Thinking Display — Design Spec

**Date:** 2026-03-30
**Status:** Approved

## Problem Statement

When using GLM-4.7-Flash.30b_Q8_0.gguf via the custom LLM extension, the chat interface displays thinking content and answer content without visual distinction. Both appear merged in the same text bubble.

## Root Cause Analysis

The current `myrecall-llm-extension.ts` implements a custom `streamSimple` that handles LLM responses. However, it routes ALL `reasoning_content` output (including both thinking process and final answer) as `text_delta`, because the GLM model uses `reasoning_content` field for the thinking phase and `content` field for the answer phase — but the plugin doesn't detect this transition.

Pi-agent's built-in OpenAI-completions provider (`openai-completions.js`) already correctly handles this transition:
1. When `reasoning_content` appears → emit `thinking_delta`
2. When `content` first appears → emit `thinking_end` then `text_start` + `text_delta`

**Key test findings:**
```
GGUF model (GLM-4.7-Flash.30b_q8_0.gguf) output pattern:
  Phase 1: delta.reasoning_content → structured thinking (7 steps)
  Phase 2: delta.content → final answer
  → pi-agent native code correctly separates these
```

## Solution Overview

Simplify the plugin to delegate all LLM streaming to pi-agent's native provider, while keeping the plugin's only job: override the zai provider's baseUrl and inject MyRecall API system prompt.

**Architecture:**
```
Before:
  GLM GGUF → plugin streamSimple (buggy) → frontend

After:
  GLM GGUF → pi-agent native OpenAI-completions → thinking/text events → frontend
  Plugin just overrides baseUrl + injects system prompt
```

## Detailed Changes

### 1. Plugin Simplification — `myrecall-llm-extension.ts`

**Before:** ~480 lines implementing full `streamSimple`
**After:** ~30 lines

```typescript
import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { readFileSync, existsSync } from "fs";
import { join } from "path";

const CONFIG_PATH = join(process.env.HOME || "", ".pi", "agent", "myrecall-llm.json");

interface LlmConfig {
  baseUrl?: string;
  apiKey?: string;
}

function loadConfig(): LlmConfig {
  try {
    if (existsSync(CONFIG_PATH)) {
      return JSON.parse(readFileSync(CONFIG_PATH, "utf-8"));
    }
  } catch { /* ignore */ }
  return {};
}

const MYRECALL_SYSTEM_ADDITION = `

You are answering questions about the user's screen activity history via MyRecall API.
IMPORTANT API ENDPOINTS (always use bash tool with curl):
  GET http://10.77.3.162:8083/v1/activity-summary?start_time=ISO&end_time=ISO
  GET http://10.77.3.162:8083/v1/search?q=keyword&start_time=ISO&end_time=ISO&limit=10
  GET http://10.77.3.162:8083/v1/frames/{id}/context
NEVER use /query, /api/query, /search, or paths not starting with /v1/
`;

export default function (pi: ExtensionAPI) {
  const config = loadConfig();

  if (!config.baseUrl) {
    console.warn("[myrecall-llm] No baseUrl in ~/.pi/agent/myrecall-llm.json — skipping");
    return;
  }

  // Override zai provider baseUrl to point to our server
  // This keeps all built-in GLM model configs (reasoning: true, thinkingFormat: "zai", etc.)
  pi.registerProvider("zai", {
    baseUrl: config.baseUrl.endsWith("/") ? config.baseUrl.slice(0, -1) : config.baseUrl,
  });

  // Inject MyRecall API instructions into system prompt for zai provider
  pi.on("before_agent_start", async (event, ctx) => {
    if (ctx.model?.provider === "zai") {
      return { systemPrompt: event.systemPrompt + MYRECALL_SYSTEM_ADDITION };
    }
  });

  console.log(`[myrecall-llm] Registered zai provider -> ${config.baseUrl}`);
}
```

**Key points:**
- `registerProvider("zai", { baseUrl })` overrides only the baseUrl of built-in zai models
- All model metadata (context window, max tokens, cost, `reasoning: true`, `thinkingFormat: "zai"`) preserved
- Pi-agent's native `streamOpenAICompletions` handles `reasoning_content` → `content` transition automatically
- `before_agent_start` injects system prompt only for zai provider (other providers unaffected)

### 2. Pi RPC Manager — `openrecall/client/chat/pi_rpc.py`

**Changes to `start()` method:**

```python
# Provider handling
effective_provider = provider
if provider == "custom":
    from .config_manager import get_chat_api_base, get_api_key
    api_base = get_chat_api_base()
    api_key = get_api_key("custom")
    if api_base:
        # Write config (already done)
        config_path = Path.home() / ".pi" / "agent" / "myrecall-llm.json"
        config_path.parent.mkdir(parents=True, exist_ok=True)
        config_data = {"baseUrl": api_base}
        if api_key:
            config_data["apiKey"] = api_key
        config_path.write_text(json.dumps(config_data))
        config_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
        # Use zai provider (model config from built-in registry, baseUrl from plugin)
        effective_provider = "zai"
        # No more --tools flag (RPC mode defaults to no tools)
        # No more -e extension flag (plugin registration happens via file loading)
```

**Command construction:**
```python
cmd = [
    "bun", "run", pi_path,
    "--mode", "rpc",
    "--provider", "zai",           # Use built-in zai provider
    "--model", model,              # e.g., "glm-4.7-flash" (from config_manager)
    "--workspace", str(self.workspace_dir),
]
# Plugin auto-loaded via ~/.pi/agent/ or explicit -e
```

**Extension loading:** The plugin is loaded automatically by pi-agent from the `.pi/agent/myrecall-llm-extension.ts` file location (configured in pi_rpc.py startup).

### 3. Model Configuration — `openrecall/client/chat/config_manager.py`

**Add zai provider models:**

```python
PROVIDER_MODELS = {
    "zai": ["glm-4.7-flash"],  # Only model available on server
    "qianfan": [...],           # Unchanged
    ...
}
```

The `glm-4.7-flash` model in pi-agent's registry maps to `zai` provider with:
- `reasoning: true`
- `thinkingFormat: "zai"` → translates to `enable_thinking` in request

### 4. Backend Accumulation — `openrecall/client/chat/service.py`

**Accumulate thinking content alongside text:**

In `stream_response()`:

```python
assistant_content = ""
assistant_thinking = ""  # NEW

while True:
    ...
    if event.get("type") == "message_update":
        msg_evt = event.get("assistantMessageEvent", {})
        if msg_evt.get("type") == "text_delta":
            assistant_content += msg_evt.get("delta", "")
        elif msg_evt.get("type") == "thinking_delta":  # NEW
            assistant_thinking += msg_evt.get("delta", "")

    elif event.get("type") == "agent_end":
        add_message(
            conv,
            role="assistant",
            content=assistant_content,
            tool_calls=tool_calls or None,
            # thinking=assistant_thinking if assistant_thinking else None,
        )
        self.save_conversation(conv)
```

**Note:** Thinking content is NOT saved to conversation history (only displayed in current streaming message). Only the final answer is persisted.

### 5. Frontend Display — `openrecall/client/web/templates/chat.html`

**Data model addition:**
```javascript
currentAssistantMsg: {
  id: 'msg-1',
  role: 'assistant',
  rawContent: '',
  content: '',
  thinking: '',           // NEW: accumulated thinking text
  thinkingExpanded: false,  // NEW: fold state
  toolCalls: [],
}
```

**Streaming event handling:**
```javascript
handleStreamEvent(eventType, payload) {
  const evt = payload.assistantMessageEvent;

  if (evt?.type === "thinking_start") {
    this.currentAssistantMsg.thinking = "";
    this.currentAssistantMsg.thinkingExpanded = false;
  }
  else if (evt?.type === "thinking_delta") {
    this.currentAssistantMsg.thinking += evt.delta ?? "";
  }
  else if (evt?.type === "thinking_end") {
    // thinking block closed, do nothing extra
  }
  else if (evt?.type === "text_delta") {
    this.currentAssistantMsg.rawContent += evt.delta ?? "";
    this.currentAssistantMsg.content = marked.parse(this.currentAssistantMsg.rawContent);
    this.scrollToBottom();
  }
  // ... tool events unchanged
}
```

**Template (in assistant bubble, before markdown content):**
```html
<!-- Thinking section — only shown if there's thinking content -->
<template x-if="msg.thinking && msg.thinking.length > 0">
  <div class="thinking-section">
    <div class="thinking-collapsed"
         x-show="!msg.thinkingExpanded"
         @click="msg.thinkingExpanded = !msg.thinkingExpanded">
      💭 思考过程 (<span x-text="msg.thinking.length"></span> 字) ▶
    </div>
    <div class="thinking-expanded"
         x-show="msg.thinkingExpanded">
      <div class="thinking-header" @click="msg.thinkingExpanded = !msg.thinkingExpanded">
        💭 思考过程 (<span x-text="msg.thinking.length"></span> 字) ▼
      </div>
      <pre class="thinking-content" x-text="msg.thinking"></pre>
    </div>
  </div>
</template>

<!-- For streaming message -->
<template x-if="currentAssistantMsg && currentAssistantMsg.thinking && currentAssistantMsg.thinking.length > 0">
  <div class="thinking-section">
    <div class="thinking-collapsed"
         x-show="!currentAssistantMsg.thinkingExpanded"
         @click="currentAssistantMsg.thinkingExpanded = !currentAssistantMsg.thinkingExpanded">
      💭 思考过程 (<span x-text="currentAssistantMsg.thinking.length"></span> 字) ▶
    </div>
    <div class="thinking-expanded"
         x-show="currentAssistantMsg.thinkingExpanded">
      <div class="thinking-header" @click="currentAssistantMsg.thinkingExpanded = !currentAssistantMsg.thinkingExpanded">
        💭 思考过程 (<span x-text="currentAssistantMsg.thinking.length"></span> 字) ▼
      </div>
      <pre class="thinking-content" x-text="currentAssistantMsg.thinking"></pre>
    </div>
  </div>
</template>
```

**CSS (in `<style>` block):**
```css
.thinking-section {
  margin-bottom: 10px;
}

.thinking-collapsed {
  cursor: pointer;
  color: #999;
  font-size: 12px;
  padding: 4px 8px;
  border-radius: 4px;
  user-select: none;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.thinking-collapsed:hover {
  background: rgba(0, 0, 0, 0.04);
  color: #666;
}

.thinking-expanded {
  background: #F5F5F7;
  border-radius: 8px;
  padding: 10px 14px;
  margin-bottom: 10px;
}

.thinking-header {
  cursor: pointer;
  color: #888;
  font-size: 12px;
  margin-bottom: 6px;
  display: flex;
  align-items: center;
  gap: 4px;
  user-select: none;
}

.thinking-header:hover {
  color: #666;
}

.thinking-content {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  font-size: 13px;
  color: #555;
  line-height: 1.5;
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0;
  max-height: 400px;
  overflow-y: auto;
}
```

## Files Modified

| File | Change |
|------|--------|
| `myrecall-llm-extension.ts` | Replace `streamSimple` (~480 lines) with `registerProvider` + `before_agent_start` (~30 lines) |
| `openrecall/client/chat/pi_rpc.py` | Change `--provider myrecall-local` to `--provider zai`, `--model auto` to `--model glm-4.7-flash` |
| `openrecall/client/chat/config_manager.py` | Add `zai` provider with `glm-4.7-flash` model |
| `openrecall/client/chat/service.py` | Accumulate `thinking_delta` events, pass thinking content to assistant message |
| `openrecall/client/web/templates/chat.html` | Add thinking fold UI and CSS |

## Testing Plan

1. Start server + client, open chat page
2. Select zai/glm-4.7-flash model
3. Send a question that triggers LLM thinking
4. Verify: thinking block appears (collapsed by default)
5. Click to expand, verify thinking content is shown
6. Verify answer renders separately below/beside thinking
7. Verify qianfan provider still works normally
8. Verify conversation history saves only answer (not thinking)
9. Verify streaming: thinking and answer appear in correct order
