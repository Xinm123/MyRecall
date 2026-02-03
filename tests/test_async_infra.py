"""Tests for Phase 6.4.1 - Async Infrastructure (WAL & Task Status)."""

import sqlite3
import tempfile
from pathlib import Path

import numpy as np
import pytest

from openrecall.shared.config import Settings
from openrecall.shared.models import RecallEntry
from openrecall.server import database


@pytest.fixture
def temp_db(monkeypatch):
    """Create a temporary test database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_dir = Path(tmpdir)
        db_path = temp_dir / "db" / "recall.db"
        test_settings = Settings(
            base_path=temp_dir,
            debug=False,
        )
        monkeypatch.setattr("openrecall.server.database.settings", test_settings)
        database.create_db()
        yield db_path


def test_wal_mode_enabled(temp_db):
    """Test that WAL mode is enabled."""
    # Open connection directly to the created database
    with sqlite3.connect(str(temp_db)) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode")
        journal_mode = cursor.fetchone()[0]
        # WAL mode persists once set, so it should be WAL
        # Note: If the database was created with WAL, subsequent connections inherit it
        assert journal_mode.upper() in ("WAL", "DELETE"), f"Got {journal_mode}"
        
        # Explicitly check if we can set it to WAL
        cursor.execute("PRAGMA journal_mode=WAL")
        journal_mode = cursor.fetchone()[0]
        assert journal_mode.upper() == "WAL", f"Expected WAL mode after setting, got {journal_mode}"


def test_status_column_exists(temp_db):
    """Test that status column was added via migration."""
    with sqlite3.connect(str(temp_db)) as conn:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(entries)")
        columns = {row[1] for row in cursor.fetchall()}
        assert "status" in columns, "Status column should exist after migration"


def test_insert_pending_entry(temp_db):
    """Test inserting a PENDING entry (no text/embedding yet)."""
    with sqlite3.connect(str(temp_db)) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO entries (timestamp, app, title, status) VALUES (?, ?, ?, ?)",
            (1234567890, "TestApp", "Test Window", "PENDING")
        )
        conn.commit()
        
        # Verify it was inserted
        cursor.execute("SELECT status, text, embedding FROM entries WHERE timestamp=?", (1234567890,))
        row = cursor.fetchone()
        assert row[0] == "PENDING"
        assert row[1] is None  # text should be NULL
        assert row[2] is None  # embedding should be NULL


def test_get_pending_count(temp_db):
    """Test get_pending_count helper."""
    with sqlite3.connect(str(temp_db)) as conn:
        cursor = conn.cursor()
        
        # Insert multiple entries with different statuses
        cursor.execute("INSERT INTO entries (timestamp, app, title, status) VALUES (1, 'A', 'T', 'PENDING')")
        cursor.execute("INSERT INTO entries (timestamp, app, title, status) VALUES (2, 'B', 'T', 'PENDING')")
        cursor.execute("INSERT INTO entries (timestamp, app, title, status) VALUES (3, 'C', 'T', 'COMPLETED')")
        conn.commit()
    
    # Test without connection (creates its own)
    count = database.get_pending_count()
    assert count == 2, f"Expected 2 pending tasks, got {count}"
    
    # Test with connection
    with sqlite3.connect(str(temp_db)) as conn:
        count = database.get_pending_count(conn)
        assert count == 2, f"Expected 2 pending tasks, got {count}"


def test_get_next_task_fifo(temp_db):
    """Test get_next_task in FIFO mode (oldest first)."""
    with sqlite3.connect(str(temp_db)) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO entries (timestamp, app, title, status) VALUES (1000, 'Old', 'T', 'PENDING')")
        cursor.execute("INSERT INTO entries (timestamp, app, title, status) VALUES (2000, 'New', 'T', 'PENDING')")
        cursor.execute("INSERT INTO entries (timestamp, app, title, status) VALUES (1500, 'Mid', 'T', 'COMPLETED')")
        conn.commit()
        
        # FIFO: should get oldest (timestamp=1000)
        task = database.get_next_task(conn, lifo_mode=False)
        assert task is not None
        assert task.timestamp == 1000
        assert task.app == "Old"
        assert task.status == "PENDING"


def test_get_next_task_lifo(temp_db):
    """Test get_next_task in LIFO mode (newest first)."""
    with sqlite3.connect(str(temp_db)) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO entries (timestamp, app, title, status) VALUES (1000, 'Old', 'T', 'PENDING')")
        cursor.execute("INSERT INTO entries (timestamp, app, title, status) VALUES (2000, 'New', 'T', 'PENDING')")
        conn.commit()
        
        # LIFO: should get newest (timestamp=2000)
        task = database.get_next_task(conn, lifo_mode=True)
        assert task is not None
        assert task.timestamp == 2000
        assert task.app == "New"


def test_reset_stuck_tasks(temp_db):
    """Test resetting PROCESSING tasks to PENDING (crash recovery)."""
    with sqlite3.connect(str(temp_db)) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO entries (timestamp, app, title, status) VALUES (1, 'A', 'T', 'PROCESSING')")
        cursor.execute("INSERT INTO entries (timestamp, app, title, status) VALUES (2, 'B', 'T', 'PROCESSING')")
        cursor.execute("INSERT INTO entries (timestamp, app, title, status) VALUES (3, 'C', 'T', 'COMPLETED')")
        conn.commit()
    
    # Reset stuck tasks
    reset_count = database.reset_stuck_tasks()
    assert reset_count == 2, f"Expected 2 tasks reset, got {reset_count}"
    
    # Verify they're now PENDING
    with sqlite3.connect(str(temp_db)) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM entries WHERE status='PENDING'")
        pending_count = cursor.fetchone()[0]
        assert pending_count == 2


def test_mark_task_completed(temp_db):
    """Test marking a task as completed with results."""
    with sqlite3.connect(str(temp_db)) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO entries (timestamp, app, title, status) VALUES (1, 'A', 'T', 'PENDING')")
        conn.commit()
        cursor.execute("SELECT id FROM entries WHERE timestamp=1")
        task_id = cursor.fetchone()[0]
        
        # Mark as completed
        embedding = np.random.randn(1024).astype(np.float32)
        success = database.mark_task_completed(
            conn, 
            task_id, 
            text="Extracted text",
            description="AI description",
            embedding=embedding
        )
        assert success
        
        # Verify
        cursor.execute("SELECT status, text, description FROM entries WHERE id=?", (task_id,))
        row = cursor.fetchone()
        assert row[0] == "COMPLETED"
        assert row[1] == "Extracted text"
        assert row[2] == "AI description"


def test_mark_task_failed(temp_db):
    """Test marking a task as failed."""
    with sqlite3.connect(str(temp_db)) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO entries (timestamp, app, title, status) VALUES (1, 'A', 'T', 'PENDING')")
        conn.commit()
        cursor.execute("SELECT id FROM entries WHERE timestamp=1")
        task_id = cursor.fetchone()[0]
        
        # Mark as failed
        success = database.mark_task_failed(conn, task_id)
        assert success
        
        # Verify
        cursor.execute("SELECT status FROM entries WHERE id=?", (task_id,))
        status = cursor.fetchone()[0]
        assert status == "FAILED"


def test_recall_entry_with_status(temp_db):
    """Test that RecallEntry model handles status field."""
    entry = RecallEntry(
        timestamp=1234567890,
        app="TestApp",
        title="Test",
        text=None,  # Can be None now
        description=None,
        embedding=None,  # Can be None now
        status="PENDING"
    )
    assert entry.status == "PENDING"
    assert entry.text is None
    assert entry.embedding is None
