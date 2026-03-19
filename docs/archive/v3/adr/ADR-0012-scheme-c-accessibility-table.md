# ADR-0012 Scheme C：accessibility 表分表写入 + focused P0 修复

- 状态：**Superseded for v3 mainline on 2026-03-13**
- 日期：2026-03-02
- 覆盖：018A（部分）、022A（部分）
- 新增：025A
- 关联：**OQ-043（OCR-only 收口）**

> **重要说明**：本 ADR 的 Scheme C 分表写入语义（AX 成功 → accessibility 表，OCR fallback → ocr_text 表）已被 **OQ-043** defer 到 v4。
>
> - v3 主线：OCR-only，所有帧写入 `ocr_text` 表，`text_source='ocr'`
> - accessibility 表：保留为 **v4 reserved seam**，v3 代码完全不触碰
>
> 本 ADR 保留为审计历史，用于 v4 恢复 AX 时的设计输入。

## Context

架构评审中发现三个关键事实：

1. **screenpipe 双写架构**：screenpipe 有两条完全独立的 accessibility 写入路径：
   - `paired_capture`（frame 级）：AX 成功 → `frames.accessibility_text` + `frames.text_source='accessibility'`，**不写 `ocr_text` 行**（`ocr_data = None`，`db.rs:1538` 的 `if let Some(...)` 不执行）；AX 失败 → OCR fallback → 写 `ocr_text` 行。证据：`paired_capture.rs:153-154`、`db.rs:1487-1570`。
   - `ui_recorder` 树遍历器（独立循环）：每 ~500ms 遍历 AX tree → 写入独立 `accessibility` 表（`db.rs:5287-5311`）。

2. **spec 矛盾**：v3 spec 同时声明 `ocr_text 与 frames 保持 1:1`（018A）和 `AX-first + OCR-fallback 对齐 screenpipe`（§3.3）。在 screenpipe 中，AX 成功帧无 `ocr_text` 行，因此 1:1 不成立。

3. **focused 限制**：screenpipe `db.rs:1870-1872` 在 `focused` 或 `browser_url` 存在时强制 `content_type = ContentType::OCR`。根因：`accessibility` 表无 `focused` 列，`search_accessibility()` 不接受 `focused` 参数。在 AX-first 模式下 ~90%+ 帧无 `ocr_text` 行，`search_ocr()` 用 `INNER JOIN ocr_text` 会漏掉这些帧。这是 screenpipe 的已知 bug/limitation。

## Decision

### Scheme C（分表写入，025A）

**写入路径**：
- AX 成功 → `frames` 行（`accessibility_text=AX 文本`, `text_source='accessibility'`）+ `accessibility` 表行 + **无 `ocr_text` 行**
- AX 失败/OCR fallback → `frames` 行（`text_source='ocr'`）+ `ocr_text` 行 + **无 `accessibility` 行**

**搜索分发**：
- `content_type=ocr` → `search_ocr()`（INNER JOIN ocr_text，现有逻辑）
- `content_type=accessibility` → `search_accessibility()`（accessibility + accessibility_fts）
- `content_type=all`（默认）→ 并行 search_ocr() + search_accessibility() → merge by timestamp DESC

### focused P0 修复

v3 `accessibility` 表新增 `focused BOOLEAN DEFAULT NULL` 列（screenpipe 无此列）。`search_accessibility()` 支持 `focused` 过滤。v3 **不做** screenpipe 的 `focused/browser_url → force content_type=ocr` 降级。

### frame_id 方案 3

v3 `accessibility` 表新增 `frame_id INTEGER DEFAULT NULL`（screenpipe 无此列）。`paired_capture` 写入时填入对应 `frames.id`；未来独立 `ui_recorder` walker 写入时留 NULL。`search_accessibility()` 通过 `LEFT JOIN frames ON accessibility.frame_id = frames.id` 做精确关联（当 frame_id 非 NULL 时），避免 screenpipe 的 ±1s 时间窗口 JOIN 模糊性。

## screenpipe 参考与对齐

- `accessibility` 表 DDL 对齐 screenpipe migration `20250202000000`（lines 8-19, 30-37, 40-55）
- `accessibility_fts` FTS5 + triggers 基于 screenpipe 同一 migration，v3 增加 `browser_url` 列（4 indexed 列 vs screenpipe 3 列）确保 API 语义一致
- `focused` 列、`frame_id` 列、`accessibility_fts.browser_url` 列为 v3 增强，screenpipe 无对应
- 搜索三路径分发对齐 screenpipe `search()` 的 `ContentType` 路由（`db.rs:1850-2054`），但 v3 裁剪 `Audio` 和 `Input`

## Consequences

- 优点：
  - 搜索覆盖完整：AX 成功帧可通过 `search_accessibility()` 检索，`focused` 过滤不丢数据
  - 与 screenpipe 能力层完全对齐：`content_type` 参数语义一致
  - `frame_id` 精确关联消除 ±1s 时间窗口的模糊性
  - DDL 复杂度可控（一张表 + 一张 FTS + 3 triggers + 2 indexes）
- 代价：
  - P0 范围略增：多建一张表 + FTS + triggers（但 DDL 直接复用 screenpipe migration 模式，实现成本低）
  - 初始迁移文件 `20260227000001_initial_schema.sql` 内容增加

## Risks

- `accessibility` 表在 P0 建立但 `ui_recorder` 独立管线 P1+ 才实装，初期 accessibility 行 = paired_capture 写入量（非独立数据源）
- `frame_id` 为 NULL 的行（未来独立 walker）需要 LEFT JOIN，性能特性待 P1+ 验证

## Validation

- P1-S3 Gate：AX 成功帧写入 `accessibility` 表的正确率 = 100%
- P1-S4 Gate：`search_accessibility()` 路径覆盖率 = 100%；`focused` 过滤正确性 = 100%
- P1-S4 Gate：`content_type=all` 并行合并结果按 timestamp DESC 有序 = 100%
