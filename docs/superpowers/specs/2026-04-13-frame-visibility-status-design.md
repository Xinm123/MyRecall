# Frame Visibility Status Design

**Date:** 2026-04-13
**Status:** Draft

## Problem

Users see incomplete/partially-processed frames in search results, affecting relevance and user experience. Frames may have OCR completed but missing description or embedding, leading to inconsistent search results.

## Solution

Add a `visibility_status` field that tracks when a frame is fully processed and ready for querying. A frame is "queryable" only when all processing stages are complete: OCR + description + embedding.

## Design

### Database Schema

**New field on `frames` table:**

```sql
ALTER TABLE frames ADD COLUMN visibility_status TEXT DEFAULT 'pending';
```

**Values:**
- `pending` (default) - frame is still being processed or partially processed
- `queryable` - all required stages complete (OCR + description + embedding)
- `failed` - one or more stages failed permanently

**Index for query performance:**

```sql
CREATE INDEX idx_frames_visibility ON frames(visibility_status, timestamp DESC);
```

### Definition of "Queryable"

A frame is queryable when **all** of the following are complete:
- Processing: `status = 'completed'` (set by V3ProcessingWorker for all frames)
- Description generation: `description_status = 'completed'`
- Embedding generation: `embedding_status = 'completed'`

**Note:** All frames go through V3ProcessingWorker which sets `status = 'completed'`. The `text_source` field indicates whether text came from accessibility API (`'accessibility'`) or OCR (`'ocr'`), but does not affect the completion check.

**Why:** Ensures users only see frames with full semantic context (description) and vector search capability (embedding), regardless of search mode.

### Worker Update Logic

**Shared helpers in `FramesStore`:**

```python
def try_set_queryable(self, conn: sqlite3.Connection, frame_id: int) -> bool:
    """Set visibility_status='queryable' if all stages are complete.

    Called by each worker after completing their stage.
    Idempotent - safe to call multiple times.

    Args:
        conn: Database connection (caller manages transaction)
        frame_id: Frame ID to update

    Returns:
        True if frame was marked queryable, False otherwise.
    """
    cursor = conn.execute(
        """
        UPDATE frames
        SET visibility_status = 'queryable'
        WHERE id = ?
          AND status = 'completed'
          AND description_status = 'completed'
          AND embedding_status = 'completed'
          AND visibility_status = 'pending'
        """,
        (frame_id,),
    )
    return cursor.rowcount > 0

def try_set_queryable_standalone(self, frame_id: int) -> bool:
    """Set visibility_status='queryable' if all stages are complete.

    Standalone version that manages its own database connection.
    Used by V3ProcessingWorker which doesn't pass connections.

    Args:
        frame_id: Frame ID to update

    Returns:
        True if frame was marked queryable, False otherwise.
    """
    try:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE frames
                SET visibility_status = 'queryable'
                WHERE id = ?
                  AND status = 'completed'
                  AND description_status = 'completed'
                  AND embedding_status = 'completed'
                  AND visibility_status = 'pending'
                """,
                (frame_id,),
            )
            return cursor.rowcount > 0
    except sqlite3.Error as e:
        logger.error("try_set_queryable_standalone failed frame_id=%d: %s", frame_id, e)
        return False

def try_set_failed(self, conn: sqlite3.Connection, frame_id: int) -> bool:
    """Mark frame as failed if any stage failed.

    Args:
        conn: Database connection (caller manages transaction)
        frame_id: Frame ID to update

    Returns:
        True if frame was marked failed, False otherwise.
    """
    cursor = conn.execute(
        """
        UPDATE frames
        SET visibility_status = 'failed'
        WHERE id = ? AND visibility_status = 'pending'
          AND (status = 'failed' OR description_status = 'failed' OR embedding_status = 'failed')
        """,
        (frame_id,),
    )
    return cursor.rowcount > 0

def try_set_failed_standalone(self, frame_id: int) -> bool:
    """Mark frame as failed if any stage failed.

    Standalone version that manages its own database connection.

    Args:
        frame_id: Frame ID to update

    Returns:
        True if frame was marked failed, False otherwise.
    """
    try:
        with self._connect() as conn:
            cursor = conn.execute(
                """
                UPDATE frames
                SET visibility_status = 'failed'
                WHERE id = ? AND visibility_status = 'pending'
                  AND (status = 'failed' OR description_status = 'failed' OR embedding_status = 'failed')
                """,
                (frame_id,),
            )
            return cursor.rowcount > 0
    except sqlite3.Error as e:
        logger.error("try_set_failed_standalone failed frame_id=%d: %s", frame_id, e)
        return False
```

**Worker integration points:**

1. **V3ProcessingWorker** (`openrecall/server/processing/v3_worker.py`) - after marking `status='completed'`
2. **FramesStore.complete_description_task** (`openrecall/server/database/frames_store.py`) - after setting `description_status='completed'`
3. **EmbeddingService.mark_completed** (`openrecall/server/embedding/service.py`) - after setting `embedding_status='completed'`

Each worker calls `try_set_queryable()` (or `try_set_queryable_standalone()`) after completing their stage, and `try_set_failed()` (or `try_set_failed_standalone()`) after permanent failure.

### API Query Changes

| Endpoint | Current Filter | New Filter |
|----------|---------------|------------|
| `GET /v1/search` (FTS) | `status = 'completed'` | `visibility_status = 'queryable'` |
| `GET /v1/search` (vector) | `status = 'completed' AND embedding_status = 'completed'` | `visibility_status = 'queryable'` |
| `GET /v1/search` (hybrid) | Combined | `visibility_status = 'queryable'` |
| `GET /v1/activity-summary` | No status filter | `visibility_status = 'queryable'` |
| `GET /v1/frames/{id}/context` | No status filter | `visibility_status = 'queryable'` |

**Files to modify:**

- `openrecall/server/search/engine.py` - FTS search WHERE clause
- `openrecall/server/search/hybrid_engine.py` - Vector/hybrid search WHERE clause
- `openrecall/server/database/frames_store.py` - Activity summary queries + get_frame_context
- `openrecall/server/api_v1.py` - Frame context 404 handling

### Migration

**File:** `openrecall/server/database/migrations/20260414000000_add_visibility_status.sql`

```sql
-- Add visibility_status column
ALTER TABLE frames ADD COLUMN visibility_status TEXT DEFAULT 'pending';

-- Create index for query performance
CREATE INDEX idx_frames_visibility ON frames(visibility_status, timestamp DESC);

-- Backfill existing frames that are already fully processed
UPDATE frames
SET visibility_status = 'queryable'
WHERE status = 'completed'
  AND description_status = 'completed'
  AND embedding_status = 'completed';

-- Backfill frames with permanent failures
UPDATE frames
SET visibility_status = 'failed'
WHERE status = 'failed'
   OR description_status = 'failed'
   OR embedding_status = 'failed';
```

### Testing

**Unit tests:**
- `test_visibility_status_helper()` - Test `try_set_queryable()` logic
- `test_visibility_status_failed()` - Test `try_set_failed()` logic

**Integration tests:**
- `test_search_only_returns_queryable_frames()` - Verify search API filtering
- `test_activity_summary_only_queryable()` - Verify activity-summary filtering
- `test_frame_context_not_ready()` - Verify 404 for non-queryable frames

**Migration test:**
- `test_visibility_status_migration_backfill()` - Verify backfill correctness

## Files Changed

| File | Change |
|------|--------|
| `openrecall/server/database/migrations/20260414000000_add_visibility_status.sql` | New migration |
| `openrecall/server/database/frames_store.py` | Add helpers (`try_set_queryable*`, `try_set_failed*`) + query filters + integrate in `complete_description_task`/`fail_description_task` |
| `openrecall/server/processing/v3_worker.py` | Call `try_set_queryable_standalone()` after completion, `try_set_failed_standalone()` on failure |
| `openrecall/server/embedding/service.py` | Call `try_set_queryable()` in `mark_completed()`, `try_set_failed()` in `mark_failed()` |
| `openrecall/server/search/engine.py` | Update WHERE clause |
| `openrecall/server/search/hybrid_engine.py` | Update WHERE clause |
| `openrecall/server/api_v1.py` | Frame context visibility check |
| `tests/test_visibility_status.py` | New test file |

## Rollback

```sql
ALTER TABLE frames DROP COLUMN visibility_status;
DROP INDEX IF EXISTS idx_frames_visibility;
```
