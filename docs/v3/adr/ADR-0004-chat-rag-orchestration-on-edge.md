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
- 仅采用软约束时，若缺少持续观测与回归，引用质量可能下滑。

## Validation
- 分阶段观测目标（non-blocking）：
  - P1-S5：回答引用覆盖率目标 >= 85%
  - P1-S7 / Phase2 / Phase3：回答引用覆盖率目标 >= 92%
  - Stretch 目标：>= 95%
- 所有目标与统计口径以 `MyRecall/docs/v3/gate_baseline.md` 为准。
