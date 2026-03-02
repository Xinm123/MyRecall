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
- **Pi 原生事件类型**（11 种）：`message_update`（text delta）、`tool_execution_start/update/end`、`agent_start/end`、`turn_start/end`、`message_start/end`、`response`（success/error）。
- **内层协议**（Manager ↔ Pi）：Pi stdin/stdout JSON Lines（对齐 screenpipe `pi.rs`）。
- **外层协议**（前端 ↔ Edge）：HTTP SSE（拓扑适配层，因 MyRecall 前后端跨进程通信，screenpipe 为 Tauri IPC 直连）。

### 工具格式：SKILL.md（DA-3）

- Tool 以 Pi SKILL.md 文件格式定义（对齐 screenpipe）。
- P1-S5 最小集：`myrecall-search` Skill（对标 screenpipe `screenpipe-search`）。
- `frame_lookup` 和 `time_range_expansion` 按需在 P1-S7 后拆分为独立 Skill。

### 模型路由（DA-5）

- 通过 Pi `--provider`/`--model` 启动参数 + `~/.pi/agent/models.json` 配置。
- P1 不做自动 fallback chain（对齐 screenpipe 行为）。
- Provider 切换通过配置页面修改 + Manager 重启 Pi 进程生效。

### Citation 策略（DA-8=A→B 渐进）

- P1-S5：不做结构化 citation 解析（`chat_messages.citations` 字段留空）；通过提示词引导 Pi 在回答中内嵌时间戳/关键词。
- P1-S7 评估点：根据引用覆盖率观测数据决定是否启动 B 阶段（结构化 citation 后处理）。
- 若 B 阶段启动：在 Manager 层对 Pi 回答做正则/LLM 后处理，提取 `capture_id/frame_id/timestamp` 写入 `citations` 字段。

### 运行时依赖（DA-9=C）

- Edge 需安装 bun 运行时 + Pi binary（`bun add -g @mariozechner/pi-coding-agent@<pinned-version>` 或等效方式）。
- Python Manager 负责检测 bun/Pi 可用性并在缺失时给出安装引导。

## screenpipe 参考与对齐

- screenpipe 做法：Tauri app 内嵌 Pi agent（`pi.rs` 1781 行），通过 stdin/stdout JSON Lines 与 Pi RPC 通信，前端通过 Tauri IPC 接收事件。
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
- 所有目标与统计口径以 `MyRecall/docs/v3/gate_baseline.md` 为准。
