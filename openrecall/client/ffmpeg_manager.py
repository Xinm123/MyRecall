"""FFmpeg subprocess manager for continuous screen recording."""

from __future__ import annotations

import logging
import os
import platform
import re
import select
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
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
        on_chunk_started: Optional[Callable[[str], None]] = None,
        monitor_id: str = "",
        segment_list_filename: str = "segments.csv",
        pipeline_mode: str = "segment",
        pipe_write_timeout_ms: int = 1500,
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.chunk_duration = chunk_duration
        self.fps = fps
        self.crf = crf
        self.resolution = resolution
        self.on_chunk_complete = on_chunk_complete
        self.on_chunk_started = on_chunk_started
        self.monitor_id = monitor_id or "default"
        self.pipeline_mode = self._normalize_pipeline_mode(pipeline_mode)
        self.pipe_write_timeout_ms = max(0, int(pipe_write_timeout_ms))

        self._process: Optional[subprocess.Popen] = None
        self._stop_event = threading.Event()
        self._watchdog_thread: Optional[threading.Thread] = None
        self._segment_list_path = self.output_dir / segment_list_filename
        self._known_segments: set[str] = set()
        self._restart_count: int = 0
        self._restart_count_window_start: float = 0.0
        self._last_start_time: float = 0.0
        self._chunk_counter: int = 0
        self._last_detected_chunk_path: Optional[str] = None
        self._active_chunk_path: Optional[str] = None
        self._started_chunk_paths_logged: set[str] = set()
        self._darwin_input_spec: Optional[str] = None
        self._write_inflight_since_monotonic: float = 0.0
        self._last_write_completed_monotonic: float = 0.0
        self._write_timeout_supported = os.name != "nt"
        self._current_chunk_started_at: float = 0.0
        self._frames_written_in_chunk: int = 0
        self._frames_per_chunk: int = max(1, int(round(self.fps * self.chunk_duration)))

        self._stdin_lock = threading.Lock()
        self._input_profile: Optional[PixelFormatProfile] = None
        self._active_encoder: str = self._select_default_encoder()
        self._encoder_fallback_used = False

    @staticmethod
    def _normalize_pipeline_mode(mode: str) -> str:
        normalized = (mode or "").strip().lower()
        if normalized not in {"segment", "chunk_process"}:
            return "segment"
        return normalized

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
        if self.pipeline_mode == "chunk_process":
            active_path = self._active_chunk_path
            if active_path and Path(active_path).exists():
                return active_path

        if self._last_detected_chunk_path:
            last_path = Path(self._last_detected_chunk_path)
            if last_path.exists():
                return str(last_path)

        segments = self._read_segment_list()
        for segment in reversed(segments):
            segment_path = self.output_dir / segment
            if segment_path.exists():
                return str(segment_path)
        return None

    @property
    def active_chunk_path(self) -> Optional[str]:
        active_path = self._active_chunk_path
        if active_path:
            path_obj = Path(active_path)
            if path_obj.exists():
                return str(path_obj)
            if self.pipeline_mode == "chunk_process":
                return active_path
        return self.current_chunk_path

    @property
    def write_stuck_seconds(self) -> float:
        started_at = self._write_inflight_since_monotonic
        if started_at <= 0:
            return 0.0
        return max(0.0, time.monotonic() - started_at)

    @property
    def last_write_completed_monotonic(self) -> float:
        return self._last_write_completed_monotonic

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
        self._start_rawvideo_process(profile)

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

        self._write_inflight_since_monotonic = time.monotonic()
        try:
            with self._stdin_lock:
                start = time.perf_counter()
                self._write_with_timeout(process, frame_bytes)
                elapsed = time.perf_counter() - start
                self._frames_written_in_chunk += 1
            self._last_write_completed_monotonic = time.monotonic()
            if (
                self.pipeline_mode == "chunk_process"
                and self._input_profile is not None
                and self._frames_written_in_chunk >= self._frames_per_chunk
            ):
                self._rotate_chunk_process()
            return elapsed
        finally:
            self._write_inflight_since_monotonic = 0.0

    def stop(self) -> Optional[str]:
        self._stop_event.set()
        last_chunk = None

        process = self._process
        active_chunk_before_stop = self._active_chunk_path
        if process is not None and process.poll() is None:
            try:
                self._close_stdin_if_safe(process)
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

        if self.pipeline_mode == "segment":
            new_segments = self._poll_segments()
            if new_segments:
                last_chunk = new_segments[-1]
        else:
            if active_chunk_before_stop and Path(active_chunk_before_stop).exists():
                last_chunk = active_chunk_before_stop
                self._emit_chunk_completed(active_chunk_before_stop)

        self._process = None
        self._active_chunk_path = None
        self._write_inflight_since_monotonic = 0.0
        self._frames_written_in_chunk = 0
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
        active_chunk_before_restart = self._active_chunk_path
        if process is not None:
            try:
                self._close_stdin_if_safe(process)
                process.kill()
                process.wait(timeout=5)
            except Exception:
                pass
            self._process = None
            self._write_inflight_since_monotonic = 0.0
            self._frames_written_in_chunk = 0

        if (
            self.pipeline_mode == "chunk_process"
            and active_chunk_before_restart
            and Path(active_chunk_before_restart).exists()
        ):
            self._emit_chunk_completed(active_chunk_before_restart)

        if self._stop_event.is_set():
            return

        if self._input_profile is None:
            self._start_process(self._build_platform_capture_command(), use_pipe_input=False)
        else:
            self._start_rawvideo_process(self._input_profile)

    def _start_process(
        self,
        cmd: list[str],
        use_pipe_input: bool,
        active_chunk_path: Optional[str] = None,
    ) -> None:
        if self.is_alive():
            logger.warning("FFmpeg already running, ignoring start")
            return
        if not self.check_ffmpeg_available():
            raise RuntimeError("ffmpeg not found in PATH")

        if self.pipeline_mode == "segment" and self._segment_list_path.exists():
            self._known_segments = set(self._read_segment_list())

        logger.info("Starting FFmpeg: %s", " ".join(cmd))
        stdin_target = subprocess.PIPE if use_pipe_input else subprocess.DEVNULL
        process_env = os.environ.copy()
        process_env["TZ"] = "UTC"
        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            stdin=stdin_target,
            env=process_env,
        )
        self._last_start_time = time.time()
        self._active_chunk_path = active_chunk_path
        self._started_chunk_paths_logged.clear()
        self._write_inflight_since_monotonic = 0.0
        self._last_write_completed_monotonic = 0.0
        self._frames_written_in_chunk = 0
        self._current_chunk_started_at = time.time() if active_chunk_path else 0.0
        self._stop_event.clear()

        if use_pipe_input and self._write_timeout_supported:
            self._set_stdin_nonblocking(self._process)

        if self._watchdog_thread is None or not self._watchdog_thread.is_alive():
            self._watchdog_thread = threading.Thread(
                target=self._watchdog_loop,
                daemon=True,
                name=f"FFmpegWatchdog-{self.monitor_id}",
            )
            self._watchdog_thread.start()

        logger.info("FFmpeg started (PID=%s)", self._process.pid)
        if active_chunk_path:
            self._emit_chunk_started(active_chunk_path)

    def _build_ffmpeg_command(self) -> list[str]:
        """Backward-compatible command builder used by tests."""
        if self._input_profile is not None:
            return self._build_rawvideo_command(self._input_profile)
        return self._build_platform_capture_command()

    def _start_rawvideo_process(self, profile: PixelFormatProfile) -> None:
        self._frames_per_chunk = max(1, int(round(profile.fps * self.chunk_duration)))
        if self.pipeline_mode == "chunk_process":
            output_file = self._next_chunk_file_path()
            cmd = self._build_rawvideo_command(profile, output_file=output_file)
            self._start_process(cmd, use_pipe_input=True, active_chunk_path=output_file)
            return

        self._start_process(self._build_rawvideo_command(profile), use_pipe_input=True)

    def _sanitize_monitor_id(self) -> str:
        monitor_id = (self.monitor_id or "").strip()
        sanitized = re.sub(r"[^A-Za-z0-9_-]+", "_", monitor_id).strip("_-")
        return sanitized or "default"

    def _segment_output_pattern(self) -> str:
        monitor_id = self._sanitize_monitor_id()
        filename = f"monitor_{monitor_id}_%Y-%m-%d_%H-%M-%S.mp4"
        return str(self.output_dir / filename)

    def _next_chunk_file_path(self) -> str:
        monitor_id = self._sanitize_monitor_id()
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H-%M-%S")
        candidate = self.output_dir / f"monitor_{monitor_id}_{timestamp}.mp4"
        suffix = 1
        while candidate.exists():
            candidate = self.output_dir / f"monitor_{monitor_id}_{timestamp}_{suffix:02d}.mp4"
            suffix += 1
        return str(candidate)

    def _build_platform_capture_command(self) -> list[str]:
        output_pattern = self._segment_output_pattern()
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
            "-strftime",
            "1",
            "-y",
            output_pattern,
        ]

        if self.resolution:
            scale_idx = cmd.index("-c:v")
            cmd.insert(scale_idx, f"scale={self.resolution}")
            cmd.insert(scale_idx, "-vf")

        return cmd

    def _build_rawvideo_command(
        self,
        profile: PixelFormatProfile,
        output_file: Optional[str] = None,
    ) -> list[str]:
        output_target = output_file or self._segment_output_pattern()

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
            "-use_wallclock_as_timestamps",
            "1",
        ]

        if profile.color_range in {"tv", "pc"}:
            cmd.extend(["-color_range", profile.color_range])

        cmd.extend(["-i", "-"])

        cmd.extend(self._encoder_args())

        if self.pipeline_mode == "chunk_process":
            cmd.extend(["-y", output_target])
            return cmd

        cmd.extend(
            [
                "-force_key_frames",
                f"expr:gte(t,n_forced*{self.chunk_duration})",
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
                "-strftime",
                "1",
                "-y",
                output_target,
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
            if self.pipeline_mode == "segment":
                self._poll_active_chunk_start()
                new_segments = self._poll_segments()
                for segment_path in new_segments:
                    self._emit_chunk_completed(segment_path)

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

    def _poll_active_chunk_start(self) -> Optional[str]:
        """Detect and log a newly started active chunk file."""
        active_chunk_path = self._detect_active_chunk_path()
        if active_chunk_path is None:
            return None
        if active_chunk_path == self._active_chunk_path:
            return None
        if active_chunk_path in self._started_chunk_paths_logged:
            self._active_chunk_path = active_chunk_path
            return None

        self._emit_chunk_started(active_chunk_path)
        return active_chunk_path

    def _detect_active_chunk_path(self) -> Optional[str]:
        """Return latest chunk file that appears to belong to current ffmpeg run."""
        pattern = f"monitor_{self._sanitize_monitor_id()}_*.mp4"
        candidates = list(self.output_dir.glob(pattern))
        if not candidates:
            candidates = list(self.output_dir.glob("*.mp4"))

        latest_path: Optional[Path] = None
        latest_mtime = float("-inf")
        for candidate in candidates:
            try:
                mtime = candidate.stat().st_mtime
            except OSError:
                continue
            if mtime < (self._last_start_time - 1):
                continue
            if mtime > latest_mtime:
                latest_path = candidate
                latest_mtime = mtime

        return str(latest_path) if latest_path is not None else None

    def _close_stdin_if_safe(self, process: subprocess.Popen) -> None:
        stdin = process.stdin
        if stdin is None:
            return

        # Avoid deadlock during shutdown/restart when writer thread is flushing stdin.
        lock_acquired = self._stdin_lock.acquire(blocking=False)
        if not lock_acquired:
            logger.warning("Skipping FFmpeg stdin close because writer lock is busy")
            return
        try:
            stdin.close()
        except Exception:
            pass
        finally:
            self._stdin_lock.release()

    def _emit_chunk_started(self, chunk_path: str) -> None:
        self._started_chunk_paths_logged.add(chunk_path)
        self._active_chunk_path = chunk_path
        logger.info(
            "Video chunk recording started | file=%s | monitor_id=%s",
            Path(chunk_path).name,
            self.monitor_id,
        )
        if self.on_chunk_started:
            try:
                self.on_chunk_started(chunk_path)
            except Exception as exc:
                logger.error("Chunk start callback error: %s", exc)

    def _emit_chunk_completed(self, chunk_path: str) -> None:
        self._last_detected_chunk_path = chunk_path
        if self.on_chunk_complete:
            try:
                self.on_chunk_complete(chunk_path)
            except Exception as exc:
                logger.error("Chunk completion callback error: %s", exc)

    def _set_stdin_nonblocking(self, process: Optional[subprocess.Popen]) -> None:
        if not process or process.stdin is None:
            return
        try:
            os.set_blocking(process.stdin.fileno(), False)
        except Exception:
            self._write_timeout_supported = False

    def _write_with_timeout(self, process: subprocess.Popen, frame_bytes: bytes) -> None:
        stdin = process.stdin
        if stdin is None:
            raise BrokenPipeError("FFmpeg stdin unavailable")

        timeout_seconds = self.pipe_write_timeout_ms / 1000.0
        if timeout_seconds <= 0 or not self._write_timeout_supported:
            stdin.write(frame_bytes)
            stdin.flush()
            return

        fd = stdin.fileno()
        total = 0
        view = memoryview(frame_bytes)
        deadline = time.monotonic() + timeout_seconds
        while total < len(frame_bytes):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"FFmpeg stdin write timed out after {self.pipe_write_timeout_ms}ms"
                )

            _, writable, _ = select.select([], [fd], [], min(remaining, 0.05))
            if not writable:
                continue

            try:
                written = os.write(fd, view[total:])
            except BlockingIOError:
                continue
            except BrokenPipeError:
                raise
            except OSError as exc:
                raise OSError(f"FFmpeg stdin write failed: {exc}") from exc

            if written <= 0:
                raise BrokenPipeError("FFmpeg stdin closed during write")
            total += written

    def _rotate_chunk_process(self) -> None:
        process = self._process
        if process is None:
            return

        current_chunk = self._active_chunk_path
        try:
            if process.stdin:
                process.stdin.close()
        except Exception:
            pass

        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            logger.warning("FFmpeg did not close chunk in time, killing process")
            process.kill()
            process.wait(timeout=5)

        self._process = None
        self._frames_written_in_chunk = 0
        self._write_inflight_since_monotonic = 0.0

        if current_chunk and Path(current_chunk).exists():
            self._emit_chunk_completed(current_chunk)

        if self._stop_event.is_set():
            self._active_chunk_path = None
            return

        profile = self._input_profile
        if profile is None:
            self._start_process(self._build_platform_capture_command(), use_pipe_input=False)
            return
        self._start_rawvideo_process(profile)

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
                self._last_detected_chunk_path = segment_path

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
