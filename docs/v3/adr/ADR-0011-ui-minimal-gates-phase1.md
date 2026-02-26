# ADR-0011 Phase 1 UI Gate 采用最小可用集

- 状态：Accepted
- 日期：2026-02-26

## Context
- 现有 v3 文档已明确 UI 在 P1~P3 部署于 Edge（ADR-0006），但各子阶段对 UI 的功能验收约束不足。
- 若仅验证后端链路而缺少 UI Gate，容易出现“能力已实现但用户不可用”的假通过。
- 用户确认采用 A 方案：先增强 UI 可用性验收，不做 UI 重构。

## Decision
- 采用 `012A`：P1 引入“最小可用 UI Gate”，覆盖可用性、可解释性、可恢复性，不引入 UI 架构或视觉重构。
- 子阶段 UI Gate 基线：
  - P1-S1：`/`、`/search`、`/timeline` 路由可达，健康态/错误态可见。
  - P1-S2：timeline 可见 capture 上传中/入队状态。
  - P1-S3：frame 详情可见 AX/OCR fallback 来源。
  - P1-S4：search 过滤项与 API 参数契约对齐，结果可回溯。
  - P1-S5：chat 引用可点击并可回溯。
  - P1-S6：路由状态与降级提示可见。
  - P1-S7：`timeline -> search -> chat -> citation -> frame` 关键路径脚本化回归。
- P2/P3 不新增 UI 功能，仅验证 LAN/Debian 场景下的 UI 稳定性与恢复行为。

## screenpipe 参考与对齐
- screenpipe UI 以 API 驱动为主（search/chat/timeline 关键交互依赖服务端能力接口）。
- 本决策与 screenpipe 在“关键交互闭环可验证”上对齐；在 UI 技术栈与部署形态上不要求完全对齐（由 Edge-Centric 约束决定）。

## Consequences
- 优点：
  - 在不扩大 P1 范围的前提下，补齐“用户可用性”验收闭环。
  - 将 UI 问题前置到各子阶段发现，降低 P1-S7 集中返工风险。
- 代价：
  - 增加阶段验收工作量与测试脚本维护成本。
  - 无法覆盖全部复杂交互，仅保障最小可用闭环。

## Risks
- 最小 Gate 可能遗漏长尾交互缺陷。
- Edge 高负载下 UI 与处理链路争用仍可能导致体验抖动。

## Validation
- 每个 P1 子阶段验收记录必须包含 UI 检查项与证据（截图/录屏/日志）。
- UI 关键路径通过率纳入 Gate；未达标不得进入下一子阶段。
- Phase2/Phase3 增加 UI 稳定性门槛（LAN 24h、Debian 7 天致命中断次数为 0）。
