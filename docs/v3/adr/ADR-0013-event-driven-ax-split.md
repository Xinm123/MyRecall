# ADR-0013 P1-S2 拆分：事件驱动 (S2a) + AX 采集 (S2b)

- 状态：Accepted
- 日期：2026-03-09
- 关联：ADR-0008（Phase 1 串行子阶段）、OQ-027（Capture 运行机制）、OQ-028（Host spool 持久化）

## Context

P1-S2 原定义为"事件驱动 capture + AX 文本采集 + 去重 + 背压保护"的大阶段，经架构评审发现以下问题：

1. **复杂度耦合**：事件驱动（需跨平台事件监听）与 AX 采集（需 AX 树遍历 + 权限处理）是两个独立技术栈，合并开发风险高。

2. **Gate 依赖矛盾**：
   - `trigger_coverage = 100%` 仅依赖事件监听框架
   - `dedup_skip_rate >= 95%` 依赖 `content_hash`（需 AX 采集）
   - 若不拆分，事件驱动失败会阻塞 AX 采集验证，反之亦然

3. **平台优先级**：用户选择"macOS-only 先行"（OQ-001=B），但 AX 采集在 P1 阶段同样仅 macOS 可用。

4. **实现语言选择**：Python 生态已具备生产级 AX 库（macOS: macapptree/pyobjc, Windows: uiautomation, Linux: pyatspi2），与现有 codebase 一致，开发周期与当前阶段目标匹配。

## Decision

### 1. P1-S2 拆分为 S2a + S2b

| 子阶段 | 范围 | 依赖 | 时序 |
|--------|------|------|------|
| **P1-S2a** | 事件驱动 capture（事件监听 + 触发标记 + 去抖 + 背压） | 无 | Week 1-2 |
| **P1-S2b** | AX 文本采集（AX 树遍历 + content_hash + 权限处理） | P1-S2a 的触发机制 | Week 3-4 |
| **P1-S3** | 处理（AX-first + OCR fallback + text_source 标记） | P1-S2b 的 accessibility_text | Week 5-6 |

### 2. 实现语言：Python

- **理由**：与现有 openrecall codebase 一致；pyobjc/pywinauto/pyatspi2 均为生产级库；开发周期 3-4 周。
- **性能评估**：Python AX 树遍历 ~100-500ms/次，对于事件驱动 + 快照式捕获**完全足够**。
- **频率策略**：P1/P2 维持 1Hz（有意偏离 screenpipe 5Hz），Python 实现安全余量充足。
- **延迟观测策略**：`capture_latency_p95` 仅作观测记录（P50/P90/P95/P99），不作为 Gate Pass/Fail 或阶段触发条件。

### 3. 平台策略：macOS-first

- P1-S2a/S2b 仅实现 macOS（验证架构可行性）
- Windows/Linux 推迟至 P2 阶段
- P1 阶段 Win/Linux 用户使用 `idle` + `manual` 触发（满足 `trigger_coverage = 100%` 要求）

### 4. Gate 调整

| Gate | 原类型 | 调整后 | 理由 |
|------|--------|--------|------|
| `dedup_skip_rate >= 95%` | Hard Gate | **Soft KPI** | 依赖 content_hash（S2b 交付）；S2a 阶段无法计算 |

## P1-S2a 交付范围（事件驱动）

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
- `collapse_trigger_count >= 1`
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

## P1-S2b 交付范围（AX 采集）

### 功能

- macOS AXUIElement 树遍历
- 文本提取（AXValue, AXTitle, AXDescription）
- Browser URL 提取（AXDocument + AppleScript fallback）
- `content_hash` 计算（SHA256, 对齐 screenpipe）
- 权限检测与 TCC 引导

### Gate

- `dedup_skip_rate >= 95%`（观测指标）
- `content_hash` 覆盖率 >= 90%（AX 成功帧）
- AX 树遍历超时 < 500ms（P95）

### AX 降级策略（与 screenpipe 对齐）

| 场景 | 处理方式 |
|------|----------|
| 截图 | 始终写入磁盘（永不阻塞） |
| AX 超时 | 500ms 保护，继续处理已获取部分 |
| AX 有文本 | 使用 AX 文本，跳过 OCR |
| AX 空/失败 | OCR fallback |
| text_source | accessibility / ocr |

### Browser URL 提取策略（与 screenpipe 完全对齐）

| 浏览器 | Fallback 层级 | 预期成功率 |
|--------|--------------|-----------|
| Chrome/Safari/Edge | Tier 1: AXDocument | ~95%+ |
| Arc | Tier 2: AppleScript + Title Cross-Check | ~90%+ |
| 其他/兜底 | Tier 3: AXTextField shallow walk | ~80%+ |

**关键设计**：
- content_hash **仅基于 text_content**，不包含 browser_url
- 提取失败返回 None，不阻断 capture
- 成功率 >= 95%（观测指标，非 Gate）

**Arc Stale URL 检测**（对齐 screenpipe `url_timing_test.rs`）：
- 问题：AppleScript 有 ~107ms 延迟，期间用户切换 tab 会导致 URL 与截图不匹配
- 方案：同时获取 title + URL，与 window_title 进行 cross-check
- 不匹配时返回 None（拒绝 stale URL）
- 设计原则：**Better None than wrong URL**

**Title 匹配算法**（`titles_match()`）：
- 去除 badge 计数：`(45) WhatsApp` → `WhatsApp`、`[2] Gmail` → `Gmail`
- 大小写不敏感匹配
- 包含匹配（处理标题截断）

### 文件结构

```
openrecall/client/accessibility/
├── __init__.py
├── base.py          # AX 树遍历基类
├── macos.py         # AXUIElement 实现
├── windows.py       # UI Automation 实现（P2）
└── linux.py         # AT-SPI2 实现（P2）
```

## screenpipe 参考与对齐

| 维度 | screenpipe | MyRecall v3 (Python) |
|------|-------------------|----------------------|
| 事件监听 | CGEventTap (cidre) | CGEventTap (pyobjc) |
| AX 树遍历 | AXUIElement (cidre) | AXUIElement (pyobjc/macapptree) |
| content_hash | DefaultHasher (u64, 精确匹配) | SHA256 (hex, 精确匹配，行为对齐) |
| 去抖参数 | min=200ms, idle=30s | 有意偏离：min=1000ms (P1 安全起点), idle=30s |

> **注**：screenpipe 的 `simhash` 字段用于 tree walker 内部缓存，不参与 frame-level 去重。Frame 去重使用 `content_hash` 精确匹配。MyRecall 的 SHA256 与 screenpipe 的 DefaultHasher 行为一致（都是精确匹配），且具有跨 session 一致性优势。

## Consequences

- 优点：
  - 单阶段风险降低：S2a/S2b 独立验收，失败不互相阻塞
  - 开发周期缩短：Python 实现 3-4 周
  - 与 P1-S3 串行依赖明确：S2b 的 AX 数据是 S3 AX-first 处理的前置条件
- 代价：
  - P1 阶段 Win/Linux 用户仅能用 idle/manual 触发
  - `dedup_skip_rate` 在 S2a 阶段无法达标（改为 Soft KPI）

## Risks

- Python 性能瓶颈：若 `capture_latency_p95` 长期偏高，需在既有 Python 架构内优化触发、上传与持久化链路
- macOS 权限问题：TCC 弹窗可能导致用户流失（需优化引导 UX）
  - **缓解措施**：用 Python + pyobjc 实现 screenpipe permissions.rs 的瞬态失败检测逻辑（连续 2 次失败才触发、5 分钟冷却期），减少误报
- AX 树遍历超时：Electron 应用可能有 10k+ 节点（需深度限制 + 超时保护）
  - **缓解措施**：提高 walk_timeout 至 500ms（有意偏离 screenpipe 默认 250ms）
- Electron 异步树构建：首次遍历可能返回空文本（Chromium 异步构建 DOM 树）
  - **缓解措施**：对齐 screenpipe，不重试；下次事件触发自然获得完整文本；空文本帧由 OCR fallback 兜底
- 频率差异：P1/P2 维持 1Hz（有意偏离 screenpipe 5Hz），若未来需要更高频率需重新评估

## Validation

- P1-S2a Gate：trigger_coverage = 100%；`capture_latency_p95` 强制观测记录（non-blocking）
- P1-S2b Gate：content_hash 覆盖率 >= 90%；dedup_skip_rate（Soft KPI，仅记录数值）
- P1-S3 Gate：AX-first 成功率 >= 70%，text_source 正确标记率 = 100%
