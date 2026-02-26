# ADR-0004 Chat RAG 编排放在 Edge

- 状态：Accepted
- 日期：2026-02-26

## Context
- Chat 是核心能力。
- v2 缺少一等 Chat 编排层。

## Decision
- Edge 新增 Chat Orchestrator，执行：
  - query planning
  - search tool 调用
  - citation 绑定（capture/frame/timestamp）
  - model routing（local/cloud）
- 对外 Chat 接口采用 OpenAI-compatible + tool schema，便于模型切换与客户端复用。
- 模型策略与 screenpipe 对齐：本地与云端 provider 都支持，按配置切换（可选 fallback），切换权在 Edge。

## screenpipe 参考与对齐
- screenpipe 做法：前端 Pi agent 通过 `/search` 等工具做检索增强，并可调用 `/ai/chat/completions`。
- 对齐结论：能力可对齐；实现路径改为"后端 Edge 编排优先"。

## Consequences
- 优点：治理统一、可观测性强、Host 更轻。
- 代价：Edge 服务复杂度显著上升。

## Risks
- 无强制 citation 会导致幻觉与不可追溯。

## Validation
- 验收门槛：回答引用覆盖率 >= 95%，且引用可回放到原始截图。
