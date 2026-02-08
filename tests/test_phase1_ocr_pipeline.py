"""Phase 1 tests: OCR pipeline and FTS insertion."""
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


class TestOCRTextInsertion:
    """Test OCR text storage in database."""

    def test_insert_ocr_text(self, sql_store):
        """insert_ocr_text stores text for a frame."""
        # Insert prereqs
        chunk_id = sql_store.insert_video_chunk(file_path="/tmp/test.mp4")
        assert chunk_id is not None
        frame_id = sql_store.insert_frame(video_chunk_id=chunk_id, offset_index=0, timestamp=1000.0)
        assert frame_id is not None

        sql_store.insert_ocr_text(frame_id, "Hello World from screen")

        # Verify
        from openrecall.shared.config import settings
        conn = sqlite3.connect(str(settings.db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM ocr_text WHERE frame_id=?", (frame_id,)).fetchone()
        conn.close()
        assert row is not None
        assert row["text"] == "Hello World from screen"
        assert row["text_length"] == len("Hello World from screen")

    def test_insert_ocr_text_with_engine(self, sql_store):
        """insert_ocr_text stores OCR engine name."""
        chunk_id = sql_store.insert_video_chunk(file_path="/tmp/test.mp4")
        frame_id = sql_store.insert_frame(video_chunk_id=chunk_id, offset_index=0, timestamp=1000.0)

        sql_store.insert_ocr_text(frame_id, "test", ocr_engine="rapidocr")

        from openrecall.shared.config import settings
        conn = sqlite3.connect(str(settings.db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM ocr_text WHERE frame_id=?", (frame_id,)).fetchone()
        conn.close()
        assert row["ocr_engine"] == "rapidocr"


class TestOCRFTSInsertion:
    """Test FTS5 index for OCR text."""

    def test_insert_ocr_text_fts(self, sql_store):
        """insert_ocr_text_fts adds entry to FTS index."""
        chunk_id = sql_store.insert_video_chunk(file_path="/tmp/test.mp4")
        frame_id = sql_store.insert_frame(video_chunk_id=chunk_id, offset_index=0, timestamp=1000.0)

        sql_store.insert_ocr_text_fts(frame_id, "Python programming language", app_name="VSCode", window_name="main.py")

        from openrecall.shared.config import settings
        conn = sqlite3.connect(str(settings.db_path))
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM ocr_text_fts WHERE frame_id=?", (frame_id,)).fetchone()
        conn.close()
        assert row is not None
        assert "Python" in row["text"]

    def test_fts_search_matches(self, sql_store):
        """FTS search finds matching OCR text."""
        chunk_id = sql_store.insert_video_chunk(file_path="/tmp/test.mp4")
        frame_id = sql_store.insert_frame(video_chunk_id=chunk_id, offset_index=0, timestamp=1000.0)

        sql_store.insert_ocr_text(frame_id, "Python programming language")
        sql_store.insert_ocr_text_fts(frame_id, "Python programming language", app_name="VSCode")

        results = sql_store.search_video_fts("Python", limit=10)
        assert len(results) > 0
        assert results[0]["frame_id"] == frame_id

    def test_fts_search_no_match(self, sql_store):
        """FTS search returns empty for non-matching query."""
        results = sql_store.search_video_fts("nonexistent_term_xyz", limit=10)
        assert len(results) == 0

    def test_fts_multiple_frames(self, sql_store):
        """FTS search returns multiple matching frames."""
        chunk_id = sql_store.insert_video_chunk(file_path="/tmp/test.mp4")

        for i in range(5):
            frame_id = sql_store.insert_frame(
                video_chunk_id=chunk_id, offset_index=i, timestamp=1000.0 + i
            )
            sql_store.insert_ocr_text(frame_id, f"Document editor frame {i}")
            sql_store.insert_ocr_text_fts(frame_id, f"Document editor frame {i}")

        results = sql_store.search_video_fts("Document editor", limit=10)
        assert len(results) == 5


class TestVideoChunkProcessor:
    """Test the full processing pipeline."""

    def test_processor_with_mock_ocr(self, sql_store, tmp_path):
        """VideoChunkProcessor processes frames with mock OCR."""
        from openrecall.server.video.processor import VideoChunkProcessor
        from PIL import Image

        # Create mock OCR provider
        mock_ocr = MagicMock()
        mock_ocr.extract_text.return_value = "Mock OCR text from frame"

        # Create test frames directory
        from openrecall.shared.config import settings
        settings.frames_path.mkdir(parents=True, exist_ok=True)

        # Create a fake chunk
        chunk_id = sql_store.insert_video_chunk(file_path="/tmp/fake.mp4")

        # Mock the frame extractor
        from openrecall.server.video.frame_extractor import ExtractedFrame
        mock_frame = ExtractedFrame(
            path=tmp_path / "test_frame.png",
            offset_index=0,
            timestamp=1000.0,
            kept=True,
        )
        # Create the test frame image
        img = Image.new("RGB", (320, 240), color="blue")
        img.save(str(mock_frame.path), format="PNG")

        mock_extractor = MagicMock()
        mock_extractor.extract_frames.return_value = [mock_frame]

        processor = VideoChunkProcessor(
            frame_extractor=mock_extractor,
            ocr_provider=mock_ocr,
            sql_store=sql_store,
        )

        result = processor.process_chunk(chunk_id, "/tmp/fake.mp4", 1000.0)

        assert result.error is None
        assert result.total_frames_extracted == 1
        assert result.frames_after_dedup == 1
        assert result.frames_with_ocr == 1
        assert result.elapsed_seconds >= 0

    def test_processor_handles_ocr_failure(self, sql_store, tmp_path):
        """Processor handles OCR failures gracefully."""
        from openrecall.server.video.processor import VideoChunkProcessor
        from openrecall.server.video.frame_extractor import ExtractedFrame
        from PIL import Image

        mock_ocr = MagicMock()
        mock_ocr.extract_text.side_effect = Exception("OCR failed")

        from openrecall.shared.config import settings
        settings.frames_path.mkdir(parents=True, exist_ok=True)

        chunk_id = sql_store.insert_video_chunk(file_path="/tmp/fake.mp4")

        mock_frame = ExtractedFrame(
            path=tmp_path / "test_frame.png",
            offset_index=0,
            timestamp=1000.0,
            kept=True,
        )
        img = Image.new("RGB", (320, 240), color="red")
        img.save(str(mock_frame.path), format="PNG")

        mock_extractor = MagicMock()
        mock_extractor.extract_frames.return_value = [mock_frame]

        processor = VideoChunkProcessor(
            frame_extractor=mock_extractor,
            ocr_provider=mock_ocr,
            sql_store=sql_store,
        )

        result = processor.process_chunk(chunk_id, "/tmp/fake.mp4", 1000.0)

        # Should complete without error even if OCR fails
        assert result.error is None
        assert result.frames_with_ocr == 0

    def test_processor_propagates_chunk_app_window_to_frames_and_fts(self, sql_store, tmp_path):
        """Chunk-level app/window metadata should be copied into frames and FTS rows."""
        from openrecall.server.video.processor import VideoChunkProcessor
        from openrecall.server.video.frame_extractor import ExtractedFrame
        from openrecall.shared.config import settings
        from PIL import Image

        settings.frames_path.mkdir(parents=True, exist_ok=True)

        chunk_id = sql_store.insert_video_chunk(
            file_path="/tmp/fake.mp4",
            app_name="Cursor",
            window_name="settings.json",
        )
        assert chunk_id is not None

        mock_ocr = MagicMock()
        mock_ocr.extract_text.return_value = "cursor token settings"

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

        result = processor.process_chunk(chunk_id, "/tmp/fake.mp4", 1000.0)
        assert result.error is None

        conn = sqlite3.connect(str(settings.db_path))
        conn.row_factory = sqlite3.Row
        frame_row = conn.execute("SELECT app_name, window_name FROM frames ORDER BY id DESC LIMIT 1").fetchone()
        fts_row = conn.execute("SELECT app_name, window_name FROM ocr_text_fts ORDER BY rowid DESC LIMIT 1").fetchone()
        conn.close()

        assert frame_row is not None
        assert frame_row["app_name"] == "Cursor"
        assert frame_row["window_name"] == "settings.json"
        assert fts_row is not None
        assert fts_row["app_name"] == "Cursor"
        assert fts_row["window_name"] == "settings.json"
