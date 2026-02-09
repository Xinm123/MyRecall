"""Video recorder (Producer) with monitor-id driven rawvideo pipelines."""

from __future__ import annotations

import hashlib
import logging
import os
import queue
import shutil
import threading
import time
import urllib.parse
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests

from openrecall.client.buffer import LocalBuffer, get_buffer
from openrecall.client.consumer import UploaderConsumer
from openrecall.client.ffmpeg_manager import FFmpegManager
from openrecall.client.sck_stream import (
    MonitorInfo,
    PixelFormatProfile,
    RawFrame,
    SCKStreamError,
    create_monitor_source,
    list_monitors_detailed,
)
from openrecall.shared.config import settings
from openrecall.shared.utils import get_active_app_name, get_active_window_title

logger = logging.getLogger(__name__)

MIN_DISK_FREE_BYTES = 10 * 1024 * 1024 * 1024  # 10 GB
STATUS_LOG_INTERVAL_SECONDS = 20


class CaptureModeState:
    """Capture control state machine."""

    SCK_ACTIVE = "SCK_ACTIVE"
    SCK_DEGRADED_RETRYING = "SCK_DEGRADED_RETRYING"
    LEGACY_ACTIVE = "LEGACY_ACTIVE"
    PAUSED_BY_TOGGLE = "PAUSED_BY_TOGGLE"


@dataclass
class PipelineStats:
    dropped_generation_mismatch: int = 0
    dropped_queue_full: int = 0
    profile_change_restarts: int = 0
    broken_pipe_events: int = 0


class MonitorPipelineController:
    """Per-monitor pipeline with atomic profile reconfigure and writer isolation."""

    STATE_STOPPED = "STOPPED"
    STATE_RUNNING = "RUNNING"
    STATE_RESTARTING = "RESTARTING"
    STATE_STOPPING = "STOPPING"
    KEEPALIVE_INTERVAL_SECONDS = 1.0

    def __init__(
        self,
        monitor_id: str,
        ffmpeg_manager: FFmpegManager,
        queue_maxsize: int = 64,
        restart_on_profile_change: bool = True,
        pipe_write_warn_ms: int = 50,
    ):
        self.monitor_id = monitor_id
        self.ffmpeg_manager = ffmpeg_manager
        self.restart_on_profile_change = restart_on_profile_change
        self.pipe_write_warn_ms = pipe_write_warn_ms

        self.stats = PipelineStats()
        self._state = self.STATE_STOPPED
        self._pipeline_lock = threading.Lock()
        self._generation = 0
        self._profile: Optional[PixelFormatProfile] = None

        self._queue: queue.Queue[tuple[int, RawFrame]] = queue.Queue(maxsize=max(1, queue_maxsize))
        self._stop_event = threading.Event()
        self._writer_thread: Optional[threading.Thread] = None
        self._write_latencies_ms: deque[float] = deque(maxlen=512)
        self._broken_pipe_recovering = False
        self._last_frame_data: Optional[bytes] = None
        self._last_source_frame_monotonic: float = 0.0
        self._last_write_monotonic: float = 0.0
        self._keepalive_stall_warned = False

    def start(self, profile: PixelFormatProfile) -> None:
        with self._pipeline_lock:
            if self._state == self.STATE_STOPPING:
                return
            if self._state == self.STATE_RUNNING:
                return
            self._profile = profile
            self._generation += 1
            self._state = self.STATE_RUNNING
            self._last_frame_data = None
            self._last_source_frame_monotonic = 0.0
            self._last_write_monotonic = 0.0
            self._keepalive_stall_warned = False

        self.ffmpeg_manager.start_with_profile(profile)
        self._start_writer_thread_if_needed()

    def stop(self) -> None:
        with self._pipeline_lock:
            self._state = self.STATE_STOPPING
            self._generation += 1

        self._stop_event.set()
        if self._writer_thread and self._writer_thread.is_alive():
            self._writer_thread.join(timeout=2.0)
        self._writer_thread = None
        self.ffmpeg_manager.stop()

        with self._pipeline_lock:
            self._state = self.STATE_STOPPED
            self._profile = None
            self._last_frame_data = None
            self._last_source_frame_monotonic = 0.0
            self._last_write_monotonic = 0.0
            self._keepalive_stall_warned = False

    def submit_frame(self, frame: RawFrame) -> None:
        if self._state == self.STATE_STOPPING:
            return

        if self._profile is None:
            self.start(frame.profile)

        if self.restart_on_profile_change and frame.profile != self._profile:
            self._reconfigure_pipeline(frame.profile)

        self._last_frame_data = frame.data
        self._last_source_frame_monotonic = time.monotonic()
        if self._keepalive_stall_warned:
            logger.info("Source frames resumed monitor=%s", self.monitor_id)
            self._keepalive_stall_warned = False
        self._enqueue_for_generation(frame, generation=self._generation)

    def _reconfigure_pipeline(self, profile: PixelFormatProfile) -> None:
        with self._pipeline_lock:
            if self._state == self.STATE_STOPPING:
                return
            if self._profile == profile:
                return
            self._state = self.STATE_RESTARTING
            self._generation += 1
            self._profile = profile
            self._last_frame_data = None
            self._last_source_frame_monotonic = 0.0
            self._last_write_monotonic = 0.0
            self._keepalive_stall_warned = False

        self.stats.profile_change_restarts += 1
        self.ffmpeg_manager.reconfigure(profile)

        with self._pipeline_lock:
            if self._state != self.STATE_STOPPING:
                self._state = self.STATE_RUNNING
        self._broken_pipe_recovering = False

    def _enqueue_for_generation(self, frame: RawFrame, generation: int) -> None:
        item = (generation, frame)
        try:
            self._queue.put_nowait(item)
            return
        except queue.Full:
            self.stats.dropped_queue_full += 1

        try:
            self._queue.get_nowait()
            self._queue.task_done()
        except queue.Empty:
            pass

        try:
            self._queue.put_nowait(item)
        except queue.Full:
            self.stats.dropped_queue_full += 1

    def _start_writer_thread_if_needed(self) -> None:
        if self._writer_thread and self._writer_thread.is_alive():
            return
        self._stop_event.clear()
        self._writer_thread = threading.Thread(
            target=self._writer_loop,
            name=f"MonitorWriter-{self.monitor_id}",
            daemon=True,
        )
        self._writer_thread.start()

    def _writer_loop(self) -> None:
        while not self._stop_event.is_set():
            self._drain_once(block=True)

    def _drain_once_for_test(self) -> None:
        self._drain_once(block=False)

    @property
    def write_latency_p95_ms(self) -> float:
        if not self._write_latencies_ms:
            return 0.0
        samples = sorted(self._write_latencies_ms)
        idx = max(0, int(0.95 * (len(samples) - 1)))
        return float(samples[idx])

    @property
    def writer_alive(self) -> bool:
        return bool(self._writer_thread and self._writer_thread.is_alive())

    def seconds_since_last_write(self, now_monotonic: Optional[float] = None) -> Optional[float]:
        if self._last_write_monotonic <= 0:
            return None
        now = now_monotonic if now_monotonic is not None else time.monotonic()
        return max(0.0, now - self._last_write_monotonic)

    def _drain_once(self, block: bool) -> None:
        timeout = 0.2 if block else 0.0
        try:
            generation, frame = self._queue.get(timeout=timeout)
        except queue.Empty:
            self._emit_keepalive_frame_if_due()
            return

        try:
            if generation != self._generation:
                self.stats.dropped_generation_mismatch += 1
                return

            elapsed = self.ffmpeg_manager.write_frame(frame.data)
            self._broken_pipe_recovering = False
            self._last_write_monotonic = time.monotonic()
            elapsed_ms = float(elapsed or 0.0) * 1000.0
            self._write_latencies_ms.append(elapsed_ms)
            if elapsed_ms >= self.pipe_write_warn_ms:
                logger.warning(
                    "Slow ffmpeg stdin write monitor=%s latency=%.2fms",
                    self.monitor_id,
                    elapsed_ms,
                )

        except (BrokenPipeError, OSError):
            if not self._broken_pipe_recovering:
                self.stats.broken_pipe_events += 1
                self._broken_pipe_recovering = True
                if self.restart_on_profile_change and self._profile is not None:
                    self._reconfigure_pipeline(self._profile)
        finally:
            self._queue.task_done()

    def _emit_keepalive_frame_if_due(self) -> None:
        if self._state == self.STATE_STOPPING:
            return
        if self._last_frame_data is None:
            return

        now = time.monotonic()
        last_write = self._last_write_monotonic or self._last_source_frame_monotonic
        if last_write and (now - last_write) < self.KEEPALIVE_INTERVAL_SECONDS:
            return

        if (
            self._last_source_frame_monotonic
            and (now - self._last_source_frame_monotonic) >= self.KEEPALIVE_INTERVAL_SECONDS * 2
            and not self._keepalive_stall_warned
        ):
            logger.warning(
                "No new source frames monitor=%s for %.1fs, emitting keepalive frames",
                self.monitor_id,
                now - self._last_source_frame_monotonic,
            )
            self._keepalive_stall_warned = True

        try:
            elapsed = self.ffmpeg_manager.write_frame(self._last_frame_data)
            self._broken_pipe_recovering = False
            self._last_write_monotonic = now
            elapsed_ms = float(elapsed or 0.0) * 1000.0
            self._write_latencies_ms.append(elapsed_ms)
            if elapsed_ms >= self.pipe_write_warn_ms:
                logger.warning(
                    "Slow ffmpeg keepalive write monitor=%s latency=%.2fms",
                    self.monitor_id,
                    elapsed_ms,
                )
        except (BrokenPipeError, OSError):
            if not self._broken_pipe_recovering:
                self.stats.broken_pipe_events += 1
                self._broken_pipe_recovering = True
                if self.restart_on_profile_change and self._profile is not None:
                    self._reconfigure_pipeline(self._profile)


class VideoRecorder:
    """Client-side video recorder with monitor-id driven capture pipelines."""

    def __init__(
        self,
        buffer: Optional[LocalBuffer] = None,
        consumer: Optional[UploaderConsumer] = None,
    ):
        self.buffer = buffer or get_buffer()
        self.output_dir = settings.client_video_chunks_path
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._stop_requested = False
        self.recording_enabled = True
        self.upload_enabled = True
        self.last_heartbeat_time = 0.0
        self._disk_full_paused = False
        self._runtime_recording_paused = False
        self._paused_previous_state = CaptureModeState.SCK_DEGRADED_RETRYING
        self._capture_state = CaptureModeState.SCK_DEGRADED_RETRYING

        self._legacy_ffmpeg = FFmpegManager(
            output_dir=self.output_dir,
            chunk_duration=settings.video_chunk_duration,
            fps=settings.video_fps,
            crf=settings.video_crf,
            on_chunk_complete=lambda path: self._on_chunk_complete(path, None),
        )

        # Backward-compatible alias used by existing tests.
        self._ffmpeg = self._legacy_ffmpeg

        self._pipelines: dict[str, MonitorPipelineController] = {}
        self._sources: dict[str, object] = {}
        self._monitor_by_id: dict[str, MonitorInfo] = {}
        self._use_legacy_mode = False
        self._state_lock = threading.RLock()

        self._watcher_stop_event = threading.Event()
        self._watcher_thread: Optional[threading.Thread] = None
        self._monitor_sync_interval = max(2, int(settings.sck_recovery_probe_seconds))
        self._last_monitor_sync_at = 0.0

        self._sck_retry_count = 0
        self._next_sck_retry_at = 0.0
        self._legacy_probe_at = 0.0
        self._last_sck_error_code = ""
        self._last_sck_error_at = 0.0
        self._sck_available = False
        self._status_log_interval_seconds = STATUS_LOG_INTERVAL_SECONDS
        self._last_status_log_at = 0.0
        self._pipeline_stall_timeout_seconds = max(
            30.0,
            float(settings.video_no_chunk_progress_timeout_seconds),
        )
        self._write_stall_timeout_seconds = max(
            5.0,
            min(60.0, (float(settings.video_pipe_write_timeout_ms) / 1000.0) * 2.0),
        )
        self._chunk_progress_by_monitor: dict[str, tuple[str, float]] = {}

        self.consumer = consumer or UploaderConsumer(
            buffer=self.buffer,
            should_upload=lambda: self.upload_enabled,
        )

    def check_ffmpeg_available(self) -> bool:
        return self._legacy_ffmpeg.check_ffmpeg_available()

    def start(self) -> None:
        if not self.consumer.is_alive():
            self.consumer.start()
        self._start_monitor_watcher()

    def stop(self) -> None:
        self._stop_requested = True
        self._stop_monitor_watcher()
        self._stop_recording_backend()
        self.consumer.stop()
        if self.consumer.is_alive():
            self.consumer.join(timeout=2.0)

    def run_capture_loop(self) -> None:
        os.environ["TOKENIZERS_PARALLELISM"] = "false"
        self.start()

        logger.info("Video recorder started (monitor-id pipeline)")
        logger.info("  Chunk duration: %ss", settings.video_chunk_duration)
        logger.info("  FPS: %s, CRF: %s", settings.video_fps, settings.video_crf)
        logger.info(
            "  Pipeline mode: %s | Pipe write timeout: %sms | No-progress timeout: %ss",
            settings.video_pipeline_mode,
            settings.video_pipe_write_timeout_ms,
            settings.video_no_chunk_progress_timeout_seconds,
        )
        logger.info("  Output dir: %s", self.output_dir)

        self._start_recording_backend()

        while not self._stop_requested:
            now = time.time()
            if now - self.last_heartbeat_time > 5:
                self._send_heartbeat()
                self.last_heartbeat_time = now
            if now - self._last_status_log_at >= self._status_log_interval_seconds:
                self._log_periodic_status(now)

            if not self.recording_enabled:
                if not self._runtime_recording_paused:
                    self._pause_recording_backend_for_runtime_toggle()
                    self._runtime_recording_paused = True
                    logger.info("⏸️ Recording paused (recording_enabled=False)")
                time.sleep(1)
                continue

            if self._runtime_recording_paused:
                resumed = self._resume_recording_backend_for_runtime_toggle()
                self._runtime_recording_paused = False
                if resumed:
                    logger.info("▶️ Recording resumed (recording_enabled=True)")
                else:
                    logger.info("▶️ Recording resumed (recording_enabled=True); recreating capture backend")
                    self._start_recording_backend()

            if self._check_disk_full():
                if not self._disk_full_paused:
                    logger.warning(
                        "Disk space below %sGB, pausing video recording",
                        MIN_DISK_FREE_BYTES // (1024**3),
                    )
                    self._disk_full_paused = True
                    self._stop_recording_backend()
                time.sleep(5)
                continue

            if self._disk_full_paused:
                logger.info("Disk space recovered, resuming video recording")
                self._disk_full_paused = False

            if not self._backend_alive():
                self._start_recording_backend()

            if self._use_legacy_mode:
                if self._legacy_ffmpeg.restart_count_last_hour > 10:
                    logger.error("FFmpeg restart count exceeded 10/hour in legacy mode")
            else:
                for monitor_id, controller in self._pipelines.items():
                    if controller.ffmpeg_manager.restart_count_last_hour > 10:
                        logger.error(
                            "FFmpeg restart count exceeded 10/hour for monitor %s",
                            monitor_id,
                        )

            time.sleep(1)

    def _log_periodic_status(self, now: Optional[float] = None) -> None:
        current_time = now or time.time()
        self._last_status_log_at = current_time

        pending_uploads = self.buffer.count()

        if self._capture_state == CaptureModeState.PAUSED_BY_TOGGLE or not self.recording_enabled:
            logger.info("Client status | state=paused | pending_uploads=%s", pending_uploads)
            return

        if self._disk_full_paused:
            logger.info("Client status | state=disk_full_paused | pending_uploads=%s", pending_uploads)
            return

        if self._use_legacy_mode or self._capture_state == CaptureModeState.LEGACY_ACTIVE:
            legacy_chunk = self._chunk_name_for_manager(self._legacy_ffmpeg)
            logger.info(
                "Client status | state=recording_legacy | current_chunk=%s | pending_uploads=%s",
                legacy_chunk,
                pending_uploads,
            )
            return

        if self._capture_state == CaptureModeState.SCK_ACTIVE:
            monitor_chunks = []
            for monitor_id in sorted(self._pipelines.keys()):
                controller = self._pipelines[monitor_id]
                chunk_name = self._chunk_name_for_manager(controller.ffmpeg_manager)
                monitor_chunks.append(f"{monitor_id}:{chunk_name}")

            logger.info(
                "Client status | state=recording | monitor_chunks=%s | pending_uploads=%s",
                ", ".join(monitor_chunks) if monitor_chunks else "initializing",
                pending_uploads,
            )
            return

        retry_in_seconds = max(0, int(self._next_sck_retry_at - current_time))
        logger.info(
            "Client status | state=retrying_capture | retry_in=%ss | pending_uploads=%s",
            retry_in_seconds,
            pending_uploads,
        )

    @staticmethod
    def _chunk_name_from_path(chunk_path: object) -> str:
        if not isinstance(chunk_path, str) or not chunk_path:
            return "initializing"
        return Path(chunk_path).name

    @staticmethod
    def _chunk_name_for_manager(ffmpeg_manager: FFmpegManager) -> str:
        active_chunk_path = getattr(ffmpeg_manager, "active_chunk_path", None)
        chunk_name = VideoRecorder._chunk_name_from_path(active_chunk_path)
        if chunk_name != "initializing":
            return chunk_name

        chunk_name = VideoRecorder._chunk_name_from_path(ffmpeg_manager.current_chunk_path)
        if chunk_name != "initializing":
            return chunk_name

        try:
            latest_file = max(
                ffmpeg_manager.output_dir.glob("*.mp4"),
                key=lambda p: p.stat().st_mtime,
                default=None,
            )
            if latest_file is not None:
                return latest_file.name
        except Exception:
            pass
        return chunk_name

    def _backend_alive(self) -> bool:
        if self._capture_state == CaptureModeState.PAUSED_BY_TOGGLE:
            return True
        if self._use_legacy_mode or self._capture_state == CaptureModeState.LEGACY_ACTIVE:
            return self._legacy_ffmpeg.is_alive()
        if self._capture_state == CaptureModeState.SCK_DEGRADED_RETRYING:
            return False
        return bool(self._sources)

    def _start_recording_backend(self) -> None:
        if self._capture_state == CaptureModeState.PAUSED_BY_TOGGLE:
            return

        if self._use_legacy_mode or self._capture_state == CaptureModeState.LEGACY_ACTIVE:
            if not self._legacy_ffmpeg.is_alive():
                try:
                    self._legacy_ffmpeg.start()
                except RuntimeError as exc:
                    logger.error("Failed to start legacy FFmpeg: %s", exc)
            return

        if self._capture_state == CaptureModeState.SCK_ACTIVE and self._sources:
            return

        self._attempt_sck_start_once()

    def _pause_recording_backend_for_runtime_toggle(self) -> None:
        """Pause recording without tearing down monitor pipelines."""
        self._paused_previous_state = self._capture_state
        if self._use_legacy_mode:
            if self._legacy_ffmpeg.is_alive():
                self._legacy_ffmpeg.stop()
        else:
            self._stop_monitor_sources_only()
        self._capture_state = CaptureModeState.PAUSED_BY_TOGGLE

    def _resume_recording_backend_for_runtime_toggle(self) -> bool:
        """Resume recording after runtime toggle pause."""
        self._capture_state = self._paused_previous_state

        if self._use_legacy_mode:
            if not self._legacy_ffmpeg.is_alive():
                try:
                    self._legacy_ffmpeg.start()
                except RuntimeError as exc:
                    logger.error("Failed to resume legacy FFmpeg capture: %s", exc)
                    return False
            return self._legacy_ffmpeg.is_alive()

        if self._sources:
            self._capture_state = CaptureModeState.SCK_ACTIVE
            return True

        if self._pipelines and self._resume_monitor_sources_from_existing_pipelines():
            self._capture_state = CaptureModeState.SCK_ACTIVE
            return True

        self._capture_state = CaptureModeState.SCK_DEGRADED_RETRYING
        return self._attempt_sck_start_once(force=True)

    def _resume_monitor_sources_from_existing_pipelines(self) -> bool:
        if not self._pipelines:
            return False

        monitor_ids = list(self._pipelines.keys())
        monitors = [
            self._monitor_by_id.get(monitor_id)
            for monitor_id in monitor_ids
            if self._monitor_by_id.get(monitor_id) is not None
        ]
        if not monitors:
            return False

        for index, monitor in enumerate(monitors):
            controller = self._pipelines.get(monitor.monitor_id)
            if controller is None:
                continue

            source = create_monitor_source(
                monitor=monitor,
                fps=settings.video_fps,
                on_frame=controller.submit_frame,
                pool_max_bytes=settings.video_pool_max_bytes,
                color_range_mode=settings.video_color_range,
            )
            try:
                source.start()
            except Exception:
                logger.exception("Failed to resume source for monitor_id=%s", monitor.monitor_id)
                continue

            self._sources[monitor.monitor_id] = source
            if index > 0 and settings.video_segment_stagger_seconds > 0:
                time.sleep(settings.video_segment_stagger_seconds)

        return bool(self._sources)

    def _stop_monitor_sources_only(self) -> None:
        if not self._sources:
            return
        for source in list(self._sources.values()):
            try:
                source.stop()
            except Exception:
                logger.exception("Failed stopping monitor source")
        self._sources.clear()

    def _stop_monitor_capture(self, clear_metadata: bool) -> None:
        self._stop_monitor_sources_only()

        if self._pipelines:
            for controller in list(self._pipelines.values()):
                try:
                    controller.stop()
                except Exception:
                    logger.exception("Failed stopping monitor pipeline")
        self._pipelines.clear()
        self._chunk_progress_by_monitor.clear()

        if clear_metadata:
            self._monitor_by_id = {}

    def _stop_recording_backend(self) -> None:
        self._stop_monitor_capture(clear_metadata=True)

        if self._legacy_ffmpeg.is_alive():
            self._legacy_ffmpeg.stop()

        self._capture_state = CaptureModeState.SCK_DEGRADED_RETRYING
        self._use_legacy_mode = False

    def _discover_target_monitors(self) -> tuple[list[MonitorInfo], Optional[SCKStreamError]]:
        available, discovery_error = list_monitors_detailed()
        self._sck_available = any(m.backend == "sck" for m in available)
        if not available:
            return [], discovery_error

        selected = self._filter_monitors(available, settings.video_monitor_id_list)
        if not selected:
            error = discovery_error or SCKStreamError(
                code="display_not_found",
                detail="Selected monitor IDs were not found in current topology",
                retryable=True,
            )
            return [], error
        return selected, None

    def _filter_monitors(self, monitors: list[MonitorInfo], monitor_ids: list[str]) -> list[MonitorInfo]:
        selected = list(monitors)
        normalized_ids = {m.strip() for m in monitor_ids if m.strip()}
        if normalized_ids:
            selected = [m for m in selected if m.monitor_id in normalized_ids]

        if settings.primary_monitor_only and selected:
            primary = [m for m in selected if m.is_primary]
            return primary[:1] if primary else selected[:1]

        return selected

    def _attempt_sck_start_once(self, force: bool = False) -> bool:
        with self._state_lock:
            now = time.time()
            if not force and now < self._next_sck_retry_at:
                return False

            monitors, error = self._discover_target_monitors()
            if not monitors:
                self._record_sck_error(error or SCKStreamError("no_displays", "No displays discovered"))
                self._sck_retry_count += 1
                self._capture_state = CaptureModeState.SCK_DEGRADED_RETRYING
                self._use_legacy_mode = False
                self._schedule_sck_retry()
                self._maybe_switch_to_legacy()
                return False

            if not self._start_monitor_capture(monitors):
                self._sck_retry_count += 1
                self._capture_state = CaptureModeState.SCK_DEGRADED_RETRYING
                self._use_legacy_mode = False
                self._schedule_sck_retry()
                self._maybe_switch_to_legacy()
                return False

            self._clear_sck_error()
            self._sck_retry_count = 0
            self._next_sck_retry_at = 0.0
            self._capture_state = CaptureModeState.SCK_ACTIVE
            self._use_legacy_mode = False

            if self._legacy_ffmpeg.is_alive():
                self._legacy_ffmpeg.stop()

            return True

    def _schedule_sck_retry(self) -> None:
        if self._last_sck_error_code == "permission_denied":
            self._next_sck_retry_at = time.time() + max(1, settings.sck_permission_backoff_seconds)
        else:
            self._next_sck_retry_at = time.time() + max(1, settings.sck_retry_backoff_seconds)

    def _maybe_switch_to_legacy(self) -> None:
        if self._sck_retry_count < max(1, settings.sck_start_retry_max):
            return
        self._switch_to_legacy(
            f"SCK retries exhausted ({self._sck_retry_count}/{settings.sck_start_retry_max})"
        )

    def _switch_to_legacy(self, reason: str) -> None:
        with self._state_lock:
            logger.warning("Using legacy FFmpeg capture fallback: %s", reason)
            self._stop_monitor_capture(clear_metadata=False)
            self._capture_state = CaptureModeState.LEGACY_ACTIVE
            self._use_legacy_mode = True
            self._legacy_probe_at = time.time() + max(1, settings.sck_recovery_probe_seconds)

            if not self._legacy_ffmpeg.is_alive():
                try:
                    self._legacy_ffmpeg.start()
                except RuntimeError as exc:
                    logger.error("Failed to start legacy FFmpeg fallback: %s", exc)

    def _start_monitor_capture(self, monitors: Optional[list[MonitorInfo]] = None) -> bool:
        with self._state_lock:
            if monitors is None:
                monitors, error = self._discover_target_monitors()
                if not monitors:
                    self._record_sck_error(error or SCKStreamError("no_displays", "No displays discovered"))
                    return False

            self._stop_monitor_capture(clear_metadata=False)
            self._monitor_by_id = {m.monitor_id: m for m in monitors}
            logger.info("Selected monitors: %s", ", ".join(m.monitor_id for m in monitors))

            for index, monitor in enumerate(monitors):
                monitor_output_dir = self.output_dir / f"monitor_{monitor.monitor_id}"
                monitor_output_dir.mkdir(parents=True, exist_ok=True)

                ffmpeg_manager = FFmpegManager(
                    output_dir=monitor_output_dir,
                    chunk_duration=settings.video_chunk_duration,
                    fps=settings.video_fps,
                    crf=settings.video_crf,
                    on_chunk_complete=lambda path, m=monitor: self._on_chunk_complete(path, m),
                    monitor_id=monitor.monitor_id,
                    segment_list_filename=f"segments_{monitor.monitor_id}.csv",
                    pipeline_mode=settings.video_pipeline_mode,
                    pipe_write_timeout_ms=settings.video_pipe_write_timeout_ms,
                )

                controller = MonitorPipelineController(
                    monitor_id=monitor.monitor_id,
                    ffmpeg_manager=ffmpeg_manager,
                    queue_maxsize=64,
                    restart_on_profile_change=settings.video_pipeline_restart_on_profile_change,
                    pipe_write_warn_ms=settings.video_pipe_write_warn_ms,
                )

                source = create_monitor_source(
                    monitor=monitor,
                    fps=settings.video_fps,
                    on_frame=controller.submit_frame,
                    pool_max_bytes=settings.video_pool_max_bytes,
                    color_range_mode=settings.video_color_range,
                )

                try:
                    source.start()
                except SCKStreamError as exc:
                    self._record_sck_error(exc)
                    logger.exception("Failed to start source for monitor_id=%s", monitor.monitor_id)
                    controller.stop()
                    continue
                except Exception as exc:
                    self._record_sck_error(SCKStreamError("stream_start_failed", str(exc)))
                    logger.exception("Failed to start source for monitor_id=%s", monitor.monitor_id)
                    controller.stop()
                    continue

                self._pipelines[monitor.monitor_id] = controller
                self._sources[monitor.monitor_id] = source

                if index > 0 and settings.video_segment_stagger_seconds > 0:
                    time.sleep(settings.video_segment_stagger_seconds)

            return bool(self._sources)

    def _record_sck_error(self, error: SCKStreamError) -> None:
        self._last_sck_error_code = (error.code or "unknown").strip()
        self._last_sck_error_at = time.time()

    def _clear_sck_error(self) -> None:
        self._last_sck_error_code = ""
        self._last_sck_error_at = 0.0

    def _start_monitor_watcher(self) -> None:
        if self._watcher_thread and self._watcher_thread.is_alive():
            return

        self._watcher_stop_event.clear()
        self._watcher_thread = threading.Thread(
            target=self._monitor_watcher_loop,
            name="MonitorWatcher",
            daemon=True,
        )
        self._watcher_thread.start()

    def _stop_monitor_watcher(self) -> None:
        self._watcher_stop_event.set()
        if self._watcher_thread and self._watcher_thread.is_alive():
            self._watcher_thread.join(timeout=2.0)
        self._watcher_thread = None

    def _monitor_watcher_loop(self) -> None:
        while not self._watcher_stop_event.wait(timeout=1.0):
            if self._stop_requested:
                return
            try:
                self._watcher_tick()
            except Exception:
                logger.exception("Monitor watcher tick failed")

    def _watcher_tick(self) -> None:
        if self._runtime_recording_paused or self._disk_full_paused or not self.recording_enabled:
            return

        if self._capture_state == CaptureModeState.SCK_ACTIVE:
            now = time.time()
            stalled_monitors = self._detect_stalled_pipelines(now)
            if stalled_monitors:
                logger.error(
                    "Detected stalled monitor-id pipeline(s): %s; forcing SCK backend restart",
                    ", ".join(stalled_monitors),
                )
                if not self._attempt_sck_start_once(force=True):
                    self._capture_state = CaptureModeState.SCK_DEGRADED_RETRYING
                    self._schedule_sck_retry()
                return
            if now - self._last_monitor_sync_at >= self._monitor_sync_interval:
                self._last_monitor_sync_at = now
                self._sync_monitors()
            return

        if self._capture_state == CaptureModeState.SCK_DEGRADED_RETRYING:
            self._attempt_sck_start_once()
            return

        if self._capture_state == CaptureModeState.LEGACY_ACTIVE and settings.sck_auto_recover_from_legacy:
            self._try_recover_from_legacy()

    def _detect_stalled_pipelines(self, now_wallclock: Optional[float] = None) -> list[str]:
        now = now_wallclock if now_wallclock is not None else time.time()
        now_monotonic = time.monotonic()
        active_ids = set(self._pipelines.keys())
        for monitor_id in list(self._chunk_progress_by_monitor.keys()):
            if monitor_id not in active_ids:
                self._chunk_progress_by_monitor.pop(monitor_id, None)

        stalled: list[str] = []
        for monitor_id, controller in self._pipelines.items():
            manager = controller.ffmpeg_manager
            chunk_name = self._chunk_name_for_manager(manager)

            progress = self._chunk_progress_by_monitor.get(monitor_id)
            if progress is None or progress[0] != chunk_name:
                self._chunk_progress_by_monitor[monitor_id] = (chunk_name, now)
                continue

            stagnant_for = now - progress[1]
            if stagnant_for < self._pipeline_stall_timeout_seconds:
                continue

            seconds_since_write = controller.seconds_since_last_write(now_monotonic)
            write_stuck_for = float(getattr(manager, "write_stuck_seconds", 0.0) or 0.0)
            writer_alive = bool(getattr(controller, "writer_alive", False))
            pipeline_mode = str(getattr(manager, "pipeline_mode", "segment") or "segment")
            no_write_progress = (
                seconds_since_write is None
                or seconds_since_write >= self._write_stall_timeout_seconds
            )
            write_blocked = write_stuck_for >= self._write_stall_timeout_seconds
            no_chunk_progress = pipeline_mode == "segment"

            if no_chunk_progress or no_write_progress or write_blocked or not writer_alive:
                since_write_value = (
                    f"{seconds_since_write:.1f}s"
                    if seconds_since_write is not None
                    else "n/a"
                )
                logger.error(
                    "Stalled pipeline detected | monitor_id=%s | chunk=%s | stagnant_for=%.1fs | "
                    "seconds_since_write=%s | write_stuck_for=%.1fs | writer_alive=%s | mode=%s | no_chunk_progress=%s",
                    monitor_id,
                    chunk_name,
                    stagnant_for,
                    since_write_value,
                    write_stuck_for,
                    writer_alive,
                    pipeline_mode,
                    no_chunk_progress,
                )
                stalled.append(monitor_id)

        return stalled

    def _sync_monitors(self) -> None:
        with self._state_lock:
            monitors, error = self._discover_target_monitors()
            if not monitors:
                if error:
                    self._record_sck_error(error)
                self._capture_state = CaptureModeState.SCK_DEGRADED_RETRYING
                self._use_legacy_mode = False
                self._schedule_sck_retry()
                return

            desired_ids = {m.monitor_id for m in monitors}
            current_ids = set(self._monitor_by_id.keys())
            if desired_ids == current_ids:
                return

            logger.info(
                "Monitor topology changed (current=%s, desired=%s), restarting monitor-id pipelines",
                sorted(current_ids),
                sorted(desired_ids),
            )
            if not self._start_monitor_capture(monitors):
                self._capture_state = CaptureModeState.SCK_DEGRADED_RETRYING
                self._use_legacy_mode = False
                self._schedule_sck_retry()

    def _try_recover_from_legacy(self) -> None:
        with self._state_lock:
            now = time.time()
            if now < self._legacy_probe_at:
                return
            self._legacy_probe_at = now + max(1, settings.sck_recovery_probe_seconds)

            monitors, error = self._discover_target_monitors()
            if not monitors:
                if error:
                    self._record_sck_error(error)
                return

            logger.info("Legacy mode recovery probe: attempting switch back to monitor-id pipeline")
            if self._legacy_ffmpeg.is_alive():
                self._legacy_ffmpeg.stop()

            if self._start_monitor_capture(monitors):
                self._capture_state = CaptureModeState.SCK_ACTIVE
                self._use_legacy_mode = False
                self._sck_retry_count = 0
                self._next_sck_retry_at = 0.0
                self._clear_sck_error()
                logger.info("Recovered from legacy fallback to monitor-id pipeline")
                return

            self._capture_state = CaptureModeState.LEGACY_ACTIVE
            self._use_legacy_mode = True
            if not self._legacy_ffmpeg.is_alive():
                try:
                    self._legacy_ffmpeg.start()
                except RuntimeError as exc:
                    logger.error("Failed to restart legacy FFmpeg after recovery probe: %s", exc)

    def _on_chunk_complete(self, chunk_path: str, monitor: Optional[MonitorInfo] = None) -> None:
        try:
            path = Path(chunk_path)
            if not path.exists():
                logger.warning("Completed chunk not found: %s", chunk_path)
                return

            file_size = path.stat().st_size
            if file_size == 0:
                logger.warning("Empty chunk file: %s", chunk_path)
                return

            monitor_id = monitor.monitor_id if monitor else "legacy"
            logger.info(
                "Video chunk recording ended | file=%s | size_mb=%.1f | monitor_id=%s",
                path.name,
                file_size / (1024 * 1024),
                monitor_id,
            )

            checksum = self._compute_checksum(chunk_path)
            timestamp = int(time.time())

            metadata = {
                "type": "video_chunk",
                "timestamp": timestamp,
                "start_time": timestamp - settings.video_chunk_duration,
                "end_time": timestamp,
                "device_name": monitor.name if monitor else "primary_display",
                "monitor_id": monitor.monitor_id if monitor else "",
                "monitor_width": monitor.width if monitor else 0,
                "monitor_height": monitor.height if monitor else 0,
                "monitor_is_primary": 1 if monitor and monitor.is_primary else 0,
                "monitor_backend": monitor.backend if monitor else "",
                "monitor_fingerprint": monitor.fingerprint if monitor else "",
                "active_app": get_active_app_name() or "Unknown App",
                "active_window": get_active_window_title() or "Unknown Title",
                "resolution": f"{monitor.width}x{monitor.height}" if monitor else "",
                "fps": settings.video_fps,
                "codec": "h264",
                "crf": settings.video_crf,
                "chunk_filename": path.name,
                "file_size_bytes": file_size,
                "checksum": f"sha256:{checksum}",
            }
            # Canonical server keys (keep active_* for backward compatibility).
            metadata["app_name"] = metadata["active_app"]
            metadata["window_title"] = metadata["active_window"]

            self.buffer.enqueue_file(chunk_path, metadata)
            logger.info(
                "Video chunk enqueued: %s (%.1fMB monitor_id=%s)",
                path.name,
                file_size / (1024 * 1024),
                metadata["monitor_id"] or monitor_id,
            )
        except Exception:
            logger.exception("Error processing completed chunk %s", chunk_path)

    def _compute_checksum(self, file_path: str) -> str:
        sha256 = hashlib.sha256()
        with open(file_path, "rb") as file:
            for block in iter(lambda: file.read(65536), b""):
                sha256.update(block)
        return sha256.hexdigest()

    def _check_disk_full(self) -> bool:
        try:
            usage = shutil.disk_usage(str(self.output_dir))
            return usage.free < MIN_DISK_FREE_BYTES
        except Exception:
            return False

    def _capture_mode_status(self) -> str:
        if self._capture_state == CaptureModeState.PAUSED_BY_TOGGLE or self._runtime_recording_paused:
            return "paused"
        if self._use_legacy_mode or self._capture_state == CaptureModeState.LEGACY_ACTIVE:
            return "legacy"
        if self._capture_state in {CaptureModeState.SCK_ACTIVE, CaptureModeState.SCK_DEGRADED_RETRYING}:
            return "monitor_id"
        return "unknown"

    def _send_heartbeat(self) -> None:
        try:
            url = f"{settings.api_url.rstrip('/')}/heartbeat"
            parsed = urllib.parse.urlparse(url)
            is_loopback = parsed.hostname in {"localhost", "127.0.0.1", "::1"}

            request_kwargs = {"timeout": 2}
            if is_loopback:
                request_kwargs["proxies"] = {"http": None, "https": None}

            payload = {
                "capture_mode": self._capture_mode_status(),
                "sck_available": bool(self._sck_available),
                "sck_last_error_code": self._last_sck_error_code,
                "sck_last_error_at": self._last_sck_error_at,
                "selected_monitors": sorted(self._monitor_by_id.keys()),
            }
            response = requests.post(url, json=payload, **request_kwargs)
            response.raise_for_status()

            data = response.json()
            config = data.get("config", {})
            self.recording_enabled = config.get("recording_enabled", True)
            self.upload_enabled = config.get("upload_enabled", True)
        except requests.RequestException as exc:
            logger.warning("Heartbeat failed (network): %s", exc)
        except Exception as exc:
            logger.warning("Heartbeat failed: %s", exc)
