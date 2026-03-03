# MyRecall-v3 决策基线（SSOT）

- 版本：v1.0
- 日期：2026-03-03
- 作用：本文件是 001A~025A 的唯一“当前有效状态”清单。
- 关联：[`adr/`](./adr/), [`spec.md`](./spec.md), [`open_questions.md`](./open_questions.md)

## DEC-000 规则

- 决策引用格式统一为 `DEC-xxxx`（如 `DEC-020A`）。
- 非本文件禁止维护“已拍板完整列表”；只能引用 ID。
- 若决策被覆盖，状态必须更新为 `Superseded` 并给出替代 ID。

## 决策条目（001A~025A）

| 决策 ID | 状态 | 生效日期 | 当前结论（摘要） | 主要依据 |
|---|---|---|---|---|
| DEC-001A | Accepted | 2026-02-26 | 与 screenpipe 做行为/能力对齐，不做拓扑对齐。 | [ADR-0001](./adr/ADR-0001-edge-centric-responsibility-split.md) |
| DEC-002A | Accepted (Revised) | 2026-03-01 | Chat 请求用简单 JSON；响应 SSE 透传 Pi 原生事件；不做 OpenAI format 翻译。 | [ADR-0004](./adr/ADR-0004-chat-rag-orchestration-on-edge.md) |
| DEC-003A | Accepted (Superseded prior approach) | 2026-02-26 | Search 主路径完全对齐 screenpipe vision-only，线上仅 FTS+过滤，舍弃 hybrid。 | [ADR-0005](./adr/ADR-0005-search-screenpipe-vision-only.md), [ADR-0003](./adr/ADR-0003-edge-index-and-search-hybrid.md) |
| DEC-004A | Accepted | 2026-02-26 | Host 采集 accessibility 文本（仅采集，不推理）。 | [ADR-0001](./adr/ADR-0001-edge-centric-responsibility-split.md) |
| DEC-005A | Accepted (Revised) | 2026-02-26 | Edge 支持本地/云端模型切换（Pi provider/model）；P1 不做自动 fallback。 | [ADR-0004](./adr/ADR-0004-chat-rag-orchestration-on-edge.md) |
| DEC-006A | Accepted (Phase-upgrade) | 2026-02-26 | 传输安全按阶段升级：P1 token+TLS 可选，P2+ mTLS 强制。 | [ADR-0002](./adr/ADR-0002-host-edge-ingest-protocol.md) |
| DEC-007A | Accepted | 2026-02-26 | P1~P3 UI 继续部署在 Edge；Host 不承载 UI。 | [ADR-0006](./adr/ADR-0006-ui-placement-edge-first.md) |
| DEC-008A | Accepted | 2026-02-26 | 功能开发集中在 P1 完成；P2/P3 功能冻结。 | [ADR-0007](./adr/ADR-0007-phase-functional-freeze.md) |
| DEC-009A | Accepted | 2026-02-26 | Phase 1 拆为 P1-S1~S7 串行子阶段并逐段 Gate。 | [ADR-0008](./adr/ADR-0008-phase1-serial-substages.md) |
| DEC-010A | Accepted | 2026-02-26 | 每个阶段/子阶段验收必须有 Markdown 归档记录。 | [ADR-0009](./adr/ADR-0009-acceptance-markdown-records.md) |
| DEC-011A | Accepted | 2026-02-26 | Gate 采用双轨：数值适度放宽 + 功能完成度强化。 | [ADR-0010](./adr/ADR-0010-gate-dual-track-metrics.md) |
| DEC-012A | Accepted | 2026-02-26 | UI Gate 采用最小可用集，不做 UI 重构。 | [ADR-0011](./adr/ADR-0011-ui-minimal-gates-phase1.md) |
| DEC-013A | Accepted | 2026-02-26 | Chat 引用覆盖率为 Soft KPI（non-blocking），分阶段目标观测回归。 | [gate_baseline.md](./gate_baseline.md) |
| DEC-014A | Accepted | 2026-02-27 | 删除 fusion/caption/keywords 索引时预计算，索引时零 AI 调用。 | [ADR-0005](./adr/ADR-0005-search-screenpipe-vision-only.md) |
| DEC-015A | Accepted | 2026-02-27 | `ocr_text_embeddings` 仅离线实验，不进入线上 search 主路径。 | [ADR-0005](./adr/ADR-0005-search-screenpipe-vision-only.md) |
| DEC-016A | Accepted | 2026-02-27 | v3 全新数据起点，不做 v2 数据迁移。 | [ADR-0007](./adr/ADR-0007-phase-functional-freeze.md) |
| DEC-017A | Accepted | 2026-02-27 | 数据模型采用“主路径对齐 + 差异显式”。 | [data_model.md](./data_model.md) |
| DEC-018A | Superseded by DEC-018C | 2026-03-02 | 历史方案（不再有效）。 | [ADR-0012](./adr/ADR-0012-scheme-c-accessibility-table.md) |
| DEC-018C | Accepted | 2026-03-02 | Scheme C：AX 成功写 accessibility；OCR fallback 写 ocr_text；`text_source` 在 frames。 | [ADR-0012](./adr/ADR-0012-scheme-c-accessibility-table.md) |
| DEC-019A | Accepted | 2026-02-27 | P1 ingest 协议为单次幂等上传 + queue/status；分片协议推迟到 P2。 | [ADR-0002](./adr/ADR-0002-host-edge-ingest-protocol.md) |
| DEC-020A | Accepted | 2026-02-27 | P1 API 契约冻结：`/v1/search` 合并 keyword，返回 `file_path + frame_url`，统一错误格式。 | [api_contract.md](./api_contract.md) |
| DEC-021A | Accepted | 2026-02-27 | `ocr_text` 增加 `app_name/window_name`；接受与 frames 潜在 drift。 | [data_model.md](./data_model.md) |
| DEC-022A | Superseded by DEC-022C | 2026-03-02 | 历史单路径搜索方案（不再有效）。 | [ADR-0012](./adr/ADR-0012-scheme-c-accessibility-table.md) |
| DEC-022C | Accepted | 2026-03-02 | Search 三路径分发：`search_ocr/search_accessibility/search_all`。 | [ADR-0012](./adr/ADR-0012-scheme-c-accessibility-table.md) |
| DEC-023A | Accepted | 2026-02-27 | Migration 采用手写 SQL + `schema_migrations`。 | [data_model.md](./data_model.md) |
| DEC-024A | Accepted | 2026-02-26 | API 命名空间冻结为 `/v1/*`。 | [api_contract.md](./api_contract.md) |
| DEC-025A | Accepted | 2026-03-02 | P0 建 `accessibility` 表，新增 `focused` 与 `frame_id` 修复筛选与关联。 | [ADR-0012](./adr/ADR-0012-scheme-c-accessibility-table.md) |

## 变更日志

| 日期 | 变更 | 影响范围 | 回滚策略 |
|---|---|---|---|
| 2026-03-03 | 建立决策 SSOT，统一 `DEC-*` 引用命名。 | `spec/roadmap/open_questions/acceptance` | 若发现引用断裂，回滚到上一个提交并保留 `decisions.md` 空壳与迁移清单。 |
| 2026-03-01 | **DEC-002A 修订**：Chat 请求格式从 OpenAI-compatible 改为简单 JSON `{message, session_id, images?}`；响应从 OpenAI format 改为 SSE 透传 Pi 原生 11 种事件。 | Chat 架构（ADR-0004） | 修订不可逆，需重新评估对齐策略。 |
| 2026-02-26 | **DEC-005A 修订**：Edge 支持本地/云端模型切换（Pi `--provider`/`--model` 参数）；P1 不做自动 fallback，provider 故障直接报错。 | Chat 路由（ADR-0004） | 修订不可逆，需重新评估 provider 策略。 |
| 2026-03-02 | **DEC-018A → DEC-018C**：Scheme C 表设计替代原 Scheme A/B 方案（AX 成功写 accessibility，OCR fallback 写 ocr_text）。 | 数据模型（ADR-0012） | 需重建数据库或 migration。 |
| 2026-03-02 | **DEC-022A → DEC-022C**：搜索从单路径改为三路径分发（`search_ocr/search_accessibility/search_all`）。 | 搜索 API（ADR-0012） | 需更新 API 契约与测试用例。 |
| 2026-03-02 | **DEC-025A 新增**：P0 建 `accessibility` 表，新增 `focused` 与 `frame_id` 列修复筛选与关联。 | 数据模型（ADR-0012） | 需执行新 migration。 |

## 修订详情

### DEC-002A 修订记录（2026-03-01）

| 项目 | 修订前 | 修订后 |
|------|--------|--------|
| 请求格式 | OpenAI-compatible `{messages: [...], ...}` | 简单 JSON `{message, session_id, images?}` |
| 响应格式 | OpenAI format `{choices: [{delta: {content: ...}}]}` | SSE 透传 Pi 原生 11 种事件 |
| 事件映射 | 仅 `message_update` → `delta.content` | 11 种 Pi 事件透传（message_start/message_update/message_end/agent_start/agent_end/tool_execution_*/response 等） |
| 决策依据 | DA-2 初版分析 | DA-2 修订：AG-UI Protocol 等行业趋势验证 + Chat UI 绿地开发无兼容需求 |

### DEC-005A 修订记录（2026-02-26）

| 项目 | 初版 | 修订后 |
|------|------|--------|
| 模型位置 | 未明确 | Edge 推理（Host 不做 OCR/Embedding/Chat） |
| provider 切换 | 未明确 | 支持通过 `--provider`/`--model` 切换 |
| fallback 机制 | 未明确 | P1 不做自动 fallback，故障直接报错 |

## 禁止重复项

- `spec.md`, `roadmap.md`, `open_questions.md` 不得再维护完整“已拍板清单”。
- 新决策必须先更新本文件，再更新引用文档。
