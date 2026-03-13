# P1-S2b 验收记录（Capture Completion / Monitor-Aware Coordination）

- 阶段：P1-S2b
- 日期：2026-03-13（OCR-only 收口后重写）
- 负责人：pyw
- 版本/提交：待定
- 状态：`Planned`
- ADR：[ADR-0013](../../adr/ADR-0013-event-driven-ax-split.md)
- 依赖：P1-S2a（事件驱动 trigger 生成） + P1-S2a+（权限稳定性收口 Pass）

## 0. screenpipe 对照与对齐

- screenpipe 语义：事件先尽量归属到受影响的 monitor，再由 per-monitor capture worker 执行截图；不是“所有 worker 广播消费同一 trigger”。
- 本阶段对齐：收口 `TriggerSource -> TriggerRouter -> CaptureCoordinator -> MonitorWorker[target]` 的语义边界，并验证 capture completion 的 HTTP/metadata 契约。
- 本阶段不实现 AX 树遍历、`accessibility_text` handoff、`content_hash` Gate 或 OCR processing；这些已不属于 v3 主线。
- 平台策略：macOS-only（P1 仅验证 macOS；Windows/Linux 推迟到后续稳定性阶段）。

## 1. 范围与目标

- 范围：trigger routing、monitor-aware capture coordination、`device_name` binding、focused context 冻结、spool/ingest handoff、一致性与恢复语义。
- 目标：确保一条 trigger 能稳定收敛到正确 capture，而不是把错误 monitor、重复 capture 或不一致 metadata 带入后续 OCR 主线。
- 对应 Gate 条件：
  - `trigger_target_routing_correctness = 100%`
  - `device_binding_correctness = 100%`
  - `single_monitor_duplicate_capture_rate = 0%`
  - `topology_rebuild_correctness = 100%`
  - `capture_to_ingest_latency_ms`：Soft KPI（按 `device_name` 分桶，记录 P50/P90/P95/P99）

### 1.0 In-scope outcomes（本阶段必须交付）

- trigger scope 语义冻结：`specific-monitor` / `active-monitor` / `global-reevaluation`
- coordinator 责任冻结：fan-out / 目标 monitor 选择发生在 worker 之前，worker 只消费 monitor-bound work item
- `device_name` 绑定冻结：由实际完成截图的 monitor worker 负责最终绑定
- `focused_context = {app_name, window_name}` 冻结：同一 capture 周期内一次性产出，允许部分缺失，但禁止字段级混拼
- ~~`browser_url` 语义冻结：best-effort metadata；命中 stale 或无法确认一致性时必须写 `None`~~（P1 不采集 Browser URL）
- topology rebuild：monitor 增减、primary 切换、monitor 不可用恢复后，worker 集合与路由状态可恢复
- spool handoff correctness：capture 完成后，metadata / image / `capture_trigger` / `device_name` 一致入 spool，再进入 `/v1/ingest`

### 1.0b Out-of-scope（本阶段明确不做）

- AX 树遍历、AXValue/AXTitle/AXDescription 提取
- `accessibility_text` / `content_hash` compatibility-field handoff
- content-based dedup 规则
- OCR processing、`text_source` 判定、`ocr_text` / `accessibility` 分表写入
- `/v1/search`、`/v1/chat`、citation 回溯

### 1.0c S2b -> S3 handoff contract（进入 P1-S3 前冻结）

- S2b 只负责 capture completion，不负责 OCR 处理与 `text_source` 判定。
- 上传主契约：`POST /v1/ingest` 在 v3 主线必须携带截图与 capture metadata：`capture_id`、`timestamp`、`event_ts`（建议）、`capture_trigger`、`device_name`、`app_name`、`window_name`。
- proof sample canonical key 契约：进入 S2b Gate proof 的 payload 必须使用 canonical keys `app_name`、`window_name`、`device_name`；`active_app`、`active_window` 等 alias 仅允许用于 compatibility observation，不得作为 proof sample 真值。
- 上下文一致性契约：`app_name/window_name` 必须由同一轮 focused-context snapshot 一次性产出；允许整体缺失/部分为 `None`，但不允许字段级跨来源混拼。
- **P1 不采集 `browser_url`**：字段保留为 `NULL`，P2+ 评估是否启用分层提取策略。
- device-binding 契约：`device_name` 表示实际被截取的 monitor，要求与本次 capture cycle 一致；若内部仍存在事件源预绑定 device 的实现，其只能作为 `event_device_hint`，不得直接作为最终验收真值。
- outcome 契约：S2b evidence 必须能区分 `capture_completed`、`routing_filtered`、`permission_blocked`、`spool_failed`、`schema_rejected`、`topology_rebuilt`。

### 1.0d Input dependencies from stable P1-S2a contracts

- 触发机制：`idle/app_switch/manual/click` 触发事件（由 P1-S2a 提供）
- `capture_trigger` 字段赋值逻辑（由 P1-S2a 实现）
- 去抖门控（`min_capture_interval_ms=1000`，由 P1-S2a 实现）
- 性能监控框架（`capture_latency_p95`，由 P1-S2a 引入）
- 队列安全边界：`queue_saturation_ratio <= 10%`、`overflow_drop_count = 0`；`collapse_trigger_count` 仅保留为观测指标

### 1.1 HTTP 契约 delta（本阶段，scope=对外 HTTP）

- SSOT：[../../http_contract_ledger.md](../../http_contract_ledger.md)
- 实施边界（已冻结）：S2b 功能正确性的证明链路仅认 `/v1/*` + v3 runtime/store；legacy `/api/*` 与旧 worker 仅做兼容回归检查，不承担新的 S2b 语义或验收责任。

| 类型 | 接口 | 变化/说明 | SSOT |
|---|---|---|---|
| CHANGE | POST `/v1/ingest` | S2b 不新增 OCR-only 主线路径必填字段；本阶段对外 HTTP 主要收口 capture completion 语义（`device_name` 绑定、focused context same-cycle coherence、spool/ingest handoff 一致性） | [../../http_contract_ledger.md](../../http_contract_ledger.md) |
| RETAIN | `/v1/*` | 对外 HTTP 无新增/废弃/替代端点 | [../../spec.md](../../spec.md) §4.9 |

## 2. 环境与输入

- 运行环境：macOS（P1-S2b 仅验证 macOS）
- 配置与数据集：
  - 单屏与多屏场景（主屏+副屏）
  - 四类 trigger 样本：`idle/app_switch/manual/click`
  - Browser URL best-effort 样本：Chrome / Safari / Edge（Arc 仅 observation）
  - topology 变化场景：monitor 增加、移除、primary 切换、monitor 不可用恢复
- 依赖版本：capture routing / coordinator / monitor worker 版本

### 2.1 指标口径与样本说明（必填）

- 口径基线版本（默认 [../../gate_baseline.md](../../gate_baseline.md)）：v1.5
- 指标样本数：
  - `trigger_target_routing_correctness`：四类 trigger 均命中，且每类样本 `>= 20`
  - `device_binding_correctness`：`>= 100 captures`
  - `single_monitor_duplicate_capture_rate`：`>= 100` 个单 monitor 作用域 trigger
  - `topology_rebuild_correctness`：至少覆盖 monitor 增加、移除、primary 切换、monitor 不可用恢复各 `>= 1` 次
  - `inter_write_gap_sec` Soft KPI：每设备样本 `>= 100`
- 统计时间窗：
  - 主窗：连续 5 分钟多屏、多 trigger 场景
  - topology 窗：每类变更场景独立记录起止时间
- 百分位算法：Nearest-rank（剔除前 10 个预热样本）
- proof sample 排除规则（必填）：legacy `/api/*`、alias-only payload、mixed-version 样本、`broken_window=true` 样本不得进入 Gate proof。

## 3. 验收步骤

1. 启动 Host/Edge，开启 capture debug 日志，并确认 `/v1/ingest`、`/v1/ingest/queue/status`、`/v1/health` 可用。
2. 对四类 trigger 分别执行采样，记录 trigger、目标 monitor、最终 `device_name`、截图归属与 metadata。
3. 抽样校验 routing correctness：
   - `click` 命中发生点击的 monitor
   - `app_switch` 命中当前 active/focused monitor
   - `manual` 与 `idle` 行为符合当前 coordinator 规则
4. 抽样校验 `device_name` binding correctness：payload / spool / ingest 后的 `device_name` 必须与实际截图 monitor 一致。
5. 执行单 monitor 作用域 trigger 压测，验证不会因 fan-out 或 worker 过滤错误产生重复 capture。
6. 执行 topology rebuild 场景：
   - 增加 monitor
   - 移除 monitor
   - 切换 primary monitor
   - 使 monitor 临时不可用后恢复
   验证 worker 集合、分发结果和 `device_name` 都能恢复正确。
7. 抽样校验 focused context coherence：`app_name/window_name/browser_url` 来自同一轮 snapshot；不确定样本按 `None` 处理，不得写明显错误窗口或 URL。
8. 记录 Browser URL best-effort 行为（observation only，非 Gate）：
   - 成功样本返回合法 `http(s)` URL
   - 无法确认一致性样本置 `None`
9. 执行 `inter_write_gap_sec` SQL 观测（按 `device_name` 分桶，Soft KPI）：
   ```sql
   WITH samples AS (
     SELECT device_name, timestamp
     FROM frames
     WHERE capture_trigger IN ('app_switch', 'click')
       AND timestamp >= datetime('now', '-5 minutes')
   ),
   ordered AS (
     SELECT device_name,
            timestamp,
            LAG(timestamp) OVER (PARTITION BY device_name ORDER BY timestamp) AS prev_ts
     FROM samples
   )
   SELECT
     device_name,
     COUNT(*) AS writes,
     COALESCE(MAX((julianday(timestamp) - julianday(prev_ts)) * 86400.0), 0) AS max_gap_sec
   FROM ordered
   WHERE prev_ts IS NOT NULL
   GROUP BY device_name;
   ```
10. 归档 proof sample、queue/status/health 快照与多屏证据。

## 4. 结果与指标

### 4.1 数值指标

- `trigger_target_routing_correctness`（目标 = 100%）：
- `device_binding_correctness`（目标 = 100%）：
- `single_monitor_duplicate_capture_rate`（目标 = 0%）：
- `topology_rebuild_correctness`（目标 = 100%）：
- `capture_to_ingest_latency_ms`（Soft KPI）：
  - 记录 P50/P90/P95/P99 分布（按 `device_name` 分桶，样本 >= 50）
- ~~Browser URL observation~~（P1 不采集）
- 备注（是否满足最小样本数要求）：是 | 否（不足项：...）

### 4.2 功能完成度指标（强制）

- 功能清单完成率（目标 100%）：
- API/Schema 契约完成率（目标 100%）：
- 关键功能用例通过率（目标 >= 95%）：

### 4.3 完善度指标（强制）

- capture completion 异常与降级场景通过率（目标 >= 95%）：覆盖 routing filtered、topology rebuild、permission blocked、spool failed。
- ~~权限异常闭环~~（移至 P1-S2a+ 专项验收）
- proof-sample exclusion 正确率（目标 100%）：legacy、alias-only、mixed-version、`broken_window` 样本全部被正确排除。
- 可观测性检查项完成率（目标 100%，日志/指标/错误码）：
- 文档与验收记录完整率（目标 100%）：

### 4.4 UI 验收（按阶段启用）

- 路由可达与基础状态可见性检查（健康态/错误态）：通过。
- UI 关键交互通过率：本阶段检查 timeline 新 capture 可见率 >= 95%。
- UI 证据附件（截图/录屏/日志路径）：

## 5. 结论

- Gate 结论：`Pass` | `Fail`
- 样本数符合性判定：`Pass` | `Fail`（若 `Fail`，本阶段不得给出 Gate `Pass` 结论）
- 依据：
- 阻塞项（若 Fail 必填）：

## 6. 风险与后续动作

- 风险：routing / worker ownership 设计错误会导致错 monitor capture 或重复 capture。

- 风险：monitor topology 变化处理不完整会导致 `device_name` 漂移或 capture 漏采。
- 后续动作：若多屏 routing 不稳定，优先收紧 coordinator 归属规则；若 topology rebuild 失败，先修复 worker 生命周期，再复跑本阶段。 
