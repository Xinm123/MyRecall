# ADR-0001 Edge-Centric 职责边界

- 状态：Accepted
- 日期：2026-02-26

## Context
- 目标要求 Edge 必须参与，且 Host 仅负责采集/上传/缓存。
- screenpipe 当前主干拓扑更偏单机本地闭环。

## Decision
- MyRecall-v3 采用强制 Edge-Centric：
  - Host：capture + spool + upload + resume。
  - Edge：processing + index + search + chat。

## screenpipe 参考与对齐
- screenpipe 做法：视觉处理与检索主要在本地节点完成。
- 对齐结论：行为可对齐，拓扑不对齐（刻意不对齐）。

## Consequences
- 优点：可演进到专用 Edge（Debian 盒子），Host 负载更可控。
- 代价：引入网络链路与分布式一致性问题。

## Risks
- Edge 不可达导致 Host backlog 膨胀。

## Validation
- 故障注入：Edge 断开 30min 后恢复，数据不丢且顺序可恢复。
