"""
Tests for retry failed frames functionality.

Usage:
    pytest tests/test_retry_failed_frames.py -v
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from openrecall.server.database.frames_store import FramesStore


@pytest.fixture
def temp_store():
    """Create a temporary FramesStore with test frames."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        store = FramesStore(str(db_path))

        # Create tables
        with store._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS frames (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    frame_id TEXT UNIQUE,
                    capture_id TEXT UNIQUE,
                    timestamp TEXT,
                    status TEXT DEFAULT 'pending',
                    error_message TEXT,
                    description_status TEXT,
                    embedding_status TEXT,
                    visibility_status TEXT DEFAULT 'pending',
                    snapshot_path TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS description_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    frame_id INTEGER,
                    status TEXT DEFAULT 'pending',
                    error_message TEXT,
                    retry_count INTEGER DEFAULT 0,
                    UNIQUE(frame_id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS embedding_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    frame_id INTEGER,
                    status TEXT DEFAULT 'pending',
                    error_message TEXT,
                    retry_count INTEGER DEFAULT 0,
                    UNIQUE(frame_id)
                )
            """)
            conn.commit()

        yield store


class TestResetFailedFrames:
    """Tests for FramesStore.reset_failed_frames()."""

    def test_reset_ocr_failed_frame(self, temp_store):
        """Frame with OCR failure should have status reset to pending."""
        # Insert a frame with OCR failure
        with temp_store._connect() as conn:
            conn.execute("""
                INSERT INTO frames (frame_id, status, error_message, visibility_status, snapshot_path)
                VALUES ('test-1', 'failed', 'OCR error', 'failed', '/tmp/test.jpg')
            """)
            conn.commit()

        result = temp_store.reset_failed_frames()

        assert result["total"] == 1
        assert result["breakdown"]["ocr"] == 1

        # Verify frame was reset
        with temp_store._connect() as conn:
            row = conn.execute(
                "SELECT status, error_message, visibility_status FROM frames WHERE frame_id = 'test-1'"
            ).fetchone()
            assert row["status"] == "pending"
            assert row["error_message"] is None
            assert row["visibility_status"] == "pending"

    def test_reset_description_failed_frame(self, temp_store):
        """Frame with description failure should have description_status reset and task enqueued."""
        with temp_store._connect() as conn:
            conn.execute("""
                INSERT INTO frames (id, frame_id, status, description_status, visibility_status, snapshot_path)
                VALUES (1, 'test-2', 'completed', 'failed', 'failed', '/tmp/test.jpg')
            """)
            conn.commit()

        result = temp_store.reset_failed_frames()

        assert result["total"] == 1
        assert result["breakdown"]["description"] == 1

        with temp_store._connect() as conn:
            row = conn.execute(
                "SELECT description_status, visibility_status FROM frames WHERE frame_id = 'test-2'"
            ).fetchone()
            assert row["description_status"] == "pending"
            assert row["visibility_status"] == "pending"

            # Check task was enqueued
            task = conn.execute(
                "SELECT status FROM description_tasks WHERE frame_id = 1"
            ).fetchone()
            assert task is not None
            assert task["status"] == "pending"

    def test_reset_embedding_failed_frame(self, temp_store):
        """Frame with embedding failure should have embedding_status reset and task enqueued."""
        with temp_store._connect() as conn:
            conn.execute("""
                INSERT INTO frames (id, frame_id, status, description_status, embedding_status, visibility_status, snapshot_path)
                VALUES (1, 'test-3', 'completed', 'completed', 'failed', 'failed', '/tmp/test.jpg')
            """)
            conn.commit()

        result = temp_store.reset_failed_frames()

        assert result["total"] == 1
        assert result["breakdown"]["embedding"] == 1

        with temp_store._connect() as conn:
            row = conn.execute(
                "SELECT embedding_status, visibility_status FROM frames WHERE frame_id = 'test-3'"
            ).fetchone()
            assert row["embedding_status"] == "pending"
            assert row["visibility_status"] == "pending"

            task = conn.execute(
                "SELECT status FROM embedding_tasks WHERE frame_id = 1"
            ).fetchone()
            assert task is not None
            assert task["status"] == "pending"

    def test_reset_multiple_failures_in_one_frame(self, temp_store):
        """Frame with multiple failed stages should reset all failed stages."""
        with temp_store._connect() as conn:
            conn.execute("""
                INSERT INTO frames (id, frame_id, status, description_status, embedding_status, visibility_status, snapshot_path)
                VALUES (1, 'test-4', 'completed', 'failed', 'failed', 'failed', '/tmp/test.jpg')
            """)
            conn.commit()

        result = temp_store.reset_failed_frames()

        assert result["total"] == 1
        assert result["breakdown"]["description"] == 1
        assert result["breakdown"]["embedding"] == 1

        with temp_store._connect() as conn:
            row = conn.execute(
                "SELECT description_status, embedding_status, visibility_status FROM frames WHERE frame_id = 'test-4'"
            ).fetchone()
            assert row["description_status"] == "pending"
            assert row["embedding_status"] == "pending"
            assert row["visibility_status"] == "pending"

    def test_no_failed_frames_returns_zero(self, temp_store):
        """When no failed frames exist, should return zero counts."""
        with temp_store._connect() as conn:
            conn.execute("""
                INSERT INTO frames (frame_id, status, visibility_status, snapshot_path)
                VALUES ('test-5', 'completed', 'queryable', '/tmp/test.jpg')
            """)
            conn.commit()

        result = temp_store.reset_failed_frames()

        assert result["total"] == 0
        assert result["breakdown"]["ocr"] == 0
        assert result["breakdown"]["description"] == 0
        assert result["breakdown"]["embedding"] == 0

    def test_reset_resets_existing_failed_task(self, temp_store):
        """Existing failed task should be reset to pending, not ignored."""
        with temp_store._connect() as conn:
            conn.execute("""
                INSERT INTO frames (id, frame_id, status, description_status, visibility_status, snapshot_path)
                VALUES (1, 'test-6', 'completed', 'failed', 'failed', '/tmp/test.jpg')
            """)
            # Insert existing failed task
            conn.execute("""
                INSERT INTO description_tasks (frame_id, status, error_message, retry_count)
                VALUES (1, 'failed', 'Previous error', 2)
            """)
            conn.commit()

        result = temp_store.reset_failed_frames()

        assert result["breakdown"]["description"] == 1

        with temp_store._connect() as conn:
            task = conn.execute(
                "SELECT status, error_message, retry_count FROM description_tasks WHERE frame_id = 1"
            ).fetchone()
            assert task["status"] == "pending"
            assert task["error_message"] is None
            assert task["retry_count"] == 3  # Incremented from 2 to 3
