## ADDED Requirements

### Requirement: Fixed Host-to-Edge state reporting contract
系统 MUST 使用固定内部端点 `POST /heartbeat` 作为 Host 状态上报入口，MUST NOT 使用“或等价入口”并行实现。该 payload MUST 同时承载权限快照与 trigger_channel 采样，且采样频率必须可区分配置：权限快照 5s、trigger_channel 1Hz。

### Requirement: Heartbeat payload field completeness and freshness
`POST /heartbeat` payload MUST 至少包含 `capture_permission_status`、`capture_permission_reason`、`last_permission_check_ts`、`queue_depth`、`queue_capacity`、`collapse_trigger_count`、`overflow_drop_count`。Server MUST 以 TTL=60s 判定权限快照新鲜度，超时后 `/v1/health` MUST 返回 `capture_permission_reason=stale_permission_state` 且 `status` 不得为 `ok`。

#### Scenario: Report permission snapshot and trigger_channel through one fixed endpoint
- **WHEN** Host 周期性发送状态上报
- **THEN** 系统 MUST 通过 `POST /heartbeat` 单一路径上报权限快照（5s）与 trigger_channel 采样（1Hz）并在服务端镜像存储

#### Scenario: Degrade health when heartbeat snapshot is stale
- **WHEN** 最近权限快照超过 60 秒未更新
- **THEN** `/v1/health` MUST 返回非 `ok` 状态并暴露 `capture_permission_reason=stale_permission_state`
