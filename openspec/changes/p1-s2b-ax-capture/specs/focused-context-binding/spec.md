## ADDED Requirements

### Requirement: focused_context one-shot assembly
系统 MUST 将 `focused_context` 视为同一轮 capture cycle 内一次性产出的 bundle：`{app_name, window_name, browser_url}`。`app_name`、`window_name`、`browser_url` MAY 单独为 `None`，但三者 MUST 来自同一轮 snapshot 结果，不得把不同时间点或不同来源的字段事后混拼为一个 `focused_context`。

Acceptance impact: 该要求冻结 focused-context 一致性样本的判断标准；S2b focused-context 验收必须以同轮 bundle 为真值，而不是以单字段命中率替代。

#### Scenario: Keep partially known focused_context without mixing fields
- **WHEN** 同一轮 snapshot 只能确认 `app_name`，但无法可靠确认 `window_name` 或 `browser_url`
- **THEN** 系统 MUST 仅返回已确认字段，并将其余字段写为 `None`，不得补入来自其他时间点或其他来源的值

#### Scenario: Reject field-level mixing across snapshots
- **WHEN** `app_name`、`window_name`、`browser_url` 需要跨多轮查询才能拼出一个非空组合
- **THEN** 系统 MUST 放弃该混拼结果，并仅保留来自单轮 snapshot 的一致字段集合

### Requirement: capture-time device_name binding
系统 MUST 将最终写入 payload、spool metadata、dedup bucket 与 Gate evidence 的 `device_name` 绑定到实际截图发生的 monitor，而不是绑定到 event source 提供的预估值。若内部事件仍携带设备 hint，该 hint MUST 明确视为 `event_device_hint`，MAY 仅用于路由或诊断，但不得成为 persisted truth。迁移期允许内部 debounce、trigger route 或队列消费继续读取 `event_device_hint`，但任何上传、落盘、proof sample 与统计分桶都 MUST 只使用 `final_device_name`。

Acceptance impact: 该要求冻结 `device_name` binding 的证明口径；`inter_write_gap_sec`、dedup bucket、device binding 测试与证据导出必须按最终 screenshot monitor 分桶。

#### Scenario: Persist final capture-time device binding
- **WHEN** recorder 消费某个 trigger 并对实际 monitor 执行截图
- **THEN** 系统 MUST 以该 monitor 的最终绑定结果作为 `device_name` 写入 payload 与后续证据口径

#### Scenario: Prefer final device_name over event hint
- **WHEN** 事件源携带的设备 hint 与实际截图 monitor 不一致
- **THEN** 系统 MUST 以 capture-time 绑定得到的 `device_name` 为准，并不得把 hint 上传为最终值

#### Scenario: Preserve proof semantics during device-hint migration
- **WHEN** 迁移期内部仍保留 `event_device_hint` 字段用于 debounce 或路由
- **THEN** proof sample、dedup bucket、`inter_write_gap_sec` 与最终 payload 仍 MUST 只按 `final_device_name` 解释

### Requirement: Trigger broadcast and per-monitor worker ownership
系统 MUST 将 S2b 的 Host capture 拓扑解释为 `TriggerSource -> TriggerBus(broadcast) -> MonitorWorker[N]`。`TriggerSource` MUST 只发布 `TriggerIntent`，而不得发布最终 monitor truth；`TriggerBus` MUST 负责 fan-out 且不得因为单个 monitor worker 变慢而阻塞其它 monitor；每个 `MonitorWorker` MUST 独占一个 monitor binding，并在同一 capture cycle 内完成 screenshot、focused-context snapshot、Browser URL、`content_hash`、dedup 与 outcome 分类。只有 `MonitorWorker` MAY 产生 `final_device_name`。

Acceptance impact: 该要求冻结 S2b 的 trigger topology 与 owner boundary；实现与验收都必须能证明 `final_device_name` 来源于 per-monitor worker，而不是 event source 预绑定。

#### Scenario: Fan out one trigger intent to all monitor workers
- **WHEN** Host 接收到一个合法 `TriggerIntent`
- **THEN** 系统 MUST 将其 broadcast 给所有活跃 `MonitorWorker`，并允许每个 worker 独立决定是否为自己的 monitor 执行 paired capture

#### Scenario: Keep final device ownership inside monitor worker
- **WHEN** 任一 `MonitorWorker` 为某次 trigger 执行截图
- **THEN** 只有该 worker 的 monitor binding MAY 成为最终上传的 `device_name`

### Requirement: Better None than wrong for focused metadata
当系统无法确认 `window_name`、`browser_url` 或其与 screenshot 的同轮一致性时，系统 MUST 写 `None`，而不是猜测填充非空值。任何已确认错误的非空 `window_name` 或 `browser_url` 都 MUST 被视为 S2b failure，而不是可接受的近似值。系统 MUST 为 focused-context 错填保留可统计证据口径；不确定样本记为 `None` 不计错填，确认错误的非空值必须进入 mismatch/failure 统计。

Acceptance impact: 该要求冻结 focused-context 与 `browser_url` 的 false-positive 禁止规则；S2b required evidence 只能把确认正确的非空值计为成功样本。

#### Scenario: Emit None for uncertain window binding
- **WHEN** 系统无法可靠判断当前 screenshot 对应哪个前台窗口
- **THEN** `window_name` MUST 为 `None`，并且该帧不得通过猜测得到非空窗口名
