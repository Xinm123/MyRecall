# MyRecall-v3 文档一致性治理（SSOT）

- 版本：v1.0
- 日期：2026-03-03
- 目标：避免跨文档冲突、重复、漂移；保证规范可验证、可演进。

## 1. SSOT 矩阵

| 主题 | SSOT 文件 | 其他文档允许内容 | 禁止内容 |
|---|---|---|---|
| 决策状态 | [`decisions.md`](./decisions.md) | 引用 `DEC-*` + 链接 | 复制完整已决清单 |
| 架构边界 | [`architecture.md`](./architecture.md) | 阶段内引用边界结论 | 重写完整架构规则 |
| 数据结构/SQL 路由 | [`data_model.md`](./data_model.md) | 引用 `DB-*` + 本阶段说明 | DDL/触发器/SQL 复制 |
| API 契约 | [`api_contract.md`](./api_contract.md) | 引用 `API-*` + 测试说明 | 重新定义 schema |
| 指标口径 | [`gate_baseline.md`](./gate_baseline.md) | 引用 `GATE-*` + 阶段阈值说明 | 复制公式与判定规则 |
| 验收证据 | `acceptance/**` | 测试步骤、结果、证据 | 发布新规范条款 |

## 2. 引用规范

### 2.1 ID 规则

- 决策：`DEC-xxxx`（如 `DEC-020A`）。
- 数据：`DB-...`（如 `DB-001`）。
- API：`API-...`（如 `API-200`）。
- Gate：`GATE-...`（如 `GATE-TTS-001`）。

### 2.2 强制要求

1. `roadmap/open_questions/acceptance` 只能写“ID + 链接 + 本阶段说明”。
2. 每个验收文档开头必须有“规范引用 IDs”。
3. 非 SSOT 文档不得出现完整 DDL 与完整 API schema。

## 3. 变更流程

1. 提案：提交“变更影响矩阵”（涉及哪些 SSOT）。
2. 更新顺序：先改 SSOT，再改引用文档，最后改验收模板与检查脚本。
3. 校验：运行 `python scripts/check_docs_consistency.py`。
4. 评审：至少 1 位架构评审 + 1 位实施负责人确认。
5. 发布：在 `decisions.md` 的变更日志记录日期、影响范围、回滚策略。

### 3.1 一致性检查脚本说明

脚本路径：`scripts/check_docs_consistency.py`

**执行方式**：
```bash
cd MyRecall && python scripts/check_docs_consistency.py
```

**检查项清单**：

| 检查项 | 验证内容 | 报错时动作 |
|--------|----------|------------|
| 必填文件存在 | spec.md, architecture.md, data_model.md, api_contract.md, decisions.md, document_governance.md, roadmap.md, open_questions.md, gate_baseline.md | 终止发布 |
| spec.md 行数限制 | <= 220 行 | 需拆分 spec.md |
| spec.md SSOT 链接 | 必须链接到 architecture.md, data_model.md, api_contract.md, decisions.md | 补充链接 |
| DDL 隔离 | 非 SSOT 文档（spec.md, roadmap.md, open_questions.md, acceptance/**）不得包含 CREATE TABLE/TRIGGER/VIRTUAL TABLE | 移除 DDL |
| spec.md 禁止项 | 不得包含 "## 8. 已拍板基线" 章节 | 迁移到 decisions.md |
| roadmap.md 禁止项 | 不得维护完整 DEC-xxx 清单 | 改为引用 |
| open_questions.md 禁止项 | 不得包含 "已拍板结论" | 迁移到 decisions.md |
| decisions.md 完整性 | 必须包含 DEC-001A ~ DEC-025A | 补充缺失决策 |
| decisions.md 重复检查 | 决策表中不得出现重复 DEC ID | 去除重复 |
| 验收文档必填章节 | 每个 acceptance/**/*.md 必须包含 "## 0. 规范引用 IDs" | 补充章节 |
| Scheme C 验收 | p1-s3.md 必须验证 accessibility 路径 | 补充验收逻辑 |
| p1-s4.md 冲突检查 | 不得包含旧方案残留（如 frames INNER JOIN ocr_text 单路径） | 清除冲突内容 |
| 相对链接有效性 | 所有 Markdown 相对链接必须指向存在文件 | 修复链接 |

**退出码**：0 = 通过，1 = 存在错误

## 4. 旧章节 -> 新文件映射

- 规则 1：`主 SSOT` 是唯一规范来源。
- 规则 2：`次级引用` 仅用于背景与追溯，不承载新规范条款。
- 规则 3：治理文档禁止复制完整 DDL/API 正文。
- 规则 4：`对齐等级` 仅允许使用固定词表：`完全对齐` / `主路径对齐` / `行为对齐` / `概念对齐` / `部分对齐` / `不适用（治理层）`。

### 4.1 章节级映射（总览）

| 旧小节（spec.md） | 主 SSOT | 次级引用 | 关键 IDs | 对齐等级与备注 |
|---|---|---|---|---|
| §1~§2（矛盾、总体架构、职责边界） | `architecture.md` | `decisions.md`, `adr/ADR-0001*.md` | DEC-001A | 主路径对齐；仅能力/行为对齐，不做拓扑对齐 |
| §3（数据模型、DDL、查询路由、迁移） | `data_model.md` | `decisions.md`, `adr/ADR-0012*.md` | DB-001, DEC-017A, DEC-023A | 主路径对齐；差异显式治理 |
| §3.0.6（Host 上传 payload） | `api_contract.md` | `architecture.md`, `decisions.md` | API-010, API-100, DEC-019A | 概念对齐；实现为 Host->Edge 契约适配 |
| §5（演进路线） | `roadmap.md` | `gate_baseline.md`, `acceptance/**` | DEC-008A, DEC-009A, DEC-010A | 不适用（治理层）；以阶段 Gate 为主 |
| §6.3（指标口径引用） | `gate_baseline.md` | `roadmap.md`, `acceptance/**` | DEC-011A, DEC-013A | 不适用（治理层）；统一口径保持不变 |
| §8（已拍板基线） | `decisions.md` | `adr/**`, `spec.md` | DEC-001A~DEC-025A | 不适用（治理层）；决策 SSOT |

### 4.2 旧 spec §4 小节级精确分流（新增）

| 旧小节（spec.md） | 主 SSOT | 次级引用 | 关键 IDs | 对齐等级与备注 |
|---|---|---|---|---|
| §4.1 使用场景与 non-goals | `architecture.md`（§1, §6） | `decisions.md`, `adr/ADR-0001*.md` | DEC-001A | 主路径对齐；拓扑不对齐为刻意策略 |
| §4.2 Capture pipeline（Host/Edge） | `architecture.md`（ARCH-010/020/030） | `api_contract.md`（API-100/API-101）, `decisions.md` | DEC-004A, DEC-019A | 主路径对齐；实现为 Host->Edge 主链路 |
| §4.3 Vision processing（Scheme C） | `data_model.md`（Table 1/2/8） | `decisions.md`, `adr/ADR-0012*.md` | DEC-014A, DEC-018C, DEC-025A | 主路径对齐；包含 `focused/frame_id` 等 v3 增强 |
| §4.4 索引与存储 | `data_model.md`（DB-001.1 + FTS + migration） | `decisions.md`, `architecture.md` | DEC-017A, DEC-023A | 主路径对齐；`edge.db` 与差异显式治理 |
| §4.5 Search（召回与排序） | `api_contract.md`（API-200） | `data_model.md`, `decisions.md`, `adr/ADR-0005*.md` | DEC-003A, DEC-020A, DEC-022C | 主路径对齐；`/v1/search` 合并 keyword，且修复 `focused/browser_url` 限制 |
| §4.6 Chat（核心能力） | `architecture.md`（ARCH-031） | `api_contract.md`（API-500）, `decisions.md`, `adr/ADR-0004*.md` | DEC-002A, DEC-005A, DEC-013A | 行为对齐；外层 SSE 适配替代 Tauri IPC |
| §4.7 同步与传输（LAN 主链路） | `api_contract.md`（API-100/API-101） | `architecture.md`, `decisions.md`, `adr/ADR-0002*.md` | DEC-006A, DEC-019A, DEC-024A | 概念对齐；实现为 Host->Edge 主链路且安全策略分阶段 |
| §4.8 UI 能力与阶段 Gate | `roadmap.md`（P1~P3 Gate） | `architecture.md`, `decisions.md`, `adr/ADR-0011*.md` | DEC-007A, DEC-011A, DEC-012A | 行为对齐；UI 形态与部署不追求同构 |
| §4.9 API 契约总览 | `api_contract.md`（API-001/002/100/101/200/300/400/500） | `decisions.md`, `spec.md` | DEC-020A, DEC-024A | 部分对齐；v3 命名空间冻结为 `/v1/*` |

## 5. 已知冲突与修复基线

- ~~冲突：`acceptance/phase1/p1-s4.md` 仍要求 `frames INNER JOIN ocr_text` 单路径与 `frames-completed == ocr_text`。~~
- ~~修复：改为 Scheme C 三路径 Gate（`search_ocr/search_accessibility/search_all`）与分路径计数口径。~~
- 状态：**已解决** - p1-s4.md (v2026-03-03) 已更新为 Scheme C 三路径验收标准，正确引用 DEC-022C/DEC-025A，步骤 52-55 已描述三路径分发逻辑。
- 依据：`DEC-018C`, `DEC-022C`, `DEC-025A`, [`ADR-0012`](./adr/ADR-0012-scheme-c-accessibility-table.md)。

## 6. T0/T1/T2 执行状态

- T0：冲突修复 + 边界冻结。✅ 已完成（p1-s4.md Scheme C 冲突已解决）
- T1：拆分迁移（本次已完成）。
- T2：一致性检查 + PR 模板门禁（本次已完成初版）。
