"""P1-S3 Unit Test: three-layer idempotency defense.

Tests that the three-layer idempotency defense prevents duplicate
OCR processing:

Layer 1: Fetch filter - only get status='pending' frames
Layer 2: Pre-write check - check ocr_text existence before write
Layer 3: INSERT OR IGNORE - database-level safety net

SSOT: design.md D5
"""

import sqlite3
from pathlib import Path

import pytest

from openrecall.server.database.frames_store import FramesStore
from openrecall.server.database.migrations_runner import run_migrations
from openrecall.server.processing.idempotency import (
    check_ocr_text_exists,
    get_pending_frames_for_ocr,
)


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


class TestIdempotencyLayer1:
    """Tests for Layer 1: fetch filter (status='pending' only)."""

    def test_fetch_only_pending_frames(self, store: FramesStore, temp_db: Path):
        """Test that only pending frames are fetched."""
        # Create frames with different statuses
        frame_id_1, _ = store.claim_frame(
            capture_id="pending-1",
            metadata={"timestamp": "2026-03-17T12:00:00Z"},
        )
        frame_id_2, _ = store.claim_frame(
            capture_id="processing-1",
            metadata={"timestamp": "2026-03-17T12:01:00Z"},
        )
        store.advance_frame_status(frame_id_2, "pending", "processing")

        frame_id_3, _ = store.claim_frame(
            capture_id="completed-1",
            metadata={"timestamp": "2026-03-17T12:02:00Z"},
        )
        store.advance_frame_status(frame_id_3, "pending", "processing")
        store.advance_frame_status(frame_id_3, "processing", "completed")

        frame_id_4, _ = store.claim_frame(
            capture_id="failed-1",
            metadata={"timestamp": "2026-03-17T12:03:00Z"},
        )
        store.mark_failed(frame_id_4, "TEST", "req", "failed-1")

        # Fetch pending frames
        with sqlite3.connect(str(temp_db)) as conn:
            conn.row_factory = sqlite3.Row
            frames = get_pending_frames_for_ocr(conn)

            # Only frame_id_1 should be returned
            assert len(frames) == 1
            assert frames[0][0] == frame_id_1  # frame_id

    def test_fetch_returns_correct_tuple_structure(self, store: FramesStore, temp_db: Path):
        """Test that fetch returns correct tuple structure."""
        frame_id, _ = store.claim_frame(
            capture_id="test-tuple",
            metadata={
                "timestamp": "2026-03-17T12:00:00Z",
                "app_name": "TestApp",
                "window_name": "TestWindow",
            },
        )
        store.finalize_claimed_frame(frame_id, "test-tuple", "/path/to/snapshot.jpg")

        with sqlite3.connect(str(temp_db)) as conn:
            conn.row_factory = sqlite3.Row
            frames = get_pending_frames_for_ocr(conn)

            assert len(frames) == 1
            frame = frames[0]
            # (frame_id, capture_id, capture_trigger, app_name, window_name, snapshot_path)
            assert frame[0] == frame_id
            assert frame[1] == "test-tuple"
            assert frame[3] == "TestApp"
            assert frame[4] == "TestWindow"
            assert frame[5] == "/path/to/snapshot.jpg"


class TestIdempotencyLayer2:
    """Tests for Layer 2: pre-write check (ocr_text existence)."""

    def test_check_ocr_text_exists_false_initially(self, store: FramesStore, temp_db: Path):
        """Test that check_ocr_text_exists returns False when no row exists."""
        frame_id, _ = store.claim_frame(
            capture_id="check-1",
            metadata={"timestamp": "2026-03-17T12:00:00Z"},
        )

        with sqlite3.connect(str(temp_db)) as conn:
            exists = check_ocr_text_exists(conn, frame_id)
            assert exists is False

    def test_check_ocr_text_exists_true_after_insert(self, store: FramesStore, temp_db: Path):
        """Test that check_ocr_text_exists returns True after insert."""
        frame_id, _ = store.claim_frame(
            capture_id="check-2",
            metadata={"timestamp": "2026-03-17T12:00:00Z"},
        )

        # Insert OCR text
        store.insert_ocr_text(
            frame_id=frame_id,
            text="Test text",
            text_length=9,
            ocr_engine="rapidocr",
            app_name="App",
            window_name="Window",
        )

        with sqlite3.connect(str(temp_db)) as conn:
            exists = check_ocr_text_exists(conn, frame_id)
            assert exists is True


class TestIdempotencyLayer3:
    """Tests for Layer 3: INSERT OR IGNORE database-level safety net."""

    def test_insert_or_ignore_prevents_duplicate(self, store: FramesStore, temp_db: Path):
        """Test that INSERT OR IGNORE prevents duplicate ocr_text rows."""
        frame_id, _ = store.claim_frame(
            capture_id="layer3-1",
            metadata={"timestamp": "2026-03-17T12:00:00Z"},
        )

        # First insert
        result1 = store.insert_ocr_text(
            frame_id=frame_id,
            text="First",
            text_length=5,
            ocr_engine="rapidocr",
            app_name="App",
            window_name="Window",
        )
        assert result1 is True

        # Second insert should be ignored
        result2 = store.insert_ocr_text(
            frame_id=frame_id,
            text="Second",
            text_length=6,
            ocr_engine="rapidocr",
            app_name="App",
            window_name="Window",
        )
        assert result2 is False

    def test_unique_index_enforced(self, store: FramesStore, temp_db: Path):
        """Test that unique index is enforced at database level."""
        frame_id, _ = store.claim_frame(
            capture_id="layer3-2",
            metadata={"timestamp": "2026-03-17T12:00:00Z"},
        )

        # Insert via store method
        store.insert_ocr_text(
            frame_id=frame_id,
            text="Text",
            text_length=4,
            ocr_engine="rapidocr",
            app_name="App",
            window_name="Window",
        )

        # Try direct insert (should fail without OR IGNORE)
        with sqlite3.connect(str(temp_db)) as conn:
            with pytest.raises(sqlite3.IntegrityError):
                conn.execute(
                    "INSERT INTO ocr_text (frame_id, text, text_length, ocr_engine) "
                    "VALUES (?, ?, ?, ?)",
                    (frame_id, "Duplicate", 8, "rapidocr"),
                )


class TestIdempotencyIntegration:
    """Integration tests for all three layers working together."""

    def test_processing_skips_existing_ocr(self, store: FramesStore, temp_db: Path):
        """Test that processing would skip frames with existing ocr_text."""
        frame_id, _ = store.claim_frame(
            capture_id="integration-1",
            metadata={
                "timestamp": "2026-03-17T12:00:00Z",
                "app_name": "App",
                "window_name": "Window",
            },
        )

        # Pre-insert OCR text (simulating previous processing)
        store.insert_ocr_text(
            frame_id=frame_id,
            text="Pre-existing OCR",
            text_length=15,
            ocr_engine="rapidocr",
            app_name="App",
            window_name="Window",
        )

        # Layer 2 check should find it
        with sqlite3.connect(str(temp_db)) as conn:
            exists = check_ocr_text_exists(conn, frame_id)
            assert exists is True

        # Processing should skip (not duplicate)
        result = store.insert_ocr_text(
            frame_id=frame_id,
            text="New OCR",
            text_length=7,
            ocr_engine="rapidocr",
            app_name="App",
            window_name="Window",
        )
        assert result is False  # No new row inserted

        # Verify original text preserved
        with sqlite3.connect(str(temp_db)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT text FROM ocr_text WHERE frame_id = ?",
                (frame_id,),
            ).fetchone()
            assert row["text"] == "Pre-existing OCR"
