## ADDED Requirements

### Requirement: Capture trigger tagging and validation readiness
系统 MUST 在 Host 侧为每个新上报 capture 赋值 `capture_trigger`，并保证该字段在进入 ingest 前可被校验为 P1 允许枚举：`idle`、`app_switch`、`manual`、`click`。系统 MUST 不允许空值或非法值进入 S2a 新上报路径。

#### Scenario: Reject missing capture_trigger before ingest acceptance
- **WHEN** 新上报 capture 缺失 `capture_trigger` 或值不在 P1 枚举集合内
- **THEN** 系统 MUST 阻止该 payload 被视为有效采集输入
