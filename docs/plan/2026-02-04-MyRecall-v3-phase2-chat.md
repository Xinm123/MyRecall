# Phase 2 (Chat + Unified Search) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 引入 Chat MVP（tool-call 思路 + 强约束）与统一检索入口 `/api/v3/search`，让“总结/问答”成为 MyRecall 的一等能力。

**Architecture:** Chat 不直接塞库；通过内部 tool `search_content(args)` 调用 v3 search（或直接调 SearchEngine），并对上下文做限额/截断/超时。回答必须给出 citations（timestamp + image_url）。

**Tech Stack:** Flask、现有 SearchEngine（混合检索 + rerank）、OpenAI-compatible SDK/HTTP（取决于 provider）、vanilla JS UI

## Scope
- In:
  - `/api/v3/search`（filters 显式化：start/end/app/window/limit/mode）
  - `/api/v3/chat`（非 streaming MVP）
  - Chat UI 页面（最小可用）
  - tool-call 的强约束（必须）
- Out:
  - streaming（SSE/WS）
  - 多模态（audio/ui events）

## Sources of Truth
- SearchEngine：`MyRecall/openrecall/server/search/engine.py`
- QueryParser：`MyRecall/openrecall/server/utils/query_parser.py`
- screenpipe chat 思路参考：`screenpipe/docs/dataflow-pipeline.zh-en.md`（Chat 章节）

---

### Task 1: `/api/v3/search`（统一入口 + 显式 filters 优先）

**Files:**
- Modify: `MyRecall/openrecall/server/api_v3.py`
- Modify: `MyRecall/openrecall/server/search/engine.py`
- Test: `MyRecall/tests/test_api_v3_search_filters.py`

**规则**
- 若 query 里给了 `start_time/end_time`：优先使用，不再依赖 QueryParser 的 today/yesterday
- `limit` 上限（建议 200）
- 返回字段至少包含：timestamp/app/window/caption/scene/action/score/image_url

---

### Task 2: Chat 配置（provider/model/env）

**Files:**
- Modify: `MyRecall/openrecall/shared/config.py`

**新增 env（建议）**
- `OPENRECALL_CHAT_PROVIDER`（默认 openai）
- `OPENRECALL_CHAT_MODEL_NAME`
- `OPENRECALL_CHAT_API_KEY`
- `OPENRECALL_CHAT_API_BASE`
- （可选）`OPENRECALL_CHAT_TIMEOUT_SECONDS`

---

### Task 3: `/api/v3/chat`（tool-call + 强约束截断/限额/超时）

**Files:**
- Create: `MyRecall/openrecall/server/chat/agent.py`
- Modify: `MyRecall/openrecall/server/api_v3.py`
- Test: `MyRecall/tests/test_api_v3_chat_limits.py`

**硬约束（建议写死常量）**
- `SEARCH_LIMIT_CAP=10`
- `ITEM_TEXT_CAP=300`
- `TOTAL_TEXT_CAP=4000`
- `TOOL_CALL_ROUNDS_CAP=3`
- `TOOL_TIMEOUT_SECONDS=30`

**返回结构（MVP）**
- `message: {role:"assistant", content:"..."}`
- `citations: [{timestamp, app_name, window_title, image_url}]`
- （debug）`tool_trace`

---

### Task 4: Chat UI（最小可用）

**Files:**
- Modify: `MyRecall/openrecall/server/app.py`
- Create: `MyRecall/openrecall/server/templates/chat.html`
- (Optional) Modify: `MyRecall/openrecall/server/templates/layout.html`

**行为**
- 维护前端 messages（无状态 server）
- 发送到 `/api/v3/chat`
- 展示 citations（点击打开图片或跳 `/timeline-v3#ts=...`）

---

### Task 5: 文档同步（Chat 的“受控工具调用”原则）

**Files:**
- Modify: `MyRecall/docs/plan/2026-02-04-MyRecall-v3-metrics.md`（限额/预算口径必须一致）

