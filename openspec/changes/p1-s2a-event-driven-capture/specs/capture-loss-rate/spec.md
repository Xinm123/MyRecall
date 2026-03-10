## ADDED Requirements

### Requirement: Capture loss-rate gate for overload validation
系统 MUST 在 P1-S2a 验收中提供 Capture 丢包率判定能力，公式为 `loss_rate = (应到达 capture 数 - 成功 commit capture 数) / 应到达 capture 数`。在 `300 events/min`、持续 5 分钟压测窗口下，`loss_rate` MUST 小于 `0.3%`。

### Requirement: Loss-rate evidence export
验收脚本 MUST 导出 `loss_rate`、压测窗口标识、样本分母/分子及计算依据，确保 Gate 结论可追溯。

#### Scenario: Validate loss-rate threshold under fixed stress injection
- **WHEN** 执行 5 分钟 `300 events/min` 事件注入压测
- **THEN** 系统 MUST 产出可复算证据并满足 `loss_rate < 0.3%`
