"""Phase 1.5 tests: OCR engine name propagation."""
import importlib
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from openrecall.server.video.frame_extractor import ExtractedFrame


def _init_test_db(db_path: Path):
    """Create test database with all required tables."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE IF NOT EXISTS entries (id INTEGER PRIMARY KEY AUTOINCREMENT, app TEXT, title TEXT, text TEXT, timestamp INTEGER UNIQUE, embedding BLOB, description TEXT, status TEXT DEFAULT 'COMPLETED')")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_timestamp ON entries (timestamp)")
    conn.execute("CREATE TABLE IF NOT EXISTS video_chunks (id INTEGER PRIMARY KEY AUTOINCREMENT, file_path TEXT NOT NULL, device_name TEXT DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now')), expires_at TEXT, encrypted INTEGER DEFAULT 0, checksum TEXT, status TEXT DEFAULT 'PENDING', app_name TEXT DEFAULT '', window_name TEXT DEFAULT '')")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_video_chunks_status ON video_chunks(status)")
    conn.execute("CREATE TABLE IF NOT EXISTS frames (id INTEGER PRIMARY KEY AUTOINCREMENT, video_chunk_id INTEGER NOT NULL, offset_index INTEGER NOT NULL, timestamp REAL NOT NULL, app_name TEXT DEFAULT '', window_name TEXT DEFAULT '', focused INTEGER DEFAULT 0, browser_url TEXT DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now')), FOREIGN KEY (video_chunk_id) REFERENCES video_chunks(id) ON DELETE CASCADE)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_frames_video_chunk_id ON frames(video_chunk_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_frames_timestamp ON frames(timestamp)")
    conn.execute("CREATE TABLE IF NOT EXISTS ocr_text (frame_id INTEGER NOT NULL, text TEXT NOT NULL, text_json TEXT, ocr_engine TEXT DEFAULT '', text_length INTEGER, created_at TEXT NOT NULL DEFAULT (datetime('now')), FOREIGN KEY (frame_id) REFERENCES frames(id) ON DELETE CASCADE)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ocr_text_frame_id ON ocr_text(frame_id)")
    conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS ocr_text_fts USING fts5(text, app_name, window_name, frame_id UNINDEXED, tokenize='unicode61')")
    conn.commit()
    conn.close()


def _init_fts_db(fts_path: Path):
    """Create FTS database."""
    fts_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(fts_path))
    conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS ocr_fts USING fts5(snapshot_id UNINDEXED, ocr_text, caption, keywords)")
    conn.commit()
    conn.close()


@pytest.fixture
def sql_store(tmp_path, monkeypatch):
    """Create an isolated SQLStore with test DB."""
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
    store = SQLStore()
    return store


class TestOCREngineName:
    """3 tests for OCR engine name propagation (Requirement C)."""

    def test_mock_ocr_engine_name_stored(self, sql_store, tmp_path):
        """Mock OCR provider with engine_name="test_engine" writes correct value."""
        from openrecall.server.video.processor import VideoChunkProcessor
        from openrecall.shared.config import settings

        settings.frames_path.mkdir(parents=True, exist_ok=True)

        # Create mock OCR with custom engine name
        mock_ocr = MagicMock()
        mock_ocr.extract_text.return_value = "Test OCR output"
        mock_ocr.engine_name = "test_engine"

        # Create chunk and mock frame
        chunk_id = sql_store.insert_video_chunk(file_path="/tmp/test.mp4")
        mock_frame = ExtractedFrame(
            path=tmp_path / "test_frame.png",
            offset_index=0,
            timestamp=1000.0,
            kept=True,
        )
        img = Image.new("RGB", (320, 240), color="blue")
        img.save(str(mock_frame.path), format="PNG")

        mock_extractor = MagicMock()
        mock_extractor.extract_frames.return_value = [mock_frame]

        processor = VideoChunkProcessor(
            frame_extractor=mock_extractor,
            ocr_provider=mock_ocr,
            sql_store=sql_store,
        )
        result = processor.process_chunk(chunk_id, "/tmp/test.mp4", 1000.0)
        assert result.error is None
        assert result.frames_with_ocr == 1

        # Verify ocr_engine in database
        conn = sqlite3.connect(str(settings.db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT ocr_engine FROM ocr_text LIMIT 1").fetchone()
        conn.close()
        assert row is not None
        assert row["ocr_engine"] == "test_engine"

    def test_fallback_ocr_provider_engine_name(self):
        """_FallbackOCRProvider has engine_name == 'fallback'."""
        from openrecall.server.video.processor import _FallbackOCRProvider
        provider = _FallbackOCRProvider()
        assert provider.engine_name == "fallback"

    def test_provider_without_engine_name_stores_unknown(self, sql_store, tmp_path):
        """Provider without engine_name attribute stores 'unknown'."""
        from openrecall.server.video.processor import VideoChunkProcessor
        from openrecall.shared.config import settings

        settings.frames_path.mkdir(parents=True, exist_ok=True)

        # Create mock OCR WITHOUT engine_name attribute
        mock_ocr = MagicMock(spec=[])  # spec=[] means no attributes
        mock_ocr.extract_text = MagicMock(return_value="Some text")
        # Do NOT set engine_name - processor should use getattr(..., "unknown")

        chunk_id = sql_store.insert_video_chunk(file_path="/tmp/test.mp4")
        mock_frame = ExtractedFrame(
            path=tmp_path / "test_frame.png",
            offset_index=0,
            timestamp=1000.0,
            kept=True,
        )
        img = Image.new("RGB", (320, 240), color="green")
        img.save(str(mock_frame.path), format="PNG")

        mock_extractor = MagicMock()
        mock_extractor.extract_frames.return_value = [mock_frame]

        processor = VideoChunkProcessor(
            frame_extractor=mock_extractor,
            ocr_provider=mock_ocr,
            sql_store=sql_store,
        )
        result = processor.process_chunk(chunk_id, "/tmp/test.mp4", 1000.0)
        assert result.error is None

        # Verify ocr_engine is "unknown"
        conn = sqlite3.connect(str(settings.db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT ocr_engine FROM ocr_text LIMIT 1").fetchone()
        conn.close()
        assert row is not None
        assert row["ocr_engine"] == "unknown"
