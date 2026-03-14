---
status: active
owner: pyw
last_updated: 2026-03-13
depends_on:
  - open_questions.md
references:
  - spec.md
  - roadmap.md
---

# MyRecall-v3 Gate 指标口径基线（SSOT）

- 版本：v1.7
- 生效日期：2026-03-13
- 变更说明：
  - OQ-043 OCR-only 收口 — `inter_write_gap_sec` 移除，由 `capture_to_ingest_latency_ms` 替代
  - P1 不采集 Browser URL
- 适用范围：[spec.md](spec.md)、[roadmap.md](roadmap.md)、`adr/`、`acceptance/`

## 1. 口径优先级

- 本文是 Gate 与 SLO 的唯一口径源（Single Source of Truth）。
- 其他文档若与本文冲突，以本文为准，并在 48 小时内修订冲突文本。
- 适用边界：本文优先级仅适用于 Gate/SLO 指标口径（公式、样本、时间窗、判定规则）；API 契约与数据模型语义分别以 [spec.md](spec.md) 与 [data-model.md](data-model.md) 为准。

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

## 3.1 Search 引用字段完整率（P1-S4，OCR-only）

- 目的：统一 `/v1/search` OCR-only 结果的引用字段验收口径，避免将 v4 预留 seam 误当成 v3 活跃结果模型。
- 判定类型：
  - `Search 引用字段完整率`：**Hard Gate**
  - `Search capture_id 覆盖率`：**Soft KPI**（non-blocking）
- 阈值（P1-S4）：
  - Search 引用字段完整率 = 100%
  - Search capture_id 覆盖率目标 >= 99%（未达标需提交整改动作，不触发 Gate Fail）

定义：

1. `Search 引用字段完整率`（Hard Gate）
- 公式：`search_ref_completeness = (搜索结果中 frame_id 与 timestamp 同时非空的条数 / 搜索结果总条数) * 100%`

2. `Search capture_id 覆盖率`（Soft KPI）
- 公式：`search_capture_id_coverage = (搜索结果中 capture_id 非空的条数 / 搜索结果总条数) * 100%`
- 说明：`capture_id` 为 v3 增强可选字段，不属于 Search 对齐硬门槛；该指标仅用于质量观测与回归。

## 3.2 Capture 去重与背压口径（P1-S2）

- 目的：将 P1-S2 的去重/背压 Gate 从描述性判定收敛为自动化可计算指标。
- 统一压测窗口：5 分钟（重复内容压测与过载注入均使用该窗口）。

判定类型与阈值（P1-S2）：

1. `capture_latency_p95`（观测指标，**强制观测记录**）
- 公式：`capture_latency_ms = (frames.ingested_at - event_ts) * 1000`
- 事件定义：
  - `event_ts`：Host 侧触发事件时间（触发源：`idle/app_switch/manual/click`）
  - `frames.ingested_at`：Edge 侧该 capture 完成 SQLite 持久化的时间点（以 DB commit 成功为准；即原口径中的 `edge_db_persisted_ts`）
- 边界说明：`capture_latency_p95` 为触发到 Edge DB 持久化完成的端到端延迟，包含 Host->Edge 传输与 ingest 处理；不以 Host spool 落盘作为终点
- 说明：此指标为**观测指标**，P1-S2a 阶段强制观测并记录数值（建议记录 P50/P90/P95/P99），不参与 Gate Pass/Fail 判定

2. `trigger_coverage`（Hard Gate）
- 公式：`trigger_coverage = (covered_trigger_types / 4) × 100%`（目标触发类型固定为 `idle/app_switch/manual/click`）。
- 阈值：`= 100%`
- 最小样本：四类触发均命中，且每类样本 `>= 20`

3. `capture_to_ingest_latency_ms`（Soft KPI，P1-S2b 新增，替代 `inter_write_gap_sec`）
- 公式：`latency_ms = (frames.ingested_at - capture_completed_ts) * 1000`
  - `capture_completed_ts`：Host 侧 capture worker 完成截图并写入 spool 的时间戳
    - 在 P1-S2b 主链路中，`capture_completed_ts` 对应持久化 metadata 中的 `timestamp` 字段（即 Host 侧 capture-completion / spool-write completion time）
  - `ingested_at`：Edge 侧该 capture 完成 SQLite 持久化的时间点
- 类型：**Soft KPI only**（non-blocking，用于 S2b 质量观测）
- 分桶维度：`device_name`
- 观测口径：按 `device_name` 分桶记录 P50/P90/P95/P99 分布
- 最小样本：每设备 >= 50 captures
- 说明：
  - 该指标衡量 S2b 核心链路效率：spool handoff → upload → ingest
  - 若某设备 P95 显著高于其他，提示该 monitor worker 或 spool 分区存在瓶颈
- 窗口有效性：仅使用无 Host/Edge 重启的连续窗口；窗口内若发生 Host 或 Edge 重启，标记 `broken_window=true`

~~3. `inter_write_gap_sec`（已移除，OCR-only 下由 `capture_to_ingest_latency_ms` 替代）~~

4. `queue_saturation_ratio`（Hard Gate）
- 公式：`queue_saturation_ratio = (queue_depth >= 0.9 * queue_capacity 的采样数 / 总采样数) * 100%`
- 阈值：`<= 10%`
- 最小样本：队列深度采样点 `>= 300`

5. `collapse_trigger_count`（观测指标）
- 公式：过载注入窗口内 collapse 触发次数计数。
- 说明：用于证明背压保护路径是否被命中；`= 0` 不直接构成 Fail。

6. `overflow_drop_count`（Hard Gate）
- 公式：过载注入窗口内因通道溢出导致丢弃的 capture 数。
- 阈值：`= 0`

7. `trigger_target_routing_correctness`（Hard Gate，P1-S2b）
- 公式：`routing_correctness = (目标 monitor 归属正确的 trigger 数 / 参与判定的 trigger 总数) * 100%`
- 阈值：`= 100%`
- 最小样本：`idle/app_switch/manual/click` 四类 trigger 均命中，且每类样本 `>= 20`

8. `device_binding_correctness`（Hard Gate，P1-S2b）
- 公式：`device_binding_correctness = (capture metadata 中 device_name 与实际截图 monitor 一致的 capture 数 / 参与判定的 capture 总数) * 100%`
- 阈值：`= 100%`
- 最小样本：`>= 100 captures`

9. `single_monitor_duplicate_capture_rate`（Hard Gate，P1-S2b）
- 公式：`duplicate_capture_rate = (单 monitor 作用域产生重复 capture 的 frame 数 / 单 monitor 作用域入库 frame 总数) * 100%`
- **"重复 capture" 定义**：需同时满足以下条件：
  1. 同一 `device_name`（单 monitor 作用域）
  2. 实际产生了 >1 个持久化 frame（被 debounce 丢弃的不计入）
  3. 这些 frames 归属于同一 user action，且落在同一 `min_capture_interval_ms` 窗口内
- **不计入情形**：
  - Debounce 阶段被丢弃的 trigger（未产生 frame，见 `p1-s2b.md` §3.2 第 3 点）
  - 不同 user action 产生的 frame（即使时间接近）
  - 同一 user action 产生的多帧但明确属于跨 monitor 并行 capture
- 阈值：`= 0%`
- 最小样本：`>= 100` 个单 monitor 作用域 trigger
- **实现说明**：正常情况下 debounce 机制（`min_capture_interval_ms` 窗口）确保同一 monitor 窗口期内只保留第一个 trigger，后续 trigger 被丢弃且不截图。本指标是机械性的 coordination Gate，不依赖 simhash / content_hash / 图像相似度算法。

10. `topology_rebuild_correctness`（Hard Gate，P1-S2b）
- 公式：`topology_rebuild_correctness = (monitor topology 变化后恢复正确分发的场景数 / monitor topology 变化场景总数) * 100%`
- 阈值：`= 100%`
- 最小场景集：至少覆盖 monitor 增加、移除、primary 切换、monitor 不可用恢复各 `>= 1` 次

11. `Host CPU`（Soft KPI，non-blocking）
- 说明：CPU 使用率仅用于趋势观测与容量评估，不作为跨设备 Gate 判定条件。
- 记录要求：验收报告需附硬件基线（机型/芯片/核心数）与负载背景（后台任务、显示器配置）。

## 3.3 UI 健康态/错误态展示通过率（P1-S1）

- 目的：将 P1-S1 的 UI 健康态/错误态从描述性要求收敛为可脚本化判定，避免主观评审。
- 判定类型：**Hard Gate**（任一页面未达标即阶段 Fail）。

### 3.3.1 默认时序参数（SSOT）

以下参数为 P1-S1 Gate 判定口径的一部分（实现可配置，但验收必须以本节为准）：

- `poll_interval_ms = 5000`
- `request_timeout_ms = 2000`
- `unreachable_grace_ms = 5000`

### 3.3.2 可验证锚点（Hard Requirement）

- 三个页面 `/`、`/search`、`/timeline` 首屏必须存在稳定 DOM 选择器：`#mr-health`
- `#mr-health` 必须暴露：`data-state="healthy|unreachable|degraded"`
- Gate 判定以 `#mr-health` 与 `data-state` 为准（文案用于人类可解释性，不作为唯一判定依据）。

### 3.3.3 通过率定义

- 页面集合：`P = {"/", "/search", "/timeline"}`，`|P| = 3`
- `ui_health_state_pass_rate = (pass_pages / 3) * 100%`
- Hard Gate 阈值：`ui_health_state_pass_rate = 100%`

### 3.3.4 页面通过条件（P1-S1）

对任一页面 `p in P`，满足以下全部条件则 `p` 通过：

1) **健康态可见**：`#mr-health[data-state="healthy"]` 可见，且页面文案包含 `服务健康/队列正常`。

2) **UNREACHABLE 可见（禁止刷新页面）**：
- 在页面完成首屏渲染后（不刷新页面），制造浏览器侧对 `GET /v1/health` 的请求失败/超时（例如停止 Edge 进程，或 DevTools 对 `/v1/health` 启用 request blocking）。
- 该页面必须在 **15 秒内**进入 `#mr-health[data-state="unreachable"]`，且页面文案包含 `Edge 不可达`。

3) **自动恢复（禁止刷新页面）**：
- 恢复 `GET /v1/health` 可达（例如启动 Edge 进程，或解除 request blocking）。
- 该页面必须在 **10 秒内**自动回到 `#mr-health[data-state="healthy"]`，且页面文案包含 `服务健康/队列正常`。

说明：15s/10s 为可操作的验收时间窗，覆盖 `unreachable_grace_ms + poll_interval_ms + request_timeout_ms` 的最坏情况并预留抖动余量。

## 4. 指标定义（统一公式）

1. `Citation Coverage`（DA-8A 默认口径）
- 公式：`coverage = (有有效引用的回答数 / 应当提供引用的回答总数) * 100%`
- 有效引用（DA-8A）：
  - OCR/frame 结果：回答中包含可解析 deep link `myrecall://frame/{frame_id}`
- UI 落点：点击 `myrecall://frame/{id}` 后统一落到 `/timeline`，通过 `GET /v1/frames/:frame_id/metadata`（timestamp resolver，最小稳定契约）解析 timestamp 定位
- 说明：`GET /v1/frames/:frame_id/context` 为可选增强（URL/上下文提取），不作为 P1 Gate 前置条件
  - `frame_id`/`timestamp` 必须来自真实检索结果，不得伪造。
- 结构化增强（DA-8B，可选）：在 DA-8A 基础上，`chat_messages.citations` 可写入结构化引用（`frame_id`/`timestamp`，可选 `capture_id`）；未启用 DA-8B 前，不作为 Gate 前置条件。

2. `TTS P95`（Time-to-Searchable）—— 分层定义

### 2.1 OCR主路径 TTS（Soft KPI）
- 公式：Host capture timestamp → ocr_text表写入完成且FTS索引就绪
- 目标：P95 <= 15s
- 样本占比预期：v3 主线 `~100% captures`
- P1 引擎口径：OCR 主路径统一按 RapidOCR 路径统计（不做跨引擎归一化）
- 说明：OCR路径受分辨率、CPU负载、模型性能影响大，作为观测项而非 Gate Fail 条件
- 超标处置：若OCR路径P95 > 15s，验收报告需附加根因分析（分辨率分布/CPU瓶颈/队列深度）

### 2.2 全局TTS P95（参考值）
- 阈值：<= 15s（P1-S7记录，不强制Gate）
- 测量方法：不分路径，全量capture的TTS分布
- 用途：端到端体验趋势观测，用于P2 LAN场景的性能基线对比

3. `Search P95`（P1 阶段记录实际值，暂不设硬性阈值）
- 统计范围：`GET /v1/search`（含 keyword 检索语义）。
- 起点：Edge API 收到请求。
- 终点：Edge API 返回最后一个字节。
- 标准时间窗：查询窗口 <= 24h（超大时间窗单独统计，不纳入统计）。
- P1 阶段策略：记录实际 P95 分布，暂不设硬性阈值。
- 阈值确定：参考 screenpipe `timeline_performance_test.rs`（5s 以上被视为问题），在 P1-S7 前根据实测数据确定最终目标。

4. `Chat 系统可用率`（P1-S6 主 Gate）
- 公式：`chat_availability = (1 - 系统错误次数 / 总请求数) * 100%`
- **系统错误定义**（计入失败）：
  - Pi Sidecar 进程 crash（exit code ≠ 0）
  - Manager 协议错误（无法解析的 Pi 事件、SSE 序列化失败）
  - Edge 内部 500 错误（数据库异常、资源耗尽）
- **排除项**（不计入失败，但计入分母）：
  - OpenAI/Claude 等 provider 5xx 错误
  - Provider 429 限流错误
  - 180s 请求 timeout（业务逻辑边界，见观测指标）
- 阈值：`>= 98%`
- 最小样本：>= 100 requests
- 用户主动 abort 不计入样本

5. `Chat 完成率`（Soft KPI，non-blocking）
- 公式：`chat_completion_rate = (成功完成请求数 / 总请求数) * 100%`
- 成功完成：请求在 180s 内返回成功 `response` 事件
- 包含所有错误类型（含 provider 错误、timeout）
- 目标：`>= 95%`
- 说明：用于端到端体验趋势观测，不参与 Gate Pass/Fail 判定

6. `Chat 首 token P95`（观测 KPI，non-blocking）
- 起点：Edge Chat API 收到请求。
- 终点：流式通道发出第一个 token。
- 目标：`<= 3.5s`

7. `Chat 完成时间分布`（新增观测）
- P50/P90/P99 完成时间（从请求到 `response` 事件）
- 用于验证 180s timeout 阈值合理性及识别长尾延迟
- 观测维度：按 provider（OpenAI/Claude/Ollama）分别统计
- 起点：Edge Chat API 收到请求。
- 终点：流式通道发出第一个 token。

8. `Capture 丢失率`
   - 公式：`loss_rate = (应到达 capture 数 - 成功 commit capture 数) / 应到达 capture 数`
   - 阈值：
     - P1-S2：< 0.3%（压测环境）
     - Phase 2：<= 0.2%（生产环境）
     - Phase 3：<= 0.1%（生产稳定期）

9. **运行机制与压测假设（P1）**
   - 运行机制（SSOT）：Capture 采用事件驱动触发（`idle/app_switch/manual/click`），其中 `idle` 为 timeout fallback 事件。
   - 压测假设（仅用于可比性）：部分 Gate 使用固定事件注入速率（如 `300 events/min`）作为测试条件，不代表生产运行机制为固定频率轮询。
   - 参数口径：

| 参数 | 单位 | P1 默认 | 分类 | 说明 |
|---|---|---:|---|---|
| `min_capture_interval_ms` | ms | 1000 | 主参数 | 全触发共享最小间隔去抖；有意偏离 screenpipe Performance 模式（200ms），Python 实现安全起点 |
| `idle_capture_interval_ms` | ms | 30000 | 主参数 | 无事件时触发 `idle` fallback 的最大空窗 |
| `OPENRECALL_CAPTURE_INTERVAL` | s | legacy | 兼容参数 | 不作为 P1 主触发机制；仅当未显式设置 `idle_capture_interval_ms` 时映射为 `idle_capture_interval_ms = OPENRECALL_CAPTURE_INTERVAL * 1000` |

   - screenpipe v0.3.160 引入 Power Profile（Performance/Balanced/Saver，`power/profile.rs`），动态调整捕获间隔。MyRecall-v3 P1 不实现此能力。
   - **若 P2+ 引入 Power Profile，TTS P95 与 Capture 丢失率的 SLO 阈值须按各 profile（至少覆盖 Saver 最坏情况）重新定义。**

## 5. 统计与采样规则

- 百分位算法：Nearest-rank。
- 预热剔除：每轮测量剔除前 10 个样本。
- 最小样本数（低于该值不得做有效判定）：
- TTS（分层独立统计）：
    - OCR主路径：>= 100 captures（用于Soft KPI观测）
    - 全局：>= 100 captures（v3 中通常与 OCR 主路径样本集一致；用于趋势参考）
  - Search：>= 200 queries
  - Chat 系统可用率：>= 100 requests
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
