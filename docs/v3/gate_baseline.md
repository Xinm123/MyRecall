---
status: active
owner: pyw
last_updated: 2026-03-04
depends_on:
  - open_questions.md
references:
  - spec.md
  - roadmap.md
---

# MyRecall-v3 Gate 指标口径基线（SSOT）

- 版本：v1.3
- 生效日期：2026-02-26
- 适用范围：`spec.md`、`roadmap.md`、`adr/`、`acceptance/`

## 1. 口径优先级

- 本文是 Gate 与 SLO 的唯一口径源（Single Source of Truth）。
- 其他文档若与本文冲突，以本文为准，并在 48 小时内修订冲突文本。

## 2. 指标类型定义

- Hard Gate（硬门槛）：任一项不达标即阶段 `Fail`。
- SLO Gate（数值门槛）：按阶段阈值判定，超阈值即阶段 `Fail`。
- Soft KPI（软约束）：用于质量观测与回归，不作为阶段 `Fail` 条件。
- Stretch KPI（拉伸目标）：用于持续优化，不作为阶段 `Fail` 条件。

## 3. Chat 引用覆盖率（Soft KPI）

| 阶段 | Soft KPI 目标 | Stretch KPI |
|---|---:|---:|
| P1-S5 | >= 85% | >= 95% |
| P1-S7 | >= 92% | >= 95% |
| Phase 2 | >= 92% | >= 95% |
| Phase 3 | >= 92% | >= 95% |

- 说明：Chat 引用覆盖率不参与 Gate Pass/Fail 判定；若低于目标，必须在验收记录中给出整改动作与回归计划。

## 3.1 Search 引用字段完整率（P1-S4）

- 目的：统一 `/v1/search` 在 `OCR`/`UI` 两类结果下的引用字段验收口径，避免将类型化结果误判为统一字段模型。
- 判定类型：
  - `OCR 引用字段完整率`：**Hard Gate**
  - `UI 引用字段完整率`：**Hard Gate**
  - `OCR capture_id 覆盖率`：**Soft KPI**（non-blocking）
- 阈值（P1-S4）：
  - OCR 引用字段完整率 = 100%
  - UI 引用字段完整率 = 100%
  - OCR capture_id 覆盖率目标 >= 99%（未达标需提交整改动作，不触发 Gate Fail）

定义：

1. `OCR 引用字段完整率`（Hard Gate）
- 公式：`ocr_ref_completeness = (OCR 结果中 frame_id 与 timestamp 同时非空的条数 / OCR 结果总条数) * 100%`

2. `UI 引用字段完整率`（Hard Gate）
- 公式：`ui_ref_completeness = (UI 结果中 frame_id 与 timestamp 同时非空的条数 / UI 结果总条数) * 100%`
- 说明：P1 阶段正常 paired_capture 路径下 accessibility.frame_id 应为非 NULL（由 paired_capture 写入）

3. `OCR capture_id 覆盖率`（Soft KPI）
- 公式：`ocr_capture_id_coverage = (OCR 结果中 capture_id 非空的条数 / OCR 结果总条数) * 100%`
- 说明：`capture_id` 为 v3 增强可选字段，不属于 Search 对齐硬门槛；该指标仅用于质量观测与回归。

## 3.2 Capture 去重与背压口径（P1-S2）

- 目的：将 P1-S2 的去重/背压 Gate 从描述性判定收敛为自动化可计算指标。
- 统一压测窗口：5 分钟（重复内容压测与过载注入均使用该窗口）。

判定类型与阈值（P1-S2）：

1. `enqueue_latency_p95`（Hard Gate）
- 公式：`enqueue_latency_sec = edge_enqueued_ts - event_ts`，按样本分布计算 P95。
- 阈值：`P95(enqueue_latency_sec) <= 3s`
- 最小样本：`eligible_events >= 200`

2. `trigger_coverage`（Hard Gate）
- 公式：`trigger_coverage = covered_trigger_types / 4`（目标触发类型固定为 `idle/app_switch/manual/click`）。
- 阈值：`= 100%`
- 最小样本：四类触发均命中，且每类样本 `>= 20`

3. `dedup_skip_rate`（Hard Gate）
- 公式：`dedup_skip_rate = (dedup_skipped / dedup_eligible) * 100%`
- 阈值：`>= 95%`
- 最小样本：`dedup_eligible >= 500`

4. `inter_write_gap_sec`（Hard Gate）
- 公式：相邻两次成功写入时间差（秒）构成样本分布。
- 阈值：`P99 <= 30s` 且 `max <= 45s`
- 最小样本：成功写入样本 `>= 100`

5. `queue_saturation_ratio`（Hard Gate）
- 公式：`queue_saturation_ratio = (queue_depth >= 0.9 * queue_capacity 的采样数 / 总采样数) * 100%`
- 阈值：`<= 10%`
- 最小样本：队列深度采样点 `>= 300`

6. `collapse_trigger_count`（Hard Gate）
- 公式：过载注入窗口内 collapse 触发次数计数。
- 阈值：`>= 1`

7. `overflow_drop_count`（Hard Gate）
- 公式：过载注入窗口内因通道溢出导致丢弃的 capture 数。
- 阈值：`= 0`

8. `Host CPU`（Soft KPI，non-blocking）
- 说明：CPU 使用率仅用于趋势观测与容量评估，不作为跨设备 Gate 判定条件。
- 记录要求：验收报告需附硬件基线（机型/芯片/核心数）与负载背景（后台任务、显示器配置）。

## 4. 指标定义（统一公式）

1. `Citation Coverage`（DA-8A 默认口径）
- 公式：`coverage = (有有效引用的回答数 / 应当提供引用的回答总数) * 100%`
- 有效引用（DA-8A）：
  - OCR 结果：回答中包含可解析 deep link `myrecall://frame/{frame_id}`
  - UI 结果：回答中包含可解析 deep link `myrecall://frame/{accessibility.frame_id}`（v3 改进，外键精确关联）
  - 无 frame_id 时回退 `myrecall://timeline?timestamp=ISO8601`（仅未来独立 walker 场景，P1 不触发）
  - UI 落点：点击 `myrecall://frame/{id}` 后统一落到 `/timeline`，通过 `GET /v1/frames/:frame_id/metadata` 解析 timestamp 定位
  - `frame_id`/`timestamp` 必须来自真实检索结果，不得伪造。
- 结构化增强（DA-8B，可选）：在 DA-8A 基础上，`chat_messages.citations` 可写入结构化引用（`frame_id`/`timestamp`，可选 `capture_id`）；未启用 DA-8B 前，不作为 Gate 前置条件。

2. `TTS P95`（Time-to-Searchable）
- 起点：Host 侧 capture 事件时间戳。
- 终点：该 capture 首次可被 `GET /v1/search` 查询返回的时间点。

3. `Search P95`（P1 阶段记录实际值，暂不设硬性阈值）
- 统计范围：`GET /v1/search`（含 keyword 检索语义）。
- 起点：Edge API 收到请求。
- 终点：Edge API 返回最后一个字节。
- 标准时间窗：查询窗口 <= 24h（超大时间窗单独统计，不纳入统计）。
- P1 阶段策略：记录实际 P95 分布，暂不设硬性阈值。
- 阈值确定：参考 screenpipe `timeline_performance_test.rs`（5s 以上被视为问题），在 P1-S7 前根据实测数据确定最终目标。

4. `Chat 请求成功率`（P1-S6 主 Gate）
- 公式：`chat_success_rate = (成功请求数 / 总请求数) * 100%`
- 成功判定：请求在 180s 内完成并返回成功响应（流式完成或等价成功终止事件）。
- 失败判定：timeout（180s）、provider error、Pi crash、协议错误等导致请求未成功完成。
- 计数规则：timeout 必须计入分母且记为失败，不得剔除；用户主动 abort 不计入样本。

5. `Chat 首 token P95`（观测 KPI，non-blocking）
- 起点：Edge Chat API 收到请求。
- 终点：流式通道发出第一个 token。

6. `Capture 丢失率`
   - 公式：`loss_rate = (应到达 capture 数 - 成功 commit capture 数) / 应到达 capture 数`

7. **频率假设与 Power Profile 备注**
   - P1 所有 SLO 均基于固定捕获频率假设（由 `OPENRECALL_CAPTURE_INTERVAL` 配置）。
   - screenpipe v0.3.160 引入 Power Profile（Performance/Balanced/Saver，`power/profile.rs`），动态调整捕获间隔。MyRecall-v3 P1 不实现此能力。
   - **若 P2+ 引入 Power Profile，TTS P95 与 Capture 丢失率的 SLO 阈值须按最坏情况（Saver 模式）重新定义。**

## 5. 统计与采样规则

- 百分位算法：Nearest-rank。
- 预热剔除：每轮测量剔除前 10 个样本。
- 最小样本数（低于该值不得做有效判定）：
  - TTS：>= 200 captures
  - Search：>= 200 queries
  - Chat 请求成功率：>= 100 requests
  - Chat 首 token（观测，可选）：>= 100 requests（若输出该指标）
  - Citation Coverage（Soft KPI）：
    - P1-S5：>= 80 个问答样本
    - P1-S7 / Phase2 / Phase3：>= 100 个问答样本
- 重试样本：同一请求重试只计第一次失败与最终结果，不得重复计入成功样本。

## 6. 验收证据要求

- 每次 Gate 必须附：
  - 原始日志路径
  - 原始统计脚本或 SQL
  - 指标汇总表（含样本数、P50/P95/P99）
  - Pass/Fail 结论与未达标项整改动作
- 若包含 Soft KPI（如 Citation Coverage）：
  - 必须附偏差分析与后续回归计划
