"""Phase 1 tests: FrameExtractor and frame deduplication."""
import importlib
import shutil
import subprocess
import time
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
from PIL import Image


def _has_ffmpeg():
    """Check if ffmpeg is available."""
    return shutil.which("ffmpeg") is not None


def _create_synthetic_video(output_path: str, duration: int = 5):
    """Create a synthetic test video with constant color."""
    cmd = [
        "ffmpeg", "-nostdin", "-y",
        "-f", "lavfi",
        "-i", f"color=c=blue:s=320x240:d={duration}",
        "-c:v", "libx264", "-crf", "23",
        "-pix_fmt", "yuv420p",
        output_path,
    ]
    try:
        subprocess.run(cmd, capture_output=True, check=True, timeout=30)
        return True
    except Exception:
        return False


def _create_changing_video(output_path: str, duration: int = 5):
    """Create a synthetic video with color changes each second."""
    # Use testsrc which produces changing frame numbers
    cmd = [
        "ffmpeg", "-nostdin", "-y",
        "-f", "lavfi",
        "-i", f"testsrc=size=320x240:rate=1:duration={duration}",
        "-c:v", "libx264", "-crf", "23",
        "-pix_fmt", "yuv420p",
        output_path,
    ]
    try:
        subprocess.run(cmd, capture_output=True, check=True, timeout=30)
        return True
    except Exception:
        return False


@pytest.fixture
def setup_env(tmp_path, monkeypatch):
    """Set up environment for FrameExtractor tests."""
    monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "MRS"))
    monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "MRC"))
    monkeypatch.setenv("OPENRECALL_FRAME_EXTRACTION_INTERVAL", "1.0")
    importlib.reload(importlib.import_module("openrecall.shared.config"))
    return tmp_path


@pytest.fixture
def synthetic_video(tmp_path):
    """Create a static synthetic test video."""
    video_path = str(tmp_path / "test_chunk.mp4")
    if not _has_ffmpeg():
        pytest.skip("FFmpeg not available")
    if not _create_synthetic_video(video_path, duration=5):
        pytest.skip("Failed to create synthetic video")
    return video_path


@pytest.fixture
def changing_video(tmp_path):
    """Create a synthetic video with changing frames."""
    video_path = str(tmp_path / "changing_chunk.mp4")
    if not _has_ffmpeg():
        pytest.skip("FFmpeg not available")
    if not _create_changing_video(video_path, duration=5):
        pytest.skip("Failed to create changing video")
    return video_path


class TestFrameExtractorExtraction:
    """Test frame extraction from video chunks."""

    @pytest.mark.skipif(not _has_ffmpeg(), reason="FFmpeg not available")
    def test_extract_frames_returns_list(self, setup_env, synthetic_video):
        """extract_frames returns a list of ExtractedFrame objects."""
        from openrecall.server.video.frame_extractor import FrameExtractor

        frames_dir = setup_env / "MRS" / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        extractor = FrameExtractor(
            extraction_interval=1.0,
            dedup_threshold=0.99,  # Keep most frames
            frames_dir=frames_dir,
        )
        frames = extractor.extract_frames(
            synthetic_video, video_chunk_id=1, chunk_start_time=1000.0
        )
        assert isinstance(frames, list)
        assert len(frames) > 0

    @pytest.mark.skipif(not _has_ffmpeg(), reason="FFmpeg not available")
    def test_extracted_frames_have_correct_attributes(self, setup_env, synthetic_video):
        """Each ExtractedFrame has path, offset_index, timestamp, kept."""
        from openrecall.server.video.frame_extractor import FrameExtractor

        frames_dir = setup_env / "MRS" / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        extractor = FrameExtractor(
            extraction_interval=1.0,
            dedup_threshold=0.99,
            frames_dir=frames_dir,
        )
        frames = extractor.extract_frames(
            synthetic_video, video_chunk_id=1, chunk_start_time=1000.0
        )
        for frame in frames:
            assert hasattr(frame, "path")
            assert hasattr(frame, "offset_index")
            assert hasattr(frame, "timestamp")
            assert hasattr(frame, "kept")
            assert frame.kept is True
            assert frame.path.exists()

    @pytest.mark.skipif(not _has_ffmpeg(), reason="FFmpeg not available")
    def test_frame_timestamps_are_sequential(self, setup_env, synthetic_video):
        """Frame timestamps increase monotonically."""
        from openrecall.server.video.frame_extractor import FrameExtractor

        frames_dir = setup_env / "MRS" / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        extractor = FrameExtractor(
            extraction_interval=1.0,
            dedup_threshold=0.99,
            frames_dir=frames_dir,
        )
        frames = extractor.extract_frames(
            synthetic_video, video_chunk_id=1, chunk_start_time=1000.0
        )
        timestamps = [f.timestamp for f in frames]
        for i in range(1, len(timestamps)):
            assert timestamps[i] > timestamps[i - 1]

    @pytest.mark.skipif(not _has_ffmpeg(), reason="FFmpeg not available")
    def test_frame_pngs_are_valid_images(self, setup_env, synthetic_video):
        """Extracted frame PNGs are valid images that can be opened."""
        from openrecall.server.video.frame_extractor import FrameExtractor

        frames_dir = setup_env / "MRS" / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        extractor = FrameExtractor(
            extraction_interval=1.0,
            dedup_threshold=0.99,
            frames_dir=frames_dir,
        )
        frames = extractor.extract_frames(
            synthetic_video, video_chunk_id=1, chunk_start_time=1000.0
        )
        for frame in frames:
            img = Image.open(frame.path)
            assert img.size[0] > 0
            assert img.size[1] > 0


class TestFrameExtractorDedup:
    """Test MSSIM-based frame deduplication."""

    @pytest.mark.skipif(not _has_ffmpeg(), reason="FFmpeg not available")
    def test_dedup_with_static_video(self, setup_env, synthetic_video):
        """Static video (no changes) should result in few kept frames."""
        from openrecall.server.video.frame_extractor import FrameExtractor

        frames_dir = setup_env / "MRS" / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        extractor = FrameExtractor(
            extraction_interval=1.0,
            dedup_threshold=0.95,
            frames_dir=frames_dir,
        )
        frames = extractor.extract_frames(
            synthetic_video, video_chunk_id=1, chunk_start_time=1000.0
        )
        # Static blue video - only first frame should be kept (rest are near-identical)
        assert len(frames) <= 2

    @pytest.mark.skipif(not _has_ffmpeg(), reason="FFmpeg not available")
    def test_dedup_threshold_high_keeps_all(self, setup_env, synthetic_video):
        """With threshold > 1.0, no frames should be deduped (MSSIM never exceeds 1.0)."""
        from openrecall.server.video.frame_extractor import FrameExtractor

        frames_dir = setup_env / "MRS" / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        # Note: threshold must be > 1.0 because 0.0 is falsy and falls through to default
        extractor = FrameExtractor(
            extraction_interval=1.0,
            dedup_threshold=1.01,
            frames_dir=frames_dir,
        )
        frames = extractor.extract_frames(
            synthetic_video, video_chunk_id=1, chunk_start_time=1000.0
        )
        # All raw frames should be kept since no similarity exceeds 1.01
        assert len(frames) >= 3  # 5-second video at 1fps = ~5 frames

    @pytest.mark.skipif(not _has_ffmpeg(), reason="FFmpeg not available")
    def test_changing_video_keeps_more_frames(self, setup_env, changing_video):
        """Changing video content produces more kept frames than static."""
        from openrecall.server.video.frame_extractor import FrameExtractor

        frames_dir = setup_env / "MRS" / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        extractor = FrameExtractor(
            extraction_interval=1.0,
            dedup_threshold=0.95,
            frames_dir=frames_dir,
        )
        frames = extractor.extract_frames(
            changing_video, video_chunk_id=1, chunk_start_time=1000.0
        )
        # testsrc produces visibly different frames each second
        assert len(frames) >= 2


class TestFrameExtractorFFmpeg:
    """Test FFmpeg subprocess invocation."""

    @pytest.mark.skipif(not _has_ffmpeg(), reason="FFmpeg not available")
    def test_run_ffmpeg_extraction(self, setup_env, synthetic_video):
        """_run_ffmpeg_extraction produces frame PNGs in output dir."""
        from openrecall.server.video.frame_extractor import FrameExtractor

        frames_dir = setup_env / "MRS" / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        extractor = FrameExtractor(
            extraction_interval=1.0,
            frames_dir=frames_dir,
        )
        import tempfile

        with tempfile.TemporaryDirectory(prefix="test_extract_") as tmpdir:
            raw_frames = extractor._run_ffmpeg_extraction(synthetic_video, tmpdir)
            assert len(raw_frames) > 0
            for f in raw_frames:
                assert f.exists()
                assert f.suffix == ".png"

    def test_run_ffmpeg_invalid_path(self, setup_env):
        """_run_ffmpeg_extraction returns empty for invalid video path."""
        from openrecall.server.video.frame_extractor import FrameExtractor

        frames_dir = setup_env / "MRS" / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        extractor = FrameExtractor(frames_dir=frames_dir)
        import tempfile

        with tempfile.TemporaryDirectory(prefix="test_invalid_") as tmpdir:
            raw_frames = extractor._run_ffmpeg_extraction("/nonexistent.mp4", tmpdir)
            assert raw_frames == []


class TestFrameExtractorSingleFrame:
    """Test on-demand single frame extraction."""

    @pytest.mark.skipif(not _has_ffmpeg(), reason="FFmpeg not available")
    def test_extract_single_frame(self, setup_env, synthetic_video):
        """extract_single_frame returns a valid PNG path."""
        from openrecall.server.video.frame_extractor import FrameExtractor

        frames_dir = setup_env / "MRS" / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        extractor = FrameExtractor(frames_dir=frames_dir)
        result = extractor.extract_single_frame(synthetic_video, offset_seconds=2.0)
        assert result is not None
        assert result.exists()
        assert result.suffix == ".png"

    @pytest.mark.skipif(not _has_ffmpeg(), reason="FFmpeg not available")
    def test_extract_single_frame_at_zero(self, setup_env, synthetic_video):
        """extract_single_frame at offset 0 works."""
        from openrecall.server.video.frame_extractor import FrameExtractor

        frames_dir = setup_env / "MRS" / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        extractor = FrameExtractor(frames_dir=frames_dir)
        result = extractor.extract_single_frame(synthetic_video, offset_seconds=0.0)
        assert result is not None
        assert result.exists()

    def test_extract_single_frame_invalid_path(self, setup_env):
        """extract_single_frame returns None for invalid path."""
        from openrecall.server.video.frame_extractor import FrameExtractor

        frames_dir = setup_env / "MRS" / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        extractor = FrameExtractor(frames_dir=frames_dir)
        result = extractor.extract_single_frame(
            "/nonexistent/video.mp4", offset_seconds=0.0
        )
        assert result is None


class TestFrameExtractorPerformance:
    """Gate 1-P-01: Frame extraction performance."""

    @pytest.mark.skipif(not _has_ffmpeg(), reason="FFmpeg not available")
    def test_extraction_latency(self, setup_env, synthetic_video):
        """Frame extraction should complete in reasonable time."""
        from openrecall.server.video.frame_extractor import FrameExtractor

        frames_dir = setup_env / "MRS" / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        extractor = FrameExtractor(
            extraction_interval=1.0,
            dedup_threshold=0.99,
            frames_dir=frames_dir,
        )
        t0 = time.perf_counter()
        frames = extractor.extract_frames(
            synthetic_video, video_chunk_id=1, chunk_start_time=1000.0
        )
        elapsed = time.perf_counter() - t0
        # For a 5-second video, extraction should complete in <30s
        assert elapsed < 30.0, f"Extraction took {elapsed:.1f}s (expected <30s)"
        assert len(frames) > 0
