# P1-S2b 验收记录（AX 采集）

- 阶段：P1-S2b
- 日期：2026-03-09（Entry Contract 定稿；2026-03-09 更新 Browser URL 策略）
- 负责人：pyw
- 版本/提交：待定
- 状态：`Entry Contract Ready`
- ADR：[ADR-0013](../../adr/ADR-0013-event-driven-ax-split.md)
- 依赖：P1-S2a（事件驱动触发机制）

## 0. screenpipe 对照与对齐

- screenpipe 做法：`paired_capture` 在事件触发时同步执行 AX 树遍历，提取 accessibility 文本。
- **AX 树遍历对齐**：
  - screenpipe 使用 AXUIElement (cidre Rust bindings)
  - MyRecall v3 使用 pyobjc / macapptree (Python)
  - 提取字段对齐：AXValue, AXTitle, AXDescription, browser_url
- **content_hash 对齐**：
  - screenpipe 使用 DefaultHasher (u64, 精确匹配)
  - MyRecall v3 使用 SHA256 (hex, 精确匹配)
  - 两者行为一致（精确匹配去重），SHA256 具有跨 session 一致性优势
- **实现语言**：Python（详见 ADR-0013）
- **平台策略**：macOS-only（P1 仅实现 macOS，Windows/Linux 推迟 P2）
- **去抖对齐（有意偏离）**：
  - screenpipe Performance 模式使用 `min_capture_interval_ms=200ms`（5 Hz）
  - MyRecall v3 P1 使用 `min_capture_interval_ms=1000ms`（1 Hz）—— Python 实现的安全起点
- **性能策略（关键决策，继承自 P1-S2a）**：
  - P1/P2 阶段采用保守频率（1 Hz），有意偏离 screenpipe（5 Hz）
  - 性能监控 `capture_latency_p95` 作为采集链路观测指标（non-blocking）

## 1. 范围与目标

- 范围：macOS AXUIElement 树遍历、文本提取、Browser URL 提取、content_hash 计算、权限处理。
- 目标：验证 AX 文本采集质量与 content_hash 去重效果。
- 对应 Gate 条件：
  - `content_hash` 覆盖率 >= 90%（`ax_hash_eligible`：`TRIM(COALESCE(accessibility_text, '')) <> ''` 的已上传帧）
  - AX 树遍历超时 < 500ms（P95）
  - `inter_write_gap_sec`：Soft KPI（记录 P50/P90/P99）+ Hard Gate（按 `device_name` 分桶，每设备 max <= 45s，样本 >= 100）

### 1.0 In-scope outcomes（本阶段必须交付）

- macOS AXUIElement 树遍历（深度限制 + 超时保护）
  - **walk_timeout = 500ms**（有意偏离 screenpipe 默认 250ms，适配复杂 Electron 应用）
  - **element_timeout = 200ms**（与 screenpipe 一致）
  - **max_nodes = 5000**（与 screenpipe 一致）
  - **max_depth = 30**（与 screenpipe 一致）
- 文本提取（AXValue, AXTitle, AXDescription）
- Browser URL 提取（Chrome/Safari/Edge 为 required evidence；Arc 为 AppleScript heuristic sub-scope）
- `content_hash` 计算（SHA256，精确匹配，与 screenpipe DefaultHasher 行为一致）
- 权限检测与 TCC 引导（Accessibility 权限）
- **AX 降级策略**（与 screenpipe 对齐）：
  - 截图始终写入磁盘（永不阻塞）
  - AX 树遍历超时保护：500ms，超时后继续处理已获取部分
  - AX 返回有文本 → 上传 raw AX 文本，供 S3 直接判定为 `accessibility`
  - AX 返回空文本/失败 → 仍上传 raw AX 结果，供 S3 执行 OCR fallback 判定
  - `text_source` 最终标记：由 S3 处理阶段判定（S2b 不负责）
  - 语义边界（强制）：
    - `AX timeout / AX empty` 的最终语义归属 S3；S2b 仅负责 raw handoff 不丢帧、字段语义正确。
    - `permission denied/revoked` 属于能力失效分支，必须进入权限降级流程，不得仅按 OCR fallback 吞掉异常。
    - `focused_context = {app_name, window_name, browser_url}`；`capture_device_binding = {device_name}`。
    - `app_name/window_name` 必须来自同一次 capture 的同源上下文快照（最终以 AX snapshot 为准）；禁止对 app/window 分别二次查询后拼接。
    - 若同帧无法确认 window 归属，`window_name` 必须置 `NULL/None`；禁止写入明显错误窗口（原则：**Better None than wrong window**）。
  - **Electron 异步树构建**：首次遍历可能返回空文本（Chromium 异步构建 DOM 树），下次事件触发时自然获得完整文本；空文本帧由 OCR fallback 兜底
- **Browser URL 提取策略**（与 screenpipe 完全对齐）：
  - **三层 Fallback 链**：
    - Tier 1: AXDocument 属性（Chrome/Safari/Edge，无延迟）
    - Tier 2: AppleScript（Arc 专用，~107ms 延迟）
    - Tier 3: AXTextField shallow walk（兜底）
  - **Arc Stale URL 检测**（对齐 screenpipe `url_timing_test.rs`）：
    - 问题：AppleScript 有 ~107ms 延迟，期间用户切换 tab 会导致 URL 与截图不匹配
    - 方案：同时获取 title + URL，与 window_title 进行 cross-check
    - 不匹配时返回 None（拒绝 stale URL）
    - 设计原则：**Better None than wrong URL**
  - **Title 匹配算法**（`titles_match()`）：
    - 去除 badge 计数：`(45) WhatsApp` → `WhatsApp`、`[2] Gmail` → `Gmail`
    - 大小写不敏感匹配
    - 包含匹配（处理标题截断）
  - content_hash 仅基于 text_content，不包含 browser_url（与 screenpipe 一致）
  - 提取失败返回 None，不阻断 capture
  - **失败分类统计**：
    | 指标 | 说明 |
    |------|------|
    | `browser_url_success` | 返回有效 http(s) URL |
    | `browser_url_rejected_stale` | Arc title mismatch（stale 被拒绝）|
    | `browser_url_failed_all_tiers` | 三层 fallback 全失败 |
    | `browser_url_skipped` | 非 browser 应用 |
  - **成功率口径**：success / (success + rejected_stale + failed_all_tiers) >= 95%（观测指标）

### 1.0b Out-of-scope（本阶段明确不做）

- 事件监听框架（已完成于 P1-S2a）
- AX-first 处理逻辑（属于 P1-S3）
- OCR fallback（属于 P1-S3；P1 策略固定为 RapidOCR，不做多引擎对比）
- `/v1/search` 与 `/v1/chat` 功能完成（分别属于 P1-S4/P1-S5+ 范围）
- Windows/Linux AX 采集（属于 P2）
- Arc Browser AppleScript URL 提取（timeboxed optional sub-scope；若 S2b Day 3 仍不稳定，则 defer，不影响 S2b 主 Gate）

### 1.0c S2b -> S3 handoff contract（进入 P1-S3 前冻结）

- S2b 仅负责采集与上传，不负责 `text_source` 判定，不负责 `accessibility/ocr_text` 分表写入。
- 上传契约：`POST /v1/ingest` 的 CapturePayload 必须包含 `accessibility_text` 与 `content_hash` 两个字段：`accessibility_text` 必须为 string（允许 `""`，禁止 `null`）；`content_hash` 必须存在且值为 `sha256:...` 或 `null`（禁止 `""`）。
- 空 AX 文本语义：当 AX 结果为空（含仅空白）时，S2b 必须仍然上传该帧，不得因空 AX 丢弃 capture；该帧由 S3 执行 OCR fallback。
- 空 AX 上传语义：空 AX 帧上传时必须满足 `accessibility_text=""` 且 `content_hash=null`。
- Handoff 可审计性：S2b 上传的原始 `accessibility_text` 必须可追溯，S3 仅可基于 `TRIM(COALESCE(accessibility_text, ''))` 做空值判定，不得要求 S2b 承担处理阶段语义。
- S2b Gate 口径：`content_hash` 覆盖率仅基于 `ax_hash_eligible = TRIM(COALESCE(accessibility_text, '')) <> ''` 的已上传帧；不得以 `frames.text_source` 作为分母过滤条件。
- 上下文一致性契约：CapturePayload 中 `app_name/window_name/browser_url` 必须由同一轮 focused-context snapshot 一次性产出；允许整体缺失/部分为 `None`，但不允许字段级跨来源混拼。
- device-binding 契约：`device_name` 表示实际被截取的 monitor，要求与本次 capture cycle 一致，不要求与 `focused_context` 同源。
- `browser_url` 仅可在与 `focused_context` 交叉校验一致时写入；校验失败或 stale 时必须置 `None`（原则：**Better None than wrong URL**）。
- `content_hash` 仅可基于最终上报的 `accessibility_text` 计算；计算前必须执行与 [../../spec.md](../../spec.md) 一致的 canonicalization；空字符串对应 `content_hash=null`，partial AX text 仍正常计算 hash。
- 一致性验收口径：新增 `app_window_mismatch_rate`（抽样人工核验 + 自动规则）并作为 S2b 观测指标，目标接近 0；出现不确定样本时按 `window_name=None` 处理，不计错填。

### 1.0d Input dependencies from stable P1-S2a contracts

- 触发机制：`idle/app_switch/manual/click` 触发事件（由 P1-S2a 提供）
- `capture_trigger` 字段赋值逻辑（由 P1-S2a 实现）
- 去抖门控（`min_capture_interval_ms=1000`，由 P1-S2a 实现，1 Hz 安全起点）
- 性能监控框架（`capture_latency_p95`，由 P1-S2a 引入）
- 队列安全边界（由 P1-S2a 验证）：`queue_saturation_ratio <= 10%`、`overflow_drop_count = 0`；`collapse_trigger_count` 仅保留为观测指标
- **Host 端 dedup 判定**（P1-S2b 新增）：
  - Host 在 capture 完成并生成 `accessibility_text/content_hash` 后、upload 前执行 dedup 判定，避免重复图片上传
  - dedup 条件：非 idle/manual + 距上次写入 < 30s + content_hash 相同
  - 空文本不参与 dedup（与 screenpipe 对齐）
  - dedup 判定成功后不调用 ingest API
  - `last_write_time` 的语义固定为最近一次成功写入 Host 本地 spool 的时间

### 1.0e Stage 2 alignment (frozen screenpipe-style monitor semantics)

- 目标：对齐 screenpipe 的“全局 trigger 广播 + 每 monitor 独立 capture loop”语义，消除触发语义与采样语义耦合。
- 设计约束：event source 仅发 trigger（不绑定 device）；`device_name` 由 monitor worker 在消费 trigger 时确定。
- `primary_monitor_only` 语义收敛：仅控制启用的 monitor worker 集合，不在 click/app_switch 事件源中做分叉过滤。
- 元数据口径：`focused_context = {app_name, window_name, browser_url}` 表示 focused UI 上下文，必须由同一轮 snapshot 一次性产出；`device_name` 表示实际采样 monitor；二者须在同一 capture 周期内组装，但不承诺同瞬时原子快照。
- 验收增量（S2b）：新增多屏一致性场景（主屏+副屏）并验证 `trigger`、`device_name`、截图归属的可解释性与稳定性。

### 1.1 HTTP 契约 delta（本阶段，scope=对外 HTTP）

- SSOT：[../../http_contract_ledger.md](../../http_contract_ledger.md)
- 实施边界（已冻结）：S2b 功能正确性的证明链路仅认 `/v1/*` + v3 runtime/store；legacy `/api/*` 与旧 worker 仅做兼容回归检查，不承担新的 S2b 语义或验收责任（见 [../../open_questions.md](../../open_questions.md) OQ-042）。

| 类型 | 接口 | 变化/说明 | SSOT |
|---|---|---|---|
| CHANGE | POST `/v1/ingest` | CapturePayload 增加 `accessibility_text` 和 `content_hash` 字段 | [spec.md](../../spec.md) §4.7；[data-model.md](../../data-model.md) §3.0.6 |
| RETAIN | `/v1/*` | 对外 HTTP 无新增/废弃/替代端点 | [spec.md](../../spec.md) §4.9 |

## 2. 环境与输入

- 运行环境：macOS（P1-S2b 仅验证 macOS）
- 权限要求：Accessibility 权限（System Preferences → Privacy & Security → Accessibility）
- 配置与数据集：
  - AX 树遍历测试场景（Chrome, Safari, VS Code, Terminal, Finder 等）
- Browser URL 测试场景（required: Chrome, Safari, Edge；conditional: Arc）
  - 高频“内容不变”压测脚本（app switch/click，5 分钟）
  - 采集参数基线：AX 树遍历超时 `500ms`、深度限制 `30`、节点限制 `5000`
  - 依赖版本：记录 AX 模块版本

### 2.1 指标口径与样本说明（必填）

- 口径基线版本（默认 [../../gate_baseline.md](../../gate_baseline.md)）：v1.4
- 指标样本数：
  - AX 采集样本：>= 200 次（多应用场景）
  - `inter_write_gap_sec` Hard Gate：每设备样本 `>= 100`
  - Browser URL 样本：>= 50 次（多浏览器场景）
- 统计时间窗：
  - 主窗：连续 5 分钟多窗口场景
  - 压测窗：内容不变压测持续 5 分钟
- 百分位算法：Nearest-rank（剔除前 10 个预热样本）
- 窗口元信息（必填）：`window_id`、`host_pid`、`edge_pid`、`restart_events`、`broken_window`
- 有效窗规则：窗口内若发生 Host 或 Edge 重启，标记 `broken_window=true`；该窗口结果仅用于观测，不可作为 Hard Gate 证据

## 3. 验收步骤

1. 启动 Host/Edge，开启采集 debug 日志。
2. 验证 Accessibility 权限状态：
   - 若未授权，确认 TCC 引导流程正确显示
   - 若已授权，确认 AX 树遍历可正常执行
3. 按应用清单执行 AX 采集测试：
   - Chrome（浏览器 URL 提取）
   - Safari（AXDocument 属性）
   - Arc（AppleScript fallback）
   - VS Code（代码文本提取）
   - Terminal（终端文本）
   - Finder（文件名）
4. 抽样核验 AX 文本字段完整性：
    - 非空 AX 样本：`accessibility_text` 非空
    - `browser_url` 正确（浏览器场景）
    - `content_hash` 计算正确
   - 边界样本：AX 空文本帧在 ingest 可见（不得丢帧），不计入 `content_hash` coverage 分母，并在后续 S3 验收中可被 OCR fallback 消化
5. 执行高频“内容不变”压测（app switch/click，5 分钟），记录窗口元信息，并校验 `inter_write_gap_sec`（Soft KPI + Hard Gate：按 `device_name` 分桶，每设备 max <= 45s，样本 >= 100；`broken_window=true` 仅观测不判定）。
6. 测量 AX 树遍历延迟：
   - 记录每次遍历耗时
   - 统计 P95 是否 < 500ms
7. 执行 SQL 校验：
    - `content_hash` 覆盖率（`ax_hash_eligible`）：
      ```sql
      SELECT
        COUNT(*) AS ax_hash_eligible,
        SUM(
          CASE
            WHEN content_hash IS NOT NULL
             AND LENGTH(content_hash) = 71
             AND SUBSTR(content_hash, 1, 7) = 'sha256:'
            THEN 1 ELSE 0
          END
        ) AS with_hash,
        ROUND(
          SUM(
            CASE
              WHEN content_hash IS NOT NULL
               AND LENGTH(content_hash) = 71
               AND SUBSTR(content_hash, 1, 7) = 'sha256:'
              THEN 1 ELSE 0
            END
          ) * 100.0 / COUNT(*),
          2
        ) AS coverage_pct
      FROM frames
      WHERE TRIM(COALESCE(accessibility_text, '')) <> ''
        AND timestamp >= datetime('now', '-5 minutes');
      ```
      判定：`coverage_pct >= 90%`
      说明：空 AX 文本帧必须上传，但不进入本指标分母。
    - `inter_write_gap_sec`（Soft KPI + Hard Gate）：
      - Hard Gate: 按 `device_name` 分桶判定，每设备 `max <= 45s`（每设备样本 >= 100）
      - Soft KPI（non-blocking）：记录 P50/P90/P99 分布
      - 说明：P99 不设硬性阈值（dedup 保底写入场景下 P99 天然接近 30s，无区分度）
      ```sql
      WITH samples AS (
        SELECT device_name, timestamp
        FROM frames
        WHERE capture_trigger IN ('app_switch', 'click')
          AND timestamp >= datetime('now', '-5 minutes')
      ),
      ordered AS (
        SELECT device_name,
               timestamp,
               LAG(timestamp) OVER (PARTITION BY device_name ORDER BY timestamp) AS prev_ts
        FROM samples
      )
      SELECT
        device_name,
        COUNT(*) AS writes,
        COALESCE(MAX((julianday(timestamp) - julianday(prev_ts)) * 86400.0), 0) AS max_gap_sec
      FROM ordered
      WHERE prev_ts IS NOT NULL
      GROUP BY device_name;
      ```
      判定：每个 `device_name` 都满足 `writes >= 100` 且 `max_gap_sec <= 45`；同时输出 P50/P90/P99 分布作为 Soft KPI 记录。
8. 抽样校验 Browser URL 提取：
   - Chrome: AXDocument 属性
   - Safari: AXDocument 属性
   - Arc: AppleScript fallback（仅当 Arc support 未 defer 时作为 conditional evidence）
   - 判定：URL 以 `http://` 或 `https://` 开头
9. **Arc Stale URL 检测测试**（conditional evidence，对齐 screenpipe）：
   - 在 Arc 中打开两个 tab（Tab A: google.com, Tab B: github.com）
   - 快速切换 tab（< 200ms 间隔）并触发 capture
   - 验证：browser_url 为 None 的帧比例合理（stale 被正确拒绝）
   - 验证：无 URL 与截图内容不匹配的情况
10. **Title 匹配算法测试**：
    - Arc 显示 `(45) WhatsApp`，验证能正确匹配 `WhatsApp`
    - Discord 显示 `💬1 - screenpipe | Discord`，验证能正确匹配
11. **Browser URL 统计验证**：
    - 运行 5 分钟多浏览器场景
    - 验证 `browser_url_*` 计数器正确累加
    - required browser success denominator 仅统计 Chrome/Safari/Edge
    - Arc 若已实现则单独记录为 conditional evidence；若 deferred，不计入 required success denominator，也不视为回归
12. 权限恢复验证（强制）：
    - 运行中撤销 Accessibility 权限，验证系统进入权限降级状态；
    - 重新授权后验证状态进入 `recovering` 并最终回到 `granted`；
    - 验证恢复后 AX 路径重新生效，且不会把 `permission denied` 误判为 `AX empty`。

### 3.1 Verification commands and minimum pass criteria（Entry Contract）

> 注：P1-S2b 测试依赖 macOS AX 权限，需本机手动跑。测试策略为「Gate 校验脚本 + 最小集成测试」，不强制 CI 自动化。

> 开发约束（已冻结）：P1-S2b 核心能力采用 TDD；`tests/test_p1_s2b_content_hash.py`、`tests/test_p1_s2b_ax_timeout.py` 等测试文件属于阶段正式交付物，但应在开发过程中随功能自然落地。`scripts/acceptance/p1_s2b_local.sh` 作为 Exit Gate 编排层，在阶段收口时补齐并执行（见 [../../open_questions.md](../../open_questions.md) OQ-041）。

- P1-S2a 防回归基线（必须先过）：
  - `pytest tests/test_v3_migrations_bootstrap.py tests/test_p1_s1_*.py tests/test_p1_s1_grid_data_contract.py -q`
  - 最小通过线：`0 failed`
- P1-S2b Gate 校验脚本：
  - `pytest tests/test_p1_s2b_content_hash.py -q` — content_hash 覆盖率 SQL 校验
  - `pytest tests/test_p1_s2b_ax_timeout.py -q` — AX 遍历延迟 P95 校验
  - 最小通过线：`0 failed`
- P1-S2b 最小集成测试（补充）：
  - `pytest tests/test_p1_s2b_integration.py -q`（如创建）
  - 最小通过线：`0 failed`
- 组合回归（阶段收口）：
  - `pytest tests/test_v3_migrations_bootstrap.py tests/test_p1_s1_*.py tests/test_p1_s1_grid_data_contract.py -q`
  - 最小通过线：`0 failed` 且不降低已有通过率。

### 3.2 轨道 A（本机 Gate 验收）实施细则（强制）

- 目标：把 AX 权限与 S2b 指标验证流程标准化，确保复测可比、证据可审计。
- 执行入口（建议固定）：`scripts/acceptance/p1_s2b_local.sh`
- 定位：该脚本属于 S2b Exit Gate 编排层，负责串联已落地测试、指标导出与证据收集；不替代开发期的 TDD 契约测试。
- 执行前置：
  - 运行环境为 macOS（Accessibility 权限已配置）；
  - Host/Edge 进程已按 runbook 启动；
  - Browser 场景样本（Chrome/Safari/Arc）按步骤准备完成。
- 脚本最小职责：
  - 固化本次验收上下文（时间窗、权限状态、配置快照、git rev）；
  - 按文档顺序运行 Gate 校验脚本（content_hash 覆盖率、AX timeout、inter_write_gap 分桶）；
  - 导出 `/v1/ingest/queue/status` 与 `/v1/health` 快照；
  - 输出统一结果摘要（`Pass/Fail` + 失败项 + 证据路径）。
- 证据产物（必填）：
  - `p1-s2b-local-gate.log`（脚本总日志）
  - `p1-s2b-metrics.json`（content_hash/inter_write_gap/browser_url 指标汇总）
  - `p1-s2b-health-snapshots.json`（健康态与权限态快照）
  - `p1-s2b-ui-proof.md`（timeline 新帧、URL 提取、恢复流程截图索引）
- 通过线：
  - Gate 脚本 `0 failed`；
  - 样本口径满足本节 `2.1`；
  - 证据文件齐全且可追溯。

## 4. 结果与指标

### 4.1 数值指标

- AX 树遍历延迟 P95（目标 < 500ms）：
- `content_hash` 覆盖率（目标 >= 90%，分母=`ax_hash_eligible`）：
- `inter_write_gap_sec`（Soft KPI + Hard Gate）：
  - Hard Gate: 按 `device_name` 分桶，每设备 max <= 45s（样本 >= 100）
  - Soft KPI: 记录 P50/P90/P99 分布
- **Browser URL 统计**：
  - `browser_url_success`：
  - `browser_url_rejected_stale`：
  - `browser_url_failed_all_tiers`：
  - `browser_url_skipped`：
  - 成功率（目标 >= 95%）：
- 备注（是否满足最小样本数要求）：是 | 否（不足项：...）

### 4.2 功能完成度指标（强制）

- 功能清单完成率（目标 100%）：
- API/Schema 契约完成率（目标 100%）：
- 关键功能用例通过率（目标 >= 95%）：

### 4.3 完善度指标（强制）

- capability/context 异常与降级场景通过率（目标 >= 95%）：覆盖 `browser_url_rejected_stale`、empty-AX no-drop handoff、Arc deferred 记录与上下文一致性。
- 权限处理场景通过率（目标 100%）：覆盖 `startup_denied / revoked_mid_run / restored_after_denied`，并在 S2b Exit 前关闭。
- 可观测性检查项完成率（目标 100%，日志/指标/错误码）：
- 文档与验收记录完整率（目标 100%）：

### 4.4 UI 验收（按阶段启用）

- 路由可达与基础状态可见性检查（健康态/错误态）：通过。
- UI 关键交互通过率：本阶段检查 timeline 新 capture 可见率 >= 95%。
- UI 证据附件（截图/录屏/日志路径）：

## 5. 结论

- Gate 结论：`Pass` | `Fail`
- 样本数符合性判定：`Pass` | `Fail`（若 `Fail`，本阶段不得给出 Gate `Pass` 结论）
- 依据：
- 阻塞项（若 Fail 必填）：

## 6. 风险与后续动作

- 风险：AX 树遍历在 Electron 应用中可能超时（10k+ 节点）。
- 风险：Browser URL 提取在某些浏览器可能失败（需要 fallback）。
- 风险：Electron 应用首次遍历可能返回空文本（异步树构建）。
- 后续动作：若 AX 遍历超时，调整深度限制或节点限制；若 Browser URL 失败，增加更多 fallback 策略。
- 后续动作：
  - 若 500ms 超时仍不够，提高到 1000ms 并记录 CPU 影响。
  - 若 Day 3 仍不稳定，defer Arc Browser 支持，专注 Chrome/Safari/Edge；该动作属于时间盒 scope-cut fallback，不构成 S2b Gate 分支。
- **Electron 空文本处理**（对齐 screenpipe）：不重试，下次事件触发自然获得完整文本；空文本帧由 OCR fallback 兜底。

## 7. Rollback Rule

### 7.1 触发条件（任一命中即触发回滚流程）

- 任一改动导致 P1-S1/P1-S2a 防回归基线出现失败。
- 任一改动破坏已冻结契约（ingest/queue/health/UI health gate/timestamp 口径）。

### 7.2 回滚流程（必须按顺序执行）

1. 停止继续叠加新改动，冻结当前提交窗口。
2. 定位引入回归的最小变更集。
3. 撤销或修复该最小变更集，直到防回归基线恢复全绿。
4. 重新执行组合回归并保存证据文件到 `docs/v3/acceptance/phase1/evidence/`。

## 8. Release Gate

### 8.1 Code Gate（必须满足）

- 防回归基线通过：`tests/test_v3_migrations_bootstrap.py + tests/test_p1_s1_*.py + tests/test_p1_s2a_*.py + tests/test_p1_s1_grid_data_contract.py`。
- P1-S2b 目标测试通过：`tests/test_p1_s2b_*.py`。

### 8.2 Acceptance Gate（必须满足）

- 本文件强制章节完整填写。
- 证据路径可追溯。

### 8.3 最终判定规则

- `Pass`：`Code Gate=Pass` 且 `Acceptance Gate=Pass`。
- `Fail`：任一 Gate 不满足即 `Fail`。
