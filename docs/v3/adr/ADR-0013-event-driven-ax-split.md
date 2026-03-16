---
status: **⚠️ SUPERSEDED for v3 mainline**
date: 2026-03-09
superseded_date: 2026-03-13
superseded_by: OQ-043 (OCR-only 收口)
current_semantics: P1-S2b = Capture Completion (not AX collection)
---

# ADR-0013 P1-S2 拆分：事件驱动 (S2a) + ~~AX 采集 (S2b)~~

> ================================================================================
> 🚨 **CRITICAL NOTICE: THIS ADR IS SUPERSEDED FOR V3 MAINLINE** 🚨
> ================================================================================n>
> **Superseded Date**: 2026-03-13 by [OQ-043](../open_questions.md#oQ-043)
>
> **Current Status**: 
> - ✅ **P1-S2a**: 事件驱动 capture — 已完成并保持不变
> - ✅ **P1-S2b**: 已转型为 **"Capture Completion"**（trigger routing + monitor-aware coordination + device binding + spool handoff）
> - ❌ **P1-S2b 原定 AX 采集**: **已废弃**，AX 主链路 defer 到 v4
>
> **执行依据**（按优先级排序）：
> 1. [open_questions.md OQ-043](../open_questions.md) — OCR-only 决策（SSOT）
> 2. [roadmap.md P1-S2b](../roadmap.md) — 当前阶段定义
> 3. [acceptance/phase1/p1-s2b.md](../acceptance/phase1/p1-s2b.md) — 验收标准
>
> **冲突解决规则**：
> - 若本 ADR 下文与上述现行文档冲突，**一律以后者为准**
> - **禁止**依据本 ADR 的历史 S2b=AX 范围编写实现、测试或 Gate 结论
>
> **保留目的**：本文档仅作为架构决策审计历史保留，展示决策演进过程
>
> ================================================================================

- 日期：2026-03-09
- 关联：ADR-0008（Phase 1 串行子阶段）、OQ-027（Capture 运行机制）、OQ-028（Host spool 持久化）、**OQ-043（OCR-only 收口）**

---

## Context

P1-S2 原定义为"事件驱动 capture + AX 文本采集 + 去重 + 背压保护"的大阶段，经架构评审发现以下问题：

1. **复杂度耦合**：事件驱动（需跨平台事件监听）与 AX 采集（需 AX 树遍历 + 权限处理）是两个独立技术栈，合并开发风险高。

2. **Gate 依赖矛盾**：
   - `trigger_coverage = 100%` 仅依赖事件监听框架
   - dedup 效果验收依赖 `content_hash` + 30s 保底写入口径（需 AX 采集）
   - 若不拆分，事件驱动失败会阻塞 AX 采集验证，反之亦然

3. **平台优先级**：用户选择"macOS-only 先行"（OQ-001=B），但 AX 采集在 P1 阶段同样仅 macOS 可用。

4. **实现语言选择**：Python 生态已具备生产级 AX 库（macOS: macapptree/pyobjc, Windows: uiautomation, Linux: pyatspi2），与现有 codebase 一致，开发周期与当前阶段目标匹配。

---

## Decision

### 1. P1-S2 拆分为 S2a + S2b

| 子阶段 | 原始范围 | 当前范围 (OQ-043 后) | 状态 |
|--------|----------|---------------------|------|
| **P1-S2a** | 事件驱动 capture（事件监听 + 触发标记 + 去抖 + 背压） | 事件驱动 capture（事件监听 + 触发标记 + 去抖 + 背压） | ✅ 已完成 |
| **P1-S2b** | ~~AX 文本采集（AX 树遍历 + content_hash + 权限处理）~~ | **Capture Completion**（trigger routing + monitor coordination + device binding + spool handoff） | ✅ 已转型 |
| **P1-S3** | ~~处理（AX-first + OCR fallback + text_source 标记）~~ | **OCR-only Processing**（OCR + text_source='ocr'） | ✅ 已转型 |

> **⚠️ 历史记录**：上表"原始范围"列仅为审计历史；"当前范围"为 v3 主线实际执行口径。

### 2. 实现语言：Python

- **理由**：与现有 openrecall codebase 一致；pyobjc/pywinauto/pyatspi2 均为生产级库；开发周期 3-4 周。
- **性能评估**：Python AX 树遍历 ~100-500ms/次，对于事件驱动 + 快照式捕获**完全足够**（注：AX 采集已 defer 到 v4，此评估仅保留为历史记录）。
- **频率策略**：P1/P2 维持 1Hz（有意偏离 screenpipe 5Hz），Python 实现安全余量充足。
- **延迟观测策略**：`capture_latency_p95` 仅作观测记录（P50/P90/P95/P99），不作为 Gate Pass/Fail 或阶段触发条件。

### 3. 平台策略：macOS-first

- P1-S2a/S2b 仅实现 macOS（验证架构可行性）
- Windows/Linux 推迟至 P2 阶段
- P1 阶段 Win/Linux 用户使用 `idle` + `manual` 触发（满足 `trigger_coverage = 100%` 要求）

---

## P1-S2a 交付范围（事件驱动）— 仍然有效

### 功能

- macOS CGEventTap 事件监听（click, app_switch；typing_pause/scroll_stop 推迟至 P2）
- 触发标记（`capture_trigger` 字段赋值）
- 去抖门控（`min_capture_interval_ms=1000`，1 Hz；有意偏离 screenpipe Performance 200ms (5 Hz)；Python 实现安全起点）
- idle fallback（超时触发语义，`idle_capture_interval_ms=30000`，不依赖用户活跃判定）
- 背压保护（有界通道 + lag 折叠）

### Gate

- `trigger_coverage = 100%`（idle/app_switch/manual/click 四类均命中）
- `capture_latency_p95` 强制观测记录（P50/P90/P95/P99，non-blocking）
- `queue_saturation_ratio <= 10%`
- `collapse_trigger_count` 仅作为观测指标记录
- `overflow_drop_count = 0`

### 文件结构

```
openrecall/client/events/
├── __init__.py
├── base.py          # 事件监听基类 + CaptureTrigger enum
├── macos.py         # CGEventTap 实现
├── windows.py       # SetWindowsHookEx 实现（P2）
└── linux.py         # evdev 实现（P2）
```

---

## ~~P1-S2b 交付范围（AX 采集）~~ — 已废弃

> 🚨 **本节已废弃（Superseded）**
>
> 自 OQ-043 (2026-03-13) 起，v3 主线正式收口为 **OCR-only**。
> 
> - **原定 S2b = AX 文本采集** — 废弃，AX 主链路 defer 到 v4
> - **现行 S2b = Capture Completion** — 见 [p1-s2b.md](../acceptance/phase1/p1-s2b.md)
> 
> 以下内容为**历史记录**，仅用于架构审计，不得作为实现依据。

<details>
<summary>点击展开：已废弃的 AX 采集设计（仅供历史参考）</summary>

### ~~功能（已废弃）~~

- ~~macOS AXUIElement 树遍历~~
- ~~文本提取（AXValue, AXTitle, AXDescription）~~
- ~~Browser URL 提取（AXDocument + AppleScript fallback）~~
- ~~`content_hash` 计算（SHA256, 对齐 screenpipe）~~
- ~~权限检测与 TCC 引导~~

### ~~Gate（已废弃）~~

- ~~`inter_write_gap_sec` Hard Gate：按 `device_name` 分桶，每设备 `max <= 45s`~~
- ~~`content_hash` 覆盖率 >= 90%~~
- ~~AX 树遍历超时 < 500ms（P95）~~

### ~~AX 降级策略（历史记录）~~

| 场景 | 处理方式 |
|------|----------|
| 截图 | 始终写入磁盘（永不阻塞） |
| AX 超时 | 500ms 保护，继续处理已获取部分 |
| AX 有文本 | 使用 AX 文本，跳过 OCR |
| AX 空/失败 | OCR fallback |
| text_source | accessibility / ocr（由 P1-S3 处理阶段判定） |

### ~~Browser URL 提取策略（历史记录）~~

| 浏览器 | Fallback 层级 | 预期成功率 |
|--------|--------------|-----------|
| Chrome/Safari/Edge | Tier 1: AXDocument | ~95%+ |
| Arc | Tier 2: AppleScript + Title Cross-Check | ~90%+ |
| 其他/兜底 | Tier 3: AXTextField shallow walk | ~80%+ |

</details>

---

## P1-S2b 当前交付范围（Capture Completion）— 现行口径

> 📋 **执行依据**：[p1-s2b.md](../acceptance/phase1/p1-s2b.md)

### 功能（现行）

- trigger routing 语义冻结：`specific-monitor` (click), `active-monitor` (app_switch), `per-monitor-idle` (deadline), `coordinator-defined` (manual)
- `MonitorRegistry` + `MonitorWorker` 拓扑管理
- `device_name` 绑定语义：由实际完成截图的 monitor worker 负责最终绑定
- `focused_context = {app_name, window_name}` 冻结（P1 不采集 `browser_url`）
- monitor topology rebuild：增减、primary 切换、不可用恢复
- spool handoff correctness：metadata / image / `capture_trigger` / `device_name` 一致性

### Gate（现行）

- `trigger_target_routing_correctness = 100%`
- `device_binding_correctness = 100%`
- `single_monitor_duplicate_capture_rate = 0%`
- `topology_rebuild_correctness = 100%`

### 文件结构（现行）

```
openrecall/client/
├── events/              # S2a：事件监听
├── monitors/            # S2b：monitor 管理（新增）
│   ├── registry.py      # MonitorRegistry
│   ├── worker.py        # MonitorWorker
│   └── coordinator.py   # CaptureCoordinator
├── spool.py             # S2b：spool handoff
└── hash_utils.py        # S2b+：simhash（可选）
```

---

## screenpipe 参考与对齐

| 维度 | screenpipe | MyRecall v3 (Python) |
|------|-------------------|----------------------|
| 事件监听 | CGEventTap (cidre) | CGEventTap (pyobjc) ✅ 已实现 |
| ~~AX 树遍历~~ | ~~AXUIElement (cidre)~~ | ~~AXUIElement (pyobjc/macapptree)~~ ❌ **defer 到 v4** |
| ~~content_hash~~ | ~~DefaultHasher (u64)~~ | ~~SHA256~~ ❌ **不再作为主线 dedup** |
| simhash | DefaultHasher (内部缓存) | DHash (P1-S2b+ 可选) |
| 去抖参数 | min=200ms, idle=30s | min=1000ms (P1 安全起点), idle=30s |

---

## Consequences

### 实际结果（OQ-043 后）

- **S2a/S2b 拆分成功**：降低单阶段风险，独立验收通过
- **OCR-only 主线收敛**：简化 P1 实现，加速交付
- **AX defer 到 v4**：保留 schema seam，为后续恢复留边界
- **S2b 语义转型**：从 AX 采集转向 Capture Completion，仍满足架构解耦目标

### 历史记录（原始决策时的预期）

<details>
<summary>点击展开：原始决策时的 Consequences（仅供历史参考）</summary>

- 优点：
  - 单阶段风险降低：S2a/S2b 独立验收，失败不互相阻塞
  - 开发周期缩短：Python 实现 3-4 周
  - 与 P1-S3 串行依赖明确：S2b 的 AX 数据是 S3 AX-first 处理的前置条件
- 代价：
  - P1 阶段 Win/Linux 用户仅能用 idle/manual 触发
- `inter_write_gap_sec` 在 S2a 阶段不判定（依赖 S2b 的 `content_hash` + Host-side dedup 语义）

</details>

---

## Risks

### 已缓解的风险

| 风险 | 缓解措施 | 状态 |
|------|----------|------|
| AX 复杂度阻塞 S2b | 将 AX defer 到 v4，S2b 专注 Capture Completion | ✅ 已解决 |
| OCR-only 语义不清 | OQ-043 明确收口，spec/roadmap/acceptance 统一更新 | ✅ 已解决 |

### 仍需关注的风险

- Python 性能瓶颈：若 `capture_latency_p95` 长期偏高，需在既有 Python 架构内优化触发、上传与持久化链路
- macOS 权限问题：TCC 弹窗可能导致用户流失（已用 Python + pyobjc 实现 screenpipe permissions.rs 的瞬态失败检测逻辑）
- 频率差异：P1/P2 维持 1Hz（有意偏离 screenpipe 5Hz），若未来需要更高频率需重新评估

---

## Validation

### 现行验收标准（v3 主线）

- P1-S2a Gate：`trigger_coverage = 100%`；`capture_latency_p95` 强制观测记录（non-blocking）— **✅ Pass**
- P1-S2a 背压放行：`queue_saturation_ratio <= 10%`、`overflow_drop_count = 0`；`collapse_trigger_count` 仅作为观测指标记录 — **✅ Pass**
- P1-S2b Gate：`trigger_target_routing_correctness = 100%`、`device_binding_correctness = 100%`、`single_monitor_duplicate_capture_rate = 0%`、`topology_rebuild_correctness = 100%` — **✅ Pass**

### ~~历史验收标准（已废弃）~~

<details>
<summary>点击展开：已废弃的 AX 相关验收标准（仅供历史参考）</summary>

- ~~P1-S2b Gate：content_hash 覆盖率 >= 90%（基于 raw `accessibility_text` 非空分母）；`inter_write_gap_sec`（Soft KPI + Hard Gate）~~ — ❌ 废弃
- ~~P1-S3 Gate：AX-first 成功率 >= 70%，text_source 正确标记率 = 100%~~ — ❌ 废弃

</details>

---

## 文档历史

| 日期 | 变更 | 作者 |
|------|------|------|
| 2026-03-09 | 初稿：P1-S2 拆分为 S2a + S2b（原定 S2b=AX 采集） | pyw |
| 2026-03-13 | **SUPERSEDED**：OQ-043 收口为 OCR-only，S2b 转型为 Capture Completion | pyw |
| 2026-03-15 | 修订：增加醒目 Superseded 标记，重构文档结构，明确历史记录与现行口径 | pyw |

---

**⚠️ 再次提醒**：本文档为**审计历史记录**，v3 主线执行口径以 [OQ-043](../open_questions.md)、[roadmap.md](../roadmap.md)、[p1-s2b.md](../acceptance/phase1/p1-s2b.md) 为准。
