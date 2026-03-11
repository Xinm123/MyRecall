## Why

P1-S1 已完成基础 ingest 链路（Host spool → Edge 入队 → 状态机骨架），但当前采集仍依赖固定频率轮询——这既不符合 screenpipe 的事件驱动架构，也无法提供 capture_trigger 语义标记。P1-S2a 的目标是将采集机制从"定时轮询"升级为"事件驱动触发 + idle fallback"，并补齐去抖门控与背压保护，为后续 P1-S2b（AX 采集）和 P1-S3（处理管线）提供稳定的触发基础。

## What Changes

- **新增 macOS CGEventTap 事件监听**：通过 pyobjc 实现 click 和 app_switch 两类事件监听（typing_pause/scroll_stop 推迟至 P2）
- **新增触发标记**：每次 capture 必须赋值 `capture_trigger` 字段，P1 枚举为 `idle/app_switch/manual/click`
- **新增去抖门控**：全触发共享 `min_capture_interval_ms=1000`（1 Hz，有意偏离 screenpipe Performance 200ms）
- **新增 idle fallback**：采用超时触发语义，`idle_capture_interval_ms=30000`（无事件 30s 自动触发，不依赖用户活跃判定）
- **新增背压保护**：有界触发通道 + lag 折叠策略，防止高频事件拖垮处理链路；Gate 口径按 `queue_saturation_ratio <= 10%`、`collapse_trigger_count >= 1`、`overflow_drop_count = 0`（见 `docs/v3/gate_baseline.md`）
- **新增权限状态机**：`granted/transient_failure/denied_or_revoked/recovering` 四态；参数固定为 `REQUIRED_CONSECUTIVE_FAILURES=2`、`REQUIRED_CONSECUTIVE_SUCCESSES=3`、`EMIT_COOLDOWN_SEC=300`、`permission_poll_interval_sec=10`（对齐 `docs/v3/spec.md`）
- **变更 `POST /v1/ingest`**：CapturePayload 的 `capture_trigger` 字段在 S2a 生效，枚举值需校验
- **新增 `/v1/health` 权限状态暴露**：返回 `capture_permission_status`、`capture_permission_reason`、`last_permission_check_ts`，且权限失效期间 `status` 不得为 `ok`
- **锁定 Host→Edge 状态上报契约**：固定扩展 `POST /heartbeat`（内部端点）承载权限快照（5s）与 trigger_channel 采样（1Hz），移除“或等价入口”歧义
- **新增性能观测**：强制记录 `capture_latency_p95`（P50/P90/P95/P99），non-blocking
- **补齐验收证据口径**：背压必须导出原始 1Hz 序列证据；新增 Capture 丢包率（`loss_rate < 0.3%`）验收项
- **新增 Gate 校验测试**：`tests/test_p1_s2a_trigger_coverage.py`、`tests/test_p1_s2a_debounce.py`
- **新增本机验收脚本**：`scripts/acceptance/p1_s2a_local.sh`

## Non-goals

- AX 文本采集（属于 P1-S2b）
- `content_hash` 计算与内容去重（属于 P1-S2b）
- `processing_mode=ax_ocr` 的模型/推理链路（属于 P1-S3+）
- Windows/Linux 事件监听（属于 P2）
- `window_focus` 触发类型（P1 不纳入）
- typing_pause/scroll_stop 触发类型（推迟至 P2）
- 高于 1 Hz 的采集频率优化

## Capabilities

### New Capabilities
- `event-capture`: macOS CGEventTap 事件监听（click, app_switch）与触发标记（`capture_trigger` 赋值）
- `debounce`: 全触发共享最小间隔去抖（`min_capture_interval_ms=1000`）
- `backpressure`: 有界触发通道与 lag 折叠策略，防止高频事件拖垮处理链路
- `idle-fallback`: 无事件时 idle fallback 触发（`idle_capture_interval_ms=30000`），采用超时触发语义（不依赖用户活跃判定）
- `permission-state-machine`: macOS 权限状态机（`granted/transient_failure/denied_or_revoked/recovering`），瞬态失败检测与受控降级
- `capture-trigger-tag`: CapturePayload 中 `capture_trigger` 字段的赋值与 Edge 端校验
- `health-permission-status`: `/v1/health` 暴露 `capture_permission_status`，权限失效时 `status` 不得为 `ok`
- `host-state-reporting`: Host→Edge 状态上报契约（固定 `POST /heartbeat`、字段/频率/TTL）
- `ui-state-sync`: Grid 状态同步契约（`pending -> completed` 收敛可验证）
- `capture-loss-rate`: Capture 丢包率 Gate（`loss_rate < 0.3%`）

### Modified Capabilities
- `ingest-contract`: `POST /v1/ingest` 在 S2a 起对 `capture_trigger` 执行枚举校验（`idle/app_switch/manual/click`）
- `health-contract`: `GET /v1/health` 在权限异常期间保证 `capture_permission_status` 与 `status` 语义一致（权限失效/恢复中不得返回 `ok`）

## Impact

- **Client 代码** (`openrecall/client/`)：
  - 新增 `openrecall/client/events/` 模块（事件监听 + 触发枚举 + 去抖门控 + idle fallback）
  - 修改 capture manager 以集成事件驱动触发替代固定轮询
  - 新增权限状态机模块
  - 新增背压保护（有界通道 + lag 折叠）

- **Server 代码** (`openrecall/server/`)：
  - `POST /v1/ingest`：`capture_trigger` 字段校验生效
  - `GET /v1/health`：新增 `capture_permission_status`、`capture_permission_reason`、`last_permission_check_ts`
  - `POST /heartbeat`（内部）：固定为 Host 状态上报入口（权限快照 + trigger_channel 采样）

- **数据模型**：`frames.capture_trigger` 在 DDL 层保持兼容（列可为空），但自 P1-S2a 起在 API 语义与校验层视为必填并强制枚举校验

- **测试与验收**：
  - 新增 `tests/test_p1_s2a_trigger_coverage.py`
  - 新增 `tests/test_p1_s2a_debounce.py`
  - 新增 `scripts/acceptance/p1_s2a_local.sh`（强制交付，输出本机 Gate 证据包）

- **UI**：Grid（`/`）需展示新 capture 的上传/入队状态；`/timeline` 需验证新帧可见与时间定位

- **依赖**：pyobjc（macOS CGEventTap 与权限检测）
