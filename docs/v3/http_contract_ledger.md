---
status: draft
owner: pyw
last_updated: 2026-03-05
scope: external-http-only
ssot:
  - spec.md
  - roadmap.md
  - open_questions.md
---

# MyRecall-v3 Phase 1 HTTP Contract Ledger（对外 HTTP Only）

本文件用于把 Phase 1 的“对外 HTTP 契约”收敛为：

- 一张可审计的“P1 HTTP Baseline”（端点清单 + SSOT 链接）
- 每个子阶段（P1-S1..S7）的“契约 delta”（新增/废弃/替代/保留/语义变更）

目标：让 `acceptance/phase1/p1-s*.md` 的 **API/Schema 契约完成率（目标 100%）** 有明确分母，并且可逐阶段回归。

## 0. Scope

- 覆盖：对外 HTTP（路径、方法、关键状态码与错误响应格式、legacy 命名空间策略）。
- 不覆盖：Pi 内部 JSON Lines / SSE 事件类型细节、deep link 语义、DB schema 细节（它们在 [spec.md](spec.md) / [data-model.md](data-model.md) 中仍是 SSOT，但不在本 ledger 的“HTTP-only scope”里细拆）。

## 1. SSOT（唯一事实源）

- P1 端点清单：[spec.md](./spec.md) §4.9
- 各端点完整契约：[spec.md](./spec.md)（search/chat/ingest/frames/health 各节）
- Phase 1 子阶段与 `/api/*` 渐进策略：[roadmap.md](./roadmap.md) §1.1
- 决策记录：[open_questions.md](./open_questions.md)（OQ-024 等）

## 2. Definitions（本 ledger 的“契约”最小定义）

对外 HTTP 契约至少包含：

- Path + Method
- Success status code（至少 2xx/3xx/4xx/5xx 的边界）
- Error body shape（统一错误格式）

说明：详细 request/response schema 以 [spec.md](spec.md) 为准，本文件只做索引与阶段映射。

## 3. Phase 1 HTTP Baseline（End State）

P1 的最终对外 HTTP surface（端点存在性与对外命名空间）以 [spec.md](spec.md) §4.9 为准：

| Contract-ID | Method | Path | SSOT |
|---|---|---|---|
| C-API-INGEST-001 | POST | `/v1/ingest` | [spec.md](spec.md) §4.7 |
| C-API-INGEST-002 | GET | `/v1/ingest/queue/status` | [spec.md](spec.md) §4.7 |
| C-API-SEARCH-001 | GET | `/v1/search` | [spec.md](spec.md) §4.5 |
| C-API-CHAT-001 | POST | `/v1/chat` | [spec.md](spec.md) §4.6/§4.9 |
| C-API-FRAME-001 | GET | `/v1/frames/:frame_id` | [spec.md](spec.md) §4.9 |
| C-API-FRAME-002 | GET | `/v1/frames/:frame_id/metadata` | [spec.md](spec.md) §4.9 |
| C-API-FRAME-003 | GET | `/v1/frames/:frame_id/context` | [spec.md](spec.md) §4.9 |
| C-API-HEALTH-001 | GET | `/v1/health` | [spec.md](spec.md) §4.9 |

### 3.1 Unified error response（HTTP-only baseline）

统一错误响应格式为：

```json
{"error": "human readable message", "code": "SNAKE_CASE_CODE", "request_id": "uuid-v4"}
```

SSOT：[spec.md](spec.md) §4.9（统一错误响应格式）。

## 4. Legacy namespace retirement（`/api/*`）

SSOT：[roadmap.md](roadmap.md) §1.1；[spec.md](spec.md) §4.5（命名空间冻结）；[open_questions.md](open_questions.md) OQ-024。

### 4.0 Legacy endpoints in scope（P1 Gate scope）

本 ledger 的“legacy 命名空间渐进废弃”只要求覆盖 v2 的以下端点（其余 `/api/*` 不作为 P1 Gate 的契约范围）：

- `POST /api/upload`（摄入）
- `GET /api/search`（检索）
- `GET /api/queue/status`（队列状态）
- `GET /api/health`（健康检查）

替代映射（REPLACE）：

| Legacy（v2） | Replacement（v3） |
|---|---|
| `POST /api/upload` | `POST /v1/ingest` |
| `GET /api/search` | `GET /v1/search` |
| `GET /api/queue/status` | `GET /v1/ingest/queue/status` |
| `GET /api/health` | `GET /v1/health` |

### 4.1 规则

- 对外契约只允许 `/v1/*` 作为默认入口；`/api/*` 只用于“废弃回归检查”。
- P1-S1..P1-S3：上述 4 个 legacy 端点按规则返回重定向并携带 `Location`：`POST /api/upload` 返回 `308`，其余 3 个 GET 端点返回 `301`（并记录 `[DEPRECATED]` 日志）。
- P1-S4 起：上述 4 个 legacy 端点必须返回 `410 Gone`（完全废弃）；建议使用统一错误格式返回（SSOT：[spec.md](spec.md) §4.9）。

说明：除上述端点外的 `/api/*` 行为不纳入 P1 Gate 口径；不得作为客户端默认调用路径。

### 4.2 重要澄清（避免阶段矛盾）

- P1-S1..S3 的 legacy 重定向（POST=308, GET=301）仅表达“命名空间迁移提示”，不等价于“目标端点当期已完成实现”。
- Gate 的验收应按子阶段定义执行：例如 P1-S1 只要求约定重定向 + 日志，不要求 `/v1/search` 在 P1-S1 可用。

## 5. Phase 1 substage deltas（HTTP-only）

每个子阶段仅列出相对上一阶段的变化；未列出的 baseline 契约默认 `RETAIN`。

### P1-S1 delta（基础链路）

| 类型 | Contract-ID | 接口 | 变化/说明 | SSOT |
|---|---|---|---|---|
| ADD | C-API-INGEST-001 | POST `/v1/ingest` | P1 首次必须可用；幂等语义起效 | [spec.md](spec.md) §4.7 |
| ADD | C-API-INGEST-002 | GET `/v1/ingest/queue/status` | 队列可观测性对外可用；响应 MUST 包含 `processing_mode`（P1-S1 固定 `noop`） | [spec.md](spec.md) §4.7 |
| ADD | C-API-FRAME-001 | GET `/v1/frames/:frame_id` | 主读取链路 JPEG 对外可用 | [spec.md](spec.md) §4.9 |
| ADD | C-API-HEALTH-001 | GET `/v1/health` | 健康检查对外可用 | [spec.md](spec.md) §4.9 |
| DEPRECATE | C-NS-API-001 | `POST /api/upload`; `GET /api/search`; `GET /api/queue/status`; `GET /api/health` | P1-S1~S3：`POST /api/upload`=308，其余 GET=301 → 对应 `/v1/*` + `[DEPRECATED]` 日志（仅废弃回归检查） | [roadmap.md](roadmap.md) §1.1 |

### P1-S2a delta（事件驱动）

| 类型 | Contract-ID | 接口 | 变化/说明 | SSOT |
|---|---|---|---|---|
| CHANGE | C-API-INGEST-001A | POST `/v1/ingest` | metadata/CapturePayload 在 S2a 生效：`capture_trigger` 枚举为 `idle/app_switch/manual/click`（`window_focus` 不纳入 P1） | [spec.md](spec.md) §4.7；[data-model.md](data-model.md) §3.0.6；`acceptance/phase1/p1-s2a.md` §1.1 |
| CHANGE | C-API-INGEST-001A-OBS | POST `/v1/ingest` | metadata/CapturePayload 在 S2a 增加 `event_ts` 观测字段：用于 `capture_latency_ms` 计算；缺失/非法样本排除出 `capture_latency_p95` 分位统计并计入观测异常 | [spec.md](spec.md) §4.7；[data-model.md](data-model.md) §3.0.6；`acceptance/phase1/p1-s2a.md` §3 |
| CHANGE | C-API-INGEST-002A | GET `/v1/ingest/queue/status` | S2a 增加背压观测子结构 `trigger_channel`：`queue_depth`、`queue_capacity`、`collapse_trigger_count`、`overflow_drop_count`，作为 `queue_saturation_ratio` 统一读口径 | [spec.md](spec.md) §4.7；`acceptance/phase1/p1-s2a.md` §3 |
| CHANGE | C-API-HEALTH-001A | GET `/v1/health` | S2a 权限契约收口：响应必须包含 `capture_permission_status`、`capture_permission_reason`、`last_permission_check_ts`；权限失效/恢复中不得返回 `status=ok`；权限快照超时返回 `stale_permission_state` | [spec.md](spec.md) §4.9；`acceptance/phase1/p1-s2a.md` §3 |

### P1-S2b delta（AX 采集）

| 类型 | Contract-ID | 接口 | 变化/说明 | SSOT |
|---|---|---|---|---|
| CHANGE | C-API-INGEST-001B | POST `/v1/ingest` | metadata/CapturePayload 在 S2b 增加 `accessibility_text` 与 `content_hash` 字段 | [spec.md](spec.md) §4.7；[data-model.md](data-model.md) §3.0.6；`acceptance/phase1/p1-s2b.md` §1.1 |

### P1-S3 delta（处理）

| 类型 | Contract-ID | 接口 | 变化/说明 | SSOT |
|---|---|---|---|---|
| RETAIN | (all) | `/v1/*` | 对外 HTTP 无新增/废弃/替代端点（处理阶段主要影响内部数据与可解释性） | [spec.md](spec.md) §4.9 |

### P1-S4 delta（检索）

| 类型 | Contract-ID | 接口 | 变化/说明 | SSOT |
|---|---|---|---|---|
| ADD | C-API-SEARCH-001 | GET `/v1/search` | Search 对外可用（FTS5+过滤） | [spec.md](spec.md) §4.5 |
| REMOVE | C-NS-API-001 | `POST /api/upload`; `GET /api/search`; `GET /api/queue/status`; `GET /api/health` | 从阶段性重定向（POST=308, GET=301）切换为 `410 Gone`（完全废弃） | [roadmap.md](roadmap.md) §1.1 |
| CHANGE | C-API-SEARCH-002 | GET `/v1/search/keyword` | P1 不提供独立端点：必须返回 `404 Not Found`（避免回归出独立路径） | `acceptance/phase1/p1-s4.md` |

### P1-S5 delta（Chat-1 Grounding 与引用）

| 类型 | Contract-ID | 接口 | 变化/说明 | SSOT |
|---|---|---|---|---|
| ADD | C-API-CHAT-001 | POST `/v1/chat` | Chat 对外可用（HTTP-only：JSON request + SSE response） | [spec.md](spec.md) §4.6/§4.9 |
| ADD | C-API-FRAME-002 | GET `/v1/frames/:frame_id/metadata` | 端点对外可用（HTTP-only：最小稳定字段 `{frame_id,timestamp}`） | [spec.md](spec.md) §4.9 |
| ADD | C-API-FRAME-003 | GET `/v1/frames/:frame_id/context` | 端点对外可用（HTTP-only：frame context JSON） | [spec.md](spec.md) §4.9 |

### P1-S6 delta（Chat-2 路由与流式）

| 类型 | Contract-ID | 接口 | 变化/说明 | SSOT |
|---|---|---|---|---|
| CHANGE | C-API-CHAT-001 | POST `/v1/chat` | 运行时故障口径补齐：provider timeout（180s watchdog）、Pi crash 等需以“可恢复且可观测”的方式对外表达（HTTP 状态仍为 SSE 流式响应） | [roadmap.md](roadmap.md) P1-S6；[spec.md](spec.md) §4.6 |

### P1-S7 delta（端到端验收 / 功能冻结）

| 类型 | Contract-ID | 接口 | 变化/说明 | SSOT |
|---|---|---|---|---|
| RETAIN | (all) | `/v1/*` | P1 功能冻结：不新增/废弃/替代对外端点；以全链路回归验证为主 | [roadmap.md](roadmap.md) P1-S7 |
