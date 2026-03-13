# P1-S2a+ 验收记录（权限稳定性收口）

- 阶段：P1-S2a+
- 日期：紧接 S2a Pass 后
- 负责人：pyw
- 状态：`Planned`
- 依赖：P1-S2a Pass
- 角色：P1-S2b Entry Gate 前置条件

## 0. 范围收口说明

- 本阶段是紧接 P1-S2a 的独立收口阶段，不是新的大功能阶段。
- v3 主线按 OCR-only 收口：权限能力只为事件驱动 capture 的稳定性负责，不再承担 AX 主链路交付。
- 本阶段只收口 Input Monitoring 权限稳定性，以及其对 `/v1/health`、capture 启停、恢复语义的影响。
- Accessibility 在 v3 P1 中降级为 soft observation：若已授权，可记录调试信息；不是本阶段 Hard Gate。

## 1. 范围与目标

- 范围：Input Monitoring 权限探测、权限状态机、受控降级、自动恢复、`/v1/health` 语义、手测证据闭环。
- 目标：把“权限暂态抖动”和“真实 denied/revoked”区分开，保证系统不会出现“capture 实际失效但 health 仍显示 ok”的假健康状态。
- 对应 Gate 条件：
  - 权限场景矩阵通过率 = 100%（Hard Gate）
  - `/v1/health` 权限字段完整性与状态语义正确率 = 100%（Hard Gate）
  - 权限丢失后 capture 进入受控降级，权限恢复后自动恢复 = 100%（Hard Gate）

### 1.0 In-scope outcomes（本阶段必须交付）

- Input Monitoring 权限状态机：`granted/transient_failure/denied_or_revoked/recovering`
- 参数冻结：
  - `REQUIRED_CONSECUTIVE_FAILURES = 2`
  - `REQUIRED_CONSECUTIVE_SUCCESSES = 3`
  - `EMIT_COOLDOWN_SEC = 300`
  - `permission_poll_interval_sec = 10`
- `/v1/health` 权限字段对外语义冻结：
  - `capture_permission_status`
  - `capture_permission_reason`
  - `last_permission_check_ts`
- 降级语义冻结：
  - 当 `capture_permission_status in ("denied_or_revoked", "recovering")` 时，`/v1/health.status` 不得返回 `ok`
  - 当权限快照超时（`now_utc - last_permission_check_ts > 60s`）时，`capture_permission_reason = "stale_permission_state"`
- 验证边界冻结：
  - 状态机与 health 语义允许自动化验证
  - TCC 实际切换以 macOS 手测为主路径

### 1.0b Out-of-scope（本阶段明确不做）

- AX tree walk、AX metadata 主链路、`accessibility_text` 处理链路
- Browser URL 采集
- `content_hash` / content-based dedup Gate
- OCR processing、`text_source` 判定、search/chat 能力

### 1.0c 与 S2a / S2b 的分工边界

| 验证项 | S2a | S2a+ | S2b |
|---|---|---|---|
| 事件驱动 trigger 生成 | 负责 | 继承 | 继承 |
| Input Monitoring 权限状态机 | 不再作为 Exit Gate owning item | 负责 | 继承集成验证 |
| `/v1/health` 权限字段语义 | 基础契约已暴露 | 负责收口 | 继承并验证不会阻断 capture completion |
| 权限失效后的 capture 降级/恢复 | 不再以 S2a Gate 判定 | 负责 | 继承并验证与 topology / routing 协同时仍成立 |

## 2. 环境与执行约束

### 2.1 Terminal 模式限制（必须记录）

- 当前 v3 仅支持 Terminal 启动：`./run_server.sh`、`./run_client.sh`
- Terminal 继承的 TCC 身份可能与未来签名 App 不同，因此本阶段的实机权限结果只能作为 P1 本地 Gate 证据，不得表述为长期生产稳定性证明。
- 每次验收必须记录当前运行模式为 `Terminal mode`，并在证据中记录权限相关环境变量。

### 2.2 Gate 允许的验证层级

- **自动化层**：验证状态机转移、health 字段完整性、降级语义、快照陈旧语义。
- **手测层**：验证真实 TCC 场景切换，包括 startup denied、mid-run revoke、restore。
- **说明**：若未来引入签名 App，本阶段契约继续有效，但需以固定签名身份重新做一轮稳定性验收。

## 3. 场景矩阵（Hard Gate）

| 场景 | 前置条件 | 期望状态机 | 期望 `/v1/health.status` | 期望 reason | 期望 capture 行为 | 证据要求 |
|---|---|---|---|---|---|---|
| `startup_not_determined` | 首次启动或权限状态未定 | `transient_failure` 或等价引导态 | `degraded` | 不得为 `granted` | 不得静默开始事件驱动 capture | health 快照 + UI 引导截图 + 日志 |
| `startup_denied` | 启动前已拒绝 Input Monitoring | `denied_or_revoked` | `degraded` | `input_monitoring_denied` 或等价实现枚举 | capture 不启动或立即进入受控降级 | health 快照 + 日志 + UI 降级截图 |
| `revoked_mid_run` | 运行中撤销权限 | `granted -> transient_failure -> denied_or_revoked` | `ok/degraded -> degraded` | 非 `granted`，且应能区分 denied/revoked/transient | capture 停止继续消费外部事件触发 | 状态变化时间线 + health 快照 + 日志 |
| `restored_after_denied` | denied/revoked 后重新授权 | `denied_or_revoked -> recovering -> granted` | `degraded -> ok` | `granted` 或恢复中原因 | capture 自动恢复，无需人工重启进程 | 状态变化时间线 + health 快照 + 恢复日志 + UI 截图 |
| `stale_permission_state` | 权限轮询结果超过 60s 未刷新 | 状态值可保留上次快照 | `degraded` | `stale_permission_state` | 不得伪装为健康稳定态 | health 快照 + 日志 |

### 3.1 判定补充

- `startup_not_determined` 允许实现层采用等价引导态，但对外 health 语义必须表现为 `degraded`，且不得让用户误以为 capture 已稳定可用。
- `transient_failure` 不得直接等价于 `denied_or_revoked`；必须遵守 2 次连续失败阈值。
- `recovering` 期间系统可以继续运行，但 `/v1/health.status` 不得返回 `ok`，直到连续 3 次成功达标。

## 4. 验收步骤

1. 确认 P1-S2a 已 Pass，且当前验收窗口不混入新的 S2b 改动。
2. 按本节场景矩阵逐项执行 startup / revoke / restore / stale drill。
3. 每个场景至少保留以下证据：
   - Host/Edge 日志片段（带时间戳）
   - `/v1/health` 快照
   - UI 引导/降级/恢复截图（适用时）
4. 核对以下语义：
   - health 响应必须同时包含 `capture_permission_status`、`capture_permission_reason`、`last_permission_check_ts`
   - 权限失效或恢复中不得返回 `status=ok`
   - `stale_permission_state` 必须触发 `status=degraded`
5. 记录执行环境：Terminal mode、git rev、时间窗、相关环境变量、任何 TCC 异常观察。

## 5. 自动化验证入口（本阶段强制交付）

- 本阶段必须新增测试文件：`tests/test_p1_s2a_plus_permission_fsm.py`
- 该测试文件必须至少覆盖以下集合：
  - `test_startup_not_determined_health_degraded()`
  - `test_startup_denied_transitions_to_denied_or_revoked()`
  - `test_mid_run_revoked_stops_capture_and_degrades_health()`
  - `test_restored_after_denied_recovers_to_granted()`
  - `test_stale_permission_snapshot_forces_degraded_health()`
  - `test_health_contract_contains_permission_fields()`
- 说明：以上为本阶段 Gate 的强制交付要求；若测试文件缺失、未实现或未通过，则本阶段不得给出 `Pass`。

## 6. 执行入口与证据产物

### 6.1 执行入口要求

- S2a+ 必须拥有独立、可追溯的本机 Gate 执行入口。
- 可接受形式：
  - 新增独立脚本 `scripts/acceptance/p1_s2a_plus_local.sh`，或
  - 明确扩展现有 `scripts/acceptance/p1_s2a_local.sh` 并实际支持 S2a+ 专用入口。
- 在入口未落地前，本文档只能作为 `Planned`，不得填写 `Pass`。

### 6.2 证据产物（最小集合）

- `p1-s2a-plus-local-gate.log`：脚本/手测总日志
- `p1-s2a-plus-permission-transitions.jsonl`：权限状态变化时间线
- `p1-s2a-plus-health-snapshots.json`：各场景 `/v1/health` 快照
- `p1-s2a-plus-ui-proof.md`：引导/降级/恢复截图索引
- `p1-s2a-plus-context.json`：执行环境上下文（Terminal mode、git rev、env snapshot）

## 7. SQL / 数据验证边界

- 本阶段不以 `frames` 表内的 `permission_status` 字段作为 Gate 验证基础，因为当前 v3 主数据模型未定义该列，见 `docs/v3/data-model.md`。
- 权限 Gate 的真值来源是：
  - 权限状态机输出
  - `/v1/health` 对外响应
  - 日志与手测证据
- 若后续需要持久化权限事件，应单独定义事件表或观测日志格式，不得在本阶段文档中假设 `frames.permission_status` 已存在。

## 8. 结论模板

- Gate 结论：`Pass` | `Fail` | `Planned`
- 权限场景矩阵：✅ | ❌
- `/v1/health` 权限语义：✅ | ❌
- 自动恢复：✅ | ❌
- 执行环境备注：Terminal mode（P1 已知限制）
- 未关闭项：
- 依据：

## 9. 后续动作

- 若 Pass：允许进入 P1-S2b，并把 S2a+ 证据作为 S2b Entry prerequisite。
- 若 Fail：优先修复权限探测契约、状态机语义或 health 语义，再重新执行本阶段验收。
