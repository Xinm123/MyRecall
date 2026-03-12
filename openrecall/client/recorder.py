import json
import logging
import os
import queue
import threading
import time
from pathlib import Path
from typing import Callable, Mapping

import mss
import numpy as np
import requests
from PIL import Image
from numpy.typing import NDArray

from openrecall.client.accessibility.service import (
    FocusedContextSnapshot,
    PairedCaptureService,
)
from openrecall.client.accessibility.macos import get_frontmost_ax_root
from openrecall.client.accessibility.hash import should_dedup
from openrecall.client.accessibility.types import AccessibilityRawHandoff
from openrecall.client.events.base import (
    CaptureTrigger,
    MonitorDescriptor,
    MonitorRegistry,
    TriggerBus,
    TriggerDebouncer,
    TriggerEvent,
    TriggerEventChannel,
    TriggerIntent,
    TriggerEventSnapshot,
    utc_now_iso,
)
from openrecall.client.events.macos import get_frontmost_app_name, list_monitors
from openrecall.client.events.macos import MacOSAppSwitchMonitor, MacOSEventTap
from openrecall.client.events.permissions import (
    PermissionSnapshot,
    PermissionState,
    PermissionStateMachine,
    detect_permissions,
)
from openrecall.client.consumer import UploaderConsumer
from openrecall.client.spool import SpoolQueue, get_spool
from openrecall.client.v3_uploader import SpoolUploader
from openrecall.shared.config import settings
from openrecall.shared.utils import (
    _build_request_kwargs,
    get_active_app_name,
    get_active_window_title_for_app,
)

logger = logging.getLogger(__name__)

ImageArray = NDArray[np.uint8]


def mean_structured_similarity_index(
    img1: ImageArray, img2: ImageArray, L: int = 255
) -> float:
    """Calculates the Mean Structural Similarity Index (MSSIM) between two images.

    Args:
        img1: The first image as a NumPy array (RGB).
        img2: The second image as a NumPy array (RGB).
        L: The dynamic range of the pixel values (default is 255).

    Returns:
        The MSSIM value between the two images (float between -1 and 1).
    """
    K1, K2 = 0.01, 0.03
    C1, C2 = (K1 * L) ** 2, (K2 * L) ** 2

    def rgb2gray(img: ImageArray) -> NDArray[np.float64]:
        """Converts an RGB image to grayscale."""
        return 0.2989 * img[..., 0] + 0.5870 * img[..., 1] + 0.1140 * img[..., 2]

    img1_gray: NDArray[np.float64] = rgb2gray(img1)
    img2_gray: NDArray[np.float64] = rgb2gray(img2)
    mu1 = float(np.mean(img1_gray))
    mu2 = float(np.mean(img2_gray))
    sigma1_sq = float(np.var(img1_gray))
    sigma2_sq = float(np.var(img2_gray))
    sigma12 = float(np.mean((img1_gray - mu1) * (img2_gray - mu2)))
    ssim_index = ((2 * mu1 * mu2 + C1) * (2 * sigma12 + C2)) / (
        (mu1**2 + mu2**2 + C1) * (sigma1_sq + sigma2_sq + C2)
    )
    return float(ssim_index)


def is_similar(
    img1: ImageArray, img2: ImageArray, similarity_threshold: float | None = None
) -> bool:
    """Checks if two images are similar based on MSSIM.

    Args:
        img1: The first image as a NumPy array.
        img2: The second image as a NumPy array.
        similarity_threshold: The threshold above which images are considered similar.

    Returns:
        True if the images are similar, False otherwise.
    """
    if settings.disable_similarity_filter:
        return False
    similarity: float = compute_similarity(img1, img2)
    threshold = (
        similarity_threshold
        if similarity_threshold is not None
        else settings.similarity_threshold
    )
    return similarity >= threshold


def take_screenshots() -> list[ImageArray]:
    """Takes screenshots of all connected monitors or just the primary one.

    Depending on the `settings.primary_monitor_only` flag, captures either
    all monitors or only the primary monitor (index 1 in mss.monitors).

    Returns:
        A list of screenshots, where each screenshot is a NumPy array (RGB).
    """
    screenshots: list[ImageArray] = []
    with mss.mss() as sct:
        # sct.monitors[0] is the combined view of all monitors
        # sct.monitors[1] is the primary monitor
        # sct.monitors[2:] are other monitors
        monitor_indices = range(1, len(sct.monitors))  # Skip the 'all monitors' entry

        if settings.primary_monitor_only:
            monitor_indices = [1]  # Only index 1 corresponds to the primary monitor

        for i in monitor_indices:
            # Ensure the index is valid before attempting to grab
            if i < len(sct.monitors):
                monitor_info = sct.monitors[i]
                # Grab the screen
                sct_img = sct.grab(monitor_info)
                # Convert to numpy array and change BGRA to RGB
                screenshot = np.array(sct_img)[:, :, [2, 1, 0]]
                screenshots.append(screenshot)
            else:
                logger.warning("Monitor index %s out of bounds. Skipping.", i)

    return screenshots


def resize_image(image: ImageArray, max_dim: int = 800) -> ImageArray:
    """
    Resizes an image to fit within a maximum dimension while maintaining aspect ratio.
    Args:
        image: The input image as a NumPy array (RGB).
        max_dim: The maximum dimension for resizing.
    Returns:
        The resized image as a NumPy array (RGB).
    """
    pil_image = Image.fromarray(image)
    pil_image.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
    return np.array(pil_image)


def compute_similarity(img1: ImageArray, img2: ImageArray) -> float:
    compress_img1: ImageArray = resize_image(img1)
    compress_img2: ImageArray = resize_image(img2)
    return mean_structured_similarity_index(compress_img1, compress_img2)


class MonitorWorker(threading.Thread):
    def __init__(
        self,
        *,
        worker_id: str,
        intent_queue: queue.Queue[TriggerIntent],
        process_intent: Callable[["MonitorWorker", TriggerIntent, float], None],
    ) -> None:
        super().__init__(name=f"monitor-worker-{worker_id}", daemon=True)
        self._worker_id = worker_id
        self._intent_queue = intent_queue
        self._process_intent = process_intent
        self._stop_event = threading.Event()
        self._dedup_state_by_device: dict[str, dict[str, float | str | None]] = {}

    @property
    def worker_id(self) -> str:
        return self._worker_id

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                intent = self._intent_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                self._process_intent(self, intent, time.perf_counter())
            except Exception:
                logger.exception(
                    "MonitorWorker processing failed for %s", self._worker_id
                )

    def record_successful_spool_write(
        self,
        *,
        final_device_name: str,
        content_hash: str | None,
        write_time_epoch: float,
    ) -> None:
        self._dedup_state_by_device[final_device_name] = {
            "last_content_hash": content_hash,
            "last_write_time": write_time_epoch,
        }

    def should_skip_dedup(
        self,
        *,
        capture_trigger: str,
        final_device_name: str,
        content_hash: str | None,
        now_epoch: float,
        permission_blocked: bool,
    ) -> bool:
        state = self._dedup_state_by_device.get(final_device_name)
        if state is None:
            return False
        last_write_time = state.get("last_write_time")
        if not isinstance(last_write_time, (int, float)):
            return False
        last_content_hash = state.get("last_content_hash")
        elapsed_seconds = max(0.0, now_epoch - float(last_write_time))
        return should_dedup(
            capture_trigger=capture_trigger,
            content_hash=content_hash,
            last_content_hash=(
                last_content_hash if isinstance(last_content_hash, str) else None
            ),
            elapsed_seconds=elapsed_seconds,
            permission_blocked=permission_blocked,
        )


class ScreenRecorder:
    """Producer: captures screenshots and enqueues to local buffer.

    Manages the consumer thread lifecycle and provides graceful shutdown.
    """

    def __init__(
        self,
        consumer: UploaderConsumer | None = None,
    ):
        """Initialize the recorder.

        Args:
            consumer: UploaderConsumer instance. Creates new if not provided.
        """
        self._stop_requested: bool = False

        # Phase 8.2: Runtime configuration state
        self.recording_enabled: bool = True
        self.upload_enabled: bool = True
        self.last_heartbeat_time: float = 0.0
        self._last_permission_report_time: float = 0.0
        self._last_trigger_report_time: float = 0.0
        self._warned_capture_issue: bool = False
        self.consumer: UploaderConsumer | None = consumer
        self._spool: SpoolQueue = get_spool()
        self._spool_uploader: SpoolUploader = SpoolUploader()
        self._trigger_channel: TriggerEventChannel = TriggerEventChannel(
            settings.trigger_queue_capacity
        )
        self._trigger_bus: TriggerBus = TriggerBus(capacity=1)
        self._trigger_debouncer: TriggerDebouncer = TriggerDebouncer(
            settings.min_capture_interval_ms
        )
        self._monitor_registry: MonitorRegistry = MonitorRegistry()
        self._trigger_bus_workers: set[str] = set()
        self._monitor_workers: dict[str, MonitorWorker] = {}
        self._accessibility_service: PairedCaptureService = PairedCaptureService()
        self._permission_state_machine: PermissionStateMachine = (
            PermissionStateMachine()
        )
        self._last_permission_snapshot: PermissionSnapshot = (
            self._permission_state_machine.snapshot()
        )
        self._screen_capture_status: str = "ok"
        self._screen_capture_reason: str = "capture_continuing"
        self._warned_blank_devices: set[str] = set()
        self._last_permission_poll_time: float = 0.0
        self._event_tap: MacOSEventTap | None = None
        self._app_switch_monitor: MacOSAppSwitchMonitor | None = None

        # Capture stats for periodic logging
        self._capture_counts: dict[CaptureTrigger, int] = {t: 0 for t in CaptureTrigger}
        self._latency_samples: list[float] = []
        self._debounced_count: int = 0
        self._last_stats_report_time: float = 0.0
        self._stats_report_interval_sec: int = settings.stats_interval_sec
        self._trigger_queue_peak: int = 0
        self._spool_peak: int = 0
        self._host_pid: int = os.getpid()
        self._runtime_started_at: str = utc_now_iso()
        self._stats_lock: threading.RLock = threading.RLock()

    def start(self) -> None:
        """Start the consumer thread."""
        if self.consumer is not None and not self.consumer.is_alive():
            self.consumer.start()
        if not self._spool_uploader.is_alive():
            self._spool_uploader.start()

    def _plaintext_forensic_log_path(self) -> Path:
        runtime_tag = self._runtime_started_at.replace(":", "-")
        return (
            settings.client_data_dir
            / "logs"
            / f"plaintext-forensic-{runtime_tag}-{self._host_pid}.jsonl"
        )

    def _write_plaintext_forensic_log(
        self,
        *,
        metadata: Mapping[str, object],
        capture_id: str | None,
        screenshot_path: str | None,
        spool_metadata_path: str | None,
        local_screenshot_path: str | None,
    ) -> None:
        if not settings.plaintext_forensic_log_enabled:
            return

        log_path = self._plaintext_forensic_log_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        payload = dict(metadata)
        payload.update(
            {
                "logged_at": utc_now_iso(),
                "capture_id": capture_id,
                "screenshot_path": screenshot_path,
                "spool_metadata_path": spool_metadata_path,
                "local_screenshot_path": local_screenshot_path,
            }
        )

        try:
            with open(log_path, "a", encoding="utf-8") as fh:
                if fh.tell() > 0:
                    fh.write("\n")
                separator_id = capture_id or "capture-pending"
                timestamp = str(metadata.get("timestamp", "unknown-timestamp"))
                capture_trigger = str(
                    metadata.get("capture_trigger", "unknown-trigger")
                )
                device_name = str(metadata.get("device_name", "unknown-device"))
                outcome = str(metadata.get("outcome", "unknown-outcome"))
                fh.write(
                    f"==== {separator_id} | {timestamp} | {capture_trigger} | {device_name} | {outcome} ====\n"
                )
                json.dump(payload, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
        except OSError as exc:
            logger.warning("Failed to write plaintext forensic log: %s", exc)

    def _send_heartbeat(
        self,
        *,
        include_permission: bool = True,
        include_trigger: bool = True,
    ) -> None:
        """Send heartbeat to server and sync runtime configuration.

        Phase 8.2: Periodically registers client activity and fetches current
        runtime settings (recording_enabled, upload_enabled, etc.) from server.
        """
        try:
            url = f"{settings.api_url.rstrip('/')}/heartbeat"
            payload: dict[str, object] = {}
            if include_permission:
                payload.update(
                    {
                        "capture_permission_status": self._last_permission_snapshot.status.value,
                        "capture_permission_reason": self._last_permission_snapshot.reason,
                        "last_permission_check_ts": self._last_permission_snapshot.last_check_ts,
                        "screen_capture_status": self._screen_capture_status,
                        "screen_capture_reason": self._screen_capture_reason,
                    }
                )
            if include_trigger:
                snapshot = self.trigger_channel_snapshot()
                payload.update(
                    {
                        "queue_depth": snapshot.queue_depth,
                        "queue_capacity": snapshot.queue_capacity,
                        "collapse_trigger_count": snapshot.collapse_trigger_count,
                        "overflow_drop_count": snapshot.overflow_drop_count,
                    }
                )

            response = requests.post(
                url,
                json=payload,
                **_build_request_kwargs(url),
            )
            response.raise_for_status()

            data = response.json()
            config = data.get("config", {})
            self.recording_enabled = config.get("recording_enabled", True)
            self.upload_enabled = config.get("upload_enabled", True)
            if settings.debug:
                logger.debug(
                    f"Heartbeat synced: recording={self.recording_enabled}, "
                    f"upload={self.upload_enabled}"
                )
        except requests.RequestException as e:
            logger.warning(f"Heartbeat failed (network): {e}")
        except Exception as e:
            logger.warning(f"Heartbeat failed: {e}")

    def _emit_trigger(self, event: TriggerEvent, *, now_ms: int | None = None) -> bool:
        event_time_ms = now_ms if now_ms is not None else int(time.time() * 1000)
        if not self._trigger_debouncer.should_fire(event.device_name, event_time_ms):
            return False
        return self._trigger_channel.put(event)

    def trigger_channel_snapshot(self) -> TriggerEventSnapshot:
        return self._trigger_channel.snapshot()

    def _get_debounced_count_and_reset(self) -> int:
        return self._trigger_debouncer.get_and_reset_debounced_count()

    def _report_stats(self) -> None:
        with self._stats_lock:
            total_captures = sum(self._capture_counts.values())
            if total_captures == 0:
                return

            latency_avg = (
                int(sum(self._latency_samples) / len(self._latency_samples))
                if self._latency_samples
                else 0
            )
            latency_max = (
                int(max(self._latency_samples)) if self._latency_samples else 0
            )
            idle_count = self._capture_counts[CaptureTrigger.IDLE]
            app_switch_count = self._capture_counts[CaptureTrigger.APP_SWITCH]
            click_count = self._capture_counts[CaptureTrigger.CLICK]
            manual_count = self._capture_counts[CaptureTrigger.MANUAL]
            trigger_queue_peak = self._trigger_queue_peak
            spool_peak = self._spool_peak

            for trigger in CaptureTrigger:
                self._capture_counts[trigger] = 0
            self._latency_samples.clear()
            self._trigger_queue_peak = 0
            self._spool_peak = 0

        debounced = self._get_debounced_count_and_reset()

        logger.info(
            "📊 Capture (%ds): idle=%d app_switch=%d click=%d manual=%d | debounced=%d | latency avg=%dms max=%dms | trigger_queue peak=%d spool peak=%d",
            self._stats_report_interval_sec,
            idle_count,
            app_switch_count,
            click_count,
            manual_count,
            debounced,
            latency_avg,
            latency_max,
            trigger_queue_peak,
            spool_peak,
        )

    def emit_manual_trigger(
        self,
        device_name: str,
        *,
        now_ms: int | None = None,
        event_ts: str | None = None,
    ) -> bool:
        return self._emit_trigger(
            TriggerEvent(
                capture_trigger=CaptureTrigger.MANUAL,
                device_name=device_name,
                event_ts=event_ts or utc_now_iso(),
            ),
            now_ms=now_ms,
        )

    def stop(self) -> None:
        """Stop the recorder and consumer thread gracefully."""
        self._stop_requested = True
        for worker in self._monitor_workers.values():
            worker.stop()
        for worker in self._monitor_workers.values():
            worker.join(timeout=1.0)
        self._monitor_workers.clear()
        if self._app_switch_monitor is not None:
            self._app_switch_monitor.stop()
        if self.consumer is not None:
            self.consumer.stop()
        self._spool_uploader.stop()
        if self.consumer is not None and self.consumer.is_alive():
            self.consumer.join(timeout=2.0)
        if self._spool_uploader.is_alive():
            self._spool_uploader.join(timeout=2.0)

    def _refresh_monitors(self) -> list[MonitorDescriptor]:
        previous_snapshot = self._monitor_registry.snapshot()
        monitors = list_monitors(settings.primary_monitor_only)
        self._monitor_registry.refresh(monitors)
        self._sync_trigger_bus_workers(monitors)
        if previous_snapshot != self._monitor_registry.snapshot():
            self._trigger_debouncer.reset_all()
            self._warned_blank_devices.clear()
        return monitors

    def _sync_trigger_bus_workers(self, monitors: list[MonitorDescriptor]) -> None:
        active_workers = {monitor.device_name for monitor in monitors}
        for worker_id in active_workers - self._trigger_bus_workers:
            worker_queue = self._trigger_bus.ensure_worker(worker_id)
            worker = MonitorWorker(
                worker_id=worker_id,
                intent_queue=worker_queue,
                process_intent=self._process_trigger_intent_for_monitor,
            )
            self._monitor_workers[worker_id] = worker
            worker.start()
        for worker_id in self._trigger_bus_workers - active_workers:
            worker = self._monitor_workers.pop(worker_id, None)
            if worker is not None:
                worker.stop()
                worker.join(timeout=1.0)
            self._trigger_bus.remove_worker(worker_id)
        self._trigger_bus_workers = active_workers

    def _capture_monitor(self, monitor: MonitorDescriptor) -> ImageArray:
        with mss.mss() as sct:
            return np.array(
                sct.grab(
                    {
                        "left": monitor.left,
                        "top": monitor.top,
                        "width": monitor.width,
                        "height": monitor.height,
                    }
                )
            )[:, :, [2, 1, 0]]

    def _record_capture_stats(
        self,
        *,
        trigger: CaptureTrigger,
        latency_ms: int,
        trigger_queue_depth: int,
        spool_depth: int,
    ) -> None:
        with self._stats_lock:
            self._capture_counts[trigger] += 1
            self._latency_samples.append(latency_ms)
            self._trigger_queue_peak = max(
                self._trigger_queue_peak, trigger_queue_depth
            )
            self._spool_peak = max(self._spool_peak, spool_depth)

    def _process_trigger_intent_for_monitor(
        self,
        worker: MonitorWorker,
        intent: TriggerIntent,
        dequeued_at: float,
    ) -> None:
        metadata: dict[str, object] | None = None
        worker_device_name = worker.worker_id
        monitor = self._monitor_registry.get(worker_device_name)
        if monitor is None:
            return

        event_device_hint = intent.event_device_hint or worker_device_name
        event = TriggerEvent(
            capture_trigger=intent.capture_trigger,
            device_name=event_device_hint,
            event_ts=intent.event_ts,
            active_app=intent.active_app,
            active_window=intent.active_window,
            payload=intent.payload,
        )

        try:
            screenshot = self._capture_monitors([monitor]).get(worker_device_name)
            if screenshot is None:
                raise RuntimeError(
                    f"screen_capture_monitor_unavailable:{worker_device_name}"
                )
        except Exception:
            self._set_screen_capture_status(
                ok=False,
                reason="screen_capture_failed",
            )
            logger.exception(
                "Failed to capture monitor screenshot for worker=%s",
                worker_device_name,
            )
            return

        try:
            image = Image.fromarray(screenshot)
            local_screenshot_path: str | None = None
            if settings.client_save_local_screenshots:
                file_tag = int(time.time())
                filepath = settings.client_screenshots_path / f"{file_tag}.webp"
                image.save(str(filepath), format="webp", lossless=True)
                local_screenshot_path = str(filepath)

            capture_snapshot_id = utc_now_iso()
            ax_root = get_frontmost_ax_root()
            focused_context_snapshot = FocusedContextSnapshot(
                snapshot_id=capture_snapshot_id,
                app_name=None,
                window_name=None,
            )
            raw_handoff = self._accessibility_service.collect_raw_handoff(
                final_device_name=worker_device_name,
                event_device_hint=event_device_hint,
                focused_context_snapshot=focused_context_snapshot,
                focused_context_snapshot_id_for_browser=capture_snapshot_id,
                permission_blocked=self._permission_state_machine.state
                in {
                    PermissionState.DENIED_OR_REVOKED,
                    PermissionState.RECOVERING,
                },
                ax_root=ax_root,
            )
            metadata = self._build_capture_metadata(
                event,
                context_active_app=intent.active_app or "",
                context_active_window=intent.active_window or "",
                raw_handoff=raw_handoff,
                host_pid=self._host_pid,
                runtime_started_at=self._runtime_started_at,
            )
            final_device_name = str(metadata["device_name"])
            outcome = metadata.get("outcome")
            content_hash_value = metadata.get("content_hash")
            content_hash = (
                content_hash_value if isinstance(content_hash_value, str) else None
            )
            permission_blocked = outcome == "permission_blocked"
            dedup_checked_at = time.time()
            capture_id: str | None = None
            if worker.should_skip_dedup(
                capture_trigger=intent.capture_trigger.value,
                final_device_name=final_device_name,
                content_hash=content_hash,
                now_epoch=dedup_checked_at,
                permission_blocked=permission_blocked,
            ):
                metadata["outcome"] = "dedup_skipped"

            if metadata["outcome"] != "dedup_skipped":
                metadata["capture_cycle_latency_ms"] = int(
                    (time.perf_counter() - dequeued_at) * 1000
                )
                metadata["_capture_cycle_started_at"] = dequeued_at
                capture_id = self._spool.enqueue(image, metadata)
                worker.record_successful_spool_write(
                    final_device_name=final_device_name,
                    content_hash=content_hash,
                    write_time_epoch=dedup_checked_at,
                )
            else:
                metadata["capture_cycle_latency_ms"] = int(
                    (time.perf_counter() - dequeued_at) * 1000
                )

            full_cycle_latency_ms = int((time.perf_counter() - dequeued_at) * 1000)
            metadata["capture_cycle_latency_ms"] = full_cycle_latency_ms
            spool_jpg_path = (
                str(settings.spool_path / f"{capture_id}.jpg")
                if capture_id is not None
                else None
            )
            spool_metadata_path = (
                str(settings.spool_path / f"{capture_id}.json")
                if capture_id is not None
                else None
            )
            self._write_plaintext_forensic_log(
                metadata=metadata,
                capture_id=capture_id,
                screenshot_path=spool_jpg_path,
                spool_metadata_path=spool_metadata_path,
                local_screenshot_path=local_screenshot_path,
            )
            self._set_screen_capture_status(
                ok=True,
                reason="capture_continuing",
            )
            self._warn_if_blank_frame(
                TriggerEvent(
                    capture_trigger=intent.capture_trigger,
                    device_name=final_device_name,
                    event_ts=intent.event_ts,
                ),
                screenshot,
            )

            latency_ms = int(metadata["capture_cycle_latency_ms"])
            trigger_queue_depth = self.trigger_channel_snapshot().queue_depth
            spool_depth = self._spool.count()
            bound_monitor = self._monitor_registry.get(final_device_name)
            monitor_info = (
                f"primary {bound_monitor.width}x{bound_monitor.height}"
                if bound_monitor and bound_monitor.is_primary
                else f"{bound_monitor.width}x{bound_monitor.height}"
                if bound_monitor
                else "unknown"
            )

            self._record_capture_stats(
                trigger=intent.capture_trigger,
                latency_ms=full_cycle_latency_ms,
                trigger_queue_depth=trigger_queue_depth,
                spool_depth=spool_depth,
            )

            logger.debug(
                "📸 trigger=%s device=%s app=%s window=%s latency_ms=%d trigger_queue=%d spool=%d monitor=%s",
                intent.capture_trigger.value,
                final_device_name,
                metadata.get("active_app", "Unknown"),
                metadata.get("active_window", "Unknown"),
                latency_ms,
                trigger_queue_depth,
                spool_depth,
                monitor_info,
            )
        except Exception:
            self._set_screen_capture_status(
                ok=False,
                reason="spool_write_failed",
            )
            failure_latency_ms = int((time.perf_counter() - dequeued_at) * 1000)
            if metadata is not None:
                failure_metadata = dict(metadata)
                failure_metadata["outcome"] = "spool_failed"
                failure_metadata["capture_cycle_latency_ms"] = failure_latency_ms
                self._write_plaintext_forensic_log(
                    metadata=failure_metadata,
                    capture_id=None,
                    screenshot_path=None,
                    spool_metadata_path=None,
                    local_screenshot_path=None,
                )
            logger.exception(
                "Failed to persist buffered screenshot outcome=spool_failed latency_ms=%d host_pid=%d runtime_started_at=%s",
                failure_latency_ms,
                self._host_pid,
                self._runtime_started_at,
            )

    def _primary_monitor(self) -> MonitorDescriptor | None:
        monitors = self._monitor_registry.list_monitors()
        if not monitors:
            return None
        for monitor in monitors:
            if monitor.is_primary:
                return monitor
        return monitors[0]

    def _start_event_sources(self) -> None:
        if self._event_tap is None:
            self._event_tap = MacOSEventTap(
                callback=self._handle_external_trigger,
                monitor_lookup=self._monitor_registry.match_point,
            )
            self._event_tap.start()
        if self._app_switch_monitor is None:
            self._app_switch_monitor = MacOSAppSwitchMonitor(
                callback=self._handle_external_trigger,
                monitor_provider=self._primary_monitor,
            )
            self._app_switch_monitor.start()

    def _handle_external_trigger(self, event: TriggerEvent) -> None:
        self._emit_trigger(event)

    def _poll_permissions(self, *, now_epoch: float) -> None:
        if (
            now_epoch - self._last_permission_poll_time
            < settings.permission_poll_interval_sec
        ):
            return
        check_result = detect_permissions()
        self._last_permission_snapshot = self._permission_state_machine.record_check(
            check_result
        )
        self._set_screen_capture_status(
            ok=check_result.screen_capture_ok,
            reason=check_result.screen_capture_reason,
        )
        self._last_permission_poll_time = now_epoch

    def _log_permission_degraded(self) -> None:
        if self._permission_state_machine.should_emit(time.time()):
            logger.warning(
                "Capture degraded due to permissions: status=%s reason=%s",
                self._last_permission_snapshot.status.value,
                self._last_permission_snapshot.reason,
            )

    def _set_screen_capture_status(self, *, ok: bool, reason: str) -> None:
        self._screen_capture_status = "ok" if ok else "degraded"
        self._screen_capture_reason = reason or (
            "capture_continuing" if ok else "screen_capture_failed"
        )

    def _wait_for_trigger(
        self,
        *,
        timeout_seconds: float,
        fallback_device_name: str,
    ) -> TriggerEvent:
        while True:
            try:
                return self._trigger_channel.get(timeout=timeout_seconds)
            except queue.Empty:
                idle_event = TriggerEvent(
                    capture_trigger=CaptureTrigger.IDLE,
                    device_name=fallback_device_name,
                    event_ts=utc_now_iso(),
                )
                _ = self._emit_trigger(idle_event)
                continue

    def _snapshot_active_context(self) -> tuple[str, str]:
        active_app = get_active_app_name() or get_frontmost_app_name()
        active_window = get_active_window_title_for_app(active_app)
        return active_app, active_window

    def _build_capture_metadata(
        self,
        event: TriggerEvent,
        *,
        context_active_app: str,
        context_active_window: str,
        raw_handoff: AccessibilityRawHandoff | None = None,
        capture_cycle_latency_ms: int | None = None,
        host_pid: int | None = None,
        runtime_started_at: str | None = None,
    ) -> dict[str, object]:
        if event.capture_trigger is CaptureTrigger.APP_SWITCH:
            active_app = event.active_app or context_active_app
            active_window = event.active_window or context_active_window
        else:
            active_app = context_active_app or event.active_app
            active_window = context_active_window or event.active_window

        app_name = active_app or None
        window_name = active_window or None
        browser_url = None
        device_name = event.device_name
        event_device_hint = event.device_name
        accessibility_text = ""
        content_hash = None
        outcome = None
        browser_url_classification = "browser_url_skipped"

        if raw_handoff is not None:
            app_name = raw_handoff.focused_context.app_name
            window_name = raw_handoff.focused_context.window_name
            browser_url = raw_handoff.focused_context.browser_url
            browser_url_classification = raw_handoff.browser_url_classification
            device_name = raw_handoff.final_device_name
            event_device_hint = raw_handoff.event_device_hint or event.device_name
            accessibility_text = raw_handoff.accessibility_text
            content_hash = raw_handoff.content_hash
            outcome = raw_handoff.outcome

        return {
            "timestamp": utc_now_iso(),
            "capture_trigger": event.capture_trigger.value,
            "device_name": device_name,
            "event_device_hint": event_device_hint,
            "event_ts": event.event_ts,
            "active_app": active_app or "Unknown App",
            "active_window": active_window or "Unknown Title",
            "app_name": app_name,
            "window_name": window_name,
            "browser_url": browser_url,
            "browser_url_classification": browser_url_classification,
            "focused": app_name is not None,
            "accessibility_text": accessibility_text,
            "content_hash": content_hash,
            "outcome": outcome,
            "capture_cycle_latency_ms": capture_cycle_latency_ms,
            "host_pid": host_pid,
            "runtime_started_at": runtime_started_at,
        }

    def _capture_monitors(
        self,
        monitors: list[MonitorDescriptor],
    ) -> dict[str, ImageArray]:
        captures: dict[str, ImageArray] = {}
        with mss.mss() as sct:
            for monitor in monitors:
                screenshot = np.array(
                    sct.grab(
                        {
                            "left": monitor.left,
                            "top": monitor.top,
                            "width": monitor.width,
                            "height": monitor.height,
                        }
                    )
                )[:, :, [2, 1, 0]]
                captures[monitor.device_name] = screenshot
        return captures

    def _warn_if_blank_frame(self, event: TriggerEvent, screenshot: ImageArray) -> None:
        if event.device_name in self._warned_blank_devices:
            return
        if float(np.mean(screenshot)) >= 1.0 or float(np.std(screenshot)) >= 1.0:
            return

        self._warned_blank_devices.add(event.device_name)
        self._set_screen_capture_status(ok=False, reason="blank_frame_detected")
        logger.warning(
            "Captured frames look blank for %s. permission_status=%s permission_reason=%s",
            event.device_name,
            self._last_permission_snapshot.status.value,
            self._last_permission_snapshot.reason,
        )

    def run_capture_loop(self) -> None:
        """Main capture loop. Runs until stop() is called.

        Captures screenshots, detects changes, and enqueues to buffer.
        Blocks only on disk I/O, never on network.
        """
        os.environ["TOKENIZERS_PARALLELISM"] = "false"

        # Start the consumer thread
        self.start()

        logger.info("🎥 Recorder started (Producer-Consumer mode)")
        logger.info(
            f"   Monitors: {'Primary only' if settings.primary_monitor_only else 'All'}"
        )

        monitors = self._refresh_monitors()
        self._monitor_registry.refresh(monitors)
        self._sync_trigger_bus_workers(monitors)
        self._start_event_sources()
        logger.info(f"   Tracking {len(monitors)} monitor(s)")

        while not self._stop_requested:
            # Phase 8.2: Sync runtime configuration every 5 seconds
            current_time = time.time()
            include_trigger = current_time - self._last_trigger_report_time >= 1
            include_permission = current_time - self._last_permission_report_time >= 5
            if include_trigger or include_permission:
                self._send_heartbeat(
                    include_permission=include_permission,
                    include_trigger=include_trigger,
                )
                self.last_heartbeat_time = current_time
                if include_trigger:
                    self._last_trigger_report_time = current_time
                if include_permission:
                    self._last_permission_report_time = current_time
            self._poll_permissions(now_epoch=current_time)

            # Periodic stats logging
            if (
                current_time - self._last_stats_report_time
                >= self._stats_report_interval_sec
            ):
                self._report_stats()
                self._last_stats_report_time = current_time

            # Phase 8.2: Rule 1 - Stop recording if recording_enabled=False
            if not self.recording_enabled:
                logger.info("⏸️  Recording paused (recording_enabled=False)")
                time.sleep(1)
                continue
            if self._permission_state_machine.is_degraded():
                self._log_permission_degraded()

            monitors = self._refresh_monitors()
            self._monitor_registry.refresh(monitors)
            self._sync_trigger_bus_workers(monitors)
            if not monitors:
                if settings.debug:
                    logger.debug("No monitors available for event-driven capture")
                time.sleep(1)
                continue

            fallback_device_name = monitors[0].device_name
            event = self._wait_for_trigger(
                timeout_seconds=settings.idle_capture_interval_ms / 1000.0,
                fallback_device_name=fallback_device_name,
            )

            self._trigger_bus.broadcast(
                TriggerIntent(
                    capture_trigger=event.capture_trigger,
                    event_ts=event.event_ts,
                    event_device_hint=event.device_name,
                    active_app=event.active_app,
                    active_window=event.active_window,
                    payload=event.payload,
                )
            )
            if not self.upload_enabled:
                logger.debug(
                    "Upload disabled: buffered locally (will upload when enabled)"
                )

        for worker in self._monitor_workers.values():
            worker.stop()
        for worker in self._monitor_workers.values():
            worker.join(timeout=1.0)


# Module-level singleton for backwards compatibility
_recorder: ScreenRecorder | None = None


def get_recorder() -> ScreenRecorder:
    """Get or create the global ScreenRecorder instance."""
    global _recorder
    if _recorder is None:
        _recorder = ScreenRecorder()
    return _recorder


def record_screenshots_thread() -> None:
    """Legacy function for backwards compatibility.

    Wraps the new ScreenRecorder class.
    """
    recorder = get_recorder()
    recorder.run_capture_loop()
