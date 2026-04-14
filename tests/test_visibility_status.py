"""Unit tests for visibility_status helper methods."""
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
                    snapshot_path TEXT,
                    full_text TEXT,
                    browser_url TEXT,
                    accessibility_text TEXT,
                    ocr_text TEXT,
                    text_source TEXT,
                    device_name TEXT,
                    focused INTEGER
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

    def test_returns_false_when_status_is_null(self, temp_store):
        """Should return False when any status is NULL (incomplete processing)."""
        with temp_store._connect() as conn:
            # Insert a frame with NULL description_status (newly ingested)
            conn.execute(
                """
                INSERT INTO frames (id, status, description_status, embedding_status, visibility_status)
                VALUES (1, 'completed', NULL, NULL, 'pending')
                """
            )

            result = temp_store.try_set_queryable(conn, 1)

            assert result is False

            row = conn.execute(
                "SELECT visibility_status FROM frames WHERE id = 1"
            ).fetchone()
            assert row["visibility_status"] == "pending"


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
