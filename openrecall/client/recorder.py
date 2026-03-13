import logging
import os
import queue
import time
from collections.abc import Callable

import mss
import numpy as np
import requests
from PIL import Image
from numpy.typing import NDArray

from openrecall.client.events.base import (
    CaptureTrigger,
    MonitorDescriptor,
    MonitorRegistry,
    TriggerDebouncer,
    TriggerEvent,
    TriggerEventChannel,
    TriggerEventSnapshot,
    utc_now_iso,
)
from openrecall.client.events.macos import get_frontmost_app_name, list_monitors
from openrecall.client.events.macos import MacOSAppSwitchMonitor, MacOSEventTap
from openrecall.client.events.permissions import (
    PermissionCheckResult,
    PermissionSnapshot,
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
        self._trigger_debouncer: TriggerDebouncer = TriggerDebouncer(
            settings.min_capture_interval_ms
        )
        self._monitor_registry: MonitorRegistry = MonitorRegistry()
        self._permission_state_machine: PermissionStateMachine = (
            PermissionStateMachine()
        )
        self._last_permission_snapshot: PermissionSnapshot = (
            self._permission_state_machine.snapshot()
        )
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

    def start(self) -> None:
        """Start the consumer thread."""
        if self.consumer is not None and not self.consumer.is_alive():
            self.consumer.start()
        if not self._spool_uploader.is_alive():
            self._spool_uploader.start()

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
        total_captures = sum(self._capture_counts.values())
        if total_captures == 0:
            return

        debounced = self._get_debounced_count_and_reset()
        latency_avg = (
            int(sum(self._latency_samples) / len(self._latency_samples))
            if self._latency_samples
            else 0
        )
        latency_max = int(max(self._latency_samples)) if self._latency_samples else 0

        logger.info(
            "📊 Capture (%ds): idle=%d app_switch=%d click=%d manual=%d | debounced=%d | latency avg=%dms max=%dms | trigger_queue peak=%d spool peak=%d",
            self._stats_report_interval_sec,
            self._capture_counts[CaptureTrigger.IDLE],
            self._capture_counts[CaptureTrigger.APP_SWITCH],
            self._capture_counts[CaptureTrigger.CLICK],
            self._capture_counts[CaptureTrigger.MANUAL],
            debounced,
            latency_avg,
            latency_max,
            self._trigger_queue_peak,
            self._spool_peak,
        )

        # Reset stats
        for t in CaptureTrigger:
            self._capture_counts[t] = 0
        self._latency_samples.clear()
        self._trigger_queue_peak = 0
        self._spool_peak = 0

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
        if previous_snapshot != self._monitor_registry.snapshot():
            self._trigger_debouncer.reset_all()
            self._warned_blank_devices.clear()
        return monitors

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
        if self._permission_state_machine.is_degraded():
            logger.debug(
                "Ignoring external trigger while permission is degraded: status=%s reason=%s trigger=%s",
                self._last_permission_snapshot.status.value,
                self._last_permission_snapshot.reason,
                event.capture_trigger.value,
            )
            return
        self._emit_trigger(event)

    def _poll_permissions(self, *, now_epoch: float) -> None:
        if (
            now_epoch - self._last_permission_poll_time
            < settings.permission_poll_interval_sec
        ):
            return
        self._last_permission_snapshot = self._permission_state_machine.record_check(
            detect_permissions()
        )
        self._last_permission_poll_time = now_epoch

    def _degraded_sleep(self) -> None:
        if self._permission_state_machine.should_emit(time.time()):
            logger.warning(
                "Capture degraded due to permissions: status=%s reason=%s",
                self._last_permission_snapshot.status.value,
                self._last_permission_snapshot.reason,
            )
        time.sleep(1)

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
    ) -> dict[str, str]:
        if event.capture_trigger is CaptureTrigger.APP_SWITCH:
            active_app = event.active_app or context_active_app
            active_window = event.active_window or context_active_window
        else:
            active_app = context_active_app or event.active_app
            active_window = context_active_window or event.active_window
        return {
            "timestamp": utc_now_iso(),
            "capture_trigger": event.capture_trigger.value,
            "device_name": event.device_name,
            "event_ts": event.event_ts,
            "active_app": active_app or "Unknown App",
            "active_window": active_window or "Unknown Title",
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

    def _record_permission_issue(self, reason: str) -> None:
        self._last_permission_snapshot = self._permission_state_machine.record_check(
            PermissionCheckResult(ok=False, reason=reason)
        )

    def _warn_if_blank_frame(self, event: TriggerEvent, screenshot: ImageArray) -> None:
        if event.device_name in self._warned_blank_devices:
            return
        if float(np.mean(screenshot)) >= 1.0 or float(np.std(screenshot)) >= 1.0:
            return

        self._warned_blank_devices.add(event.device_name)
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
                self._degraded_sleep()
                continue

            monitors = self._refresh_monitors()
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

            screenshots = self._capture_monitors(monitors)
            screenshot = screenshots.get(event.device_name)
            if screenshot is None:
                logger.warning(
                    "Skipping trigger %s because device_name %s is unavailable",
                    event.capture_trigger.value,
                    event.device_name,
                )
                self._monitor_registry.drop(event.device_name)
                self._trigger_debouncer.reset_device(event.device_name)
                continue

            try:
                capture_start_time = time.time()
                image = Image.fromarray(screenshot)
                if settings.client_save_local_screenshots:
                    file_tag = int(time.time())
                    filepath = settings.client_screenshots_path / f"{file_tag}.webp"
                    image.save(str(filepath), format="webp", lossless=True)

                context_active_app, context_active_window = (
                    self._snapshot_active_context()
                )
                metadata = self._build_capture_metadata(
                    event,
                    context_active_app=context_active_app,
                    context_active_window=context_active_window,
                )
                self._spool.enqueue(image, metadata)
                self._warn_if_blank_frame(event, screenshot)

                latency_ms = int((time.time() - capture_start_time) * 1000)
                trigger_queue_depth = self.trigger_channel_snapshot().queue_depth
                spool_depth = self._spool.count()
                monitor = self._monitor_registry.get(event.device_name)
                monitor_info = (
                    f"primary {monitor.width}x{monitor.height}"
                    if monitor and monitor.is_primary
                    else f"{monitor.width}x{monitor.height}"
                    if monitor
                    else "unknown"
                )

                self._capture_counts[event.capture_trigger] += 1
                self._latency_samples.append(latency_ms)
                self._trigger_queue_peak = max(
                    self._trigger_queue_peak, trigger_queue_depth
                )
                self._spool_peak = max(self._spool_peak, spool_depth)

                logger.debug(
                    "📸 trigger=%s device=%s app=%s window=%s latency_ms=%d trigger_queue=%d spool=%d monitor=%s",
                    event.capture_trigger.value,
                    event.device_name,
                    metadata.get("active_app", "Unknown"),
                    metadata.get("active_window", "Unknown"),
                    latency_ms,
                    trigger_queue_depth,
                    spool_depth,
                    monitor_info,
                )

                if not self.upload_enabled:
                    logger.debug(
                        "Upload disabled: buffered locally (will upload when enabled)"
                    )
            except Exception:
                logger.exception("Failed to persist buffered screenshot")


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
