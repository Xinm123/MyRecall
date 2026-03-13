## ADDED Requirements

### Requirement: Health response includes complete permission fields
`GET /v1/health` MUST 同时返回 `capture_permission_status`、`capture_permission_reason`、`last_permission_check_ts`，并且三者 MUST 对应同一次权限快照。健康响应 MUST 继续遵守 `docs/v3/spec.md` 中的外部契约，不得把权限语义拆到独立接口或 UI 私有状态中。

#### Scenario: Health response always includes permission fields
- **WHEN** 客户端请求 `GET /v1/health`
- **THEN** 响应 MUST 包含 `capture_permission_status`、`capture_permission_reason`、`last_permission_check_ts`

#### Scenario: Permission fields come from one snapshot
- **WHEN** 系统返回一次健康响应
- **THEN** 三个权限字段 MUST 对应同一次权限轮询或镜像快照，而不是混合不同时间点的值

### Requirement: Health status degrades on denied, recovering, or stale permission state
当 `capture_permission_status` 为 `denied_or_revoked` 或 `recovering` 时，`GET /v1/health.status` MUST NOT 返回 `ok`。当 `now_utc - last_permission_check_ts > 60s` 时，系统 MUST 将健康状态降级，并将 `capture_permission_reason` 设为 `stale_permission_state`，即使最近一次已知权限状态值仍为 `granted`。该陈旧语义 MUST 同时表现为：触发条件是快照超时、health contract 中 reason 变为 `stale_permission_state` 且 `status != ok`、UI 呈现为 degraded。

**Acceptance impact**
- Hard Gate: `/v1/health` 权限字段完整性与状态语义正确率 MUST 为 100%。
- Frozen stale threshold: `now_utc - last_permission_check_ts > 60s`.

#### Scenario: Recovering never reports ok
- **WHEN** 权限状态为 `recovering`
- **THEN** `GET /v1/health.status` MUST NOT 返回 `ok`

#### Scenario: Denied permission never reports ok
- **WHEN** 权限状态为 `denied_or_revoked`
- **THEN** `GET /v1/health.status` MUST NOT 返回 `ok`

#### Scenario: Stale permission snapshot forces degraded health
- **WHEN** 最近一次权限快照距离当前时间超过 60 秒
- **THEN** `GET /v1/health.status` MUST NOT 返回 `ok`，并暴露 `capture_permission_reason=stale_permission_state`

### Requirement: UI health anchor follows the health contract
页面级健康锚点 `#mr-health` MUST 根据 `/v1/health` 的权限字段和健康状态收敛到 `data-state="degraded"`，当权限为 `denied_or_revoked`、`recovering` 或 `stale_permission_state` 时不得显示为 `healthy`。

#### Scenario: UI degrades on stale permission state
- **WHEN** `/v1/health` 返回 `capture_permission_reason=stale_permission_state`
- **THEN** `#mr-health` MUST 呈现 `data-state="degraded"`

#### Scenario: UI degrades on denied or recovering permission
- **WHEN** `/v1/health` 返回 `capture_permission_status=denied_or_revoked` 或 `capture_permission_status=recovering`
- **THEN** `#mr-health` MUST 呈现 `data-state="degraded"`
