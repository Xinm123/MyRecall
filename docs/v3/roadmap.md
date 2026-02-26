# MyRecall-v3 路线图（执行视图）

- 版本：v0.2（Draft）
- 日期：2026-02-26
- 文档角色：只描述阶段推进与 Gate 执行，不定义事实阈值。
- 事实来源：所有能力与指标定义见 [`spec.md`](./spec.md)。

## 1. 执行原则

1. P1 完成全部功能闭环；P2/P3 功能冻结。
2. P1 按 `S1 -> S2 -> S3 -> S4 -> S5 -> S6 -> S7` 串行推进。
3. 每阶段/子阶段必须同时满足：
- 对应能力 `C-*` 达成。
- 对应指标 `M-*` 达标。
- 对应验收文档完成并归档。
4. 未通过 Gate 不得进入下一阶段。

## 2. 时间线

| 阶段 | 时间 | 目标 |
|---|---|---|
| P1（本机双进程） | 2026-03-02 ~ 2026-03-20 | 完成 Host/Edge 全功能闭环与端到端验收 |
| P2（LAN 双机） | 2026-03-23 ~ 2026-04-17 | 验证 LAN 稳定性、重放一致性与 mTLS |
| P3（Debian 生产） | 2026-04-20 ~ 2026-05-29 | 完成服务化部署、7天稳定运行与回滚闭环 |

## 3. Phase 1：串行子阶段

### 3.1 P1-S1（基础链路）
- 交付焦点：Host 上传链路、Edge ingest/queue 骨架、UI 基线可用。
- 能力引用：`C-ING-001, C-ING-002, C-ING-003, C-UI-001, C-UI-002`
- Gate 引用：`M-ING-004, M-UI-001, M-UI-002`
- 验收文档：`acceptance/phase1/p1-s1.md`

### 3.2 P1-S2（采集）
- 交付焦点：事件驱动 capture、idle fallback、AX 文本采集与 timeline 状态可见。
- 能力引用：`C-CAP-001, C-CAP-002, C-CAP-003`
- Gate 引用：`M-ING-001, M-ING-002, M-ING-003`
- 验收文档：`acceptance/phase1/p1-s2.md`

### 3.3 P1-S3（处理）
- 交付焦点：AX-first/OCR-fallback、fusion 产物、处理来源可解释。
- 能力引用：`C-PRO-001, C-PRO-002, C-PRO-003, C-PRO-004`
- Gate 引用：`M-PRO-001, M-PRO-002`
- 验收文档：`acceptance/phase1/p1-s3.md`

### 3.4 P1-S4（检索）
- 交付焦点：`/v1/search`、`/v1/search/keyword`、检索回溯字段与 UI/API 契约映射。
- 能力引用：`C-SCH-001, C-SCH-002, C-SCH-003, C-SCH-004`
- Gate 引用：`M-SCH-001, M-SCH-002, M-SCH-003, M-SCH-004`
- 验收文档：`acceptance/phase1/p1-s4.md`

### 3.5 P1-S5（Chat-1 Grounding 与引用）
- 交付焦点：Chat 工具编排、引用强制策略与可回溯。
- 能力引用：`C-CHT-001, C-CHT-002`
- Gate 引用：`M-CHT-001, M-CHT-002, M-CHT-003`
- 验收文档：`acceptance/phase1/p1-s5.md`

### 3.6 P1-S6（Chat-2 路由与流式）
- 交付焦点：local/cloud 路由、超时降级、流式协议一致性。
- 能力引用：`C-CHT-003, C-CHT-004, C-CHT-005`
- Gate 引用：`M-CHT-004, M-CHT-005, M-CHT-006`
- 验收文档：`acceptance/phase1/p1-s6.md`

### 3.7 P1-S7（端到端验收）
- 交付焦点：关键路径脚本化回归、P1 基线冻结、跨子阶段回归。
- 能力引用：`C-UI-003 + P1 能力基线冻结`
- Gate 引用：`M-CHT-001, M-SYS-001, M-UI-003, M-SYS-002`
- 验收文档：`acceptance/phase1/p1-s7.md`

## 4. Phase 2：LAN 双机验证（功能冻结）

- 目标：验证跨机器稳定性、重放一致性、传输安全升级。
- 能力引用：`C-ING-001, C-ING-002, C-ING-003, C-UI-003`
- Gate 引用：`M-ING-003, M-ING-005, M-SEC-001, M-OPS-001, M-SYS-002`
- 验收文档：`acceptance/phase2/phase2-lan-validation.md`

## 5. Phase 3：Debian 生产形态（功能冻结）

- 目标：完成部署、观测、回滚与 7 天稳定运行。
- 能力引用：`C-OPS-001, C-OPS-002, C-UI-003`
- Gate 引用：`M-CHT-001, M-OPS-001, M-OPS-002, M-OPS-003, M-SYS-002`
- 验收文档：`acceptance/phase3/phase3-debian-production.md`

## 6. 阶段入口/退出条件

### 6.1 入口条件（每阶段）
- 前一阶段 Gate 结论为 Pass。
- 前一阶段阻塞项清零。
- 验收文档已归档到 `acceptance/` 对应文件。

### 6.2 退出条件（每阶段）
- 对应 `C-*` 全部达成。
- 对应 `M-*` 全部达标。
- 失败样例与风险已转入 `open_questions.md` 或下一阶段回归集。

## 7. 风险清单（执行级）

- R-001：P1 范围膨胀导致串行链路延期。
- R-002：事件风暴导致 Host 资源波动和丢包风险。
- R-003：语义查询退化影响 Chat 引用覆盖率。
- R-004：Edge 高压下 UI 与处理链路资源争用。
- R-005：P2/P3 安全与部署脚本稳定性不足导致复盘成本上升。

## 8. 变更策略

- 改阈值/定义：只改 `spec.md`。
- 改阶段时间：改本文件与对应验收计划。
- 改决策取舍：新增或更新 `adr/*`，并在 `spec.md` 更新索引。
