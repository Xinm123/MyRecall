## ADDED Requirements

### Requirement: Grid as status-sync source of truth
系统 MUST 将 Grid（`/`）作为上传/入队状态同步主视图；Timeline（`/timeline`）仅用于新帧可见与时间定位验证。P1-S2a 中 `pending -> completed` 状态收敛必须可验证，不得退回 legacy `screenshots/*.png` 依赖。

### Requirement: Status convergence observability for UI verification
系统 MUST 提供可用于验收脚本复核的状态收敛口径：新 capture 从 `queued/pending` 到 `completed` 的收敛时间分布可读，并支持 `P95 <= 8s` 的 Gate 判定。

#### Scenario: Show degraded state on permission failure in Grid health anchor
- **WHEN** `/v1/health` 返回 `capture_permission_status=denied_or_revoked` 或 `recovering`
- **THEN** Grid 的 `#mr-health` MUST 呈现 `data-state="degraded"` 且不得误报 `healthy`

#### Scenario: Verify timeline visibility without becoming status-sync authority
- **WHEN** 新 capture 写入并可通过 `/v1/frames/:frame_id` 读取
- **THEN** Timeline MUST 可见该新帧并可按时间定位，但状态同步主判定仍以 Grid 为准
