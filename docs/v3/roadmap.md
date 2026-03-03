# MyRecall-v3 路线图（Edge-Centric, vision-only）

- 版本：v1.0
- 日期：2026-03-03
- 节奏原则：每阶段独立验收；Edge 从 Day 1 参与；P2/P3 功能冻结。

## 0. 引用基线

- 决策基线：[`decisions.md`](./decisions.md)
- 架构边界：[`architecture.md`](./architecture.md)
- 数据规范：[`data_model.md`](./data_model.md)
- API 契约：[`api_contract.md`](./api_contract.md)
- 指标口径：[`gate_baseline.md`](./gate_baseline.md)
- 验收归档：[`acceptance/`](./acceptance/)

## 1. 阶段目标与里程碑

## Phase 1：本机模拟 Edge（进程级隔离）

- 时间：2026-03-02 ~ 2026-03-20
- 目标：在本机双进程完成 v3 全链路功能闭环。
- 执行规则：P1-S1 -> P1-S2 -> P1-S3 -> P1-S4 -> P1-S5 -> P1-S6 -> P1-S7 串行推进。
- 关键引用 IDs：DEC-008A, DEC-009A, DEC-010A, DEC-011A, DEC-012A。

### P1-S1（基础链路）

- 交付：Host spool/uploader；Edge ingest/queue 骨架；页面可用。
- Gate：
  - 断网恢复自动重传 + 幂等去重正确。
  - `GET /v1/ingest/queue/status` 可观测完整。
  - 对外命名空间仅 `/v1/*`。
  - UI 路由可达率 = 100%。

### P1-S2（采集）

- 交付：事件驱动 capture + idle fallback + AX 文本采集上传。
- Gate：
  - 切窗场景 95% capture 在 3 秒内入队。
  - 300 events/min 下 Host CPU < 25%，丢包率 < 0.3%（[`GATE-CAPTURE-LOSS-001`](./gate_baseline.md#gate-capture-loss-001)）。
  - timeline 新 capture 可见性 >= 95%。

### P1-S3（处理）

- 交付：AX-first + OCR-fallback；Scheme C 分表写入；`text_source` 可追踪。
- Gate：
  - AX 成功帧写入 `accessibility` 表正确率 = 100%。
  - 决策日志可追溯率 >= 95%。
  - 索引时零 AI 增强检查通过率 = 100%。
  - UI 处理来源展示完整率 = 100%。
- 关键引用 IDs：DEC-018C, DEC-025A, DB-001。

### P1-S4（检索）

- 交付：`/v1/search`（含 `content_type`）；Scheme C 三路径分发；结果可回溯。
- Gate：
  - 精确词查询不低于对齐基线。
  - Search P95 <= 1.8s（[`GATE-SEARCH-P95-001`](./gate_baseline.md#gate-search-p95-001)）。
  - 搜索三路径分发一致性 = 100%。
  - `focused` 在 accessibility 路径过滤正确率 = 100%。
  - 检索结果引用字段完整率 = 100%。
- 关键引用 IDs：DEC-020A, DEC-022C, API-200, DB-001。

### P1-S5（Chat-1：Grounding 与引用）

- 交付：Pi Sidecar 基础能力；`/v1/chat` SSE；`myrecall-search` Skill；引用回溯。
- Gate：
  - Chat 工具能力清单完成率 = 100%。
  - 引用点击回溯成功率 >= 95%。
  - Soft KPI：引用覆盖率 >= 85%（non-blocking）（[`GATE-CITATION-001`](./gate_baseline.md#gate-citation-001)）。
- 关键引用 IDs：DEC-002A, DEC-013A, API-500。

### P1-S6（Chat-2：路由与流式）

- 交付：provider/model 路由；Pi 流式事件；timeout/健康状态可见。
- Gate：
  - Chat 首 token P95 <= 3.5s（[`GATE-CHAT-FIRST-TOKEN-001`](./gate_baseline.md#gate-chat-first-token-001)）。
  - provider 切换与 timeout 场景覆盖率 = 100%。
  - 流式协议一致性用例通过率 = 100%。

### P1-S7（端到端验收）

- 交付：故障注入回归；P1 功能冻结清单；UI 关键路径报告。
- Gate：
  - TTS P95 <= 12s（[`GATE-TTS-001`](./gate_baseline.md#gate-tts-001)）。
  - S1~S6 回归全通过。
  - P1 功能清单完成率 = 100%。
  - 验收记录完整率 = 100%。
  - UI 关键路径脚本通过率 = 100%。
  - Soft KPI：引用覆盖率 >= 92%（Stretch >= 95%，non-blocking）（[`GATE-CITATION-001`](./gate_baseline.md#gate-citation-001)）。

## Phase 2：LAN 双机（另一台 Mac 作为 Edge）

- 时间：2026-03-23 ~ 2026-04-17
- 目标：验证 LAN 稳定性与重放正确性（不新增功能）。
- 核心交付：24h soak 报告、链路瓶颈定位、mTLS 升级演练。
- 验收门槛：
  - 24h soak 无致命中断。
  - capture 丢失率 <= 0.2%（[`GATE-CAPTURE-LOSS-001`](./gate_baseline.md#gate-capture-loss-001)）。
  - 重放一致性通过率 = 100%。
  - mTLS 握手/证书轮换通过率 = 100%。
  - UI 关键路径 24h 致命中断次数 = 0。
  - Soft KPI：引用覆盖率 >= 92%（Stretch >= 95%）（[`GATE-CITATION-001`](./gate_baseline.md#gate-citation-001)）。

## Phase 3：Debian Edge（生产形态）

- 时间：2026-04-20 ~ 2026-05-29
- 目标：完成服务化部署与运维闭环（不新增功能）。
- 核心交付：Debian 部署、观测面板、灰度升级与回滚策略。
- 验收门槛：
  - 7 天稳定运行。
  - 部署脚本成功率 = 100%。
  - 回滚演练通过率 = 100%。
  - UI 关键路径 7 天致命中断次数 = 0。
  - Soft KPI：引用覆盖率 >= 92%（Stretch >= 95%）（[`GATE-CITATION-001`](./gate_baseline.md#gate-citation-001)）。

## 2. 工作流分解（按链路）

1. Capture：P1 完成功能；P2/P3 仅稳定性调优。
2. Processing：P1 完成 Scheme C；P2/P3 不新增处理功能。
3. Search：P1 完成 FTS+过滤与三路径分发；P2/P3 仅性能优化。
4. Chat：P1 完成 Pi Sidecar + 引用 + 路由流式；P2/P3 仅稳定性治理。
5. UI：P1 最小可用闭环；P2/P3 仅稳定性与异常可见性。

## 3. 风险清单（按优先级）

- P0：Edge 故障导致 Host 长时间积压。
- P0：Chat 引用质量不足影响可信度。
- P0：P1 范围膨胀导致延期。
- P1：事件触发过激导致采集风暴。
- P1：语义型查询召回下降影响 Chat grounding。

## 4. 里程碑退出条件（DoD）

每个阶段必须提供：

- 功能验收报告。
- 故障注入报告。
- 性能指标报告。
- 未决问题更新（写入 `open_questions.md`）。

## 5. 验收记录规范

- 每个阶段/子阶段 Gate 判定前必须完成对应 Markdown 验收记录。
- 验收记录缺失或不完整，视为 Gate 未通过。
- 记录模板：[`acceptance/TEMPLATE.md`](./acceptance/TEMPLATE.md)
- 归档入口：[`acceptance/README.md`](./acceptance/README.md)

## 6. 指标口径（SSOT）

- 所有公式、样本数、时间窗、百分位算法与 Pass/Fail 规则统一使用 [`gate_baseline.md`](./gate_baseline.md)。
- 若本文与 `gate_baseline.md` 冲突，以 `gate_baseline.md` 为准并在 48 小时内修订。

## 7. 禁止重复项

- 本文不得复制完整 DDL、完整 API schema、完整已决清单。
- 需要细节时必须通过 `DEC-* / DB-* / API-* / GATE-*` 引用对应 SSOT。
