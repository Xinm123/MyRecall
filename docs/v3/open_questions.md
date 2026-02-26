# MyRecall-v3 待决问题（必须拍板）

- 日期：2026-02-26
- 说明：以下问题若不拍板，会直接阻塞实现。

| ID | 级别 | 问题 | 选项 | 建议 | 依据 | 风险 | 截止 |
|---|---|---|---|---|---|---|---|
| OQ-001 | P0 | "对齐 screenpipe" 的语义是行为对齐还是实现对齐？ | A 行为对齐（推荐）/ B 实现对齐 | A（已决） | 你的 Edge-Centric 要求与 screenpipe 单机拓扑冲突 | 不拍板会导致方案反复摇摆 | 2026-03-01 |
| OQ-002 | P0 | Chat API 形态 | A OpenAI-compatible + tool schema（推荐）/ B 自定义协议 | A（已决） | 便于本地/云模型切换与客户端复用 | B 会增加前后端耦合 | 2026-03-03 |
| OQ-003 | P0 | Search 策略（vision-only） | A 完全对齐 screenpipe（FTS+元数据过滤，舍弃 hybrid）/ B 保留 MyRecall hybrid | A（已决，覆盖原003） | 你明确要求“search 完全和 screenpipe 对齐，舍弃 hybrid” | 语义召回能力可能下降 | 2026-03-05 |
| OQ-004 | P1 | Host 是否采集 accessibility 文本 | A 采集（推荐）/ B 不采集 | A（已决） | 可对齐 screenpipe paired capture，降低 Edge OCR 压力 | A 需处理平台差异 | 2026-03-08 |
| OQ-005 | P1 | Edge 默认模型策略 | A 本地与云端都支持，按配置切换（可选 fallback，推荐）/ B cloud-first 固定 | A（已决） | 与 screenpipe 的 provider 配置切换能力对齐，且不破坏 Edge-Centric | 需定义 fallback 触发阈值并做压测 | 2026-03-10 |
| OQ-006 | P1 | 传输安全级别（LAN） | A token + TLS 可选（P1）/ B mTLS 强制（P2+） | A->B（已决） | 当前同 LAN，先保证可用性，再在 P2+ 强制 mTLS | 若迟迟不进入 B 阶段，存在长期内网信任风险 | 2026-03-12 |
| OQ-007 | P1 | 页面/UI 在 P1~P3 的部署位置 | A 继续部署在 Edge（推荐）/ B 迁移到 Host | A（已决） | 先保障 Edge 主链路与 Chat 能力收敛，避免并行改造 UI 拖慢节奏 | Edge 计算与 UI 资源争用风险上升 | 2026-03-14 |
| OQ-008 | P1 | 功能开发阶段策略 | A 功能集中在 P1 完成，P2/P3 功能冻结（推荐）/ B 功能按阶段渐进到 P3 | A（已决） | 你明确要求 P2/P3 只做部署与稳定性，不再做功能开发 | P1 范围膨胀导致延期风险上升 | 2026-03-16 |
| OQ-009 | P1 | Phase 1 执行方式 | A 拆分为串行子阶段并逐段验收（推荐）/ B 继续单阶段并行实现后统一验收 | A（已决） | 你明确要求“串行实现、分别验收”，并要求将原 P1-S2 再拆分为“采集/处理”，同时 Chat 再拆分、E2E 验收独立为最后阶段 | 串行化可能降低局部并行效率 | 2026-03-18 |
| OQ-010 | P1 | 验收记录要求 | A 每个阶段/子阶段都必须有 Markdown 详细验收记录（推荐）/ B 仅关键阶段记录 | A（已决） | 你明确要求“每个阶段（子阶段）验收都要用 Markdown 详细记录” | 文档维护成本上升 | 2026-03-19 |
| OQ-011 | P1 | Gate 指标策略 | A 数值阈值适度放宽 + 功能完成度/完善度 Gate 强化（推荐）/ B 维持原严格数值为主 | A（已决） | 你明确要求“数值可宽松一些，但增加功能是否完成/完善的指标和 Gate” | 若功能口径不清会引入主观判定风险 | 2026-03-20 |
| OQ-012 | P1 | UI Gate 粒度 | A 最小可用 Gate（推荐）/ B 完整 UI 契约测试 | A（已决） | 你已明确选择 A，优先保障 P1 交付节奏，同时补齐 UI 可用性验收 | 可能遗漏复杂交互缺陷，需在 P2/P3 重点监控稳定性 | 2026-03-21 |

## 需实验清单

1. AX-first 是否显著提升检索质量（需实验）。
2. 事件驱动捕获在多显示器下的 CPU 上限（需实验）。
3. Debian 端 OCR/VL 组合在 24h soak 中的稳定性（需查证）。

## 已拍板结论（2026-02-26）

1. OQ-001 = A：按“行为/能力对齐”执行，不追求与 screenpipe 的部署拓扑一致。
2. OQ-002 = A：Chat API 采用 OpenAI-compatible + tool schema。
3. OQ-003 = A（覆盖）：Search 完全对齐 screenpipe（vision-only），线上仅保留 FTS+过滤，舍弃 hybrid。
4. OQ-004 = A：Host 采集 accessibility 文本（仅采集，不做推理），Edge 继续 AX-first + OCR-fallback。
5. OQ-005 = A：Edge 支持本地与云端模型，按配置切换（可选 fallback），对齐 screenpipe 的 provider 选择能力。
6. OQ-006 = A->B：P1 使用 token + TLS 可选，P2+ 升级为 mTLS 强制。
7. OQ-007 = A：P1~P3 页面继续在 Edge，Host 不负责 UI；UI 迁移到 Host 仅作为 Post-P3 可选项。
8. OQ-008 = A：功能开发集中在 P1 完成；P2/P3 功能冻结，仅做部署与稳定性。
9. OQ-009 = A：Phase 1 按 P1-S1~S7 串行推进，S2/S3 分别为采集/处理，Chat 拆为 S5/S6，S7 为独立端到端验收阶段。
10. OQ-010 = A：每个阶段/子阶段验收都必须有 Markdown 详细记录，并作为 Gate 输入。
11. OQ-011 = A：Gate 采用双轨策略：数值阈值适度放宽，功能完成度/完善度指标强化。
12. OQ-012 = A：UI Gate 采用“最小可用集”，在 P1 按子阶段强化 UI 可用性/可解释性验收，不做 UI 重构。
