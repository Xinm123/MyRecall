"""Phase 1 tests: FFmpegManager and VideoRecorder."""
import hashlib
import importlib
import platform
import time
import unittest.mock as mock
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestFFmpegManagerCommand:
    """Test FFmpeg command construction."""

    def test_build_command_has_required_flags(self, tmp_path):
        """FFmpeg command includes segment muxer, codec, CRF."""
        from openrecall.client.ffmpeg_manager import FFmpegManager

        mgr = FFmpegManager(output_dir=tmp_path, chunk_duration=300, fps=30, crf=23)
        cmd = mgr._build_ffmpeg_command()
        assert "ffmpeg" in cmd[0]
        assert "-nostdin" in cmd
        assert "segment" in cmd
        assert "-segment_time" in cmd
        assert "300" in cmd
        assert "-c:v" in cmd
        assert "libx264" in cmd
        assert "-crf" in cmd
        assert "23" in cmd
        assert "-strftime" in cmd
        strftime_idx = cmd.index("-strftime")
        assert cmd[strftime_idx + 1] == "1"
        assert cmd[-1].endswith("monitor_default_%Y-%m-%d_%H-%M-%S.mp4")

    def test_build_command_platform_specific(self, tmp_path):
        """Command uses correct input format for the platform."""
        from openrecall.client.ffmpeg_manager import FFmpegManager

        mgr = FFmpegManager(output_dir=tmp_path)
        cmd = mgr._build_ffmpeg_command()
        system = platform.system()
        if system == "Darwin":
            assert "avfoundation" in cmd
        elif system == "Linux":
            assert "x11grab" in cmd

    def test_build_command_darwin_detects_screen_index(self, tmp_path):
        """On macOS, auto-detect screen device index instead of hardcoded camera index."""
        from openrecall.client.ffmpeg_manager import FFmpegManager

        mgr = FFmpegManager(output_dir=tmp_path)
        listing = (
            "[AVFoundation indev @ 0x1] [0] MacBook Pro Camera\n"
            "[AVFoundation indev @ 0x1] [4] Capture screen 0\n"
        )
        mock_result = MagicMock(stdout="", stderr=listing)

        with patch("openrecall.client.ffmpeg_manager.platform.system", return_value="Darwin"):
            with patch("openrecall.client.ffmpeg_manager.subprocess.run", return_value=mock_result):
                cmd = mgr._build_ffmpeg_command()

        input_idx = cmd.index("-i") + 1
        assert cmd[input_idx] == "4:none"

    def test_build_command_darwin_honors_device_override(self, tmp_path, monkeypatch):
        """OPENRECALL_AVFOUNDATION_VIDEO_DEVICE overrides auto-detection."""
        from openrecall.client.ffmpeg_manager import FFmpegManager

        monkeypatch.setenv("OPENRECALL_AVFOUNDATION_VIDEO_DEVICE", "7")
        mgr = FFmpegManager(output_dir=tmp_path)

        with patch("openrecall.client.ffmpeg_manager.platform.system", return_value="Darwin"):
            with patch("openrecall.client.ffmpeg_manager.subprocess.run") as mock_run:
                cmd = mgr._build_ffmpeg_command()

        input_idx = cmd.index("-i") + 1
        assert cmd[input_idx] == "7:none"
        mock_run.assert_not_called()

    def test_build_command_darwin_fallbacks_to_screen_name(self, tmp_path):
        """If device listing has no screen entry, fallback to named screen input."""
        from openrecall.client.ffmpeg_manager import FFmpegManager

        mgr = FFmpegManager(output_dir=tmp_path)
        mock_result = MagicMock(stdout="", stderr="[AVFoundation indev @ 0x1] [0] Camera\n")

        with patch("openrecall.client.ffmpeg_manager.platform.system", return_value="Darwin"):
            with patch("openrecall.client.ffmpeg_manager.subprocess.run", return_value=mock_result):
                cmd = mgr._build_ffmpeg_command()

        input_idx = cmd.index("-i") + 1
        assert cmd[input_idx] == "Capture screen 0:none"

    def test_build_command_includes_segment_list(self, tmp_path):
        """Segment list CSV path is included for chunk detection."""
        from openrecall.client.ffmpeg_manager import FFmpegManager

        mgr = FFmpegManager(output_dir=tmp_path)
        cmd = mgr._build_ffmpeg_command()
        assert "-segment_list" in cmd
        csv_idx = cmd.index("-segment_list") + 1
        assert cmd[csv_idx].endswith("segments.csv")

    def test_build_command_uses_monitor_timestamp_pattern(self, tmp_path):
        """Output filename pattern includes monitor id and UTC strftime placeholders."""
        from openrecall.client.ffmpeg_manager import FFmpegManager

        mgr = FFmpegManager(output_dir=tmp_path, monitor_id="1")
        cmd = mgr._build_ffmpeg_command()
        assert cmd[-1].endswith("monitor_1_%Y-%m-%d_%H-%M-%S.mp4")

    def test_custom_resolution_adds_scale_filter(self, tmp_path):
        """Custom resolution parameter inserts a -vf scale filter."""
        from openrecall.client.ffmpeg_manager import FFmpegManager

        mgr = FFmpegManager(output_dir=tmp_path, resolution="1920:1080")
        cmd = mgr._build_ffmpeg_command()
        assert "-vf" in cmd
        assert "scale=1920:1080" in cmd


class TestFFmpegManagerLifecycle:
    """Test start/stop/restart lifecycle."""

    def test_check_ffmpeg_available(self, tmp_path):
        """check_ffmpeg_available returns bool."""
        from openrecall.client.ffmpeg_manager import FFmpegManager

        mgr = FFmpegManager(output_dir=tmp_path)
        result = mgr.check_ffmpeg_available()
        assert isinstance(result, bool)

    @patch("subprocess.Popen")
    def test_start_creates_process(self, mock_popen, tmp_path):
        """start() launches subprocess."""
        from openrecall.client.ffmpeg_manager import FFmpegManager

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 12345
        mock_popen.return_value = mock_proc

        mgr = FFmpegManager(output_dir=tmp_path)
        with patch.object(mgr, "check_ffmpeg_available", return_value=True):
            mgr.start()
            assert mgr._process is not None
            assert mgr.is_alive()
            mgr._stop_event.set()  # cleanup watchdog

    @patch("subprocess.Popen")
    def test_stop_terminates_process(self, mock_popen, tmp_path):
        """stop() terminates the process."""
        from openrecall.client.ffmpeg_manager import FFmpegManager

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.pid = 12345
        mock_proc.stderr = MagicMock()
        mock_proc.stderr.read.return_value = b""
        mock_popen.return_value = mock_proc

        mgr = FFmpegManager(output_dir=tmp_path)
        with patch.object(mgr, "check_ffmpeg_available", return_value=True):
            mgr.start()
            time.sleep(0.1)
            mgr.stop()
            mock_proc.terminate.assert_called()

    def test_stop_skips_stdin_close_when_write_lock_held(self, tmp_path):
        """stop() must not block on stdin.close when writer thread is in-flight."""
        from openrecall.client.ffmpeg_manager import FFmpegManager

        mgr = FFmpegManager(output_dir=tmp_path)

        mock_proc = MagicMock()
        mock_proc.poll.return_value = None
        mock_proc.stdin = MagicMock()
        mock_proc.stderr = MagicMock()
        mock_proc.stderr.read.return_value = b""
        mgr._process = mock_proc

        # Simulate writer thread holding the stdin write lock during shutdown.
        mgr._stdin_lock.acquire()
        try:
            mgr.stop()
        finally:
            mgr._stdin_lock.release()

        mock_proc.terminate.assert_called_once()
        mock_proc.wait.assert_called_once_with(timeout=10)
        mock_proc.stdin.close.assert_not_called()

    def test_restart_increments_counter(self, tmp_path):
        """restart() increments the restart counter."""
        from openrecall.client.ffmpeg_manager import FFmpegManager

        mgr = FFmpegManager(output_dir=tmp_path)
        mgr._stop_event.set()  # Prevent actual restart
        mgr.restart()
        assert mgr._restart_count == 1
        mgr.restart()
        assert mgr._restart_count == 2

    def test_restart_count_resets_after_hour(self, tmp_path):
        """Restart counter resets after 1-hour window."""
        from openrecall.client.ffmpeg_manager import FFmpegManager

        mgr = FFmpegManager(output_dir=tmp_path)
        mgr._stop_event.set()
        mgr._restart_count_window_start = time.time() - 3700  # >1 hour ago
        mgr._restart_count = 5
        mgr.restart()
        assert mgr._restart_count == 1  # Reset then incremented

    def test_restart_count_last_hour_property(self, tmp_path):
        """restart_count_last_hour returns 0 when window expired."""
        from openrecall.client.ffmpeg_manager import FFmpegManager

        mgr = FFmpegManager(output_dir=tmp_path)
        mgr._restart_count = 5
        mgr._restart_count_window_start = time.time() - 3700
        assert mgr.restart_count_last_hour == 0

    def test_restart_count_last_hour_current(self, tmp_path):
        """restart_count_last_hour returns count within current window."""
        from openrecall.client.ffmpeg_manager import FFmpegManager

        mgr = FFmpegManager(output_dir=tmp_path)
        mgr._restart_count = 3
        mgr._restart_count_window_start = time.time() - 100
        assert mgr.restart_count_last_hour == 3

    def test_start_raises_without_ffmpeg(self, tmp_path):
        """start() raises RuntimeError if ffmpeg not in PATH."""
        from openrecall.client.ffmpeg_manager import FFmpegManager

        mgr = FFmpegManager(output_dir=tmp_path)
        with patch.object(mgr, "check_ffmpeg_available", return_value=False):
            with pytest.raises(RuntimeError, match="ffmpeg not found"):
                mgr.start()


class TestFFmpegRawVideoProfile:
    """Test rawvideo stdin profile-driven FFmpeg command behavior."""

    def test_start_with_profile_builds_rawvideo_input(self, tmp_path):
        from openrecall.client.ffmpeg_manager import FFmpegManager
        from openrecall.client.sck_stream import PixelFormatProfile

        profile = PixelFormatProfile(
            pix_fmt="nv12",
            width=1920,
            height=1080,
            fps=30,
            color_range="tv",
        )

        mgr = FFmpegManager(output_dir=tmp_path)
        cmd = mgr._build_rawvideo_command(profile)

        assert "-f" in cmd
        assert "rawvideo" in cmd
        assert "-pixel_format" in cmd
        assert "nv12" in cmd
        assert "-video_size" in cmd
        assert "1920x1080" in cmd
        assert "-framerate" in cmd
        assert "30" in cmd
        assert "-i" in cmd
        assert "-" in cmd
        assert "-strftime" in cmd
        assert cmd[-1].endswith("monitor_default_%Y-%m-%d_%H-%M-%S.mp4")

    def test_reconfigure_restarts_on_profile_change(self, tmp_path):
        from openrecall.client.ffmpeg_manager import FFmpegManager
        from openrecall.client.sck_stream import PixelFormatProfile

        mgr = FFmpegManager(output_dir=tmp_path)
        mgr._input_profile = PixelFormatProfile("nv12", 1920, 1080, 30, "tv")

        with patch.object(mgr, "restart") as mock_restart:
            changed = mgr.reconfigure(PixelFormatProfile("bgra", 1920, 1080, 30, "tv"))

        assert changed is True
        mock_restart.assert_called_once()


class TestFFmpegSegmentPolling:
    """Test segment list polling."""

    def test_read_segment_list_empty(self, tmp_path):
        """Empty/missing segment list returns empty list."""
        from openrecall.client.ffmpeg_manager import FFmpegManager

        mgr = FFmpegManager(output_dir=tmp_path)
        assert mgr._read_segment_list() == []

    def test_read_segment_list_csv(self, tmp_path):
        """Parses CSV segment list correctly."""
        from openrecall.client.ffmpeg_manager import FFmpegManager

        mgr = FFmpegManager(output_dir=tmp_path)
        csv_path = tmp_path / "segments.csv"
        csv_path.write_text(
            "monitor_1_2026-02-08_21-45-30.mp4,0.000,300.000\n"
            "monitor_1_2026-02-08_21-46-30.mp4,300.000,600.000\n"
        )
        segments = mgr._read_segment_list()
        assert len(segments) == 2
        assert segments[0] == "monitor_1_2026-02-08_21-45-30.mp4"
        assert segments[1] == "monitor_1_2026-02-08_21-46-30.mp4"

    def test_poll_segments_detects_new(self, tmp_path):
        """_poll_segments detects newly added segments."""
        from openrecall.client.ffmpeg_manager import FFmpegManager

        mgr = FFmpegManager(output_dir=tmp_path)
        # Create segment file and CSV
        segment_name = "monitor_1_2026-02-08_21-45-30.mp4"
        (tmp_path / segment_name).write_bytes(b"fake video")
        csv_path = tmp_path / "segments.csv"
        csv_path.write_text(f"{segment_name},0.000,300.000\n")
        new = mgr._poll_segments()
        assert len(new) == 1
        assert new[0].endswith(".mp4")
        assert "monitor_1_" in new[0]

    def test_poll_segments_no_duplicate(self, tmp_path):
        """_poll_segments does not re-report known segments."""
        from openrecall.client.ffmpeg_manager import FFmpegManager

        mgr = FFmpegManager(output_dir=tmp_path)
        segment_name = "monitor_1_2026-02-08_21-45-30.mp4"
        (tmp_path / segment_name).write_bytes(b"fake video")
        csv_path = tmp_path / "segments.csv"
        csv_path.write_text(f"{segment_name},0.000,300.000\n")
        first = mgr._poll_segments()
        assert len(first) == 1
        second = mgr._poll_segments()
        assert len(second) == 0  # Already known

    def test_current_chunk_path_uses_last_detected_segment(self, tmp_path):
        """current_chunk_path returns latest discovered segment path."""
        from openrecall.client.ffmpeg_manager import FFmpegManager

        mgr = FFmpegManager(output_dir=tmp_path)
        segment_name = "monitor_1_2026-02-08_21-45-30.mp4"
        segment_path = tmp_path / segment_name
        segment_path.write_bytes(b"fake video")
        (tmp_path / "segments.csv").write_text(f"{segment_name},0.000,300.000\n")

        mgr._poll_segments()
        assert mgr.current_chunk_path == str(segment_path)

    def test_current_chunk_path_falls_back_to_csv_last_existing(self, tmp_path):
        """current_chunk_path falls back to last existing CSV segment when cache is empty."""
        from openrecall.client.ffmpeg_manager import FFmpegManager

        mgr = FFmpegManager(output_dir=tmp_path)
        first = "monitor_1_2026-02-08_21-45-30.mp4"
        second = "monitor_1_2026-02-08_21-46-30.mp4"
        first_path = tmp_path / first
        second_path = tmp_path / second
        first_path.write_bytes(b"fake video")
        second_path.write_bytes(b"fake video")
        (tmp_path / "segments.csv").write_text(f"{first},0.000,300.000\n{second},300.000,600.000\n")

        assert mgr.current_chunk_path == str(second_path)

    def test_on_chunk_complete_callback(self, tmp_path):
        """Callback fires for each new segment."""
        from openrecall.client.ffmpeg_manager import FFmpegManager

        received = []
        mgr = FFmpegManager(
            output_dir=tmp_path, on_chunk_complete=lambda p: received.append(p)
        )
        segment_name = "monitor_1_2026-02-08_21-45-30.mp4"
        (tmp_path / segment_name).write_bytes(b"fake")
        csv_path = tmp_path / "segments.csv"
        csv_path.write_text(f"{segment_name},0.000,300.000\n")

        # Simulate watchdog iteration
        new_segments = mgr._poll_segments()
        for seg in new_segments:
            if mgr.on_chunk_complete:
                mgr.on_chunk_complete(seg)

        assert len(received) == 1


class TestVideoRecorder:
    """Test VideoRecorder integration."""

    def _reload_modules(self):
        """Reload modules after env changes."""
        importlib.reload(importlib.import_module("openrecall.shared.config"))
        importlib.reload(importlib.import_module("openrecall.client.ffmpeg_manager"))
        importlib.reload(importlib.import_module("openrecall.client.video_recorder"))

    def test_on_chunk_complete_builds_metadata(self, tmp_path, monkeypatch):
        """_on_chunk_complete builds correct metadata dict."""
        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "MRS"))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "MRC"))
        self._reload_modules()

        from openrecall.client.video_recorder import VideoRecorder

        mock_buffer = MagicMock()
        mock_consumer = MagicMock()
        mock_consumer.is_alive.return_value = False

        recorder = VideoRecorder(buffer=mock_buffer, consumer=mock_consumer)

        # Create a fake chunk file
        chunk_path = tmp_path / "test_chunk.mp4"
        chunk_path.write_bytes(b"x" * 1024)

        recorder._on_chunk_complete(str(chunk_path))

        assert mock_buffer.enqueue_file.called
        call_args = mock_buffer.enqueue_file.call_args
        assert call_args[0][0] == str(chunk_path)
        meta = call_args[0][1]
        assert meta["type"] == "video_chunk"
        assert meta["codec"] == "h264"
        assert meta["file_size_bytes"] == 1024
        assert meta["checksum"].startswith("sha256:")

    def test_on_chunk_complete_skips_empty(self, tmp_path, monkeypatch):
        """_on_chunk_complete skips empty chunk files."""
        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "MRS"))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "MRC"))
        self._reload_modules()

        from openrecall.client.video_recorder import VideoRecorder

        mock_buffer = MagicMock()
        mock_consumer = MagicMock()
        mock_consumer.is_alive.return_value = False

        recorder = VideoRecorder(buffer=mock_buffer, consumer=mock_consumer)

        chunk_path = tmp_path / "empty.mp4"
        chunk_path.write_bytes(b"")

        recorder._on_chunk_complete(str(chunk_path))
        assert not mock_buffer.enqueue_file.called

    def test_on_chunk_complete_skips_missing(self, tmp_path, monkeypatch):
        """_on_chunk_complete skips missing chunk files."""
        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "MRS"))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "MRC"))
        self._reload_modules()

        from openrecall.client.video_recorder import VideoRecorder

        mock_buffer = MagicMock()
        mock_consumer = MagicMock()
        mock_consumer.is_alive.return_value = False

        recorder = VideoRecorder(buffer=mock_buffer, consumer=mock_consumer)
        recorder._on_chunk_complete("/nonexistent/path.mp4")
        assert not mock_buffer.enqueue_file.called

    def test_check_disk_full(self, tmp_path, monkeypatch):
        """_check_disk_full returns False when space is available."""
        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "MRS"))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "MRC"))
        self._reload_modules()

        from openrecall.client.video_recorder import VideoRecorder

        mock_buffer = MagicMock()
        mock_consumer = MagicMock()
        mock_consumer.is_alive.return_value = False

        recorder = VideoRecorder(buffer=mock_buffer, consumer=mock_consumer)
        assert recorder._check_disk_full() is False

    def test_compute_checksum(self, tmp_path, monkeypatch):
        """_compute_checksum returns SHA256 hex digest."""
        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "MRS"))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "MRC"))
        self._reload_modules()

        from openrecall.client.video_recorder import VideoRecorder

        mock_buffer = MagicMock()
        mock_consumer = MagicMock()
        mock_consumer.is_alive.return_value = False

        recorder = VideoRecorder(buffer=mock_buffer, consumer=mock_consumer)
        f = tmp_path / "test.bin"
        f.write_bytes(b"hello world")

        checksum = recorder._compute_checksum(str(f))
        assert len(checksum) == 64  # SHA256 hex
        expected = hashlib.sha256(b"hello world").hexdigest()
        assert checksum == expected

    def test_stop_sets_flag(self, tmp_path, monkeypatch):
        """stop() sets _stop_requested flag."""
        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "MRS"))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "MRC"))
        self._reload_modules()

        from openrecall.client.video_recorder import VideoRecorder

        mock_buffer = MagicMock()
        mock_consumer = MagicMock()
        mock_consumer.is_alive.return_value = False

        recorder = VideoRecorder(buffer=mock_buffer, consumer=mock_consumer)
        assert recorder._stop_requested is False
        recorder.stop()
        assert recorder._stop_requested is True

    def test_runtime_pause_stops_sources_not_pipelines(self, tmp_path, monkeypatch):
        """Runtime recording pause should stop monitor sources only."""
        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "MRS"))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "MRC"))
        self._reload_modules()

        from openrecall.client.video_recorder import VideoRecorder

        mock_buffer = MagicMock()
        mock_consumer = MagicMock()
        mock_consumer.is_alive.return_value = False

        recorder = VideoRecorder(buffer=mock_buffer, consumer=mock_consumer)
        recorder._use_legacy_mode = False

        source = MagicMock()
        controller = MagicMock()
        recorder._sources = {"1": source}
        recorder._pipelines = {"1": controller}

        recorder._pause_recording_backend_for_runtime_toggle()

        source.stop.assert_called_once()
        controller.stop.assert_not_called()
        assert recorder._sources == {}
        assert "1" in recorder._pipelines

    def test_runtime_resume_restarts_sources_from_existing_pipelines(self, tmp_path, monkeypatch):
        """Runtime recording resume should restart monitor sources without rebuilding pipelines."""
        monkeypatch.setenv("OPENRECALL_DATA_DIR", str(tmp_path))
        monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "MRS"))
        monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "MRC"))
        self._reload_modules()

        from openrecall.client.sck_stream import MonitorInfo
        from openrecall.client.video_recorder import VideoRecorder

        mock_buffer = MagicMock()
        mock_consumer = MagicMock()
        mock_consumer.is_alive.return_value = False

        recorder = VideoRecorder(buffer=mock_buffer, consumer=mock_consumer)
        recorder._use_legacy_mode = False
        recorder._sources = {}
        recorder._pipelines = {"1": MagicMock()}
        recorder._monitor_by_id = {
            "1": MonitorInfo(
                monitor_id="1",
                name="display-1",
                width=1512,
                height=982,
                is_primary=True,
                backend="sck",
                fingerprint="1512x982:1",
                source_index=1,
            )
        }

        source = MagicMock()
        with patch("openrecall.client.video_recorder.create_monitor_source", return_value=source):
            started = recorder._resume_recording_backend_for_runtime_toggle()

        assert started is True
        source.start.assert_called_once()
        assert recorder._sources["1"] is source
