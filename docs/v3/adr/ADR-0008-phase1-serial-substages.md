# ADR-0008 Phase 1 串行子阶段与 Gate 验收

- 状态：Accepted
- 日期：2026-02-26

## Context
- 用户要求：Phase 1 拆分为多个阶段，串行实现，分别验收。
- 现状风险：Phase 1 范围已包含全功能闭环，若并行推进后统一验收，失败定位成本高，返工面大。

## Decision
- Phase 1 固定拆分为七个串行子阶段：
  - P1-S1：基础链路（Host 上传 + Edge ingest/queue + 页面可用）
  - P1-S2：采集（事件驱动 capture + idle fallback + AX 文本采集）
  - P1-S3：处理（AX-first/OCR-fallback + text_source 记录，索引时零 AI 增强）
  - P1-S4：检索（FTS+过滤 API 与返回契约）
  - P1-S5：Chat-1（grounding 与引用）
  - P1-S6：Chat-2（provider/model 路由、Pi 事件流式输出、timeout 处理）
  - P1-S7：端到端验收（仅验收，不新增功能）
- 执行规则：
  - 必须串行推进
  - 每个子阶段都要通过 Gate 验收，才允许进入下一阶段

## screenpipe 参考与对齐
- screenpipe 的功能链路是完整闭环，侧重可用性与迭代稳定性。
- 本决策在“先做可验证闭环，再推进下一层能力”的工程节奏上与 screenpipe 实践可对齐；只是 v3 在组织上更显式地引入 Gate。

## Consequences
- 优点：
  - 验收边界清晰，问题定位与回归范围可控。
  - 降低“大爆炸集成”风险，便于持续度量 SLO。
- 代价：
  - 串行化会牺牲部分并行效率，可能延长关键路径。

## Risks
- 若阶段切分不合理，可能出现前序阶段过重导致整体节奏拖慢。

## Validation
- 每个子阶段输出独立验收报告（功能、故障注入、性能）。
- Gate 规则纳入 CI/发布检查清单：未通过不得进入下一子阶段。
