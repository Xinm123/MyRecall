"""Phase 1 tests: Search integration with video FTS."""
import importlib
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _init_test_db(db_path: Path):
    """Create test database with all required tables."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE IF NOT EXISTS entries (id INTEGER PRIMARY KEY AUTOINCREMENT, app TEXT, title TEXT, text TEXT, timestamp INTEGER UNIQUE, embedding BLOB, description TEXT, status TEXT DEFAULT 'COMPLETED')")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON entries (timestamp)")
    conn.execute("CREATE TABLE IF NOT EXISTS video_chunks (id INTEGER PRIMARY KEY AUTOINCREMENT, file_path TEXT NOT NULL, device_name TEXT DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now')), expires_at TEXT, encrypted INTEGER DEFAULT 0, checksum TEXT, status TEXT DEFAULT 'PENDING')")
    conn.execute("CREATE TABLE IF NOT EXISTS frames (id INTEGER PRIMARY KEY AUTOINCREMENT, video_chunk_id INTEGER NOT NULL, offset_index INTEGER NOT NULL, timestamp REAL NOT NULL, app_name TEXT DEFAULT '', window_name TEXT DEFAULT '', focused INTEGER DEFAULT 0, browser_url TEXT DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now')), FOREIGN KEY (video_chunk_id) REFERENCES video_chunks(id) ON DELETE CASCADE)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_frames_video_chunk_id ON frames(video_chunk_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_frames_timestamp ON frames(timestamp)")
    conn.execute("CREATE TABLE IF NOT EXISTS ocr_text (frame_id INTEGER NOT NULL, text TEXT NOT NULL, text_json TEXT, ocr_engine TEXT DEFAULT '', text_length INTEGER, created_at TEXT NOT NULL DEFAULT (datetime('now')), FOREIGN KEY (frame_id) REFERENCES frames(id) ON DELETE CASCADE)")
    conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS ocr_text_fts USING fts5(text, app_name, window_name, frame_id UNINDEXED, tokenize='unicode61')")
    conn.commit()
    conn.close()


def _init_fts_db(fts_path: Path):
    """Create FTS database for legacy search."""
    fts_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(fts_path))
    conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS ocr_fts USING fts5(snapshot_id UNINDEXED, ocr_text, caption, keywords)")
    conn.commit()
    conn.close()


@pytest.fixture
def sql_store(tmp_path, monkeypatch):
    """Create isolated SQLStore."""
    monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "MRS"))
    monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "MRC"))
    importlib.reload(importlib.import_module("openrecall.shared.config"))

    from openrecall.shared.config import settings
    db_path = settings.db_path
    fts_path = settings.fts_path
    _init_test_db(db_path)
    _init_fts_db(fts_path)

    import openrecall.server.database.sql
    importlib.reload(openrecall.server.database.sql)
    import openrecall.server.database
    importlib.reload(openrecall.server.database)

    from openrecall.server.database import SQLStore
    return SQLStore()


class TestVideoFTSSearch:
    """Test video FTS search via SQLStore."""

    def test_search_returns_matching_frames(self, sql_store):
        """search_video_fts finds frames by OCR text."""
        chunk_id = sql_store.insert_video_chunk(file_path="/tmp/test.mp4")
        frame_id = sql_store.insert_frame(
            video_chunk_id=chunk_id, offset_index=0, timestamp=1000.0,
            app_name="Terminal", window_name="bash",
        )
        sql_store.insert_ocr_text(frame_id, "git commit -m fix database migration")
        sql_store.insert_ocr_text_fts(frame_id, "git commit -m fix database migration", app_name="Terminal", window_name="bash")

        results = sql_store.search_video_fts("database migration", limit=10)
        assert len(results) > 0
        assert results[0]["frame_id"] == frame_id
        assert results[0]["app_name"] == "Terminal"

    def test_search_returns_metadata(self, sql_store):
        """FTS results include timestamp and video_chunk_id."""
        chunk_id = sql_store.insert_video_chunk(file_path="/tmp/test.mp4")
        frame_id = sql_store.insert_frame(
            video_chunk_id=chunk_id, offset_index=5, timestamp=1500.0,
        )
        sql_store.insert_ocr_text(frame_id, "unique search term abcxyz")
        sql_store.insert_ocr_text_fts(frame_id, "unique search term abcxyz")

        results = sql_store.search_video_fts("abcxyz", limit=10)
        assert len(results) == 1
        r = results[0]
        assert "frame_id" in r
        assert "timestamp" in r
        assert "video_chunk_id" in r
        assert "offset_index" in r
        assert r["video_chunk_id"] == chunk_id
        assert r["offset_index"] == 5

    def test_search_respects_limit(self, sql_store):
        """FTS search respects the limit parameter."""
        chunk_id = sql_store.insert_video_chunk(file_path="/tmp/test.mp4")
        for i in range(10):
            fid = sql_store.insert_frame(video_chunk_id=chunk_id, offset_index=i, timestamp=1000.0 + i)
            sql_store.insert_ocr_text(fid, f"common search term iteration {i}")
            sql_store.insert_ocr_text_fts(fid, f"common search term iteration {i}")

        results = sql_store.search_video_fts("common search", limit=3)
        assert len(results) == 3


class TestSQLStoreVideoMethods:
    """Test SQLStore video chunk CRUD operations."""

    def test_insert_and_get_video_chunk(self, sql_store):
        """Insert a video chunk and retrieve it."""
        chunk_id = sql_store.insert_video_chunk(
            file_path="/tmp/test.mp4",
            device_name="primary_display",
            checksum="abc123",
        )
        assert chunk_id is not None

        chunk = sql_store.get_video_chunk_by_id(chunk_id)
        assert chunk is not None
        assert chunk["file_path"] == "/tmp/test.mp4"
        assert chunk["device_name"] == "primary_display"
        assert chunk["checksum"] == "abc123"
        assert chunk["status"] == "PENDING"

    def test_video_chunk_status_transitions(self, sql_store):
        """Test PENDING -> PROCESSING -> COMPLETED transitions."""
        chunk_id = sql_store.insert_video_chunk(file_path="/tmp/test.mp4")

        conn = sqlite3.connect(str(sql_store.db_path))

        # PENDING -> PROCESSING
        assert sql_store.mark_video_chunk_processing(conn, chunk_id) is True
        chunk = sql_store.get_video_chunk_by_id(chunk_id)
        assert chunk["status"] == "PROCESSING"

        # PROCESSING -> COMPLETED
        assert sql_store.mark_video_chunk_completed(conn, chunk_id) is True
        chunk = sql_store.get_video_chunk_by_id(chunk_id)
        assert chunk["status"] == "COMPLETED"

        conn.close()

    def test_video_chunk_failed_status(self, sql_store):
        """Test PENDING -> PROCESSING -> FAILED transition."""
        chunk_id = sql_store.insert_video_chunk(file_path="/tmp/test.mp4")
        conn = sqlite3.connect(str(sql_store.db_path))

        sql_store.mark_video_chunk_processing(conn, chunk_id)
        assert sql_store.mark_video_chunk_failed(conn, chunk_id) is True

        chunk = sql_store.get_video_chunk_by_id(chunk_id)
        assert chunk["status"] == "FAILED"
        conn.close()

    def test_get_next_pending_fifo(self, sql_store):
        """get_next_pending returns oldest PENDING chunk."""
        id1 = sql_store.insert_video_chunk(file_path="/tmp/first.mp4")
        id2 = sql_store.insert_video_chunk(file_path="/tmp/second.mp4")

        conn = sqlite3.connect(str(sql_store.db_path))
        chunk = sql_store.get_next_pending_video_chunk(conn)
        assert chunk is not None
        assert chunk["id"] == id1  # FIFO order
        conn.close()

    def test_reset_stuck_video_chunks(self, sql_store):
        """reset_stuck resets PROCESSING to PENDING."""
        chunk_id = sql_store.insert_video_chunk(file_path="/tmp/test.mp4")
        conn = sqlite3.connect(str(sql_store.db_path))
        sql_store.mark_video_chunk_processing(conn, chunk_id)

        count = sql_store.reset_stuck_video_chunks(conn)
        assert count == 1

        chunk = sql_store.get_video_chunk_by_id(chunk_id)
        assert chunk["status"] == "PENDING"
        conn.close()

    def test_insert_and_get_frame(self, sql_store):
        """Insert and retrieve a frame."""
        chunk_id = sql_store.insert_video_chunk(file_path="/tmp/test.mp4")
        frame_id = sql_store.insert_frame(
            video_chunk_id=chunk_id, offset_index=3, timestamp=1500.0,
            app_name="Safari", window_name="Google",
        )
        assert frame_id is not None

        frame = sql_store.get_frame_by_id(frame_id)
        assert frame is not None
        assert frame["offset_index"] == 3
        assert frame["timestamp"] == 1500.0
        assert frame["app_name"] == "Safari"

    def test_query_frames_by_time_range(self, sql_store):
        """query_frames_by_time_range returns correct frames."""
        chunk_id = sql_store.insert_video_chunk(file_path="/tmp/test.mp4")
        for i in range(10):
            sql_store.insert_frame(
                video_chunk_id=chunk_id, offset_index=i, timestamp=1000.0 + i * 10,
            )

        frames, total = sql_store.query_frames_by_time_range(
            start_time=1020.0, end_time=1060.0, limit=50, offset=0,
        )
        # Timestamps 1020, 1030, 1040, 1050, 1060 = 5 frames
        assert total == 5
        assert len(frames) == 5

    def test_insert_frames_batch(self, sql_store):
        """insert_frames_batch inserts multiple frames."""
        chunk_id = sql_store.insert_video_chunk(file_path="/tmp/test.mp4")
        frames = [
            {"video_chunk_id": chunk_id, "offset_index": i, "timestamp": 1000.0 + i}
            for i in range(5)
        ]
        ids = sql_store.insert_frames_batch(frames)
        assert len(ids) == 5
        for fid in ids:
            assert fid is not None
