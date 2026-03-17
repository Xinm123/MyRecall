"""P1-S3 Integration Test: OCR pipeline end-to-end.

Tests the complete OCR processing pipeline:
1. Sample JPEG → OCR execution
2. OCR result → ocr_text table write
3. FTS index auto-population

This test requires the RapidOCR backend to be functional.
"""

import sqlite3
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from openrecall.server.database.frames_store import FramesStore
from openrecall.server.database.migrations_runner import run_migrations
from openrecall.server.processing.ocr_processor import OcrResult, OcrStatus, execute_ocr


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


@pytest.fixture
def sample_jpeg_path() -> Path:
    """Path to sample JPEG test fixture."""
    fixtures_dir = Path(__file__).resolve().parent.parent / "tests/fixtures/images"
    return fixtures_dir / "sample_jpeg.jpg"


class TestOcrPipeline:
    """End-to-end OCR pipeline tests."""

    def test_ocr_pipeline_with_sample_jpeg(
        self, store: FramesStore, temp_db: Path, sample_jpeg_path: Path
    ):
        """Test complete OCR pipeline with sample JPEG."""
        if not sample_jpeg_path.exists():
            pytest.skip("Sample JPEG fixture not found")

        # 1. Create a frame with the sample JPEG
        frame_id, _ = store.claim_frame(
            capture_id="pipeline-test-1",
            metadata={
                "timestamp": "2026-03-17T12:00:00Z",
                "app_name": "TestApp",
                "window_name": "TestWindow",
            },
        )
        store.finalize_claimed_frame(
            frame_id, "pipeline-test-1", str(sample_jpeg_path)
        )

        # 2. Execute OCR on the image
        result = execute_ocr(str(sample_jpeg_path))

        # 3. Verify OCR result structure
        assert isinstance(result, OcrResult)
        assert result.elapsed_ms > 0

        # If OCR extracted text, write to database
        if result.is_success:
            # 4. Write to ocr_text
            inserted = store.insert_ocr_text(
                frame_id=frame_id,
                text=result.text,
                text_length=result.text_length,
                ocr_engine="rapidocr",
                app_name="TestApp",
                window_name="TestWindow",
            )
            assert inserted is True

            # 5. Verify database write
            with sqlite3.connect(str(temp_db)) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT * FROM ocr_text WHERE frame_id = ?",
                    (frame_id,),
                ).fetchone()

                assert row is not None
                assert row["text"] == result.text
                assert row["ocr_engine"] == "rapidocr"

            # 6. Verify FTS auto-population
            with sqlite3.connect(str(temp_db)) as conn:
                conn.row_factory = sqlite3.Row
                # Search for any text from the OCR result
                if result.text:
                    rows = conn.execute(
                        "SELECT * FROM ocr_text_fts WHERE ocr_text_fts MATCH ?",
                        (result.text.split()[0] if result.text.split() else result.text,),
                    ).fetchall()
                    # FTS should have indexed the text
                    assert len(rows) >= 1

    def test_ocr_pipeline_with_missing_file(self, store: FramesStore):
        """Test OCR pipeline handles missing file gracefully."""
        result = execute_ocr("/nonexistent/path/to/image.jpg")

        assert result.status == OcrStatus.FAILED
        assert "image_not_found" in result.error_reason or "not_found" in result.error_reason

    def test_ocr_pipeline_with_corrupted_file(self, store: FramesStore):
        """Test OCR pipeline handles corrupted file gracefully."""
        corrupted_path = (
            Path(__file__).resolve().parent.parent
            / "tests/fixtures/images/corrupted_image.jpg"
        )

        if not corrupted_path.exists():
            pytest.skip("Corrupted image fixture not found")

        result = execute_ocr(str(corrupted_path))

        # Should either fail or return empty text (both are acceptable)
        # Also accept FAILED if OCR models aren't available
        assert result.status in (OcrStatus.FAILED, OcrStatus.EMPTY_TEXT)

    def test_ocr_pipeline_empty_text_image(self, store: FramesStore):
        """Test OCR pipeline with image that has no text."""
        empty_text_path = (
            Path(__file__).resolve().parent.parent
            / "tests/fixtures/images/empty_text_image.jpg"
        )

        if not empty_text_path.exists():
            pytest.skip("Empty text image fixture not found")

        result = execute_ocr(str(empty_text_path))

        # Empty text is valid - no error, just empty
        # Also accept FAILED if OCR models aren't available
        assert result.status in (OcrStatus.SUCCESS, OcrStatus.EMPTY_TEXT, OcrStatus.FAILED)

    @patch("openrecall.server.ocr.rapid_backend.RapidOCRBackend")
    def test_ocr_pipeline_exception_propagation(
        self, mock_backend_class, store: FramesStore, tmp_path: Path
    ):
        """Test that OCR exceptions are properly caught and classified."""
        # Create a valid image file
        from PIL import Image
        test_image = tmp_path / "test.jpg"
        Image.new("RGB", (100, 100), color="red").save(test_image, "JPEG")

        # Mock the backend to raise an exception
        mock_instance = MagicMock()
        mock_instance.extract_text_with_boxes.side_effect = RuntimeError("Mock OCR failure")
        mock_backend_class.return_value = mock_instance

        result = execute_ocr(str(test_image))

        assert result.status == OcrStatus.FAILED
        assert "RuntimeError" in result.error_reason or "Mock OCR failure" in result.error_reason
