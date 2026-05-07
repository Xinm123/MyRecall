-- MyRecall v3 FTS Unification Migration
-- Consolidates OCR text and accessibility text into frames.full_text
-- Per spec: docs/superpowers/specs/2026-03-25-fts-unification-design.md

-- ============================================================================
-- Step 1: Add full_text column to frames
-- ============================================================================
ALTER TABLE frames ADD COLUMN full_text TEXT DEFAULT NULL;

-- ============================================================================
-- Step 2: Merge for hybrid frames (MUST run before Step 3)
-- Detect frames with BOTH text sources populated and merge them first.
-- ============================================================================

-- Merge when both frames.accessibility_text and frames.ocr_text exist
UPDATE frames SET full_text = accessibility_text || char(10) || frames.ocr_text
WHERE accessibility_text IS NOT NULL AND accessibility_text != ''
  AND frames.ocr_text IS NOT NULL AND frames.ocr_text != '';

-- Merge when accessibility_text exists with ocr_text table row (but no frames.ocr_text column)
UPDATE frames SET full_text = accessibility_text || char(10) || (
    SELECT ot.text FROM ocr_text ot WHERE ot.frame_id = frames.id LIMIT 1
)
WHERE full_text IS NULL
  AND accessibility_text IS NOT NULL AND accessibility_text != ''
  AND (frames.ocr_text IS NULL OR frames.ocr_text = '')
  AND EXISTS (SELECT 1 FROM ocr_text ot WHERE ot.frame_id = frames.id AND ot.text != '');

-- ============================================================================
-- Step 3: Backfill from accessibility_text (AX-only path)
-- After hybrid frames are handled, backfill accessibility-only frames.
-- ============================================================================
UPDATE frames SET full_text = accessibility_text
WHERE full_text IS NULL
  AND accessibility_text IS NOT NULL AND accessibility_text != '';

-- ============================================================================
-- Step 4: Backfill from ocr_text column (OCR-only path)
-- Check both locations: frames.ocr_text column and ocr_text table.
-- ============================================================================

-- First try frames.ocr_text column
UPDATE frames SET full_text = frames.ocr_text
WHERE full_text IS NULL
  AND frames.ocr_text IS NOT NULL AND frames.ocr_text != '';

-- Then try ocr_text table as fallback
UPDATE frames SET full_text = (
    SELECT ot.text FROM ocr_text ot WHERE ot.frame_id = frames.id LIMIT 1
)
WHERE full_text IS NULL
  AND EXISTS (SELECT 1 FROM ocr_text ot WHERE ot.frame_id = frames.id);

-- ============================================================================
-- Step 5: Rebuild frames_fts with new schema
-- Old: metadata only (app_name, window_name, browser_url, focused, id)
-- New: full_text + metadata (without focused)
-- ============================================================================

DROP TRIGGER IF EXISTS frames_ai;
DROP TRIGGER IF EXISTS frames_au;
DROP TRIGGER IF EXISTS frames_ad;
DROP TABLE IF EXISTS frames_fts;

CREATE VIRTUAL TABLE frames_fts USING fts5(
    full_text,
    app_name,
    window_name,
    browser_url,
    id UNINDEXED,
    tokenize='unicode61'
);

-- Populate from frames with text
INSERT INTO frames_fts(id, full_text, app_name, window_name, browser_url)
SELECT
    id,
    full_text,
    COALESCE(app_name, ''),
    COALESCE(window_name, ''),
    COALESCE(browser_url, '')
FROM frames
WHERE full_text IS NOT NULL AND full_text != '';

-- ============================================================================
-- Step 6: Create new FTS triggers
-- ============================================================================

-- INSERT: index when full_text is non-empty
CREATE TRIGGER frames_ai AFTER INSERT ON frames
WHEN NEW.full_text IS NOT NULL AND NEW.full_text != ''
BEGIN
    INSERT INTO frames_fts(id, full_text, app_name, window_name, browser_url)
    VALUES (NEW.id, NEW.full_text, COALESCE(NEW.app_name, ''), COALESCE(NEW.window_name, ''), COALESCE(NEW.browser_url, ''));
END;

-- UPDATE: re-index on full_text or metadata change
CREATE TRIGGER frames_au AFTER UPDATE OF full_text, app_name, window_name, browser_url ON frames
BEGIN
    DELETE FROM frames_fts WHERE id = OLD.id;
    INSERT INTO frames_fts(id, full_text, app_name, window_name, browser_url)
    SELECT NEW.id, COALESCE(NEW.full_text, ''), COALESCE(NEW.app_name, ''), COALESCE(NEW.window_name, ''), COALESCE(NEW.browser_url, '')
    WHERE NEW.full_text IS NOT NULL AND NEW.full_text != '';
END;

-- DELETE: remove from FTS
CREATE TRIGGER frames_ad AFTER DELETE ON frames
BEGIN
    DELETE FROM frames_fts WHERE id = OLD.id;
END;

-- ============================================================================
-- Step 7: Drop old FTS tables and triggers
-- ============================================================================

-- Drop ocr_text_fts
DROP TRIGGER IF EXISTS ocr_text_ai;
DROP TRIGGER IF EXISTS ocr_text_update;
DROP TRIGGER IF EXISTS ocr_text_delete;
DROP TABLE IF EXISTS ocr_text_fts;

-- Drop accessibility_fts
DROP TRIGGER IF EXISTS accessibility_ai;
DROP TRIGGER IF EXISTS accessibility_au;
DROP TRIGGER IF EXISTS accessibility_ad;
DROP TABLE IF EXISTS accessibility_fts;
