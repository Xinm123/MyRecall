## ADDED Requirements

### Requirement: Health permission status exposure
系统 MUST 通过 `/v1/health` 暴露 `capture_permission_status`，并与 UI 健康锚点保持一致。若权限状态为 `denied_or_revoked` 或 `recovering`，健康语义 MUST 不返回 `ok`，且页面状态锚点 `#mr-health` 的 `data-state` 必须为 `degraded`（不得误报为 `healthy`）。

### Requirement: Health permission field completeness
系统 MUST 在 `/v1/health` 中同时暴露 `capture_permission_status`、`capture_permission_reason`、`last_permission_check_ts`，且三者 MUST 对应同一次权限轮询结果。

#### Scenario: Reflect degraded health when permission is unavailable
- **WHEN** 权限状态进入 `denied_or_revoked` 或 `recovering`
- **THEN** 系统 MUST 返回非 ok 健康状态并使 UI 以 `#mr-health` 与 `data-state` 呈现 `degraded`

#### Scenario: Return complete permission fields in health response
- **WHEN** 客户端请求 `/v1/health`
- **THEN** 响应 MUST 包含 `capture_permission_status`、`capture_permission_reason` 与 `last_permission_check_ts`
