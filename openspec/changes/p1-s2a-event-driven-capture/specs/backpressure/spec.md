## ADDED Requirements

### Requirement: Bounded trigger channel with collapse strategy
系统 MUST 在 trigger -> debounce -> queue -> ingest 链路中引入有界触发通道，并在 lag 场景执行折叠策略。系统 MUST 记录并暴露 `collapse_trigger_count` 与 `overflow_drop_count`，并保证过载窗口内可产生折叠事件且不产生溢出丢弃。

### Requirement: Backpressure observability read contract
系统 MUST 提供统一读取口径用于背压验收：`queue_depth`、`queue_capacity`、`collapse_trigger_count`、`overflow_drop_count`。该口径 MUST 可由 `GET /v1/ingest/queue/status` 读取，并基于 1Hz 采样与 5 分钟窗口进行统计（窗口外样本不得进入分母）。

### Requirement: Backpressure raw evidence export contract
系统 MUST 为背压 Gate 导出可复算原始证据：至少包含 1Hz 采样序列（`ts`、`queue_depth`、`queue_capacity`、`collapse_trigger_count`、`overflow_drop_count`）、窗口标识与计算依据（脚本或 SQL）。仅汇总值不足以通过验收。

#### Scenario: Collapse when channel is lagging
- **WHEN** 触发输入速率持续高于下游处理能力并导致通道接近饱和
- **THEN** 系统 MUST 将多次待处理触发折叠为单次兜底触发并增加 `collapse_trigger_count`

#### Scenario: Read backpressure counters from a single contract surface
- **WHEN** 验收脚本读取 `GET /v1/ingest/queue/status`
- **THEN** 响应 MUST 提供 `queue_depth`、`queue_capacity`、`collapse_trigger_count`、`overflow_drop_count` 的统一口径数据供 `queue_saturation_ratio` 计算

#### Scenario: Export recomputable raw samples for backpressure gate
- **WHEN** 验收脚本生成 P1-S2a 证据包
- **THEN** 系统 MUST 输出背压原始 1Hz 序列与计算依据，使 `queue_saturation_ratio` 可离线复算
