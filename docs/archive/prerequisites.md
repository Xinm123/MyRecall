# Chat Prerequisites

- 版本：v1.0
- 日期：2026-03-19
- 状态：Draft
- 角色：定义进入 Chat 开发前的 Gate，不承载完整实现细节或最终架构结论

---

## 1. 文档角色与证据优先级

本文件只回答三个问题：

1. 什么能力属于 `Entry Gate`
2. `Entry Gate` 内部哪些是 `P0-core`，哪些是 `P0-support`
3. 什么能力应留到 `Parity Gate`

当前总判断：

- MyRecall 目前尚未达到 `Entry Gate`
- 进入 Chat 主链路开发前，仍需先补齐核心数据面与工具面
- 当前最核心缺口集中在：`ui_events`、`independent tree walker`、`elements(source='accessibility')`、unified `/v1/search`、`/v1/frames/{id}/context`、`/v1/activity-summary`

本文件明确不承载以下内容：

- 最终 Chat 运行架构
- 大段实现细节、伪代码、DDL 草案
- 长期工期估算
- “与 screenpipe 完全对齐”这类不带边界的结论

证据优先级按以下顺序执行：

1. MyRecall 当前代码与实际运行约束
2. screenpipe 实际实现（`_ref/screenpipe/`）
3. `docs/v3/chat/*`
4. 其他 `docs/v3/*`（仅参考，尤其 `P1-S4` 之后内容不作为强事实源）
5. screenpipe 文档说明（仅作弱参考）

---

## 2. Gate 定义

### 2.1 Entry Gate

`Entry Gate` 表示：在开始 MyRecall Chat 主链路开发前，必须先补齐的、接近 screenpipe vision-only 当前数据面与工具面的能力。

### 2.2 Parity Gate

`Parity Gate` 表示：不阻塞进入 Chat 开发，但为了进一步贴近 screenpipe 实现、提高稳态安全性或补足 exact parity，需要在后续继续完成的能力。

### 2.3 P0-core vs P0-support

- `P0-core`：不具备这些能力时，Chat grounding 主工作流无法成立
- `P0-support`：同样属于 Entry Gate，但可以在 `P0-core` 闭环后并行补齐

### 2.4 Entry Gate 完成判定

只有当以下条件同时成立时，才应视为达到 `Entry Gate`：

1. Chat 所需数据面已形成，而不再只是局部 seam 或 reserved 字段
2. Agent-facing 工具入口已形成稳定 contract，而不是临时拼接的调试接口
3. 关键能力能以 screenpipe-like 方式被消费，而不需要大量 prompt 特判

---

## 3. 当前状态与差距矩阵

### 3.1 Data Plane

| 能力 | screenpipe | MyRecall 当前 | 当前分类 |
|------|-----------|---------------|----------|
| OCR 文本搜索 | ✅ | ✅ 已有 | 已满足 |
| `ui_events.click` | ✅ | ❌ 未实现 | Entry Gate / P0-core |
| `ui_events.element context` | ✅ | ❌ 未实现 | Entry Gate / P0-core |
| `ui_events.text` | ✅ | ❌ 未实现 | Entry Gate / P0-core |
| `ui_events.app_switch` | ✅ | ⚠️ 仅有 capture trigger，缺独立事件面 | Entry Gate / P0-core |
| `ui_events.clipboard` | ✅ | ❌ 未实现 | Entry Gate / P0-core |
| `independent tree walker` | ✅ | ❌ 未实现 | Entry Gate / P0-core |
| `accessibility` 表写入 | ✅ | ❌ 未实现 | Entry Gate / P0-core |
| `elements(source='accessibility')` | ✅ | ❌ 未实现 | Entry Gate / P0-core |
| `browser_url` | ✅ | ⚠️ 预留字段但未形成数据面 | Entry Gate / P0-core |
| `elements(source='ocr')` 完整落地 | ✅ | ❌ 未实现 | Parity Gate |
| exclusion / privacy hardening 机制 | ✅ | ❌ 未实现 | Parity Gate |

### 3.2 Tooling / API

| 能力 | screenpipe | MyRecall 当前 | 当前分类 |
|------|-----------|---------------|----------|
| `content_type=input` | ✅ | ❌ 未实现 | Entry Gate / P0-core |
| `content_type=accessibility` | ✅ | ❌ 未实现 | Entry Gate / P0-core |
| unified `GET /v1/search` | ✅ | ❌ 未实现 | Entry Gate / P0-core |
| `GET /v1/elements` | ✅ | ❌ 未实现 | Entry Gate / P0-core |
| `GET /v1/frames/{id}/context` | ✅ | ❌ 未实现 | Entry Gate / P0-core |
| `GET /v1/activity-summary` | ✅ | ❌ 未实现 | Entry Gate / P0-core |
| `GET /v1/frames/{id}/elements` | ✅ | ❌ 未实现 | Entry Gate / P0-support |
| `POST /v1/raw_sql` | ✅ | ❌ 未实现 | Entry Gate / P0-support |

### 3.3 Status / Phrasing

| 项目 | screenpipe | MyRecall 当前 | 当前分类 |
|------|-----------|---------------|----------|
| “完全对齐 screenpipe（vision-only）”表述 | ❌ 不适用 | ❌ 当前不能成立 | 已失效口径 |

说明：

- `Browser URL` 原旧文档曾放在 P2，但在当前讨论中已提升为 `Entry Gate / P0-core`
- `content_type=all` 视为 unified `/v1/search` 的正式能力，不单列为独立项目
- `paired_capture` 的 OCR/accessibility 选择逻辑、`tree walker` 的具体采样参数等实现细节，以 `capability-alignment.md` 为准

---

## 4. Entry Gate / P0-core

### 4.1 数据面

| 能力 | 要求 | 说明 |
|------|------|------|
| `paired_capture` | 必须 | 截图时同步获取 accessibility tree；整体语义为 accessibility-first，必要时 OCR fallback |
| `independent tree walker` | 必须 | 使 `content_type=accessibility` 成为真实存在的数据面，而非 capture-backed 兼容实现 |
| `ui_events` | 必须 | 至少包含 click、text、app_switch、clipboard，以及 element context |
| `browser_url` | 必须 | 浏览器场景下属于核心 grounding 元数据，至少必须进入 capture metadata 与 search-facing 结果 |
| `elements(source='accessibility')` | 必须 | accessibility 结构化元素能力是 `activity-summary`、`/elements`、`/frames/{id}/context` 的基础 |

### 4.2 工具面

| 能力 | 要求 | 说明 |
|------|------|------|
| unified `GET /v1/search` | 必须 | 必须支持 `content_type=ocr/input/accessibility/all` |
| typed search result model | 必须 | 对齐 screenpipe 的 `SearchResponse + ContentItem` 思路；MyRecall 使用 `accessibility` 命名而非 `UI` |
| `GET /v1/elements` | 必须 | 作为结构化 UI 搜索入口 |
| `GET /v1/frames/{id}/context` | 必须 | 返回 `frame_id/text/nodes/urls/text_source`，并遵循 accessibility-first + OCR fallback |
| `GET /v1/activity-summary` | 必须 | 作为 broad question 的首个概览入口；schema 尽量与 screenpipe 同形 |

### 4.3 `/v1/activity-summary` 的 Entry Gate 约束

- 属于 `Entry Gate / P0-core`
- `recent_texts` 必须来自 `elements(source='accessibility')`
- `audio_summary` 在 vision-only 阶段保留空壳字段，而不是删除字段
- 角色定位是“先概览，再下钻”，不是最终回答接口

### 4.4 `/v1/search` 的 Entry Gate 约束

- `content_type=all` 是正式 agent-facing 能力，不是调试开关
- 返回值必须是可判别类型的联合结果，而不是扁平化结构
- `InputContent` 允许显式暴露 `element_value`
- `elements` 侧不新增独立 `value` 字段

说明：

- `GET /v1/elements` 在本文件中只定义为 Entry Gate 必备接口
- 其最小 query contract 以 `docs/v3/chat/capability-alignment.md` 为准

---

## 5. Entry Gate / P0-support

| 能力 | 当前结论 | 说明 |
|------|----------|------|
| `GET /v1/frames/{id}/elements` | 必须 | 属于 Entry Gate，但优先级低于 `/v1/frames/{id}/context` |
| `POST /v1/raw_sql` | 必须 | 当前阶段为 screenpipe-like tool parity 保留；分类为 `P0-support` |

### 5.1 `/v1/raw_sql` 当前阶段结论

- 当前阶段允许按 screenpipe-like 能力对齐，以支撑 agent/tool parity
- 这是当前阶段的必要高级接口，不代表其当前安全边界已经成为长期稳态 contract
- 该结论不是最终稳态安全结论
- 在 Chat 主链路跑通、且 Host/Edge 分机前，必须复审是否收紧为受限只读 SQL API

---

## 6. Parity Gate

当前已明确不阻塞 `Entry Gate`，但后续仍应继续追的能力包括：

| 能力 | 当前状态 | 说明 |
|------|----------|------|
| `elements(source='ocr')` 完整落地 | 后置 | Entry Gate 先要求 accessibility 侧完整可用；此处指完整、稳定、可依赖的 OCR elements 能力面，而不是零散 fallback 写入的存在性 |
| `/v1/raw_sql` 安全边界收口 | 后置 | 未来 Host/Edge 分机前复审只读限制、白名单和鉴权策略 |
| search / context / elements 的更高 exact parity | 后置 | 包括更多内部行为与边界一致性，而非只满足 agent-facing contract |
| exclusion / privacy hardening 机制 | 后置 | 当前不作为 Entry Gate blocker，但不再视为“永远不实现” |

说明：

- `Parity Gate` 不表示“不重要”，而表示“不阻塞进入 Chat 主链路开发”
- 某些 `Parity Gate` 项可能在分机前或上线前重新升高优先级，例如 `/v1/raw_sql` 安全边界收口

---

## 7. 当前阶段策略说明

### 7.1 vision-only 对齐口径

- 本阶段以 screenpipe 的 vision-only 能力面为对齐目标
- audio 不进入本轮前置能力范围
- 但与 audio 相关的 schema 位置，如 `/v1/activity-summary.audio_summary`，保留兼容形状

### 7.2 当前阶段隐私/采集策略

- 总体策略：能力优先
- 明确例外：`secure/password field` 不落库
- `clipboard content` 当前默认保留，不做自动 PII 脱敏
- `ui_events.element_value` 允许保留，但同样遵守 `secure/password field` 例外
- `elements` 不新增独立 `value` 字段，继续使用统一 `text`

### 7.3 当前阶段与 screenpipe 的显式偏离

- MyRecall 在 `/search` 结果中使用 `accessibility` 命名，而不是 screenpipe 的历史 `UI` 命名
- MyRecall 当前接受 `InputContent.element_value` 对外暴露，作为 screenpipe 风格结构上的小幅增强
- `/v1/raw_sql` 当前只做能力对齐，最终安全边界待后续收口

### 7.4 当前不应使用的口径

在本阶段，不应再使用以下笼统表述：

- “已经与 screenpipe 完全对齐（vision-only）”
- “Chat 前所有问题都已经关闭”
- “隐私策略已经最终确定”

---

## 8. 已重开的旧决策

| 旧决策 | 新状态 | 处理方式 |
|--------|--------|----------|
| `Q5` | Reopened | 原单层“Chat 前必须完成”框架失效，改为 `Entry Gate / Parity Gate / P0-core / P0-support` 分类 |
| `D1` | Reopened and refined | `/v1/activity-summary` 明确归入 `Entry Gate / P0-core`，详细语义转入 `capability-alignment.md` |
| `D2` | Reopened | `/v1/raw_sql` 明确归入 `Entry Gate / P0-support`，并增加 Host/Edge 分机前复审要求 |
| `D3` | Retired as phrasing | “完全对齐（vision-only）”不再作为可用结论，改为能力面对齐 + 显式偏离列表 |
| `C1-C4` | Reopened and migrated | 属于架构议题，不再留在 prerequisites 主文档，迁入 `architecture.md` |
| `A1` | Partially reopened | 保留 clipboard 默认不脱敏，但仅限 clipboard/ui_events 路径，不再外推为总原则 |
| `A2` | Reopened | 旧的“密码字段不跳过”结论废止，改为 `secure/password field` 不落库 |
| `A3` | Partially reopened | exclusion 机制需要，但不作为当前 Entry Gate blocker |
| `A4` | Reopened | `ui_events.element_value` 保留，但 password/secure value 不落库；`elements` 不新增独立 value |

### 8.1 已失效的旧表述

以下旧表述不再作为当前 SSOT：

- “Chat 前必须完成”作为单层门槛的说法
- “与 screenpipe 完全对齐（vision-only）”的笼统表述
- “不主动过滤或脱敏任何内容”作为总隐私原则的表述

### 8.2 当前 SSOT 边界

- Gate 分类以本文件为准
- 能力面对齐细节以 `capability-alignment.md` 为准
- Chat 架构与部署边界以 `architecture.md` 为准

---

## 9. 文档索引

- 能力面对齐细节：`docs/v3/chat/capability-alignment.md`
- Chat 运行架构与待定部署决策：`docs/v3/chat/architecture.md`
- screenpipe Chat 事实基线：`docs/v3/baselines/chat/chat_baseline_screenpipe.md`
