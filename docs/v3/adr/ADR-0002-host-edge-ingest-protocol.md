# ADR-0002 Host-Edge 传输协议（幂等 + 断点续传）

- 版本：v1.0
- 状态：Accepted
- 日期：2026-02-26

## Context
- 现有 MyRecall v2 使用单次 `/api/upload`（历史路径），适合同机或轻载，不足以应对频繁断连与重放。
- v3 对外 API 命名空间冻结为 `/v1/*`；`/api/*` 不属于 v3 对外契约。

## Decision
- 采用 019A 分阶段协议：
  - P1：单次幂等上传 `POST /v1/ingest` + 队列状态端点 `GET /v1/ingest/queue/status`。
    - 重复 `capture_id` 返回 `200 OK + {"status":"already_exists"}`，不重复入库。
  - P2+：在不破坏 P1 契约前提下，新增 `session/chunk/commit/checkpoint` 四端点用于 LAN 弱网分片与断点续传。
- 以 `capture_id` 作为幂等键，Edge 侧去重写入。
- 安全策略采用 A->B 渐进：
  - P1：token 鉴权 + TLS 可选（LAN 场景先保证可用性）。
  - P2+：mTLS 强制（收敛到零信任内网模型）。

## screenpipe 参考与对齐
- screenpipe 做法：本地 capture 后直接入库；另有 sync provider 处理同步批次。
- 对齐结论：概念可对齐（可恢复同步），实现不对齐（我们是 Host->Edge 主链路）。

## Consequences
- 优点：P1 协议最小化，先保证可用与幂等；P2+ 再引入分片复杂度，降低首阶段交付风险。
- 代价：协议存在两阶段能力差异，P2+ 需要兼容 P1 单帧通道与分片通道并存。

## Risks
- P1 队列容量不足时可能出现持续 `QUEUE_FULL`，需要 Host 重试与告警策略。
- P2+ checkpoint 错误会导致重复处理或漏处理。

## Validation
- P1：重复包重放（同一 `capture_id`）不重复入库；断连恢复后自动续传，`queue/status` 计数与实际处理状态一致。
- P2+：网络 chaos（丢包、乱序、重复发送、进程重启）下，分片回放后一致性校验通过。
