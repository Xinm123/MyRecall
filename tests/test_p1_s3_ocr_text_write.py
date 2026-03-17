"""P1-S3 Unit Test: ocr_text row creation with correct fields.

Tests that OCR results are correctly persisted to the ocr_text table
with all required fields: frame_id, text, text_length, ocr_engine,
app_name, window_name.

SSOT: design.md D3, D5.1
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from openrecall.server.database.frames_store import FramesStore
from openrecall.server.database.migrations_runner import run_migrations
from openrecall.shared.config import settings


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Create a temporary database with v3 schema."""
    db_path = tmp_path / "test_edge.db"
    conn = sqlite3.connect(str(db_path))
    migrations_dir = Path(__file__).resolve().parent.parent / (
        "openrecall/server/database/migrations"
    )
    run_migrations(conn, migrations_dir)
    conn.close()
    return db_path


@pytest.fixture
def store(temp_db: Path) -> FramesStore:
    """Create a FramesStore with temporary database."""
    return FramesStore(db_path=temp_db)


class TestOcrTextWrite:
    """Tests for ocr_text row creation."""

    def test_insert_ocr_text_creates_row(self, store: FramesStore, temp_db: Path):
        """Test that insert_ocr_text creates a row with correct fields."""
        # First create a frame
        frame_id, _ = store.claim_frame(
            capture_id="test-capture-001",
            metadata={
                "timestamp": "2026-03-17T12:00:00Z",
                "app_name": "TestApp",
                "window_name": "TestWindow",
            },
        )

        # Insert OCR text
        result = store.insert_ocr_text(
            frame_id=frame_id,
            text="Hello World",
            text_length=11,
            ocr_engine="rapidocr",
            app_name="TestApp",
            window_name="TestWindow",
        )

        assert result is True

        # Verify the row was created
        with sqlite3.connect(str(temp_db)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM ocr_text WHERE frame_id = ?",
                (frame_id,),
            ).fetchone()

            assert row is not None
            assert row["text"] == "Hello World"
            assert row["text_length"] == 11
            assert row["ocr_engine"] == "rapidocr"
            assert row["app_name"] == "TestApp"
            assert row["window_name"] == "TestWindow"
            assert row["text_json"] is None  # P1 doesn't fill this

    def test_insert_ocr_text_idempotent(self, store: FramesStore, temp_db: Path):
        """Test that duplicate insert is ignored (INSERT OR IGNORE)."""
        frame_id, _ = store.claim_frame(
            capture_id="test-capture-002",
            metadata={
                "timestamp": "2026-03-17T12:01:00Z",
                "app_name": "App1",
                "window_name": "Window1",
            },
        )

        # First insert
        result1 = store.insert_ocr_text(
            frame_id=frame_id,
            text="First Text",
            text_length=10,
            ocr_engine="rapidocr",
            app_name="App1",
            window_name="Window1",
        )
        assert result1 is True

        # Second insert (should be ignored)
        result2 = store.insert_ocr_text(
            frame_id=frame_id,
            text="Second Text",
            text_length=11,
            ocr_engine="rapidocr",
            app_name="App1",
            window_name="Window1",
        )
        assert result2 is False  # No row inserted

        # Verify original text preserved
        with sqlite3.connect(str(temp_db)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT text FROM ocr_text WHERE frame_id = ?",
                (frame_id,),
            ).fetchone()

            assert row["text"] == "First Text"

    def test_insert_ocr_text_rejects_empty_text(self, store: FramesStore):
        """Test that empty text is rejected with assertion error."""
        frame_id, _ = store.claim_frame(
            capture_id="test-capture-003",
            metadata={"timestamp": "2026-03-17T12:02:00Z"},
        )

        with pytest.raises(AssertionError) as exc_info:
            store.insert_ocr_text(
                frame_id=frame_id,
                text="",  # Empty text should be rejected
                text_length=0,
                ocr_engine="rapidocr",
                app_name="App",
                window_name="Window",
            )

        assert "refusing empty text" in str(exc_info.value)

    def test_insert_ocr_text_fts_populated(self, store: FramesStore, temp_db: Path):
        """Test that FTS trigger populates ocr_text_fts."""
        frame_id, _ = store.claim_frame(
            capture_id="test-capture-004",
            metadata={
                "timestamp": "2026-03-17T12:03:00Z",
                "app_name": "SearchApp",
                "window_name": "SearchWindow",
            },
        )

        store.insert_ocr_text(
            frame_id=frame_id,
            text="This is searchable text",
            text_length=22,
            ocr_engine="rapidocr",
            app_name="SearchApp",
            window_name="SearchWindow",
        )

        # Verify FTS table was populated via trigger
        with sqlite3.connect(str(temp_db)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM ocr_text_fts WHERE ocr_text_fts MATCH 'searchable'",
            ).fetchall()

            assert len(rows) == 1
            assert rows[0]["frame_id"] == frame_id
            assert "searchable" in rows[0]["text"]

    def test_unique_constraint_on_frame_id(self, store: FramesStore, temp_db: Path):
        """Test that UNIQUE constraint prevents duplicate frame_id in ocr_text."""
        frame_id, _ = store.claim_frame(
            capture_id="test-capture-005",
            metadata={"timestamp": "2026-03-17T12:04:00Z"},
        )

        # First insert succeeds
        store.insert_ocr_text(
            frame_id=frame_id,
            text="Text 1",
            text_length=6,
            ocr_engine="rapidocr",
            app_name="App",
            window_name="Window",
        )

        # Direct insert without INSERT OR IGNORE should fail
        with sqlite3.connect(str(temp_db)) as conn:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO ocr_text (frame_id, text, text_length, ocr_engine) "
                    "VALUES (?, ?, ?, ?)",
                    (frame_id, "Text 2", 6, "rapidocr"),
                )
