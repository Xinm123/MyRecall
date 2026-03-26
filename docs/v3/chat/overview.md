# MyRecall v3 Chat 功能实现概览

## 文档定位

本文档定义 Chat 功能的实现阶段划分，基于以下已完成的基建：

- **Capture & Accessibility**: 已完成（见 `implementation-phases.md`）
- **API 基础**: `/v1/search`, `/v1/activity-summary`, `/v1/frames/{id}/context` 已实现
- **数据层**: `frames`, `accessibility`, `elements` 表结构已稳定

本文档定义 Chat 功能层的实现阶段，与 `mvp.md` 的关系：

- `mvp.md`: 定义 Chat MVP 的目标行为和 API 合同
- 本文档: 定义 Chat 功能的实现顺序和阶段划分

## 核心决策

在详细设计前，我们确认了以下核心决策：

### 决策1: Agent Runtime 位置

| 子决策 | 最终方案 |
|--------|----------|
| 进程关系 | A: 同进程（Chat Service 作为 Client 模块） |
| 生命周期 | 按需进程 + Pi session 机制（与 screenpipe 对齐） |
| API访问 | C3: System Prompt 注入 |

### 决策2: 如何集成 Pi

| 决策项 | 方案 |
|--------|------|
| 集成方式 | A: Subprocess (RPC mode) |
| Pi版本 | `@mariozechner/pi-coding-agent@0.60.0` (锁定) |
| Pi安装位置 | A2: 内嵌到 `~/.myrecall/pi-agent/` (独立于数据目录) |
| 通信协议 | RPC mode (stdin JSON 命令, stdout JSONL 事件流) |
| Session 管理 | 固定 `session_id="chat"`，N:1 映射 |

**与 screenpipe 对齐**：使用 RPC 模式实现长期运行的 Pi 进程，通过 stdin/stdout 进行 JSON RPC 通信。

### 决策3: Conversation Storage

| 子决策 | 方案 |
|--------|------|
| 存储格式 | A: 文件JSON (`~/MRC/chats/{conversation_id}.json`) |
| Session管理 | 策略1: 让 Pi 管理 (`~/MRC/chat-workspace/.pi/`) |
| 工作目录 | 固定目录 (`~/MRC/chat-workspace/`)，所有 conversation 共享 |
| 映射关系 | N:1（多个 conversation 共享一个 Pi session） |

**与 screenpipe 对齐**：所有对话共享一个固定的 Pi workspace，切换 conversation 时调用 `new_session` 重置 Pi 上下文。历史消息仅在 UI 层显示，不同步到 Pi 推理上下文。

### 决策4: Chat UI 架构

| 子决策 | 方案 |
|--------|------|
| UI架构 | A: 嵌入现有Web (Flask + Alpine.js) |
| 流式方案 | SSE (Server-Sent Events) |
| MVP范围 | 基础聊天 + 流式响应 + Markdown |

### 决策5: Tool Surface 设计

| 子决策 | 方案 |
|--------|------|
| 新增端点 | MVP阶段不新增，现有API足够 |
| Skill文档 | 创建 `myrecall-search` skill |
| Tool展示 | 定义友好的 API 调用展示格式 |

### 决策6: LLM Provider 选择

**采用方案 A3：使用 Pi 内置 `minimax-cn` Provider（默认）+ `kimi-coding`（备用）**

| 决策项 | 方案 |
|--------|------|
| 默认 Provider | `minimax-cn` |
| 备用 Provider | `kimi-coding` (免费) |
| 默认模型 | `MiniMax-M2.7` |
| minimax-cn endpoint | `https://api.minimaxi.com/anthropic` |
| minimax-cn API format | `anthropic-messages` |
| minimax-cn Auth | `MINIMAX_CN_API_KEY` 环境变量 |
| minimax-cn Context | 204,800 tokens |
| kimi-coding endpoint | `https://api.kimi.com/coding` |
| kimi-coding Auth | `KIMI_API_KEY` 环境变量 |
| kimi-coding Context | 262,144 tokens (免费) |
| Config | **不写 models.json** — 使用 Pi 内置 providers |

详细设计见 `phase1-foundation/spec.md` Decisions Summary。

## 阶段划分

```
阶段1: 基础设施 (Foundation)
   │
   ▼
阶段2: 核心服务 (Core Service)
   │
   ▼
阶段3: Web UI (Frontend)
   │
   ▼
阶段4: 完善体验 (Polish)
```

### 阶段依赖图

```
阶段1 ──► 阶段2 ──► 阶段3 ──► 阶段4
  │          │          │
  │          │          └── 依赖阶段2的SSE端点
  │          └── 依赖阶段1的Pi安装
  └── 独立，可并行探索
```

---

## 阶段1: 基础设施 (Foundation)

**目标**: 建立 Pi 集成的基础设施

### 任务清单

| 任务 | 描述 | 交付物 |
|------|------|--------|
| 1.1 Pi 安装管理 | 自动下载/安装 Pi 到 `~/.myrecall/pi-agent/` | `openrecall/client/chat/pi_manager.py` |
| 1.2 Skill 创建 | 创建 `myrecall-search` skill 文件 | 内嵌到 `openrecall/client/chat/skills/myrecall-search/SKILL.md` |
| 1.3 集成测试 | 验证 Pi 可以调用 MyRecall API | `tests/test_chat_pi_integration.py` |

### 验收标准

- [x] 能够通过命令行启动 Pi
- [x] Pi 可以访问 MyRecall API (`/v1/activity-summary`)
- [x] `myrecall-search` skill 正确安装

**状态**: ✅ 已完成 (2026-03-26)

---

## 阶段2: 核心服务 (Core Service)

**目标**: 实现 Chat Service 后端逻辑

### 任务清单

| 任务 | 描述 | 交付物 |
|------|------|--------|
| 2.1 Types & Data Models | Conversation, Message, ToolCall, PiStatus 数据结构 | `openrecall/client/chat/types.py` |
| 2.2 Conversation Manager | 创建/列表/删除/保存对话 | `openrecall/client/chat/conversation.py` |
| 2.3 Pi RPC Manager | RPC 模式进程管理、stdin/stdout 通信 | `openrecall/client/chat/pi_rpc.py` |
| 2.4 Chat Service | 流式响应协调、错误恢复 | `openrecall/client/chat/service.py` |
| 2.5 SSE Routes | `/chat/api/stream` 等端点 + 注册 blueprint | `openrecall/client/chat/routes.py` + `openrecall/client/web/app.py` |
| 2.6 Integration Tests | 端到端测试 | `tests/test_chat_integration.py` |

详细设计见 `phase2-core-service/spec.md` 和 `phase2-core-service/plan.md`。

### 验收标准

- [ ] `curl` 可以 POST 到 `/chat/api/stream` 并收到 SSE 事件流
- [ ] Pi 进程自动启动（首次消息时）
- [ ] Pi 进程崩溃后自动重启（指数退避，最多3次）
- [ ] Conversation 文件正确创建在 `~/MRC/chats/`
- [ ] Conversation 列表按 `updated_at` 降序返回
- [ ] `POST /chat/api/new-session` 正确重置 Pi 上下文
- [ ] 错误场景返回有意义的 JSON 错误
- [ ] SSE 连接支持 keepalive（15秒间隔）和超时处理（5分钟）
- [ ] 并发请求被拒绝并返回 `{"type": "error", "code": "BUSY"}`
- [ ] Pi 进程在服务关闭时被正确终止

---

## 阶段3: Web UI (Frontend)

**目标**: 实现用户可用的聊天界面

### 任务清单

| 任务 | 描述 | 交付物 |
|------|------|--------|
| 3.1 Chat 路由 + 导航 | `/chat` 页面路由 + header 导航集成 | `app.py`, `layout.html`, `icons.html` |
| 3.2 chat.html 模板 | 侧边栏 + 消息展示 + SSE 流式 + Markdown + ToolCall，全部内嵌于单一模板文件 | `openrecall/client/web/templates/chat.html` |
| 3.3 UI 测试 | 模板渲染测试 | `tests/test_chat_ui.py` |
| 3.4 导航集成验证 | 确认 header Chat 链接正常工作 | — |

> **说明**：SSE 流式逻辑内嵌于 `chat.html` 的 Alpine.js 中，不使用独立 JS 文件。设计决策与现有 `search.html` / `timeline.html` 保持一致，无构建步骤。

### 验收标准

- [ ] 用户可以在浏览器中访问 `/chat`
- [ ] 发送消息后能看到流式响应
- [ ] Tool Call 正确展示

---

## 阶段4: 完善体验 (Polish)

**目标**: 提升用户体验

### 任务清单

| 任务 | 描述 | 交付物 |
|------|------|--------|
| 4.1 会话持久化 | 列表、切换、删除对话 | UI + API |
| 4.2 @Mention 系统 | `@today`, `@appname` 等 | 输入增强 |
| 4.3 错误处理 | 友好的错误提示 | UI 反馈 |
| 4.4 配置集成 | LLM provider 配置到 settings | 配置项 |

### 验收标准

- [ ] 用户可以管理多个对话
- [ ] @mention 正确过滤时间范围
- [ ] 错误场景有友好提示

---

## 文档结构

```
docs/v3/chat/
├── overview.md                    # 本文档 - 总体阶段划分
├── mvp.md                         # Chat MVP 目标行为和 API 合同
├── implementation-phases.md       # Capture & Accessibility 基建阶段
├── phase1-foundation/
│   ├── spec.md                    # Phase 1 规格说明
│   └── plan.md                    # Phase 1 实现计划
└── phase2-core-service/
    ├── spec.md                    # Phase 2 规格说明
    └── plan.md                    # Phase 2 实现计划
```

---

## 术语表

| 术语 | 定义 |
|------|------|
| **Conversation** | 用户视角的"对话"，包含标题、创建时间等元数据，存储为 JSON 文件 |
| **Session** | Pi Agent 执行上下文，包含消息历史、工具调用记录，由 Pi 自动管理 |
| **Message** | 单条对话消息，属于某个 Conversation，包含 user/assistant 角色和内容 |
| **Chat Service** | Host 端的聊天服务模块，管理 Pi 子进程、事件流、Conversation 存储 |
| **Pi Agent** | 基于 @mariozechner/pi-coding-agent 的 AI Agent，执行实际对话逻辑 |
| **Skill** | Pi 的技能包，包含工具使用说明，如 `myrecall-search` |
| **Tool Call** | Agent 调用外部工具（如 API）的记录，展示在聊天界面中 |
| **SSE** | Server-Sent Events，服务端向客户端推送事件流的技术 |

---

## 目录结构

### 与现有配置对齐

MyRecall 现有数据目录配置：

| 配置项 | 环境变量 | 默认值 | 用途 |
|--------|----------|--------|------|
| Server 数据 | `OPENRECALL_SERVER_DATA_DIR` | `~/MRS` | Edge 数据（DB、frames） |
| Client 数据 | `OPENRECALL_CLIENT_DATA_DIR` | `~/MRC` | Host 数据（spool、buffer） |

### Chat 功能新增目录

| 目录 | 路径 | 用途 |
|------|------|------|
| Pi 安装 | `~/.myrecall/pi-agent/` | Pi 内嵌安装（运行时，独立于数据） |
| Chat 存储 | `~/MRC/chats/` | Conversation JSON 文件 |
| Chat workspace | `~/MRC/chat-workspace/` | 固定的 Pi 工作目录（所有 conversation 共享） |

### 完整目录结构

```
~/.myrecall/
└── pi-agent/                    # Pi 内嵌安装
    ├── node_modules/
    │   └── @mariozechner/
    │       └── pi-coding-agent/
    └── package.json

~/.pi/agent/                     # Pi 全局配置（与 Pi 共享）
├── auth.json                    # API keys
├── settings.json                # Pi 设置
└── skills/
    └── myrecall-search/
        └── SKILL.md             # MyRecall API skill

~/MRS/                           # Server 数据 (OPENRECALL_SERVER_DATA_DIR)
├── db/
│   └── edge.db
└── frames/

~/MRC/                           # Client 数据 (OPENRECALL_CLIENT_DATA_DIR)
├── spool/
├── chats/                       # Chat: Conversation 存储
│   ├── conv-uuid-1.json
│   └── conv-uuid-2.json
└── chat-workspace/              # Chat: 固定的 Pi workspace（所有 conversation 共享）
    └── .pi/                     # Pi session 文件 (由 Pi 自动管理)
```

### 与 Screenpipe 对比

| 项目 | Screenpipe | MyRecall |
|------|------------|----------|
| 数据根目录 | `~/.screenpipe/` | `~/MRS` (server) / `~/MRC` (client) |
| Pi 安装 | `~/.screenpipe/pi-agent/` | `~/.myrecall/pi-agent/` |
| Chat 存储 | `~/.screenpipe/chats/` | `~/MRC/chats/` |
| Session 文件 | `~/.screenpipe/pi-chat/.pi/` | `~/MRC/chat-workspace/.pi/` |
| Pi 进程模式 | RPC mode (stdin/stdout) | RPC mode (stdin/stdout) — **对齐** |
| Session 映射 | N:1 (固定 session_id="chat") | N:1 (固定 session_id="chat") — **对齐** |
| SSE 事件格式 | 直接透传 Pi 原始事件 | 直接透传 Pi 原始事件 — **对齐** |
| LLM Provider | screenpipe cloud (`api.screenpi.pe`) | **minimax-cn** (`api.minimaxi.com/anthropic`) — default; **kimi-coding** (`api.kimi.com/coding`) — free backup |
| Model config | 写入 `models.json` | **不写 models.json** — 使用 Pi 内置 providers |

---

## 架构图

```
┌─────────────────────────────────────────────────────────────────┐
│                        Host (Client)                             │
│                      Port 8883 (Web UI)                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────┐    ┌──────────┐    ┌──────────────────────┐       │
│  │ Recorder │───▶│  Spool   │───▶│      Uploader        │       │
│  └──────────┘    └──────────┘    └──────────────────────┘       │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │                    Chat Service                           │   │
│  │  ┌─────────────┐    ┌─────────────────────────────────┐  │   │
│  │  │  Web Route  │    │      Pi RPC Manager             │  │   │
│  │  │  /chat/api  │    │  - RPC mode (stdin/stdout)      │  │   │
│  │  │             │    │  - session_id: "chat"           │  │   │
│  │  └─────────────┘    │  - workspace: ~/MRC/chat-       │  │   │
│  │                     │    workspace/                     │  │   │
│  │                     │  - auto-start/restart            │  │   │
│  │                     └─────────────────────────────────┘  │   │
│  │                                                           │   │
│  │  ┌─────────────────────────────────────────────────────┐ │   │
│  │  │ Conversation Manager (~/MRC/chats/*.json)            │ │   │
│  │  │ - UI 层对话历史，不同步到 Pi 上下文                   │ │   │
│  │  └─────────────────────────────────────────────────────┘ │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
└───────────────────────────┬──────────────────────────────────────┘
                            │ HTTP API
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│                       Edge (Server)                              │
│                      Port 8083 (API)                             │
├─────────────────────────────────────────────────────────────────┤
│  /v1/search, /v1/frames/{id}/context, /v1/activity-summary      │
└─────────────────────────────────────────────────────────────────┘

文件系统:
┌─────────────────────────────────────────────────────────────────┐
│ ~/.myrecall/pi-agent/     # Pi 内嵌安装                         │
│ ~/.pi/agent/skills/       # Skill 文件（myrecall-search）       │
│ ~/MRC/chats/              # Conversation 文件存储               │
│ ~/MRC/chat-workspace/     # 固定的 Pi workspace                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 参考实现

### Screenpipe 关键文件

| 组件 | 路径 |
|------|------|
| Pi Executor (Rust) | `_ref/screenpipe/crates/screenpipe-core/src/agents/pi.rs` |
| Chat Storage | `_ref/screenpipe/apps/screenpipe-app-tauri/lib/chat-storage.ts` |
| Pi Event Handler | `_ref/screenpipe/apps/screenpipe-app-tauri/lib/pi-event-handler.ts` |
| Screenpipe API Skill | `_ref/screenpipe/crates/screenpipe-core/assets/skills/screenpipe-api/SKILL.md` |

### Pi 关键文档

| 文档 | 路径 |
|------|------|
| Main README | `_ref/pi-mono/packages/coding-agent/README.md` |
| Session 格式 | `_ref/pi-mono/packages/coding-agent/docs/session.md` |
| Extensions | `_ref/pi-mono/packages/coding-agent/docs/extensions.md` |
| Skills | `_ref/pi-mono/packages/coding-agent/docs/skills.md` |
| Providers | `_ref/pi-mono/packages/coding-agent/docs/providers.md` |
| Models | `_ref/pi-mono/packages/coding-agent/docs/models.md` |
| kimi-coding Provider | `_ref/pi-mono/packages/ai/src/models.generated.ts` (line 4464) |
| minimax-cn Provider (China) | `_ref/pi-mono/packages/ai/src/models.generated.ts` (line 4620) |
| minimax Provider (international) | `_ref/pi-mono/packages/ai/src/models.generated.ts` (line 4500) |

---

## 里程碑

| 阶段 | 目标 | 状态 |
|------|------|------|
| 阶段1 | Pi 集成基础设施就绪 | ✅ 已完成 (2026-03-26) |
| 阶段2 | Chat Service 后端可用 | ✅ 已完成 (2026-03-26) |
| 阶段3 | Web UI 可用 | ⏳ 待开始 |
| 阶段4 | 体验完善 | ⏳ 待开始 |

---

## 变更历史

| 日期 | 变更 |
|------|------|
| 2026-03-25 | 初始创建，定义核心决策和阶段划分 |
| 2026-03-25 | 修正目录路径与现有配置对齐，添加术语表 |
| 2026-03-25 | 补充 LLM Provider 对比表，更新 Pi 关键文档引用 |
| 2026-03-25 | 添加 minimax 作为默认 Provider，kimi-coding 作为备用 |
| 2026-03-26 | Phase 1 完成验收，更新验收标准状态 |
| 2026-03-26 | Phase 2 完成，所有后端文件、API 端点和测试已就绪 |
| 2026-03-26 | 更新决策2：从 JSON mode 改为 RPC mode（与 screenpipe 对齐） |
| 2026-03-26 | 更新决策3：Conversation:Session 映射改为 N:1，固定 workspace |
| 2026-03-26 | 更新阶段2任务清单和验收标准，与 plan.md 对齐 |
| 2026-03-26 | 更新架构图和目录结构，反映 RPC 模式设计 |
| 2026-03-26 | 决策2添加 Pi 版本锁定说明 (`@0.60.0`) |
| 2026-03-26 | 完善验收标准：添加 keepalive 间隔、并发请求处理、重启次数限制 |
| 2026-03-26 | Phase 2 文档一致性修正：Task 2.1 添加 PiStatus 数据类；Task 2.5 补充 `web/app.py` blueprint 注册交付物 |
