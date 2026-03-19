# ADR-0004 Chat RAG 编排放在 Edge（Pi Sidecar 架构）

- 状态：Accepted（修订）
- 日期：2026-02-26（初版）；2026-03-01（修订：DA-2/DA-7/DA-8/DA-9 决策落地）

## Context
- Chat 是核心能力。v2 缺少一等 Chat 编排层。
- DA-7 可行性分析确认：Pi agent（screenpipe 官方 AI agent，bun 运行时）可作为 sidecar 运行在 Edge，复用 screenpipe 成熟的 RPC 模式、SKILL.md 工具格式和多 provider 路由能力。
- DA-2 分析确认：Pi stdout 有 11 种事件类型，OpenAI-compatible format 仅能无损映射 1 种（`message_update` → `delta.content`）；6 种事件类型无 OpenAI 等价物；行业趋势（AG-UI Protocol 等）验证 agent 场景用自定义事件协议更合理；Chat UI 绿地开发无存量兼容需求。

## Decision

### 架构：Pi Sidecar + Python Manager（DA-7=A）

```
Frontend → POST /v1/chat {message, session_id, images?} → Edge Python Manager
  → Pi Sidecar (bun, --mode rpc, stdin/stdout JSON Lines)
    → LLM Provider (OpenAI/Ollama/Cloud via --provider/--model)
    → curl Edge /v1/search (via myrecall-search SKILL.md)
  → stdout events → Manager → SSE stream → Frontend
  → chat_messages SQLite table (persistence)
```

- **Pi Sidecar**：bun 进程，`~/.bun/bin/pi --mode rpc --provider <p> --model <m>`。
- **Python Manager**（~600-800 行）：进程生命周期管理（spawn/watchdog/restart）+ 协议桥接（Pi JSON Lines ↔ HTTP SSE）+ `chat_messages` 持久化。

### 协议：Pi 原生事件透传（DA-2 修订）

- **请求**：简单 JSON `{message, session_id, images?}`（不采用 OpenAI-compatible request format）。
- **响应**：HTTP SSE 透传 Pi 原生事件，不做 OpenAI format 翻译。
- **Pi 顶层事件类型**（核心 11 种）：`message_update`、`tool_execution_start/update/end`、`agent_start/end`、`turn_start/end`、`message_start/end`、`response`（success/error）。
- **事件分层约定**：`message_update` 内层的 `assistantMessageEvent.type` 子事件（如 `text_delta`、`thinking_start`、`thinking_delta`、`thinking_end`、`content_block_delta`）单独解析，不与顶层事件枚举混用；运行时若出现未知扩展顶层事件，按前向兼容处理（透传 + 记录）。
- **内层协议**（Manager ↔ Pi）：Pi stdin/stdout JSON Lines（对齐 screenpipe `pi.rs`）。
- **外层协议**（前端 ↔ Edge）：HTTP SSE（拓扑适配层，因 MyRecall 前后端跨进程通信，screenpipe 为 Tauri IPC 直连）。

### 工具格式：SKILL.md（DA-3）

- Tool 以 Pi SKILL.md 文件格式定义（对齐 screenpipe）。
- P1-S5 最小集：`myrecall-search` Skill（对标 screenpipe `screenpipe-search`），统一包含搜索、时间范围渐进扩展、帧详情获取等能力。

### 模型路由（DA-5）

- 通过 Pi `--provider`/`--model` 启动参数 + `~/.pi/agent/models.json` 配置。
- P1 不做自动 fallback chain（对齐 screenpipe 行为）。
- Provider 切换通过配置页面修改 + Manager 重启 Pi 进程生效。

### Citation 策略（DA-8=A→B 渐进）

- P1-S5：不做结构化 citation 解析（`chat_messages.citations` 字段留空）；通过提示词与 Skill 规则要求 Pi 输出可解析 deep link：
  - OCR/frame 结果：`myrecall://frame/{frame_id}`
  - P1 不使用 UI/accessibility citation；若 v4 恢复 AX path，再重新定义该引用口径
- deep link 导航解析：点击 `myrecall://frame/{id}` 后，通过 `GET /v1/frames/:frame_id/metadata`（timestamp resolver，最小稳定契约）解析 timestamp 并在 `/timeline` 定位（对齐 screenpipe `/frames/{id}/metadata` 语义）。
- 帧上下文（URL/文本）获取：通过 `GET /v1/frames/:frame_id/context`（020B）获取（对齐 screenpipe `/frames/{id}/context`；P1 仅 text/urls，P2+ 扩展 nodes）。
- P1-S7 评估点：根据引用覆盖率观测数据决定是否启动 B 阶段（结构化 citation 后处理）。
- 若 B 阶段启动：在 Manager 层对 Pi 回答做后处理，提取并校验 `frame_id/timestamp`（可选 `capture_id`）写入 `citations` 字段。

### 运行时依赖（DA-9=C）

**bundled bun 策略（对齐 screenpipe）：**
- Edge 捆绑 bun 二进制（与可执行文件同目录），确保 Pi 始终可运行
- bun 查找顺序：1) 捆绑 bun → 2) ~/.bun/bin/bun → 3) 系统路径
- Pi 通过 `bun add -g @mariozechner/pi-coding-agent@<pinned-version>` 安装

**自动安装与检测：**
- Python Manager 启动时自动检测 bun/Pi 可用性
- 缺失时尝试自动安装（`install_pi.sh` 或内置安装逻辑）
- 安装失败时记录错误但继续运行，Chat API 返回可用性状态

**P1-S5 Gate 前置验证：**
- bun --version 可执行
- pi --version 可执行
- /v1/chat 返回非 503

**对齐 screenpipe：**

- screenpipe 做法：Tauri app 内嵌 Pi agent（`pi.rs` 1799 行），通过 stdin/stdout JSON Lines 与 Pi RPC 通信，前端通过 Tauri IPC 接收事件。
- 对齐结论：能力/行为完全对齐（RPC 协议、SKILL.md 工具格式、model routing）；拓扑适配为 HTTP SSE 替代 Tauri IPC（per Decision 001A "行为对齐不做拓扑对齐"）。

## Consequences
- 优点：复用 screenpipe 成熟 agent 基础设施（~600-800 行 vs 自建 ~3000 行）；天然对齐 screenpipe 工具生态；模型路由零开发成本。
- 代价：引入 bun 运行时依赖；Pi 版本升级需跟踪 screenpipe 上游。

## Risks
- Pi binary 尺寸和 bun 安装在 Debian 受限环境的兼容性（DA-9 已验证 x86_64 + aarch64 支持）。
- 仅采用软约束 citation 时（DA-8=A 阶段），若缺少持续观测与回归，引用质量可能下滑。

## Validation
- 分阶段观测目标（non-blocking）：
  - P1-S5：回答引用覆盖率目标 >= 85%
  - P1-S7 / Phase2 / Phase3：回答引用覆盖率目标 >= 92%
  - Stretch 目标：>= 95%
- 所有目标与统计口径以 [../gate_baseline.md](../gate_baseline.md) 为准。
