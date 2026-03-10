## ADDED Requirements

### Requirement: Global debounce gate for all triggers
系统 MUST 对全触发路径应用统一去抖门控，参数 `min_capture_interval_ms` 在 P1 默认值为 1000。该门控 MUST 同时约束事件触发、manual 触发与 idle fallback 触发，确保同一 monitor 的高频触发不会产生违规入库间隔。

#### Scenario: Reject trigger inside debounce interval
- **WHEN** 同一 monitor 在上一次已接受触发后不足 1000ms 再次到达可触发事件
- **THEN** 系统 MUST 拒绝该触发进入下游采集与入队流程
