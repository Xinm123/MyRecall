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
