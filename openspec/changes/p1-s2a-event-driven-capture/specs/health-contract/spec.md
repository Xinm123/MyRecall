## MODIFIED Requirements

### Requirement: GET /v1/health permission-aware status contract
系统 MUST 在 `GET /v1/health` 响应中返回完整权限字段集合：`capture_permission_status`、`capture_permission_reason`、`last_permission_check_ts`。权限一致性语义 MUST 满足：当权限处于 `denied_or_revoked` 或 `recovering` 时，`status` MUST 至少为 `degraded`，不得返回 `ok`。权限恢复后，状态回归 MUST 基于连续成功阈值达标，而不是单次成功即恢复。

### Requirement: GET /v1/health stale permission snapshot contract
若权限状态快照超过 60 秒未更新，`GET /v1/health` MUST 返回非 `ok` 的 `status`（至少为 `degraded`），并返回 `capture_permission_reason=stale_permission_state`。

#### Scenario: Prevent ok status during permission recovery
- **WHEN** 权限已从失效转入 `recovering` 但尚未达到连续成功阈值
- **THEN** `/v1/health` MUST 返回非 ok 的 `status` 并持续暴露 `capture_permission_status=recovering`

#### Scenario: Expose stale permission snapshot as degraded
- **WHEN** 权限状态快照超过 60 秒未更新
- **THEN** `/v1/health` MUST 返回非 ok 的 `status` 且 `capture_permission_reason=stale_permission_state`
