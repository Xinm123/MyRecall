# P1-S2b 验收记录（Capture Completion / Monitor-Aware Coordination）

- 阶段：P1-S2b
- 日期：2026-03-14（P1-S2b 路由语义收口）
- 负责人：pyw
- 状态：`Planned`
- ADR：[ADR-0013](../../adr/ADR-0013-event-driven-ax-split.md)
- 依赖：P1-S2a（事件驱动 trigger 生成） + P1-S2a+（权限稳定性收口 Pass）

## 0. screenpipe 对照与对齐

- screenpipe 语义：事件先尽量归属到受影响的 monitor，再由 per-monitor capture worker 执行截图；不是"所有 worker 广播消费同一 trigger"。
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

### 1.0 In-scope outcomes（本阶段必须交付）

- trigger routing 语义冻结：`specific-monitor` (click), `active-monitor` (app_switch), `per-monitor-idle` (deadline), `coordinator-defined` (manual)；支持 `routing_filtered` 丢弃语义。
- coordinator 责任冻结：fan-out / 目标 monitor 选择发生在 worker 之前，worker 只消费 monitor-bound work item
- `device_name` 绑定冻结：由实际完成截图的 monitor worker 负责最终绑定
- `focused_context = {app_name, window_name}` 冻结：同一 capture 周期内一次性产出，允许部分缺失，但禁止字段级混拼
- topology rebuild：monitor 增减、primary 切换、monitor 不可用恢复后，worker 集合与路由状态可恢复
- spool handoff correctness：capture 完成后，metadata / image / `capture_trigger` / `device_name` 一致入 spool，再进入 `/v1/ingest`

### 1.0b Out-of-scope（本阶段明确不做）

- AX 树遍历、AXValue/AXTitle/AXDescription 提取
- `accessibility_text` / `content_hash` compatibility-field handoff
- content-based dedup 规则
- OCR processing、`text_source` 判定、`ocr_text` / `accessibility` 分表写入
- `/v1/search`、`/v1/chat`、citation 回溯
- **P1 不采集 `browser_url`**

### 1.0c S2b -> S3 handoff contract（进入 P1-S3 前冻结）

- S2b 只负责 capture completion，不负责 OCR 处理与 `text_source` 判定。
- 上传主契约：`POST /v1/ingest` 在 v3 主线必须携带截图与 capture metadata：`capture_id`、`timestamp`、`event_ts`（建议）、`capture_trigger`、`device_name`、`app_name`、`window_name`。
- 上下文一致性契约：`app_name/window_name` 必须由同一轮 focused-context snapshot 一次性产出；允许整体缺失/部分为 `None`，但不允许字段级跨来源混拼。
- device-binding 契约：`device_name` 表示实际被截取的 monitor，要求与本次 capture cycle 一致。
- outcome 契约：S2b evidence 必须能区分 `capture_completed`、`routing_filtered`、`permission_blocked`、`spool_failed`、`schema_rejected`、`topology_rebuilt`，并通过 `/v1/health.capture_runtime.last_capture_outcome` 与日志双重取证。

## 2. 环境与输入

- 运行环境：macOS（P1-S2b 仅验证 macOS）
- 配置与数据集：
  - 单屏与多屏场景（主屏+副屏）
  - 四类 trigger 样本：`idle/app_switch/manual/click`
  - topology 变化场景：monitor 增加、移除、primary 切换、monitor 不可用恢复

### 2.1 指标口径与样本说明（必填）

- 口径基线版本（默认 [../../gate_baseline.md](../../gate_baseline.md)）：v1.7
- 指标样本数：
  - `trigger_target_routing_correctness`：四类 trigger 均命中，且每类样本 `>= 20`
  - `device_binding_correctness`：`>= 100 captures`
  - `topology_rebuild_correctness`：至少覆盖 monitor 增加、移除、primary 切换、monitor 不可用恢复各 `>= 1` 次
- 统计时间窗：
  - 主窗：单次完整 S2b 验收窗口（仅统计无 Host/Edge 重启的连续窗口）
  - 异常窗：monitor topology 变化场景各自独立记录起止时间
- 百分位算法：Nearest-rank（剔除前 10 个预热样本；仅 `capture_to_ingest_latency_ms` 观测使用）
- proof sample 排除规则（必填）：legacy `/api/*`、alias-only payload、mixed-version 样本、`broken_window=true` 样本不得进入 Gate proof。
  - `alias-only payload`：仅通过兼容键名映射勉强入库、但缺少 v3 主契约字段组合（如缺失标准 `capture_trigger` 或 `device_name`）的样本
  - `mixed-version`：同一统计窗口内混入 P1-S1 历史帧、旧 `/api/*` 写入样本或未满足 S2a+/S2b 字段契约的新旧协议混合样本
  - `broken_window=true`：窗口内发生 Host/Edge 重启、导致时间窗与 worker/topology 状态不连续的样本

## 3. 验收步骤与场景 (Executable Scenarios)

### 3.1 核心路由场景验证表

本表定义了 Trigger -> Monitor 路由的基准预期。每一行必须通过日志审计或数据校验。

| 场景 ID | 场景标签 | 触发动作 (Trigger) | 目标 Monitor (Target) | 截图设备 (Device) | 预期 capture_trigger | 预期 app/window | 备注 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| SC-R1 | same-monitor switch by click | click (Monitor A) | Monitor A | Monitor A | click | Monitor A 焦点应用 | 同屏点击路由 |
| SC-R2 | cross-monitor switch by click | click (Monitor B) | Monitor B | Monitor B | click | Monitor B 焦点应用 | 跨屏点击路由 |
| SC-F1 | secondary-monitor app_switch | app_switch (Monitor B) | Monitor B | **NULL** | **(None)** | **NULL** | PRIMARY_MONITOR_ONLY=true 目标副屏路由过滤，无 frame 持久化 |
| SC-I1 | per-enabled-monitor idle | idle (Monitor A) | Monitor A | Monitor A | idle | Monitor A 应用 (若焦点) | 独立闲置倒计时 |
| SC-I2 | non-focused idle frame | idle (Monitor B) | Monitor B | Monitor B | idle | null / null | 非焦点屏截图时 app/window 必须显式为 null |
| SC-O1 | one user action | click + app_switch | Monitor A | Monitor A | click / app_switch | Monitor A 焦点应用 | 同屏双触发：去重后至少保留一份一致 frame |

### 3.2 验证准则

1. **`routing_filtered` 规则**: 若目标 monitor 未启用（如 `PRIMARY_MONITOR_ONLY=true` 时的副屏），Coordinator 必须静默丢弃该 trigger。验收表现为：无 spool 文件产生，无数据库 frame 记录。
2. **`null` 规则**: 若截图 monitor 非当前系统焦点屏幕（Active Monitor），其 `app_name` 和 `window_name` 必须写入 `null`。**机械验证要求**: 检查 SQLite 中对应 `device_name` 非活跃时的记录，确保字段显式为 NULL，禁止复用该 monitor 上次的活跃值。
   - **职责澄清**: Coordinator 负责选择目标 monitor；monitor worker 在执行实际截图后确认最终 `device_name` 绑定。若两者不一致，应视为 topology race / binding failure，而不是静默纠正。
3. **`one user action` 规则**: 单次交互（如点击 Dock 切换应用）若同时发出 `click` 和 `app_switch` 事件，Coordinator 应在 `min_capture_interval_ms` 窗口内去抖：
   - **默认行为**：同一 monitor 在 `min_capture_interval_ms`（默认 1000ms）窗口内只保留第一个 trigger，后续 trigger 被丢弃且不执行截图
   - **验收表现**：spool 目录只产生一个 capture 文件（单个 `capture_id`）
   - **异常情形**：若因 debounce 机制失效产生两份，其截图内容应具有时间一致性
4. **重复 capture 定义**: `single_monitor_duplicate_capture_rate` 中的"重复 capture"指：
   - 同一 `device_name`（单 monitor 作用域）
   - 实际产生了 >1 个持久化 frame（被 debounce 丢弃的不计入）
   - 这些 frames 归属于同一 user action，且落在同一 `min_capture_interval_ms` 窗口内
   - **不计入情形**: debounce 阶段被丢弃的 trigger（未产生 frame）、不同 user action 产生的 frame（即使时间接近）、明确属于跨 monitor 并行 capture 的多帧

5. **`topology_rebuild_correctness` 判定规则**:
   - **时间预算**: monitor 变化后，worker 集合重建应在 **10 秒内**完成（观测，non-blocking）
   - **零丢失**: topology 变化期间，已路由到有效 monitor 的 trigger 不得丢失
   - **一致性**: `MonitorRegistry.snapshot()` 与 `/v1/health.capture_runtime.active_monitors` 返回的 monitor 列表必须一致
   - **恢复确认**: SC-T4 场景中，恢复后首个 capture 的 `device_name` 必须与变化前同一物理 monitor 一致（验证 device_name 稳定性）

### 3.3 Topology Rebuild 场景验证表

本表定义了 monitor topology 变化的验收场景。每一行必须通过日志审计或数据校验。

| 场景 ID | 场景标签 | 前置条件 | 具体操作 | 期望行为 | 验证方式 | 证据要求 |
|:---|:---|:---|:---|:---|:---|:---|
| SC-T1 | monitor 增加 | 单屏运行中 | 连接第二个显示器 | 新 monitor 在 `MonitorRegistry` 中可见；对应 worker 启动并响应 routing | `GET /v1/health.capture_runtime.active_monitors` 数量 +1；新 device 有 capture 记录 | health 快照前后对比 + 日志 `device_name binding added` |
| SC-T2 | monitor 移除 | 双屏运行中 | 断开副屏连接线 | 移除的 monitor 从 Registry 清除；对应 worker 优雅停止；不再向该 device 路由 trigger | health 返回的 monitor 数量 -1；该 device 不再有新 capture | health 快照 + 日志 `device_name binding removed` |
| SC-T3 | primary 切换 | 双屏运行，副屏设为 primary | 系统设置中切换 primary 显示器 | `PRIMARY_MONITOR_ONLY=true` 时，仅新 primary 响应 trigger；worker 集合按新 primary 重建 | 切换后所有 capture 的 `device_name` 均为新 primary | health 快照 + capture 记录 device_name 分布 |
| SC-T4 | monitor 不可用恢复 | 某 monitor 临时断开（如休眠）后重新连接 | 重新唤醒副屏 | monitor 重新注册；worker 重新启动；routing 恢复正常 | 重新连接后 30s 内该 device 产生 capture | 日志时间线 + capture 记录 |

## 4. 结果与指标

### 4.1 数值指标

- `trigger_target_routing_correctness`（目标 = 100%）：
- `device_binding_correctness`（目标 = 100%）：
- `single_monitor_duplicate_capture_rate`（目标 = 0%）：
- `topology_rebuild_correctness`（目标 = 100%）：

### 4.1b Soft KPI（观测，non-blocking）

- `capture_to_ingest_latency_ms`（按 `device_name` 分桶记录 P50/P90/P95/P99；若未达样本条件需注明原因并附整改动作）：

### 4.2 功能完成度指标（强制）

- 功能清单完成率（目标 100%）：
- API/Schema 契约完成率（目标 100%）：
- 关键功能用例通过率（目标 >= 95%）：

## 5. 结论

- Gate 结论：`Pass` | `Fail`
- 依据：
- 阻塞项（若 Fail 必填）：

## 6. 风险与后续动作

- 风险：monitor topology 变化处理不完整会导致 `device_name` 漂移或 capture 漏采。
- 后续动作：若多屏 routing 不稳定，优先收紧 coordinator 归属规则。

## 7. Exit Gate 与后续阶段

### 7.1 Exit Gate（允许进入后续阶段）

满足以下全部条件方可退出 P1-S2b：

- 本文档 §5 Gate 结论为 `Pass`
- 所有 Hard Gate 指标达标（routing correctness、device_binding、duplicate_capture_rate、topology_rebuild）
- 验收证据齐全（日志、指标汇总、health 快照、spool 一致性检查）

### 7.2 后续阶段路径

从 P1-S2b Exit Gate 后，进入路径为：

1. **P1-S3（OCR Processing）** — 主线必经
   - 说明：OCR-only 主线只依赖 S2b Pass 后的 capture-completion 产物

2. **P1-S2b+（感知哈希实现）** — 可选增强
   - 说明：若执行，仅增加内容相似度观测/工具能力，不得阻塞 S3 主线
   - 详见：`docs/v3/acceptance/phase1/p1-s2b-plus.md`

### 7.3 与 P1-S2b+ 的衔接

- **主线依赖**：S3 只依赖 S2b Pass；S2b+ 若执行，不得反向收紧 S2b/S3 Entry Gate
- **功能增强**：S2b+ 在 S2b 的 capture completion 基础上，增加内容相似度观测/工具能力
- **Gate 判定**：`single_monitor_duplicate_capture_rate` 的 Hard Gate 归属 S2b，不依赖 S2b+ 的 simhash 技术
- **语义边界**：S2b+ 不修改 S2b 已冻结的 routing、device_name binding、topology 等核心语义
