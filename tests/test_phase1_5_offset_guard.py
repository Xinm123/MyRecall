"""Phase 1.5 tests: Offset guard validation."""
import logging

import pytest

from openrecall.server.video.processor import _validate_frame_offset
from openrecall.server.video.frame_extractor import ExtractedFrame
from pathlib import Path


def _make_frame(offset_index, timestamp, path=None):
    """Helper to create an ExtractedFrame for testing."""
    return ExtractedFrame(
        path=path or Path("/tmp/fake.png"),
        offset_index=offset_index,
        timestamp=timestamp,
        kept=True,
    )


class TestOffsetGuard:
    """6 tests for _validate_frame_offset()."""

    def test_negative_offset_rejected(self):
        """Negative offset_index is rejected."""
        frame = _make_frame(offset_index=-1, timestamp=1000.0)
        reason = _validate_frame_offset(
            frame, video_chunk_id=1, chunk_path="/tmp/test.mp4",
            chunk_start_time=1000.0, chunk_end_time=1060.0, prev_offset=-1,
        )
        assert reason == "negative_offset"

    def test_offset_zero_accepted(self):
        """Offset 0 is accepted normally."""
        frame = _make_frame(offset_index=0, timestamp=1000.0)
        reason = _validate_frame_offset(
            frame, video_chunk_id=1, chunk_path="/tmp/test.mp4",
            chunk_start_time=1000.0, chunk_end_time=1060.0, prev_offset=-1,
        )
        assert reason is None

    def test_timestamp_before_chunk_start_rejected(self):
        """Timestamp before chunk_start_time is rejected."""
        frame = _make_frame(offset_index=0, timestamp=999.0)
        reason = _validate_frame_offset(
            frame, video_chunk_id=1, chunk_path="/tmp/test.mp4",
            chunk_start_time=1000.0, chunk_end_time=1060.0, prev_offset=-1,
        )
        assert reason == "timestamp_before_chunk_start"

    def test_timestamp_after_chunk_end_rejected(self):
        """Timestamp after chunk_end_time is rejected."""
        frame = _make_frame(offset_index=0, timestamp=1061.0)
        reason = _validate_frame_offset(
            frame, video_chunk_id=1, chunk_path="/tmp/test.mp4",
            chunk_start_time=1000.0, chunk_end_time=1060.0, prev_offset=-1,
        )
        assert reason == "timestamp_after_chunk_end"

    def test_non_monotonic_offset_rejected(self):
        """Non-monotonic offset (3 after 5) is rejected."""
        frame = _make_frame(offset_index=3, timestamp=1015.0)
        reason = _validate_frame_offset(
            frame, video_chunk_id=1, chunk_path="/tmp/test.mp4",
            chunk_start_time=1000.0, chunk_end_time=1060.0, prev_offset=5,
        )
        assert reason == "non_monotonic_offset"

    def test_valid_sequential_offsets_accepted(self):
        """Valid sequential offsets all pass validation."""
        prev = -1
        for i in range(5):
            frame = _make_frame(offset_index=i, timestamp=1000.0 + i * 5)
            reason = _validate_frame_offset(
                frame, video_chunk_id=1, chunk_path="/tmp/test.mp4",
                chunk_start_time=1000.0, chunk_end_time=1060.0, prev_offset=prev,
            )
            assert reason is None, f"Frame {i} unexpectedly rejected: {reason}"
            prev = i

    def test_missing_required_fields_rejected(self):
        """Missing required fields (video_chunk_id/offset_index/chunk_path) are rejected."""
        frame = _make_frame(offset_index=0, timestamp=1000.0)
        # Missing video_chunk_id
        reason = _validate_frame_offset(
            frame, video_chunk_id=None, chunk_path="/tmp/test.mp4",
            chunk_start_time=1000.0, chunk_end_time=1060.0, prev_offset=-1,
        )
        assert reason == "missing_required_fields"

        # Missing chunk_path
        reason = _validate_frame_offset(
            frame, video_chunk_id=1, chunk_path=None,
            chunk_start_time=1000.0, chunk_end_time=1060.0, prev_offset=-1,
        )
        assert reason == "missing_required_fields"

    def test_offset_guard_structured_log(self, caplog):
        """Offset guard rejection produces structured log with required fields."""
        from openrecall.server.video.processor import VideoChunkProcessor
        from unittest.mock import MagicMock
        from PIL import Image
        import tempfile
        import importlib

        # Create a frame with negative offset to trigger rejection
        tmpdir = tempfile.mkdtemp()
        frame = ExtractedFrame(
            path=Path(tmpdir) / "test.png",
            offset_index=-1,
            timestamp=1000.0,
            kept=True,
        )
        img = Image.new("RGB", (10, 10), color="red")
        img.save(str(frame.path), format="PNG")

        mock_extractor = MagicMock()
        mock_extractor.extract_frames.return_value = [frame]

        mock_ocr = MagicMock()
        mock_ocr.extract_text.return_value = ""
        mock_ocr.engine_name = "test"

        # Need a real sql_store for get_video_chunk_by_id
        mock_sql = MagicMock()
        mock_sql.get_video_chunk_by_id.return_value = {"end_time": 1060.0}

        processor = VideoChunkProcessor(
            frame_extractor=mock_extractor,
            ocr_provider=mock_ocr,
            sql_store=mock_sql,
        )

        with caplog.at_level(logging.WARNING, logger="openrecall.server.video.processor"):
            processor.process_chunk(1, "/tmp/test.mp4", 1000.0)

        # Verify structured log fields
        assert any("offset_guard_reject" in record.message for record in caplog.records), \
            f"Expected offset_guard_reject in log, got: {[r.message for r in caplog.records]}"
        reject_log = next(r for r in caplog.records if "offset_guard_reject" in r.message)
        assert "reason=negative_offset" in reject_log.message
        assert "chunk_id=1" in reject_log.message
        assert "frame_id=unassigned" in reject_log.message
        assert "offset=-1" in reject_log.message
        assert "source=frame_extractor" in reject_log.message
        assert "source_key=" in reject_log.message
        assert "chunk_end_ts=1060.000" in reject_log.message
        assert "timestamp_utc=" in reject_log.message
