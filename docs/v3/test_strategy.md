# MyRecall-v3 测试策略

- 版本：v1.1
- 日期：2026-03-13
- 状态：已锁定
- 关联决策：016A（v3 全新数据起点）

---

## 1. 核心决策

**v3 全部使用全新测试，不复用 v2 现有测试。**

现有测试文件保留在 `tests/` 目录下，仅作为实现参考，不计入 v3 验收。

---

## 2. 决策理由

| 维度 | v2 | v3 | 结论 |
|------|-----|-----|------|
| 架构 | 单机闭环 | Host/Edge 分离 | 不兼容 |
| 数据模型 | LanceDB + FTS | SQLite（v3 主线 OCR-only，AX schema seam 保留） | 不兼容 |
| API | `/api/*` | `/v1/*` | 契约变更 |
| Capture | 定时轮询 | 事件驱动 | 逻辑重写 |
| Chat | 无 | Pi Sidecar + SSE | 全新 |

v3 是全新起点（决策 016A），架构与 v2 根本不同，复用测试的成本 > 全部重写。

---

## 3. 测试分层结构

```
tests/
├── host/                          # Host 端测试（全新）
│   ├── test_capture_trigger.py    # 事件驱动 capture
│   ├── test_host_uploader.py      # 幂等上传协议
│   └── test_spool_buffer.py       # Host spool
│
├── edge/                          # Edge 端测试（全新）
│   ├── test_ingest_api.py         # /v1/ingest 端点
│   ├── test_ocr_pipeline.py      # OCR-only processing
│   ├── test_search_api.py        # /v1/search 端点
│   ├── test_frames_api.py        # /v1/frames/* 端点
│   └── test_health_api.py        # /v1/health 端点
│
├── chat/                          # Chat 测试（全新）
│   ├── test_chat_manager.py
│   ├── test_chat_protocol.py
│   ├── test_chat_persistence.py
│   └── test_chat_e2e.py
│
└── e2e/                          # 端到端测试（全新）
    └── test_host_edge_integration.py
```

---

## 4. 各阶段测试覆盖

### P1-S1（基础链路）
- `test_ingest_api.py` — 幂等上传、队列状态
- `test_frames_api.py` — 图像获取（`GET /v1/frames/:frame_id`，`Content-Type: image/jpeg`）
- `test_health_api.py` — 健康检查

### P1-S2（采集）
- **Gate 校验脚本**（核心，必须）：
  - `test_p1_s2a_trigger_coverage.py` — SQL 校验 trigger_coverage = 100%
  - `test_p1_s2a_debounce.py` — SQL 校验去抖违规数 = 0
  - `test_p1_s2_routing.py` — routing correctness / duplicate capture / topology rebuild 校验（注：S2a/S2b 联合交付，命名为 S2 而非 S2b）
  - `test_p1_s2_device_binding.py` — `device_name` 绑定与 focused-context coherence 校验（注：S2a/S2b 联合交付，命名为 S2 而非 S2b）
- **最小集成测试**（补充）：
  - capture-completion 协调逻辑（可单元测）
  - 队列状态 API
  - S2b metadata/handoff 字段矩阵：`capture_trigger`、`device_name`、`app_name/window_name/browser_url` 的 canonical key 与一致性规则
  - focused-context 一致性矩阵：禁止 mixed-source `app_name/window_name`、stale `browser_url` 必须 rejected to `null`、`device_name` 必须对应实际截图 monitor
  - Arc stale-url 场景仅在 Arc support 未 defer 时执行；若 Arc deferred，不计入 required browser success 判定

> 注：P1-S2 测试依赖 macOS CGEventTap 真实事件，需本机手动跑，不强制 CI 自动化

> P1-S2a 交付约束（强制）：`test_p1_s2a_trigger_coverage.py` 与 `test_p1_s2a_debounce.py` 属于阶段交付物，不得以“后补测试”方式延后到 P1-S2b。

> Gate 边界说明：上述两个测试文件属于 **P1-S2a Exit Gate 交付物**（决定能否进入 P1-S2b），不是 P1-S2a Entry Gate 的阻塞前置。

> P1-S2b 开发方式（已冻结）：S2b 采用 TDD 开发；`test_p1_s2b_routing.py`、`test_p1_s2b_device_binding.py` 等测试文件是随功能演进自然沉淀的阶段交付物，不要求在开工前一次性补齐。`scripts/acceptance/p1_s2b_local.sh` 属于 Exit Gate 编排层，应在阶段收口时补齐并执行。

### P1-S3（处理）
- `test_ocr_pipeline.py` — OCR-only 处理、`ocr_text` 写入与失败语义

### P1-S4（检索）
- `test_search_api.py` — FTS、过滤参数、OCR-only 搜索契约

### P1-S5~S6（Chat）
- `test_chat_manager.py` — Pi 进程管理
- `test_chat_protocol.py` — 事件流协议
- `test_chat_persistence.py` — 会话持久化
- `test_frames_api.py` — deep link resolver（`GET /v1/frames/:frame_id/metadata`，最小稳定契约 `{frame_id,timestamp}`）

### P1-S7（验收）
- `test_chat_e2e.py` — E2E 场景覆盖 >= 30
- `test_host_edge_integration.py` — 完整链路

---

## 5. P1-S2 测试策略补充

> **重要说明**：P1-S2（采集）测试依赖 macOS CGEventTap 真实事件与多屏/权限实机场景，**无法在 CI 环境自动化**，需本机手动跑。

### 测试策略：「Gate 校验脚本 + 最小集成测试」

| 类型 | 说明 | 运行方式 |
|------|------|----------|
| **Gate 校验脚本** | 将验收文档的 SQL 校验封装为 pytest 参数化测试 | 本机手动跑 |
| **最小集成测试** | 针对可单元测试的模块（去重逻辑、队列 API） | 可 CI |

### 轨道 A（本机 Gate 验收）落地规范

- 适用范围：P1-S2a（CGEventTap）、P1-S2a+（permission stability closure）与 P1-S2b（capture completion / monitor-aware coordination）三个子阶段。
- 脚本入口（统一约定）：
  - `scripts/acceptance/p1_s2a_local.sh`
  - `scripts/acceptance/p1_s2a_plus_local.sh`
  - `scripts/acceptance/p1_s2b_local.sh`
- 运行要求：
  - 必须在 macOS 实机执行（不得在 CI 容器替代）；
  - 执行前固定时间窗、配置快照、权限状态，避免样本口径漂移；
  - 每次执行必须产出统一命名的证据包（日志 + 指标汇总 + 健康快照 + UI 截图索引）。
- 结果判定：
  - `Gate pytest` 全绿（`0 failed`）+ 文档样本口径满足；
  - 证据不齐全时不得给出 Gate `Pass`。

### P1-S2 权限故障矩阵（强制）

| 场景 | 前置条件 | 期望状态机 | 期望健康态 | 期望 UI/日志 |
|------|---------|-----------|-----------|-------------|
| startup_not_determined | 首次启动，未授权 | `transient_failure` 或引导态 | `degraded` | 显示授权引导，不静默失败 |
| startup_denied | 启动前已拒绝权限 | `denied_or_revoked` | `degraded` | 明确提示权限缺失 + 设置入口 |
| revoked_mid_run | 运行中撤销权限 | `granted -> transient_failure -> denied_or_revoked` | `degraded` | 记录权限丢失事件，进入降级 |
| restored_after_denied | 用户恢复授权 | `denied_or_revoked -> recovering -> granted` | `degraded -> ok` | 恢复提示与自动恢复日志 |
| stale_permission_state | 权限快照超过 60s 未刷新 | 保留上次状态或等价内部态 | `degraded` | health 返回 `stale_permission_state` |

- 参数口径（与文档契约一致）：`REQUIRED_CONSECUTIVE_FAILURES=2`、`REQUIRED_CONSECUTIVE_SUCCESSES=3`、`EMIT_COOLDOWN_SEC=300`、`permission_poll_interval_sec=10`。
- 自动化边界：TCC 状态切换为手测主路径；状态机与健康接口可通过集成测试验证。
- 证据要求（每个场景必填）：
  - Host/Edge 日志片段（含时间戳与权限状态变化）
  - `/v1/health` 响应快照（至少两次：异常中、恢复后）
  - UI 状态截图（引导/降级/恢复）
  - 执行环境上下文（Terminal mode、git rev、env snapshot）

阶段归属说明：
- P1-S2a：负责事件驱动 trigger、去抖、背压与基础 health 契约暴露；不再作为 permission fault drill 的 owning Gate。
- P1-S2a+：负责 permission state machine / degraded-recovering-ok 闭环、health 权限语义、stale permission snapshot 语义与手测证据闭环。
- P1-S2b：继承并验证 permission 状态不会阻断 capture completion，同时负责 routing / device binding / topology rebuild 等采集闭环验证。
- P1-S3：负责 OCR success / failure / failed status 的 processing semantic tests。

### 需要的测试文件

| 子阶段 | 文件 | 内容 |
|--------|------|------|
| S2a | `test_p1_s2a_trigger_coverage.py` | SQL 校验 trigger_coverage = 100% |
| S2a | `test_p1_s2a_debounce.py` | SQL 校验去抖违规数 = 0 |
| S2a+ | `test_p1_s2a_plus_permission_fsm.py` | 权限状态机、health 语义、stale snapshot、恢复闭环校验 |
| S2b | `test_p1_s2b_routing.py` | trigger routing / duplicate capture / topology rebuild 校验 |
| S2b | `test_p1_s2b_device_binding.py` | `device_name` binding 与 focused-context coherence 校验 |

### 不需要做的

- ❌ 完整的 CGEventTap 单元测试（难以 mock 真实系统事件）
- ❌ 完整的 AX 树遍历单元测试（依赖 macOS 环境）
- ❌ CI 环境自动化（需本机手动跑）

---

## 6. 标记规范

所有 v3 测试使用以下 pytest 标记：

```python
pytestmark = pytest.mark.unit  # 或 integration
```

- **unit**: 单元测试，无外部依赖（mock）
- **integration**: 集成测试，需要真实组件（Flask app、SQLite）
- **e2e**: 端到端测试，不在默认套件中运行

---

## 6. 现有测试处理

| 文件 | 处理方式 |
|------|---------|
| `test_phase*.py` | 保留，不运行，仅作参考 |
| `test_nlp*.py` | 保留，不运行，仅作参考 |
| `test_ai_*.py` | 保留，不运行，仅作参考 |
| `test_api_*.py` | 保留，不运行，仅作参考 |

---

## 7. 工作量估算

| 模块 | 预估行数 |
|------|---------|
| Host | ~500 |
| Edge API | ~500 |
| Edge Processing | ~250 |
| Chat | ~550 |
| E2E | ~200 |
| **总计** | **~2000** |

---

## 8. 验收标准

- 每个 P1 子阶段的 Gate 对应测试用例必须通过
- 测试覆盖率不设硬性指标，但关键路径必须覆盖
- E2E 测试场景数 >= 30
