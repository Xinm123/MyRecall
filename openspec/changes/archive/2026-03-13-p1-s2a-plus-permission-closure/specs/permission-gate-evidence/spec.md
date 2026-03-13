## ADDED Requirements

### Requirement: S2a+ implementation ships a dedicated automated verification file
系统 MUST 交付独立测试文件 `tests/test_p1_s2a_plus_permission_fsm.py`，且该文件 MUST 至少覆盖以下场景：`startup_not_determined`、`startup_denied`、`revoked_mid_run`、`restored_after_denied`、`stale_permission_state`，以及 `/v1/health` 权限字段完整性。其中 `startup_not_determined` 是启动时内部条件名；其外部契约 MUST 表现为 `capture_permission_status=transient_failure`。

**Acceptance impact**
- Required evidence: `tests/test_p1_s2a_plus_permission_fsm.py`.
- Required scenario set: `test_startup_not_determined_health_degraded()`、`test_startup_denied_transitions_to_denied_or_revoked()`、`test_mid_run_revoked_stops_capture_and_degrades_health()`、`test_restored_after_denied_recovers_to_granted()`、`test_stale_permission_snapshot_forces_degraded_health()`、`test_health_contract_contains_permission_fields()`.

#### Scenario: Missing required test file fails local gate verification
- **WHEN** `tests/test_p1_s2a_plus_permission_fsm.py` 不存在、未实现或未通过
- **THEN** P1-S2a+ 本机 Gate 验证 MUST 失败，且阶段 MUST NOT 推进到 P1-S2b

#### Scenario: Automated suite covers the frozen S2a+ matrix
- **WHEN** 系统声明已完成 P1-S2a+ 的自动化验证
- **THEN** 上述 6 个强制测试场景 MUST 可追溯到独立测试文件中的实现

### Requirement: S2a+ implementation ships a dedicated local gate entrypoint script and evidence bundle
系统 MUST 交付独立本机 Gate 执行脚本 `scripts/acceptance/p1_s2a_plus_local.sh`，并输出最小证据集合：`p1-s2a-plus-local-gate.log`、`p1-s2a-plus-permission-transitions.jsonl`、`p1-s2a-plus-health-snapshots.json`、`p1-s2a-plus-ui-proof.md`、`p1-s2a-plus-context.json`。`p1-s2a-plus-context.json` MUST 记录 `Terminal mode`、git rev、时间窗和相关环境变量。

**Acceptance impact**
- Required evidence bundle: `p1-s2a-plus-local-gate.log`、`p1-s2a-plus-permission-transitions.jsonl`、`p1-s2a-plus-health-snapshots.json`、`p1-s2a-plus-ui-proof.md`、`p1-s2a-plus-context.json`.
- Execution constraint: evidence MUST record `Terminal mode` as the P1 limitation.

#### Scenario: Local gate run emits the minimum evidence set
- **WHEN** 运行 S2a+ 本机 Gate 执行脚本
- **THEN** 系统 MUST 生成完整的最小证据集合，而不是仅输出日志或人工说明

#### Scenario: Context file records Terminal mode limitation
- **WHEN** 生成 `p1-s2a-plus-context.json`
- **THEN** 该文件 MUST 记录当前运行模式为 `Terminal mode`，并包含 git rev、时间窗与权限相关环境变量快照
