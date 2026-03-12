## ADDED Requirements

### Requirement: Permission state machine remains the AX capability gate
系统 MUST 继续使用四态权限状态机 `granted`、`transient_failure`、`denied_or_revoked`、`recovering` 作为 S2b 权限语义，固定参数 MUST 为连续 2 次失败进入 `denied_or_revoked`、连续 3 次成功恢复到 `granted`、轮询周期 `10s`、冷却时间 `300s`。该状态机 MUST 只表达 AX capability，可观测地约束 paired capture 是否执行 AX walk / URL 提取 / dedup，而不得引入新的语义状态。S2b MUST 将 `accessibility` 与 screenshot 主链路区分建模：本状态机只裁决 AX capability，不裁决 screenshot 主链路是否继续；`transient_failure` 仅作为连续失败统计与观测态，不单独产出 capability-blocked handoff。

Acceptance impact: 该要求冻结权限恢复的 Gate 样本与状态流转参数；startup denied、mid-run revoked、recovered 三类证据必须按本状态机验证。

#### Scenario: Enter denied_or_revoked after two consecutive failures
- **WHEN** 权限检测连续 2 次失败
- **THEN** 系统 MUST 将状态转移到 `denied_or_revoked` 并进入 capability degraded 路径

#### Scenario: Return to granted after three consecutive successes
- **WHEN** 系统处于 `recovering` 且连续 3 次检测成功
- **THEN** 系统 MUST 将状态恢复到 `granted` 并重新允许完整 AX paired capture

#### Scenario: Keep screenshot path outside the AX capability FSM
- **WHEN** screenshot 主链路因非 AX 原因不可用，或 screen recording permission 单独失效
- **THEN** 系统 MUST 将其视为 screenshot path 问题，而不是把该情况解释为 `permission_blocked` 或 AX empty

#### Scenario: Do not classify transient failure as permission-blocked by itself
- **WHEN** 权限检测出现单次失败并进入 `transient_failure`
- **THEN** 系统 MUST 仅记录该状态用于恢复判定与观测，而不得仅凭该状态直接产出 `permission_blocked`

### Requirement: Permission failure is not empty-AX fallback
系统 MUST 将 `permission_blocked` 与普通 empty-AX 区分开。处于 `denied_or_revoked` 或 `recovering` 的 capture MAY 继续截图与 heartbeat，但 MUST 跳过 AX walk / URL 提取 / dedup，并以 `accessibility_text=""`、`content_hash=null`、`browser_url=null` 表达 capability-blocked raw handoff。系统 MUST 为该分支产出可计数 outcome `permission_blocked`，不得仅依赖空字段组合做隐式推断。系统 MUST NOT 将该情况伪装成 OCR fallback、普通 AX empty、或 dedup skip。

Acceptance impact: 该要求冻结 permission-blocked 样本的解释口径；权限相关 evidence、health 输出与 raw handoff 字段矩阵必须把 capability failure 与 empty-AX 分开统计。

#### Scenario: Emit permission-blocked raw handoff while keeping screenshot flow alive
- **WHEN** capture cycle 开始时权限状态为 `denied_or_revoked` 或 `recovering`
- **THEN** 系统 MUST 继续保持 screenshot / heartbeat 主链路，但 MUST 以 capability-blocked 语义上报空 AX handoff，并停止 dedup 判定

#### Scenario: Distinguish permission-blocked from ordinary empty-AX
- **WHEN** 两个样本都满足 `accessibility_text=""` 且 `content_hash=null`，但其中一个来自 capability degraded 路径，另一个来自 AX 成功但文本为空
- **THEN** 系统 MUST 仅把前者记为 `permission_blocked`，后者 MUST 记为 `ax_empty`

### Requirement: Health and UI observability preserve permission state
系统 MUST 将权限状态通过 heartbeat 传播到 `/v1/health`，并保持 `#mr-health` / `data-state` 的降级可观测性。`/v1/health` 中 `capture_permission_status` MUST 表示 AX capability state；系统 MUST 另外暴露独立的 `screen_capture_status` 与 `screen_capture_reason`，用于表达 screenshot-path continuity。`denied_or_revoked` 与 `recovering` MUST 使 `/v1/health` 进入 `degraded`，但 `unreachable` 仅属于 UI/网络层观测，不得被服务端健康响应复用为权限状态。

Acceptance impact: 该要求冻结 permission health evidence 的边界；服务端 `/v1/health`、UI `#mr-health` 与网络不可达样本必须分开验证。

#### Scenario: Report degraded health during permission recovery
- **WHEN** 权限状态为 `recovering`
- **THEN** `/v1/health` MUST 继续暴露该状态并维持 `degraded`，直到恢复条件满足

#### Scenario: Keep AX capability and screenshot continuity in separate health fields
- **WHEN** AX capability degraded 但 screenshot 主链路仍连续
- **THEN** `/v1/health` MUST 能同时表达 `capture_permission_status!=granted` 与独立的 `screen_capture_status=ok`，而不得把两者折叠成单一字段

### Requirement: Prolonged degraded periods remain observable
系统 MUST 在权限长期 degraded 时继续保留对 screenshot continuity、heartbeat continuity 与 spool/backpressure 行为的可观测性。S2b MAY 不在本阶段定义额外持久化字段，但 evidence 导出 MUST 能区分“AX path blocked”与“capture loop 停止”这两类状态。

Acceptance impact: 该要求防止权限降级被误实现为整体采集停摆；相关 evidence 至少需要能显示 screenshot/heartbeat 仍在继续。
