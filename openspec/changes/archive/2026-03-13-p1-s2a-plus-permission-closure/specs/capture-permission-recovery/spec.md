## ADDED Requirements

### Requirement: Capture enters controlled degradation when Input Monitoring is unavailable
当 Input Monitoring 权限状态进入 `denied_or_revoked` 时，系统 MUST 进入受控降级：停止继续消费外部事件触发进行 capture，并保持 recorder 主循环、权限轮询与健康上报仍然存活。系统 MUST 提供可见的恢复提示，而不是在权限已失效时静默继续表现为稳定运行。

**Acceptance impact**
- Hard Gate: 权限丢失后 capture 进入受控降级 MUST 为 100%。

#### Scenario: Mid-run revoke stops external event-driven capture
- **WHEN** 系统运行中权限从 `granted` 经失败阈值转移到 `denied_or_revoked`
- **THEN** 系统 MUST 停止继续消费外部事件触发进行新的 capture

#### Scenario: Degraded mode keeps liveness signals active
- **WHEN** 系统处于 `denied_or_revoked`
- **THEN** recorder MUST 继续执行权限轮询与状态上报，以便后续自动恢复和陈旧快照判定仍然有效

### Requirement: Restored permission auto-recovers without process restart
当 Input Monitoring 在 `denied_or_revoked` 之后恢复可用时，系统 MUST 无需人工重启进程即可自动恢复。恢复路径 MUST 为 `denied_or_revoked -> recovering -> granted`，并在达到连续成功阈值前保持 `GET /v1/health.status MUST NOT return ok` 的健康契约语义。

**Acceptance impact**
- Hard Gate: 权限恢复后自动恢复 MUST 为 100%。

#### Scenario: First restored success enters recovering
- **WHEN** 系统处于 `denied_or_revoked` 且首次权限检测成功
- **THEN** 系统 MUST 转移到 `recovering`

#### Scenario: Threshold completion returns capture to normal service
- **WHEN** 系统处于 `recovering` 且连续成功达到 3 次
- **THEN** 系统 MUST 转移到 `granted` 并允许 event-driven capture 恢复正常消费外部事件触发

#### Scenario: Recovery does not require manual restart
- **WHEN** 权限在运行中被恢复
- **THEN** 系统 MUST 自动恢复到可用态，而不要求人工重启 client 或 server 进程
