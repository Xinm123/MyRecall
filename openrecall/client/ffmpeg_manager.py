"""FFmpeg subprocess manager for continuous screen recording."""

from __future__ import annotations

import logging
import os
import platform
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from openrecall.client.sck_stream import PixelFormatProfile

logger = logging.getLogger(__name__)


class FFmpegManager:
    """Manages FFmpeg lifecycle for both legacy and rawvideo monitor pipelines."""

    def __init__(
        self,
        output_dir: Path,
        chunk_duration: int = 60,
        fps: int = 30,
        crf: int = 23,
        resolution: str = "",
        on_chunk_complete: Optional[Callable[[str], None]] = None,
        monitor_id: str = "",
        segment_list_filename: str = "segments.csv",
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.chunk_duration = chunk_duration
        self.fps = fps
        self.crf = crf
        self.resolution = resolution
        self.on_chunk_complete = on_chunk_complete
        self.monitor_id = monitor_id or "default"

        self._process: Optional[subprocess.Popen] = None
        self._stop_event = threading.Event()
        self._watchdog_thread: Optional[threading.Thread] = None
        self._segment_list_path = self.output_dir / segment_list_filename
        self._known_segments: set[str] = set()
        self._restart_count: int = 0
        self._restart_count_window_start: float = 0.0
        self._last_start_time: float = 0.0
        self._chunk_counter: int = 0
        self._darwin_input_spec: Optional[str] = None

        self._stdin_lock = threading.Lock()
        self._input_profile: Optional[PixelFormatProfile] = None
        self._active_encoder: str = self._select_default_encoder()
        self._encoder_fallback_used = False

    @staticmethod
    def check_ffmpeg_available() -> bool:
        return shutil.which("ffmpeg") is not None

    @property
    def restart_count_last_hour(self) -> int:
        now = time.time()
        if now - self._restart_count_window_start > 3600:
            return 0
        return self._restart_count

    @property
    def current_chunk_path(self) -> Optional[str]:
        pattern = f"chunk_{self._chunk_counter:04d}.mp4"
        path = self.output_dir / pattern
        return str(path) if path.exists() else None

    def is_alive(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self) -> None:
        """Start legacy platform capture mode (backward compatible)."""
        self._input_profile = None
        self._active_encoder = self._select_default_encoder()
        self._encoder_fallback_used = False
        self._start_process(self._build_platform_capture_command(), use_pipe_input=False)

    def start_with_profile(self, profile: PixelFormatProfile) -> None:
        """Start stdin rawvideo mode with the given frame profile."""
        self._input_profile = profile
        self._active_encoder = self._select_default_encoder()
        self._encoder_fallback_used = False
        self._start_process(self._build_rawvideo_command(profile), use_pipe_input=True)

    def reconfigure(self, profile: PixelFormatProfile) -> bool:
        """Restart process if profile changed; returns True when restart happened."""
        if self._input_profile == profile and self.is_alive():
            return False
        self.restart(profile)
        return True

    def write_frame(self, frame_bytes: bytes) -> float:
        """Write one raw frame to FFmpeg stdin and return write latency seconds."""
        process = self._process
        if process is None or process.poll() is not None:
            raise BrokenPipeError("FFmpeg process not running")
        if process.stdin is None:
            raise BrokenPipeError("FFmpeg stdin unavailable")

        with self._stdin_lock:
            start = time.perf_counter()
            process.stdin.write(frame_bytes)
            process.stdin.flush()
            return time.perf_counter() - start

    def stop(self) -> Optional[str]:
        self._stop_event.set()
        last_chunk = None

        process = self._process
        if process is not None and process.poll() is None:
            try:
                if process.stdin:
                    try:
                        process.stdin.close()
                    except Exception:
                        pass
                process.terminate()
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                logger.warning("FFmpeg did not stop gracefully, killing")
                process.kill()
                process.wait(timeout=5)
            except Exception as e:
                logger.error("Error stopping FFmpeg: %s", e)

        if process is not None and process.stderr:
            try:
                stderr = process.stderr.read()
                if stderr:
                    stderr_text = stderr.decode("utf-8", errors="replace")
                    if "error" in stderr_text.lower():
                        logger.warning("FFmpeg stderr: %s", stderr_text[-500:])
            except Exception:
                pass

        new_segments = self._poll_segments()
        if new_segments:
            last_chunk = new_segments[-1]

        self._process = None
        if self._watchdog_thread is not None:
            self._watchdog_thread.join(timeout=5)
            self._watchdog_thread = None
        return last_chunk

    def restart(self, profile: Optional[PixelFormatProfile] = None) -> None:
        logger.warning("Restarting FFmpeg...")
        now = time.time()
        if now - self._restart_count_window_start > 3600:
            self._restart_count = 0
            self._restart_count_window_start = now
        self._restart_count += 1

        if profile is not None:
            self._input_profile = profile

        process = self._process
        if process is not None:
            try:
                if process.stdin:
                    try:
                        process.stdin.close()
                    except Exception:
                        pass
                process.kill()
                process.wait(timeout=5)
            except Exception:
                pass
            self._process = None

        if self._stop_event.is_set():
            return

        if self._input_profile is None:
            self._start_process(self._build_platform_capture_command(), use_pipe_input=False)
        else:
            self._start_process(self._build_rawvideo_command(self._input_profile), use_pipe_input=True)

    def _start_process(self, cmd: list[str], use_pipe_input: bool) -> None:
        if self.is_alive():
            logger.warning("FFmpeg already running, ignoring start")
            return
        if not self.check_ffmpeg_available():
            raise RuntimeError("ffmpeg not found in PATH")

        if self._segment_list_path.exists():
            self._known_segments = set(self._read_segment_list())

        logger.info("Starting FFmpeg: %s", " ".join(cmd))
        stdin_target = subprocess.PIPE if use_pipe_input else subprocess.DEVNULL
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            stdin=stdin_target,
        )
        self._last_start_time = time.time()
        self._stop_event.clear()

        if self._watchdog_thread is None or not self._watchdog_thread.is_alive():
            self._watchdog_thread = threading.Thread(
                target=self._watchdog_loop,
                daemon=True,
                name=f"FFmpegWatchdog-{self.monitor_id}",
            )
            self._watchdog_thread.start()

        logger.info("FFmpeg started (PID=%s)", self._process.pid)

    def _build_ffmpeg_command(self) -> list[str]:
        """Backward-compatible command builder used by tests."""
        if self._input_profile is not None:
            return self._build_rawvideo_command(self._input_profile)
        return self._build_platform_capture_command()

    def _build_platform_capture_command(self) -> list[str]:
        output_pattern = str(self.output_dir / "chunk_%04d.mp4")
        system = platform.system()

        if system == "Darwin":
            video_input = self._get_macos_video_input()
            input_args = [
                "-nostdin",
                "-f",
                "avfoundation",
                "-framerate",
                str(self.fps),
                "-capture_cursor",
                "1",
                "-i",
                video_input,
            ]
        elif system == "Linux":
            input_args = [
                "-nostdin",
                "-f",
                "x11grab",
                "-framerate",
                str(self.fps),
                "-i",
                ":0",
            ]
        else:
            input_args = [
                "-nostdin",
                "-f",
                "gdigrab",
                "-framerate",
                str(self.fps),
                "-i",
                "desktop",
            ]

        cmd = [
            "ffmpeg",
            *input_args,
            "-c:v",
            "libx264",
            "-crf",
            str(self.crf),
            "-preset",
            "fast",
            "-pix_fmt",
            "yuv420p",
            "-f",
            "segment",
            "-segment_time",
            str(self.chunk_duration),
            "-segment_format",
            "mp4",
            "-segment_list",
            str(self._segment_list_path),
            "-segment_list_type",
            "csv",
            "-reset_timestamps",
            "1",
            "-y",
            output_pattern,
        ]

        if self.resolution:
            scale_idx = cmd.index("-c:v")
            cmd.insert(scale_idx, f"scale={self.resolution}")
            cmd.insert(scale_idx, "-vf")

        return cmd

    def _build_rawvideo_command(self, profile: PixelFormatProfile) -> list[str]:
        output_pattern = str(self.output_dir / "chunk_%04d.mp4")

        cmd = [
            "ffmpeg",
            "-f",
            "rawvideo",
            "-pixel_format",
            profile.pix_fmt,
            "-video_size",
            f"{profile.width}x{profile.height}",
            "-framerate",
            str(profile.fps),
        ]

        if profile.color_range in {"tv", "pc"}:
            cmd.extend(["-color_range", profile.color_range])

        cmd.extend(["-i", "-"])

        cmd.extend(self._encoder_args())

        cmd.extend(
            [
                "-f",
                "segment",
                "-segment_time",
                str(self.chunk_duration),
                "-segment_format",
                "mp4",
                "-segment_list",
                str(self._segment_list_path),
                "-segment_list_type",
                "csv",
                "-reset_timestamps",
                "1",
                "-y",
                output_pattern,
            ]
        )
        return cmd

    def _encoder_args(self) -> list[str]:
        args = ["-c:v", self._active_encoder, "-pix_fmt", "yuv420p"]
        if self._active_encoder == "libx264":
            args.extend(["-crf", str(self.crf), "-preset", "fast"])
        elif self._active_encoder == "h264_videotoolbox":
            args.extend(["-allow_sw", "1"])
        return args

    def _select_default_encoder(self) -> str:
        if platform.system() == "Darwin":
            return "h264_videotoolbox"
        return "libx264"

    def _get_macos_video_input(self) -> str:
        if self._darwin_input_spec:
            return self._darwin_input_spec

        override = os.getenv("OPENRECALL_AVFOUNDATION_VIDEO_DEVICE", "").strip()
        if override:
            self._darwin_input_spec = override if ":" in override else f"{override}:none"
            logger.warning(
                "OPENRECALL_AVFOUNDATION_VIDEO_DEVICE is deprecated; "
                "monitor-id rawvideo pipeline is preferred. Using override=%s",
                self._darwin_input_spec,
            )
            return self._darwin_input_spec

        screen_index = self._detect_macos_screen_device_index()
        if screen_index is not None:
            self._darwin_input_spec = f"{screen_index}:none"
            logger.info("Detected avfoundation screen device index: %s", screen_index)
            return self._darwin_input_spec

        self._darwin_input_spec = "Capture screen 0:none"
        logger.warning(
            "Could not auto-detect avfoundation screen index; falling back to %s",
            self._darwin_input_spec,
        )
        return self._darwin_input_spec

    def _detect_macos_screen_device_index(self) -> Optional[str]:
        try:
            result = subprocess.run(
                ["ffmpeg", "-f", "avfoundation", "-list_devices", "true", "-i", ""],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            listing = f"{result.stdout}\n{result.stderr}"
            match = re.search(
                r"\[(\d+)\]\s+(?:Capture screen|screen capture)\b",
                listing,
                flags=re.IGNORECASE,
            )
            if match:
                return match.group(1)
        except Exception as exc:
            logger.debug("Failed to inspect avfoundation devices: %s", exc)
        return None

    def _watchdog_loop(self) -> None:
        logger.info("FFmpeg watchdog started")
        while not self._stop_event.is_set():
            new_segments = self._poll_segments()
            for segment_path in new_segments:
                if self.on_chunk_complete:
                    try:
                        self.on_chunk_complete(segment_path)
                    except Exception as exc:
                        logger.error("Chunk completion callback error: %s", exc)

            process = self._process
            if process is not None and process.poll() is not None and not self._stop_event.is_set():
                exit_code = process.returncode
                logger.error("FFmpeg exited unexpectedly (code=%s)", exit_code)

                if process.stderr:
                    try:
                        stderr = process.stderr.read()
                        if stderr:
                            logger.error("FFmpeg stderr: %s", stderr.decode("utf-8", errors="replace")[-500:])
                    except Exception:
                        pass

                if (
                    self._input_profile is not None
                    and self._active_encoder == "h264_videotoolbox"
                    and not self._encoder_fallback_used
                ):
                    logger.warning("h264_videotoolbox failed; falling back to libx264")
                    self._active_encoder = "libx264"
                    self._encoder_fallback_used = True

                self.restart(self._input_profile)

            self._stop_event.wait(timeout=1.0)

        logger.info("FFmpeg watchdog stopped")

    def _poll_segments(self) -> list[str]:
        new_segments: list[str] = []
        current_segments = self._read_segment_list()

        for segment in current_segments:
            if segment in self._known_segments:
                continue
            segment_path = str(self.output_dir / segment)
            if Path(segment_path).exists():
                new_segments.append(segment_path)
                self._known_segments.add(segment)
                self._chunk_counter += 1

        return new_segments

    def _read_segment_list(self) -> list[str]:
        segments: list[str] = []
        if not self._segment_list_path.exists():
            return segments

        try:
            with open(self._segment_list_path, "r", encoding="utf-8") as file:
                for line in file:
                    line = line.strip()
                    if not line:
                        continue
                    parts = line.split(",")
                    if parts:
                        segments.append(parts[0].strip())
        except Exception as exc:
            logger.error("Error reading segment list: %s", exc)

        return segments
