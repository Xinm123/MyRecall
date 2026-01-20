"""Tests for filtering PENDING entries in search/display."""

import tempfile
from pathlib import Path

import numpy as np
import pytest

from openrecall.shared.config import Settings
from openrecall.server import database


@pytest.fixture
def temp_db(monkeypatch):
    """Create a temporary test database."""
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_dir = Path(tmpdir)
        test_settings = Settings(
            base_path=temp_dir,
            debug=False,
        )
        monkeypatch.setattr("openrecall.server.database.settings", test_settings)
        database.create_db()
        yield test_settings


def test_get_all_entries_excludes_pending(temp_db):
    """Test that get_all_entries only returns COMPLETED entries."""
    import sqlite3
    
    # Insert entries with different statuses
    with sqlite3.connect(str(temp_db.db_path)) as conn:
        cursor = conn.cursor()
        
        # PENDING entry (should NOT be returned)
        cursor.execute(
            "INSERT INTO entries (timestamp, app, title, status) VALUES (?, ?, ?, ?)",
            (1000, "App1", "Title1", "PENDING")
        )
        
        # COMPLETED entry (should be returned)
        embedding = np.random.randn(1024).astype(np.float32).tobytes()
        cursor.execute(
            "INSERT INTO entries (timestamp, app, title, text, description, embedding, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (2000, "App2", "Title2", "Some text", "Description", embedding, "COMPLETED")
        )
        
        # PROCESSING entry (should NOT be returned)
        cursor.execute(
            "INSERT INTO entries (timestamp, app, title, status) VALUES (?, ?, ?, ?)",
            (3000, "App3", "Title3", "PROCESSING")
        )
        
        # Another COMPLETED entry
        cursor.execute(
            "INSERT INTO entries (timestamp, app, title, text, description, embedding, status) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (4000, "App4", "Title4", "More text", "Desc", embedding, "COMPLETED")
        )
        
        conn.commit()
    
    # Query all entries
    entries = database.get_all_entries()
    
    # Should only return 2 COMPLETED entries
    assert len(entries) == 2, f"Expected 2 COMPLETED entries, got {len(entries)}"
    assert all(e.status == "COMPLETED" for e in entries), "All returned entries should be COMPLETED"
    assert all(e.embedding is not None for e in entries), "All returned entries should have embeddings"
    
    # Verify timestamps (should be in DESC order)
    assert entries[0].timestamp == 4000
    assert entries[1].timestamp == 2000


def test_get_entries_by_time_range_excludes_pending(temp_db):
    """Test that get_entries_by_time_range only returns COMPLETED entries."""
    import sqlite3
    
    with sqlite3.connect(str(temp_db.db_path)) as conn:
        cursor = conn.cursor()
        embedding = np.random.randn(1024).astype(np.float32).tobytes()
        
        # PENDING in range (should NOT be returned)
        cursor.execute(
            "INSERT INTO entries (timestamp, app, title, status) VALUES (?, ?, ?, ?)",
            (1500, "App1", "Title1", "PENDING")
        )
        
        # COMPLETED in range (should be returned)
        cursor.execute(
            "INSERT INTO entries (timestamp, app, title, text, embedding, status) VALUES (?, ?, ?, ?, ?, ?)",
            (2000, "App2", "Title2", "Text", embedding, "COMPLETED")
        )
        
        # COMPLETED outside range (should NOT be returned)
        cursor.execute(
            "INSERT INTO entries (timestamp, app, title, text, embedding, status) VALUES (?, ?, ?, ?, ?, ?)",
            (5000, "App3", "Title3", "Text", embedding, "COMPLETED")
        )
        
        conn.commit()
    
    # Query time range [1000, 3000]
    entries = database.get_entries_by_time_range(1000, 3000)
    
    # Should only return 1 COMPLETED entry in range
    assert len(entries) == 1, f"Expected 1 entry, got {len(entries)}"
    assert entries[0].timestamp == 2000
    assert entries[0].status == "COMPLETED"


def test_get_timestamps_includes_all_statuses(temp_db):
    """Test that get_timestamps includes ALL entries regardless of status."""
    import sqlite3
    
    with sqlite3.connect(str(temp_db.db_path)) as conn:
        cursor = conn.cursor()
        
        # Insert entries with different statuses
        cursor.execute("INSERT INTO entries (timestamp, app, title, status) VALUES (1000, 'A', 'T', 'PENDING')")
        cursor.execute("INSERT INTO entries (timestamp, app, title, status) VALUES (2000, 'B', 'T', 'COMPLETED')")
        cursor.execute("INSERT INTO entries (timestamp, app, title, status) VALUES (3000, 'C', 'T', 'PROCESSING')")
        cursor.execute("INSERT INTO entries (timestamp, app, title, status) VALUES (4000, 'D', 'T', 'FAILED')")
        conn.commit()
    
    # get_timestamps should return ALL timestamps (for timeline view)
    timestamps = database.get_timestamps()
    
    assert len(timestamps) == 4, f"Expected 4 timestamps, got {len(timestamps)}"
    assert timestamps == [4000, 3000, 2000, 1000], "Should be in DESC order"
