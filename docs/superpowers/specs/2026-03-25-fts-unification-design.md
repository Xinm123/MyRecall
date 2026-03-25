# FTS Unification Design

**Date:** 2026-03-25
**Status:** Draft
**Author:** Claude

## Summary

Unify MyRecall's FTS structure to align with screenpipe's design. Consolidate OCR text and accessibility text into a single `frames.full_text` column, indexed by a rebuilt `frames_fts` table.

## Motivation

**Current state:**
- 3 separate FTS tables: `frames_fts` (metadata only), `ocr_text_fts`, `accessibility_fts`
- Search API requires `content_type` parameter to select which FTS table to query
- Complex search logic with dual-query merging

**Problems:**
- Misaligned with screenpipe reference implementation
- Unnecessary complexity in search engine
- Slower searches due to dual-query + merge overhead

**Goal:**
- Single FTS table (`frames_fts`) indexing all text content
- Simplified search engine with single query path
- Align with screenpipe's consolidated design

## Design

### 1. Database Schema Changes

#### Add `frames.full_text` column

```sql
ALTER TABLE frames ADD COLUMN full_text TEXT DEFAULT NULL;
```

This column stores merged text from all sources:
- `accessibility_text` (AX-first path)
- `ocr_text` (OCR-fallback path)
- Both combined (hybrid case)

#### Rebuild `frames_fts` with new schema

**Old schema:**
```sql
CREATE VIRTUAL TABLE frames_fts USING fts5(
    app_name,
    window_name,
    browser_url,
    focused,
    id UNINDEXED,
    tokenize='unicode61'
);
```

**New schema:**
```sql
CREATE VIRTUAL TABLE frames_fts USING fts5(
    full_text,
    app_name,
    window_name,
    browser_url,
    id UNINDEXED,
    tokenize='unicode61'
);
```

**Changes:**
- Add `full_text` column (primary searchable text)
- Remove `focused` column (boolean, not useful for text search)

**Note:** `focused` is only removed from FTS indexing, not from the `frames` table. Search results still include `frames.focused` in the response.

### 2. Data Migration

Migration file: `20260325120000_consolidate_fts_to_full_text.sql`

**Important:** Steps must run in this exact order to ensure hybrid frames get merged text, not just accessibility_text.

#### Step 1: Add column

```sql
ALTER TABLE frames ADD COLUMN full_text TEXT DEFAULT NULL;
```

#### Step 2: Merge for hybrid frames (MUST run before Step 3)

Detect frames with BOTH text sources populated and merge them first.
- If `accessibility_text` AND `ocr_text` (column or table) both exist → merge both
- Order: accessibility_text first, then OCR text

```sql
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
```

#### Step 3: Backfill from accessibility_text (AX-only path)

After hybrid frames are handled, backfill accessibility-only frames:

```sql
UPDATE frames SET full_text = accessibility_text
WHERE full_text IS NULL
  AND accessibility_text IS NOT NULL AND accessibility_text != '';
```

#### Step 4: Backfill from ocr_text column (OCR-only path)

MyRecall stores OCR text in two locations:
- `ocr_text.text` table (with bounding boxes in `text_json`)
- `frames.ocr_text` column (denormalized for quick access)

Check both locations, preferring the column (may be more recent):

```sql
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
```

#### Step 5: Rebuild frames_fts

```sql
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

INSERT INTO frames_fts(id, full_text, app_name, window_name, browser_url)
SELECT
    id,
    full_text,
    COALESCE(app_name, ''),
    COALESCE(window_name, ''),
    COALESCE(browser_url, '')
FROM frames
WHERE full_text IS NOT NULL AND full_text != '';
```

#### Step 6: Create new triggers

```sql
CREATE TRIGGER frames_ai AFTER INSERT ON frames
WHEN NEW.full_text IS NOT NULL AND NEW.full_text != ''
BEGIN
    INSERT INTO frames_fts(id, full_text, app_name, window_name, browser_url)
    VALUES (NEW.id, NEW.full_text, COALESCE(NEW.app_name, ''), COALESCE(NEW.window_name, ''), COALESCE(NEW.browser_url, ''));
END;

CREATE TRIGGER frames_au AFTER UPDATE OF full_text, app_name, window_name, browser_url ON frames
BEGIN
    DELETE FROM frames_fts WHERE id = OLD.id;
    INSERT INTO frames_fts(id, full_text, app_name, window_name, browser_url)
    SELECT NEW.id, COALESCE(NEW.full_text, ''), COALESCE(NEW.app_name, ''), COALESCE(NEW.window_name, ''), COALESCE(NEW.browser_url, '')
    WHERE NEW.full_text IS NOT NULL AND NEW.full_text != '';
END;

CREATE TRIGGER frames_ad AFTER DELETE ON frames
BEGIN
    DELETE FROM frames_fts WHERE id = OLD.id;
END;
```

#### Step 7: Drop old FTS tables and triggers

```sql
DROP TRIGGER IF EXISTS ocr_text_ai;
DROP TRIGGER IF EXISTS ocr_text_update;
DROP TRIGGER IF EXISTS ocr_text_delete;
DROP TABLE IF EXISTS ocr_text_fts;

DROP TRIGGER IF EXISTS accessibility_ai;
DROP TRIGGER IF EXISTS accessibility_au;
DROP TRIGGER IF EXISTS accessibility_ad;
DROP TABLE IF EXISTS accessibility_fts;
```

### 3. Tables Retained

| Table | Retained | Reason |
|-------|----------|--------|
| `ocr_text` | Yes | Stores `text_json` (bounding boxes) for highlight rendering |
| `accessibility` | Yes | Stores accessibility tree for chat context |
| `frames.accessibility_text` | Yes | Source of truth for AX-first frames |
| `frames.ocr_text` | Yes | Source of truth for OCR-fallback frames |
| `frames.text_source` | Yes | Tracks which source provided canonical text (`'accessibility'`/`'ocr'`/`'hybrid'`) |
| `ocr_text_fts` | No | Replaced by `frames_fts` |
| `accessibility_fts` | No | Replaced by `frames_fts` |

**Divergence from screenpipe:** screenpipe drops the `accessibility` table entirely after FTS consolidation. MyRecall retains it because the chat feature uses the full accessibility tree for context. The `accessibility` table continues to receive new writes during ingest.

### 4. Search Engine Changes

#### Simplified query pattern

**Before:** 3 separate methods (`_search_ocr`, `_search_accessibility`, `_search_all`) with complex merging.

**After:** Single `_search` method with one FTS query.

```sql
SELECT frames.id AS frame_id,
       frames.timestamp,
       frames.full_text AS text,
       frames.app_name,
       frames.window_name,
       frames.browser_url,
       frames.focused,
       frames.device_name,
       frames.text_source,
       frames_fts.rank AS fts_rank
FROM frames
INNER JOIN frames_fts ON frames.id = frames_fts.id
WHERE frames.status = 'completed'
  AND frames_fts MATCH ?
GROUP BY frames.id
ORDER BY frames_fts.rank, frames.timestamp DESC
LIMIT ? OFFSET ?;
```

#### API compatibility

The `content_type` parameter (`ocr`/`accessibility`/`all`) on `/v1/search` is:
- **Retained** for backward compatibility
- **Ignored** (all results returned regardless)
- **Logged** as deprecation warning in debug mode

#### Files to modify

| File | Change |
|------|--------|
| `openrecall/server/search/engine.py` | Simplify to single query path, remove `_search_ocr`, `_search_accessibility`, `_search_all` |
| `openrecall/server/api_v1.py` | Keep `content_type` param, add deprecation log |

### 5. Ingest Path Changes

#### How `full_text` gets populated

**At frame insert time (`FramesStore.insert_frame()`):**

1. If `accessibility_text` provided:
   - `full_text = accessibility_text`
   - `text_source = 'accessibility'`

2. If OCR-only (no AX data):
   - `full_text = NULL` initially
   - Worker sets `full_text = ocr_text` after OCR completes
   - `text_source = 'ocr'`

3. If hybrid (both sources):
   - `full_text = accessibility_text + ocr_text` (merged)
   - `text_source = 'hybrid'`

#### Files to modify

| File | Change |
|------|--------|
| `openrecall/server/database/frames_store.py` | Add `full_text` to INSERT, add UPDATE method for worker |
| `openrecall/server/processing/v3_worker.py` | Update `full_text` after OCR |

### 6. Testing Strategy

#### Unit tests

| Test | File | Description |
|------|------|-------------|
| Migration backfill | `tests/test_v3_migrations_bootstrap.py` | Verify backfill for all `text_source` cases |
| FTS triggers | `tests/test_p1_s3_fts_trigger.py` | Verify INSERT/UPDATE/DELETE triggers |
| Search engine | `tests/test_p1_s4_search_fts.py` | Verify single-query path |

#### Integration tests

| Test | Description |
|------|-------------|
| AX ingest + search | New frames with AX text are searchable |
| OCR ingest + search | New frames with OCR text are searchable |
| Migration | Existing data correctly backfilled |

## Migration Rollout

1. **Deploy migration:** Schema changes applied on server startup
2. **Backfill:** `full_text` populated from existing data
3. **FTS rebuild:** `frames_fts` rebuilt with new schema
4. **Cleanup:** Old FTS tables dropped

## Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| Large dataset backfill takes time | Migration runs incrementally, server remains operational |
| Search returns unexpected results | Unit tests cover all query patterns |
| API clients rely on `content_type` | Parameter accepted but ignored, deprecation logged |

## Success Criteria

1. All existing frames have `full_text` populated
2. Search latency <= 200ms (P95)
3. All tests pass
4. API backward compatible (existing clients work without changes)
