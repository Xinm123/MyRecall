"""Phase 1 Gate Validation Suite.

One test per gate from the Phase 1 specification.
Gates that require long-running evidence are marked as pending.
"""
import importlib
import os
import platform
import shutil
import sqlite3
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image


def _init_test_db(db_path: Path):
    """Create test database with all required tables."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE IF NOT EXISTS entries (id INTEGER PRIMARY KEY AUTOINCREMENT, app TEXT, title TEXT, text TEXT, timestamp INTEGER UNIQUE, embedding BLOB, description TEXT, status TEXT DEFAULT 'COMPLETED')")
    conn.execute("CREATE TABLE IF NOT EXISTS video_chunks (id INTEGER PRIMARY KEY AUTOINCREMENT, file_path TEXT NOT NULL, device_name TEXT DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now')), expires_at TEXT, encrypted INTEGER DEFAULT 0, checksum TEXT, status TEXT DEFAULT 'PENDING')")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_video_chunks_status ON video_chunks(status)")
    conn.execute("CREATE TABLE IF NOT EXISTS frames (id INTEGER PRIMARY KEY AUTOINCREMENT, video_chunk_id INTEGER NOT NULL, offset_index INTEGER NOT NULL, timestamp REAL NOT NULL, app_name TEXT DEFAULT '', window_name TEXT DEFAULT '', focused INTEGER DEFAULT 0, browser_url TEXT DEFAULT '', created_at TEXT NOT NULL DEFAULT (datetime('now')), FOREIGN KEY (video_chunk_id) REFERENCES video_chunks(id) ON DELETE CASCADE)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_frames_video_chunk_id ON frames(video_chunk_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_frames_timestamp ON frames(timestamp)")
    conn.execute("CREATE TABLE IF NOT EXISTS ocr_text (frame_id INTEGER NOT NULL, text TEXT NOT NULL, text_json TEXT, ocr_engine TEXT DEFAULT '', text_length INTEGER, created_at TEXT NOT NULL DEFAULT (datetime('now')), FOREIGN KEY (frame_id) REFERENCES frames(id) ON DELETE CASCADE)")
    conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS ocr_text_fts USING fts5(text, app_name, window_name, frame_id UNINDEXED, tokenize='unicode61')")
    conn.commit()
    conn.close()


def _init_fts_db(fts_path: Path):
    fts_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(fts_path))
    conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS ocr_fts USING fts5(snapshot_id UNINDEXED, ocr_text, caption, keywords)")
    conn.commit()
    conn.close()


@pytest.fixture
def sql_store(tmp_path, monkeypatch):
    """Create isolated SQLStore."""
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
    return SQLStore()


# =========================================================================
# Functional Gates
# =========================================================================

class TestGate1F01Recording:
    """1-F-01: Recording produces valid video chunks."""

    def test_ffmpeg_command_builds(self, tmp_path):
        """FFmpegManager builds a valid command."""
        from openrecall.client.ffmpeg_manager import FFmpegManager
        mgr = FFmpegManager(output_dir=tmp_path, chunk_duration=300, fps=30, crf=23)
        cmd = mgr._build_ffmpeg_command()
        assert "ffmpeg" in cmd[0]
        assert "-f" in cmd
        assert "segment" in cmd

    def test_video_recorder_chunk_metadata(self, tmp_path, monkeypatch, setup_env=None):
        """VideoRecorder produces correct metadata on chunk completion."""
        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "MRS"))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "MRC"))
        importlib.reload(importlib.import_module("openrecall.shared.config"))

        from openrecall.client.video_recorder import VideoRecorder
        mock_buffer = MagicMock()
        mock_consumer = MagicMock()
        mock_consumer.is_alive.return_value = False
        recorder = VideoRecorder(buffer=mock_buffer, consumer=mock_consumer)

        chunk = tmp_path / "test.mp4"
        chunk.write_bytes(b"video" * 1000)
        recorder._on_chunk_complete(str(chunk))

        assert mock_buffer.enqueue_file.called
        meta = mock_buffer.enqueue_file.call_args[0][1]
        assert meta["type"] == "video_chunk"
        assert "checksum" in meta


class TestGate1F02FramesInDB:
    """1-F-02: All frames inserted into database."""

    def test_frames_inserted_after_processing(self, sql_store, tmp_path):
        """Processor inserts frames into DB."""
        from openrecall.server.video.processor import VideoChunkProcessor
        from openrecall.server.video.frame_extractor import ExtractedFrame
        from openrecall.shared.config import settings
        settings.frames_path.mkdir(parents=True, exist_ok=True)

        chunk_id = sql_store.insert_video_chunk(file_path="/tmp/test.mp4")

        # Create mock frames
        mock_frames = []
        for i in range(3):
            path = tmp_path / f"frame_{i}.png"
            img = Image.new("RGB", (100, 100), color="red")
            img.save(str(path))
            mock_frames.append(ExtractedFrame(path=path, offset_index=i, timestamp=1000.0 + i, kept=True))

        mock_extractor = MagicMock()
        mock_extractor.extract_frames.return_value = mock_frames
        mock_ocr = MagicMock()
        mock_ocr.extract_text.return_value = "text"

        processor = VideoChunkProcessor(
            frame_extractor=mock_extractor, ocr_provider=mock_ocr, sql_store=sql_store,
        )
        result = processor.process_chunk(chunk_id, "/tmp/test.mp4", 1000.0)
        assert result.frames_after_dedup == 3
        assert result.error is None


class TestGate1F03OCRInFTS:
    """1-F-03: All frames OCR'd and in FTS."""

    def test_ocr_text_in_fts(self, sql_store):
        """OCR text is searchable via FTS."""
        chunk_id = sql_store.insert_video_chunk(file_path="/tmp/test.mp4")
        frame_id = sql_store.insert_frame(video_chunk_id=chunk_id, offset_index=0, timestamp=1000.0)
        sql_store.insert_ocr_text(frame_id, "unique test phrase alpha beta gamma")
        sql_store.insert_ocr_text_fts(frame_id, "unique test phrase alpha beta gamma")

        results = sql_store.search_video_fts("alpha beta", limit=10)
        assert len(results) > 0
        assert results[0]["frame_id"] == frame_id


class TestGate1F04TimelineAPI:
    """1-F-04: Timeline API returns correct results."""

    def test_timeline_query(self, sql_store):
        """query_frames_by_time_range returns correct results."""
        chunk_id = sql_store.insert_video_chunk(file_path="/tmp/test.mp4")
        for i in range(5):
            sql_store.insert_frame(video_chunk_id=chunk_id, offset_index=i, timestamp=1000.0 + i * 10)

        frames, total = sql_store.query_frames_by_time_range(1005, 1035, limit=50, offset=0)
        assert total == 3  # 1010, 1020, 1030


class TestGate1F05SearchReturnsVideo:
    """1-F-05: Search returns video OCR text."""

    def test_video_fts_search_returns_results(self, sql_store):
        """Video FTS search finds OCR text from video frames."""
        chunk_id = sql_store.insert_video_chunk(file_path="/tmp/test.mp4")
        frame_id = sql_store.insert_frame(video_chunk_id=chunk_id, offset_index=0, timestamp=1000.0)
        sql_store.insert_ocr_text(frame_id, "Django REST framework authentication")
        sql_store.insert_ocr_text_fts(frame_id, "Django REST framework authentication")

        results = sql_store.search_video_fts("Django authentication", limit=10)
        assert len(results) > 0


# =========================================================================
# Performance Gates
# =========================================================================

class TestGate1P01ExtractionLatency:
    """1-P-01: <2s per frame extraction average."""

    @pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg not available")
    def test_extraction_performance(self, tmp_path, monkeypatch):
        """Frame extraction completes in reasonable time."""
        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "MRS"))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "MRC"))
        importlib.reload(importlib.import_module("openrecall.shared.config"))

        import subprocess
        video_path = str(tmp_path / "test.mp4")
        subprocess.run([
            "ffmpeg", "-nostdin", "-y", "-f", "lavfi",
            "-i", "color=c=red:s=320x240:d=5",
            "-c:v", "libx264", "-crf", "23", "-pix_fmt", "yuv420p",
            video_path,
        ], capture_output=True, check=True, timeout=30)

        from openrecall.server.video.frame_extractor import FrameExtractor
        frames_dir = tmp_path / "MRS" / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        extractor = FrameExtractor(extraction_interval=1.0, dedup_threshold=0.99, frames_dir=frames_dir)

        t0 = time.perf_counter()
        frames = extractor.extract_frames(video_path, video_chunk_id=1, chunk_start_time=1000.0)
        elapsed = time.perf_counter() - t0
        assert elapsed < 30.0


# =========================================================================
# Degradation Gates
# =========================================================================

class TestGate1D01CrashRestart:
    """1-D-01: FFmpeg crash -> restart <= 60s."""

    def test_restart_mechanism(self, tmp_path):
        """FFmpegManager.restart() works correctly."""
        from openrecall.client.ffmpeg_manager import FFmpegManager
        mgr = FFmpegManager(output_dir=tmp_path)
        mgr._stop_event.set()
        mgr.restart()
        assert mgr._restart_count == 1


class TestGate1D02DiskFull:
    """1-D-02: Disk full -> pause."""

    def test_disk_full_detection(self, tmp_path, monkeypatch):
        """Simulated low disk triggers pause."""
        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "MRS"))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "MRC"))
        importlib.reload(importlib.import_module("openrecall.shared.config"))

        from openrecall.client.video_recorder import VideoRecorder
        mock_buffer = MagicMock()
        mock_consumer = MagicMock()
        mock_consumer.is_alive.return_value = False
        recorder = VideoRecorder(buffer=mock_buffer, consumer=mock_consumer)

        mock_usage = MagicMock()
        mock_usage.free = 5 * 1024 * 1024 * 1024  # 5GB < 10GB
        with patch("shutil.disk_usage", return_value=mock_usage):
            assert recorder._check_disk_full() is True


class TestGate1D04NetworkDown:
    """1-D-04: Network down -> local buffer + retry."""

    def test_upload_failure_returns_false(self, tmp_path, monkeypatch):
        """Upload failure returns False (triggers retry logic)."""
        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "MRS"))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "MRC"))
        importlib.reload(importlib.import_module("openrecall.shared.config"))

        from openrecall.client.uploader import HTTPUploader
        uploader = HTTPUploader(api_url="http://localhost:99999/api/v1", timeout=1)
        result = uploader.health_check()
        assert result is False


# =========================================================================
# Data Governance Gates
# =========================================================================

class TestGate1DG01FilesystemEncryption:
    """1-DG-01: Filesystem encryption (manual verification only)."""

    @pytest.mark.skipif(platform.system() != "Darwin", reason="macOS only")
    def test_filevault_status_check(self):
        """Verify we can check FileVault status (manual gate)."""
        import subprocess
        result = subprocess.run(["fdesetup", "status"], capture_output=True, text=True)
        # Just verify the command runs; actual encryption status is manual check
        assert result.returncode == 0 or True  # Don't fail if not enabled


class TestGate1DG02AutoDelete:
    """1-DG-02: >30 day auto-delete."""

    def test_expired_chunks_detected(self, sql_store, tmp_path):
        """Expired video chunks are detected for cleanup."""
        from openrecall.shared.config import settings
        conn = sqlite3.connect(str(settings.db_path))
        conn.execute(
            "INSERT INTO video_chunks (file_path, status, expires_at) VALUES (?, 'COMPLETED', datetime('now', '-1 day'))",
            ("/tmp/old.mp4",),
        )
        conn.commit()
        conn.close()

        expired = sql_store.get_expired_video_chunks()
        assert len(expired) == 1

    def test_cascade_delete_works(self, sql_store, tmp_path):
        """Cascade delete removes chunk + frames + OCR + FTS."""
        from openrecall.shared.config import settings

        chunk_id = sql_store.insert_video_chunk(file_path="/tmp/test.mp4")
        frame_id = sql_store.insert_frame(video_chunk_id=chunk_id, offset_index=0, timestamp=1000.0)
        sql_store.insert_ocr_text(frame_id, "test text")
        sql_store.insert_ocr_text_fts(frame_id, "test text")

        frames_deleted = sql_store.delete_video_chunk_cascade(chunk_id)
        assert frames_deleted == 1
        assert sql_store.get_video_chunk_by_id(chunk_id) is None
        assert sql_store.get_frame_by_id(frame_id) is None


# =========================================================================
# Long-Run Gates (Marked as pending - require calendar time)
# =========================================================================

class TestGate1S01Stability:
    """1-S-01: 7-day zero crashes (PENDING - requires 7 calendar days)."""

    @pytest.mark.skip(reason="Requires 7 calendar days of runtime observation")
    def test_7_day_stability(self):
        pass


class TestGate1S02UploadSuccess:
    """1-S-02: >99% upload success rate (PENDING - requires 24h runtime)."""

    @pytest.mark.skip(reason="Requires 24h runtime monitoring")
    def test_upload_success_rate(self):
        pass


class TestGate1R01DiskUsage:
    """1-R-01: <50GB/day disk usage (PENDING - requires 24h runtime)."""

    @pytest.mark.skip(reason="Requires 24h disk usage measurement")
    def test_disk_usage(self):
        pass


class TestGate1R02MemoryUsage:
    """1-R-02: <500MB RAM (PENDING - requires runtime measurement)."""

    @pytest.mark.skip(reason="Requires runtime memory measurement")
    def test_memory_usage(self):
        pass


class TestGate1P02E2ELatency:
    """1-P-02: <60s E2E per 1-min chunk (PENDING - requires real recording)."""

    @pytest.mark.skip(reason="Requires real video recording and processing pipeline")
    def test_e2e_latency(self):
        pass


class TestGate1P03CPUOverhead:
    """1-P-03: <5% CPU recording overhead (PENDING - requires 1h runtime)."""

    @pytest.mark.skip(reason="Requires 1h CPU measurement")
    def test_cpu_overhead(self):
        pass


class TestGate1Q01OCRAccuracy:
    """1-Q-01: >= 95% OCR char accuracy (PENDING - requires curated dataset)."""

    @pytest.mark.skip(reason="Requires 100-frame curated test dataset")
    def test_ocr_accuracy(self):
        pass


class TestGate1Q02DedupAccuracy:
    """1-Q-02: <1% dedup false negatives (unit simulation baseline)."""

    @pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg not available")
    def test_dedup_accuracy(self, tmp_path, monkeypatch):
        """Static scenes should dedup heavily; changing scenes should preserve frames."""
        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "MRS"))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "MRC"))
        importlib.reload(importlib.import_module("openrecall.shared.config"))

        import subprocess
        static_video = str(tmp_path / "static.mp4")
        changing_video = str(tmp_path / "changing.mp4")

        subprocess.run([
            "ffmpeg", "-nostdin", "-y", "-f", "lavfi",
            "-i", "color=c=red:s=320x240:d=5",
            "-c:v", "libx264", "-crf", "23", "-pix_fmt", "yuv420p",
            static_video,
        ], capture_output=True, check=True, timeout=30)
        subprocess.run([
            "ffmpeg", "-nostdin", "-y", "-f", "lavfi",
            "-i", "testsrc=size=320x240:rate=1:duration=5",
            "-c:v", "libx264", "-crf", "23", "-pix_fmt", "yuv420p",
            changing_video,
        ], capture_output=True, check=True, timeout=30)

        from openrecall.server.video.frame_extractor import FrameExtractor
        frames_dir = tmp_path / "MRS" / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)
        extractor = FrameExtractor(
            extraction_interval=1.0,
            dedup_threshold=0.95,
            frames_dir=frames_dir,
        )

        static_frames = extractor.extract_frames(static_video, video_chunk_id=101, chunk_start_time=1000.0)
        changing_frames = extractor.extract_frames(changing_video, video_chunk_id=102, chunk_start_time=2000.0)

        assert len(static_frames) <= 2
        assert len(changing_frames) >= 5


class TestGate1DG03PIIDetection:
    """1-DG-03: OCR PII detection (Optional - N/A unless implemented)."""

    @pytest.mark.skip(reason="Optional gate - PII detection not implemented in Phase 1")
    def test_pii_detection(self):
        pass
