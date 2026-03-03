# ADR 索引（Architecture Decision Records）

- 版本：v1.0
- 日期：2026-03-03
- 作用：本文件是 ADR 的快速导航索引
- 关联：[`decisions.md`](../decisions.md)、[`spec.md`](../spec.md)

---

## 概述

| 统计 | 数量 |
|------|------|
| 已 Accepted | 10 |
| 已 Superseded | 2 |
| **总计** | **12** |

---

## ADR 索引表

| ADR ID | 标题 | 状态 | 生效日期 | 关联 SSOT | 关联 DEC |
|--------|------|------|----------|------------|----------|
| [ADR-0001](./ADR-0001-edge-centric-responsibility-split.md) | Edge-Centric 职责边界 | Accepted | 2026-02-26 | `architecture.md` | DEC-001A, DEC-004A |
| [ADR-0002](./ADR-0002-host-edge-ingest-protocol.md) | Host-Edge 传输协议（幂等 + 断点续传） | Accepted | 2026-02-26 | `api_contract.md` | DEC-006A, DEC-019A |
| [ADR-0003](./ADR-0003-edge-index-and-search-hybrid.md) | 边缘索引与混合搜索 | ~~Superseded~~ | — | `data_model.md` | DEC-003A |
| [ADR-0004](./ADR-0004-chat-rag-orchestration-on-edge.md) | Chat RAG 编排（Pi Sidecar + Manager） | Accepted (Revised) | 2026-03-01 | `architecture.md`, `api_contract.md` | DEC-002A, DEC-005A |
| [ADR-0005](./ADR-0005-search-screenpipe-vision-only.md) | Search 纯 Vision-Only 路径 | Accepted | 2026-02-26 | `data_model.md`, `api_contract.md` | DEC-003A, DEC-014A, DEC-015A |
| [ADR-0006](./ADR-0006-ui-placement-edge-first.md) | UI 部署位置（Edge First） | Accepted | 2026-02-26 | `architecture.md` | DEC-007A |
| [ADR-0007](./ADR-0007-phase-functional-freeze.md) | Phase 功能冻结策略 | Accepted | 2026-02-26 | `roadmap.md` | DEC-008A, DEC-016A |
| [ADR-0008](./ADR-0008-phase1-serial-substages.md) | Phase 1 串行子阶段 | Accepted | 2026-02-26 | `roadmap.md` | DEC-009A |
| [ADR-0009](./ADR-0009-acceptance-markdown-records.md) | 验收 Markdown 记录 | Accepted | 2026-02-26 | `acceptance/README.md` | DEC-010A |
| [ADR-0010](./ADR-0010-gate-dual-track-metrics.md) | Gate 双轨指标（数值 + 功能） | Accepted | 2026-02-26 | `gate_baseline.md` | DEC-011A |
| [ADR-0011](./ADR-0011-ui-minimal-gates-phase1.md) | Phase 1 最小 UI Gate | Accepted | 2026-02-26 | `roadmap.md` | DEC-012A |
| [ADR-0012](./ADR-0012-scheme-c-accessibility-table.md) | Scheme C: accessibility 表设计 | Accepted | 2026-03-02 | `data_model.md` | DEC-018C, DEC-022C, DEC-025A |

---

## 按主题分组

### 架构与职责

| ADR ID | 主题 | 关键结论 |
|--------|------|----------|
| ADR-0001 | Edge-Centric | Host 负责采集/上传，Edge 负责处理/检索/Chat |
| ADR-0006 | UI 部署 | P1~P3 UI 部署在 Edge，不承载于 Host |

### 传输与协议

| ADR ID | 主题 | 关键结论 |
|--------|------|----------|
| ADR-0002 | Host-Edge 传输 | 幂等上传 + 断点续传，P1 单次上传 + queue/status |

### 搜索与数据

| ADR ID | 主题 | 关键结论 |
|--------|------|----------|
| ADR-0003 | 混合搜索 | ~~已废弃~~，被 ADR-0005 替代 |
| ADR-0005 | Vision-Only | 纯 FTS+过滤，舍弃 hybrid embedding |
| ADR-0012 | Scheme C | AX 成功写 accessibility 表，OCR fallback 写 ocr_text 表 |

### Chat

| ADR ID | 主题 | 关键结论 |
|--------|------|----------|
| ADR-0004 | Pi Sidecar | Python Manager + Pi 子进程，SSE 透传事件 |

### 阶段与验收

| ADR ID | 主题 | 关键结论 |
|--------|------|----------|
| ADR-0007 | 功能冻结 | P1 开发，P2/P3 仅稳定性 |
| ADR-0008 | 子阶段 | P1 拆为 S1~S7 串行推进 |
| ADR-0009 | 验收记录 | Markdown 归档 |
| ADR-0010 | Gate 指标 | 数值 + 功能双轨 |
| ADR-0011 | UI Gate | 最小可用集 |

---

## 已废弃/替代的 ADR

| 被替代的 ADR | 替代方案 | 说明 |
|--------------|----------|------|
| ADR-0003 | ADR-0005 | 混合搜索方案废弃，改为纯 Vision-Only |
| DEC-018A | DEC-018C | Scheme C 表设计替代原 Scheme A/B 方案（对应 ADR-0012） |
| DEC-022A | DEC-022C | Scheme C 三路径替代单路径搜索（对应 ADR-0012） |

---

## 维护规则

1. 新 ADR 必须在 `decisions.md` 中有对应 DEC 条目
2. ADR 状态变更（Accepted → Superseded）必须同步更新 `decisions.md`
3. 每个 ADR 文件头部必须包含：版本号、状态、生效日期（如 "版本：v1.0"）
4. 本索引由 `adr/README.md` 承载，更新后版本号 +1

---

## 版本历史

| 版本 | 日期 | 变更 |
|------|------|------|
| v1.0 | 2026-03-03 | 初始索引 |
