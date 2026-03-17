# P1-S4 Critical Review — FTS Search & Legacy API Removal

**审查范围**：`openspec/changes/p1-s4/` 全部 artifacts（proposal、design、2 specs、tasks），关联上游 SSOT（`spec.md` §4.5、`data-model.md` §3.0.3、`gate_baseline.md` §3.1/§3.5、`http_contract_ledger.md` §4.0/§4.1、`acceptance/phase1/p1-s4.md`），以及现有代码（v2 `engine.py`、screenpipe `db.rs:search_ocr()`）。

---

## 1. 总体结论

> [!TIP]
> **P1-S4 文档质量高，SSOT 对齐严谨，screenpipe 行为对齐令人信服。可以进入实施阶段。** 以下列出需要注意的问题和建议。

---

## 2. 优点（已做对的部分）

| 维度 | 评价 |
|------|------|
| **screenpipe 对齐** | `search_ocr()` 的 conditional JOIN 策略、BM25 ranking、`sanitize_fts5_query` 都精确对齐了 `db.rs:2057-2207`，四种 JOIN 组合矩阵与 screenpipe 完全一致 |
| **SSOT 溯源** | 每个决策点都标注了上游 section reference（`spec.md §4.5`、`data-model.md §3.0.3`、`gate_baseline.md §3.1`），溯源链完整 |
| **Non-goals 清晰** | 明确排除了 embedding/hybrid search、`expand_search_query`、search cache、`browser_url` active filtering、`include_frames` 实现 |
| **Legacy 410 策略** | 从 301/308 到 410 的渐进废弃路径在 `http_contract_ledger.md` 有清晰的阶段定义 |
| **测试矩阵完整** | tasks.md §7-§12 覆盖了 FTS 召回、SQL 路径、response schema、reference fields、clear-safe、v4 seam、legacy 410、UI mapping、citation backtrace 共 9 个测试维度 |
| **Design Decisions 有理有据** | D1-D7 每项决策都附带了 "Why not" 和 screenpipe 对齐声明 |

---

## 3. 发现的问题与建议

### 3.1 ⚠️ `frames_fts MATCH` 的元数据过滤构造方式未在 spec 中明确

**问题**：`fts-search/spec.md` 说 "Metadata filtering via `frames_fts MATCH` for `app_name`, `window_name`, `focused`"，但没有明确 MATCH 表达式的精确构造方式。screenpipe 的做法是用 **列限定短语**（`app_name:"Safari"`），`data-model.md` 也提到"直接构造列限定短语"，但 delta spec 和 tasks 中都没有写清楚具体的 MATCH 构造格式。

**风险**：如果实现时用了错误的 FTS5 语法（例如不加列前缀、不引号包裹），会导致跨列 false match 或 FTS5 syntax error。

**建议**：
- 在 `fts-search/spec.md` 的 "Metadata filtering" requirement 下补充 scenario：
  - `frames_fts MATCH 'app_name:"Safari"'`（列限定 + 引号包裹）
- 在 tasks.md 2.7 添加断言：验证 `app_name` 过滤实际使用 `app_name:"value"` 列限定 FTS5 语法

### 3.2 ⚠️ `focused` 过滤走 `frames_fts MATCH` 的实际可靠性

**问题**：screenpipe 中 `focused` 被写入 FTS 表时是 `0` 或 `1`（整数转字符串），MATCH 用 `focused:1`。但 `data-model.md` DDL 中 `frames.focused` 是 `BOOLEAN DEFAULT NULL`，写入 `frames_fts` 时用 `COALESCE(NEW.focused, 0)`。

**风险**：
- `focused=true` 时 FTS5 接收到的 token 是 `1`（sqlite BOOLEAN 的真值表示），这是正确的
- `focused=NULL` 时 COALESCE 写入 `0`，这意味着 `focused:0` 会匹配**所有非前台帧 + 所有 focused 为 NULL 的帧**，可能不是用户预期的语义

**建议**：需要在实现和测试中明确：`focused=false` 和 `focused=null` 在 FTS 层不可区分。这是一个已知的 P1 行为边界，应在 spec 中明确记录。如果 UI 只提供 `focused=true` 过滤（不提供 `focused=false`），则此问题不影响用户体验。

### 3.3 ⚠️ `ocr_text_fts` JOIN 的 `frame_id` 一对多问题

**问题**：`data-model.md` 中 `ocr_text_fts` 的列结构是 `(text, app_name, window_name, frame_id UNINDEXED)`，JOIN 条件是 `JOIN ocr_text_fts ON ocr_text.frame_id = ocr_text_fts.frame_id`。理论上一个 `frame_id` 对应一条 `ocr_text` 行（P1 OCR 单引擎），所以 JOIN 是 1:1。

**但是**：如果某些路径意外写入多条 `ocr_text` 行（例如重试/重处理），`ocr_text_fts` 也会有多行同 `frame_id`，导致 JOIN 膨胀。

**建议**：tasks.md 已有 `orphan_ocr` 检查，建议补充一个 `duplicate_ocr_per_frame` 断言：
```sql
SELECT COUNT(*) FROM (
    SELECT frame_id, COUNT(*) AS cnt 
    FROM ocr_text GROUP BY frame_id HAVING cnt > 1
);
```
预期结果 = 0。

### 3.4 💡 Design D4 中 `v1_api.py` vs `api.py` 的路由归属

**问题**：design.md D4 说将 `/v1/search` 路由加到 `openrecall/server/v1_api.py`，但现有代码中 **没有** `v1_api.py` 文件。当前所有路由（包括 legacy 和 v1）都在 `api.py` 中。

**建议**：
- 方案 A：在 `api.py` 中直接添加（最小改动，与现有模式一致）
- 方案 B：新建 `v1_api.py` Blueprint（更清晰的 namespace 分离）

两种方案都可行。如果选方案 B，tasks.md 需要增加 Blueprint 注册步骤。当前 tasks 3.1 说 "Add `GET /v1/search` route in v1 API blueprint"，暗示方案 B，需要确保 Design 和 Tasks 一致。

### 3.5 💡 COUNT 查询未使用 `GROUP BY`

**问题**：`data-model.md` 定义 COUNT 为 `COUNT(DISTINCT frames.id)`，主查询有 `GROUP BY frames.id`。COUNT 路径不需要 GROUP BY，但如果 `ocr_text` 有多行同 `frame_id`，INNER JOIN 会膨胀 `frames.id` 出现次数，`COUNT(DISTINCT frames.id)` 可以正确去重。

**评估**：设计是正确的，`COUNT(DISTINCT frames.id)` 确保了即使 INNER JOIN 膨胀也能得到正确计数。无需修改。

### 3.6 💡 tasks.md 中的测试文件 `test_p1_s4_sql_path.py` 的断言策略

**问题**：tasks 7.2 说 "use loose keyword assertions (e.g. `USING FTS5 SEARCH`)"，但 `acceptance/p1-s4.md` §3 步骤 4 更精确地说明了应该验证 JOIN 和 FTS 条件是否正确追加。

**评估**：这两个表述一致且互补。`acceptance/p1-s4.md` 正确指出要避免与 SQLite 内部查询计划文本强绑定。tasks.md 的"松散关键字断言"是正确的实现方向。

### 3.7 💡 Latency 记录的指标口径需要更具体

**问题**：tasks 2.9 说 "Add per-request latency logging at info level"，但 `gate_baseline.md §3.5.2` 要求区分三类查询（标准 ≤24h / 超大 >24h / 空查询），且 §3.5.1 说 "预热剔除前 10 个样本" 和 "> 30s 标记为 timeout"。

**建议**：tasks 2.9 应该更精确：
- 记录 latency_ms 时标注查询类型分类（标准/超大/空）
- 纯 info 日志可能不够用于事后统计分析，建议结构化日志格式（如 `MRV3 search_latency_ms=X query_type=standard q_present=true`）
- 或者在验收阶段使用单独的基准测试脚本完成统计，不要求 runtime 做分类

### 3.8 ✅ Legacy 410 spec 无问题

`specs/legacy-api-removal/spec.md` 简洁、完整、无歧义。4 个端点 + 1 个日志要求，每个都有精确 scenario。无改进建议。

---

## 4. 文档间一致性核查

| 检查点 | proposal | design | spec | tasks | acceptance | 上游 SSOT | 结果 |
|--------|----------|--------|------|-------|------------|-----------|------|
| `GET /v1/search` 参数列表 | ✅ 11 参数 | ✅ 引用 spec.md §4.5 | ✅ 完整 | ✅ tasks 3.1 列出全部 | ✅ §1.2 对照表 | ✅ spec.md §4.5 | **一致** |
| Response schema 字段 | ✅ 列出关键字段 | ✅ D7 引用 spec.md | ✅ 引用字段完整 | ✅ tasks 3.2/3.3 | ✅ 引用字段 Hard Gate | ✅ gate §3.1 | **一致** |
| JOIN 策略四种组合 | ✅ 概述 | ✅ D2 矩阵表 | ✅ 四 scenario | ✅ tasks 2.2 | ✅ §3 步骤 4 | ✅ data-model §3.0.3 | **一致** |
| ORDER BY 逻辑 | ✅ BM25/timestamp | ✅ D2 表 | ✅ 两 scenario | ✅ tasks 2.3 | ✅ §3 步骤 4 | ✅ data-model | **一致** |
| 410 Gone 4 端点 | ✅ 列出 | ✅ D6 | ✅ 4 requirement | ✅ tasks 5.1-5.5 | ✅ §3 步骤 8 | ✅ http_contract §4.1 | **一致** |
| `/v1/search/keyword` 404 | ✅ 提及 | ✅ 隐含 | ✅ 1 scenario | ✅ tasks 4.1 | ✅ §1 Gate | ✅ spec §4.5 | **一致** |
| Search P95 观测（非阈值） | ✅ 未提及细节 | ✅ 提及 | ✅ §last requirement | ✅ tasks 2.9 | ✅ §4.1 | ✅ gate §3.5.3 | **一致** |
| `sanitize_fts5_query` | ✅ 提及 | ✅ D3 | ✅ 2 scenario | ✅ tasks 1.1/1.2 | 隐含在 §1.3 | ✅ data-model §sanitize | **一致** |

> [!NOTE]
> 所有八个核心检查点在六层文档间**完全一致**，无矛盾。这是非常好的文档纪律。

---

## 5. screenpipe 对齐验证

通过阅读 `_ref/screenpipe/crates/screenpipe-db/src/db.rs` 第 2057-2207 行的 `search_ocr()` 实现，确认以下对齐点：

| screenpipe 行为 | P1-S4 设计 | 对齐 |
|----------------|-----------|------|
| `JOIN ocr_text ON frames.id = ocr_text.frame_id`（INNER JOIN, 非 LEFT） | ✅ `data-model.md` 明确 INNER JOIN | ✅ |
| 条件 `frames_fts` JOIN（仅当 app/window/browser/focused 非空） | ✅ D2 矩阵 | ✅ |
| 条件 `ocr_text_fts` JOIN（仅当 q 非空） | ✅ D2 矩阵 | ✅ |
| `ocr_text_fts.rank, frames.timestamp DESC`（q 非空时） | ✅ D2 ORDER BY | ✅ |
| `frames.timestamp DESC`（q 为空时） | ✅ D2 ORDER BY | ✅ |
| `sanitize_fts5_query(query)` 用于 `ocr_text_fts MATCH` | ✅ D3 | ✅ |
| `app_name:"value"`列限定 FTS5 语法用于 `frames_fts MATCH` | ⚠️ 隐含但未显式写入 delta spec | **需补充** |
| `text_length` / `min_length` / `max_length` 过滤 | ✅ tasks 2.6 | ✅ |
| `GROUP BY frames.id`（消除 JOIN 膨胀） | ⚠️ screenpipe 有但 design/tasks 未提及 | **需补充** |

---

## 6. 最终建议清单

| # | 优先级 | 建议 | 影响文件 |
|---|--------|------|----------|
| 1 | 🔴 High | **补充 `GROUP BY frames.id`**：screenpipe `search_ocr()` 有 `GROUP BY frames.id`（行 2131），P1-S4 design/tasks 未提及。若不加，同一 frame 可能因多 tag 或多 ocr_text 行出现重复结果。 | design.md, tasks.md 2.2 |
| 2 | 🟡 Medium | **显式记录 `frames_fts MATCH` 的列限定语法**（`app_name:"value"` 格式）在 spec 或 design 中，避免实现者误用全局 MATCH | fts-search/spec.md, tasks.md 2.7 |
| 3 | 🟡 Medium | **`focused=NULL` 在 FTS 层的行为边界**应在 spec 中注明：`COALESCE(focused, 0)` 导致 NULL 和 false 不可区分 | fts-search/spec.md §focused scenario |
| 4 | 🟢 Low | **Latency 日志结构化**：tasks 2.9 建议采用结构化日志 key-value 格式，以便对接 `gate_baseline.md §3.5` 的 query_type 分类统计 | tasks.md 2.9 |
| 5 | 🟢 Low | **确认 `/v1/search` 路由归属**（`api.py` 还是新建 `v1_api.py`），当前 design D4 和现有代码不匹配 | design.md D4 |
| 6 | 🟢 Low | **补充 `duplicate_ocr_per_frame` 防守断言**到 §11 数据完整性验证 | tasks.md 11.1 |

---

## 7. 结论

P1-S4 变更文档**整体质量优秀**，SSOT 溯源严格，与 screenpipe 行为对齐准确，测试矩阵覆盖全面。上述 6 项建议中只有 #1（GROUP BY）是实质性遗漏，需要在实施前补充。其余均为增强性建议。

**可以进入实施阶段**，建议优先处理建议 #1 和 #2。
