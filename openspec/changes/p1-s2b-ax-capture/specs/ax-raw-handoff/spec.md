## ADDED Requirements

### Requirement: AX paired capture raw handoff
系统 MUST 在每次有效 `capture_trigger` 对应的 per-monitor capture cycle 中，于 screenshot 完成后、写入 Host spool 前执行 macOS AXUIElement 遍历，并产出 raw `accessibility_text` handoff。该能力 MUST 仅适用于 macOS v3 Host 主链路，并固定遵守 `walk_timeout=500ms`、`max_depth=30`、`max_nodes=5000` 的上界。系统 MUST 保留 `idle`、`app_switch`、`manual`、`click` 作为唯一允许的 `capture_trigger` 值，不得在 S2b 中引入新的 trigger 语义。

Acceptance impact: 该要求冻结 S2b AX 遍历预算与 trigger 采样口径；`AX walk P95 < 500ms`、样本覆盖范围与 required trigger 枚举必须按本要求验证。

#### Scenario: Produce raw AX handoff in the same capture cycle
- **WHEN** Host 在 v3 主链路中消费一个合法 `capture_trigger` 并完成 screenshot
- **THEN** 系统 MUST 在同一 capture cycle 中执行 AX 遍历，并在写入 spool 前得到该帧对应的 raw `accessibility_text`

#### Scenario: Produce raw handoff inside the monitor worker that captured the screenshot
- **WHEN** 一个 `MonitorWorker` 为某次 trigger 执行 paired capture
- **THEN** 该 worker MUST 同时拥有 screenshot、AX handoff、`final_device_name` 与 dedup 判定的 owner，而不得把 raw handoff 延后给 uploader 或 server 再补齐

#### Scenario: Bound AX traversal by S2b limits
- **WHEN** AX 树规模超过正常范围或页面结构复杂
- **THEN** 系统 MUST 仍以 `walk_timeout=500ms`、`max_depth=30`、`max_nodes=5000` 作为强制边界，并不得无限阻塞 capture cycle

### Requirement: Raw handoff field contract
系统 MUST 在 `POST /v1/ingest` 的新上报 payload 中始终携带 `accessibility_text` 与 `content_hash` 两个 key。`accessibility_text` MUST 为 required string，允许 `""`，禁止 `null`；`content_hash` MUST 为 required nullable string，允许 `null`，禁止 `""`。当 AX 成功返回但最终文本为空，或当能力闭环要求上传空 AX 样本时，系统 MUST 使用 `accessibility_text=""` 与 `content_hash=null` 表达 empty-AX no-drop handoff。

Acceptance impact: 该要求冻结 `/v1/ingest` 的 required-key 矩阵；S2b handoff 字段矩阵测试与 mixed-version 样本过滤必须按此契约执行。

#### Scenario: Accept empty-AX as a valid raw handoff
- **WHEN** 某帧的 AX 遍历完成但最终 `accessibility_text` 为空字符串
- **THEN** 系统 MUST 继续上传该帧，并使用 `accessibility_text=""` 与 `content_hash=null` 作为唯一合法表达

#### Scenario: Reject missing required handoff keys
- **WHEN** 新上报 payload 缺失 `accessibility_text` 或 `content_hash`，或把 `accessibility_text` 设为 `null`，或把 `content_hash` 设为 `""`
- **THEN** `/v1/ingest` MUST 将该请求视为 contract failure 并拒绝其进入 S2b 正确性主链路

### Requirement: Partial AX text remains valid raw output
系统 MUST 将 AX timeout 后已成功收集到的 partial text 视为有效 raw output，而不是把该样本强制降格为 empty-AX。若 timeout 前已经得到非空 `accessibility_text`，系统 MUST 按最终上报文本继续完成 `content_hash` 计算与后续 handoff。

Acceptance impact: 该要求冻结 `test_p1_s2b_ax_timeout.py` 的断言口径；AX timeout 样本必须能够区分 empty-AX 与 partial-text success。

#### Scenario: Preserve partial text after timeout
- **WHEN** AX 遍历在超时前已经收集到部分文本，但未能完整走完树
- **THEN** 系统 MUST 以上述部分文本作为最终 `accessibility_text` 继续 handoff，而不是把该帧改写为 `accessibility_text=""`

### Requirement: Capture outcome classification for raw handoff
系统 MUST 将每个 capture cycle 的 S2b raw-handoff 结果归类到有限 outcome 集合：`capture_completed`、`ax_empty`、`ax_timeout_partial`、`browser_url_rejected_stale`、`permission_blocked`、`dedup_skipped`、`spool_failed`、`schema_rejected`。这些 outcome MUST 只表达 raw handoff、capability、transport 与 contract 事实，而不得承载 S3 的 `text_source`、OCR fallback 或 search 语义。

Note: recorder MUST 在 upload 前归类 `capture_completed`、`ax_empty`、`ax_timeout_partial`、`browser_url_rejected_stale`、`permission_blocked`、`dedup_skipped`、`spool_failed`；`schema_rejected` 明确由 `/v1/ingest` 对非法 payload 进行 contract-failure 归类。两阶段共同构成完整的 S2b outcome 矩阵。

Acceptance impact: 该要求冻结 S2b evidence 的结果分类口径；日志、指标、Gate 报表与人工验收必须能区分上述 outcome，而不是把不同失败路径混成空 AX 或 generic failure。

### Requirement: capture_cycle_latency is a required acceptance artifact
系统 MUST 记录完整 `capture_cycle_latency`，其口径固定为 `TriggerBus`/worker dequeue -> `final_device_name` 绑定 -> screenshot -> AX walk -> Browser URL -> `content_hash` -> dedup 判定 -> spool write 完成。该指标 MUST 作为 S2b acceptance artifact 输出，用于区分“AX walk 本身达标”与“完整 paired capture 周期达标”。

Acceptance impact: 阶段收口时必须导出 `capture_cycle_latency` 观测结果；仅验证 `AX walk P95 < 500ms` 不足以替代完整 capture cycle 证据。

#### Scenario: Export capture-cycle latency as evidence
- **WHEN** S2b Gate evidence 被汇总
- **THEN** 系统 MUST 同时提供 `AX walk` 观测与完整 `capture_cycle_latency` 观测，而不得以前者替代后者

#### Scenario: Classify timeout with partial text separately from empty-AX
- **WHEN** AX 遍历超时，但最终 `accessibility_text` 非空
- **THEN** 系统 MUST 将该样本记为 `ax_timeout_partial`，而不是 `ax_empty`

#### Scenario: Classify schema rejection as contract failure
- **WHEN** `/v1/ingest` 收到缺失 required handoff key 或非法值的 payload
- **THEN** 系统 MUST 将该样本记为 `schema_rejected`，并将其排除在成功 handoff 样本之外
