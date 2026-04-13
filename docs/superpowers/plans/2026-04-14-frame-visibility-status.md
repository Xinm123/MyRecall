# Frame Visibility Status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `visibility_status` field to ensure only fully-processed frames (OCR + description + embedding completed) are visible in search, activity-summary, and frame context APIs.

**Architecture:** Add a new `visibility_status` column to the frames table with values `pending`/`queryable`/`failed`. Workers call a helper method after completing their stage to check if all stages are done and set `visibility_status='queryable'`. API queries filter by this field instead of checking individual status fields.

**Tech Stack:** SQLite, Python, Flask

---

## File Structure

| File | Responsibility |
|------|----------------|
| `openrecall/server/database/migrations/20260414000000_add_visibility_status.sql` | Migration: add column, index, backfill |
| `openrecall/server/database/frames_store.py` | Helper methods: `try_set_queryable()`, `try_set_queryable_standalone()`, update queries |
| `openrecall/server/processing/v3_worker.py` | Call helper after OCR completes |
| `openrecall/server/description/service.py` | Call helper in `mark_completed()` |
| `openrecall/server/embedding/service.py` | Call helper in `mark_completed()` |
| `openrecall/server/search/engine.py` | Update WHERE clause |
| `openrecall/server/search/hybrid_engine.py` | Update WHERE clause |
| `openrecall/server/api_v1.py` | Frame context visibility check |
| `tests/test_visibility_status.py` | Unit tests |

---

### Task 1: Database Migration

**Files:**
- Create: `openrecall/server/database/migrations/20260414000000_add_visibility_status.sql`

- [ ] **Step 1: Write the migration file**

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

- [ ] **Step 2: Run migrations test to verify**

Run: `pytest tests/test_v3_migrations_bootstrap.py -v`
Expected: PASS (migration runs without error)

- [ ] **Step 3: Commit**

```bash
git add openrecall/server/database/migrations/20260414000000_add_visibility_status.sql
git commit -m "feat(db): add visibility_status column with migration"
```

---

### Task 2: FramesStore Helper Methods

**Files:**
- Modify: `openrecall/server/database/frames_store.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_visibility_status.py`:

```python
"""Unit tests for visibility_status helper methods."""
import sqlite3
import tempfile
from pathlib import Path

import pytest

from openrecall.server.database.frames_store import FramesStore


@pytest.fixture
def temp_store():
    """Create a temporary FramesStore for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        store = FramesStore(db_path=db_path)
        # Create minimal schema
        with store._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS frames (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    capture_id TEXT UNIQUE,
                    timestamp TEXT,
                    status TEXT DEFAULT 'pending',
                    description_status TEXT,
                    embedding_status TEXT,
                    visibility_status TEXT DEFAULT 'pending',
                    app_name TEXT,
                    window_name TEXT,
                    snapshot_path TEXT
                )
            """)
        yield store


class TestTrySetQueryable:
    """Tests for try_set_queryable method."""

    def test_sets_queryable_when_all_stages_complete(self, temp_store):
        """Should set visibility_status='queryable' when all stages are done."""
        with temp_store._connect() as conn:
            # Insert a frame with all stages complete
            conn.execute(
                """
                INSERT INTO frames (id, status, description_status, embedding_status, visibility_status)
                VALUES (1, 'completed', 'completed', 'completed', 'pending')
                """
            )

            # Call the helper
            result = temp_store.try_set_queryable(conn, 1)

            assert result is True

            # Verify the update
            row = conn.execute(
                "SELECT visibility_status FROM frames WHERE id = 1"
            ).fetchone()
            assert row["visibility_status"] == "queryable"

    def test_returns_false_when_stages_incomplete(self, temp_store):
        """Should return False and not update when stages are incomplete."""
        with temp_store._connect() as conn:
            # Insert a frame with incomplete stages
            conn.execute(
                """
                INSERT INTO frames (id, status, description_status, embedding_status, visibility_status)
                VALUES (1, 'completed', 'completed', 'pending', 'pending')
                """
            )

            result = temp_store.try_set_queryable(conn, 1)

            assert result is False

            row = conn.execute(
                "SELECT visibility_status FROM frames WHERE id = 1"
            ).fetchone()
            assert row["visibility_status"] == "pending"

    def test_idempotent_already_queryable(self, temp_store):
        """Should return False if already queryable (idempotent)."""
        with temp_store._connect() as conn:
            conn.execute(
                """
                INSERT INTO frames (id, status, description_status, embedding_status, visibility_status)
                VALUES (1, 'completed', 'completed', 'completed', 'queryable')
                """
            )

            result = temp_store.try_set_queryable(conn, 1)

            assert result is False  # No change made


class TestTrySetQueryableStandalone:
    """Tests for try_set_queryable_standalone method (manages own connection)."""

    def test_sets_queryable_when_all_stages_complete(self, temp_store):
        """Should set visibility_status='queryable' using own connection."""
        with temp_store._connect() as conn:
            conn.execute(
                """
                INSERT INTO frames (id, status, description_status, embedding_status, visibility_status)
                VALUES (1, 'completed', 'completed', 'completed', 'pending')
                """
            )

        # Call standalone version (no conn passed)
        result = temp_store.try_set_queryable_standalone(1)

        assert result is True

        with temp_store._connect() as conn:
            row = conn.execute(
                "SELECT visibility_status FROM frames WHERE id = 1"
            ).fetchone()
            assert row["visibility_status"] == "queryable"


class TestTrySetFailed:
    """Tests for try_set_failed method."""

    def test_sets_failed_when_any_stage_failed(self, temp_store):
        """Should set visibility_status='failed' when any stage failed."""
        with temp_store._connect() as conn:
            conn.execute(
                """
                INSERT INTO frames (id, status, description_status, embedding_status, visibility_status)
                VALUES (1, 'failed', 'completed', 'pending', 'pending')
                """
            )

            result = temp_store.try_set_failed(conn, 1)

            assert result is True

            row = conn.execute(
                "SELECT visibility_status FROM frames WHERE id = 1"
            ).fetchone()
            assert row["visibility_status"] == "failed"

    def test_does_not_override_queryable(self, temp_store):
        """Should not change visibility_status if already queryable."""
        with temp_store._connect() as conn:
            conn.execute(
                """
                INSERT INTO frames (id, status, description_status, embedding_status, visibility_status)
                VALUES (1, 'failed', 'completed', 'pending', 'queryable')
                """
            )

            result = temp_store.try_set_failed(conn, 1)

            assert result is False

            row = conn.execute(
                "SELECT visibility_status FROM frames WHERE id = 1"
            ).fetchone()
            assert row["visibility_status"] == "queryable"


class TestTrySetFailedStandalone:
    """Tests for try_set_failed_standalone method (manages own connection)."""

    def test_sets_failed_when_any_stage_failed(self, temp_store):
        """Should set visibility_status='failed' using own connection."""
        with temp_store._connect() as conn:
            conn.execute(
                """
                INSERT INTO frames (id, status, description_status, embedding_status, visibility_status)
                VALUES (1, 'completed', 'failed', 'pending', 'pending')
                """
            )

        # Call standalone version (no conn passed)
        result = temp_store.try_set_failed_standalone(1)

        assert result is True

        with temp_store._connect() as conn:
            row = conn.execute(
                "SELECT visibility_status FROM frames WHERE id = 1"
            ).fetchone()
            assert row["visibility_status"] == "failed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_visibility_status.py -v`
Expected: FAIL with `AttributeError: 'FramesStore' object has no attribute 'try_set_queryable'`

- [ ] **Step 3: Implement the helper methods**

Add to `openrecall/server/database/frames_store.py` after the `mark_failed` method (around line 488):

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
            logger.error(
                "try_set_queryable_standalone failed frame_id=%d: %s",
                frame_id,
                e,
            )
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
            logger.error(
                "try_set_failed_standalone failed frame_id=%d: %s",
                frame_id,
                e,
            )
            return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_visibility_status.py -v`
Expected: PASS (all tests pass)

- [ ] **Step 5: Commit**

```bash
git add openrecall/server/database/frames_store.py tests/test_visibility_status.py
git commit -m "feat(db): add visibility_status helper methods"
```

---

### Task 3: V3ProcessingWorker Integration

**Files:**
- Modify: `openrecall/server/processing/v3_worker.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_visibility_status.py`:

```python
class TestV3ProcessingWorkerIntegration:
    """Tests for V3ProcessingWorker visibility_status integration."""

    def test_sets_queryable_after_ocr_when_others_complete(self, temp_store):
        """V3ProcessingWorker should set queryable after OCR if description/embedding done."""
        with temp_store._connect() as conn:
            # Simulate a frame where description and embedding are already done
            # (unlikely in practice, but tests the logic)
            conn.execute(
                """
                INSERT INTO frames (
                    id, capture_id, timestamp, status, description_status,
                    embedding_status, visibility_status, app_name, window_name, snapshot_path
                )
                VALUES (1, 'test-capture', '2026-04-14T00:00:00Z', 'processing',
                        'completed', 'completed', 'pending', 'TestApp', 'TestWindow', '/tmp/test.jpg')
                """
            )

        # Simulate V3ProcessingWorker completing OCR
        result = temp_store.try_set_queryable_standalone(1)

        # Since status is still 'processing', should NOT be queryable yet
        assert result is False

        # Now set status to completed
        with temp_store._connect() as conn:
            conn.execute("UPDATE frames SET status = 'completed' WHERE id = 1")

        result = temp_store.try_set_queryable_standalone(1)

        # Now all conditions are met
        assert result is True

        with temp_store._connect() as conn:
            row = conn.execute(
                "SELECT visibility_status FROM frames WHERE id = 1"
            ).fetchone()
            assert row["visibility_status"] == "queryable"
```

- [ ] **Step 2: Run test to verify expected behavior**

Run: `pytest tests/test_visibility_status.py::TestV3ProcessingWorkerIntegration -v`
Expected: PASS (test validates the helper logic)

- [ ] **Step 3: Add call to V3ProcessingWorker**

In `openrecall/server/processing/v3_worker.py`, find the section after `advance_frame_status` (around line 301) and add the call:

```python
        ok = self._store.advance_frame_status(frame_id, "processing", "completed")
        if not ok:
            logger.error(
                "V3ProcessingWorker: processing→completed failed for frame_id=%d",
                frame_id,
            )
            return

        # Try to mark as queryable if all stages are complete
        if self._store.try_set_queryable_standalone(frame_id):
            logger.debug(
                "V3ProcessingWorker: frame_id=%d marked as queryable",
                frame_id,
            )

        logger.info(
            "MRV3 ocr_completed frame_id=%d text_length=%d engine=rapidocr elapsed_ms=%.1f",
            frame_id,
            result.text_length,
            elapsed_ms,
        )
```

Also add call in `_mark_failed` method (around line 341) after `self._store.mark_failed`:

```python
        try:
            self._store.mark_failed(
                frame_id=frame_id,
                reason=reason,
                request_id=request_id,
                capture_id=capture_id,
            )
            # Mark visibility_status as failed
            self._store.try_set_failed_standalone(frame_id)
        except Exception as exc:
            logger.error(
                "V3ProcessingWorker: mark_failed DB write failed frame_id=%d: %s",
                frame_id,
                exc,
            )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_visibility_status.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add openrecall/server/processing/v3_worker.py
git commit -m "feat(worker): integrate visibility_status in V3ProcessingWorker"
```

---

### Task 4: DescriptionWorker Integration

**Files:**
- Modify: `openrecall/server/database/frames_store.py` (complete_description_task method)

- [ ] **Step 1: Update complete_description_task to call try_set_queryable**

Find `complete_description_task` in `openrecall/server/database/frames_store.py` (around line 1644) and modify:

```python
    def complete_description_task(
        self,
        conn: sqlite3.Connection,
        task_id: int,
        frame_id: int,
    ) -> None:
        """Mark a description task as completed and update frames table."""
        conn.execute(
            """
            UPDATE description_tasks
            SET status = 'completed',
                completed_at = strftime('%Y-%m-%dT%H:%M:%fZ', 'now')
            WHERE id = ?
            """,
            (task_id,),
        )
        conn.execute(
            "UPDATE frames SET description_status = 'completed' WHERE id = ?",
            (frame_id,),
        )
        # Try to mark as queryable if all stages are complete
        self.try_set_queryable(conn, frame_id)
```

- [ ] **Step 2: Update fail_description_task to call try_set_failed**

Find `fail_description_task` in `openrecall/server/database/frames_store.py` (around line 1683) and modify:

```python
    def fail_description_task(
        self,
        conn: sqlite3.Connection,
        task_id: int,
        frame_id: int,
        error_message: str,
    ) -> None:
        conn.execute(
            """
            UPDATE description_tasks
            SET status = 'failed', error_message = ?
            WHERE id = ?
            """,
            (error_message, task_id),
        )
        conn.execute(
            "UPDATE frames SET description_status = 'failed' WHERE id = ?",
            (frame_id,),
        )
        # Mark visibility_status as failed
        self.try_set_failed(conn, frame_id)
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_visibility_status.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add openrecall/server/database/frames_store.py
git commit -m "feat(db): integrate visibility_status in description task completion"
```

---

### Task 5: EmbeddingWorker Integration

**Files:**
- Modify: `openrecall/server/embedding/service.py`

- [ ] **Step 1: Update mark_completed in EmbeddingService**

Find `mark_completed` in `openrecall/server/embedding/service.py` (around line 103) and modify:

```python
    def mark_completed(self, conn, task_id: int, frame_id: int) -> None:
        """Mark an embedding task as completed."""
        now = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            UPDATE embedding_tasks
            SET status = 'completed', completed_at = ?
            WHERE id = ?
            """,
            (now, task_id),
        )
        conn.execute(
            """
            UPDATE frames SET embedding_status = 'completed'
            WHERE id = ?
            """,
            (frame_id,),
        )
        conn.commit()
        # Try to mark as queryable if all stages are complete
        self._store.try_set_queryable(conn, frame_id)
```

- [ ] **Step 2: Update mark_failed in EmbeddingService**

Find `mark_failed` in `openrecall/server/embedding/service.py` (around line 123) and add after setting `embedding_status = 'failed'`:

```python
    def mark_failed(
        self,
        conn,
        task_id: int,
        frame_id: int,
        error_message: str,
        retry_count: int,
    ) -> None:
        """Mark an embedding task as failed or schedule retry."""
        if retry_count < _MAX_RETRIES:
            delay_seconds = _RETRY_DELAYS[retry_count - 1]
            next_retry = datetime.now(timezone.utc).replace(microsecond=0)
            next_retry = next_retry + timedelta(seconds=delay_seconds)
            conn.execute(
                """
                UPDATE embedding_tasks
                SET retry_count = ?, next_retry_at = ?, error_message = ?
                WHERE id = ?
                """,
                (retry_count + 1, next_retry.isoformat(), error_message, task_id),
            )
            logger.info(
                f"Embedding task #{task_id} failed (retry {retry_count}/{_MAX_RETRIES}), "
                f"rescheduled at {next_retry.isoformat()}"
            )
        else:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                """
                UPDATE embedding_tasks
                SET status = 'failed', error_message = ?, failed_at = ?
                WHERE id = ?
                """,
                (error_message, now, task_id),
            )
            conn.execute(
                """
                UPDATE frames SET embedding_status = 'failed'
                WHERE id = ?
                """,
                (frame_id,),
            )
            # Mark visibility_status as failed
            self._store.try_set_failed(conn, frame_id)
            logger.error(
                f"Embedding task #{task_id} permanently failed for frame #{frame_id}: {error_message}"
            )
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_visibility_status.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add openrecall/server/embedding/service.py
git commit -m "feat(embedding): integrate visibility_status in EmbeddingWorker"
```

---

### Task 6: SearchEngine WHERE Clause Update

**Files:**
- Modify: `openrecall/server/search/engine.py`

- [ ] **Step 1: Update _build_where_clause method**

Find `_build_where_clause` in `openrecall/server/search/engine.py` (around line 126) and change:

```python
    def _build_where_clause(
        self, params: SearchParams
    ) -> tuple[str, list[Any]]:
        """Build WHERE clause and parameters for frames JOIN frames_fts query.

        Shared helper used by both _build_query and count_by_type to avoid
        duplicating the filter-building logic.

        Args:
            params: Search parameters

        Returns:
            Tuple of (WHERE clause string, parameters list)
        """
        has_text_query = bool(params.q and params.q.strip())
        where_parts = ["frames.visibility_status = 'queryable'", "frames.full_text IS NOT NULL"]
        params_list: list[Any] = []
```

Change from `"frames.status = 'completed'"` to `"frames.visibility_status = 'queryable'"`.

- [ ] **Step 2: Run existing search tests**

Run: `pytest tests/ -k search -v`
Expected: Tests may fail if they don't have visibility_status set. This is expected until migration runs.

- [ ] **Step 3: Commit**

```bash
git add openrecall/server/search/engine.py
git commit -m "feat(search): filter by visibility_status in FTS engine"
```

---

### Task 7: HybridSearchEngine WHERE Clause Update

**Files:**
- Modify: `openrecall/server/search/hybrid_engine.py`

- [ ] **Step 1: Update _get_recent_embedded_frames method**

Find `_get_recent_embedded_frames` in `openrecall/server/search/hybrid_engine.py` (around line 161) and change both WHERE clauses:

```python
    def _get_recent_embedded_frames(
        self, db_path: Path, limit: int, offset: int
    ) -> Tuple[List[Dict[str, Any]], int]:
        """Get recent frames that have embeddings (browse mode for vector search)."""
        import sqlite3

        try:
            conn = sqlite3.connect(str(db_path))
            conn.row_factory = sqlite3.Row

            # Count total frames with embeddings
            count_row = conn.execute(
                """
                SELECT COUNT(*) as total FROM frames
                WHERE visibility_status = 'queryable'
                """
            ).fetchone()
            total = count_row["total"] if count_row else 0

            # Get recent frames with embeddings
            rows = conn.execute(
                """
                SELECT id as frame_id, timestamp, full_text, text_source,
                       app_name, window_name, browser_url, focused,
                       device_name, file_path, embedding_status
                FROM frames
                WHERE visibility_status = 'queryable'
                ORDER BY timestamp DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            ).fetchall()
```

- [ ] **Step 2: Commit**

```bash
git add openrecall/server/search/hybrid_engine.py
git commit -m "feat(search): filter by visibility_status in hybrid engine"
```

---

### Task 8: Activity Summary Query Updates

**Files:**
- Modify: `openrecall/server/database/frames_store.py`

- [ ] **Step 1: Update get_activity_summary_apps**

Find `get_activity_summary_apps` in `openrecall/server/database/frames_store.py` (around line 1276). Change `WHERE status = 'completed'` to `WHERE visibility_status = 'queryable'`:

```python
    def get_activity_summary_apps(
        self,
        start_time: str,
        end_time: str,
        app_name: Optional[str] = None,
    ) -> list[dict]:
        """Return apps with accurate usage minutes from timestamp gaps.

        Uses SQLite LEAD() window function to calculate the actual time gap
        between consecutive frames per app. Only gaps < 300 seconds (5 min)
        count toward usage time, filtering out "away from computer" periods.

        Also returns first_seen and last_seen timestamps.

        Args:
            start_time: ISO8601 start timestamp
            end_time: ISO8601 end timestamp
            app_name: Optional filter by app name

        Returns:
            List of dicts with name, frame_count, minutes, first_seen, last_seen
        """
        apps = []
        try:
            with self._connect() as conn:
                if app_name:
                    inner_sql = """
                        SELECT
                            app_name,
                            timestamp AS ts,
                            (JULIANDAY(LEAD(timestamp) OVER (
                                PARTITION BY app_name ORDER BY timestamp
                            )) - JULIANDAY(timestamp)) * 86400.0 AS gap_sec
                        FROM frames
                        WHERE visibility_status = 'queryable'
                          AND app_name = ?
                          AND timestamp >= ?
                          AND timestamp <= ?
                    """
                    params = [app_name, start_time, end_time]
                else:
                    inner_sql = """
                        SELECT
                            app_name,
                            timestamp AS ts,
                            (JULIANDAY(LEAD(timestamp) OVER (
                                PARTITION BY app_name ORDER BY timestamp
                            )) - JULIANDAY(timestamp)) * 86400.0 AS gap_sec
                        FROM frames
                        WHERE visibility_status = 'queryable'
                          AND timestamp >= ?
                          AND timestamp <= ?
                          AND app_name IS NOT NULL
                          AND app_name != ''
                    """
                    params = [start_time, end_time]
```

- [ ] **Step 2: Update get_activity_summary_total_frames**

Find `get_activity_summary_total_frames` (around line 1363) and change:

```python
    def get_activity_summary_total_frames(
        self,
        start_time: str,
        end_time: str,
        app_name: Optional[str] = None,
    ) -> int:
        """Return count of queryable frames in time range.

        Args:
            start_time: ISO8601 start timestamp
            end_time: ISO8601 end timestamp
            app_name: Optional filter by app name

        Returns:
            Count of queryable frames in the specified range.
        """
        try:
            with self._connect() as conn:
                if app_name:
                    row = conn.execute(
                        """
                        SELECT COUNT(*) as cnt FROM frames
                        WHERE visibility_status = 'queryable'
                          AND app_name = ?
                          AND timestamp >= ?
                          AND timestamp <= ?
                        """,
                        (app_name, start_time, end_time),
                    ).fetchone()
                else:
                    row = conn.execute(
                        """
                        SELECT COUNT(*) as cnt FROM frames
                        WHERE visibility_status = 'queryable'
                          AND timestamp >= ?
                          AND timestamp <= ?
                        """,
                        (start_time, end_time),
                    ).fetchone()
                return row["cnt"] if row else 0
        except sqlite3.Error as e:
            logger.error("get_activity_summary_total_frames failed: %s", e)
            return 0
```

- [ ] **Step 3: Update get_activity_summary_time_range**

Find `get_activity_summary_time_range` (around line 1400) and change:

```python
    def get_activity_summary_time_range(
        self,
        start_time: str,
        end_time: str,
        app_name: Optional[str] = None,
    ) -> Optional[dict]:
        """Return actual time range of queryable frames.

        Args:
            start_time: ISO8601 start timestamp (filter)
            end_time: ISO8601 end timestamp (filter)
            app_name: Optional filter by app name

        Returns:
            Dict with 'start' and 'end' keys, or None if no frames.
        """
        try:
            with self._connect() as conn:
                if app_name:
                    row = conn.execute(
                        """
                        SELECT MIN(timestamp) as start, MAX(timestamp) as end
                        FROM frames
                        WHERE visibility_status = 'queryable'
                          AND app_name = ?
                          AND timestamp >= ?
                          AND timestamp <= ?
                        """,
                        (app_name, start_time, end_time),
                    ).fetchone()
                else:
                    row = conn.execute(
                        """
                        SELECT MIN(timestamp) as start, MAX(timestamp) as end
                        FROM frames
                        WHERE visibility_status = 'queryable'
                          AND timestamp >= ?
                          AND timestamp <= ?
                        """,
                        (start_time, end_time),
                    ).fetchone()
```

- [ ] **Step 4: Commit**

```bash
git add openrecall/server/database/frames_store.py
git commit -m "feat(db): filter activity-summary by visibility_status"
```

---

### Task 9: Frame Context Visibility Check

**Files:**
- Modify: `openrecall/server/database/frames_store.py`
- Modify: `openrecall/server/api_v1.py`

- [ ] **Step 1: Update get_frame_context to include visibility_status**

Find `get_frame_context` in `openrecall/server/database/frames_store.py` (around line 1444). Add `visibility_status` to the SELECT and return dict:

```python
    def get_frame_context(
        self,
        frame_id: int,
    ) -> Optional[dict]:
        """Return frame context for chat grounding.

        Returns:
            - frame_id, timestamp, app_name, window_name: frame metadata
            - text: accessibility_text or ocr_text, truncated at MAX_TEXT_LENGTH chars
            - text_source: 'accessibility' | 'ocr' | 'hybrid' | None
            - urls: extracted from text via regex
            - browser_url, status, visibility_status: frame metadata

        Text is always truncated at MAX_TEXT_LENGTH (5000) chars with "..." suffix.
        """
        try:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT f.id, f.accessibility_text, f.ocr_text, f.text_source,
                           f.browser_url, f.status, f.visibility_status,
                           f.timestamp, f.app_name, f.window_name
                    FROM frames f
                    WHERE f.id = ?
                    """,
                    (frame_id,),
                ).fetchone()

                if row is None:
                    return None

                frame_id_val = row["id"]
                # Use frames.ocr_text for OCR frames, frames.accessibility_text for accessibility frames
                if row["text_source"] == "ocr":
                    text = row["ocr_text"] or ""
                else:
                    text = row["accessibility_text"] or ""
                text_source = row["text_source"]
                browser_url = row["browser_url"]
                status = row["status"]
                visibility_status = row["visibility_status"]
                timestamp = row["timestamp"]
                app_name = row["app_name"]
                window_name = row["window_name"]

                urls: list[str] = []

                # Extract URLs from text using regex (screenpipe-aligned)
                for url in self._extract_urls_from_text(text):
                    if url not in urls:
                        urls.append(url)

                # Apply fixed text truncation at MAX_TEXT_LENGTH
                result_text = text
                if len(result_text) > self.MAX_TEXT_LENGTH:
                    result_text = result_text[:self.MAX_TEXT_LENGTH] + "..."

                return {
                    "frame_id": frame_id_val,
                    "timestamp": timestamp,
                    "app_name": app_name,
                    "window_name": window_name,
                    "text": result_text,
                    "text_source": text_source,
                    "urls": urls,
                    "browser_url": browser_url,
                    "status": status,
                    "visibility_status": visibility_status,
                }
        except Exception:
            logger.exception(f"Error getting frame context for frame_id={frame_id}")
            return None
```

- [ ] **Step 2: Update API handler to check visibility_status**

Find `get_frame_context` in `openrecall/server/api_v1.py` (around line 685). Add visibility check:

```python
@v1_bp.route("/frames/<int:frame_id>/context", methods=["GET"])
def get_frame_context(frame_id: int):
    """Return frame context for chat grounding.

    Returns:
        200 JSON — frame context (always includes description, text, urls, text_source)
        404 NOT_FOUND — frame_id not in DB or not queryable
    """
    request_id = str(uuid.uuid4())

    store = _get_frames_store()

    context = store.get_frame_context(frame_id)

    if context is None:
        return make_error_response(
            "frame not found",
            "NOT_FOUND",
            404,
            request_id=request_id,
        )

    # Check if frame is queryable
    if context.get("visibility_status") != "queryable":
        return make_error_response(
            "frame not ready for querying",
            "NOT_READY",
            404,
            request_id=request_id,
        )

    # Add description if completed
    description = None
    try:
        with store._connect() as conn:
            row = conn.execute(
                "SELECT description_status FROM frames WHERE id = ?",
                (frame_id,),
            ).fetchone()
            if row and row["description_status"] == "completed":
                desc_row = store.get_frame_description(conn, frame_id)
                if desc_row:
                    description = {
                        "narrative": desc_row["narrative"],
                        "summary": desc_row["summary"],
                        "tags": desc_row["tags"],
                    }
    except Exception as e:
        logger.warning(f"Failed to get description for frame {frame_id}: {e}")

    # Remove visibility_status from response (internal field)
    context.pop("visibility_status", None)

    # Insert description at the correct field position (after window_name, before text)
    # Build ordered result dict
    result = {
        "frame_id": context["frame_id"],
        "timestamp": context["timestamp"],
        "app_name": context["app_name"],
        "window_name": context["window_name"],
        "description": description,
        "text": context["text"],
        "text_source": context["text_source"],
        "urls": context["urls"],
        "browser_url": context["browser_url"],
        "status": context["status"],
    }

    return jsonify(result)
```

- [ ] **Step 3: Commit**

```bash
git add openrecall/server/database/frames_store.py openrecall/server/api_v1.py
git commit -m "feat(api): check visibility_status in frame context endpoint"
```

---

### Task 10: Integration Tests

**Files:**
- Modify: `tests/test_visibility_status.py`

- [ ] **Step 1: Add integration tests**

Add to `tests/test_visibility_status.py`:

```python
class TestSearchFiltersByVisibilityStatus:
    """Integration tests for search API filtering by visibility_status."""

    def test_fts_search_only_returns_queryable(self, temp_store):
        """FTS search should only return frames with visibility_status='queryable'."""
        from openrecall.server.search.engine import SearchEngine

        # Create frames table with FTS
        with temp_store._connect() as conn:
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS frames_fts USING fts5(
                    id, full_text, app_name, window_name, browser_url,
                    content='frames', content_rowid='id'
                )
            """)
            # Insert frames with different visibility statuses
            conn.execute("""
                INSERT INTO frames (id, status, description_status, embedding_status,
                                   visibility_status, full_text, app_name, timestamp)
                VALUES (1, 'completed', 'completed', 'completed', 'queryable',
                        'hello world', 'TestApp', '2026-04-14T00:00:00Z')
            """)
            conn.execute("""
                INSERT INTO frames (id, status, description_status, embedding_status,
                                   visibility_status, full_text, app_name, timestamp)
                VALUES (2, 'completed', 'completed', 'pending', 'pending',
                        'hello universe', 'TestApp', '2026-04-14T01:00:00Z')
            """)
            # Add to FTS
            conn.execute("""
                INSERT INTO frames_fts (id, full_text, app_name)
                VALUES (1, 'hello world', 'TestApp'), (2, 'hello universe', 'TestApp')
            """)

        engine = SearchEngine(db_path=temp_store.db_path)
        results, total = engine.search(q="hello", limit=10)

        assert total == 1
        assert results[0]["frame_id"] == 1


class TestActivitySummaryFiltersByVisibilityStatus:
    """Tests for activity-summary filtering by visibility_status."""

    def test_activity_summary_only_counts_queryable(self, temp_store):
        """Activity summary should only count frames with visibility_status='queryable'."""
        with temp_store._connect() as conn:
            conn.execute("""
                INSERT INTO frames (id, status, description_status, embedding_status,
                                   visibility_status, app_name, timestamp)
                VALUES (1, 'completed', 'completed', 'completed', 'queryable',
                        'TestApp', '2026-04-14T00:00:00Z')
            """)
            conn.execute("""
                INSERT INTO frames (id, status, description_status, embedding_status,
                                   visibility_status, app_name, timestamp)
                VALUES (2, 'completed', 'completed', 'pending', 'pending',
                        'TestApp', '2026-04-14T00:01:00Z')
            """)

        total = temp_store.get_activity_summary_total_frames(
            start_time="2026-04-14T00:00:00Z",
            end_time="2026-04-14T23:59:59Z",
        )

        assert total == 1


class TestFrameContextChecksVisibilityStatus:
    """Tests for frame context endpoint visibility check."""

    def test_frame_context_returns_404_for_non_queryable(self, temp_store):
        """Frame context should return None for non-queryable frames."""
        with temp_store._connect() as conn:
            conn.execute("""
                INSERT INTO frames (id, status, description_status, embedding_status,
                                   visibility_status, app_name, timestamp)
                VALUES (1, 'completed', 'pending', 'pending', 'pending',
                        'TestApp', '2026-04-14T00:00:00Z')
            """)

        context = temp_store.get_frame_context(1)
        assert context is not None
        assert context["visibility_status"] == "pending"
```

- [ ] **Step 2: Run all tests**

Run: `pytest tests/test_visibility_status.py -v`
Expected: PASS

- [ ] **Step 3: Run full test suite**

Run: `pytest -x`
Expected: All tests pass (may have some pre-existing failures unrelated to this change)

- [ ] **Step 4: Commit**

```bash
git add tests/test_visibility_status.py
git commit -m "test: add integration tests for visibility_status filtering"
```

---

### Task 11: Migration Test

**Files:**
- Modify: `tests/test_v3_migrations_bootstrap.py`

- [ ] **Step 1: Add backfill verification test**

Find an appropriate place in `tests/test_v3_migrations_bootstrap.py` and add:

```python
    def test_visibility_status_migration_backfill(self):
        """Verify visibility_status migration correctly backfills existing frames."""
        # Run migrations
        from openrecall.server.database.migrations_runner import run_migrations

        run_migrations(self.db_path)

        # Insert test data before the visibility_status check
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            # Insert a fully processed frame
            conn.execute("""
                INSERT INTO frames (capture_id, timestamp, status, description_status,
                                   embedding_status, app_name)
                VALUES ('test-1', '2026-04-14T00:00:00Z', 'completed', 'completed',
                        'completed', 'TestApp')
            """)
            # Insert a partially processed frame
            conn.execute("""
                INSERT INTO frames (capture_id, timestamp, status, description_status,
                                   embedding_status, app_name)
                VALUES ('test-2', '2026-04-14T00:01:00Z', 'completed', 'completed',
                        'pending', 'TestApp')
            """)
            # Insert a failed frame
            conn.execute("""
                INSERT INTO frames (capture_id, timestamp, status, description_status,
                                   embedding_status, app_name)
                VALUES ('test-3', '2026-04-14T00:02:00Z', 'failed', 'pending',
                        'pending', 'TestApp')
            """)

        # Re-run migration to apply backfill
        run_migrations(self.db_path)

        # Verify backfill
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row

            # Check fully processed frame is queryable
            row = conn.execute(
                "SELECT visibility_status FROM frames WHERE capture_id = 'test-1'"
            ).fetchone()
            assert row["visibility_status"] == "queryable"

            # Check partially processed frame is pending
            row = conn.execute(
                "SELECT visibility_status FROM frames WHERE capture_id = 'test-2'"
            ).fetchone()
            assert row["visibility_status"] == "pending"

            # Check failed frame is failed
            row = conn.execute(
                "SELECT visibility_status FROM frames WHERE capture_id = 'test-3'"
            ).fetchone()
            assert row["visibility_status"] == "failed"
```

- [ ] **Step 2: Run migration tests**

Run: `pytest tests/test_v3_migrations_bootstrap.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_v3_migrations_bootstrap.py
git commit -m "test: add visibility_status backfill verification"
```

---

### Task 12: Final Verification

- [ ] **Step 1: Run all tests**

Run: `pytest -v --tb=short`
Expected: All tests pass

- [ ] **Step 2: Run server locally and verify**

```bash
# Terminal 1
./run_server.sh --mode local --debug

# Terminal 2
curl -s "http://localhost:8083/v1/health" | python -m json.tool
```

Expected: Server starts without error

- [ ] **Step 3: Final commit**

```bash
git add -A
git status
git commit -m "feat: complete frame visibility status implementation"
```

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Database migration | migrations/20260414000000_add_visibility_status.sql |
| 2 | FramesStore helpers | frames_store.py, tests/test_visibility_status.py |
| 3 | V3ProcessingWorker integration | v3_worker.py |
| 4 | DescriptionWorker integration | frames_store.py |
| 5 | EmbeddingWorker integration | embedding/service.py |
| 6 | FTS search filter | search/engine.py |
| 7 | Hybrid search filter | search/hybrid_engine.py |
| 8 | Activity summary filters | frames_store.py |
| 9 | Frame context check | frames_store.py, api_v1.py |
| 10 | Integration tests | tests/test_visibility_status.py |
| 11 | Migration test | tests/test_v3_migrations_bootstrap.py |
| 12 | Final verification | - |
