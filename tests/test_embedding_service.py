# tests/test_embedding_service.py
"""Tests for embedding service."""
import sqlite3
import tempfile
from pathlib import Path

import pytest

from openrecall.server.embedding.service import EmbeddingService


class TestEmbeddingService:
    def test_enqueue_embedding_task(self, tmp_path):
        """Should insert a pending embedding task."""
        # Create a test database
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript("""
            CREATE TABLE frames (
                id INTEGER PRIMARY KEY,
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
            INSERT INTO frames (id) VALUES (1), (2);
        """)
        conn.commit()

        from openrecall.server.database.frames_store import FramesStore
        store = FramesStore.__new__(FramesStore)
        store._db_path = str(db_path)

        service = EmbeddingService(store=store)

        # Enqueue task
        service.enqueue_embedding_task(conn, frame_id=1)

        # Verify task was created
        row = conn.execute(
            "SELECT * FROM embedding_tasks WHERE frame_id = 1"
        ).fetchone()
        assert row is not None
        assert row[2] == "pending"  # status column

        conn.close()

    def test_get_queue_status(self, tmp_path):
        """Should return queue statistics."""
        db_path = tmp_path / "test.db"
        conn = sqlite3.connect(str(db_path))
        conn.executescript("""
            CREATE TABLE frames (
                id INTEGER PRIMARY KEY,
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
            INSERT INTO frames (id) VALUES (1), (2), (3);
            INSERT INTO embedding_tasks (frame_id, status) VALUES
                (1, 'pending'),
                (2, 'processing'),
                (3, 'completed');
        """)
        conn.commit()

        from openrecall.server.database.frames_store import FramesStore
        store = FramesStore.__new__(FramesStore)
        store._db_path = str(db_path)

        service = EmbeddingService(store=store)
        status = service.get_queue_status(conn)

        assert status["pending"] == 1
        assert status["processing"] == 1
        assert status["completed"] == 1

        conn.close()
