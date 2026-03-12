## ADDED Requirements

### Requirement: Three-tier browser_url extraction
系统 MUST 为 `browser_url` 实现三层提取链：Tier 1 使用 AXDocument；Tier 2 在 Arc 上使用 AppleScript 并附带标题校验；Tier 3 使用浅层 AXTextField walk。系统 MUST 只在同轮 `focused_context` 一致性成立时写入 `browser_url`，且仅允许 `http://` 或 `https://` URL 进入最终 payload。

Acceptance impact: 该要求冻结 Browser URL required evidence 的提取顺序与成功判定；Chrome、Safari、Edge 的 required-browser 样本必须按该链路收集，Arc 仅作为 conditional evidence。

#### Scenario: Use first valid browser_url tier
- **WHEN** 某一层成功返回合法 `http(s)` URL，且该值通过同轮一致性校验
- **THEN** 系统 MUST 将该值写入最终 `browser_url`，并停止继续向后层级求值

#### Scenario: Fall through to later tiers when earlier tiers fail
- **WHEN** Tier 1 无结果或结果非法
- **THEN** 系统 MUST 继续尝试后续层级，直到得到通过校验的结果或确认全部失败

### Requirement: Stale rejection before write
系统 MUST 将“成功提取到 URL”与“允许写入 `browser_url`”视为两个独立判断。只要标题交叉校验失败、同轮一致性无法确认、URL 格式非法、或命中已定义的 stale 条件，系统 MUST 把最终 `browser_url` 写为 `None`，并不得把该结果作为成功 URL 样本。S2b 允许的 stale rejection 原因 MUST 限定为：title cross-check fail、focused-context bundle inconsistency、非 `http(s)` URL、或 tier-specific freshness check fail；实现 MUST NOT 使用未定义的模糊启发式扩大 reject 范围。

Acceptance impact: 该要求冻结 `browser_url_rejected_stale` 的计数语义；Browser URL success rate 与 stale rejection evidence 必须分别统计，不得把 reject 样本算入成功。

#### Scenario: Reject stale Arc URL on title mismatch
- **WHEN** Arc AppleScript 返回的活动标签页标题与当前 screenshot / focused window 标题不一致
- **THEN** 系统 MUST 将该 URL 视为 stale 并把最终 `browser_url` 写为 `None`

#### Scenario: Reject uncertain URL even if syntactically valid
- **WHEN** 系统拿到一个合法 `http(s)` URL，但无法确认它与当前 screenshot 属于同一轮前台上下文
- **THEN** 系统 MUST 不写入该 URL，并将该样本记为 reject 或 failed evidence，而不是成功样本

### Requirement: Browser URL evidence classification
系统 MUST 将 Browser URL 结果分类为至少以下四类：`browser_url_success`、`browser_url_rejected_stale`、`browser_url_failed_all_tiers`、`browser_url_skipped`。这些分类 MUST 可用于 S2b Gate evidence，且不得与 OCR、search 或后续 processing 阶段语义混用。required browser success denominator MUST 仅由 `browser_url_success + browser_url_rejected_stale + browser_url_failed_all_tiers` 构成，并且仅统计 Chrome、Safari、Edge；Arc 样本若已实现则单独记录为 conditional evidence，若 defer 则统一计为 `browser_url_skipped` observation。

Acceptance impact: 该要求冻结 Browser URL 指标导出口径；S2b evidence 需要按上述分类汇总 required browser 样本与 conditional Arc 样本。

#### Scenario: Export failed-all-tiers when no tier yields a usable URL
- **WHEN** 三层 URL 提取均无法得到通过校验的结果
- **THEN** 系统 MUST 将该样本分类为 `browser_url_failed_all_tiers` 或 `browser_url_skipped`，并保持最终 `browser_url=None`
