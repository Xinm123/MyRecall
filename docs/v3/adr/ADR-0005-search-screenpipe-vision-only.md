# ADR-0005 Search 完全对齐 screenpipe（vision-only）

- 状态：Accepted
- 日期：2026-02-26

## Context
- 用户最新决策："search 完全和 screenpipe 对齐，舍弃 hybrid"。
- 现有 v3 草案中 `ADR-0003` 采用的是 Hybrid（FTS+Vector+rerrank），与新决策冲突。

## Decision
- MyRecall-v3 的线上 Search 路径改为与 screenpipe（vision-only）一致：
  - FTS 检索 + 元数据过滤（time/app/window/browser_url/focused）
  - 不使用 Vector 检索与 rerank 作为线上主路径
- 对外 API 语义与 screenpipe 保持一致（`/search` 风格过滤能力）。
- Embedding 若保留，仅作为离线实验能力，不作为线上 Search 依赖。

## screenpipe 参考与对齐
- screenpipe 当前主搜索路径以 FTS + 过滤为核心；embedding 主要用于 speaker 等非 vision 主检索路径。
- 对齐结论：本决策在“行为与主算法路径”上与 screenpipe 高一致。

## Consequences
- 优点：
  - 路径简单、实现可控、与目标对齐明确。
  - 检索延迟和运维复杂度更容易控制。
- 代价：
  - 语义型查询召回能力可能下降。
  - Chat 在抽象问题上的上下文召回需要更多 prompt 与过滤策略兜底。

## Risks
- 长尾语义问题检索不足，导致 Chat 回答质量波动。

## Validation
- 评测分组：
  - 组 A：精确关键词查询（必须不低于 screenpipe 对齐基线）
  - 组 B：语义描述查询（量化退化幅度并记录可接受阈值）
- 线上指标：
  - Search P95、引用覆盖率、Chat 失败率（缺上下文）
