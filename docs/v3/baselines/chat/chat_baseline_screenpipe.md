# Screenpipe Chat 事实基线核查

- 版本：v1.1
- 日期：2026-03-02
- 适用范围：Chat 功能架构评审，为 MyRecall-v3 Chat 对齐/不对齐分析提供 screenpipe 侧事实基线
- 核查方法：直接阅读 screenpipe 源码（`/Users/pyw/old/screenpipe/`），所有结论附文件路径 + 行为描述
- 原则：无法确认的内容标注"🟡 待验证"，禁止臆断

---

## 核心结论（一句话）

> **Screenpipe 没有后端 Chat Orchestrator。** 其 Chat 由前端启动的 Pi sidecar 编码 agent 通过 stdin/stdout JSON-RPC 驱动，Pi 使用通用编码工具（bash / read / write / edit / grep）调用 screenpipe REST API 完成数据检索；对话历史保存在前端 Tauri Store（JSON），而非数据库。

---

## 1. Chat 整体架构

```
┌─────────────────────┐     stdin/stdout JSON-RPC     ┌──────────────────┐
│  standalone-chat.tsx │ ──────────────────────────────▶│  Pi Agent (子进程) │
│  (React, 3333 lines)│ ◀──────────────────────────────│  (bun/node 运行)  │
│  - 消息渲染         │     pi_chunk / pi_event        │  - LLM 调用       │
│  - 系统提示构建     │                                │  - Tool 执行      │
│  - 会话管理/持久化  │                                │  - Search skill   │
└─────────────────────┘                                └────────┬─────────┘
         │                                                      │
    Tauri Store                                          HTTP REST
    (JSON 文件)                                                 │
    ├─ conversations[]                                          ▼
    ├─ activeConversationId                            ┌──────────────────┐
    └─ historyEnabled                                  │ screenpipe-server│
                                                       │ (Rust)           │
                                                       │ /search          │
                                                       │ /raw_sql         │
                                                       └──────────────────┘
```

**证据**：
- 前端组件：`apps/screenpipe-app-tauri/components/standalone-chat.tsx`（3333 行）
- Pi 进程管理：`apps/screenpipe-app-tauri/src-tauri/src/pi.rs`（PiManager struct，`pi_start` / `pi_start_inner`）
- Pi event 处理：`apps/screenpipe-app-tauri/lib/pi-event-handler.ts`（277 行，纯函数 reducer）

---

## 2. Pi Agent 的职责

Pi **不是** screenpipe 团队自研的 RAG Orchestrator，而是一个 **外部通用编码 agent**（`@mariozechner/pi-coding-agent`），通过 skill 注入获得 screenpipe 能力。

| 职责 | 实现方式 | 证据 |
|------|---------|------|
| **LLM 调用** | Pi 内部根据 `models.json` 配置调用 OpenAI / Anthropic / Ollama / custom | `pi.rs`: `ensure_pi_config()` 写入 `~/.pi/agent/models.json` |
| **数据检索** | Pi 的 `screenpipe-search` skill 通过 `bash` 调用 screenpipe `/search` REST API | `standalone-chat.tsx` line 76 注释: `"// TOOLS definition removed — search is now handled by Pi's screenpipe-search skill"` |
| **通用工具** | `bash`, `read`, `write`, `edit`, `grep` — 标准编码 agent 工具集 | `pi-event-handler.ts`: `tool_execution_start/update/end` 事件处理这些工具类型 |
| **Pipe 执行** | 同一个 Pi 进程也执行 Pipe（Markdown 定义的定时任务） | `pi.rs`: skill 注入含 `screenpipe-pipe-creator` |
| **Streaming 输出** | Pi stdout 逐行输出 JSON → Tauri event → 前端增量渲染 | `pi.rs`: stdout reader 逐行 emit `pi_chunk` event |

**Pi 技能注入**（3 个 SKILL.md 文件自动写入 `<project_dir>/.pi/skills/`；chat 默认 `project_dir` 为 `~/.screenpipe/pi-chat`）：

| Skill | 用途 |
|-------|------|
| `screenpipe-search` | 查询屏幕/音频数据（核心 Chat 检索能力） |
| `screenpipe-pipe-creator` | 创建/管理 Pipe |
| `screenpipe-media` | 视频/音频文件路径处理 |

**证据**：`pi.rs` 中 `ensure_screenpipe_skill()` 函数从 Tauri assets 目录读取并写入 skill 文件。

---

## 3. 系统提示 & 搜索规则

`standalone-chat.tsx` lines 86-129 构建系统提示，内含严格搜索规则：

- 必须使用 screenpipe search tool 获取数据
- 必须包含时间过滤器（`start_time` / `end_time`）
- 结果限制（`limit` 参数）
- 支持 `app_name` 过滤
- 支持 deep link：`screenpipe://frame/{frameId}`, `screenpipe://timeline?timestamp=...`
- 支持 Mermaid 图表渲染

**Mention 系统**（`lib/chat-utils.ts`，362 行）：
- `@today`, `@yesterday`, `@last-week`, `@last-hour` → 时间范围过滤
- `@audio`, `@screen`, `@input` → content_type 过滤
- `@appname` → app_name 过滤

**证据**：`standalone-chat.tsx` lines 86-129; `lib/chat-utils.ts` 全文

---

## 4. Provider Routing

| Provider | 配置方式 | 证据 |
|----------|---------|------|
| OpenAI (BYOK) | API key + model → `models.json` | `pi.rs`: provider config 构建逻辑 |
| Anthropic (via Screenpipe Cloud) | screenpipe user token | `pi.rs`: `screenpipe-cloud` provider 类型 |
| Ollama (本地) | `http://localhost:11434/v1` | `standalone-chat.tsx`: AIPreset 含 provider/url/model |
| Custom OpenAI-compatible | 用户自定义 base URL + API key | `pi.rs`: `ensure_pi_config()` |

**关键特征**：
- Provider 路由在 **Pi 启动时** 通过 `models.json` 配置文件写入，非运行时动态切换
- 前端切换 preset 后需重启 Pi session 生效
- **无内置 fallback 链**：Pi 使用单一 provider，超时或失败由 Pi 自身处理

---

## 5. 消息持久化

| 维度 | Screenpipe 实现 | 证据 |
|------|----------------|------|
| **存储位置** | Tauri Store（本地 JSON 文件） | `use-settings.tsx`: `ChatHistoryStore { conversations, activeConversationId, historyEnabled }` |
| **存储结构** | `ChatConversation { id, title, messages[], createdAt, updatedAt }` | `use-settings.tsx` 类型定义 |
| **消息类型** | `ChatMessage { id, role, content, timestamp, contentBlocks? }` | `use-settings.tsx` 类型定义 |
| **容量限制** | 50 conversations max, 100 messages per conversation | `standalone-chat.tsx`: auto-trim on save |
| **保存时机** | 每次 response 完成时（`isLoading` → false） | `standalone-chat.tsx`: `saveConversation()` |
| **并发策略** | 保存前 read-fresh 再 write，避免覆盖 | `standalone-chat.tsx`: `saveConversation()` 逻辑 |
| **无 DB 表** | 不存在 `chat_messages` SQLite 表 | 全局搜索未发现任何 chat 相关 DDL |

---

## 6. `/ai/chat/completions` 端点（澄清）

**此端点不是 Chat 主回答链路的一部分**，而是 Apple Intelligence 封装；但 Chat UI 的 follow-up suggestions（追问建议）辅助分支会可选调用该端点。

| 维度 | 说明 |
|------|------|
| 文件 | `crates/screenpipe-server/src/apple_intelligence_api.rs`（590 行） |
| 作用 | OpenAI-compatible 接口包装 macOS 原生 Foundation Models |
| Feature gate | `#[cfg(feature = "apple-intelligence")]`，仅 macOS aarch64 |
| 使用者 | Timeline agents；Chat UI 的 follow-up suggestions 辅助分支（`standalone-chat.tsx`） |
| 与 Chat 关系 | 主回答链路不依赖该端点（走 Pi RPC）；辅助建议分支可选调用，失败静默，不影响主回答 |

**证据**：
- `server.rs` lines 482-485：`/ai/chat/completions` 在 apple-intelligence feature 下注册
- `standalone-chat.tsx` lines 2522-2526 + 2392-2395：主回答链路走 Pi RPC（`sendMessage -> sendPiMessage -> commands.piPrompt`）
- `standalone-chat.tsx` lines 1511-1518 + 2196-2200：follow-up suggestions 辅助分支调用 `/ai/chat/completions`

---

## 7. Streaming 机制

| 维度 | 说明 |
|------|------|
| Chat 响应 streaming | Pi stdout 逐行 JSON → Tauri event `pi_chunk` → 前端增量渲染 |
| 事件类型 | `text_delta`, `tool_execution_start`, `tool_execution_update`, `tool_execution_end`, `thinking`, `agent_end` |
| ContentBlock 类型 | `text` / `thinking` / `tool`（内含 `isRunning`, `durationMs` 等状态） |
| 非 SSE | Chat **不使用** HTTP SSE，完全走 Tauri IPC |
| Frame streaming | WebSocket `/stream/frames`（独立于 Chat，用于 Timeline） |

**证据**：`pi-event-handler.ts` 事件类型定义；`pi.rs` stdout reader emit 逻辑

---

## 8. 关键文件索引

| 组件 | 文件路径（相对于 screenpipe/） | 行数 | 阅读状态 |
|------|------|------|---------|
| Chat UI 主组件 | `apps/screenpipe-app-tauri/components/standalone-chat.tsx` | 3333 | lines 1-300, 1300-1549 已读 |
| Pi event 处理 | `apps/screenpipe-app-tauri/lib/pi-event-handler.ts` | 277 | 全文已读 |
| Pi 进程管理 | `apps/screenpipe-app-tauri/src-tauri/src/pi.rs` | ~1799 | grep + 部分阅读 |
| Mention 工具 | `apps/screenpipe-app-tauri/lib/chat-utils.ts` | 362 | 全文已读 |
| Settings/Store | `apps/screenpipe-app-tauri/lib/hooks/use-settings.tsx` | 724 | lines 1-200 已读 |
| Tauri 命令 | `apps/screenpipe-app-tauri/lib/utils/tauri.ts` | 1056 | 部分阅读 |
| Apple Intelligence | `crates/screenpipe-server/src/apple_intelligence_api.rs` | 590 | lines 1-80 已读 |
| 路由注册 | `crates/screenpipe-server/src/server.rs` | 565 | lines 440-489 已读 |
| Timeline agents | `apps/screenpipe-app-tauri/components/rewind/timeline/agents.tsx` | 322 | 全文已读 |
| Pipe API | `crates/screenpipe-server/src/pipes_api.rs` | 193 | 部分阅读 |

---

## 9. 待验证项

| 项 | 状态 | 说明 |
|----|------|------|
| Pi RPC 完整消息格式 | ✅ 已验证 | `@mariozechner/pi-coding-agent` 已确认对应 `/Users/pyw/old/pi-mono/packages/coding-agent`（`package.json` 的 `name` 字段）；协议为 stdin/stdout JSON Lines：命令（stdin）、响应（`type: "response"`）、事件（stdout）。完整类型见 `src/modes/rpc/rpc-types.ts`，并由 `src/modes/rpc/rpc-mode.ts` 的 `session.subscribe(...)` 原样透传事件。 |
| Pi 错误恢复机制 | ✅ 已验证 | 分两层：1）进程层：`pi.rs` 在启动时做 `kill_orphan_pi_processes`，前端 `standalone-chat.tsx` 监听 `pi_terminated` 后自动重启；2）模型调用层：`coding-agent/src/core/agent-session.ts` 对可重试错误触发 `auto_retry_start/end`，指数退避重试。 |
| 多窗口并发写入 Tauri Store | ✅ 已验证（有限） | `standalone-chat.tsx` 明确标注 multi-window 覆盖问题，并采用 read-fresh + write-back（仅写 `chatHistory`）缓解；`use-settings.tsx` 通过 `onKeyChange` 同步变更。但应用层未见事务锁/CAS，语义仍接近最后写入者覆盖。 |
| Pi 超时/fallback 策略 | ✅ 已验证 | 无多 provider fallback 链：`pi.rs` 仅以单一 `--provider --model` 启动 Pi。存在超时/重试：`agent-session.ts` 默认 `maxRetries=3`、`baseDelayMs=2000`（指数退避），`standalone-chat.tsx` 前端请求 180s 超时兜底，`pi.rs` 启动就绪等待 `PI_READY_TIMEOUT=2s` 后做存活检查。 |
| Tauri Store 实际文件路径 | ✅ 已验证 | `use-settings.tsx` 的 `getStore()` 固定 `Store.load(\`${homeDir()}/.screenpipe/store.bin\`)`，即 `~/.screenpipe/store.bin`；Chat 历史存放在 `settings.chatHistory`。 |
| `standalone-chat.tsx` 主回答链路与 `/ai/chat/completions` 关系 | ✅ 已验证 | 主回答经 Pi RPC；follow-up suggestions 辅助分支调用 `/ai/chat/completions`，不属于主回答必经链路 |

---

## 版本记录

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-03-01 | 初始核查，基于 screenpipe 源码直接阅读 |
| v1.1 | 2026-03-02 | 补全第 9 节待验证项：确认 `@mariozechner/pi-coding-agent` 本地源码位置并完成 RPC 格式、错误恢复、超时/重试、Tauri Store 路径与并发写入策略核查 |
