## ADDED Requirements

### Requirement: Permission state machine lifecycle
系统 MUST 实现四态权限状态机，状态集合必须为 `granted`、`transient_failure`、`denied_or_revoked`、`recovering`。状态转移 MUST 使用固定参数：`REQUIRED_CONSECUTIVE_FAILURES=2`、`REQUIRED_CONSECUTIVE_SUCCESSES=3`、`EMIT_COOLDOWN_SEC=300`、`permission_poll_interval_sec=10`。当状态为 `denied_or_revoked` 或 `recovering` 时，系统 MUST 进入受控降级。

#### Scenario: Enter denied_or_revoked after consecutive failures
- **WHEN** 权限检测连续 2 次失败并达到失效阈值
- **THEN** 系统 MUST 将状态转移到 `denied_or_revoked` 并开始受控降级流程
