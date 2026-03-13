## ADDED Requirements

### Requirement: Input Monitoring permission state machine
系统 MUST 以 Input Monitoring 专用检测链路作为权限真值来源；在 Terminal-mode P1 中，该链路指向 listen-only `CGEventTapCreate` capability probe，而不是通用权限 API 可见性。系统 MUST 对外暴露四态状态机：`granted`、`transient_failure`、`denied_or_revoked`、`recovering`。状态转移 MUST 使用冻结参数 `REQUIRED_CONSECUTIVE_FAILURES=2`、`REQUIRED_CONSECUTIVE_SUCCESSES=3`、`permission_poll_interval_sec=10`、`EMIT_COOLDOWN_SEC=300`。系统 MUST NOT 通过空白截图、OCR 为空、`browser_url` 缺失或其他非权限信号推断权限丢失。

**Acceptance impact**
- Hard Gate: 权限场景矩阵通过率 MUST 为 100%。
- Frozen thresholds: `REQUIRED_CONSECUTIVE_FAILURES=2`、`REQUIRED_CONSECUTIVE_SUCCESSES=3`、`permission_poll_interval_sec=10`、`EMIT_COOLDOWN_SEC=300`.

#### Scenario: Startup without confirmed permission enters degraded transient state
- **WHEN** 系统启动时尚未确认 Input Monitoring 可用，且首次权限检测未得到稳定成功结果
- **THEN** 系统 MUST 对外暴露 `capture_permission_status=transient_failure`，并进入可恢复的降级路径而不是伪装为 `granted`

#### Scenario: startup_not_determined is not a fifth external state
- **WHEN** 自动化测试或手测流程使用 `startup_not_determined` 指代启动时尚未确认权限的内部条件
- **THEN** 该条件 MUST 在外部契约上表现为 `capture_permission_status=transient_failure`，而不是新增第五个对外状态

#### Scenario: Consecutive failures enter denied_or_revoked
- **WHEN** Input Monitoring 权限检测连续 2 次失败
- **THEN** 系统 MUST 将状态转移到 `denied_or_revoked`

#### Scenario: Recovery requires consecutive successes
- **WHEN** 系统处于 `denied_or_revoked` 且随后检测到权限恢复
- **THEN** 系统 MUST 先进入 `recovering`，并且只有在连续 3 次成功后才可回到 `granted`

### Requirement: Permission reason reflects the latest permission check outcome
系统 MUST 为每次权限状态快照记录与最新检测结果一致的 `capture_permission_reason` 和 `last_permission_check_ts`。`capture_permission_reason` MUST 能区分稳定授权、暂态失败、Input Monitoring denied/revoked，以及陈旧快照语义；实现 MAY 细化底层原因码，但 MUST NOT 让 `granted` 以外的状态返回 `capture_permission_reason=granted`。

#### Scenario: Startup denied exposes a non-granted reason
- **WHEN** 系统启动前 Input Monitoring 已被拒绝或撤销
- **THEN** 系统 MUST 暴露 `capture_permission_status=denied_or_revoked`，且 `capture_permission_reason` MUST 不是 `granted`

#### Scenario: Latest check timestamp is preserved
- **WHEN** 系统完成一次权限检测
- **THEN** 系统 MUST 更新 `last_permission_check_ts`，并使随后暴露的权限字段对应同一次检测结果
