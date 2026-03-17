"""P1-S3 Unit Test: failed state semantics for OCR failures.

Tests that various OCR failure modes result in correct 'failed' status
and error_message values:
- Exception during OCR
- Empty text result
- Null result (defensive)

SSOT: design.md D2 - OCR result classification
"""

import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from openrecall.server.database.frames_store import FramesStore
from openrecall.server.database.migrations_runner import run_migrations
from openrecall.server.processing.ocr_processor import (
    OcrResult,
    OcrStatus,
    execute_ocr,
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


class TestFailedSemantics:
    """Tests for OCR failure classification and state management."""

    def test_ocr_exception_results_in_failed(self, store: FramesStore, temp_db: Path):
        """Test that OCR exception results in 'failed' status with error message."""
        frame_id, _ = store.claim_frame(
            capture_id="test-capture-exception",
            metadata={
                "timestamp": "2026-03-17T12:00:00Z",
                "app_name": "TestApp",
            },
        )
        store.advance_frame_status(frame_id, "pending", "processing")

        # Simulate OCR exception result
        ocr_result = OcrResult(
            status=OcrStatus.FAILED,
            error_reason="OCR_FAILED: RuntimeError: Mock OCR error",
            elapsed_ms=100.0,
        )

        # Verify result classification
        assert ocr_result.is_failed is True
        assert ocr_result.is_success is False

        # Mark frame as failed
        store.mark_failed(
            frame_id=frame_id,
            reason=ocr_result.error_reason,
            request_id="req-001",
            capture_id="test-capture-exception",
        )

        # Verify database state
        with sqlite3.connect(str(temp_db)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT status, error_message FROM frames WHERE id = ?",
                (frame_id,),
            ).fetchone()
            assert row["status"] == "failed"
            assert "OCR_FAILED" in row["error_message"]

    def test_ocr_empty_text_results_in_failed(self, store: FramesStore, temp_db: Path):
        """Test that empty OCR text results in 'failed' status."""
        frame_id, _ = store.claim_frame(
            capture_id="test-capture-empty",
            metadata={"timestamp": "2026-03-17T12:01:00Z"},
        )
        store.advance_frame_status(frame_id, "pending", "processing")

        # Simulate empty text result
        ocr_result = OcrResult(
            status=OcrStatus.EMPTY_TEXT,
            error_reason="OCR_EMPTY_TEXT",
            elapsed_ms=50.0,
        )

        # Verify result classification
        assert ocr_result.is_failed is True
        assert ocr_result.status == OcrStatus.EMPTY_TEXT

        # Mark frame as failed
        store.mark_failed(
            frame_id=frame_id,
            reason=ocr_result.error_reason,
            request_id="req-002",
            capture_id="test-capture-empty",
        )

        # Verify database state
        with sqlite3.connect(str(temp_db)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT status, error_message FROM frames WHERE id = ?",
                (frame_id,),
            ).fetchone()
            assert row["status"] == "failed"
            assert "OCR_EMPTY_TEXT" in row["error_message"]

    def test_ocr_null_result_defensive(self, store: FramesStore, temp_db: Path):
        """Test that null OCR result (defensive) results in 'failed' status."""
        frame_id, _ = store.claim_frame(
            capture_id="test-capture-null",
            metadata={"timestamp": "2026-03-17T12:02:00Z"},
        )
        store.advance_frame_status(frame_id, "pending", "processing")

        # Simulate null result (defensive path)
        ocr_result = OcrResult(
            status=OcrStatus.FAILED,
            error_reason="OCR_FAILED: null_result",
            elapsed_ms=75.0,
        )

        # Verify result classification
        assert ocr_result.is_failed is True

        # Mark frame as failed
        store.mark_failed(
            frame_id=frame_id,
            reason=ocr_result.error_reason,
            request_id="req-003",
            capture_id="test-capture-null",
        )

        # Verify database state
        with sqlite3.connect(str(temp_db)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT status, error_message FROM frames WHERE id = ?",
                (frame_id,),
            ).fetchone()
            assert row["status"] == "failed"
            assert "null_result" in row["error_message"]

    def test_ocr_success_not_marked_failed(self, store: FramesStore, temp_db: Path):
        """Test that successful OCR does NOT result in 'failed' status."""
        frame_id, _ = store.claim_frame(
            capture_id="test-capture-success",
            metadata={
                "timestamp": "2026-03-17T12:03:00Z",
                "app_name": "App",
                "window_name": "Window",
            },
        )
        store.advance_frame_status(frame_id, "pending", "processing")

        # Simulate successful OCR result
        ocr_result = OcrResult(
            status=OcrStatus.SUCCESS,
            text="This is extracted text",
            elapsed_ms=150.0,
        )

        # Verify result classification
        assert ocr_result.is_success is True
        assert ocr_result.is_failed is False
        assert ocr_result.text_length == 22

        # Insert OCR text and complete processing
        store.insert_ocr_text(
            frame_id=frame_id,
            text=ocr_result.text,
            text_length=ocr_result.text_length,
            ocr_engine="rapidocr",
            app_name="App",
            window_name="Window",
        )
        store.update_text_source(frame_id, "ocr")
        store.advance_frame_status(frame_id, "processing", "completed")

        # Verify database state
        with sqlite3.connect(str(temp_db)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT status, text_source, error_message FROM frames WHERE id = ?",
                (frame_id,),
            ).fetchone()
            assert row["status"] == "completed"
            assert row["text_source"] == "ocr"
            assert row["error_message"] is None

    def test_failed_frame_has_no_ocr_text_row(self, store: FramesStore, temp_db: Path):
        """Test that failed frames do not have ocr_text rows."""
        frame_id, _ = store.claim_frame(
            capture_id="test-capture-no-ocr",
            metadata={"timestamp": "2026-03-17T12:04:00Z"},
        )
        store.advance_frame_status(frame_id, "pending", "processing")

        # Simulate failure and mark
        store.mark_failed(
            frame_id=frame_id,
            reason="OCR_FAILED",
            request_id="req-004",
            capture_id="test-capture-no-ocr",
        )

        # Verify no ocr_text row exists
        with sqlite3.connect(str(temp_db)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT COUNT(*) as cnt FROM ocr_text WHERE frame_id = ?",
                (frame_id,),
            ).fetchone()
            assert row["cnt"] == 0
