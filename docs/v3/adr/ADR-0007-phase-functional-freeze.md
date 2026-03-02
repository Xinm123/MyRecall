# ADR-0007 阶段策略：P1 功能完成，P2/P3 功能冻结

- 状态：Accepted
- 日期：2026-02-26

## Context
- 用户要求：在 Phase 1 完成和完善全部功能；Phase 2/3 仅做部署、LAN 稳定性与重放正确性、Debian 服务化。
- 当前草案中部分功能原本分布在 P2（例如事件驱动 capture、Chat 部分能力），与上述要求冲突。

## Decision
- Phase 1（本机模拟 Edge）必须完成 v3 全视觉链路功能闭环：
  - capture：事件驱动 + idle fallback
  - processing：AX-first + OCR-fallback
  - search：FTS+过滤（vision-only）
  - chat：Pi Sidecar + SKILL.md tool-driven retrieval + 提示词驱动引用 + provider/model 路由 + 流式输出 + timeout 处理
- Phase 2（LAN 双机）和 Phase 3（Debian 生产）执行功能冻结：
  - 不新增业务功能
  - 仅允许缺陷修复、性能/稳定性治理、安全与运维收敛

## screenpipe 参考与对齐
- screenpipe 在单节点形态下功能链路本身是完整可用的，部署形态不是按功能分期推进。
- 本决策在“先做完整功能，再做部署稳定化”的策略上与 screenpipe 的实践方向可对齐；拓扑层仍不对齐（v3 强制 Edge-Centric）。

## Consequences
- 优点：
  - 减少跨阶段功能变更，接口更早冻结，便于 P2/P3 专注稳定性。
  - 对部署与运维验证更友好，问题定位更聚焦。
- 代价：
  - Phase 1 范围明显增大，排期与资源压力提升。

## Risks
- P1 延期风险上升，可能挤压 P2/P3 的稳定性验证窗口。

## Validation
- P1 Gate：功能清单全部验收通过，接口契约冻结。
- P2 Gate：24h LAN soak + 重放正确性通过，无新增功能项。
- P3 Gate：Debian 7 天稳定运行 + 回滚演练通过，无新增功能项。
