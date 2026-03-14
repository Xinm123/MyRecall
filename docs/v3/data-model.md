---
status: draft
owner: pyw
last_updated: 2026-03-13
depends_on:
  - open_questions.md
references:
  - spec.md
  - gate_baseline.md
---

# MyRecall-v3 数据模型（SSOT）

> 本文件从 spec.md §3 提取，为数据模型的唯一事实源（SSOT）。

## 3. 数据模型（Edge SQLite，v3 主线 = OCR-only；AX schema seam 显式保留）

### 3.0.1 设计原则

| 原则 | 说明 |
|------|------|
| Edge 是唯一事实源 | 所有持久化表在 Edge 的 `edge.db`（单一 SQLite 文件），Host 只有 spool 文件 |
| 表名/字段名对齐 screenpipe | P1 主路径同名：`frames` / `ocr_text` / `frames_fts` / `ocr_text_fts`；`ocr_text_embeddings` 为 P2+ 可选实验表（同名保留，P1 不建） |
| 索引时零 AI 调用 | v3 主线仅存储 OCR raw text，不预计算 caption/keywords/fusion；accessibility 相关 schema 仅保留为 v4 seam |
| capture_id 全局幂等 | UUID v7（Host 生成），Edge 去重，贯穿全链路 |
| v3 全新起点 | 不做 v2 数据迁移 |

### 3.0.2 capture_id 生成规则

```
格式：UUID v7（RFC 9562）
生成方：Host（采集时生成）
特性：时间有序 + 全局唯一 + 无需中心协调
示例：019528a0-73c4-7abc-8def-1234567890ab
```

### 3.0.3 DDL（Edge SQLite）

#### Table 1: frames（对齐 screenpipe frames，vision-only 子集）

```sql
CREATE TABLE frames (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp             TIMESTAMP NOT NULL,
    app_name              TEXT DEFAULT NULL,
    window_name           TEXT DEFAULT NULL,
    browser_url           TEXT DEFAULT NULL,       -- P1: 不采集，保留为 NULL；P2+: 评估是否启用分层提取
    focused               BOOLEAN DEFAULT NULL,
    device_name           TEXT NOT NULL DEFAULT 'monitor_0',
    snapshot_path         TEXT DEFAULT NULL,       -- JPEG 快照路径（主链路，推荐 .jpg）
    capture_trigger       TEXT DEFAULT NULL,       -- 'idle'|'app_switch'|'manual'|'click' (P1); P2+: 'window_focus'|'typing_pause'|'scroll_stop'|'clipboard'|'visual_change'
    event_ts              TEXT DEFAULT NULL,       -- 触发时刻（UTC ISO8601），用于 capture_latency 计算
    accessibility_text    TEXT DEFAULT NULL,       -- v4 seam 预留（OQ-043）；v3 主线 OCR-only，不写入 accessibility_text；保留 DDL 避免 P2+ 重建表
    text_source           TEXT DEFAULT NULL,       -- v3 主线固定为 'ocr'（OQ-043）；'accessibility' 为 v4 预留 seam
    content_hash          TEXT DEFAULT NULL,       -- 预留字段；v3 主线不作为 payload 必填或 dedup 契约
    simhash               INTEGER DEFAULT NULL,    -- 感知哈希，近似重复检测

    -- v3 Edge-Centric 追加
    capture_id            TEXT NOT NULL UNIQUE,    -- UUID v7，Host 生成，幂等键
    image_size_bytes      INTEGER,
    ingested_at           TEXT NOT NULL
                          DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    status                TEXT NOT NULL DEFAULT 'pending',  -- 处理管线生命周期：'pending'|'processing'|'completed'|'failed'（P1-S1 的 processing 为 noop/轻量处理；P1-S3+ 启用 OCR processing）
    error_message         TEXT,
    retry_count           INTEGER DEFAULT 0,
    processed_at          TEXT
);

-- B-tree 索引（精确过滤 / 时间范围）
CREATE INDEX idx_frames_timestamp     ON frames(timestamp);
CREATE INDEX idx_frames_app_name      ON frames(app_name);
CREATE INDEX idx_frames_window_name   ON frames(window_name);
CREATE INDEX idx_frames_browser_url   ON frames(browser_url);
CREATE INDEX idx_frames_focused       ON frames(focused);
CREATE INDEX idx_frames_snapshot_path ON frames(snapshot_path)
    WHERE snapshot_path IS NOT NULL;
CREATE INDEX idx_frames_status        ON frames(status)
    WHERE status IN ('pending', 'processing', 'failed');
CREATE INDEX idx_frames_content_hash  ON frames(content_hash)
    WHERE content_hash IS NOT NULL;
CREATE INDEX idx_frames_event_ts      ON frames(event_ts)
    WHERE event_ts IS NOT NULL;
```

#### Table 2: ocr_text（对齐 screenpipe ocr_text，v3 主文本存储）

```sql
CREATE TABLE ocr_text (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    frame_id              INTEGER NOT NULL,
    text                  TEXT NOT NULL DEFAULT '',
    text_json             TEXT,                    -- bounding box JSON（可选）
    ocr_engine            TEXT,
    text_length           INTEGER DEFAULT 0,
    app_name              TEXT DEFAULT NULL,       -- 对齐 screenpipe，写入时从 CapturePayload 取值
    window_name           TEXT DEFAULT NULL,       -- 对齐 screenpipe，写入时从 CapturePayload 取值
    -- 注：与 frames.app_name/window_name 来源相同（同一 CapturePayload）；
    --     若 frames 行后续被修正，ocr_text 不联动更新（接受 drift，对齐 screenpipe 行为）。
    FOREIGN KEY (frame_id) REFERENCES frames(id) ON DELETE CASCADE
);

CREATE INDEX idx_ocr_text_frame_id ON ocr_text(frame_id);
```

#### Table 3: frames_fts（对齐 screenpipe frames_fts，FTS 全文语义过滤）

```sql
-- app_name/window_name/browser_url/focused 走主线 FTS 过滤；accessibility_text 列仅作前向兼容保留
-- 去掉 screenpipe 的 name 字段（v3 无 frames.name）
CREATE VIRTUAL TABLE frames_fts USING fts5(
    app_name,
    window_name,
    browser_url,
    focused,
    accessibility_text,
    id UNINDEXED,
    tokenize='unicode61'
);

-- INSERT 触发器
CREATE TRIGGER frames_ai AFTER INSERT ON frames BEGIN
    INSERT INTO frames_fts(id, app_name, window_name, browser_url, focused, accessibility_text)
    VALUES (
        NEW.id,
        COALESCE(NEW.app_name, ''),
        COALESCE(NEW.window_name, ''),
        COALESCE(NEW.browser_url, ''),
        COALESCE(NEW.focused, 0),
        COALESCE(NEW.accessibility_text, '')
    );
END;

-- UPDATE 触发器（清空字段时也必须同步，避免陈旧 token）
CREATE TRIGGER frames_au AFTER UPDATE ON frames BEGIN
    DELETE FROM frames_fts WHERE id = OLD.id;
    INSERT INTO frames_fts(id, app_name, window_name, browser_url, focused, accessibility_text)
    VALUES (
        NEW.id,
        COALESCE(NEW.app_name, ''),
        COALESCE(NEW.window_name, ''),
        COALESCE(NEW.browser_url, ''),
        COALESCE(NEW.focused, 0),
        COALESCE(NEW.accessibility_text, '')
    );
END;

-- DELETE 触发器
CREATE TRIGGER frames_ad AFTER DELETE ON frames BEGIN
    DELETE FROM frames_fts WHERE id = OLD.id;
END;
```

#### Table 4: ocr_text_fts（对齐 screenpipe）

```sql
-- 对齐 screenpipe：保留 app_name/window_name
-- 注：search_ocr() 的 ocr_text_fts MATCH 只传文字搜索词，不做列过滤；
--     app/window 过滤由 frames_fts 承担（选 C）。
--     保留两列的理由：FTS5 加列代价高（需 rebuild），预留未来列过滤扩展；当前无负面影响。
CREATE VIRTUAL TABLE ocr_text_fts USING fts5(
    text,
    app_name,
    window_name,
    frame_id UNINDEXED,
    tokenize='unicode61'
);

-- INSERT 触发器
-- 注：ocr_text 现有 app_name/window_name 列（对齐 screenpipe），直接取 NEW 值，无需 JOIN frames
CREATE TRIGGER ocr_text_ai AFTER INSERT ON ocr_text
WHEN NEW.text IS NOT NULL AND NEW.text != '' AND NEW.frame_id IS NOT NULL
BEGIN
    INSERT OR IGNORE INTO ocr_text_fts(frame_id, text, app_name, window_name)
    VALUES (
        NEW.frame_id,
        NEW.text,
        COALESCE(NEW.app_name, ''),
        COALESCE(NEW.window_name, '')
    );
END;

-- UPDATE 触发器（clear-safe：text 被清空时必须删除旧索引）
CREATE TRIGGER ocr_text_update AFTER UPDATE ON ocr_text BEGIN
    DELETE FROM ocr_text_fts WHERE frame_id = OLD.frame_id;
    INSERT INTO ocr_text_fts(frame_id, text, app_name, window_name)
    SELECT
        NEW.frame_id,
        NEW.text,
        COALESCE(NEW.app_name, ''),
        COALESCE(NEW.window_name, '')
    WHERE NEW.frame_id IS NOT NULL
      AND NEW.text IS NOT NULL
      AND NEW.text != '';
END;

-- DELETE 触发器
CREATE TRIGGER ocr_text_delete AFTER DELETE ON ocr_text BEGIN
    DELETE FROM ocr_text_fts WHERE frame_id = OLD.frame_id;
END;
```
#### Table 5: chat_messages（v3 独有）

```sql
CREATE TABLE chat_messages (
    id                    TEXT PRIMARY KEY,         -- UUID v4
    session_id            TEXT NOT NULL,
    role                  TEXT NOT NULL,            -- 'user'|'assistant'|'tool'
    content               TEXT NOT NULL,
    citations             TEXT,                     -- JSON 数组，frame_id 引用
    tool_calls            TEXT,                     -- JSON，tool use（P2+）
    model                 TEXT,
    latency_ms            INTEGER,
    created_at            TEXT NOT NULL
                          DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX idx_chat_session ON chat_messages(session_id, created_at);
```

#### ~~Table 6: ocr_text_embeddings~~ （P1 不建）

screenpipe migration 中存在此表，但主检索路径未使用（实验性保留）。v3 P1 Search 为纯 FTS5，**P1 不建此表**；P2+ 若有 embedding 需求，通过独立 migration 新增，且默认不进入线上主路径。

#### ~~Table 7: elements~~ （P1 不建）

screenpipe v0.3.160 新增 `elements` 表（migration `20260301000000`），将 OCR+AX 逐元素结构化存储（含 bbox、element_type、FTS5），与 `ocr_text` 并行双写。v3 P1 Search/Chat 均基于 `ocr_text` 全文，无逐元素消费者；**P1 不建此表**；P2+ 若需细粒度 UI 元素检索（如按钮/标签级定位），通过独立 migration 新增，并同步实现双写逻辑与 `/elements` API。

#### Table 8: accessibility（v4 reserved seam，P0 建表保留）

screenpipe 中 `accessibility` 表由独立 `ui_recorder` 树遍历器写入（`ui_recorder.rs:542-633`），与 `paired_capture` 完全独立。MyRecall v3 **OQ-043 决议后**：保留该表结构作为 v4 AX 恢复的 schema seam，但 **v3 OCR-only 主线代码完全不触碰此表**——不写入、不读取、不参与 Gate/检索/citation。

**v3 实施边界**：
- Migration 保留：DDL 完整保留（包括 triggers/indexes），确保 v4 恢复时无需重建 schema
- Runtime 隔离：v3 代码路径（capture → ingest → OCR → search → chat）完全不引用 `accessibility` 表
- Reserved fields：`frames.accessibility_text`、`frames.content_hash` 作为 API 预留字段保留，但 Edge 仅做透传存储（若 Host 上报），不作为 v3 主线处理依据

```sql
CREATE TABLE accessibility (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp             DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    app_name              TEXT NOT NULL,
    window_name           TEXT NOT NULL,
    text_content          TEXT NOT NULL,
    browser_url           TEXT,

    -- v3 增强（screenpipe 无以下两列；当前仅保留为 v4 seam）
    frame_id              INTEGER DEFAULT NULL,    -- 未来 AX path 启用时可精确关联 frames.id
    focused               BOOLEAN DEFAULT NULL,    -- 未来 AX path 启用时支持 focused/browser_url 过滤

    FOREIGN KEY (frame_id) REFERENCES frames(id) ON DELETE SET NULL
);

-- v3 主线说明：当前不对 accessibility 表写入；v3 P1 验收需检查该表保持空状态（SQL: `SELECT COUNT(*) FROM accessibility` = 0）。若 v4 恢复 AX path，再启用 paired_capture / walker 写入约束。

-- B-tree 索引（对齐 screenpipe migration lines 22-27 + v3 追加）
CREATE INDEX idx_accessibility_timestamp  ON accessibility(timestamp);
CREATE INDEX idx_accessibility_app_name   ON accessibility(app_name);
CREATE INDEX idx_accessibility_frame_id   ON accessibility(frame_id)
    WHERE frame_id IS NOT NULL;
CREATE INDEX idx_accessibility_focused    ON accessibility(focused)
    WHERE focused IS NOT NULL;
```

**v3 主线语义**：
- v3 OCR-only 主线仅写 `frames` + `ocr_text`；`text_source` 在活跃路径上仅允许 `'ocr'`。
- `accessibility` 表、`accessibility.frame_id`、`accessibility.focused` 均保留为 v4 seam，不参与 v3 主线 Gate、检索或 citation。
- 若 v4 恢复 AX path，再重新定义 `text_source='accessibility'`、paired_capture 与 walker 共存的终态不变量。

#### Table 9: accessibility_fts（v4 reserved seam，FTS 结构保留）

```sql
CREATE VIRTUAL TABLE accessibility_fts USING fts5(
    text_content,
    app_name,
    window_name,
    browser_url,
    content='accessibility',
    content_rowid='id',
    tokenize='unicode61'
);

-- INSERT 触发器
CREATE TRIGGER accessibility_ai AFTER INSERT ON accessibility BEGIN
    INSERT INTO accessibility_fts(rowid, text_content, app_name, window_name, browser_url)
    VALUES (
        NEW.id,
        COALESCE(NEW.text_content, ''),
        COALESCE(NEW.app_name, ''),
        COALESCE(NEW.window_name, ''),
        COALESCE(NEW.browser_url, '')
    );
END;

-- UPDATE 触发器
CREATE TRIGGER accessibility_au AFTER UPDATE ON accessibility BEGIN
    INSERT INTO accessibility_fts(accessibility_fts, rowid, text_content, app_name, window_name, browser_url)
    VALUES ('delete', OLD.id, OLD.text_content, OLD.app_name, OLD.window_name, OLD.browser_url);
    INSERT INTO accessibility_fts(rowid, text_content, app_name, window_name, browser_url)
    VALUES (
        NEW.id,
        COALESCE(NEW.text_content, ''),
        COALESCE(NEW.app_name, ''),
        COALESCE(NEW.window_name, ''),
        COALESCE(NEW.browser_url, '')
    );
END;

-- DELETE 触发器
CREATE TRIGGER accessibility_ad AFTER DELETE ON accessibility BEGIN
    INSERT INTO accessibility_fts(accessibility_fts, rowid, text_content, app_name, window_name, browser_url)
    VALUES ('delete', OLD.id, OLD.text_content, OLD.app_name, OLD.window_name, OLD.browser_url);
END;
```

**注**：`accessibility_fts` 使用 `content='accessibility'` + `content_rowid='id'`（content-sync 模式，对齐 screenpipe migration lines 30-37）。trigger 使用 delete command 而非 DELETE FROM（FTS5 content-sync 要求）。v3 保留该结构仅作为 v4 AX seam；当前主线不依赖 `accessibility_fts` 提供查询能力。

**FTS 清空一致性契约（P1 强制）**：以 API/数据契约为 SSOT，`app_name/window_name/browser_url/focused/accessibility_text/text` 任一字段从非空更新为 `NULL/''` 后，旧 token 必须在同一事务内从 FTS 中移除，不得出现可检索陈旧命中。为满足该契约，v3 对 `frames_fts` 与 `ocr_text_fts` 的 UPDATE 触发器采用 `DELETE old + INSERT new(条件写入)` 的 clear-safe 模式，不复用 screenpipe 部分 migration 中的 `WHEN NEW.xxx != ''` 门控写法。

#### FTS 分工总结（v3 OCR-only 主线）

v3 主线只定义 OCR-only 检索：

| 过滤参数 | 走哪张表 | 方式 |
|---------|---------|------|
| `q`（文字搜索） | `ocr_text_fts` | `text MATCH ?` + BM25 排序 |
| `app_name` | `frames_fts` | `app_name:? MATCH` |
| `window_name` | `frames_fts` | `window_name:? MATCH` |
| `browser_url` | `frames_fts` | `browser_url:? MATCH` |
| `focused` | `frames_fts` | `focused:1 MATCH` |
| `start_time`/`end_time` | `frames` B-tree | `timestamp >= ? AND timestamp <= ?` |
| `min_length`/`max_length` | `ocr_text` | `text_length >= ? AND text_length <= ?` |

**注**：`ocr_text_fts` 保留 `app_name`/`window_name` 列（对齐 screenpipe），但当前查询路径不对这两列做 MATCH。预留 P2+ 列过滤扩展（FTS5 加列代价高，先建好）。

**v4 seam 说明**：`accessibility` / `accessibility_fts` / `search_accessibility()` / `search_all()` 相关结构保留在 schema 层，但不属于 v3 active contract；若未来恢复 AX path，再重新定义其查询路由与聚合行为。

#### FTS 查询规范化（对齐 screenpipe `text_normalizer`，D1=B）

##### sanitize_fts5_query（防注入，必须）

用户输入的 `q` 在构造 `ocr_text_fts MATCH ?` 前必须经过 sanitize：
- 按空白分词
- 每个 token 去除内部双引号后用 `"token"` 包裹
- 防止 FTS5 运算符（`OR`/`AND`/`NOT`/`*`/`(`/`)`/`:`/`.`）被误解释

```python
def sanitize_fts5_query(query: str) -> str:
    tokens = query.strip().split()
    return " ".join(f'"{t.replace(chr(34), "")}"' for t in tokens if t.replace('"', ''))
```

| 输入 | 输出 |
|------|------|
| `hello world` | `"hello" "world"` |
| `100.100.0.42` | `"100.100.0.42"` |
| `foo(bar)` | `"foo(bar)"` |
| `C++` | `"C++"` |

##### expand_search_query（OCR 黏连词拆分 + 前缀匹配，必须）

用于主搜索路径。对每个 token：
1. 驼峰拆分：`ActivityPerformance` → `Activity` + `Performance`
2. 数字边界拆分：`test123` → `test` + `123`
3. 每个部分生成 `"part"*` 前缀匹配子句
4. 多部分用 `OR` 连接

```python
def expand_search_query(query: str) -> str:
    # 对每个 word：
    #   拆分 → parts
    #   if len(parts) > 1: ("original"* OR "part1"* OR "part2"*)
    #   else: "word"*
    # 多 word 结果用 OR 连接并加括号
```

| 输入 | 输出 |
|------|------|
| `test` | `"test"*` |
| `proStart` | `("proStart"* OR "pro"* OR "Start"*)` |
| `test123` | `("test123"* OR "test"* OR "123"*)` |
| `hello world` | `("hello"* OR "world"*)` |

##### 调用时机

| 场景 | 用哪个函数 |
|------|-----------|
| `q` 非空 → `ocr_text_fts MATCH ?` | `sanitize_fts5_query(q)` |
| 元数据过滤（app_name/window_name/browser_url/focused）→ `frames_fts MATCH ?` | 直接构造列限定短语（同 screenpipe `search_ocr()`），不经过 expand |
| 未来 fuzzy_match 场景（P2+） | `expand_search_query(q)` 替代 `sanitize_fts5_query(q)` |

**注**：P1 主路径 `q` 使用 `sanitize_fts5_query`；`expand_search_query` 同步实现但默认不启用，作为 P2 fuzzy_match 的基础设施。

#### Search SQL JOIN 策略（v3 OCR-only）

v3 仅定义单一路径 OCR 搜索；API 主契约不暴露 `content_type=accessibility/all`。

##### 主路径：`search_ocr()`

对齐 screenpipe `search_ocr()` 的 OCR 检索思路，但在 v3 中它就是唯一 active path。

```sql
-- 骨架（无条件 INNER JOIN，对齐 screenpipe）
SELECT frames.*, ocr_text.text, ocr_text.text_length, ocr_text.ocr_engine
FROM frames
INNER JOIN ocr_text ON frames.id = ocr_text.frame_id
{frame_fts_join}   -- 仅 app/window/browser/focused 非空时追加
{ocr_fts_join}     -- 仅 q 非空时追加
WHERE 1=1
    {frame_fts_condition}
    {ocr_fts_condition}
    AND (? IS NULL OR frames.timestamp >= ?)
    AND (? IS NULL OR frames.timestamp <= ?)
    AND (? IS NULL OR ocr_text.text_length >= ?)
    AND (? IS NULL OR ocr_text.text_length <= ?)
ORDER BY {order_clause}
LIMIT ? OFFSET ?
```

| 条件 | `frame_fts_join` | `ocr_fts_join` | `order_clause` |
|------|-----------------|----------------|----------------|
| `q` 空，无 app/window/browser/focused | 无 | 无 | `frames.timestamp DESC` |
| `q` 空，有 app/window/browser/focused | `JOIN frames_fts ON frames.id = frames_fts.id` | 无 | `frames.timestamp DESC` |
| `q` 非空，无 app/window/browser/focused | 无 | `JOIN ocr_text_fts ON ocr_text.frame_id = ocr_text_fts.frame_id` | `ocr_text_fts.rank, frames.timestamp DESC` |
| `q` 非空，有 app/window/browser/focused | `JOIN frames_fts ON frames.id = frames_fts.id` | `JOIN ocr_text_fts ON ocr_text.frame_id = ocr_text_fts.frame_id` | `ocr_text_fts.rank, frames.timestamp DESC` |

**INNER JOIN 语义**：`status = 'pending'/'processing'/'failed'` 的帧，`ocr_text` 行尚不存在，自然不出现在搜索结果。v3 active path 中 `completed` 帧应通过 `ocr_text` 完成检索暴露。

**注**：screenpipe 明确注释"Avoid LEFT JOIN ocr_text — it forces a scan of the entire ocr_text"（db.rs line 3133）。v3 主搜索路径遵循同样规则，不在主路径使用 LEFT JOIN `ocr_text`。

#### COUNT 查询（v3 OCR-only，D3=A）

`pagination.total` 通过单路径 `count_search_ocr()` 获得：

```sql
SELECT COUNT(DISTINCT frames.id)
FROM frames
INNER JOIN ocr_text ON frames.id = ocr_text.frame_id
{frame_fts_join}
{ocr_fts_join}
WHERE 1=1
    {frame_fts_condition}
    {ocr_fts_condition}
    AND (? IS NULL OR frames.timestamp >= ?)
    AND (? IS NULL OR frames.timestamp <= ?)
    AND (? IS NULL OR ocr_text.text_length >= ?)
    AND (? IS NULL OR ocr_text.text_length <= ?)
```

**性能兜底**：`idx_frames_timestamp` B-tree 索引覆盖主过滤维度；100k 行级别 COUNT 预期 < 50ms（TBD-03 待实现后 benchmark 验证）。

**P1 不实现搜索缓存**（D2=A），COUNT 每次实时计算。P2 引入 LRU 缓存时 COUNT 结果一并缓存。

### 3.0.4 screenpipe 对齐映射

| screenpipe 字段 | v3 字段 | 表 | 对齐 |
|----------------|---------|-----|------|
| `frames.id` (auto-int) | `frames.id` (auto-int) | frames | 100% |
| `frames.timestamp` | `frames.timestamp` | frames | 100% |
| `frames.app_name` | `frames.app_name` | frames | 100% |
| `frames.window_name` | `frames.window_name` | frames | 100% |
| `frames.browser_url` | `frames.browser_url` | frames | 100% |
| `frames.focused` | `frames.focused` | frames | 100% |
| `frames.device_name` | `frames.device_name` | frames | 100% |
| `frames.snapshot_path` | `frames.snapshot_path` | frames | 100% |
| `frames.capture_trigger` | `frames.capture_trigger` | frames | 100% |
| `frames.accessibility_text` | `frames.accessibility_text` | frames | schema 保留；v3 主线不写入 |
| `frames.text_source` | `frames.text_source` | frames | v3 主线仅 `'ocr'`；`'accessibility'` 为预留值 |
| `frames.content_hash` | `frames.content_hash` | frames | schema 保留；v3 主线不作为 active payload/dedup 契约 |
| `frames.simhash` | `frames.simhash` | frames | 100% |
| `ocr_text.frame_id` | `ocr_text.frame_id` | ocr_text | 100% |
| `ocr_text.text` | `ocr_text.text` | ocr_text | 100% |
| `ocr_text.text_json` | `ocr_text.text_json` | ocr_text | 100% |
| `ocr_text.ocr_engine` | `ocr_text.ocr_engine` | ocr_text | 100% |
| `ocr_text.text_length` | `ocr_text.text_length` | ocr_text | 100% |
| `ocr_text.app_name` | `ocr_text.app_name` | ocr_text | 100% |
| `ocr_text.window_name` | `ocr_text.window_name` | ocr_text | 100% |
| `frames_fts` 6 indexed 列（name/browser_url/app_name/window_name/focused/accessibility_text） | `frames_fts` 5 indexed 列（去掉 `name`） | FTS | 有意偏离：v3 无视频 chunk，`frames.name` 不建；且 UPDATE trigger 采用 clear-safe `DELETE+INSERT`，保证字段清空后无陈旧索引命中 |
| `ocr_text_fts` 3 indexed 列 | `ocr_text_fts` 3 indexed 列 | FTS | 列级 100%；UPDATE trigger 增强为 clear-safe `DELETE+条件 INSERT`（字段清空后删除旧索引） |
| `accessibility.id` | `accessibility.id` | accessibility | schema 保留；v3 主线不写入 |
| `accessibility.timestamp` | `accessibility.timestamp` | accessibility | schema 保留；v3 主线不写入 |
| `accessibility.app_name` | `accessibility.app_name` | accessibility | schema 保留；v3 主线不写入 |
| `accessibility.window_name` | `accessibility.window_name` | accessibility | schema 保留；v3 主线不写入 |
| `accessibility.text_content` | `accessibility.text_content` | accessibility | schema 保留；v3 主线不写入 |
| `accessibility.browser_url` | `accessibility.browser_url` | accessibility | schema 保留；v3 主线不写入 |
| *(无)* | `accessibility.frame_id` | accessibility | v4 seam（未来恢复 AX path 时用于精确关联） |
| *(无)* | `accessibility.focused` | accessibility | v4 seam（未来 AX path 时支持 focused/browser_url 过滤） |
| `accessibility_fts` 3 indexed 列 | `accessibility_fts` 4 indexed 列（+browser_url） | FTS | schema 保留；v3 主线不查询 |
| `ocr_text_embeddings` | `ocr_text_embeddings` | embeddings | P2+ 可选（P1 不建） |
| `frames.video_chunk_id` | *(不适用)* | — | v3 无视频录制 |
| `frames.name` (= video file path) | *(不适用)* | — | v3 无视频 chunk；screenpipe 全栈暴露但零实际消费者使用（TBD-02 核查结论） |
| `frames.sync_id/machine_id` | *(Post-P3)* | — | v3 当前单 Host |

### 3.0.5 v3 追加字段（非 screenpipe 对齐，Edge-Centric 必需）

| 字段 | 表 | 用途 |
|------|-----|------|
| `capture_id` | frames | UUID v7 幂等去重键（Host→Edge 传输） |
| `event_ts` | frames | 触发时刻（Host 端 UTC ISO8601），用于 `capture_latency_ms = (ingested_at - event_ts) * 1000` 计算 |
| `image_size_bytes` | frames | 传输与存储管理 |
| `ingested_at` | frames | 入库时间戳（Edge receipt time）：用于 TTS 测量、`GET /v1/health` 的 stale 判定、以及 `oldest_pending_ingested_at` 观测口径 |
| `status` | frames | 处理队列状态机（PENDING→PROCESSING→COMPLETED/FAILED） |
| `error_message` | frames | 处理失败原因 |
| `retry_count` | frames | 重试计数 |
| `processed_at` | frames | 处理完成时间 |
| `chat_messages` 全表 | — | v3 Chat 一等能力（screenpipe 无等价表） |

### 3.0.6 Host 上传 Payload

#### Capture 时序参数契约（配置层，不入 Payload）

| 参数 | 单位 | P1 默认 | 语义 | 兼容规则 |
|---|---|---:|---|---|
| `min_capture_interval_ms` | ms | 1000 | 全触发共享最小间隔去抖（有意偏离：screenpipe Performance 200ms；P1 采用 Python 安全起点） | — |
| `idle_capture_interval_ms` | ms | 30000 | 无事件时触发 `idle` fallback 的最大空窗 | — |
| `trigger_queue_capacity` | — | 64 | 触发事件通道容量（有界队列）；与 screenpipe 对齐 | 环境变量 `OPENRECALL_TRIGGER_QUEUE_CAPACITY` 可覆盖 |
| `OPENRECALL_CAPTURE_INTERVAL` | s | legacy | 兼容输入，不作为 P1 主触发机制定义 | 仅当未显式设置 `idle_capture_interval_ms` 时，映射为 `idle_capture_interval_ms = OPENRECALL_CAPTURE_INTERVAL * 1000` |

- 优先级：`idle_capture_interval_ms`（显式） > `OPENRECALL_CAPTURE_INTERVAL` 映射 > `idle_capture_interval_ms` 默认值 `30000`。
- 对齐说明：参数名、单位与默认值对齐 screenpipe 运行时代码口径（`idle_capture_interval_ms=30000`）。

```python
class CapturePayload(BaseModel):
    """Host → Edge 上传的单条 capture 数据。
    
    注：此为 API 契约层 definition。Host 端内部 metadata 结构略有不同：
    - API payload 的 `timestamp` 类型为 float（UNIX epoch 秒）
    - Host 端 metadata 的 `timestamp` 为 ISO8601 字符串（由 `utc_now_iso()` 生成）
    - 服务端在 `claim_frame()` 时将 ISO8601 字符串写入 `frames.timestamp`
    """
    capture_id: str                    # UUID v7, Host 生成
    event_ts: Optional[str] = None     # 触发时刻（UTC ISO8601），观测字段；缺失不阻断 ingest
    timestamp: float                   # UNIX epoch 秒（API 契约）；Host 端实际使用 ISO8601 字符串
    app_name: Optional[str] = None
    window_name: Optional[str] = None
    browser_url: Optional[str] = None
    device_name: str = "monitor_0"  # 屏幕标识，格式: monitor_{id}
    focused: Optional[bool] = True
    capture_trigger: str  # P1-S2a+ 新上报必填: "idle" | "app_switch" | "manual" | "click"；P2+ 追加 "window_focus" | "typing_pause" | "scroll_stop" | "clipboard" | "visual_change"
    accessibility_text: Optional[str] = None   # reserved compatibility field；v3 主线可省略
    content_hash: Optional[str] = None         # reserved compatibility field；v3 主线可省略
    simhash: Optional[int] = None         # 感知哈希，用于近似重复检测
    # image_data: 通过 multipart/form-data 的 file 字段传输
```

**字段验证规则：**

| 字段 | 类型约束 | 必填 | 验证规则 |
|------|----------|------|---------|
| `capture_id` | string | ✅ | UUID v7 格式；重复时返回 `HTTP 200 + status=already_exists`（幂等成功） |
| `event_ts` | string｜null | ❌（P1-S2a+ 观测字段，建议提供） | UTC ISO8601；用于 `capture_latency_ms = (frames.ingested_at - event_ts) * 1000`；缺失/非法或晚于入库时刻（负延迟）时 ingest 可继续成功，但该样本不得进入 `capture_latency_p95` 分位统计，并计入观测异常计数 |
| `timestamp` | float | ✅ | UNIX epoch 秒；不得早于当前时间 30 天，不得晚于当前时间 60 秒 |
| `device_name` | string | ✅ | 非空，最长 128 字符，格式: `monitor_{id}`，与 screenpipe vision-only 对齐 |
| `app_name` | string｜null | ❌ | 最长 256 字符 |
| `window_name` | string｜null | ❌ | 最长 512 字符 |
| `browser_url` | string｜null | ❌ | 若非 null 则必须为合法 URL；最长 2048 字符 |
| `capture_trigger` | string | ✅（P1-S2a+ 新上报） | P1 枚举：`"idle"` / `"app_switch"` / `"manual"` / `"click"`；P2+ 追加：`"window_focus"` / `"typing_pause"` / `"scroll_stop"` / `"clipboard"` / `"visual_change"`；`window_focus` 按 screenpipe `capture_window_focus` 语义对齐（默认关闭，高频时按需开启）；缺失/null/非法值→ `INVALID_PARAMS` |
| `accessibility_text` | string｜null | ❌ | reserved compatibility field；若提供则必须为 string 或 `null`；v3 主线不要求上报 |
| `content_hash` | string｜null | ❌ | reserved compatibility field；若提供则必须为 `sha256:` 前缀 + 64 位十六进制或 `null`；v3 主线不要求上报 |
| `simhash` | int｜null | ❌ | 若非 null 则必须为非负 64 位整数 |
| `image_data` | multipart file | ✅ | JPEG（`image/jpeg`）主契约；兼容模式可接收 PNG/WebP，但入库前统一转码为 JPEG；最大 10MB；缺失→ `INVALID_PARAMS` |

**Reserved compatibility 字段语义（v3）**：
- `accessibility_text` / `content_hash` 不属于 v3 OCR-only 主线路径必填项。
- 若发送端为了兼容或实验仍上报这两个字段，Edge 仅做结构校验并按原值存储；不得将其视为 v3 主线 Gate、processing 或 search 的前提。
- `accessibility_text` 若提供，允许为 string 或 `null`；`content_hash` 若提供，允许为 `sha256:[0-9a-f]{64}` 或 `null`。
- `content_hash` 的具体来源与 canonicalization 规则在 v3 不作为 active contract 固化；若 v4 恢复 AX / content-based dedup，再单独收口。

**上下文字段一致性契约（P1-S2b 及后续阶段）**：
- P1 active `focused_context = {app_name, window_name}`：表示同一 capture 的 focused UI 上下文；`browser_url` 在 P1 为 reserved/NULL。
- `capture_device_binding = {device_name}`：表示该次 capture cycle 中实际被截取的 monitor。
- `app_name/window_name` 若提供，必须由同一轮 focused-context snapshot 一次性产出；禁止字段级混拼。
- `browser_url` 若未来恢复采集，必须与 focused_context 校验一致；若无法确认一致性或命中 stale 检测，必须写 `null`。
- `device_name` 必须与实际截图 monitor 一致；它要求 same-cycle coherence，不承担同源 focused-context 语义。
- **非焦点显示器帧**：采集时若无法确定当前显示的 app/window（例如非活动显示器），`app_name` 与 `window_name` 必须写入 `null`。
- **严禁复用**：禁止复用该 monitor 历史看到的旧 app/window 记录作为当前真相。
- 不确定时遵循：`Better None than wrong window`；`browser_url` 的 `Better None than wrong URL` 语义保留给 P2+/v4。
- **优先规则**：`routing_filtered` 优先级最高，直接导致系统不产生持久化帧或 Payload 样本；非焦点 `null`仅在 capture 发生时适用于 payload 字段内容。
- **过滤结果**：当触发器路由至已禁用的显示器（`routing_filtered`）时，系统不产生持久化帧或 Payload 样本。

**图片格式语义（P1）**：
- 主采集/主读取链路统一 JPEG：`POST /v1/ingest` 主契约 `image/jpeg`，`frames.snapshot_path` 持久化为 JPEG，`GET /v1/frames/:frame_id` 返回 `image/jpeg`。
- 若启用兼容输入并接收 PNG/WebP，Edge 在入库前统一转码为 JPEG，不改变读取契约。

**S2a 兼容边界（capture_trigger）**：
- API 语义：自 P1-S2a 起，`POST /v1/ingest` 对新上报 capture 强制要求 `capture_trigger`（不得缺失或为 null）。
- 存储语义：`frames.capture_trigger` 保持 `DEFAULT NULL`，仅用于承载 S1 历史数据与迁移过渡，不改变历史行。

**S2a 观测边界（event_ts）**：
- `event_ts` 是 latency 观测字段，不改变 ingest 幂等语义与 `frames` 写入语义。
- `event_ts` 缺失/非法不应阻断 ingest 成功路径，但该样本必须排除在 `capture_latency_p95` 统计之外。

**幂等语义：**
- `capture_id` 重复时，Edge 不重新处理，直接返回 `HTTP 200` + `{"status": "already_exists", ...}`（可附 `request_id`；不返回错误 `code`）。
- v3 active contract 中，`capture_id` 幂等是唯一强制去重语义；`content_hash` 若存在，仅作为保留字段，不改变 ingest 正确性定义。

**dedup 语义（v3）**：
- v3 不定义基于 `content_hash` 的 active dedup 契约；主线节流/去重依赖 S2a/S2b 的 trigger debounce、routing 与 capture coordination。
- `content_hash` 若存在，仅作为保留字段存储，不参与 Edge 侧判定，也不作为 v3 Gate 统计基础。
- 若后续重新引入 content-based dedup，需单独定义来源、canonicalization、空文本行为与 Host/Edge 边界。

**trigger / device binding 语义（P1-S2b）**：
- event source 仅发出 `capture_trigger`，不得绑定 `device_name`。
- `device_name` 必须由 monitor worker 在消费 trigger、执行实际截图时绑定。
- `primary_monitor_only` 仅影响启用的 monitor worker 集合，不改变 trigger 语义。

**device_name 字段说明**：

| 字段 | 说明 |
|------|------|
| 格式 | `monitor_{id}` |
| 语义 | 屏幕标识，对齐 screenpipe vision-only 场景 |

**取值规则**：

| 平台 | id 来源 | 示例 |
|------|---------|------|
| macOS | CGDirectDisplayID | `monitor_1`, `monitor_2` |
| Windows | unique_id (mss) | `monitor_MONITOR\0...` (取前16字符) |
| Linux | 坐标组合 (left_top) | `monitor_0_0`, `monitor_1920_0` |

**实现说明**：
- Host 端通过 `mss` 库 + ctypes 获取 OS 级别 monitor id
- macOS: 调用 `CGGetActiveDisplayList` 获取 CGDirectDisplayID
- Windows: 使用 mss 返回的 `unique_id` 字段
- Linux: 使用 monitor 坐标组合作为唯一标识
- Fallback: 若无法获取 OS 级别 id，则使用数组索引 (`monitor_0`, `monitor_1`)

**与 screenpipe 对齐**：
- 格式完全一致：`monitor_{id}`
- 语义完全一致：标识显示器
- vision-only 场景 100% 对齐

### 3.0.7 Migration 策略（Q3）

#### 机制：手写 SQL + `schema_migrations` 跟踪表

v3 不引入 Alembic（无 SQLAlchemy ORM 依赖），使用标准库 `sqlite3` + 手写迁移文件，风格对齐 screenpipe 的 sqlx migrate 命名规范。

```sql
-- 启动时自动创建，记录已执行的迁移
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,        -- YYYYMMDDHHMMSS，对齐 screenpipe 迁移文件命名
    description TEXT NOT NULL,
    applied_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);
```

#### 迁移文件规范

```
openrecall/server/database/migrations/
├── 20260227000001_initial_schema.sql    -- P1 完整初始表结构（本文件 §3.0.3 所有 DDL）
└── 20260227000002_add_embeddings.sql    -- P2+，新增 ocr_text_embeddings 表
```

- 文件名：`YYYYMMDDHHMMSS_描述.sql`，纯 UP migration（不写 DOWN）
- 每个文件只做一件事，原子操作
- 已执行的迁移文件**不得修改**（通过 `schema_migrations.version` 检测）

#### 启动时执行逻辑（伪代码）

```python
def run_migrations(conn: sqlite3.Connection, migrations_dir: Path) -> None:
    conn.execute(CREATE_SCHEMA_MIGRATIONS_SQL)
    applied = {row[0] for row in conn.execute("SELECT version FROM schema_migrations")}
    for sql_file in sorted(migrations_dir.glob("*.sql")):
        version = sql_file.stem.split("_")[0]
        if version not in applied:
            conn.executescript(sql_file.read_text())
            conn.execute(
                "INSERT INTO schema_migrations(version, description) VALUES (?, ?)",
                (version, sql_file.stem)
            )
    conn.commit()
```

#### P1→P2 已知迁移

| 版本 | 文件 | 内容 |
|------|------|------|
| 20260227000001 | `initial_schema.sql` | P1 全量 DDL（含 `accessibility` / `accessibility_fts` v4 reserved seam） |
| P2+ 时确定 | `add_embeddings.sql` | 新增 `ocr_text_embeddings` 表 |
