# MyRecall-v3 Gate 指标口径基线（SSOT）

- 版本：v1.2
- 生效日期：2026-02-26
- 更新日期：2026-03-03
- 适用范围：`spec.md`、`roadmap.md`、`adr/`、`acceptance/`

## 1. 口径优先级

- 本文是 Gate 与 SLO 的唯一口径源（Single Source of Truth）。
- 其他文档若与本文冲突，以本文为准，并在 48 小时内修订冲突文本。

## 2. Gate ID 索引

| ID | 指标 |
|---|---|
| GATE-TTS-001 | TTS P95 |
| GATE-CAPTURE-LOSS-001 | Capture 丢失率 |
| GATE-SEARCH-P95-001 | Search P95 |
| GATE-CHAT-FIRST-TOKEN-001 | Chat 首 token P95 |
| GATE-CITATION-001 | Citation Coverage（Soft KPI） |
| GATE-FUNC-001 | 功能完成度/完善度强制项 |

## 3. 指标类型定义

- Hard Gate（硬门槛）：任一项不达标即阶段 `Fail`。
- SLO Gate（数值门槛）：按阶段阈值判定，超阈值即阶段 `Fail`。
- Soft KPI（软约束）：用于质量观测与回归，不作为阶段 `Fail` 条件。
- Stretch KPI（拉伸目标）：用于持续优化，不作为阶段 `Fail` 条件。

## 4. `GATE-CITATION-001` Chat 引用覆盖率（Soft KPI）

| 阶段 | Soft KPI 目标 | Stretch KPI |
|---|---:|---:|
| P1-S5 | >= 85% | >= 95% |
| P1-S7 | >= 92% | >= 95% |
| Phase 2 | >= 92% | >= 95% |
| Phase 3 | >= 92% | >= 95% |

- 说明：Chat 引用覆盖率不参与 Gate Pass/Fail 判定；若低于目标，必须在验收记录中给出整改动作与回归计划。

## 5. 指标定义（统一公式）

### 5.1 `GATE-CITATION-001` Citation Coverage（DA-8A 默认口径）

- 公式：`coverage = (有有效引用的回答数 / 应当提供引用的回答总数) * 100%`
- 有效引用（DA-8A）：回答中包含可解析 deep link（`myrecall://frame/{frame_id}` 或 `myrecall://timeline?timestamp=ISO8601`），且能回溯到真实 frame/timeline；`frame_id`/`timestamp` 必须来自真实检索结果，不得伪造。
- 结构化增强（DA-8B，可选）：在 DA-8A 基础上，`chat_messages.citations` 可写入结构化引用（`frame_id`/`timestamp`，可选 `capture_id`）；未启用 DA-8B 前，不作为 Gate 前置条件。

### 5.2 `GATE-TTS-001` TTS P95（Time-to-Searchable）

- 起点：Host 侧 capture 事件时间戳。
- 终点：该 capture 首次可被 `GET /v1/search` 查询返回的时间点。

### 5.3 `GATE-SEARCH-P95-001` Search P95

- 统计范围：`GET /v1/search`。
- 起点：Edge API 收到请求。
- 终点：Edge API 返回最后一个字节。
- 标准时间窗：查询窗口 <= 24h（超大时间窗单独统计，不纳入 Gate）。

### 5.4 `GATE-CHAT-FIRST-TOKEN-001` Chat 首 token P95

- 起点：Edge Chat API 收到请求。
- 终点：流式通道发出第一个 token。

### 5.5 `GATE-CAPTURE-LOSS-001` Capture 丢失率

- 公式：`loss_rate = (应到达 capture 数 - 成功 commit capture 数) / 应到达 capture 数`

### 5.6 频率假设与 Power Profile 备注

- P1 所有 SLO 均基于固定捕获频率假设（由 `OPENRECALL_CAPTURE_INTERVAL` 配置）。
- screenpipe v0.3.160 引入 Power Profile（Performance/Balanced/Saver，`power/profile.rs`）动态调整捕获间隔。MyRecall-v3 P1 不实现此能力。
- 若 P2+ 引入 Power Profile，TTS P95 与 Capture 丢失率阈值须按最坏情况（Saver）重新定义。

## 6. 统计与采样规则

- 百分位算法：Nearest-rank。
- 预热剔除：每轮测量剔除前 10 个样本。
- 最小样本数（低于该值不得做有效判定）：
  - TTS：>= 200 captures
  - Search：>= 200 queries
  - Chat 首 token：>= 100 requests
  - Citation Coverage：
    - P1-S5：>= 80 问答样本
    - P1-S7 / Phase2 / Phase3：>= 100 问答样本
- 重试样本：同一请求重试只计第一次失败与最终结果，不得重复计入成功样本。

## 7. `GATE-FUNC-001` 功能完成度/完善度强制项

- 功能清单完成率（目标：100%）
- API/Schema 契约完成率（目标：100%）
- 关键异常与降级场景通过率（目标：>= 95%）
- 可观测性检查项完成率（目标：100%，至少含日志/指标/错误码）
- UI 关键路径通过率（按阶段定义，目标：100%）
- 验收文档完整率（目标：100%）

## 8. 验收证据要求

每次 Gate 必须附：

- 原始日志路径
- 原始统计脚本或 SQL
- 指标汇总表（含样本数、P50/P95/P99）
- Pass/Fail 结论与未达标项整改动作

若包含 Soft KPI（如 Citation Coverage）：

- 必须附偏差分析与后续回归计划。
