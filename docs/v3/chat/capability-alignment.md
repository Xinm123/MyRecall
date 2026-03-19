# Chat Capability Alignment

- 版本：v1.0
- 日期：2026-03-19
- 状态：Draft
- 角色：记录 MyRecall Chat 前置能力与 screenpipe 实际实现的对齐关系、当前偏离点与阶段性策略

---

## 1. 文档角色

本文件不定义 Gate 本身；Gate 分类以 `docs/v3/chat/prerequisites.md` 为准。

本文件回答的是：

- screenpipe 实际实现有哪些能力面
- MyRecall 在 Chat 前需要先对齐哪些能力
- 当前阶段哪些点是刻意偏离、哪些点只是尚未完成

---

## 2. `/v1/search` 能力对齐

### 2.1 对齐目标

MyRecall 的 `/v1/search` 采用 screenpipe 风格的：

- `SearchResponse`
- `data: ContentItem[]`
- `pagination`
- `content_type=all` 返回 mixed typed results

### 2.2 MyRecall 建议模型

```ts
type SearchResponse = {
  data: ContentItem[]
  pagination: {
    limit: number
    offset: number
    total: number
  }
}

type ContentItem =
  | { type: "ocr"; content: OCRContent }
  | { type: "accessibility"; content: AccessibilityContent }
  | { type: "input"; content: InputContent }
```

当前阶段将其视为“拟定 contract”，而不是仅供参考的概念模型。

### 2.3 当前阶段拟定 contract

```ts
type OCRContent = {
  frame_id: number
  text: string
  timestamp: string
  app_name: string
  window_name: string
  browser_url?: string | null
  frame_name?: string | null
  focused?: boolean | null
  device_name: string
  file_path?: string | null
  offset_index?: number | null
  frame?: string | null // only when include_frames=true
}

type AccessibilityContent = {
  id: number
  text: string
  timestamp: string
  app_name: string
  window_name: string
  initial_traversal_at?: string | null
  file_path?: string | null
  offset_index?: number | null
  frame_name?: string | null
  browser_url?: string | null
}

type InputContent = {
  id: number
  timestamp: string
  event_type: string
  app_name?: string | null
  window_title?: string | null
  browser_url?: string | null
  text_content?: string | null
  x?: number | null
  y?: number | null
  key_code?: number | null
  modifiers?: number | null
  element_role?: string | null
  element_name?: string | null
  element_value?: string | null
  frame_id?: number | null
}
```

### 2.4 关键约束

- `content_type=ocr`：屏幕 OCR 文本检索
- `content_type=input`：用户输入/交互事件检索
- `content_type=accessibility`：独立 accessibility search plane，不是 capture-backed 兼容层
- `content_type=all`：正式 agent-facing 能力，允许混合返回，再由 `type` 分流

进一步约束：

- `AccessibilityContent` 只代表独立 accessibility search plane 的结果
- `AccessibilityContent` 不带 `frame_id`
- `AccessibilityContent.file_path / offset_index` 是媒体定位字段，不代表天然 frame-grounded
- `InputContent.frame_id` 为可选增强字段，按松耦合理解
- `InputContent.element_value` 为可选增强字段，只在相关事件中出现
- `OCRContent.file_path / offset_index` 为可选媒体定位字段
- `OCRContent.frame` 仅在 `include_frames=true` 时出现
- `window_name`（OCR/Accessibility）与 `window_title`（Input）的并存是当前按 screenpipe 各类型结果 shape 保留的命名差异，不视为疏漏；上层可统一理解为窗口上下文标签

### 2.5 与 screenpipe 的显式差异

- screenpipe API 使用历史命名 `UI`；MyRecall 明确改为 `Accessibility`
- MyRecall 计划在 `InputContent` 中显式暴露 `element_value`
- 该增强不改变 screenpipe 的 tagged-union 结构思路

---

## 3. Accessibility 数据面

screenpipe 实际上同时有两条 accessibility 链路：

1. `paired_capture`
   - 截图时同步 tree walk
   - 结果进入 `frames.accessibility_text` / `frames.accessibility_tree_json`
   - 并 dual-write 到 `elements(source='accessibility')`

2. `independent tree walker`
   - 独立线程周期性 walk focused window
   - 结果进入独立 `accessibility` / `accessibility_fts` 数据面

MyRecall 在 Chat Entry Gate 中需要同时具备这两条链路，原因不同：

- `paired_capture`：支撑 frame-grounded context
- `independent tree walker`：支撑 `content_type=accessibility` 作为真实搜索面存在

### 3.1 当前对齐结论

- `paired_capture`：Entry Gate / P0-core
- `independent tree walker`：Entry Gate / P0-core
- `tree_walker` 参数（3s、立即唤醒、300ms settle、500ms cooldown）：当前按 screenpipe 现状对齐

### 3.2 三系统关系

screenpipe 实际可拆成三条并行但相关的数据链路：

| 系统 | 职责 | 主要产物 |
|------|------|----------|
| Event-Driven Capture | 检测用户行为并触发截图 | `frames`、OCR、paired accessibility、`elements` |
| UI Events Recording | 记录交互事件详情 | `ui_events` |
| Tree Walker | 独立采集 focused window 的 accessibility 文本流 | `accessibility` |

同一个用户动作可能同时在多个系统留下记录。例如点击按钮时：

```text
click
  -> capture trigger -> screenshot -> paired_capture -> frames + elements
  -> ui event -> ui_events
  -> app/window change 时可能额外唤醒 tree walker -> accessibility
```

### 3.3 写入边界

| 数据来源 | 写入 `frames` | 写入 `elements` | 写入 `accessibility` |
|----------|---------------|-----------------|----------------------|
| `paired_capture` | ✅ | ✅ | ❌ |
| `independent tree walker` | ❌ | ❌ | ✅ |

这也是为什么：

- `frame-grounded context` 主要依赖 `paired_capture`
- `content_type=accessibility` 的独立搜索面主要依赖 `independent tree walker`

---

## 4. Elements 能力面

### 4.1 当前对齐目标

MyRecall 的 `elements` 能力面在 Entry Gate 中要求做到：

- `elements` 表存在，核心字段尽量贴近 screenpipe
- `source='accessibility'` 稳定写入
- `GET /v1/elements`
- `GET /v1/frames/{id}/elements`
- `GET /v1/frames/{id}/context`

当前阶段应明确：`elements` 主要服务 Chat grounding，而不是在此阶段就追求 screenpipe 那种更完整的统一内容层定位。

### 4.2 当前不进入 Entry Gate 的 exact parity

- `source='ocr'` 的完整 elements 写入
- 更高程度的内部实现同构
- 更细的 exact parity 边界行为

### 4.3 写入策略

当前对齐目标保留 screenpipe 的 accessibility-first 逻辑：

| 场景 | OCR 写入 `elements` | Accessibility 写入 `elements` |
|------|---------------------|-------------------------------|
| 普通应用（有 AX tree） | ❌ | ✅ |
| 普通应用（无 AX tree） | ✅ fallback | ❌ |
| Terminal 等偏 OCR 场景 | ✅ | ❌ |

这也是为什么 `elements(source='ocr')` 的完整 exact parity 被放到 `Parity Gate`：

- 当前 Entry Gate 先要求 accessibility 路径完整成立
- OCR elements 的系统化落地后续再追
- 某些场景下存在 OCR fallback 写入，不等于 `elements(source='ocr')` 的完整 parity 已完成

### 4.4 `value` 字段策略

- `elements` 侧不新增独立 `value` 字段
- accessibility/elements 继续使用 screenpipe 风格的统一 `text`
- 输入值相关信息保留在 `ui_events.element_value`

### 4.5 `/v1/elements` 与 frame 级接口的边界

- `GET /v1/elements`
  - 定位：cross-frame search
  - 当前阶段拟定最小 query contract：
    - `q`
    - `frame_id`
    - `source`
    - `role`
    - `start_time`
    - `end_time`
    - `app_name`
    - `limit`
    - `offset`
  - `source` 参数存在，但 Entry 阶段主要保证 `source=accessibility` 生效

- `GET /v1/frames/{id}/elements`
  - 定位：frame-scoped inspection
  - 返回某一帧的完整 flat tree
  - 客户端/调用方通过 `parent_id`、`depth`、`sort_order` 重建层级

- `GET /v1/frames/{id}/context`
  - 定位：frame-scoped grounding
  - 提供可直接消费的上下文，而不是完整 elements tree

---

## 5. `/v1/frames/{id}/context`

MyRecall 对齐 screenpipe 的目标是：

- 返回：
  - `frame_id`
  - `text`
  - `nodes`
  - `urls`
  - `text_source`
- 行为：
  - accessibility-first
  - OCR fallback
  - URL extraction

### 5.1 `nodes` 的当前阶段拟定 contract

按 screenpipe 轻量节点模型对齐：

```ts
type ContextNode = {
  role: string
  text: string
  depth: number
  bounds?: {
    left: number
    top: number
    width: number
    height: number
  } | null
}
```

说明：

- `nodes` 不是 `elements` row 的镜像
- 当前阶段不引入 `id`、`parent_id`、`sort_order`、`source`

### 5.2 `urls` 的提取语义

- `urls` 是两种来源的并集：
  - link/hyperlink 节点文本提取
  - 全文 regex 扫描
- 结果需要去重

### 5.3 与 `/v1/frames/{id}/elements` 的关系

- `/v1/frames/{id}/elements` 提供完整结构明细
- `/v1/frames/{id}/context` 提供可直接消费的上下文
- 两者互补，而非重复

该接口属于 Chat grounding 的关键接口，而不是附属增强。

---

## 6. `/v1/activity-summary`

### 6.1 角色定位

- broad question 的首个概览入口
- 角色是“先概览，再下钻”

### 6.2 schema 对齐原则

MyRecall 在 vision-only 阶段保留 screenpipe 同形 schema：

- `apps`
- `recent_texts`
- `audio_summary`
- `total_frames`
- `time_range`

### 6.3 当前阶段拟定 contract

```ts
type ActivitySummaryResponse = {
  apps: Array<{
    name: string
    frame_count: number
    minutes: number
  }>
  recent_texts: Array<{
    text: string
    app_name: string
    timestamp: string
  }>
  audio_summary: {
    segment_count: number
    speakers: Array<{
      name: string
      segment_count: number
    }>
  }
  total_frames: number
  time_range: {
    start: string
    end: string
  }
}
```

### 6.4 vision-only 特殊处理

- `recent_texts` 必须来源于 `elements(source='accessibility')`
- `audio_summary` 保留字段，但固定返回空壳：
  - `segment_count: 0`
  - `speakers: []`
- `apps[].minutes` 保留 screenpipe 的近似语义，不应被解释为精确 active time

---

## 7. UI Events / Input

### 7.1 Entry Gate 对齐范围

- `click`
- `text`
- `app_switch`
- `clipboard`
- `element context`

同时保留旧文档中已经确认、且与当前结论一致的事件边界：

- 不把 `scroll`、`move`、单独 `key` 事件作为本轮 Chat 前置要求
- `text` 事件使用聚合输入语义，而不是逐键记录

### 7.2 Split Pattern（click 主事件与 context 事件分离）

当前建议继续保留 screenpipe 风格的 split pattern：

1. 主 click 事件立即发送，不等待 AX API
2. element context 在后台异步获取，作为独立增强事件发送

该模式的价值是：

- 主事件记录可靠，不受 AX API 成功率影响
- element context 作为增强能力存在，失败时不拖垮主路径
- Chat 可通过时间戳和坐标关联主事件与 context 事件

当前阶段应明确：

- context 增强事件允许失败或丢失
- 没有 context 事件，不代表主 click 事件无效

### 7.3 `text` 事件的能力边界

- `text` 事件表示聚合输入片段，而不是逐键日志
- 聚合基于短静默窗口完成，但高层文档不冻结具体毫秒参数

### 7.4 当前阶段隐私边界

- `clipboard content`：当前默认保留，不做自动 PII 脱敏
- `secure/password field`：不落库
- `ui_events.element_value`：允许保留，但同样遵守 `secure/password field` 例外

### 7.5 与 screenpipe 的关系

- `capture_keystrokes` 的保守默认值属于 screenpipe 的现状
- MyRecall 当前阶段更强调 Chat/agent 能力验证
- 但在 password/secure field 上明确保留保守例外

---

## 8. Frames 字段变化

旧文档中与当前结论仍一致、且值得保留的 `frames` 扩展点包括：

| 字段 | 当前结论 | 作用 |
|------|----------|------|
| `accessibility_tree_json` | 需要 | 支撑 `/v1/frames/{id}/context` 的 nodes 和 URL extraction |
| `accessibility_text` | 需要 | 支撑 frame-grounded accessibility text |
| `text_source` | 需要 | 明确该 frame 最终采用 `accessibility` 还是 `ocr` |
| `content_hash` | 字段可保留 | 本轮不要求在 Chat Entry Gate 中实现完整去重逻辑 |


---

## 9. Browser URL

`browser_url` 不应视为附属元数据，而应视为浏览器场景的核心 grounding 字段。

至少需要进入：

- capture metadata
- `/v1/search` 相关结果

此外：

- `/v1/frames/{id}/context` 不要求单独返回 `browser_url` 字段，但应通过 `urls` 与上下文文本体现页面线索
- `activity-summary` 不要求单独增加 `browser_url` schema 字段，但可用于增强 app/window 解释语义

具体获取优先级和运行时路径由 `docs/v3/chat/architecture.md` 继续收口。

---

## 10. Enhancements

| 项目 | 当前结论 | 说明 |
|------|----------|------|
| `UI` -> `Accessibility` 命名 | 保留 | 结构对齐 screenpipe，但使用更清晰命名 |
| `InputContent.element_value` | 增强 | screenpipe DB 有该字段，当前 API 未显式暴露；MyRecall 计划显式暴露 |
| `InputContent.frame_id` | 增强 | 作为可选松耦合字段保留 |

---

## 11. Gaps / Deferred Parity

| 项目 | 当前状态 | 说明 |
|------|----------|------|
| `audio_summary` 真实音频语义 | 缺口 | 当前阶段仅保留空壳 schema |
| `elements(source='ocr')` 完整落地 | Deferred parity | 已明确放入 `Parity Gate` |
| `/v1/raw_sql` 安全边界收口 | Deferred parity | 当前接口本身保留为高级能力；deferred parity 指向安全边界收口，而不是其存在性 |
| `elements` 的完整统一内容层定位 | Deferred parity | 当前阶段主要服务 Chat grounding |
| `/v1/elements` 与相关接口的更高 exact parity | Deferred parity | 当前先保证最小可消费 contract |

---

## 12. 当前阶段采集/隐私策略备注

### 12.1 A1-A4 当前状态

| 决策 | 当前状态 | 当前结论 |
|------|----------|----------|
| `A1` | 部分重开 | clipboard 默认不脱敏，但只限 clipboard/ui_events 路径 |
| `A2` | 明确重开 | `secure/password field` 不落库 |
| `A3` | 部分重开 | 需要 exclusion 机制，但不作为当前 Entry Gate blocker |
| `A4` | 明确重开 | `ui_events.element_value` 保留；password/secure value 不落库；`elements` 不加独立 value |

### 12.2 当前阶段与 screenpipe 的关系

- 当前策略是“能力优先 + security/password 明确例外”
- 这不等于隐私边界与 screenpipe 完全同构
- 所有“完全对齐”表述都必须拆成：
  - 能力面对齐
  - Enhancements
  - Gaps / Deferred Parity
