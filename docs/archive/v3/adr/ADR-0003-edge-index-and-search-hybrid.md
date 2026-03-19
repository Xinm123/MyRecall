# ADR-0003 Edge 端索引与检索采用 Hybrid（已被替代）

- 状态：Superseded
- 日期：2026-02-26

> Superseded by `ADR-0005-search-screenpipe-vision-only.md`

## Context
- MyRecall v2 已有 Vector + FTS + rerank。
- screenpipe 检索主干更偏 FTS + 元数据过滤。

## Decision（历史）
- 曾决策：Edge 保持 Hybrid（FTS + Vector + rerank）。
- 现已废止：按用户最新指令，search 线上路径改为完全对齐 screenpipe（vision-only）。

## screenpipe 参考与对齐
- screenpipe 做法：`/search` 支持丰富过滤，FTS 权重较高。
- 对齐结论：行为对齐、算法不强制一致。

## Consequences（历史）
- 优点：语义检索能力保留，Chat RAG 质量更稳。
- 代价：双索引一致性治理成本增加。

## Risks
- reranker 依赖不可用时性能或质量回退。

## Validation
- 每日离线评测 + 线上抽样，NDCG/Recall 与延迟同时达标。
