# screenpipe Search 事实基线（仅屏幕链路）

> 生成日期：2026-03-02
> 数据来源：screenpipe 代码库（/Users/pyw/old/screenpipe），截至 2026-03 在库版本
> 链路标记：仅屏幕（不含 audio/speaker）

## 1. API 层

### 1.1 GET /search（主搜索端点）

[E-01] 代码 | search.rs:36-76 | SearchQuery 结构体 | 仅屏幕 | H | 已核查

屏幕相关 Query Parameters：

| 参数 | 类型 | 默认 | 行为 |
|------|------|------|------|
| q | string | "" | FTS5 MATCH，空值返回全部 |
| content_type | enum | all | 设为 ocr 强制屏幕链路 |
| limit | u32 | 20 | 分页大小 |
| offset | u32 | 0 | 分页偏移 |
| start_time | ISO8601 | null | frames.timestamp >= ? |
| end_time | ISO8601 | null | frames.timestamp <= ? |
| app_name | string | null | 精确匹配 frames.app_name |
| window_name | string | null | 精确匹配 frames.window_name |
| browser_url | string | null | FTS token 序列匹配（自动强制 OCR 模式） |
| focused | bool | null | 焦点过滤（自动强制 OCR 模式） |
| include_frames | bool | false | 内嵌 base64 JPEG |
| min_length | usize | null | LENGTH(ocr_text.text) >= ? |
| max_length | usize | null | LENGTH(ocr_text.text) <= ? |
| frame_name | string | null | 帧名/视频文件路径模式匹配（零实际消费者使用） |

Response：`{ data: [{ type: "OCR", content: OCRContent }], pagination: { limit, offset, total }, cloud: {...} }`

OCRContent 字段：frame_id, text, timestamp, file_path, offset_index, app_name, window_name, tags, frame(base64?), frame_name, browser_url, focused, device_name

### 1.2 GET /search/keyword（高级搜索端点）

[E-03] 代码 | search.rs:362-441 | KeywordSearchRequest | 仅屏幕 | H | 已核查

独有能力：fuzzy_match（expand_search_query 驼峰拆分）、order（显式排序）、app_names（多 app 过滤）、group（按 app/window/时间聚类）。返回 `Vec<SearchMatch>` 含 text_positions（bbox）。

### 1.3 搜索缓存

[E-02] 代码 | search.rs:149-155 | LRU cache | 仅屏幕 | H | 已核查

基于全参数哈希的 LRU 缓存；`include_frames=true` 时禁用。

## 2. DB Schema

### 2.1 核心表

[E-04] 代码 | migrations/ | 核心表定义 | 仅屏幕 | H | 已核查

| 表 | 关键列 | 用途 |
|----|--------|------|
| frames | id, timestamp, app_name, window_name, browser_url, focused, device_name, snapshot_path, accessibility_text, content_hash, simhash, capture_trigger, text_source, name | 帧元数据 |
| ocr_text | frame_id FK, text, text_json, ocr_engine, text_length, app_name, window_name | OCR 文本+位置 |
| frames_fts (FTS5) | app_name, window_name, browser_url, focused, accessibility_text, name, id UNINDEXED; tokenize=unicode61 | 元数据全文索引 |
| ocr_text_fts (FTS5) | text, app_name, window_name, frame_id UNINDEXED; tokenize=unicode61 | OCR 文本全文索引 |
| elements | frame_id, source, role, text, parent_id, depth, bounds, confidence | 结构化 OCR/AX 层级 |
| elements_fts (FTS5) | text, role, frame_id UNINDEXED (content-sync) | 元素全文索引 |
| accessibility | id, timestamp, app_name, window_name, text_content, browser_url, sync_id, machine_id, synced_at | AX 树遍历器独立写入（ui_recorder） |
| accessibility_fts (FTS5) | text_content, app_name, window_name; content='accessibility', content_rowid='id', tokenize=unicode61 | AX 文本全文索引 |
| accessibility_tags | accessibility_id FK, tag_id FK | 标签关联 |

### 2.2 FTS 维护

[E-05] 代码 | migrations/20260224*.sql | 同步 INSERT 触发器 | 仅屏幕 | H | 已核查

同步 INSERT 触发器（~0.5-1ms/行）。历史上尝试后台批量索引器已回退。

### 2.3 B-tree 索引

[E-06] 代码 | migrations/20241103*.sql | 索引覆盖 | 仅屏幕 | H | 已核查

```
idx_frames_timestamp
idx_frames_app_name
idx_frames_window_name
idx_frames_browser_url
idx_frames_focused
idx_frames_snapshot_path
idx_frames_app_window
idx_frames_timestamp_device
idx_ocr_text_frame_id
idx_ocr_text_frame_app_window
```

## 3. 查询构造与排序

### 3.1 search_ocr()（OCR 搜索路径）

[E-07] 代码 | db.rs:2057-2210 | search_ocr() | 仅屏幕 | H | 已核查

条件 JOIN 策略（4 种组合）：

| q | 元数据过滤 | frame_fts_join | ocr_fts_join | ORDER BY |
|---|-----------|----------------|--------------|----------|
| 空 | 无 | 无 | 无 | timestamp DESC |
| 空 | 有 | JOIN frames_fts | 无 | timestamp DESC |
| 非空 | 无 | 无 | JOIN ocr_text_fts | ocr_text_fts.rank, timestamp DESC |
| 非空 | 有 | JOIN frames_fts | JOIN ocr_text_fts | ocr_text_fts.rank, timestamp DESC |

### 3.2 search_accessibility()（accessibility 搜索路径）

[E-25] 代码 | db.rs:3408-3483 | search_accessibility() | 仅屏幕 | H | 已核查

参数：query, app_name, window_name, start_time, end_time, limit, offset（**无 focused 参数**）。

条件 JOIN 策略（2 种组合）：

| q | fts_join | ORDER BY |
|---|---------|----------|
| 空 | 无（直接 FROM accessibility） | timestamp DESC |
| 非空 | JOIN accessibility_fts ON accessibility_fts.rowid = accessibility.id | timestamp DESC |

注：app_name/window_name 通过 FTS 列前缀查询（`app_name:"..."`）而非 B-tree WHERE。

LEFT JOIN frames（±1s 时间窗口）获取 file_path、offset_index、frame_name。

**limitation**：不接受 focused 参数 → 由 db.rs:1870-1872 在 focused/browser_url 存在时强制降级到 content_type=ocr。v3 通过 accessibility 表增加 focused 列修复此限制。

## 4. FTS 查询规范化

[E-08] 代码 | text_normalizer.rs | 仅屏幕 | H | 已核查

- **sanitize_fts5_query**：token 引号包裹，防运算符注入
- **expand_search_query**：驼峰/数字边界拆分 + 前缀匹配

## 5. 高级特性

[E-09] 代码 | db.rs:4218-4696 | 仅屏幕 | H | 已核查

| 特性 | 函数 | 说明 |
|------|------|------|
| 文本位置+bbox | search_with_text_positions() | text_json 像素坐标 |
| 结果聚类 | cluster_search_matches() | app/window/120s 聚类 |
| 轻量分组 | search_for_grouping() | 跳过 OCR blob，max_per_app=30 |
| 自过滤 | search.rs:212-218 | 排除 app_name 含 screenpipe |
| COUNT | count_search_results() | 独立 COUNT(DISTINCT frames.id) |

## 6. DB 运行时配置

[E-10] 代码 | db.rs | 仅屏幕 | H | 已核查

```
journal_mode = WAL
synchronous = NORMAL
cache_size = -64000 (64MB)
mmap_size = 268435456 (256MB)
temp_store = MEMORY
wal_autocheckpoint = 4000
busy_timeout = 5s
pool: max=30, min=5
write_semaphore: 单 permit 应用级写串行化
```

## 7. 向量搜索（屏幕链路）

[E-11] 代码 | migrations/20250117*.sql | 仅屏幕 | H | 已核查

`ocr_text_embeddings` 表已建但 `search_ocr()` 不使用。屏幕链路搜索 = 纯 FTS5。
