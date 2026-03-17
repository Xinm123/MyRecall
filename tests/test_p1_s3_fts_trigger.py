"""P1-S3 Integration Test: FTS trigger auto-population.

Tests that the FTS triggers correctly populate ocr_text_fts when
rows are inserted into ocr_text.

SSOT: initial_schema.sql - ocr_text_ai trigger
"""

import sqlite3
from pathlib import Path

import pytest

from openrecall.server.database.frames_store import FramesStore
from openrecall.server.database.migrations_runner import run_migrations


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


class TestFtsTrigger:
    """Tests for FTS trigger auto-population."""

    def test_ocr_text_insert_populates_fts(
        self, store: FramesStore, temp_db: Path
    ):
        """Test that inserting into ocr_text populates ocr_text_fts."""
        # Create a frame
        frame_id, _ = store.claim_frame(
            capture_id="fts-test-1",
            metadata={
                "timestamp": "2026-03-17T12:00:00Z",
                "app_name": "TestApp",
                "window_name": "TestWindow",
            },
        )

        # Insert OCR text
        store.insert_ocr_text(
            frame_id=frame_id,
            text="Hello World from OCR",
            text_length=19,
            ocr_engine="rapidocr",
            app_name="TestApp",
            window_name="TestWindow",
        )

        # Verify FTS was populated
        with sqlite3.connect(str(temp_db)) as conn:
            conn.row_factory = sqlite3.Row

            # Search for text
            rows = conn.execute(
                "SELECT * FROM ocr_text_fts WHERE ocr_text_fts MATCH 'Hello'",
            ).fetchall()

            assert len(rows) == 1
            assert rows[0]["frame_id"] == frame_id
            assert "Hello" in rows[0]["text"]

    def test_ocr_text_fts_search_by_word(
        self, store: FramesStore, temp_db: Path
    ):
        """Test FTS search by individual words."""
        frame_id, _ = store.claim_frame(
            capture_id="fts-test-2",
            metadata={"timestamp": "2026-03-17T12:01:00Z"},
        )

        store.insert_ocr_text(
            frame_id=frame_id,
            text="The quick brown fox jumps over lazy dog",
            text_length=39,
            ocr_engine="rapidocr",
            app_name="App",
            window_name="Window",
        )

        with sqlite3.connect(str(temp_db)) as conn:
            # Search for each word
            for word in ["quick", "brown", "fox", "jumps", "lazy", "dog"]:
                rows = conn.execute(
                    "SELECT * FROM ocr_text_fts WHERE ocr_text_fts MATCH ?",
                    (word,),
                ).fetchall()
                assert len(rows) == 1, f"Expected to find '{word}' in FTS"

    def test_ocr_text_fts_search_by_app_name(
        self, store: FramesStore, temp_db: Path
    ):
        """Test FTS search includes app_name."""
        frame_id, _ = store.claim_frame(
            capture_id="fts-test-3",
            metadata={"timestamp": "2026-03-17T12:02:00Z"},
        )

        store.insert_ocr_text(
            frame_id=frame_id,
            text="Some text content",
            text_length=18,
            ocr_engine="rapidocr",
            app_name="UniqueAppSearchTerm",
            window_name="Window",
        )

        with sqlite3.connect(str(temp_db)) as conn:
            # Search for app name
            rows = conn.execute(
                "SELECT * FROM ocr_text_fts WHERE ocr_text_fts MATCH 'UniqueAppSearchTerm'",
            ).fetchall()

            assert len(rows) == 1

    def test_ocr_text_fts_search_by_window_name(
        self, store: FramesStore, temp_db: Path
    ):
        """Test FTS search includes window_name."""
        frame_id, _ = store.claim_frame(
            capture_id="fts-test-4",
            metadata={"timestamp": "2026-03-17T12:03:00Z"},
        )

        store.insert_ocr_text(
            frame_id=frame_id,
            text="Content here",
            text_length=12,
            ocr_engine="rapidocr",
            app_name="App",
            window_name="UniqueWindowSearchTerm",
        )

        with sqlite3.connect(str(temp_db)) as conn:
            # Search for window name
            rows = conn.execute(
                "SELECT * FROM ocr_text_fts WHERE ocr_text_fts MATCH 'UniqueWindowSearchTerm'",
            ).fetchall()

            assert len(rows) == 1

    def test_ocr_text_fts_multiple_frames(
        self, store: FramesStore, temp_db: Path
    ):
        """Test FTS with multiple frames."""
        # Create multiple frames
        for i in range(3):
            frame_id, _ = store.claim_frame(
                capture_id=f"fts-multi-{i}",
                metadata={"timestamp": f"2026-03-17T12:0{i}:00Z"},
            )
            store.insert_ocr_text(
                frame_id=frame_id,
                text=f"Frame {i} content with keyword shared",
                text_length=35,
                ocr_engine="rapidocr",
                app_name=f"App{i}",
                window_name=f"Window{i}",
            )

        with sqlite3.connect(str(temp_db)) as conn:
            # Search for shared keyword
            rows = conn.execute(
                "SELECT * FROM ocr_text_fts WHERE ocr_text_fts MATCH 'shared'",
            ).fetchall()

            assert len(rows) == 3

    def test_ocr_text_fts_delete_cascades(
        self, store: FramesStore, temp_db: Path
    ):
        """Test that deleting ocr_text row removes from FTS."""
        frame_id, _ = store.claim_frame(
            capture_id="fts-delete-test",
            metadata={"timestamp": "2026-03-17T12:04:00Z"},
        )

        store.insert_ocr_text(
            frame_id=frame_id,
            text="Text to be deleted",
            text_length=18,
            ocr_engine="rapidocr",
            app_name="App",
            window_name="Window",
        )

        # Verify FTS has the row
        with sqlite3.connect(str(temp_db)) as conn:
            rows = conn.execute(
                "SELECT * FROM ocr_text_fts WHERE ocr_text_fts MATCH 'deleted'",
            ).fetchall()
            assert len(rows) == 1

        # Delete the ocr_text row
        with sqlite3.connect(str(temp_db)) as conn:
            conn.execute("DELETE FROM ocr_text WHERE frame_id = ?", (frame_id,))
            conn.commit()

        # Verify FTS is also deleted
        with sqlite3.connect(str(temp_db)) as conn:
            rows = conn.execute(
                "SELECT * FROM ocr_text_fts WHERE ocr_text_fts MATCH 'deleted'",
            ).fetchall()
            assert len(rows) == 0

    def test_ocr_text_fts_update_reflects_changes(
        self, store: FramesStore, temp_db: Path
    ):
        """Test that updating ocr_text updates FTS."""
        frame_id, _ = store.claim_frame(
            capture_id="fts-update-test",
            metadata={"timestamp": "2026-03-17T12:05:00Z"},
        )

        store.insert_ocr_text(
            frame_id=frame_id,
            text="Original text keyword",
            text_length=21,
            ocr_engine="rapidocr",
            app_name="App",
            window_name="Window",
        )

        # Verify original text in FTS
        with sqlite3.connect(str(temp_db)) as conn:
            rows = conn.execute(
                "SELECT * FROM ocr_text_fts WHERE ocr_text_fts MATCH 'Original'",
            ).fetchall()
            assert len(rows) == 1

        # Update the text
        with sqlite3.connect(str(temp_db)) as conn:
            conn.execute(
                "UPDATE ocr_text SET text = 'Updated text keyword' WHERE frame_id = ?",
                (frame_id,),
            )
            conn.commit()

        # Verify FTS reflects update
        with sqlite3.connect(str(temp_db)) as conn:
            # Original should not be found
            rows = conn.execute(
                "SELECT * FROM ocr_text_fts WHERE ocr_text_fts MATCH 'Original'",
            ).fetchall()
            assert len(rows) == 0

            # Updated should be found
            rows = conn.execute(
                "SELECT * FROM ocr_text_fts WHERE ocr_text_fts MATCH 'Updated'",
            ).fetchall()
            assert len(rows) == 1

    def test_ocr_text_fts_empty_text_not_indexed(self, temp_db: Path):
        """Test that empty text is not indexed in FTS.

        Per the trigger: WHEN NEW.text IS NOT NULL AND NEW.text != ''
        """
        with sqlite3.connect(str(temp_db)) as conn:
            # Create frame directly
            cursor = conn.execute(
                "INSERT INTO frames (capture_id, timestamp, status) VALUES (?, ?, 'pending')",
                ("empty-text-fts", "2026-03-17T12:06:00Z"),
            )
            frame_id = cursor.lastrowid

            # Insert with empty text (shouldn't happen due to assertion, but test trigger)
            conn.execute(
                "INSERT INTO ocr_text (frame_id, text, text_length, ocr_engine) VALUES (?, '', 0, 'rapidocr')",
                (frame_id,),
            )
            conn.commit()

            # FTS should be empty for this frame
            rows = conn.execute(
                "SELECT * FROM ocr_text_fts WHERE frame_id = ?",
                (frame_id,),
            ).fetchall()

            # Empty text should not be indexed
            assert len(rows) == 0
