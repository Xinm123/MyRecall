# MyRecall-v3 Search 当前方案基线

> 生成日期：2026-03-02
> SSOT：[../../spec.md](../../spec.md) + [../../adr/ADR-0005-search-screenpipe-vision-only.md](../../adr/ADR-0005-search-screenpipe-vision-only.md) + 当前代码库
> 链路标记：仅屏幕

## 1. 设计层（v3 spec = 目标态）

### 1.1 决策

[E-12] ADR-0005 | 2026-02-26 accepted | FTS-only, 弃 hybrid | H | 已核查

- P1 主路径：纯 FTS5 + 元数据过滤
- Embedding：P2+ 离线实验，不进入线上主路径
- `/v1/search/keyword` 合并入 `/v1/search`

### 1.2 API 契约

[E-13] spec.md §4.5 GET /v1/search 契约 | /v1/search 13 参数 | H | 已核查


| 参数             | 类型      | 默认                     |
| -------------- | ------- | ---------------------- |
| q              | string  | ""                     |
| content_type   | string  | "all"                  |
| limit          | uint32  | 20                     |
| offset         | uint32  | 0                      |
| start_time     | ISO8601 | null                   |
| end_time       | ISO8601 | null                   |
| app_name       | string  | null                   |
| window_name    | string  | null                   |
| browser_url    | string  | null                   |
| focused        | bool    | null                   |
| min_length     | uint    | null                   |
| max_length     | uint    | null                   |
| include_frames | bool    | false (P1 不实现，始终 null) |


Response：`{ data: [{ type, content }], pagination: { limit, offset, total } }`

### 1.3 DB Schema

[E-14] data-model.md §3.0.3 | DDL + FTS 触发器 | H | 已核查

单一 `edge.db`：frames + ocr_text + accessibility + frames_fts + ocr_text_fts + accessibility_fts（Scheme C）。
frames 核心 16 列 100% 对齐 screenpipe。accessibility 表对齐 screenpipe migration `20250202000000` 并增强（+focused, +frame_id）。
accessibility_fts 比 screenpipe 多 `browser_url` 列（4 indexed 列 vs screenpipe 3 列），确保 `browser_url` 参数在所有 content_type 路径下统一为 FTS token 序列匹配。
同步 INSERT/UPDATE/DELETE 触发器（含 accessibility_fts content-sync triggers）。
P1 不建：ocr_text_embeddings、elements。

### 1.4 SQL 搜索策略（Scheme C 三路径分发）

data-model.md §3.0.3 Search SQL JOIN 策略。Scheme C（025A）将搜索拆为三条独立路径，由 `content_type` 参数路由：

- `content_type=ocr` → `search_ocr()`：INNER JOIN ocr_text，4 路条件 JOIN（对齐 screenpipe `search_ocr()`）
- `content_type=accessibility` → `search_accessibility()`：accessibility + accessibility_fts，支持 focused 过滤（P0 修复）
- `content_type=all`（默认）→ `search_all()`：并行 search_ocr() + search_accessibility()，按 timestamp DESC 合并

INNER JOIN 语义（search_ocr 路径）：AX 成功帧无 ocr_text 行，自然排除。这些帧由 search_accessibility() 覆盖。
LEFT JOIN frames（search_accessibility 路径）：frame_id 有索引，性能可控。

### 1.5 FTS 查询规范化（阶段0 新增）

D1=B 决策。P1 实现 `sanitize_fts5_query` + `expand_search_query`。
data-model.md 已补充 §3.0.3（FTS 查询规范化）。

### 1.6 COUNT 查询（阶段0 新增）

D3=A 决策。独立 `COUNT(DISTINCT frames.id)` 支撑 `pagination.total`。
data-model.md 已补充 §3.0.3（COUNT 查询，Scheme C 三路径）。

## 2. 实现层（当前代码 = 现状）

### 2.1 API

[E-15] api.py:29-77 | /api/search, 仅 q+limit | H | 已核查

- 路径：`/api/search`（非 `/v1/search`）
- 参数：q, limit（2/13）
- 空查询返回 `[]`（v3 要求返回全部）

### 2.2 搜索算法

[E-16] engine.py:90-433 | 3 阶段 hybrid | H | 已核查

Vector(LanceDB) → FTS boost(0.3) → Rerank(cross-encoder top30)。与 v3 vision-only 设计方向相反。

### 2.3 DB Schema

[E-17] sql.py:25-62 | entries + ocr_fts | H | 已核查

- `entries` 表：任务队列模型（id, app, title, text, timestamp UNIQUE, embedding, status）
- `ocr_fts`：snapshot_id UNINDEXED, ocr_text, caption, keywords
- 双库分离：recall.db + fts.db

### 2.4 技术债

1. 双库分离 → v3 要求统一 edge.db
2. LanceDB 为搜索必经路径 → v3 要求解耦
3. 索引时 AI 调用（caption/keywords/embedding）→ v3 要求索引时零 AI
4. SemanticSnapshot(LanceModel) → v3 需全新 response 模型

## 3. 设计 vs 实现 对齐度


| 维度        | 目标                   | 现状                | 对齐      |
| --------- | -------------------- | ----------------- | ------- |
| API 路径    | /v1/search           | /api/search       | 0%      |
| 查询参数      | 13 个                 | 2 个               | 15%     |
| 搜索算法      | FTS5 BM25            | hybrid 3-stage    | 0%      |
| DB schema | frames/ocr_text/accessibility/FTS5 | entries/ocr_fts   | 0%      |
| 排序        | BM25+timestamp       | vector+FTS+rerank | 0%      |
| 分页        | limit+offset+total   | 仅 limit           | 33%     |
| Response  | {data, pagination}   | flat list         | 0%      |
| **综合**    |                      |                   | **~8%** |
