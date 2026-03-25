# FTS Unification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Consolidate OCR text and accessibility text into a single `frames.full_text` column, indexed by a rebuilt `frames_fts` table, aligning with screenpipe's design.

**Architecture:** Add `full_text` column to frames, rebuild FTS triggers, simplify search engine to single query path, drop old FTS tables.

**Tech Stack:** Python, SQLite, FTS5, Flask

**Spec:** `docs/superpowers/specs/2026-03-25-fts-unification-design.md`

---

## File Structure

| File | Action | Description |
|------|--------|-------------|
| `openrecall/server/database/migrations/20260325120000_consolidate_fts_to_full_text.sql` | Create | Migration file |
| `openrecall/server/database/frames_store.py` | Modify | Add `full_text` to inserts/updates |
| `openrecall/server/processing/v3_worker.py` | Modify | Update `full_text` after OCR |
| `openrecall/server/search/engine.py` | Modify | Simplify to single query path |
| `openrecall/server/api_v1.py` | Modify | Deprecation log for `content_type` |
| `tests/test_v3_migrations_bootstrap.py` | Modify | Add migration test |
| `tests/test_p1_s4_search_fts.py` | Modify | Update for new query path |

---

## Task 1: Create Migration File

**Files:**
- Create: `openrecall/server/database/migrations/20260325120000_consolidate_fts_to_full_text.sql`
- Test: `tests/test_v3_migrations_bootstrap.py`

- [ ] **Step 1: Write the migration file**

Create `openrecall/server/database/migrations/20260325120000_consolidate_fts_to_full_text.sql`:

```sql
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
```

- [ ] **Step 2: Write migration test**

Add to `tests/test_v3_migrations_bootstrap.py`:

```python
import pytest
import sqlite3
import tempfile
from pathlib import Path


class TestFtsUnificationMigration:
    """Tests for 20260325120000_consolidate_fts_to_full_text.sql migration."""

    @pytest.fixture
    def db_path(self, tmp_path):
        """Create a fresh database with initial schema."""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript(
            Path("openrecall/server/database/migrations/20260227000001_initial_schema.sql").read_text()
        )
        conn.close()
        return db_path

    def _run_migration(self, db_path: Path):
        """Run the FTS unification migration."""
        conn = sqlite3.connect(str(db_path))
        migration_sql = Path(
            "openrecall/server/database/migrations/20260325120000_consolidate_fts_to_full_text.sql"
        ).read_text()
        conn.executescript(migration_sql)
        conn.close()

    def test_adds_full_text_column(self, db_path):
        """Verify full_text column is added."""
        self._run_migration(db_path)

        conn = sqlite3.connect(str(db_path))
        cursor = conn.execute("PRAGMA table_info(frames)")
        columns = {row[1] for row in cursor.fetchall()}
        conn.close()

        assert "full_text" in columns

    def test_backfill_from_accessibility_text(self, db_path):
        """Verify backfill from frames.accessibility_text."""
        conn = sqlite3.connect(str(db_path))
        # Insert a frame with accessibility_text
        conn.execute(
            """
            INSERT INTO frames (capture_id, timestamp, accessibility_text, text_source, status)
            VALUES ('test-1', '2026-03-25T12:00:00Z', 'Hello from AX', 'accessibility', 'completed')
            """
        )
        conn.commit()
        conn.close()

        self._run_migration(db_path)

        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT full_text FROM frames WHERE capture_id = 'test-1'"
        ).fetchone()
        conn.close()

        assert row[0] == "Hello from AX"

    def test_backfill_from_ocr_text_column(self, db_path):
        """Verify backfill from frames.ocr_text column."""
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            """
            INSERT INTO frames (capture_id, timestamp, ocr_text, text_source, status)
            VALUES ('test-2', '2026-03-25T12:00:00Z', 'Hello from OCR', 'ocr', 'completed')
            """
        )
        conn.commit()
        conn.close()

        self._run_migration(db_path)

        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT full_text FROM frames WHERE capture_id = 'test-2'"
        ).fetchone()
        conn.close()

        assert row[0] == "Hello from OCR"

    def test_backfill_from_ocr_text_table(self, db_path):
        """Verify backfill from ocr_text table."""
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            """
            INSERT INTO frames (capture_id, timestamp, text_source, status)
            VALUES ('test-3', '2026-03-25T12:00:00Z', 'ocr', 'completed')
            """
        )
        frame_id = conn.execute(
            "SELECT id FROM frames WHERE capture_id = 'test-3'"
        ).fetchone()[0]
        conn.execute(
            "INSERT INTO ocr_text (frame_id, text) VALUES (?, 'OCR table text')",
            (frame_id,),
        )
        conn.commit()
        conn.close()

        self._run_migration(db_path)

        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT full_text FROM frames WHERE capture_id = 'test-3'"
        ).fetchone()
        conn.close()

        assert row[0] == "OCR table text"

    def test_hybrid_merge_both_columns(self, db_path):
        """Verify merge when both accessibility_text and ocr_text columns exist."""
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            """
            INSERT INTO frames (capture_id, timestamp, accessibility_text, ocr_text, text_source, status)
            VALUES ('test-4', '2026-03-25T12:00:00Z', 'AX text', 'OCR text', 'accessibility', 'completed')
            """
        )
        conn.commit()
        conn.close()

        self._run_migration(db_path)

        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT full_text FROM frames WHERE capture_id = 'test-4'"
        ).fetchone()
        conn.close()

        assert row[0] == "AX text\nOCR text"

    def test_fts_table_has_full_text(self, db_path):
        """Verify frames_fts indexes full_text."""
        conn = sqlite3.connect(str(db_path))
        conn.execute(
            """
            INSERT INTO frames (capture_id, timestamp, accessibility_text, text_source, status)
            VALUES ('test-5', '2026-03-25T12:00:00Z', 'Searchable text', 'accessibility', 'completed')
            """
        )
        conn.commit()
        conn.close()

        self._run_migration(db_path)

        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT full_text FROM frames_fts WHERE frames_fts MATCH 'Searchable'"
        ).fetchone()
        conn.close()

        assert row is not None
        assert "Searchable" in row[0]

    def test_old_fts_tables_dropped(self, db_path):
        """Verify old FTS tables are dropped."""
        self._run_migration(db_path)

        conn = sqlite3.connect(str(db_path))
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        conn.close()

        assert "ocr_text_fts" not in tables
        assert "accessibility_fts" not in tables

    def test_insert_trigger_populates_fts(self, db_path):
        """Verify INSERT trigger populates frames_fts."""
        self._run_migration(db_path)

        conn = sqlite3.connect(str(db_path))
        conn.execute(
            """
            INSERT INTO frames (capture_id, timestamp, full_text, app_name, status)
            VALUES ('test-6', '2026-03-25T12:00:00Z', 'New frame text', 'TestApp', 'completed')
            """
        )
        conn.commit()

        row = conn.execute(
            "SELECT full_text FROM frames_fts WHERE frames_fts MATCH 'New frame'"
        ).fetchone()
        conn.close()

        assert row is not None

    def test_update_trigger_updates_fts(self, db_path):
        """Verify UPDATE trigger updates frames_fts."""
        self._run_migration(db_path)

        conn = sqlite3.connect(str(db_path))
        conn.execute(
            """
            INSERT INTO frames (capture_id, timestamp, full_text, app_name, status)
            VALUES ('test-7', '2026-03-25T12:00:00Z', 'Original text', 'TestApp', 'completed')
            """
        )
        conn.commit()

        conn.execute(
            "UPDATE frames SET full_text = 'Updated text' WHERE capture_id = 'test-7'"
        )
        conn.commit()

        # Old text should not be found
        row_old = conn.execute(
            "SELECT full_text FROM frames_fts WHERE frames_fts MATCH 'Original'"
        ).fetchone()
        # New text should be found
        row_new = conn.execute(
            "SELECT full_text FROM frames_fts WHERE frames_fts MATCH 'Updated'"
        ).fetchone()
        conn.close()

        assert row_old is None
        assert row_new is not None
```

- [ ] **Step 3: Run migration test**

Run: `pytest tests/test_v3_migrations_bootstrap.py::TestFtsUnificationMigration -v`

Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add openrecall/server/database/migrations/20260325120000_consolidate_fts_to_full_text.sql tests/test_v3_migrations_bootstrap.py
git commit -m "feat(db): add FTS unification migration

Consolidates OCR text and accessibility text into frames.full_text.
Rebuilds frames_fts to index full_text + metadata.
Drops ocr_text_fts and accessibility_fts tables."
```

---

## Task 2: Update FramesStore for full_text

**Files:**
- Modify: `openrecall/server/database/frames_store.py:926-1006`
- Test: `tests/test_p1_s3_text_source_mark.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_p1_s3_text_source_mark.py`:

```python
def test_complete_accessibility_frame_sets_full_text(tmp_db_path):
    """Verify complete_accessibility_frame sets full_text."""
    from openrecall.server.database.frames_store import FramesStore

    store = FramesStore(db_path=tmp_db_path)

    # Create a pending frame
    conn = sqlite3.connect(str(tmp_db_path))
    conn.execute(
        """
        INSERT INTO frames (capture_id, timestamp, status)
        VALUES ('test-ax-full', '2026-03-25T12:00:00Z', 'pending')
        """
    )
    conn.commit()
    frame_id = conn.execute(
        "SELECT id FROM frames WHERE capture_id = 'test-ax-full'"
    ).fetchone()[0]
    conn.close()

    # Complete with accessibility
    store.complete_accessibility_frame(
        frame_id=frame_id,
        text="Accessibility content here",
        browser_url=None,
        content_hash=None,
        simhash=None,
        accessibility_tree_json="[]",
        accessibility_text_content="Accessibility content here",
        accessibility_node_count=1,
        accessibility_truncated=False,
        elements=[],
    )

    # Verify full_text is set
    conn = sqlite3.connect(str(tmp_db_path))
    row = conn.execute(
        "SELECT full_text, text_source FROM frames WHERE id = ?", (frame_id,)
    ).fetchone()
    conn.close()

    assert row[0] == "Accessibility content here"
    assert row[1] == "accessibility"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_p1_s3_text_source_mark.py::test_complete_accessibility_frame_sets_full_text -v`

Expected: FAIL with "AssertionError: assert None == 'Accessibility content here'"

- [ ] **Step 3: Update complete_accessibility_frame to set full_text**

In `openrecall/server/database/frames_store.py`, modify the `complete_accessibility_frame` method around line 976-998:

```python
                # Update frames table
                conn.execute(
                    """
                    UPDATE frames SET
                        accessibility_text = ?,
                        full_text = ?,
                        text_source = 'accessibility',
                        accessibility_tree_json = ?,
                        browser_url = COALESCE(?, browser_url),
                        content_hash = ?,
                        simhash = ?,
                        status = 'completed',
                        processed_at = ?
                    WHERE id = ?
                    """,
                    (
                        text,
                        text,  # full_text = accessibility_text
                        accessibility_tree_json,
                        browser_url,
                        content_hash,
                        simhash,
                        now,
                        frame_id,
                    ),
                )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_p1_s3_text_source_mark.py::test_complete_accessibility_frame_sets_full_text -v`

Expected: PASS

- [ ] **Step 5: Add test for update_full_text method**

Add to `tests/test_p1_s3_text_source_mark.py`:

```python
def test_update_full_text_after_ocr(tmp_db_path):
    """Verify update_full_text sets full_text for OCR frames."""
    from openrecall.server.database.frames_store import FramesStore

    store = FramesStore(db_path=tmp_db_path)

    # Create a frame
    conn = sqlite3.connect(str(tmp_db_path))
    conn.execute(
        """
        INSERT INTO frames (capture_id, timestamp, status, ocr_text)
        VALUES ('test-ocr-full', '2026-03-25T12:00:00Z', 'completed', 'OCR content')
        """
    )
    conn.commit()
    frame_id = conn.execute(
        "SELECT id FROM frames WHERE capture_id = 'test-ocr-full'"
    ).fetchone()[0]
    conn.close()

    # Update full_text
    store.update_full_text(frame_id, "OCR content")

    # Verify
    conn = sqlite3.connect(str(tmp_db_path))
    row = conn.execute(
        "SELECT full_text FROM frames WHERE id = ?", (frame_id,)
    ).fetchone()
    conn.close()

    assert row[0] == "OCR content"
```

- [ ] **Step 6: Run test to verify it fails**

Run: `pytest tests/test_p1_s3_text_source_mark.py::test_update_full_text_after_ocr -v`

Expected: FAIL with "AttributeError: 'FramesStore' object has no attribute 'update_full_text'"

- [ ] **Step 7: Add update_full_text method to FramesStore**

Add after `update_frames_ocr_text` method in `openrecall/server/database/frames_store.py`:

```python
    def update_full_text(self, frame_id: int, text: str) -> bool:
        """Update the full_text field for a frame.

        Called after OCR completion to set full_text = ocr_text.

        Args:
            frame_id: The frame ID
            text: The text to set as full_text

        Returns:
            True if updated, False otherwise
        """
        try:
            with self._connect() as conn:
                cursor = conn.execute(
                    "UPDATE frames SET full_text = ? WHERE id = ?",
                    (text, frame_id),
                )
                conn.commit()
                return cursor.rowcount > 0
        except sqlite3.Error as e:
            logger.error(
                "update_full_text failed frame_id=%d: %s", frame_id, e
            )
            return False
```

- [ ] **Step 8: Run test to verify it passes**

Run: `pytest tests/test_p1_s3_text_source_mark.py::test_update_full_text_after_ocr -v`

Expected: PASS

- [ ] **Step 9: Commit**

```bash
git add openrecall/server/database/frames_store.py tests/test_p1_s3_text_source_mark.py
git commit -m "feat(store): set full_text on accessibility and OCR frames

- complete_accessibility_frame now sets full_text = accessibility_text
- Add update_full_text method for OCR worker to call"
```

---

## Task 3: Update V3Worker to set full_text

**Files:**
- Modify: `openrecall/server/processing/v3_worker.py:292-311`
- Test: `tests/test_p1_s3_v3_worker_lifecycle.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_p1_s3_v3_worker_lifecycle.py`:

```python
def test_worker_sets_full_text_after_ocr(tmp_db_path, tmp_frames_dir, sample_jpeg):
    """Verify worker sets full_text after OCR completion."""
    import time
    from openrecall.server.database.frames_store import FramesStore
    from openrecall.server.processing.v3_worker import V3ProcessingWorker

    store = FramesStore(db_path=tmp_db_path)

    # Create a pending frame with snapshot
    snapshot_path = str(tmp_frames_dir / "test_frame.jpg")
    shutil.copy(sample_jpeg, snapshot_path)

    conn = sqlite3.connect(str(tmp_db_path))
    conn.execute(
        """
        INSERT INTO frames (capture_id, timestamp, status, snapshot_path, capture_trigger)
        VALUES ('test-full-text', '2026-03-25T12:00:00Z', 'pending', ?, 'manual')
        """,
        (snapshot_path,),
    )
    conn.commit()
    conn.close()

    # Run worker for one iteration
    worker = V3ProcessingWorker(db_path=tmp_db_path, poll_interval=0.1)
    worker.start()
    time.sleep(2)  # Wait for processing
    worker.stop()
    worker.join(timeout=3)

    # Verify full_text is set
    conn = sqlite3.connect(str(tmp_db_path))
    row = conn.execute(
        "SELECT full_text, text_source FROM frames WHERE capture_id = 'test-full-text'"
    ).fetchone()
    conn.close()

    # OCR should have set full_text
    assert row[0] is not None  # full_text is set
    assert row[1] == "ocr"  # text_source is ocr
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_p1_s3_v3_worker_lifecycle.py::test_worker_sets_full_text_after_ocr -v`

Expected: FAIL with "AssertionError: assert None is not None"

- [ ] **Step 3: Update V3Worker to call update_full_text**

In `openrecall/server/processing/v3_worker.py`, modify around line 292-304:

```python
        # --- Step 8: Update text_source and advance to completed ---
        self._store.update_text_source(frame_id, "ocr")

        # --- Step 9: Write ocr_text to frames table ---
        self._store.update_frames_ocr_text(frame_id, result.text)

        # --- Step 9b: Set full_text for FTS indexing ---
        self._store.update_full_text(frame_id, result.text)

        ok = self._store.advance_frame_status(frame_id, "processing", "completed")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_p1_s3_v3_worker_lifecycle.py::test_worker_sets_full_text_after_ocr -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add openrecall/server/processing/v3_worker.py tests/test_p1_s3_v3_worker_lifecycle.py
git commit -m "feat(worker): set full_text after OCR completion"
```

---

## Task 4: Simplify SearchEngine

**Files:**
- Modify: `openrecall/server/search/engine.py`
- Test: `tests/test_p1_s4_search_fts.py`

- [ ] **Step 1: Write the failing test for new single-query search**

Add to `tests/test_p1_s4_search_fts.py`:

```python
class TestUnifiedFtsSearch:
    """Tests for unified FTS search using frames.full_text."""

    @pytest.fixture
    def unified_db(self, tmp_path):
        """Create a database with migrated schema and test data."""
        db_path = tmp_path / "unified.db"
        conn = sqlite3.connect(str(db_path))

        # Run initial schema
        init_sql = Path(
            "openrecall/server/database/migrations/20260227000001_initial_schema.sql"
        ).read_text()
        conn.executescript(init_sql)

        # Run FTS unification migration
        migration_sql = Path(
            "openrecall/server/database/migrations/20260325120000_consolidate_fts_to_full_text.sql"
        ).read_text()
        conn.executescript(migration_sql)

        # Insert test frames
        conn.execute(
            """
            INSERT INTO frames (capture_id, timestamp, full_text, app_name, window_name, status)
            VALUES ('ax-1', '2026-03-25T10:00:00Z', 'Email from alice@example.com about project', 'Mail', 'Inbox', 'completed')
            """
        )
        conn.execute(
            """
            INSERT INTO frames (capture_id, timestamp, full_text, app_name, window_name, status)
            VALUES ('ocr-1', '2026-03-25T11:00:00Z', 'Meeting notes from yesterday standup', 'Notes', 'Meeting', 'completed')
            """
        )
        conn.commit()
        conn.close()

        return db_path

    def test_search_finds_text_in_full_text(self, unified_db):
        """Verify search finds text in full_text column."""
        from openrecall.server.search.engine import SearchEngine

        engine = SearchEngine(db_path=unified_db)
        results, total = engine.search(q="alice")

        assert total >= 1
        assert any("alice" in r.get("text", "").lower() for r in results)

    def test_search_with_metadata_filter(self, unified_db):
        """Verify search with app_name filter works."""
        from openrecall.server.search.engine import SearchEngine

        engine = SearchEngine(db_path=unified_db)
        results, total = engine.search(q="project", app_name="Mail")

        assert total >= 1
        for r in results:
            assert r.get("app_name") == "Mail"

    def test_content_type_param_ignored(self, unified_db):
        """Verify content_type parameter is accepted but ignored."""
        from openrecall.server.search.engine import SearchEngine

        engine = SearchEngine(db_path=unified_db)

        # All these should return the same results
        results_ocr, _ = engine.search(q="project", content_type="ocr")
        results_ax, _ = engine.search(q="project", content_type="accessibility")
        results_all, _ = engine.search(q="project", content_type="all")

        # All should find the email frame
        assert len(results_ocr) >= 1
        assert len(results_ax) >= 1
        assert len(results_all) >= 1
```

- [ ] **Step 2: Run test to verify current behavior**

Run: `pytest tests/test_p1_s4_search_fts.py::TestUnifiedFtsSearch -v`

Expected: FAIL (migration not yet applied in test fixture, or search engine still uses dual-query)

- [ ] **Step 3: Simplify SearchEngine to single query**

Replace the `search`, `_search_ocr`, `_search_accessibility`, `_search_all` methods in `openrecall/server/search/engine.py` with:

```python
    def search(
        self,
        q: str = "",
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        app_name: Optional[str] = None,
        window_name: Optional[str] = None,
        focused: Optional[bool] = None,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
        browser_url: Optional[str] = None,
        content_type: str = "all",
    ) -> tuple[list[dict[str, Any]], int]:
        """Execute FTS5 search with metadata filtering.

        Args:
            q: Text query (sanitized via sanitize_fts5_query)
            limit: Max results (clamped to 1-100)
            offset: Pagination offset
            start_time: ISO8601 UTC start timestamp
            end_time: ISO8601 UTC end timestamp
            app_name: Filter by app name (exact match via FTS)
            window_name: Filter by window name (exact match via FTS)
            focused: Filter by focused state
            min_length: Minimum text length
            max_length: Maximum text length
            browser_url: Filter by browser URL
            content_type: Accepted for API compatibility, ignored (all results returned)

        Returns:
            Tuple of (results list, total count)
        """
        # Log deprecation warning for content_type (debug mode only)
        if content_type != "all" and settings.debug:
            logger.debug(
                "content_type parameter is deprecated and ignored (value=%s)",
                content_type,
            )

        start_ts = time.perf_counter()

        params = SearchParams(
            q=q,
            limit=limit,
            offset=offset,
            start_time=start_time,
            end_time=end_time,
            app_name=app_name,
            window_name=window_name,
            focused=focused,
            min_length=min_length,
            max_length=max_length,
            browser_url=browser_url,
        )

        results = []
        total = 0

        try:
            with self._connect() as conn:
                # Execute search query
                sql, sql_params = self._build_query(params, is_count=False)
                rows = conn.execute(sql, sql_params).fetchall()

                for row in rows:
                    frame_id = row["frame_id"]
                    ts = row["timestamp"]

                    result = {
                        "frame_id": frame_id,
                        "timestamp": ts,
                        "text": row["full_text"] or "",
                        "text_source": row["text_source"],
                        "app_name": row["app_name"],
                        "window_name": row["window_name"],
                        "browser_url": row["browser_url"],
                        "focused": bool(row["focused"])
                        if row["focused"] is not None
                        else None,
                        "device_name": row["device_name"] or "monitor_0",
                        "file_path": f"{ts}.jpg",
                        "frame_url": f"/v1/frames/{frame_id}",
                        "tags": [],
                        "fts_rank": float(row["fts_rank"])
                        if row["fts_rank"] is not None
                        else None,
                    }
                    results.append(result)

                # Execute count query
                count_sql, count_params = self._build_query(params, is_count=True)
                count_start = time.perf_counter()
                count_row = conn.execute(count_sql, count_params).fetchone()
                count_elapsed_ms = (time.perf_counter() - count_start) * 1000.0

                total = count_row["total"] if count_row else 0

                if count_elapsed_ms > self.COUNT_WARNING_THRESHOLD_MS:
                    logger.warning(
                        "MRV3 count_latency_warning count_ms=%.1f q='%s'",
                        count_elapsed_ms,
                        q[:50] if q else "",
                    )

        except sqlite3.Error as e:
            logger.error("Search failed: %s", e)
            return [], 0

        # Log latency
        elapsed_ms = (time.perf_counter() - start_ts) * 1000.0
        query_type = "standard" if q else "browse"
        logger.info(
            "MRV3 search_latency_ms=%.1f query_type=%s q_present=%s limit=%d offset=%d total=%d",
            elapsed_ms,
            query_type,
            bool(q),
            params.limit,
            params.offset,
            total,
        )

        return results, total

    def _build_query(
        self, params: SearchParams, is_count: bool = False
    ) -> tuple[str, list[Any]]:
        """Build the SQL query with FTS and metadata filters.

        Args:
            params: Search parameters
            is_count: If True, build COUNT query; otherwise SELECT

        Returns:
            Tuple of (SQL string, parameters list)
        """
        has_text_query = bool(params.q and params.q.strip())
        has_metadata_filters = bool(
            params.app_name or params.window_name or params.focused is not None or params.browser_url
        )

        if is_count:
            select_clause = "SELECT COUNT(DISTINCT frames.id) AS total"
        else:
            select_clause = """
                SELECT frames.id AS frame_id,
                       frames.timestamp,
                       frames.full_text,
                       frames.app_name,
                       frames.window_name,
                       frames.browser_url,
                       frames.focused,
                       frames.device_name,
                       frames.text_source"""
            if has_text_query:
                select_clause += ",\n                       frames_fts.rank AS fts_rank"
            else:
                select_clause += ",\n                       NULL AS fts_rank"

        from_clause = "FROM frames"

        join_clauses = []
        where_clauses = ["frames.status = 'completed'", "frames.full_text IS NOT NULL"]
        params_list: list[Any] = []

        # JOIN frames_fts when text query or metadata filters present
        if has_text_query or has_metadata_filters:
            join_clauses.append("INNER JOIN frames_fts ON frames.id = frames_fts.id")

        # Build FTS MATCH clause
        fts_match_parts = []

        if has_text_query:
            sanitized_q = sanitize_fts5_query(params.q)
            fts_match_parts.append(sanitized_q)

        if has_metadata_filters:
            if params.app_name:
                safe_app = _sanitize_fts_value(params.app_name)
                fts_match_parts.append(f'app_name:"{safe_app}"')
            if params.window_name:
                safe_window = _sanitize_fts_value(params.window_name)
                fts_match_parts.append(f'window_name:"{safe_window}"')
            if params.browser_url:
                safe_url = _sanitize_fts_value(params.browser_url)
                fts_match_parts.append(f'browser_url:"{safe_url}"')

        if fts_match_parts:
            where_clauses.append(f"frames_fts MATCH ?")
            params_list.append(" ".join(fts_match_parts))

        # focused filter (not in frames_fts, filter directly)
        if params.focused is not None:
            where_clauses.append("frames.focused = ?")
            params_list.append(1 if params.focused else 0)

        # Time range filtering
        if params.start_time:
            where_clauses.append("frames.timestamp >= ?")
            params_list.append(params.start_time)
        if params.end_time:
            where_clauses.append("frames.timestamp <= ?")
            params_list.append(params.end_time)

        # Text length filtering
        if params.min_length is not None:
            where_clauses.append("LENGTH(frames.full_text) >= ?")
            params_list.append(params.min_length)
        if params.max_length is not None:
            where_clauses.append("LENGTH(frames.full_text) <= ?")
            params_list.append(params.max_length)

        # Build the full query
        sql_parts = [select_clause, from_clause]
        sql_parts.extend(join_clauses)
        sql_parts.append("WHERE " + " AND ".join(where_clauses))

        if not is_count:
            sql_parts.append("ORDER BY frames_fts.rank, frames.timestamp DESC")

            limit = min(max(1, params.limit), self.MAX_LIMIT)
            offset = max(0, params.offset)
            sql_parts.append(f"LIMIT {limit} OFFSET {offset}")

        sql = "\n".join(sql_parts)
        return sql, params_list
```

- [ ] **Step 4: Remove old _search_ocr, _search_accessibility, _search_all methods**

Delete the methods `_search_ocr`, `_search_accessibility`, `_search_all`, `_build_ocr_query`, `_build_accessibility_query` from `openrecall/server/search/engine.py`.

- [ ] **Step 5: Update count_by_type method**

Replace `count_by_type` method with simpler version that ignores content_type:

```python
    def count_by_type(
        self,
        q: str = "",
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        app_name: Optional[str] = None,
        window_name: Optional[str] = None,
        focused: Optional[bool] = None,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
        browser_url: Optional[str] = None,
    ) -> dict[str, int]:
        """Count matching frames by text_source.

        Note: After FTS unification, this returns counts grouped by frames.text_source
        for backward compatibility. The content_type parameter is no longer used.

        Returns:
            Dict with "ocr" and "accessibility" counts
        """
        params = SearchParams(
            q=q,
            start_time=start_time,
            end_time=end_time,
            app_name=app_name,
            window_name=window_name,
            focused=focused,
            min_length=min_length,
            max_length=max_length,
            browser_url=browser_url,
        )

        try:
            with self._connect() as conn:
                # Get counts grouped by text_source
                base_sql, base_params = self._build_query(params, is_count=False)

                # Modify to get counts by text_source
                sql = f"""
                    SELECT text_source, COUNT(*) as cnt FROM ({base_sql})
                    GROUP BY text_source
                """

                rows = conn.execute(sql, base_params).fetchall()

                result = {"ocr": 0, "accessibility": 0}
                for row in rows:
                    ts = row["text_source"] or "unknown"
                    if ts == "ocr":
                        result["ocr"] = row["cnt"]
                    elif ts in ("accessibility", "hybrid"):
                        result["accessibility"] += row["cnt"]

                return result
        except sqlite3.Error as e:
            logger.error("Count by type failed: %s", e)
            return {"ocr": 0, "accessibility": 0}
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_p1_s4_search_fts.py -v`

Expected: All tests PASS

- [ ] **Step 7: Commit**

```bash
git add openrecall/server/search/engine.py tests/test_p1_s4_search_fts.py
git commit -m "refactor(search): simplify to single FTS query path

- Remove _search_ocr, _search_accessibility, _search_all methods
- Single search() method queries frames_fts with full_text
- content_type parameter accepted but ignored (deprecated)
- count_by_type still groups by text_source for API compatibility"
```

---

## Task 5: Update API for content_type deprecation

**Files:**
- Modify: `openrecall/server/api_v1.py:893-997`

- [ ] **Step 1: Add deprecation log to search endpoint**

In `openrecall/server/api_v1.py`, modify the `search` function around line 919-921:

```python
    # Parse content_type (default: "all")
    content_type = request.args.get("content_type", "all").strip().lower()
    if content_type not in ("ocr", "accessibility", "all"):
        content_type = "all"

    # Log deprecation warning for content_type (debug mode only)
    if content_type != "all" and settings.debug:
        logger.debug(
            "MRV3 deprecated_param content_type=%s (parameter is ignored)",
            content_type,
        )
```

- [ ] **Step 2: Verify no other changes needed**

The search endpoint should already pass `content_type` to the engine, which now ignores it.

- [ ] **Step 3: Run API search tests**

Run: `pytest tests/test_p1_s4_api_search.py -v`

Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add openrecall/server/api_v1.py
git commit -m "feat(api): log deprecation warning for content_type param

content_type parameter is accepted but ignored after FTS unification."
```

---

## Task 6: Run Full Test Suite

- [ ] **Step 1: Run all tests**

Run: `pytest -v --tb=short`

Expected: All tests PASS (or only unrelated failures)

- [ ] **Step 2: Run integration tests with running server**

```bash
# Terminal 1: Start server
./run_server.sh --debug

# Terminal 2: Run integration tests
pytest -m integration -v
```

Expected: All integration tests PASS

- [ ] **Step 3: Manual verification**

1. Start server: `./run_server.sh --debug`
2. Ingest a frame via API
3. Search for text in the frame
4. Verify results contain `full_text` in response

---

## Task 7: Update CLAUDE.md Documentation

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update FTS5 Tables section**

Change in `CLAUDE.md`:

```markdown
**FTS5 Tables**:
- `frames_fts`: Full-text index on full_text + metadata (app_name, window_name, browser_url)
```

- [ ] **Step 2: Update Key Data Structures section**

Update the Frames Table description to include `full_text`:

```markdown
- full_text (TEXT): Merged text from accessibility_text + ocr_text for FTS indexing
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for FTS unification"
```

---

## Summary

| Task | Description | Files Changed |
|------|-------------|---------------|
| 1 | Create migration file | +migration, +tests |
| 2 | Update FramesStore | frames_store.py, tests |
| 3 | Update V3Worker | v3_worker.py, tests |
| 4 | Simplify SearchEngine | engine.py, tests |
| 5 | Update API deprecation | api_v1.py |
| 6 | Run full test suite | - |
| 7 | Update documentation | CLAUDE.md |
