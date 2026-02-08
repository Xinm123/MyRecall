"""Phase 1 tests: RetentionWorker and data lifecycle."""
import importlib
import sqlite3
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image


def _init_test_db(db_path: Path):
    """Create test database with all required tables."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("CREATE TABLE IF NOT EXISTS entries (id INTEGER PRIMARY KEY AUTOINCREMENT, app TEXT, title TEXT, text TEXT, timestamp INTEGER UNIQUE, embedding BLOB, description TEXT, status TEXT DEFAULT 'COMPLETED', expires_at TEXT)")
    conn.execute("CREATE TABLE IF NOT EXISTS video_chunks (id INTEGER PRIMARY KEY AUTOINCREMENT, file_path TEXT NOT NULL, device_name TEXT DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now')), expires_at TEXT, encrypted INTEGER DEFAULT 0, checksum TEXT, status TEXT DEFAULT 'PENDING')")
    conn.execute("CREATE TABLE IF NOT EXISTS frames (id INTEGER PRIMARY KEY AUTOINCREMENT, video_chunk_id INTEGER NOT NULL, offset_index INTEGER NOT NULL, timestamp REAL NOT NULL, app_name TEXT DEFAULT '', window_name TEXT DEFAULT '', focused INTEGER DEFAULT 0, browser_url TEXT DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now')), FOREIGN KEY (video_chunk_id) REFERENCES video_chunks(id) ON DELETE CASCADE)")
    conn.execute("CREATE TABLE IF NOT EXISTS ocr_text (frame_id INTEGER NOT NULL, text TEXT NOT NULL, text_json TEXT, ocr_engine TEXT DEFAULT '', text_length INTEGER, created_at TEXT NOT NULL DEFAULT (datetime('now')), FOREIGN KEY (frame_id) REFERENCES frames(id) ON DELETE CASCADE)")
    conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS ocr_text_fts USING fts5(text, app_name, window_name, frame_id UNINDEXED, tokenize='unicode61')")
    conn.commit()
    conn.close()


def _init_fts_db(fts_path: Path):
    fts_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(fts_path))
    conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS ocr_fts USING fts5(snapshot_id UNINDEXED, ocr_text, caption, keywords)")
    conn.commit()
    conn.close()


def _seed_expired_chunk(
    db_path: Path,
    file_path: str,
    frames_path: Path,
    num_frames: int = 3,
    days_ago: int = 1,
):
    """Insert an expired COMPLETED video chunk with frames and OCR text."""
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys=ON")
    # Insert expired chunk.
    conn.execute(
        "INSERT INTO video_chunks (file_path, status, expires_at) VALUES (?, 'COMPLETED', datetime('now', ?))",
        (file_path, f"-{days_ago} day"),
    )
    chunk_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]

    frame_ids = []
    for i in range(num_frames):
        conn.execute(
            "INSERT INTO frames (video_chunk_id, offset_index, timestamp) VALUES (?, ?, ?)",
            (chunk_id, i, 1000.0 + i),
        )
        frame_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
        frame_ids.append(frame_id)
        conn.execute(
            "INSERT INTO ocr_text (frame_id, text, text_length) VALUES (?, ?, ?)",
            (frame_id, f"frame {i} ocr text", 15),
        )
        conn.execute(
            "INSERT INTO ocr_text_fts (text, frame_id) VALUES (?, ?)",
            (f"frame {i} ocr text", frame_id),
        )

    conn.commit()
    conn.close()

    # Create frame PNG files
    frames_path.mkdir(parents=True, exist_ok=True)
    for fid in frame_ids:
        img = Image.new("RGB", (100, 100), color="green")
        img.save(str(frames_path / f"{fid}.png"))

    return chunk_id, frame_ids


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


class TestRetentionQueries:
    """Test retention-related SQLStore methods."""

    def test_get_expired_video_chunks(self, sql_store, tmp_path):
        """get_expired_video_chunks finds expired COMPLETED chunks."""
        from openrecall.shared.config import settings
        frames_path = settings.frames_path

        video_file = tmp_path / "expired.mp4"
        video_file.write_bytes(b"video")
        _seed_expired_chunk(settings.db_path, str(video_file), frames_path)

        expired = sql_store.get_expired_video_chunks()
        assert len(expired) == 1
        assert expired[0]["status"] == "COMPLETED"

    def test_non_expired_chunks_not_returned(self, sql_store):
        """Chunks with future expires_at are not returned."""
        sql_store.insert_video_chunk(
            file_path="/tmp/new.mp4",
            retention_days=30,  # 30 days in the future
        )
        expired = sql_store.get_expired_video_chunks()
        assert len(expired) == 0

    def test_chunks_expired_over_30_days_are_returned(self, sql_store):
        """>30-day expired completed chunks must be selected for cleanup."""
        from openrecall.shared.config import settings
        conn = sqlite3.connect(str(settings.db_path))
        conn.execute(
            "INSERT INTO video_chunks (file_path, status, expires_at) VALUES (?, 'COMPLETED', datetime('now', '-31 day'))",
            ("/tmp/expired31.mp4",),
        )
        conn.commit()
        conn.close()

        expired = sql_store.get_expired_video_chunks()
        paths = {row["file_path"] for row in expired}
        assert "/tmp/expired31.mp4" in paths

    def test_chunks_expiring_in_30_days_are_not_returned(self, sql_store):
        """Chunks expiring in the future (now + 30 days) must not be cleaned."""
        from openrecall.shared.config import settings
        conn = sqlite3.connect(str(settings.db_path))
        conn.execute(
            "INSERT INTO video_chunks (file_path, status, expires_at) VALUES (?, 'COMPLETED', datetime('now', '+30 day'))",
            ("/tmp/future30.mp4",),
        )
        conn.commit()
        conn.close()

        expired = sql_store.get_expired_video_chunks()
        paths = {row["file_path"] for row in expired}
        assert "/tmp/future30.mp4" not in paths

    def test_pending_expired_chunks_not_returned(self, sql_store, tmp_path):
        """Expired but PENDING chunks are not returned (only COMPLETED)."""
        from openrecall.shared.config import settings
        conn = sqlite3.connect(str(settings.db_path))
        conn.execute(
            "INSERT INTO video_chunks (file_path, status, expires_at) VALUES (?, 'PENDING', datetime('now', '-31 day'))",
            ("/tmp/pending.mp4",),
        )
        conn.commit()
        conn.close()

        expired = sql_store.get_expired_video_chunks()
        assert len(expired) == 0


class TestCascadeDelete:
    """Test cascade deletion of video chunks."""

    def test_delete_video_chunk_cascade(self, sql_store, tmp_path):
        """delete_video_chunk_cascade removes chunk + frames + OCR."""
        from openrecall.shared.config import settings
        frames_path = settings.frames_path

        video_file = tmp_path / "to_delete.mp4"
        video_file.write_bytes(b"video")
        chunk_id, frame_ids = _seed_expired_chunk(
            settings.db_path, str(video_file), frames_path,
        )

        frames_deleted = sql_store.delete_video_chunk_cascade(chunk_id)
        assert frames_deleted == 3

        # Verify chunk is gone
        chunk = sql_store.get_video_chunk_by_id(chunk_id)
        assert chunk is None

        # Verify frames are gone
        for fid in frame_ids:
            frame = sql_store.get_frame_by_id(fid)
            assert frame is None

    def test_fts_cleaned_on_cascade(self, sql_store, tmp_path):
        """FTS entries are also cleaned on cascade delete."""
        from openrecall.shared.config import settings
        frames_path = settings.frames_path

        video_file = tmp_path / "fts_test.mp4"
        video_file.write_bytes(b"video")
        chunk_id, frame_ids = _seed_expired_chunk(
            settings.db_path, str(video_file), frames_path,
        )

        # Verify FTS has entries before delete
        conn = sqlite3.connect(str(settings.db_path))
        count_before = conn.execute("SELECT COUNT(*) FROM ocr_text_fts").fetchone()[0]
        conn.close()
        assert count_before > 0

        sql_store.delete_video_chunk_cascade(chunk_id)

        # Verify FTS entries are gone
        conn = sqlite3.connect(str(settings.db_path))
        count_after = conn.execute("SELECT COUNT(*) FROM ocr_text_fts").fetchone()[0]
        conn.close()
        assert count_after == 0


class TestRetentionWorker:
    """Test RetentionWorker integration."""

    def test_cleanup_expired_video_chunks(self, sql_store, tmp_path):
        """RetentionWorker._cleanup_expired_video_chunks deletes expired data."""
        from openrecall.shared.config import settings
        import openrecall.server.retention as retention_module
        importlib.reload(retention_module)
        RetentionWorker = retention_module.RetentionWorker

        video_file = tmp_path / "expired_video.mp4"
        video_file.write_bytes(b"video data")

        chunk_id, frame_ids = _seed_expired_chunk(
            settings.db_path, str(video_file), settings.frames_path,
        )

        worker = RetentionWorker()
        worker._cleanup_expired_video_chunks(sql_store)

        # Video file should be deleted
        assert not video_file.exists()

        # Frame PNGs should be deleted
        for fid in frame_ids:
            assert not (settings.frames_path / f"{fid}.png").exists()

        # DB records should be gone
        assert sql_store.get_video_chunk_by_id(chunk_id) is None

    def test_cleanup_31_day_expired_chunk_deletes_all_related_data(self, sql_store, tmp_path):
        """31-day expired COMPLETED chunk cleanup deletes DB rows + files + FTS."""
        from openrecall.shared.config import settings
        import openrecall.server.retention as retention_module
        importlib.reload(retention_module)
        RetentionWorker = retention_module.RetentionWorker

        video_file = tmp_path / "expired31_video.mp4"
        video_file.write_bytes(b"video data")
        chunk_id, frame_ids = _seed_expired_chunk(
            settings.db_path,
            str(video_file),
            settings.frames_path,
            num_frames=2,
            days_ago=31,
        )

        conn = sqlite3.connect(str(settings.db_path))
        frame_count_before = conn.execute(
            "SELECT COUNT(*) FROM frames WHERE video_chunk_id=?",
            (chunk_id,),
        ).fetchone()[0]
        ocr_count_before = conn.execute(
            "SELECT COUNT(*) FROM ocr_text WHERE frame_id IN (SELECT id FROM frames WHERE video_chunk_id=?)",
            (chunk_id,),
        ).fetchone()[0]
        fts_count_before = conn.execute(
            "SELECT COUNT(*) FROM ocr_text_fts WHERE frame_id IN (SELECT id FROM frames WHERE video_chunk_id=?)",
            (chunk_id,),
        ).fetchone()[0]
        conn.close()

        assert frame_count_before == 2
        assert ocr_count_before == 2
        assert fts_count_before == 2

        worker = RetentionWorker()
        worker._cleanup_expired_video_chunks(sql_store)

        assert not video_file.exists()
        for fid in frame_ids:
            assert not (settings.frames_path / f"{fid}.png").exists()

        conn = sqlite3.connect(str(settings.db_path))
        frame_count_after = conn.execute(
            "SELECT COUNT(*) FROM frames WHERE video_chunk_id=?",
            (chunk_id,),
        ).fetchone()[0]
        ocr_count_after = conn.execute(
            "SELECT COUNT(*) FROM ocr_text WHERE frame_id IN (SELECT id FROM frames WHERE video_chunk_id=?)",
            (chunk_id,),
        ).fetchone()[0]
        fts_count_after = conn.execute(
            "SELECT COUNT(*) FROM ocr_text_fts WHERE frame_id IN (SELECT id FROM frames WHERE video_chunk_id=?)",
            (chunk_id,),
        ).fetchone()[0]
        conn.close()

        assert frame_count_after == 0
        assert ocr_count_after == 0
        assert fts_count_after == 0

    def test_retention_worker_stop(self):
        """RetentionWorker can be stopped cleanly."""
        from openrecall.server.retention import RetentionWorker
        worker = RetentionWorker()
        worker._stop_event.set()  # Pre-stop
        # Should not hang
        worker.stop()
        assert worker._stop_event.is_set()
