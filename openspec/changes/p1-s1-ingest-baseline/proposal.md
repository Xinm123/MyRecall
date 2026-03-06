## Why

MyRecall-v3 已进入 Phase 1 - Step 1（P1-S1），需要先落地一条可脚本化回归的“基础链路”，把采集→上传→入队→可观测→UI可见的最小闭环跑通并固化为对外契约。此变更用于在保持 vision-only（不包含 audio）并对齐 screenpipe 行为基线的前提下，尽早锁定 `/v1/*` 命名空间与可观测锚点，降低后续阶段（P1-S2+）迭代漂移风险。

## What Changes

- 新增对外 `/v1/*` 最小 HTTP 面：`POST /v1/ingest`（单帧幂等上传，201/200 already_exists 语义）、`GET /v1/ingest/queue/status`（返回 `pending`/`processing`/`completed`/`failed`/`processing_mode`/`capacity`/`oldest_pending_ingested_at`，P1-S1 固定 `processing_mode=noop`）、`GET /v1/frames/:frame_id`（`Content-Type: image/jpeg`）、`GET /v1/health`（UI 轮询的数据源）。
- 强制 P1-S1 `processing_mode=noop`：只推进队列状态机与可观测闭环，不初始化任何 OCR/embedding/vision provider 或模型；启动后必须输出且仅输出一次：`MRV3 processing_mode=noop`。
- 幂等与失败可观测：`capture_id` 作为幂等键（DB UNIQUE），重复上传返回 `HTTP 200` + `{"capture_id":"...","frame_id":<int>,"status":"already_exists","request_id":"<uuid-v4>"}`（2xx 成功响应不包含错误 `code` 字段）；当 `failed` 计数增加时输出结构化日志锚点 `MRV3 frame_failed reason=`，且 `<REASON>` 仅允许 `DB_WRITE_FAILED` / `IO_ERROR` / `STATE_MACHINE_ERROR`。
- UI 健康态/错误态 Gate：`/`、`/search`、`/timeline` 三页首屏必须存在 `#mr-health`，并暴露 `data-state="healthy|unreachable|degraded"`；文案锚点：健康态包含 `服务健康/队列正常`，不可达包含 `Edge 不可达`，首帧等待态包含 `等待首帧`（上述锚点均需字面一致）；失败注入与自动恢复均禁止刷新页面。
- legacy 命名空间渐进废弃（P1-S1~S3）：仅对 Gate scope 内的 4 个 legacy 端点返回 `301` 且带 `Location` 指向对应 `/v1/*`，并记录 `[DEPRECATED]` 日志：`POST /api/upload`、`GET /api/search`、`GET /api/queue/status`、`GET /api/health`
  - ⚠️ 说明：301 是"迁移公告"，不等价于"目标端点当期已完成实现"。S1 阶段 `/v1/search` 可能返回 404（属预期，P1-S4 才实现）。

## Non-goals

- `/v1/search` 可用性（P1-S4+）。
- `/v1/chat` 可用性（P1-S5+）。
- AX-first/OCR-fallback 处理管线（P1-S3+）。
- Host 事件驱动 capture（P1-S2）。
- TLS/mTLS 强制（P2+）。

## Capabilities

### New Capabilities

- `ingest`: 单帧幂等上传契约与 Host 重试/删除语义（201 Created vs 200 already_exists；错误统一格式；JPEG 主契约）。
- `queue-observability`: `GET /v1/ingest/queue/status` 的 DB 实时计数口径、`processing_mode=noop` 暴露与可验证日志锚点要求。
- `frame-serving`: `GET /v1/frames/:frame_id` 主读取链路（`Content-Type: image/jpeg`）与快照落盘约束。
- `health-endpoint`: `GET /v1/health` 契约（对齐 screenpipe `HealthCheckResponse` 子集），为 UI 健康态判定提供稳定数据源。
- `legacy-deprecation`: `/api/*`（仅 Gate scope 4 个端点）到 `/v1/*` 的 301 + `Location` + `[DEPRECATED]` 规则与阶段演进（P1-S4 起切换为 410）。
- `ui-health-gate`: `#mr-health` + `data-state` 的 UI 状态机与验收时序口径（含不可达与自动恢复的时间窗）。

### Modified Capabilities

- （无）

## Impact

- 代码面：将新增/调整 Edge 侧 `/v1/*` 路由、QueueDriver（noop）与 SQLite schema/migrations（以 `frames` 为计数与幂等的 SSOT）；同时更新 WebUI 模板以注入 `#mr-health` 组件与轮询逻辑。
- API 面：对外默认入口从 `/api/*` 收敛到 `/v1/*`；legacy 端点仅保留 301 迁移提示（并明确不实现 catch-all `/api/*`）。
- Host 行为：Host spool/重试语义需要与幂等成功码（201/200）对齐，断连恢复后自动续传且不重复入库。
