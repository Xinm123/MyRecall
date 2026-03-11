---
status: draft
owner: pyw
last_updated: 2026-03-03
depends_on:
  - open_questions.md
references:
  - spec.md
  - gate_baseline.md
---

# MyRecall-v3 数据模型（SSOT）

> 本文件从 spec.md §3 提取，为数据模型的唯一事实源（SSOT）。

## 3. 数据模型（Edge SQLite，主路径对齐 screenpipe vision-only，差异显式）

### 3.0.1 设计原则

| 原则 | 说明 |
|------|------|
| Edge 是唯一事实源 | 所有持久化表在 Edge 的 `edge.db`（单一 SQLite 文件），Host 只有 spool 文件 |
| 表名/字段名对齐 screenpipe | P1 主路径同名：`frames` / `ocr_text` / `frames_fts` / `ocr_text_fts`；`ocr_text_embeddings` 为 P2+ 可选实验表（同名保留，P1 不建） |
| 索引时零 AI 调用 | 仅存储 OCR raw text + accessibility text，不预计算 caption/keywords/fusion（与 screenpipe 一致） |
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
    browser_url           TEXT DEFAULT NULL,
    focused               BOOLEAN DEFAULT NULL,
    device_name           TEXT NOT NULL DEFAULT 'monitor_0',
    snapshot_path         TEXT DEFAULT NULL,       -- JPEG 快照路径（主链路，推荐 .jpg）
    capture_trigger       TEXT DEFAULT NULL,       -- 'idle'|'app_switch'|'manual'|'click' (P1); P2+: 'window_focus'|'typing_pause'|'scroll_stop'|'clipboard'|'visual_change'
    event_ts              TEXT DEFAULT NULL,       -- 触发时刻（UTC ISO8601），用于 capture_latency 计算
    accessibility_text    TEXT DEFAULT NULL,
    text_source           TEXT DEFAULT NULL,       -- 'ocr'|'accessibility'
    content_hash          TEXT DEFAULT NULL,       -- sha256:hex，Host dedup 判定后上传
    simhash               INTEGER DEFAULT NULL,    -- 感知哈希，近似重复检测

    -- v3 Edge-Centric 追加
    capture_id            TEXT NOT NULL UNIQUE,    -- UUID v7，Host 生成，幂等键
    image_size_bytes      INTEGER,
    ingested_at           TEXT NOT NULL
                          DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    status                TEXT NOT NULL DEFAULT 'pending',  -- 处理管线生命周期：'pending'|'processing'|'completed'|'failed'（P1-S1 的 processing 为 noop/轻量处理；P1-S3+ 启用 AX-first/OCR-fallback）
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

#### Table 2: ocr_text（对齐 screenpipe ocr_text，仅 OCR-fallback 帧写入）

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
-- app_name/window_name/browser_url/focused/accessibility_text 走 FTS 全文语义（选 C）
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

#### Table 8: accessibility（Scheme C，P0 建表，对齐 screenpipe migration 20250202000000 + v3 增强）

screenpipe 中 `accessibility` 表由独立 `ui_recorder` 树遍历器写入（`ui_recorder.rs:542-633`），与 `paired_capture` 完全独立。v3 Scheme C 下，`paired_capture` 在 AX 成功时写入此表（代替 `ocr_text`），未来 P1+ 可增加独立 walker 管线。

```sql
CREATE TABLE accessibility (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp             DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    app_name              TEXT NOT NULL,
    window_name           TEXT NOT NULL,
    text_content          TEXT NOT NULL,
    browser_url           TEXT,

    -- v3 增强（screenpipe 无以下两列）
    frame_id              INTEGER DEFAULT NULL,    -- paired_capture 写入时填入 frames.id；独立 walker 写入时留 NULL
    focused               BOOLEAN DEFAULT NULL,    -- P0 修复：screenpipe accessibility 表无此列，导致 focused/browser_url 搜索强制降级到 OCR（db.rs:1870-1872）

    FOREIGN KEY (frame_id) REFERENCES frames(id) ON DELETE SET NULL
);

-- P1 阶段约束：正常 paired_capture 路径写入的 accessibility 行，frame_id 应为非 NULL，并通过外键精确关联截图；该约束在 P2+ 引入独立 walker 后失效。

-- B-tree 索引（对齐 screenpipe migration lines 22-27 + v3 追加）
CREATE INDEX idx_accessibility_timestamp  ON accessibility(timestamp);
CREATE INDEX idx_accessibility_app_name   ON accessibility(app_name);
CREATE INDEX idx_accessibility_frame_id   ON accessibility(frame_id)
    WHERE frame_id IS NOT NULL;
CREATE INDEX idx_accessibility_focused    ON accessibility(focused)
    WHERE focused IS NOT NULL;
```

**写入语义（Scheme C）**：
- AX 成功 → `frames` 行（`text_source='accessibility'`）+ `accessibility` 行（`frame_id` = 对应 `frames.id`）+ **无 `ocr_text` 行**
- AX 失败/OCR fallback → `frames` 行（`text_source='ocr'`）+ `ocr_text` 行 + **无 `accessibility` 行**

**终态不变量（P1-S3 Gate 约束）**：
- `text_source='accessibility'` 的完成帧必须满足：`accessibility.frame_id = frames.id` 存在，且不存在该 `frame_id` 的 `ocr_text` 行。
- `text_source='ocr'` 的完成帧必须满足：存在该 `frame_id` 的 `ocr_text` 行，且 paired_capture 路径下不存在对应 `accessibility` 行。
- 当 AX 不可用且 OCR 失败时，帧状态必须为 `failed`；不得将空/不可用 AX 文本误标为 `text_source='accessibility'`。
- 上述 `text_source` / 分表语义均属于 P1-S3 完成态契约；P1-S2b 的 `content_hash` coverage 不得以这些终态字段作为分母。

**AX 不可用（ax_unusable）定义**：
- AX 遍历报错；或
- AX 超时且已收集文本归一化后为空；或
- AX 成功返回但 `TRIM(COALESCE(accessibility_text, '')) = ''`。

**S2b raw coverage 口径（P1-S2b）**：
- `ax_hash_eligible = TRIM(COALESCE(accessibility_text, '')) <> ''` 的已上传帧。
- `content_hash` coverage 的分母仅使用 `ax_hash_eligible`，不使用 `frames.text_source`。
- 空 AX 文本帧必须上传并可追溯，但不进入该 coverage 分母。

**P0 修复说明**：screenpipe `search_accessibility()` 不接受 `focused` 参数（`db.rs:3408-3416`），`focused`/`browser_url` 存在时强制降级到 `content_type=ocr`（`db.rs:1870-1872`）。在 AX-first 模式下 ~90%+ 帧无 `ocr_text` 行，`search_ocr()` 用 `INNER JOIN ocr_text` 会漏掉这些帧。v3 通过在 `accessibility` 表增加 `focused` 列并让 `search_accessibility()` 支持过滤，修复此限制。

#### Table 9: accessibility_fts（基于 screenpipe + browser_url 增强，FTS 全文检索）

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

**注**：`accessibility_fts` 使用 `content='accessibility'` + `content_rowid='id'`（content-sync 模式，对齐 screenpipe migration lines 30-37）。trigger 使用 delete command 而非 DELETE FROM（FTS5 content-sync 要求）。v3 `accessibility_fts` 比 screenpipe 多一列 `browser_url`（screenpipe 仅 `text_content, app_name, window_name` 3 列），此为有意偏离——确保 `browser_url` 参数在所有 `content_type` 路径下统一为 FTS token 序列匹配语义。

**FTS 清空一致性契约（P1 强制）**：以 API/数据契约为 SSOT，`app_name/window_name/browser_url/focused/accessibility_text/text` 任一字段从非空更新为 `NULL/''` 后，旧 token 必须在同一事务内从 FTS 中移除，不得出现可检索陈旧命中。为满足该契约，v3 对 `frames_fts` 与 `ocr_text_fts` 的 UPDATE 触发器采用 `DELETE old + INSERT new(条件写入)` 的 clear-safe 模式，不复用 screenpipe 部分 migration 中的 `WHEN NEW.xxx != ''` 门控写法。

#### FTS 分工总结

**注**：Scheme C（025A）引入 `content_type` 参数路由。以下按路径分表说明。

##### `content_type=ocr`（search_ocr 路径）

| 过滤参数 | 走哪张表 | 方式 |
|---------|---------|------|
| `q`（文字搜索） | `ocr_text_fts` | `text MATCH ?` + BM25 排序 |
| `app_name` | `frames_fts` | `app_name:? MATCH` |
| `window_name` | `frames_fts` | `window_name:? MATCH` |
| `browser_url` | `frames_fts` | `browser_url:? MATCH` |
| `focused` | `frames_fts` | `focused:1 MATCH` |
| `start_time`/`end_time` | `frames` B-tree | `timestamp >= ? AND timestamp <= ?` |
| `min_length`/`max_length` | `ocr_text` | `text_length >= ? AND text_length <= ?` |

##### `content_type=accessibility`（search_accessibility 路径）

| 过滤参数 | 走哪张表 | 方式 |
|---------|---------|------|
| `q`（文字搜索） | `accessibility_fts` | `text_content MATCH ?` + BM25 排序 |
| `app_name` | `accessibility` | `app_name = ?`（B-tree 精确匹配） |
| `window_name` | `accessibility` | `window_name = ?`（B-tree 精确匹配） |
| `browser_url` | `accessibility_fts` | `browser_url:? MATCH`（FTS token 序列匹配，对齐 search_ocr 路径语义） |
| `focused` | `accessibility` | `focused = ?`（B-tree 精确匹配，**v3 P0 修复**，screenpipe 不支持） |
| `start_time`/`end_time` | `accessibility` B-tree | `timestamp >= ? AND timestamp <= ?` |
| `min_length`/`max_length` | — | 不适用（accessibility 行无 `text_length` 列） |

##### `content_type=all`（search_all 路径，默认）

并行执行 `search_ocr()` + `search_accessibility()`，结果按 `timestamp DESC` 合并。各路径内部路由同上。

##### 路由规则

当 `q` 为空时（search_ocr 路径）：只 JOIN `frames_fts`（若有 app/window/browser/focused 条件），ORDER BY `frames.timestamp DESC`。
当 `q` 非空时（search_ocr 路径）：JOIN `ocr_text_fts`（必须，MATCH 只传文字搜索词），按需 JOIN `frames_fts`，ORDER BY `ocr_text_fts.rank, frames.timestamp DESC`。
当 `q` 为空时（search_accessibility 路径）：B-tree 过滤（app_name/window_name/focused/timestamp）；若有 `browser_url` 条件则 JOIN `accessibility_fts`（`browser_url:? MATCH`），ORDER BY `accessibility.timestamp DESC`。
当 `q` 非空时（search_accessibility 路径）：JOIN `accessibility_fts`（MATCH 传文字搜索词 + browser_url 列前缀（若有）），按需追加 B-tree 过滤（app_name/window_name/focused/timestamp），ORDER BY `accessibility_fts.rank, accessibility.timestamp DESC`。

**注**：`ocr_text_fts` 保留 `app_name`/`window_name` 列（对齐 screenpipe），但当前查询路径不对这两列做 MATCH。预留 P2+ 列过滤扩展（FTS5 加列代价高，先建好）。

**注**：v3 **不做** screenpipe 的 `focused/browser_url → force content_type=ocr` 降级（db.rs:1870-1872）。`focused` 过滤在 `search_accessibility()` 直接由 `accessibility.focused` 列支持（P0 修复，见 ADR-0012）。

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

#### Search SQL JOIN 策略（Scheme C 三路径分发，覆盖原 Q2 单路径）

Scheme C（025A）将搜索拆为三条独立路径，由 `content_type` 参数路由（对齐 screenpipe `ContentType` 枚举）。

##### 路径 1：`search_ocr()`（`content_type=ocr`）

对齐 screenpipe `search_ocr()`（db.rs:2117-2119），仅搜索 OCR fallback 帧。

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

**INNER JOIN 语义**：`status = 'pending'/'processing'/'failed'` 的帧，`ocr_text` 行尚不存在，自然不出现在搜索结果。AX 成功帧无 `ocr_text` 行，同样被 INNER JOIN 排除（正确行为——这些帧由 `search_accessibility()` 覆盖）。

##### 路径 2：`search_accessibility()`（`content_type=accessibility`）

对齐 screenpipe `search_accessibility()`（db.rs:3408-3483），搜索 AX 成功帧 + 独立 walker 数据。

```sql
SELECT a.id, a.text_content, a.timestamp, a.app_name, a.window_name,
       a.browser_url, a.focused, a.frame_id,
       f.snapshot_path, f.device_name
FROM accessibility a
LEFT JOIN frames f ON a.frame_id = f.id
{accessibility_fts_join}   -- q 非空或 browser_url 非空时追加
WHERE 1=1
    AND (? IS NULL OR a.app_name = ?)
    AND (? IS NULL OR a.window_name = ?)
    AND (? IS NULL OR a.focused = ?)
    AND (? IS NULL OR a.timestamp >= ?)
    AND (? IS NULL OR a.timestamp <= ?)
    {accessibility_fts_condition}
ORDER BY {order_clause}
LIMIT ? OFFSET ?
```

| 条件 | `accessibility_fts_join` | `accessibility_fts_condition` | `order_clause` |
|------|------------------------|-------------------------------|----------------|
| `q` 空 且无 `browser_url` | 无 | 无 | `a.timestamp DESC` |
| `q` 空 但有 `browser_url` | `JOIN accessibility_fts ON a.id = accessibility_fts.rowid` | `AND accessibility_fts MATCH 'browser_url:"..."'` | `a.timestamp DESC` |
| `q` 非空，无 `browser_url` | `JOIN accessibility_fts ON a.id = accessibility_fts.rowid` | `AND accessibility_fts MATCH ?`（text_content 列） | `accessibility_fts.rank, a.timestamp DESC` |
| `q` 非空，有 `browser_url` | `JOIN accessibility_fts ON a.id = accessibility_fts.rowid` | `AND accessibility_fts MATCH ?`（text_content + browser_url 列前缀组合） | `accessibility_fts.rank, a.timestamp DESC` |

**browser_url FTS 语义说明**：`browser_url` 过滤统一走 `accessibility_fts` 的 `browser_url:? MATCH`（FTS token 序列匹配），与 search_ocr 路径的 `frames_fts` `browser_url:? MATCH` 语义一致。v3 `accessibility_fts` 比 screenpipe 多一列 `browser_url`（screenpipe `accessibility_fts` 仅 3 列），此为有意偏离，确保 API 契约中 `browser_url` 参数在所有 `content_type` 路径下语义一致。

**browser_url NULL 行为**：触发器写入时 `COALESCE(NEW.browser_url, '')` 将 NULL 转为空串；FTS5 `unicode61` 对空串不产生 token，因此非浏览器 app 的 accessibility 行（`browser_url IS NULL`）不会被任何 `browser_url` 查询命中。这是**预期行为**：用户传 `browser_url` 过滤时，只应返回有 URL 的记录（浏览器 app 产生的 AX 数据）。实现者不应将此误判为 bug 并修改 COALESCE 逻辑。`content_type=all` 时 OCR 路径与 AX 路径各自独立过滤后合并，浏览器页面上的帧（AX 成功或 OCR fallback）均被覆盖，无遗漏。

**LEFT JOIN frames 说明**：`accessibility.frame_id` 为 `DEFAULT NULL`（方案 3）。`paired_capture` 写入的行有 `frame_id`，精确关联 frames；未来独立 walker 写入的行 `frame_id = NULL`，LEFT JOIN 返回 NULL 字段（`snapshot_path`/`device_name` 等为 NULL）。避免 screenpipe 的 ±1s 时间窗口 JOIN 模糊性。

**注**：screenpipe `search_accessibility()` 不接受 `focused` 参数（db.rs:3408-3483）。v3 `search_accessibility()` 支持 `focused` 过滤（P0 修复，见 ADR-0012），不做 screenpipe 的 `focused → force content_type=ocr` 降级。

##### 路径 3：`search_all()`（`content_type=all`，默认）

并行执行 `search_ocr()` + `search_accessibility()`，结果按 `timestamp DESC` 合并（Scheme C 写入语义保证两条路径结果集天然互斥——AX 成功帧无 `ocr_text` 行，OCR fallback 帧无 `accessibility` 行——无需去重）。

```python
def search_all(params: SearchQuery) -> SearchResult:
    # 过量拉取：各路径传 fetch_limit = limit + offset，offset = 0
    # 确保合并后全局排序窗口内的数据完整（对齐 screenpipe db.rs:1880, 2043-2050）
    fetch_limit = params.limit + params.offset
    ocr_results = search_ocr(params._replace(limit=fetch_limit, offset=0))
    ax_results = search_accessibility(params._replace(limit=fetch_limit, offset=0))
    # 合并 + 全局按 timestamp DESC 排序
    merged = sorted(ocr_results + ax_results, key=lambda r: r.timestamp, reverse=True)
    # 统一应用一次分页（skip offset，take limit）
    return apply_pagination(merged, skip=params.offset, take=params.limit)
```

**注**：各路径分别拉取 `limit+offset` 行（`offset=0`），最坏情况内存中合并 `2×(limit+offset)` 行。P1 场景 `limit≤100`、`offset` 通常小，内存可控——前提是 UI 采用"加载更多"而非跳页（**OQ-026=A 已决**，对齐 screenpipe）。screenpipe UI 为纯"加载更多"模式（`search-modal.tsx: hasMoreOcr/loadMoreOcr`），offset 单调递增步长=limit，实际不超过几百。P2+ 可升级为 keyset cursor 分页（`before_timestamp`），彻底消除过量拉取，届时需改 API 契约。对齐 screenpipe `db.rs:1876-1880, 2043-2050`。

**注**：`min_length`/`max_length` 仅转发给 `search_ocr()`；`search_accessibility()` 函数签名不接受这两个参数（accessibility 表无 `text_length` 列），`content_type=all` 时 accessibility 结果不受 `min_length`/`max_length` 过滤影响。对齐 screenpipe `db.rs:1894-1895, 1911-1919`。

**注**：`content_type=all` 的 `pagination.total` = `count_search_ocr()` + `count_search_accessibility()`，分别独立 COUNT 再求和。

**注**：screenpipe 明确注释"Avoid LEFT JOIN ocr_text — it forces a scan of the entire ocr_text"（db.rs line 3133）。v3 `search_ocr()` 路径遵循同样规则，主搜索路径不使用 LEFT JOIN。`search_accessibility()` 的 LEFT JOIN frames 是对 `frames` 表（非 `ocr_text`），且 `frame_id` 有索引，性能可控。

#### COUNT 查询（Scheme C 三路径，D3=A）

`pagination.total` 通过独立 COUNT 查询获得，按 `content_type` 分支：

##### `content_type=ocr` → `count_search_ocr()`

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

##### `content_type=accessibility` → `count_search_accessibility()`

```sql
SELECT COUNT(*)
FROM accessibility a
{accessibility_fts_join}
WHERE 1=1
    AND (? IS NULL OR a.app_name = ?)
    AND (? IS NULL OR a.window_name = ?)
    AND (? IS NULL OR a.focused = ?)
    AND (? IS NULL OR a.timestamp >= ?)
    AND (? IS NULL OR a.timestamp <= ?)
    {accessibility_fts_condition}
```

`accessibility_fts_join` / `accessibility_fts_condition` 路由规则同 `search_accessibility()`（browser_url 走 FTS MATCH）。

##### `content_type=all` → SUM

```python
total = count_search_ocr(params) + count_search_accessibility(params)
```

**性能兜底**：`idx_frames_timestamp` 和 `idx_accessibility_timestamp` B-tree 索引覆盖主过滤维度；100k 行级别 COUNT 预期 < 50ms（TBD-03 待实现后 benchmark 验证）。

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
| `frames.accessibility_text` | `frames.accessibility_text` | frames | 100% |
| `frames.text_source` | `frames.text_source` | frames | 100% |
| `frames.content_hash` | `frames.content_hash` | frames | 100% |
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
| `accessibility.id` | `accessibility.id` | accessibility | 100% |
| `accessibility.timestamp` | `accessibility.timestamp` | accessibility | 100% |
| `accessibility.app_name` | `accessibility.app_name` | accessibility | 100% |
| `accessibility.window_name` | `accessibility.window_name` | accessibility | 100% |
| `accessibility.text_content` | `accessibility.text_content` | accessibility | 100% |
| `accessibility.browser_url` | `accessibility.browser_url` | accessibility | 100% |
| *(无)* | `accessibility.frame_id` | accessibility | v3 增强（方案 3，screenpipe 用 ±1s 时间窗口 JOIN） |
| *(无)* | `accessibility.focused` | accessibility | v3 P0 修复（screenpipe 无此列，导致 focused→force OCR limitation） |
| `accessibility_fts` 3 indexed 列 | `accessibility_fts` 4 indexed 列（+browser_url） | FTS | v3 增强（screenpipe 3 列；v3 加 browser_url 确保 API 语义一致） |
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
    
    注：此为 API 契约层定义。Host 端内部 metadata 结构略有不同：
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
    accessibility_text: str = ""
    content_hash: Optional[str] = None    # required key；值为 sha256:hex 或 null
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
| `accessibility_text` | string | ✅ | required key；禁止 `null`；允许 `""`，其语义为“该帧已上传，但无可用 AX 文本” |
| `content_hash` | string｜null | ✅ | required key；允许 `null`；若非 null 则必须为 `sha256:` 前缀 + 64 位十六进制；禁止 `""` |
| `simhash` | int｜null | ❌ | 若非 null 则必须为非负 64 位整数 |
| `image_data` | multipart file | ✅ | JPEG（`image/jpeg`）主契约；兼容模式可接收 PNG/WebP，但入库前统一转码为 JPEG；最大 10MB；缺失→ `INVALID_PARAMS` |

**S2b handoff 字段语义（强制）**：
- `accessibility_text`：key 必须出现，值必须为 string；允许 `""`，不允许 `null`。
- `content_hash`：key 必须出现；值为 `sha256:[0-9a-f]{64}` 或 `null`；不允许 `""`。
- 缺少任一 key 均视为 ingest contract error（`INVALID_PARAMS`）。
- `accessibility_text=""` 表示“该帧已上传，但无可用 AX 文本”；`content_hash=null` 表示“该帧不属于 hash-applicable 样本”。
- `content_hash` 必须仅基于最终上报的 `accessibility_text` 计算；计算前需执行固定 canonicalization：Unicode NFC、换行统一为 `\n`、每行去尾部空白、整体 `strip()`。
- AX timeout 场景下，若仍产出部分文本，则按该最终 `accessibility_text` 正常计算 `content_hash`。

**上下文字段一致性契约（P1-S2b+）**：
- `focused_context = {app_name, window_name, browser_url}`：表示同一 capture 的 focused UI 上下文。
- `capture_device_binding = {device_name}`：表示该次 capture cycle 中实际被截取的 monitor。
- `app_name/window_name/browser_url` 若提供，必须由同一轮 focused-context snapshot 一次性产出；禁止字段级混拼。
- `browser_url` 若提供，必须与该 `focused_context` 校验一致；若无法确认一致性或命中 stale 检测，必须写 `null`。
- `device_name` 必须与实际截图 monitor 一致；它要求 same-cycle coherence，不承担同源 focused-context 语义。
- 不确定时遵循：`Better None than wrong window` / `Better None than wrong URL`。

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
- `content_hash` 去重与 `capture_id` 幂等是两层语义：当 dedup 条件满足（非 `idle/manual`、距该设备最近写入 < 30s、hash 有效且匹配）时，Host 会直接跳过本次 ingest；`capture_id` 幂等仅作用于实际发送到 Edge 的请求。

**dedup 语义（P1-S2b）**：
- dedup 判定由 **Host 端**执行（capture 完成并生成 `accessibility_text/content_hash` 后、upload 前），避免重复图片上传浪费带宽
- dedup 条件：非 idle/manual + 距上次写入 < 30s + content_hash 相同 + 非空文本
- 空文本不参与 dedup（与 screenpipe 对齐）
- dedup 判定成功后，Host 不调用 ingest API
- Edge 仅接收并存储 `content_hash`，不执行 dedup 判定

**dedup 运行态约束（P1-S2b）**：
- `last_content_hash/last_write_time` 为 per-device 纯内存运行态，**在 Host 端维护**，不写入 `edge.db`。
- `last_write_time` 的语义固定为最近一次成功写入 Host 本地 spool 的时间，不得以 HTTP 成功时间、Edge ingest 接收时间或 Edge DB 落库时间替代。
- Host 重启后 dedup 进入冷启动，重启边界附近允许出现额外写入；该现象为预期行为，不视为缺陷。
- Edge 端存储的 `content_hash` 仅用于观测，不用于 dedup 判定。

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
| 20260227000001 | `initial_schema.sql` | P1 全量 DDL（frames/ocr_text/accessibility/frames_fts/ocr_text_fts/accessibility_fts/chat_messages） |
| P2+ 时确定 | `add_embeddings.sql` | 新增 `ocr_text_embeddings` 表 |
