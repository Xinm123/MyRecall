# MyRecall-v3 规格总览（导航入口）

- 版本：v1.1
- 日期：2026-03-03
- 定位：本文件是 v3 文档入口与边界摘要，不再承载完整 DDL/API/决策清单。

## 1. 目标与范围

- 目标：在 vision-only 范围内对齐 screenpipe 能力行为，同时落地 Edge-Centric（Host 轻、Edge 重）。
- 范围：capture -> processing -> search -> chat（不含 audio）。
- 部署边界：Host 与 Edge 默认同 LAN，但架构要求可远端化。

## 2. 核心已决矛盾

1. 对齐 screenpipe 与 Edge-Centric 的冲突：采用“行为/能力对齐”，不追求拓扑一致（DEC-001A）。
2. 可选模型与 Edge 必须参与的冲突：模型推理固定在 Edge，Host 不做 OCR/Embedding/Chat 推理（DEC-005A）。

完整决策见 [`decisions.md`](./decisions.md)。

## 3. SSOT 导航

| 主题 | SSOT 文件 | 说明 |
|---|---|---|
| 架构边界 | [`architecture.md`](./architecture.md) | Host/Edge 职责、关键流程、non-goals |
| 数据模型 | [`data_model.md`](./data_model.md) | DDL、FTS、触发器、Search SQL 路由、migration |
| API 契约 | [`api_contract.md`](./api_contract.md) | `/v1/*` 请求/响应、错误码、幂等语义 |
| 决策基线 | [`decisions.md`](./decisions.md) | DEC-001A~DEC-025A 当前有效状态 |
| Gate 口径 | [`gate_baseline.md`](./gate_baseline.md) | 指标公式、样本、判定规则 |
| 路线图 | [`roadmap.md`](./roadmap.md) | 里程碑、阶段 Gate、验收节奏 |
| 待决项 | [`open_questions.md`](./open_questions.md) | 仅未决问题 |
| 治理机制 | [`document_governance.md`](./document_governance.md) | SSOT、引用规范、变更流程 |

## 4. 路线与验证（摘要）

- Phase 1：本机模拟 Edge，串行推进 P1-S1~S7，完成功能闭环。
- Phase 2：LAN 双机验证，功能冻结，仅做稳定性与重放正确性。
- Phase 3：Debian 生产化，功能冻结，仅做部署运维与回滚能力。

阶段细则见 [`roadmap.md`](./roadmap.md)。

## 5. SLO 与 Gate（摘要）

- TTS P95 <= 12s（[`GATE-TTS-001`](./gate_baseline.md#gate-tts-001)）
- Capture 丢失率 <= 0.2%（[`GATE-CAPTURE-LOSS-001`](./gate_baseline.md#gate-capture-loss-001)）
- Search P95 <= 1.8s（[`GATE-SEARCH-P95-001`](./gate_baseline.md#gate-search-p95-001)）
- Chat 首 token P95 <= 3.5s（[`GATE-CHAT-FIRST-TOKEN-001`](./gate_baseline.md#gate-chat-first-token-001)）
- 引用覆盖率为 Soft KPI（non-blocking）（[`GATE-CITATION-001`](./gate_baseline.md#gate-citation-001)）

统一口径与样本规则见 [`gate_baseline.md`](./gate_baseline.md)。

## 6. 文档使用规则

1. 需要决策依据时，引用 `DEC-*`，不要复制整段“已拍板清单”。
2. 需要 DDL/SQL 时，引用 `data_model.md`，不要在非 SSOT 文档重复粘贴。
3. 需要 API schema 时，引用 `api_contract.md`，不要在 `roadmap/acceptance` 重定义。
4. 验收记录只报告结果与证据，不定义新规范条款。
5. 旧 `spec.md` 章节分流请查看 `document_governance.md` 第 4 节（旧章节 -> 新文件映射）。

## 7. 变更与回滚

- 文档变更顺序：先 SSOT -> 再引用文档 -> 再验收模板与检查脚本。
- 一致性检查：`python scripts/check_docs_consistency.py`。
- 若拆分引发引用断裂，按 `document_governance.md` 回滚策略执行。
