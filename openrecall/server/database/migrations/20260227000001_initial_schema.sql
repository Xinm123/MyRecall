-- OpenRecall v3 Initial Schema
-- Migration: 20260227000001_initial_schema.sql
-- Created: 2026-02-27
-- Updated: 2026-03-20 (Chat MVP Phase 1 - Reset to MVP Shape)
-- Tables: schema_migrations, frames, ocr_text, accessibility, elements, frames_fts, ocr_text_fts, accessibility_fts, chat_messages

-- ============================================================================
-- schema_migrations: Track applied migrations (SSOT: docs/v3/data-model.md §3.0.7)
-- ============================================================================
CREATE TABLE IF NOT EXISTS schema_migrations (
    version     TEXT PRIMARY KEY,        -- YYYYMMDDHHMMSS,对齐 screenpipe 迁移文件命名
    description TEXT NOT NULL,
    applied_at  TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- ============================================================================
-- Table 1: frames (Chat MVP Shape, SSOT: docs/v3/chat/mvp.md)
-- ============================================================================
CREATE TABLE IF NOT EXISTS frames (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp             TIMESTAMP NOT NULL,
    app_name              TEXT DEFAULT NULL,
    window_name           TEXT DEFAULT NULL,
    browser_url           TEXT DEFAULT NULL,
    focused               BOOLEAN DEFAULT NULL,
    device_name           TEXT NOT NULL DEFAULT 'monitor_0',
    snapshot_path         TEXT DEFAULT NULL,       -- JPEG 快照路径（主链路，推荐 .jpg）
    capture_trigger       TEXT DEFAULT NULL,       -- 'idle'|'app_switch'|'manual'|'click' (P1)

    -- MVP: Symmetric canonical text columns (replaces unified frames.text)
    accessibility_text        TEXT DEFAULT NULL,       -- Canonical text from accessibility (AX-first path)
    ocr_text                  TEXT DEFAULT NULL,       -- Canonical text from OCR (OCR-fallback path)
    text_source               TEXT DEFAULT NULL,       -- 'accessibility'|'ocr'

    -- MVP: Raw accessibility tree for chat context
    accessibility_tree_json TEXT DEFAULT NULL,     -- Full accessibility tree as JSON

    -- Deduplication fields
    content_hash          TEXT DEFAULT NULL,       -- sha256:hex，Edge 去重辅助
    simhash               INTEGER DEFAULT NULL,    -- 感知哈希，近似重复检测

    -- v3 Edge-Centric 追加
    capture_id            TEXT NOT NULL UNIQUE,    -- UUID v7，Host 生成，幂等键
    image_size_bytes      INTEGER,
    ingested_at           TEXT NOT NULL
                          DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
    status                TEXT NOT NULL DEFAULT 'pending',  -- 'pending'|'processing'|'completed'|'failed'
    error_message         TEXT,
    retry_count           INTEGER DEFAULT 0,
    processed_at          TEXT
);

-- B-tree 索引（精确过滤 / 时间范围）
CREATE INDEX IF NOT EXISTS idx_frames_timestamp     ON frames(timestamp);
CREATE INDEX IF NOT EXISTS idx_frames_app_name      ON frames(app_name);
CREATE INDEX IF NOT EXISTS idx_frames_window_name   ON frames(window_name);
CREATE INDEX IF NOT EXISTS idx_frames_browser_url   ON frames(browser_url);
CREATE INDEX IF NOT EXISTS idx_frames_focused       ON frames(focused);
CREATE INDEX IF NOT EXISTS idx_frames_snapshot_path ON frames(snapshot_path)
    WHERE snapshot_path IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_frames_status        ON frames(status)
    WHERE status IN ('pending', 'processing', 'failed');
CREATE INDEX IF NOT EXISTS idx_frames_content_hash  ON frames(content_hash)
    WHERE content_hash IS NOT NULL;

-- ============================================================================
-- Table 2: ocr_text (对齐 screenpipe ocr_text，仅 OCR-fallback 帧写入)
-- ============================================================================
CREATE TABLE IF NOT EXISTS ocr_text (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    frame_id              INTEGER NOT NULL,
    text                  TEXT NOT NULL DEFAULT '',
    text_json             TEXT,                    -- bounding box JSON（可选）
    ocr_engine            TEXT,
    text_length           INTEGER DEFAULT 0,
    app_name              TEXT DEFAULT NULL,
    window_name           TEXT DEFAULT NULL,
    FOREIGN KEY (frame_id) REFERENCES frames(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_ocr_text_frame_id ON ocr_text(frame_id);

-- ============================================================================
-- Table 3: frames_fts (MVP: metadata-only FTS, SSOT: docs/v3/chat/mvp.md)
-- Text search is via accessibility_fts and ocr_text_fts only.
-- ============================================================================
CREATE VIRTUAL TABLE IF NOT EXISTS frames_fts USING fts5(
    app_name,
    window_name,
    browser_url,
    focused,
    id UNINDEXED,
    tokenize='unicode61'
);

-- INSERT 触发器
CREATE TRIGGER IF NOT EXISTS frames_ai AFTER INSERT ON frames BEGIN
    INSERT INTO frames_fts(id, app_name, window_name, browser_url, focused)
    VALUES (
        NEW.id,
        COALESCE(NEW.app_name, ''),
        COALESCE(NEW.window_name, ''),
        COALESCE(NEW.browser_url, ''),
        COALESCE(NEW.focused, 0)
    );
END;

-- UPDATE 触发器（清空字段时也必须同步，避免陈旧 token）
CREATE TRIGGER IF NOT EXISTS frames_au AFTER UPDATE ON frames BEGIN
    DELETE FROM frames_fts WHERE id = OLD.id;
    INSERT INTO frames_fts(id, app_name, window_name, browser_url, focused)
    VALUES (
        NEW.id,
        COALESCE(NEW.app_name, ''),
        COALESCE(NEW.window_name, ''),
        COALESCE(NEW.browser_url, ''),
        COALESCE(NEW.focused, 0)
    );
END;

-- DELETE 触发器
CREATE TRIGGER IF NOT EXISTS frames_ad AFTER DELETE ON frames BEGIN
    DELETE FROM frames_fts WHERE id = OLD.id;
END;

-- ============================================================================
-- Table 4: ocr_text_fts (对齐 screenpipe)
-- ============================================================================
CREATE VIRTUAL TABLE IF NOT EXISTS ocr_text_fts USING fts5(
    text,
    app_name,
    window_name,
    frame_id UNINDEXED,
    tokenize='unicode61'
);

-- INSERT 触发器
CREATE TRIGGER IF NOT EXISTS ocr_text_ai AFTER INSERT ON ocr_text
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
CREATE TRIGGER IF NOT EXISTS ocr_text_update AFTER UPDATE ON ocr_text BEGIN
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
CREATE TRIGGER IF NOT EXISTS ocr_text_delete AFTER DELETE ON ocr_text BEGIN
    DELETE FROM ocr_text_fts WHERE frame_id = OLD.frame_id;
END;

-- ============================================================================
-- Table 5: chat_messages (v3 独有)
-- ============================================================================
CREATE TABLE IF NOT EXISTS chat_messages (
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

CREATE INDEX IF NOT EXISTS idx_chat_session ON chat_messages(session_id, created_at);

-- ============================================================================
-- Table 6: accessibility (MVP Shape, SSOT: docs/v3/chat/mvp.md)
-- Key changes from legacy:
-- - frame_id is NOT NULL (accessibility always paired with a frame)
-- - text_length added for efficient size queries
-- - focused removed (focused is per-frame, not per-accessibility record)
-- ============================================================================
CREATE TABLE IF NOT EXISTS accessibility (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp             DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    app_name              TEXT NOT NULL,
    window_name           TEXT NOT NULL,
    text_content          TEXT NOT NULL,
    browser_url           TEXT,

    -- MVP: frame_id is required (accessibility always belongs to a frame)
    frame_id              INTEGER NOT NULL,

    -- MVP: text_length for efficient queries
    text_length           INTEGER DEFAULT 0,

    FOREIGN KEY (frame_id) REFERENCES frames(id) ON DELETE CASCADE
);

-- B-tree 索引（对齐 screenpipe migration + v3 追加）
CREATE INDEX IF NOT EXISTS idx_accessibility_timestamp  ON accessibility(timestamp);
CREATE INDEX IF NOT EXISTS idx_accessibility_app_name   ON accessibility(app_name);
CREATE INDEX IF NOT EXISTS idx_accessibility_frame_id   ON accessibility(frame_id);

-- ============================================================================
-- Table 7: elements (MVP: individual accessibility elements)
-- Stores the tree structure of accessibility elements for each frame.
-- ============================================================================
CREATE TABLE IF NOT EXISTS elements (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    frame_id      INTEGER NOT NULL,
    source        TEXT NOT NULL DEFAULT 'accessibility',  -- 'accessibility'|'ocr'
    role          TEXT,                                    -- AXRole: button, text, etc.
    text          TEXT,                                    -- Element text content
    parent_id     INTEGER,                                 -- Parent element id (tree structure)
    depth         INTEGER,                                 -- Depth in tree (0 = root)
    left_bound    REAL,                                    -- Left coordinate
    top_bound     REAL,                                    -- Top coordinate
    width_bound   REAL,                                    -- Width
    height_bound   REAL,                                   -- Height
    sort_order    INTEGER,                                 -- Order within parent/siblings

    FOREIGN KEY (frame_id) REFERENCES frames(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_id) REFERENCES elements(id) ON DELETE SET NULL
);

-- Indexes for elements table
CREATE INDEX IF NOT EXISTS idx_elements_frame_id ON elements(frame_id);
CREATE INDEX IF NOT EXISTS idx_elements_role ON elements(role);
CREATE INDEX IF NOT EXISTS idx_elements_parent_id ON elements(parent_id);

-- ============================================================================
-- Table 8: accessibility_fts (基于 screenpipe + browser_url 增强)
-- ============================================================================
CREATE VIRTUAL TABLE IF NOT EXISTS accessibility_fts USING fts5(
    text_content,
    app_name,
    window_name,
    browser_url,
    content='accessibility',
    content_rowid='id',
    tokenize='unicode61'
);

-- INSERT 触发器
CREATE TRIGGER IF NOT EXISTS accessibility_ai AFTER INSERT ON accessibility BEGIN
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
CREATE TRIGGER IF NOT EXISTS accessibility_au AFTER UPDATE ON accessibility BEGIN
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
CREATE TRIGGER IF NOT EXISTS accessibility_ad AFTER DELETE ON accessibility BEGIN
    INSERT INTO accessibility_fts(accessibility_fts, rowid, text_content, app_name, window_name, browser_url)
    VALUES ('delete', OLD.id, OLD.text_content, OLD.app_name, OLD.window_name, OLD.browser_url);
END;
