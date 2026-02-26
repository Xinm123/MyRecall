# ADR-0002 Host-Edge 传输协议（幂等 + 断点续传）

- 状态：Accepted
- 日期：2026-02-26

## Context
- 现有 MyRecall v2 使用单次 `/api/upload`，适合同机或轻载，不足以应对频繁断连与重放。

## Decision
- 定义分阶段上传协议：session/chunk/commit/checkpoint。
- 以 `capture_id` 作为幂等键，Edge 侧去重写入。
- 安全策略采用 A->B 渐进：
  - P1：token 鉴权 + TLS 可选（LAN 场景先保证可用性）。
  - P2+：mTLS 强制（收敛到零信任内网模型）。

## screenpipe 参考与对齐
- screenpipe 做法：本地 capture 后直接入库；另有 sync provider 处理同步批次。
- 对齐结论：概念可对齐（可恢复同步），实现不对齐（我们是 Host->Edge 主链路）。

## Consequences
- 优点：断连可恢复、重复包可重放、可跨设备迁移。
- 代价：协议实现复杂度上升。

## Risks
- checkpoint 错误会导致重复处理或漏处理。

## Validation
- 网络 chaos：丢包、乱序、重复发送、进程重启，全量回放后一致性校验通过。
