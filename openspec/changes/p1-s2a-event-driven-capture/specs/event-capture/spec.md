## ADDED Requirements

### Requirement: Event-driven capture trigger emission
系统 MUST 在 macOS 上使用 CGEventTap 监听 click 与 app_switch 事件，并在触发采集时为每次采集写入合法的 `capture_trigger`。P1 仅允许以下触发值进入主链路：`idle`、`app_switch`、`manual`、`click`。主触发机制 MUST 是事件驱动，不得由固定频率轮询替代。

#### Scenario: Emit capture on supported event
- **WHEN** 监听器接收到 click 或 app_switch 事件且当前未命中全局去抖门控
- **THEN** 系统 MUST 生成一次采集请求并写入与事件一致的 `capture_trigger`
