"""P1-S3 Unit Test: frames.text_source='ocr' marking.

Tests that text_source is correctly set to 'ocr' after successful
OCR processing.

SSOT: design.md D3, tasks.md §3.2
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


class TestTextSourceMark:
    """Tests for frames.text_source marking."""

    def test_update_text_source_sets_ocr(self, store: FramesStore, temp_db: Path):
        """Test that update_text_source sets text_source='ocr'."""
        frame_id, _ = store.claim_frame(
            capture_id="test-capture-001",
            metadata={"timestamp": "2026-03-17T12:00:00Z"},
        )

        # Initially text_source should be NULL
        with sqlite3.connect(str(temp_db)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT text_source FROM frames WHERE id = ?",
                (frame_id,),
            ).fetchone()
            assert row["text_source"] is None

        # Update text_source
        result = store.update_text_source(frame_id, "ocr")
        assert result is True

        # Verify update
        with sqlite3.connect(str(temp_db)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT text_source FROM frames WHERE id = ?",
                (frame_id,),
            ).fetchone()
            assert row["text_source"] == "ocr"

    def test_update_text_source_nonexistent_frame(self, store: FramesStore):
        """Test that updating nonexistent frame returns False."""
        result = store.update_text_source(99999, "ocr")
        assert result is False

    def test_text_source_remains_null_for_failed(self, store: FramesStore, temp_db: Path):
        """Test that failed frames don't get text_source set."""
        frame_id, _ = store.claim_frame(
            capture_id="test-capture-002",
            metadata={"timestamp": "2026-03-17T12:01:00Z"},
        )

        # Mark as failed (simulating OCR failure)
        store.mark_failed(
            frame_id=frame_id,
            reason="OCR_FAILED",
            request_id="req-001",
            capture_id="test-capture-002",
        )

        # text_source should still be NULL
        with sqlite3.connect(str(temp_db)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT text_source, status FROM frames WHERE id = ?",
                (frame_id,),
            ).fetchone()
            assert row["text_source"] is None
            assert row["status"] == "failed"

    def test_text_source_after_complete_flow(self, store: FramesStore, temp_db: Path):
        """Test text_source after full processing flow."""
        frame_id, _ = store.claim_frame(
            capture_id="test-capture-003",
            metadata={
                "timestamp": "2026-03-17T12:02:00Z",
                "app_name": "TestApp",
                "window_name": "TestWindow",
            },
        )

        # Simulate processing flow
        store.advance_frame_status(frame_id, "pending", "processing")
        store.insert_ocr_text(
            frame_id=frame_id,
            text="Sample OCR text",
            text_length=15,
            ocr_engine="rapidocr",
            app_name="TestApp",
            window_name="TestWindow",
        )
        store.update_text_source(frame_id, "ocr")
        store.advance_frame_status(frame_id, "processing", "completed")

        # Verify final state
        with sqlite3.connect(str(temp_db)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT status, text_source FROM frames WHERE id = ?",
                (frame_id,),
            ).fetchone()
            assert row["status"] == "completed"
            assert row["text_source"] == "ocr"

    def test_complete_accessibility_frame_sets_full_text(self, temp_db: Path):
        """Verify complete_accessibility_frame sets full_text."""
        from openrecall.server.database.frames_store import FramesStore

        store = FramesStore(db_path=temp_db)

        # Create a pending frame
        conn = sqlite3.connect(str(temp_db))
        conn.execute(
            """
            INSERT INTO frames (capture_id, timestamp, status)
            VALUES ('test-ax-full', '2026-03-25T12:00:00Z', 'pending')
            """
        )
        conn.commit()
        frame_id = conn.execute(
            "SELECT id FROM frames WHERE capture_id = 'test-ax-full'"
        ).fetchone()[0]
        conn.close()

        # Complete with accessibility
        store.complete_accessibility_frame(
            frame_id=frame_id,
            text="Accessibility content here",
            browser_url=None,
            content_hash=None,
            simhash=None,
            accessibility_tree_json="[]",
            accessibility_text_content="Accessibility content here",
            accessibility_node_count=1,
            accessibility_truncated=False,
            elements=[],
        )

        # Verify full_text is set
        conn = sqlite3.connect(str(temp_db))
        row = conn.execute(
            "SELECT full_text, text_source FROM frames WHERE id = ?", (frame_id,)
        ).fetchone()
        conn.close()

        assert row[0] == "Accessibility content here"
        assert row[1] == "accessibility"

    def test_update_full_text_after_ocr(self, temp_db: Path):
        """Verify update_full_text sets full_text for OCR frames."""
        from openrecall.server.database.frames_store import FramesStore

        store = FramesStore(db_path=temp_db)

        # Create a frame
        conn = sqlite3.connect(str(temp_db))
        conn.execute(
            """
            INSERT INTO frames (capture_id, timestamp, status, ocr_text)
            VALUES ('test-ocr-full', '2026-03-25T12:00:00Z', 'completed', 'OCR content')
            """
        )
        conn.commit()
        frame_id = conn.execute(
            "SELECT id FROM frames WHERE capture_id = 'test-ocr-full'"
        ).fetchone()[0]
        conn.close()

        # Update full_text
        store.update_full_text(frame_id, "OCR content")

        # Verify
        conn = sqlite3.connect(str(temp_db))
        row = conn.execute(
            "SELECT full_text FROM frames WHERE id = ?", (frame_id,)
        ).fetchone()
        conn.close()

        assert row[0] == "OCR content"
