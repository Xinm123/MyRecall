## ADDED Requirements

### Requirement: Idle fallback capture
系统 MUST 在无事件窗口内提供 idle fallback。若在 `idle_capture_interval_ms=30000` 时间窗内无可执行事件触发，系统 MUST 直接触发一次 `idle` 采集，确保时间轴连续性。该触发语义 MUST 仅由超时条件决定，不得依赖用户活跃判定。

#### Scenario: Trigger idle capture after inactivity window
- **WHEN** 30 秒内未发生可执行事件触发
- **THEN** 系统 MUST 触发一次 `capture_trigger=idle` 的采集请求
