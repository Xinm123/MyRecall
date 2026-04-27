"""Tests for embedding worker."""
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from openrecall.server.embedding.worker import EmbeddingWorker


class TestEmbeddingWorker:
    def test_worker_processes_pending_task(self, tmp_path):
        """Worker should process pending task and mark completed."""
        # Create test database
        db_path = tmp_path / "test.db"
        frames_dir = tmp_path / "frames"
        frames_dir.mkdir()

        # Create a dummy image file
        test_image = frames_dir / "test.jpg"
        test_image.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE frames (
                id INTEGER PRIMARY KEY,
                capture_id TEXT,
                snapshot_path TEXT,
                full_text TEXT,
                timestamp TEXT,
                app_name TEXT,
                window_name TEXT,
                embedding_status TEXT DEFAULT NULL
            );
            CREATE TABLE embedding_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                frame_id INTEGER NOT NULL,
                status TEXT DEFAULT 'pending',
                error_message TEXT,
                retry_count INTEGER DEFAULT 0,
                next_retry_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                UNIQUE(frame_id)
            );
        """)
        conn.execute(
            "INSERT INTO frames (id, capture_id, snapshot_path, full_text, timestamp) VALUES (?, ?, ?, ?, ?)",
            (1, "test-capture-1", str(test_image), "test text", "2026-04-09T12:00:00Z"),
        )
        conn.execute("INSERT INTO embedding_tasks (frame_id, status) VALUES (1, 'pending')")
        conn.commit()

        # Create mock store and service
        from openrecall.server.database.frames_store import FramesStore
        store = FramesStore.__new__(FramesStore)
        store._db_path = str(db_path)
        store._frames_dir = frames_dir

        # Create worker with mock service
        mock_service = Mock()
        mock_service.generate_embedding.return_value = __import__("numpy").array([0.1] * 1024)

        # Mock save_embedding to do nothing (LanceDB not needed for worker test)
        mock_service.save_embedding.return_value = None

        # Mock mark_completed to actually update the database
        def mark_completed_side_effect(conn, task_id, frame_id):
            from datetime import datetime, timezone
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "UPDATE embedding_tasks SET status = 'completed', completed_at = ? WHERE id = ?",
                (now, task_id),
            )
            conn.execute(
                "UPDATE frames SET embedding_status = 'completed' WHERE id = ?",
                (frame_id,),
            )

        mock_service.mark_completed.side_effect = mark_completed_side_effect

        # Mock mark_failed to actually update the database
        def mark_failed_side_effect(conn, task_id, frame_id, error_message, retry_count):
            from datetime import datetime, timezone, timedelta
            now = datetime.now(timezone.utc)
            next_retry = now + timedelta(minutes=2 ** min(retry_count, 5))
            conn.execute(
                """
                UPDATE embedding_tasks
                SET status = 'pending',
                    error_message = ?,
                    retry_count = ?,
                    next_retry_at = ?,
                    started_at = NULL
                WHERE id = ?
                """,
                (error_message, retry_count, next_retry.isoformat(), task_id),
            )
            conn.execute(
                "UPDATE frames SET embedding_status = 'failed' WHERE id = ?",
                (frame_id,),
            )

        mock_service.mark_failed.side_effect = mark_failed_side_effect

        # Mock get_queue_status
        mock_service.get_queue_status.return_value = {"pending": 1, "processing": 0, "failed": 0}

        worker = EmbeddingWorker(store=store, poll_interval=0.1)
        worker._service = mock_service  # Inject mock service

        # Run one iteration
        with conn:
            worker._process_batch(conn)

        # Verify task was completed
        task = conn.execute(
            "SELECT status FROM embedding_tasks WHERE frame_id = 1"
        ).fetchone()
        assert task[0] == "completed"

        # Verify frame status was updated
        frame = conn.execute(
            "SELECT embedding_status FROM frames WHERE id = 1"
        ).fetchone()
        assert frame[0] == "completed"

        conn.close()

    def test_worker_retries_on_failure(self, tmp_path):
        """Worker should retry failed tasks with exponential backoff."""
        db_path = tmp_path / "test.db"
        frames_dir = tmp_path / "frames"
        frames_dir.mkdir()
        test_image = frames_dir / "test.jpg"
        test_image.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)

        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE frames (
                id INTEGER PRIMARY KEY,
                capture_id TEXT,
                snapshot_path TEXT,
                full_text TEXT,
                timestamp TEXT,
                app_name TEXT,
                window_name TEXT,
                embedding_status TEXT DEFAULT NULL
            );
            CREATE TABLE embedding_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                frame_id INTEGER NOT NULL,
                status TEXT DEFAULT 'pending',
                error_message TEXT,
                retry_count INTEGER DEFAULT 0,
                next_retry_at TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                started_at TIMESTAMP,
                completed_at TIMESTAMP,
                UNIQUE(frame_id)
            );
        """)
        conn.execute(
            "INSERT INTO frames (id, capture_id, snapshot_path, full_text, timestamp) VALUES (?, ?, ?, ?, ?)",
            (1, "test-capture-1", str(test_image), "test", "2026-04-09T12:00:00Z"),
        )
        conn.execute("INSERT INTO embedding_tasks (frame_id, status) VALUES (1, 'pending')")
        conn.commit()

        from openrecall.server.database.frames_store import FramesStore
        store = FramesStore.__new__(FramesStore)
        store._db_path = str(db_path)

        # Create worker with failing service
        mock_service = Mock()
        mock_service.generate_embedding.side_effect = Exception("API error")

        # Mock mark_failed to actually update the database
        def mark_failed_side_effect(conn, task_id, frame_id, error_message, retry_count):
            from datetime import datetime, timezone, timedelta
            now = datetime.now(timezone.utc)
            next_retry = now + timedelta(minutes=2 ** min(retry_count, 5))
            conn.execute(
                """
                UPDATE embedding_tasks
                SET status = 'pending',
                    error_message = ?,
                    retry_count = ?,
                    next_retry_at = ?,
                    started_at = NULL
                WHERE id = ?
                """,
                (error_message, retry_count, next_retry.isoformat(), task_id),
            )
            conn.execute(
                "UPDATE frames SET embedding_status = 'failed' WHERE id = ?",
                (frame_id,),
            )

        mock_service.mark_failed.side_effect = mark_failed_side_effect
        mock_service.get_queue_status.return_value = {"pending": 1, "processing": 0, "failed": 0}

        worker = EmbeddingWorker(store=store)
        worker._service = mock_service  # Inject mock service

        with conn:
            worker._process_batch(conn)

        # Verify task was rescheduled
        task = conn.execute(
            "SELECT retry_count, next_retry_at FROM embedding_tasks WHERE frame_id = 1"
        ).fetchone()
        assert task[0] == 1  # retry_count incremented
        assert task[1] is not None  # next_retry_at set

        conn.close()
