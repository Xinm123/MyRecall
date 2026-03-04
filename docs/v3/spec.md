---
status: draft
owner: pyw
last_updated: 2026-03-03
depends_on:
  - data-model.md
  - roadmap.md
  - gate_baseline.md
  - open_questions.md
---

# MyRecall-v3 规格草案（v1.0）

- 日期：2026-02-26
- 目标：在 vision-only 范围内，与 screenpipe 的视觉能力对齐，并强制落地 Edge-Centric 架构（Host 轻、Edge 重）。
- 范围：capture -> processing -> search -> chat（不含 audio）。
- 部署边界：Host 与 Edge 当前默认同一局域网（LAN），但必须保持可远端化。

## 0. 文档导航

| 文档 | 职责（SSOT） | 路径 |
|------|-------------|------|
| **本文件** (spec.md) | 架构总览、矛盾取舍、决策评审、API 契约 | — |
| [data-model.md](data-model.md) | 数据模型（DDL、FTS、screenpipe 对齐映射、Payload、Migration） | §3 提取 |
| [roadmap.md](roadmap.md) | 阶段目标、里程碑、子阶段定义、风险清单、退出条件 | §5 → 引用 |
| [gate_baseline.md](gate_baseline.md) | Gate/SLO 指标口径、统计规则、验收证据 | §6 → 引用 |
| [open_questions.md](open_questions.md) | 待决问题 + 已拍板决策（当前范围：001A–026A） | §8 → 引用 |

> **引用规则**：跨文档引用使用相对路径 + heading slug，例如 `[data-model.md#303-ddledge-sqlite](data-model.md#303-ddledge-sqlite)`。禁止引用行号。
> **依赖规则**：front matter 的 `depends_on` 仅用于自动化拓扑依赖（必须可 DAG 排序）；文档互引请使用 `references` 字段，不得用互相 `depends_on` 表达。

## 1. 先把矛盾讲清楚（必须取舍）

### 1.1 矛盾 A："对齐 screenpipe" vs "Edge-Centric"
- screenpipe 当前主干是单机本地闭环（capture/processing/search/chat 多在同节点完成）。
- 你要求的 MyRecall-v3 是强制 Edge 参与，Host 仅做轻处理。
- 结论：只能做"能力与行为对齐"，不能做"拓扑完全对齐"。
- 已确认（001A）：v3 以"行为对齐优先"为准，否则需求自相矛盾。

### 1.2 矛盾 B："可选本地/云端模型" vs "Edge 必须参与"
- 若模型在 Host 本地推理，会破坏 Edge-Centric（Host 变重）。
- 结论：模型选择权放在 Edge（本地模型或云 API），Host 不做 OCR/Embedding/Chat 推理。

## 2. 总体架构（Edge-Centric）

```mermaid
flowchart LR
  subgraph Host
    C[Capture Manager]
    B[Local Spool Buffer]
    U[Uploader + Resume]
    C --> B --> U
  end

  subgraph Edge
    W[Web UI\nFlask Pages]
    I[Ingest API]
    Q[Processing Queue]
    P[Vision Pipeline\nAX-first / OCR-fallback]
    IDX[Index Layer\nSQLite+FTS]
    S[Search API]
    CH[Chat\nPi Sidecar + Manager]
    I --> Q --> P --> IDX
    IDX --> S --> CH
    W --> S
    W --> CH
  end

  U --> I
```

### 2.1 Host 职责（严格）
- 采集：截图 + 基础上下文（app/window/monitor/timestamp/trigger）。
- 轻处理：压缩、去重哈希、可选 accessibility 文本快照（仅采集，不推理）。
- 传输：断点续传、重试、幂等上传。
- 缓存：本地 spool 与提交位点（offset/checkpoint）。
- 不允许：OCR、embedding、rerank、chat 推理、页面/UI 承载（P1~P3）。

### 2.2 Edge 职责（严格）
- 重处理：OCR（AX-first + OCR-fallback），仅存储原始文本，不做索引时 AI 增强（与 screenpipe 对齐）。
- 索引：`frames` 元数据表 + `ocr_text` + `frames_fts` / `ocr_text_fts`（FTS5）。
- 检索：FTS 召回 + 元数据过滤 + 排序。
- Chat：RAG 编排（Orchestrator 在查询时将原始文本送入 LLM 实时推理）、工具调用、引用回溯、流式输出。
- UI：继续承载现有 Flask 页面与静态资源（P1~P3）。

## 3. 数据模型

> **SSOT**: [data-model.md](data-model.md)
> 
> 数据模型的完整定义（DDL、FTS 策略、screenpipe 对齐映射、Host Payload、Migration 策略）已提取至独立文档。

## 4. 决策点逐项评审（含 screenpipe 对齐）

### 4.1 使用场景与 non-goals

### screenpipe 怎么做
- 主打"被动记忆"与"自然语言检索"，vision 结果可用于 timeline/search/chat。
- 支持多来源（OCR/UI/audio），但本次我们仅取 vision 路径。

### MyRecall-v3 决策
- 场景：开发/知识工作者对屏幕历史的检索与问答。
- non-goals：
  - 实时远程桌面流媒体。
  - 音频转写。
  - 多租户 SaaS 权限系统（v3 不做）。

### 对齐结论
- 能对齐：是（能力层）。
- 不能对齐：拓扑层（screenpipe 单机优先，v3 强制 Edge）。

### 风险
- 目标过宽导致 chat 需求蔓延。

### 验证
- 需求验收仅用 vision 数据集；audio 用例全部排除。

### 4.2 Capture pipeline（Host/Edge 边界）

### screenpipe 怎么做
- `event_driven_capture.rs`：事件驱动触发（app switch/click/typing/idle）。
- `paired_capture.rs`：截图 + accessibility 同步采集，必要时 OCR fallback。

### MyRecall-v3 决策
- Phase 1：完成事件驱动 capture（app switch/click/idle）+ manual trigger + idle fallback，并补齐 trigger 字段与采集事件总线（触发枚举以 `capture_trigger` P1 契约为准：`idle/app_switch/manual/click`）。`window_focus` 不纳入 P1；若 P2+ 启用，按 screenpipe `capture_window_focus` 语义对齐（默认关闭，高频场景按需开启）。
- 语义约束（P1）：禁止将固定频率轮询作为主触发机制；固定频率仅可用于 `idle` fallback 或兼容/实验路径。
- 参数契约（P1，对齐 screenpipe）：
  - `min_capture_interval_ms`（默认 `200`）：全触发共享最小间隔去抖。
  - `idle_capture_interval_ms`（默认 `30000`）：无事件时触发 `idle` fallback 的最大空窗。
  - 兼容映射：若未显式设置 `idle_capture_interval_ms` 且存在 `OPENRECALL_CAPTURE_INTERVAL`（秒），则按 `idle_capture_interval_ms = OPENRECALL_CAPTURE_INTERVAL * 1000` 解释；该映射仅用于兼容路径。
- Phase 2/3：capture 功能冻结，不新增采集能力，只做 LAN/Debian 稳定性验证与参数调优。
- 上传协议改为"幂等 + 可续传"：`capture_id` 唯一、chunk ACK、断点续传。
- 已拍板（OQ-004=A）：Host 采集 accessibility 文本并随 capture 上传；Host 不做 OCR/embedding 推理。
- 事件风暴抑制（对齐 screenpipe）：
  - 全触发共享最小间隔去抖（`min_capture_interval_ms`，默认 200ms）；
  - 非 `idle/manual` 触发启用内容去重（accessibility hash 相同则跳过写入），并保留 30s 强制落盘保底；
  - 触发通道有界，lag 时折叠为一次兜底触发，避免高频事件拖垮处理链路。

### 对齐结论
- 对齐级别：高度对齐（P1 即达到行为对齐）。

### 风险
- 事件风暴导致过采样与 LAN 拥塞。

### 验证
- 指标：切窗场景 95% capture 在 3 秒内入 Edge 队列。
- 压测：每分钟 300 次事件下，Host CPU < 25%，丢包率 < 0.3%。
- 去抖校验：同 monitor 连续 `app_switch/click` 入库间隔 < `min_capture_interval_ms` 的违规数应为 0。
- 去重校验：重复内容压测中应观测到 dedup skip，且 30s 保底写入仍成立（timeline 不空洞）。

### 4.3 Vision processing（与 screenpipe 对齐，Scheme C）

### screenpipe 怎么做
- accessibility 有文本时优先使用，OCR 作为 fallback（并对 terminal 类 app 做 OCR 偏好）。
- AX 成功帧：`frames.accessibility_text` = AX 文本，`frames.text_source = 'accessibility'`，**不写 `ocr_text` 行**（`paired_capture.rs:153-154`，`db.rs:1538` 的 `if let Some(...)` 不执行）。
- AX 失败帧：OCR fallback → 写 `ocr_text` 行，`frames.text_source = 'ocr'`。
- 独立 `ui_recorder` 树遍历器（每 ~500ms）：写入独立 `accessibility` 表（`db.rs:5287-5311`），与 `paired_capture` 完全解耦。

### MyRecall-v3 决策（Scheme C，025A）
- Edge 执行"AX-first + OCR-fallback"（与 screenpipe 完全对齐）。
- 对关键 app 维护 `ocr_preferred_apps`（TBD 初始名单）。
- Edge 仅存储原始 OCR text 与 accessibility text，不做索引时 AI 增强（不生成 caption/keywords/fusion_text，不写入 embedding）。
- Chat grounding 由 Orchestrator 在查询时将原始文本送入 LLM 实时推理（与 screenpipe Pi agent 模式对齐）。
- 已拍板（014A）：删除 fusion_text，索引时零 AI 调用，完全对齐 screenpipe vision-only 处理链路。

#### 写入路径（Scheme C 分表写入）

```
paired_capture 处理一帧:
  ├─ AX 成功 → frames 行 (text_source='accessibility', accessibility_text=AX文本)
  │            + accessibility 行 (text_content=AX文本, frame_id=frames.id, focused=...)
  │            + 无 ocr_text 行
  │
  └─ AX 失败 → OCR fallback
               → frames 行 (text_source='ocr')
               + ocr_text 行 (text=OCR文本, frame_id=frames.id)
               + 无 accessibility 行
```

- 处理链产物白名单（P1）：`ocr_text.text`、`ocr_text.text_json`、`frames.text_source`、`accessibility.text_content`。
- 禁止产物（P1）：`caption`、`keywords`、`fusion_text`、`ocr_text_embeddings` 写入。

### 对齐结论
- 对齐级别：完全对齐（数据流与存储结构均与 screenpipe vision-only 一致；分表写入语义对齐 screenpipe `paired_capture` + `accessibility` 独立表架构）。
- v3 增强：`accessibility.focused` 列（P0 修复，ADR-0012）、`accessibility.frame_id` 精确关联（方案 3）。

### 风险
- accessibility 文本质量不稳定，导致召回波动。

### 验证
- A/B：AX-first vs OCR-only，在同一数据集比较 Recall@20 与 NDCG@10。
- P1-S3 Gate：AX 成功帧写入 `accessibility` 表的正确率 = 100%。

### 4.4 索引与存储（Host/Edge 边界）

### screenpipe 怎么做
- SQLite 主表 + FTS（`frames_fts`/`ocr_text_fts` 等），snapshot 直接落盘并在 DB 记录路径。

### MyRecall-v3 决策
- Edge 作为唯一事实源（source of truth），使用单一 `edge.db`（SQLite）：
  - `frames`（原始采集元数据 + 处理队列状态）← 对齐 screenpipe frames
  - `ocr_text`（OCR fallback 原文 + bbox）← 对齐 screenpipe ocr_text（Scheme C：仅 AX 失败帧写入）
  - `accessibility`（AX 成功帧文本 + 独立 walker 数据）← 对齐 screenpipe accessibility 表（Scheme C，025A）
  - `frames_fts` / `ocr_text_fts` / `accessibility_fts`（FTS5 全文索引）← 对齐 screenpipe（`accessibility_fts` 增加 `browser_url` 列，确保 API 语义一致）
  - `chat_messages`（Chat 会话记录）← v3 独有
  - `ocr_text_embeddings`（P2+ 可选离线实验表，P1 不建）← 参考 screenpipe 预留
- Host 仅保留短期 spool，不做长期索引。
- 详细 DDL 见 [data-model.md §3.0.3](data-model.md#303-ddledge-sqlite)。

### 对齐结论
- 对齐级别：主路径高对齐（P1 已落地表与核心字段对齐 screenpipe vision-only，含 `accessibility` 表 + FTS）；`ocr_text_embeddings` 为 P2+ 可选，不计入 P1"100% 对齐"定义。

### 风险
- 索引与原始文档同步延迟导致检索可见性抖动。

### 验证
- 每小时对账任务：`ocr_text` 行数 + `accessibility` 行数（paired_capture 写入）≈ `frames`（status=COMPLETED）行数（允许独立 walker 带来的 accessibility 行多出）。

### 4.5 Search（召回与排序）

### screenpipe 怎么做
- `GET /search`：15+ 过滤参数，底层纯 FTS5（vision-only 路径无 embedding 参与，`search_ocr()` SQL 不 JOIN `ocr_text_embeddings`）。
- `GET /search/keyword`：独立快速路径（FTS 分组/高亮），仍是 SQL/FTS 逻辑，不涉及索引时 AI 推理。
- Response 字段：`frame_id`, `text`, `timestamp`, `file_path`（磁盘绝对路径）, `app_name`, `window_name`, `browser_url`, `focused`, `device_name`, `tags`, `frame`（base64，可选）。

### MyRecall-v3 决策（020A）
- Search 完全对齐 screenpipe（vision-only）：线上只保留 FTS5 + 过滤，不走 hybrid。
- `/v1/search/keyword` 合并到 `/v1/search`（P1 无 embedding，拆分无意义；P2+ 若引入 embedding 再拆）。
- 检索/推理边界：索引时仅入库 raw OCR + `text_source`；Chat/Orchestrator 仅在查询时实时推理。

#### API 命名空间冻结（P0-01）
- MyRecall-v3 对外 HTTP 契约统一使用 `/v1/*`。
- `/api/*` 为 v2 历史路径：P1-S1~P1-S3 返回 301 重定向至 `/v1/*` + `[DEPRECATED]` 日志；自 P1-S4 起返回 410 Gone 完全废弃。
- 兼容 alias（如存在）必须标记为 legacy，且不得作为文档、SDK、验收脚本默认入口。

#### `GET /v1/search` — 完整契约

**Query Parameters：**

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `q` | string | `""` | FTS5 全文检索，空值返回全部 |
| `content_type` | string | `"all"` | 搜索路径路由：`"ocr"` / `"accessibility"` / `"all"`（Scheme C，对齐 screenpipe `ContentType`） |
| `limit` | uint32 | `20` | 分页大小，最大 100 |
| `offset` | uint32 | `0` | 分页偏移。UI 采用"加载更多"模式（OQ-026=A，对齐 screenpipe），offset 单调递增步长=limit，实际不超过几百；P2+ 升级为 keyset cursor 后本字段废弃 |
| `start_time` | ISO8601 | null | 时间范围起点（UTC） |
| `end_time` | ISO8601 | null | 时间范围终点（UTC） |
| `app_name` | string | null | 应用名过滤（精确匹配） |
| `window_name` | string | null | 窗口名过滤（精确匹配） |
| `browser_url` | string | null | 浏览器 URL 过滤（FTS token 序列匹配，对齐 screenpipe `frames_fts MATCH`；`unicode61` 按非字母数字字符断词后做短语连续匹配） |
| `focused` | bool | null | 仅返回前台焦点帧 |
| `min_length` | uint | null | OCR 文本最小字符数（仅作用于 `content_type=ocr/all` 的 OCR 路径；`search_accessibility()` 函数不接受此参数，对齐 screenpipe） |
| `max_length` | uint | null | OCR 文本最大字符数（仅作用于 `content_type=ocr/all` 的 OCR 路径；`search_accessibility()` 函数不接受此参数，对齐 screenpipe） |
| `include_frames` | bool | `false` | true 时内嵌 base64 图像；P1 预留字段，不实现（始终返回 null） |

**Response 200 OK：**

```json
{
  "data": [
    {
      "type": "OCR",
      "content": {
        "frame_id": 123,
        "text": "提取的 OCR 文字",
        "timestamp": "2026-02-26T10:00:00Z",
        "file_path": "/data/screenshots/abc.jpg",
        "frame_url": "/v1/frames/123",
        "app_name": "Safari",
        "window_name": "GitHub - main",
        "browser_url": "https://github.com",
        "focused": true,
        "device_name": "MacBook-Pro",
        "tags": []
      }
    },
    {
      "type": "UI",
      "content": {
        "id": 456,
        "text": "AX 提取的 UI 文本",
        "timestamp": "2026-02-26T10:00:01Z",
        "file_path": "/data/screenshots/def.jpg",
        "frame_url": "/v1/frames/789",
        "app_name": "VS Code",
        "window_name": "spec.md — MyRecall",
        "browser_url": null,
        "focused": true,
        "device_name": "MacBook-Pro",
        "tags": []
      }
    }
  ],
  "pagination": {
    "limit": 20,
    "offset": 0,
    "total": 142
  }
}
```

**字段说明：**
- `file_path`：Edge 本地磁盘绝对路径（对齐 screenpipe；P1 WebUI/Chat 均在 Edge 侧可直接使用）
- `frame_url`：`/v1/frames/:frame_id` 相对路径（P2+ 跨机器时可替代 `file_path`）；`type=OCR` 时 frame_id 始终有值；`type=UI` 时 frame_id 来源于 `accessibility.frame_id`（v3 改进，外键精确关联），当为 NULL 时返回 `null`
- `type`：`"OCR"`（来自 `search_ocr()` 路径）或 `"UI"`（来自 `search_accessibility()` 路径）；对齐 screenpipe `ContentType::OCR` / `ContentType::Accessibility`。P2+ 预留 `"Audio"`
- `type=OCR` 的引用锚点字段为 `frame_id` + `timestamp`（P1-S4 Hard Gate 口径）；`type=UI` 的引用锚点字段为 `frame_id` + `timestamp`（P1-S4 Hard Gate 口径）
- `content_type=ocr` 时 response 只含 `type=OCR`；`content_type=accessibility` 时只含 `type=UI`；`content_type=all` 时混合
- `type=UI` 的 `content.text` 来源于 `accessibility.text_content`；`content.frame_id` 为 `accessibility.frame_id`（v3 改进，通过外键精确关联截图，避免 screenpipe 的 ±1s 时间窗口模糊匹配）；当 `accessibility.frame_id` 为 NULL 时，`frame_url` 返回 `null`；`file_path`/`frame_url`/`device_name` 通过 LEFT JOIN frames 获取
- `capture_id`：v3 增强可选字段（可由 `frames.capture_id` 回传），用于观测与回归；不作为 Search 对齐硬门槛
- `include_frames=true` 时 `content` 中追加 `"frame": "<base64>"` 字段；P1 不实现，始终为 null

**错误响应：** 见 §4.9 统一错误响应格式。

### 对齐结论
- **高对齐**：query params 对齐 screenpipe `SearchQuery`（含 `content_type` 路由），response 对齐 `OCRContent` + `UiContent`。
- **差异**：去掉 audio/speaker/input 相关参数（P1 无音频/输入）；新增 `frame_url` 字段；`/v1/search/keyword` 合并。
- **v3 改进**：`content_type=accessibility` + `focused` 过滤不做 screenpipe 的 force-OCR 降级。

### 风险
- 语义型查询（抽象描述、长尾表述）召回能力下降。

### 验证
- 离线评测集拆分"精确词查询/语义查询"两组；保证精确词查询不低于对齐基线，并量化语义退化幅度。

### 4.6 Chat（核心能力）

### screenpipe 怎么做
- screenpipe 的 Chat 主回答链路由 Pi 代理驱动（通过工具调用 `/search` 等检索端点）；`/ai/chat/completions` 仅用于 follow-up suggestions 辅助分支，不是主回答必经链路。

### MyRecall-v3 决策
- Edge 增加 **Pi Sidecar**（bun 进程，`--mode rpc`）+ **Python Manager**（进程管理 + 协议桥接）：
  - 内层协议（Manager ↔ Pi）：Pi stdin/stdout JSON Lines（对齐 screenpipe `pi.rs` RPC 模式）。
  - 外层协议（前端 ↔ Edge）：HTTP SSE（拓扑适配，per Decision 001A）。
  - 请求：简单 JSON `{message, session_id, images?}`；响应：SSE 透传 Pi 顶层事件（核心 11 种：`message_update`、`tool_execution_start`、`tool_execution_update`、`tool_execution_end`、`agent_start`、`agent_end`、`turn_start`、`turn_end`、`message_start`、`message_end`、`response`），不做 OpenAI format 翻译。`message_update` 内层的 `assistantMessageEvent.type` 子事件（如 `text_delta`、`thinking_start`、`thinking_delta`、`thinking_end`、`content_block_delta`）单独解析，不与顶层事件枚举混用；未知扩展顶层事件按前向兼容处理（记录并忽略或降级展示）。
  - 工具以 Pi SKILL.md 格式定义（对齐 screenpipe），P1-S5 最小集为 `myrecall-search` Skill（对标 `screenpipe-search`），`frame_lookup` 和 `time_range_expansion` 按需在 P1-S7 后拆分。
  - 软约束引用（DA-8=A）：系统提示与 `myrecall-search` Skill 显式要求输出可解析 deep link：
    - OCR 结果：使用 `myrecall://frame/{frame_id}`（frame_id 始终有值）
    - UI 结果：优先使用 `myrecall://frame/{accessibility.frame_id}`（v3 改进，通过外键精确关联）
    - 当 `accessibility.frame_id` 为 NULL 时回退 `myrecall://timeline?timestamp=ISO8601`（仅未来独立 walker 场景，P1 不触发）
    - UI 落点规则：不新增独立 `/frame/:id` 页面；`myrecall://frame/{id}` 在前端统一落到 `/timeline`，并通过 `GET /v1/frames/:frame_id/metadata` 解析 `timestamp` 后定位。
    - `frame_id`/`timestamp` 必须直接拷贝自检索结果，禁止伪造。P1-S5 不做结构化 citation（`chat_messages.citations` 留空），评估是否在 P1-S7 增加 DA-8B。
  - 模型路由：通过 Pi `--provider`/`--model` 启动参数 + `models.json` 配置控制（对齐 screenpipe）。P1 不做自动 fallback chain（对齐 screenpipe）。
- P1~P3：chat UI 与会话输入输出由 Edge 页面承载；Host 不负责 UI 与推理。
- 上述 Chat 能力要求在 P1 达成；P2/P3 不新增 Chat 功能，仅做稳定性与性能治理。
- Post-P3（可选，不纳入当前里程碑）：再评估 UI 是否迁移到 Host。

### 对齐结论
- 对齐级别：可对齐（并更符合 Edge-Centric）。

### 风险
- 无引用回答会快速失去可信度。

### 验证
- 观测指标（non-blocking）：
  - P1-S5：引用覆盖率目标 >= 85%
  - P1-S7 / P2 / P3：引用覆盖率目标 >= 92%
  - Stretch 目标：>= 95%
  - 人工抽检 hallucination rate 持续下降

### 4.7 同步与传输（LAN 主链路，断连恢复）

### screenpipe 怎么做
- 有 sync provider（批次导入导出 + 标记同步），但不是 Host/Edge LAN 主链路模型。

### MyRecall-v3 决策（019A）

#### P1 协议：单次幂等上传（方案 A）

```
POST /v1/ingest
Content-Type: multipart/form-data

Fields:
  capture_id  string    UUID v7，Host 生成，必填
  metadata    JSON      CapturePayload（除 image_data 的所有字段）
  file        binary    JPEG 图像（主契约，`image/jpeg`；兼容模式可接收 PNG/WebP，但入库前统一转码为 JPEG）

Response:
  201 Created  → {"capture_id": "...", "frame_id": 123, "status": "queued", "request_id": "uuid-v4"}
  200 OK       → {"capture_id": "...", "frame_id": 123, "status": "already_exists", "request_id": "uuid-v4"}
  400          → {"error": "...", "code": "INVALID_PAYLOAD"}
  413          → {"error": "image too large", "code": "PAYLOAD_TOO_LARGE"}
  503          → {"error": "queue full", "code": "QUEUE_FULL", "retry_after": 30}

GET /v1/ingest/queue/status
Response:
  200 OK →
  {
    "pending": 5,
    "processing": 1,
    "completed": 1023,
    "failed": 2,
    "capacity": 200,
    "oldest_pending_timestamp": "2026-02-26T10:00:00Z"
  }
  字段说明：
  - pending：等待 OCR 处理的帧数
  - processing：当前正在 OCR 处理的帧数
  - completed：本次进程启动后累计成功入库帧数（重启清零）
  - failed：本次进程启动后累计失败帧数（重启清零）
  - capacity：队列最大容量（固定配置值）；pending >= capacity 时 ingest 返回 503 QUEUE_FULL
  - oldest_pending_timestamp：最早一条 pending 帧的 timestamp（UTC ISO8601）；null 表示队列为空；
    Host 可用此字段判断队列是否卡死（如超过 5 分钟未推进则告警）
```

**幂等语义**：重复 `capture_id` 返回 `200 OK` + `"status": "already_exists"`，客户端无需区分新建/重复，直接删除 buffer 项。

**去重机制**：`frames.capture_id` UNIQUE 约束（DB 层），Edge 收到重复 capture_id 时 INSERT OR IGNORE，返回 200。

**图片格式口径（P1）**：主采集/主读取链路统一 JPEG。`frames.snapshot_path` 指向 JPEG 文件（推荐 `.jpg`），`GET /v1/frames/:frame_id` 固定返回 `Content-Type: image/jpeg`。

**Client 重试策略（P1）**：
- exponential backoff：1s → 2s → 4s → 8s → 上限 60s
- buffer 不删除，直到收到 201 或 200（already_exists）
- 503 QUEUE_FULL：遵守 `retry_after`，不立即重试
- 网络不通：无限重试，保留 buffer

**P1 鉴权**：token + TLS 可选（006A->B）

#### P2+ 协议升级路径（不破坏 P1 契约）

P2 LAN 弱网场景下新增分片批量模式，P1 单帧快速通道 `POST /v1/ingest` 继续保留，P1 Host 无需改动：

```
POST /v1/ingest/session      # 新增（P2，批量/分片模式）
PUT  /v1/ingest/chunk/{id}   # 新增（P2）
POST /v1/ingest/commit        # 新增（P2）
GET  /v1/ingest/checkpoint    # 新增（P2）
POST /v1/ingest               # 保留（P1 单帧快速通道）
GET  /v1/ingest/queue/status  # P1 已有，P2+ 继续使用
```

P2+ 升级为 mTLS 强制（006A->B）。

### 对齐结论
- 对齐级别：概念对齐（可恢复传输），实现不对齐（screenpipe 同进程直写，无 HTTP 传输层）。

### 风险
- 去重键设计错误会造成漏写或重复写。
- QUEUE_FULL 背压失效会导致 Host buffer 无限积压（需配合 spool 容量管理）。

### 验证
- 故障注入：断网/重启/乱序/重复包场景下，最终一致性通过。
- 重复包去重正确率 = 100%（相同 capture_id 不重复入库）。
- 503 背压场景：Host 遵守 retry_after，buffer 不丢、不爆。

### 4.8 UI 能力与阶段 Gate（A：最小可用集）

### screenpipe 怎么做
- UI 通过稳定 API 契约驱动核心交互（search/chat/timeline），而不是把“页面存在”当作完成标准。
- 典型主回答链路依赖点是检索端点（如 `/search`、`/search/keyword`）与 Pi RPC；`/ai/chat/completions` 在 chat 中属于辅助建议能力，不是主回答必经链路。

### MyRecall-v3 决策（012A）
- 保持 007A：P1~P3 UI 继续在 Edge，不迁移到 Host。
- 在 P1 强制引入最小 UI Gate，只覆盖可用性与可解释性，不做 UI 重构：
  - 路由可达 + 健康态/错误态可见
  - timeline 可见 capture/ingest/processing 状态
  - search 过滤项与 API 参数契约对齐，结果可回溯
  - chat 引用可点击回溯，路由/降级状态可见
  - 端到端关键路径脚本化回归
- P2/P3 功能冻结，仅验证 LAN/Debian 下 UI 稳定性与恢复行为。

### 对齐结论
- 对齐级别：中高（API 驱动交互与关键链路闭环对齐；UI 技术栈不要求一致）。

### 风险
- 最小 Gate 可能遗漏复杂交互问题。
- Edge 高负载下 UI 仍有资源争用风险。

### 验证
- 每个 P1 子阶段验收文档必须包含 UI 证据（截图/录屏 + 步骤 + 结论）。
- UI 关键路径通过率与异常可见性指标纳入阶段 Gate。

### 4.9 API 契约总览（P1 端点完整清单）

### 端点清单

| 端点 | 方法 | 说明 | 对齐 screenpipe |
|------|------|------|----------------|
| `/v1/ingest` | POST | 单帧幂等上传 | 概念对齐（019A） |
| `/v1/ingest/queue/status` | GET | 队列状态 | 概念对齐 |
| `/v1/search` | GET | FTS5 搜索 | 高对齐（020A） |
| `/v1/chat` | POST | Chat 请求（JSON）+ SSE 事件流响应 | 高对齐（DA-2/DA-7） |
| `/v1/frames/:frame_id` | GET | 图像二进制 | 高对齐（020A） |
| `/v1/frames/:frame_id/metadata` | GET | 帧 JSON 元数据 | 部分对齐（020A） |
| `/v1/health` | GET | 服务健康检查 | 高对齐 |

### `POST /v1/chat` 契约（DA-2/DA-7，P1-S5）

**Request：** `Content-Type: application/json`

```json
{
  "message": "帮我总结今天在 VS Code 里改了什么",
  "session_id": "session_20260303_001",
  "images": []
}
```

**字段说明：**
- `message`：必填，用户问题文本。
- `session_id`：必填，会话标识，用于多轮上下文与 `chat_messages` 持久化关联。
- `images`：可选，图像输入数组（P1 可为空数组）。

**Response 200 OK：** `Content-Type: text/event-stream`

```text
data: {"type":"message_update","text":"我先检索一下相关记录..."}

data: {"type":"tool_execution_start","tool":"myrecall-search"}

data: {"type":"tool_execution_end","tool":"myrecall-search","success":true}

data: {"type":"response","success":true}
```

**流式语义：**
- 事件流按 Pi 原生事件透传（不做 OpenAI format 翻译）；事件类型与顺序规则遵循 §4.6 与 ADR-0004。
- 终止事件为 `type="response"`（`success=true/false`）。
- Provider timeout、Pi crash 等运行时故障通过 SSE 错误事件/失败 `response` 表达，不引入额外 Chat 专用 HTTP 成功码分支。

**错误：**
- `400`：`{"error": "invalid chat payload", "code": "INVALID_PARAMS", "request_id": "uuid"}`
- `500`：`{"error": "chat manager unavailable", "code": "INTERNAL_ERROR", "request_id": "uuid"}`

### `GET /v1/frames/:frame_id` 契约（020A）

**Response：** `Content-Type: image/jpeg`，返回图像二进制（对齐 screenpipe `GET /frames/:id` 行为）。

**错误：**
- `404`：`{"error": "frame not found", "code": "NOT_FOUND", "request_id": "uuid"}`

### `GET /v1/frames/:frame_id/metadata` 契约（020A）

用途：deep link 导航解析（`myrecall://frame/{frame_id}` -> `timestamp` -> `/timeline` 定位）。

**Response 200 OK：**

```json
{
  "frame_id": 123,
  "timestamp": "2026-02-26T10:00:00Z",
  "app_name": "Safari",
  "window_name": "GitHub - main",
  "browser_url": "https://github.com",
  "focused": true,
  "device_name": "MacBook-Pro",
  "ocr_text": "提取的文字",
  "file_path": "/data/screenshots/abc.jpg",
  "capture_trigger": "app_switch",
  "content_hash": "sha256:abcdef...",
  "status": "completed"
}
```

**字段说明：**
- `status`：`"pending"` / `"processing"` / `"completed"` / `"failed"`
- `capture_trigger`：P1 为 `"idle"` / `"app_switch"` / `"manual"` / `"click"`；P2+ 追加 `"window_focus"` / `"typing_pause"` / `"scroll_stop"` / `"clipboard"` / `"visual_change"`；其中 `window_focus` 若启用需与 screenpipe `capture_window_focus` 语义对齐（默认关闭）；对应 CapturePayload（[data-model.md §3.0.6](data-model.md#306-host-上传-payload)）

### `GET /v1/health` 契约（对齐 screenpipe `HealthCheckResponse` 子集）

**Response 200 OK：**

```json
{
  "status": "ok",
  "last_frame_timestamp": "2026-02-26T10:00:00Z",
  "frame_status": "ok",
  "message": "",
  "queue": {
    "pending": 0,
    "processing": 0,
    "failed": 0
  }
}
```

**字段说明：**
- `status`：`"ok"` / `"degraded"` / `"error"`
- `frame_status`：`"ok"` / `"stale"`（超过 5 分钟无新帧）/ `"error"`

### 统一错误响应格式（020A，不对齐 screenpipe）

所有端点错误统一返回：

```json
{"error": "human readable message", "code": "SNAKE_CASE_CODE", "request_id": "uuid-v4"}
```

**错误码清单：**

| `code` | HTTP 状态 | 触发场景 |
|--------|-----------|---------|
| `INVALID_PARAMS` | 400 | 参数格式错误或缺失必填项 |
| `NOT_FOUND` | 404 | 资源（帧/文件）不存在 |
| `PAYLOAD_TOO_LARGE` | 413 | 图像超过大小限制 |
| `QUEUE_FULL` | 503 | ingest 队列满（附带 `retry_after` 秒） |
| `INTERNAL_ERROR` | 500 | 未预期的服务器错误 |

**说明：** screenpipe 只返回 `{"error": "message"}`（无 `code`、无 `request_id`），v3 增加 `code` 和 `request_id` 用于日志追踪与客户端差异化处理。
**补充：** `2xx` 成功响应不使用错误 `code` 字段。`capture_id` 重复属于幂等成功，使用 `HTTP 200 + "status": "already_exists"` 表达（可附 `request_id` 便于追踪）。


## 5. 演进路线

> **SSOT**: [roadmap.md](roadmap.md)
> 
> 三阶段路线图（Phase 1 本机模拟、Phase 2 LAN 双机、Phase 3 Debian 生产）及子阶段定义详见 roadmap.md。

## 6. 可验证 SLO

> **SSOT**: [gate_baseline.md](gate_baseline.md)
> 
> 所有 Gate/SLO 指标定义、统计口径、采样规则与验收证据要求以 gate_baseline.md 为准。

## 7. 明确 TBD / 需实验 / 需查证

- 已拍板（015A）：embedding 保留为离线实验表 `ocr_text_embeddings`（对齐 screenpipe），不进入线上 search 主路径。
- 已拍板（016A）：v3 全新数据起点，不做 v2 数据迁移。
- 需实验：AX-first 在多应用场景下对召回质量的净收益。
- 需查证：Debian 上 RapidOCR 与候选本地 VL 模型的稳定组合。

## 8. 已拍板决策

> **SSOT**: [open_questions.md](open_questions.md) — "已拍板结论" 各节
> 
> 所有已锁定决策（当前范围：001A–026A）的完整内容与历史变更以 open_questions.md 为唯一事实源。
