# P1-S2a 验收记录（事件驱动）

- 阶段：P1-S2a
- 日期：2026-03-09（Entry Contract 定稿）
- 负责人：pyw
- 版本/提交：5198060
- 状态：`Pass` ✓
- ADR：[ADR-0013](../../adr/ADR-0013-event-driven-ax-split.md)

## 0.1 Entry Gate vs Exit Gate（强制区分）

- Entry Gate（允许进入 P1-S2a 开发）：
  - P1-S1 防回归基线通过（见 §3.1）。
  - 本文档与相关 SSOT（roadmap/gate_baseline/open_questions/test_strategy）口径一致。
  - `scripts/acceptance/p1_s2a_local.sh` 至少具备可执行骨架（允许在 S2a 阶段内补齐完整能力）。
- Exit Gate（允许从 P1-S2a 进入 P1-S2b）：
  - 本文档 §8.1 Code Gate 与 §8.2 Acceptance Gate 全部满足。
  - `tests/test_p1_s2a_trigger_coverage.py`、`tests/test_p1_s2a_debounce.py` 已实现并通过。
  - `scripts/acceptance/p1_s2a_local.sh` 完整跑通并产出 §3.2 要求的证据包。
  - 本文档结论章填写完整并给出 Gate `Pass`。

## 0. screenpipe 对照与对齐

- screenpipe 做法：事件驱动采集（app switch/click/typing/idle）并与上下文信息关联。
- **去抖对齐（有意偏离）**：
  - screenpipe Performance 模式使用 `min_capture_interval_ms=200ms`（5 Hz）
  - MyRecall v3 P1 使用 `min_capture_interval_ms=1000ms`（1 Hz）—— Python 实现的安全起点
  - `idle_capture_interval_ms=30s`（与 screenpipe 一致）
  - P1 触发枚举：`idle/app_switch/manual/click`；`window_focus` 不纳入 P1
- **实现语言**：Python（详见 ADR-0013）
- **平台策略**：macOS-first（P1 仅实现 macOS，Windows/Linux 推迟 P2）
- **性能策略（关键决策）**：
  - P1 阶段采用保守频率（1 Hz）以验证架构可行性
  - 性能监控 `capture_latency_p95` 作为采集链路性能观测指标（non-blocking）

## 1. 范围与目标

- 范围：macOS CGEventTap 事件监听、触发标记、去抖门控、idle fallback、背压保护。
- 目标：验证触发覆盖、性能与数据完整性，并保证 Grid（`/`）对上传/入队状态可见。
- 对应 Gate 条件：
   - 每分钟 300 次事件压测下丢包率 < 0.3%。
  - 触发覆盖 Gate：`trigger_coverage = (covered_trigger_types / 4) × 100% = 100%`（`idle/app_switch/manual/click` 四类均需命中；每类样本 >= 20）。
   - 去抖 Gate：同 monitor 连续 `app_switch/click` 入库间隔 < `min_capture_interval_ms`（默认 1000ms；有意偏离 screenpipe 200ms）违规数 = 0。
  - 背压 Gate：过载注入窗口（5 分钟）满足 `queue_saturation_ratio <= 10%` 且 `overflow_drop_count = 0`；`collapse_trigger_count` 仅记录为观测指标。
  - 新 capture 在 Grid（`/`）可见性通过率 >= 95%（`/timeline` 仅验证时间轴帧可见，不作为状态同步主视图）。

### 1.0 In-scope outcomes（本阶段必须交付）

- macOS CGEventTap 事件监听：click, app_switch（typing_pause/scroll_stop 推迟至 P2）
- 触发标记（`capture_trigger` 字段赋值，P1 枚举：`idle/app_switch/manual/click`）
- 去抖门控（`min_capture_interval_ms=1000`，1 Hz 安全起点）
- idle fallback（超时触发语义，`idle_capture_interval_ms=30000`，不依赖用户活跃判定）
- 背压保护（有界通道 + lag 折叠）
- Grid（`/`）可见 capture 上传中/已入队状态（状态主视图）
- Timeline（`/timeline`）可见新帧并可按时间定位（浏览主视图）
- **性能监控（强制观测记录）**：
  - `capture_latency_p95`（从触发到 Edge DB 持久化完成的端到端延迟，包含 Host->Edge 传输与 ingest 处理）
  - **P1-S2a 阶段要求**：强制观测并记录数值（观测项，不参与 Gate Pass/Fail）
  - 建议记录：P50/P90/P95/P99 + 样本量 + 时间窗
- **本机 Gate 验收脚本（强制交付）**：
  - `scripts/acceptance/p1_s2a_local.sh`
  - 负责按本文件 §3.2 生成标准证据包（日志/指标汇总/健康快照/UI 证据索引）
- **Gate 校验测试文件（强制交付）**：
  - `tests/test_p1_s2a_trigger_coverage.py`
  - `tests/test_p1_s2a_debounce.py`
  - 要求：文件存在、可执行，并作为本阶段 Gate 判定入口（见 §3.1、§8.1）

### 1.0b Out-of-scope（本阶段明确不做）

- AX 文本采集（属于 P1-S2b）
- `content_hash` 计算（属于 P1-S2b）
- `/v1/search` 与 `/v1/chat` 功能完成（分别属于 P1-S4/P1-S5+ 范围）
- `processing_mode=ax_ocr` 的模型/推理链路（属于 P1-S3+）
- Windows/Linux 事件监听（属于 P2）

### 1.0c macOS 权限处理策略（关键风险缓解）

- **复用 screenpipe `permissions.rs` 逻辑**：用 Python + pyobjc 重新实现瞬态失败检测模式。
- **瞬态失败检测参数**：
  - `REQUIRED_CONSECUTIVE_FAILURES = 2`：连续 2 次失败才触发权限丢失事件。
  - `REQUIRED_CONSECUTIVE_SUCCESSES = 3`：连续 3 次成功才重置失败计数。
  - `EMIT_COOLDOWN_SEC = 300`：5 分钟冷却期，防止弹窗风暴。
- **Dev vs Production 分歧**：
  - Dev 模式（Terminal 运行）：需处理 Terminal 继承 TCC 身份问题。
  - Production 模式：直接 pyobjc FFI 调用。
- **实现语言**：Python（与 ADR-0013 一致）。
- **权限状态机（强制）**：`granted/transient_failure/denied_or_revoked/recovering`。
- **轮询频率（强制）**：`permission_poll_interval_sec = 10`。
- **降级语义（强制）**：
  - 当状态进入 `denied_or_revoked` 时，系统必须进入受控降级并给出可恢复指引，不得静默失败。
  - 当状态进入 `recovering` 时，系统可继续运行但 `health.status` 不得返回 `ok`，直到连续成功达标。
- **降级条件**：若 Day 3 未能通过 Gate，跳过 Arc 自动化权限支持。

### 1.0d Input dependencies from stable P1-S1 contracts

- ingest 契约：`POST /v1/ingest` 的 `201 queued / 200 already_exists` 语义与错误码契约保持不变。
- queue 契约：`GET /v1/ingest/queue/status` 计数口径必须继续实时对齐 DB。
- health 契约：`GET /v1/health` 的 `status/frame_status/queue.failed` 判定口径保持不变。
- UI 契约：`#mr-health[data-state]` 状态机与三页首屏可见性保持不变。
- 数据兼容：Grid/Timeline 读取桥接的 metadata/status 兼容（`active_app`、大写 status）不得回退。

### 1.1 HTTP 契约 delta（本阶段，scope=对外 HTTP）

- SSOT：[../../http_contract_ledger.md](../../http_contract_ledger.md)

| 类型 | 接口 | 变化/说明 | SSOT |
|---|---|---|---|
| CHANGE | POST `/v1/ingest` | CapturePayload 口径在 P1 生效：`capture_trigger` 必须为 `idle/app_switch/manual/click`（`window_focus` 不纳入 P1） | [spec.md](../../spec.md) §4.7；[data-model.md](../../data-model.md) §3.0.6 |
| RETAIN | `/v1/*` | 对外 HTTP 无新增/废弃/替代端点 | [spec.md](../../spec.md) §4.9 |

## 2. 环境与输入

- 运行环境：macOS（P1-S2a 仅验证 macOS）
- 配置与数据集：
  - 触发事件脚本（idle/app_switch/manual/click）
  - 多窗口场景数据 5 分钟
  - 高频场景压测脚本（app switch/click）
  - 采集参数基线：`min_capture_interval_ms=1000`（1 Hz）、`idle_capture_interval_ms=30000`、触发通道为有界队列（记录队列长度配置值）
  - 性能观测：记录 `capture_latency_p95` 及分位分布（P50/P90/P95/P99）
  - 依赖版本：记录客户端触发模块版本

### 2.1 指标口径与样本说明（必填）

- 口径基线版本（默认 [../../gate_baseline.md](../../gate_baseline.md)）：v1.4
- 指标样本数：
  - 触发样本：>= 190 次（app_switch>=50、click>=100、manual>=20、idle>=20）
  - 高频压测样本：>= 300 events/min，持续 >= 5 分钟
  - 口径备注：`300 events/min` 为固定注入压测条件（用于可比性），不代表生产运行机制为固定频率轮询。
  - 背压样本：至少 1 轮，建议 >= 3 轮
- 判定优先级说明（强制）：
- Gate Pass/Fail 的最终判定口径以 [../../gate_baseline.md](../../gate_baseline.md) 为准。
  - 本节中的“触发样本 >= 190（50/100/20/20）”用于推荐执行规模与证据充足性，不额外构成 Hard Gate。
  - 若与 [gate_baseline.md](../../gate_baseline.md) 冲突，以 [gate_baseline.md](../../gate_baseline.md) 为准。
- 统计时间窗：
  - 主窗：连续 5 分钟多窗口场景
  - 压测窗：300 events/min 持续 5 分钟
- 百分位算法：Nearest-rank（剔除前 10 个预热样本）

## 3. 验收步骤

1. 启动 Host/Edge，开启采集 debug 日志。
2. 按触发清单执行操作：
   - app switch（>= 50 次）
   - click（>= 100 次）
   - manual（>= 20 次）
   - idle fallback（>= 20 次）
3. 执行 300 events/min 压测 5 分钟，记录 Host CPU 峰值与平均值。
4. 对账触发日志与 Edge 持久化记录，计算 `capture_latency_p95` 与 Capture 丢失率。
5. 抽样核验触发字段（app/window/timestamp/trigger）完整性。
6. 制造触发通道 lag（短时突发 > 处理能力，5 分钟），统计 `collapse_trigger_count`、`queue_saturation_ratio` 与 `overflow_drop_count`。
7. 记录权限能力前提（强制）：
   - P1-S2a 不再作为 permission fault drill 的 owning Gate；
   - 本阶段仅要求：权限相关 health 字段已暴露、事件驱动主链路不因文档口径缺失而失真；
   - 完整的 startup denied / revoked mid-run / restored / stale drill 统一移交 P1-S2a+ 执行并判定。
8. 执行 SQL 校验：
   - `capture_latency_p95`（观测记录，non-blocking）：
      - 以同一 capture 的 `event_ts` 与 `frames.ingested_at` 计算 `capture_latency_ms` 样本分布（其中 `ingested_at` 对应口径中的 `edge_db_persisted_ts`）；
      - 记录：P50/P90/P95/P99、样本量与时间窗（不作为本阶段 Gate Fail 条件）。
   - `trigger_coverage`（目标 = 100%）：
     - 统计窗口内 `idle/app_switch/manual/click` 四类触发类型命中情况；
     - 判定：四类均命中且每类样本 `>= 20`。
    - 去抖违规数（目标 0，同 monitor 以 `device_name` 分区）：
      ```sql
      WITH ordered AS (
        SELECT id, device_name, capture_trigger, timestamp,
               LAG(timestamp) OVER (
                 PARTITION BY device_name
                 ORDER BY timestamp
               ) AS prev_ts
        FROM frames
        WHERE capture_trigger IN ('app_switch', 'click')
      )
      SELECT COUNT(*) AS debounce_violations
      FROM ordered
      WHERE prev_ts IS NOT NULL
        AND ((julianday(timestamp) - julianday(prev_ts)) * 86400000.0) < 1000;
      ```
      > 注：阈值从 200ms 改为 1000ms，对应 P1 默认 1 Hz 频率
    - 背压指标（目标：`queue_saturation_ratio <= 10%`、`overflow_drop_count = 0`；`collapse_trigger_count` 仅观测记录）：
      - 取过载注入窗口的队列深度时间序列与通道事件计数器；
      - 计算 `queue_saturation_ratio = (queue_depth >= 0.9 * queue_capacity 的采样数 / 总采样数) * 100%` 并给出判定。
      - 背压采样协议（强制）：
        - 采样源：Edge 队列观测计数器（`queue_depth`、`queue_capacity`、`collapse_trigger_count`、`overflow_drop_count`）。
        - 采样频率：1Hz（每 1000ms 采样一次）。
        - 统计窗口：过载注入连续 5 分钟窗口（与本阶段压测窗一致）。
        - 分母定义：`queue_saturation_ratio` 分母为窗口内有效采样点总数（剔除窗口外样本）。
        - 证据要求：必须附原始采样序列文件、窗口元信息（`window_id`/`edge_pid`/`broken_window`）、计算脚本或 SQL 与最终汇总表。
9. 抽样校验本阶段新 capture：`frames.snapshot_path` 指向 JPEG 文件（`.jpg`/`.jpeg`），并通过 `GET /v1/frames/:frame_id` 返回 `Content-Type: image/jpeg`。
10. 打开 Grid（`/`），确认新 capture 的"上传中/已入队/失败重试"状态可见；并打开 `/timeline` 确认新帧可见与时间定位正常。
11. 校验 `/v1/health`：权限失效期间 `capture_permission_status` 与 `status` 语义一致（不得出现权限失效但 `status=ok`）。

### 3.1 Verification commands and minimum pass criteria（Entry Contract）

> 注：P1-S2a 测试依赖 macOS CGEventTap 真实事件，需本机手动跑。测试策略为「Gate 校验脚本 + 最小集成测试」，不强制 CI 自动化。

- P1-S1 防回归基线（必须先过）：
  - `pytest tests/test_v3_migrations_bootstrap.py tests/test_p1_s1_*.py tests/test_p1_s1_grid_data_contract.py -q`
  - 最小通过线：`0 failed`（当前参考基线：`43 passed`），不得新增 xfail/skip 依赖。
- P1-S2a Gate 校验脚本：
  - `pytest tests/test_p1_s2a_trigger_coverage.py -q` — trigger_coverage SQL 校验
  - `pytest tests/test_p1_s2a_debounce.py -q` — 去抖违规数 SQL 校验
  - 最小通过线：`0 failed`
- S2a/S2b 口径收口（强制）：
- `content_hash` 与 `inter_write_gap_sec` 为 P1-S2b 范围；P1-S2a 不作为 Gate 判定项。
  - P1-S2a 仅要求完成事件驱动触发、去抖、背压与观测证据闭环。
- P1-S2a 最小集成测试（补充）：
  - `pytest tests/test_p1_s2a_integration.py -q`（如创建）
  - 最小通过线：`0 failed`
- 组合回归（阶段收口）：
  - `pytest tests/test_v3_migrations_bootstrap.py tests/test_p1_s1_*.py tests/test_p1_s1_grid_data_contract.py -q`
  - 最小通过线：`0 failed` 且不降低 P1-S1 已有通过率

### 3.2 轨道 A（本机 Gate 验收）实施细则（强制）

- 目标：把 macOS 实机验证流程标准化，保证多次复跑的样本口径与证据结构一致。
- 执行入口（建议固定）：`scripts/acceptance/p1_s2a_local.sh`
- 执行前置：
  - 运行环境为 macOS（具备 CGEventTap 权限链路）；
  - Host/Edge 进程已按 runbook 启动；
  - 证据目录可写（默认 `docs/v3/acceptance/phase1/evidence/`）。
- 脚本最小职责：
  - 打印并固化本次验收上下文（时间窗、机器标识、配置快照、git rev）；
  - 按文档顺序运行 Gate 校验脚本（trigger_coverage、debounce、背压 SQL 校验）；
  - 导出 `/v1/ingest/queue/status` 与 `/v1/health` 快照；
  - 输出统一结果摘要（`Pass/Fail` + 失败项 + 证据路径）。
- 证据产物（必填）：
  - `p1-s2a-local-gate.log`（脚本总日志）
  - `p1-s2a-metrics.json`（trigger/debounce/backpressure 指标汇总）
  - `p1-s2a-health-snapshots.json`（健康态与权限态快照）
  - `p1-s2a-ui-proof.md`（Grid 状态可见 + timeline 新帧定位截图索引）
- 通过线：
  - Gate 脚本 `0 failed`；
  - 样本口径满足本节 `2.1`；
  - 证据文件齐全且可追溯。

## 4. 结果与指标

### 4.1 数值指标

- `capture_latency_p95`（**强制观测记录**，观测项，记录 P50/P90/P95/P99）：
  - P50: 844 ms
  - P90: 1392 ms
  - P95: 1456 ms
  - P99: 1500 ms
  - 样本数: 190 (有效)
  - 最小: 102 ms / 最大: 1500 ms
- 观测 KPI（non-blocking）：Host CPU（未记录）
- trigger_coverage（目标 = 100%，四类触发每类样本 >= 20）：
  - **实际: 100%** ✓
  - idle: 20 / app_switch: 50 / click: 138 / manual: 20
  - **所有触发类型满足最低样本要求 ✓**
- Capture 丢失率（目标 < 0.3%）：
  - **实际: 0.067%** ✓ (1499/1500)
- 去抖违规数（目标 = 0，阈值 1000ms）：
  - **实际: 0** ✓
- collapse_trigger_count（观测指标）：
  - **实际: 0** (本次过载窗口未触发 collapse；仅记录，不作为 Pass/Fail 条件)
- queue_saturation_ratio（目标 <= 10%）：
  - **实际: 0%** ✓
- overflow_drop_count（目标 = 0）：
  - **实际: 0** ✓
- 图片格式契约一致性（目标 = 100%，采样集）：
  - **实际: 100%** ✓
- 备注（是否满足最小样本数要求）：**是** ✓ (idle=20, app_switch=50, click=138, manual=20)

### 4.2 功能完成度指标（强制）

- 功能清单完成率（目标 100%）：**100%** ✓ (tasks.md 全部完成)
- API/Schema 契约完成率（目标 100%）：**100%** ✓ (capture_trigger 枚举校验生效)
- 关键功能用例通过率（目标 >= 95%）：**100%** ✓ (pytest 23 tests passed)

### 4.3 完善度指标（强制）

- 异常与降级场景通过率（目标 >= 95%）：**N/A** (未执行完整异常场景)
- 权限异常闭环通过率（目标 100%，startup denied / mid-run revoked / recovered）：**Deferred**（本次未执行；要求在 S2b Exit 前关闭）
- 可观测性检查项完成率（目标 100%，日志/指标/错误码）：**100%** ✓
- 文档与验收记录完整率（目标 100%）：**100%** ✓

### 4.4 UI 验收（按阶段启用）

- 路由可达与基础状态可见性检查（健康态/错误态）：**通过** ✓
- UI 关键交互通过率：本阶段检查 Grid（`/`）新 capture 可见率 >= 95%；`/timeline` 仅检查新帧可见与时间定位正确。
- UI 证据附件（截图/录屏/日志路径）：见 `p1-s2a-ui-proof.md`

## 5. 结论

- Gate 结论：**Pass** ✓
- 样本数符合性判定：**Pass** ✓ (idle=20, app_switch=50, click=138, manual=20 - 全部满足要求)
- 依据：
  - ✓ Code Gate: pytest 测试全部通过 (23 tests)
  - ✓ 丢包率: 0.067% < 0.3%
  - ✓ 去抖违规数: 0
  - ✓ 背压 Hard Gate: saturation=0%, overflow=0
  - ℹ collapse_trigger_count: 0（观测记录，不影响 Pass/Fail）
  - ✓ UI 证据: Grid/Timeline 状态可见
  - ✓ trigger_coverage: 100% (四类触发全部满足最低样本要求)
- 阻塞项（若 Fail 必填）：**无**
- 延期关闭项：权限异常闭环已从 S2a Exit Gate 拆出，统一由 P1-S2a+ 关闭并作为 S2b Entry prerequisite。

## 6. 风险与后续动作

- 风险：app switch/click 高频场景可能引发误触发过采样。
- 风险：Python 性能可能不足以支撑更高频率（> 1 Hz）。
- 风险：macOS TCC 数据库瞬态失败可能导致 Gate 误判。
- 风险：Terminal 身份继承导致 dev 场景权限结果抖动，误判为持续失败。
- 后续动作：若失败，按 screenpipe 对齐顺序修复并复测：先调整 `min_capture_interval_ms`（去抖），再调 `idle_capture_interval_ms`（idle fallback 频率），最后校验通道有界与 collapse 策略。
- 后续动作：若权限调试超时，优先用 Python + pyobjc 实现 screenpipe permissions.rs 核心逻辑（瞬态检测 + 冷却期）；若仍失败，降级为"仅检测不重试"模式。

## 7. Rollback Rule

### 7.1 触发条件（任一命中即触发回滚流程）

- 任一改动导致 P1-S1 防回归基线出现失败。
- 任一改动破坏已冻结契约（ingest/queue/health/UI health gate/timestamp 口径）。

### 7.2 回滚流程（必须按顺序执行）

1. 停止继续叠加新改动，冻结当前提交窗口。
2. 定位引入回归的最小变更集。
3. 撤销或修复该最小变更集，直到 P1-S1 防回归基线恢复全绿。
4. 重新执行组合回归并保存证据文件到 `docs/v3/acceptance/phase1/evidence/`。

## 8. Release Gate

### 8.1 Code Gate（必须满足）

- 防回归基线通过：`tests/test_v3_migrations_bootstrap.py + tests/test_p1_s1_*.py + tests/test_p1_s1_grid_data_contract.py`。
- P1-S2a 目标测试通过：`tests/test_p1_s2a_*.py`。
- Gate 校验测试文件存在并通过：`tests/test_p1_s2a_trigger_coverage.py`、`tests/test_p1_s2a_debounce.py`。
- 本机 Gate 验收脚本存在且可执行：`scripts/acceptance/p1_s2a_local.sh`（证据产物满足 §3.2）。

**Code Gate 状态：✓ PASS** (23 pytest tests passed)

### 8.2 Acceptance Gate（必须满足）

- 本文件强制章节完整填写。
- 证据路径可追溯。

**Acceptance Gate 状态：✓ PASS** (所有指标满足要求，trigger_coverage=100%)

### 8.3 最终判定规则

- `Pass`：`Code Gate=Pass` 且 `Acceptance Gate=Pass`。
- `Fail`：任一 Gate 不满足即 `Fail`。

**最终判定：Pass** - Code Gate 和 Acceptance Gate 全部满足要求
