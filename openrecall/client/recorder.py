import json
import logging
import os
import queue
import subprocess
import threading
import time
from dataclasses import asdict

import mss
import numpy as np
import requests
from PIL import Image
from numpy.typing import NDArray

from openrecall.client.events.base import (
    CaptureTrigger,
    LockFreeDebouncer,
    MonitorDescriptor,
    MonitorRegistry,
    RoutedCaptureTask,
    TriggerDebouncer,
    TriggerEvent,
    TriggerEventChannel,
    TriggerEventSnapshot,
    utc_now_iso,
)
from openrecall.client.events.macos import (
    get_active_app_monitor,
    get_all_windows_info,
    get_frontmost_app_name,
    list_monitors,
    MacOSAppSwitchMonitor,
    MacOSEventTap,
)
from openrecall.client.events.permissions import (
    PermissionCheckResult,
    PermissionSnapshot,
    PermissionStateMachine,
    detect_permissions,
)
from openrecall.client.accessibility import collect_for_capture
from openrecall.client.consumer import UploaderConsumer
from openrecall.client.hash_utils import (
    SimhashCache,
    compute_phash,
)
from openrecall.client.spool import SpoolQueue, get_spool
from openrecall.client.v3_uploader import SpoolUploader
from openrecall.shared.config import settings
from openrecall.shared.utils import (
    _build_request_kwargs,
    get_active_app_name,
    get_active_window_title_for_app,
)

logger = logging.getLogger(__name__)


def _get_api_url() -> str:
    """Get the API URL, preferring runtime settings over TOML config.

    Checks ClientSettingsStore first (for hot-reload), falls back to TOML settings.
    """
    from pathlib import Path
    from openrecall.client.database import ClientSettingsStore

    db_path = Path(settings.client_data_dir) / "client.db"
    store = ClientSettingsStore(db_path)

    # Try to get edge_base_url from database first (user may have updated it)
    db_url = store.get("edge_base_url", "").strip()
    if db_url:
        # edge_base_url is base URL like http://localhost:8083
        # Return the /api endpoint
        return f"{db_url.rstrip('/')}/api"

    # Fall back to TOML config
    return settings.api_url


class HeartbeatThread(threading.Thread):
    """Independent background thread that sends heartbeat to server.

    Runs its own 5-second timer loop, completely decoupled from the
    capture loop. Posts /heartbeat and updates recording_enabled /
    upload_enabled from the server response.

    Thread-safety: All reads from ScreenRecorder use snapshot copies
    (dict.copy(), set.copy(), TriggerChannel.snapshot()) to avoid
    holding locks on the main capture loop.
    """

    HEARTBEAT_INTERVAL_SEC = 5

    def __init__(
        self,
        recorder: "ScreenRecorder",
        stop_event: threading.Event,
        name: str = "HeartbeatThread",
    ) -> None:
        super().__init__(name=name, daemon=True)
        self.recorder = recorder
        self._stop_event = stop_event

    def run(self) -> None:
        """Send heartbeat every 5 seconds until stop event is set."""
        logger.info("heartbeat: HeartbeatThread started")

        while not self._stop_event.is_set():
            try:
                self._send_heartbeat()
            except Exception as e:
                logger.warning("HeartbeatThread: unexpected error: %s", e)

            # Wait for next interval or stop signal
            self._stop_event.wait(timeout=self.HEARTBEAT_INTERVAL_SEC)

        logger.info("heartbeat: HeartbeatThread stopped")

    def _send_heartbeat(self) -> None:
        """Build payload, POST to /heartbeat, update config from response."""
        url = f"{_get_api_url().rstrip('/')}/heartbeat"

        # Build snapshot of recorder state (thread-safe reads)
        payload: dict[str, object] = {}

        # Permission snapshot (frozen dataclass, safe to share)
        perm = self.recorder._last_permission_snapshot
        payload["capture_permission_status"] = perm.status.value
        payload["capture_permission_reason"] = perm.reason
        payload["last_permission_check_ts"] = perm.last_check_ts

        # Trigger channel snapshot (creates new object)
        trigger_snapshot = self.recorder.trigger_channel_snapshot()
        payload["queue_depth"] = trigger_snapshot.queue_depth
        payload["queue_capacity"] = trigger_snapshot.queue_capacity
        payload["collapse_trigger_count"] = trigger_snapshot.collapse_trigger_count
        payload["overflow_drop_count"] = trigger_snapshot.overflow_drop_count

        # Runtime info (copy-on-read for mutable containers)
        payload["capture_runtime"] = {
            "topology_epoch": self.recorder._topology_epoch,
            "primary_monitor_only": settings.primary_monitor_only,
            "active_monitors": sorted(self.recorder._enabled_monitor_devices.copy()),
            "last_capture_outcome": self.recorder._last_capture_outcome.copy(),
        }

        try:
            response = requests.post(
                url,
                json=payload,
                **_build_request_kwargs(url, timeout=10),
            )
            response.raise_for_status()

            data = response.json()
            config = data.get("config", {})
            # Write back to recorder (safe: next capture loop iteration sees new value)
            self.recorder.recording_enabled = config.get("recording_enabled", True)
            self.recorder.upload_enabled = config.get("upload_enabled", True)

            if settings.debug:
                logger.debug(
                    "heartbeat: synced recording=%s upload=%s",
                    self.recorder.recording_enabled,
                    self.recorder.upload_enabled,
                )
        except requests.RequestException as e:
            logger.warning("heartbeat: network error: %s", e)
        except Exception as e:
            logger.warning("heartbeat: failed: %s", e)


ImageArray = NDArray[np.uint8]



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


def _merge_accessibility_metadata(
    base_metadata: dict[str, str | int | None],
    decision: "openrecall.client.accessibility.types.AccessibilityDecision",  # noqa: F821
) -> dict[str, str | int | None]:
    """Merge accessibility decision into capture metadata for upload.

    For adopted decisions:
    - Add text, text_source='accessibility'
    - Add browser_url, content_hash, simhash from snapshot
    - Add nested accessibility payload

    For empty_text decisions:
    - Add browser_url only (snapshot exists but no text)

    For other non-adopted decisions:
    - Return base_metadata unchanged

    Args:
        base_metadata: The base capture metadata dictionary
        decision: The accessibility decision from collect_for_capture

    Returns:
        Updated metadata dictionary with accessibility fields if applicable
    """
    from openrecall.client.accessibility.types import (
        REASON_EMPTY_TEXT,
    )

    result = dict(base_metadata)

    if decision.adopted and decision.snapshot:
        # Canonical accessibility fields
        result["text"] = decision.snapshot.text_content
        result["text_source"] = "accessibility"
        result["browser_url"] = decision.snapshot.browser_url
        result["content_hash"] = decision.snapshot.content_hash
        result["simhash"] = decision.snapshot.simhash

        # Nested accessibility payload
        result["accessibility"] = {
            "text_content": decision.snapshot.text_content,
            "tree_json": json.dumps([asdict(n) for n in decision.snapshot.nodes]),
            "node_count": decision.snapshot.node_count,
            "truncated": decision.snapshot.truncated,
            "truncation_reason": decision.snapshot.truncation_reason,
            "max_depth_reached": decision.snapshot.max_depth_reached,
            "duration_ms": decision.snapshot.duration_ms,
        }
    elif decision.snapshot and decision.reason == REASON_EMPTY_TEXT:
        # Add browser_url for empty_text case (snapshot exists)
        result["browser_url"] = decision.snapshot.browser_url

    return result


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
        self._stop_event = threading.Event()

        # Phase 8.2: Runtime configuration state
        self.recording_enabled: bool = True
        self.upload_enabled: bool = True
        self._warned_capture_issue: bool = False
        self.consumer: UploaderConsumer | None = consumer
        self._spool: SpoolQueue = get_spool()
        self._spool_uploader: SpoolUploader = SpoolUploader()
        self._trigger_channel: TriggerEventChannel = TriggerEventChannel(
            settings.trigger_queue_capacity
        )
        # Debouncer for IDLE and APP_SWITCH events (used in _emit_trigger)
        self._trigger_debouncer: TriggerDebouncer = TriggerDebouncer(
            settings.trigger_debounce_ms
        )
        # Lock-free debouncer for CLICK events (used in CGEventTap callback)
        self._click_debouncer: LockFreeDebouncer = LockFreeDebouncer(
            settings.click_debounce_ms
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
        self._heartbeat_thread: HeartbeatThread | None = None

        # PHash-based visual similarity detection (Layer 2)
        # Note: Named _phash_cache (stores image perceptual hashes, not text simhash)
        self._phash_cache: "SimhashCache" = SimhashCache(
            cache_size_per_device=settings.simhash_cache_size_per_device,
            ttl_seconds=settings.simhash_ttl_seconds,
        )
        # Content exact dedup (Layer 1 before phash fuzzy dedup)
        self._last_content_hash: dict[str, int] = {}  # device_name -> content_hash

        # MSS instance reuse for screenshot capture
        self._mss_instance: mss.mss | None = None
        self._mss_monitors_signature: tuple | None = (
            None  # For hot-plug detection (hashable)
        )
        self._mss_last_check_time: float = 0.0  # Throttle signature checks

        # Capture stats for periodic logging
        self._capture_counts: dict[CaptureTrigger, int] = {t: 0 for t in CaptureTrigger}
        self._latency_samples: list[float] = []
        self._debounced_count: int = 0
        self._last_stats_report_time: float = 0.0
        self._stats_report_interval_sec: int = settings.stats_interval_sec
        self._trigger_queue_peak: int = 0
        self._spool_peak: int = 0

        self._topology_epoch: int = 0
        self._enabled_monitor_devices: set[str] = set()
        self._idle_deadlines: dict[str, float] = {}
        self._idle_deadlines_lock: threading.Lock = threading.Lock()
        self._idle_interval_seconds: float = settings.idle_capture_interval_ms / 1000.0
        self._monitor_last_context: dict[str, tuple[str, str, float]] = {}
        self._monitor_last_context_max_size: int = 100  # Bound memory growth
        self._last_capture_outcome: dict[str, object] = {
            "outcome": "init",
            "trigger": None,
            "target_device_name": None,
            "reason": "startup",
            "routing_topology_epoch": 0,
            "event_ts": None,
            "timestamp": utc_now_iso(),
        }
        # Max skip duration safety valve - track last successful capture per device
        self._last_successful_capture_time: dict[str, float] = {}
        self._pipeline_stall_count: int = 0  # Forced captures due to max_skip_duration

        # Accessibility timing for performance logging (Phase 3)
        self._last_ax_duration_ms: int = 0

    @property
    def _stop_requested(self) -> bool:
        """Backward-compatible property for stop flag."""
        return self._stop_event.is_set()

    def start(self) -> None:
        """Start the consumer thread and heartbeat thread."""
        if self.consumer is not None and not self.consumer.is_alive():
            self.consumer.start()
        if not self._spool_uploader.is_alive():
            self._spool_uploader.start()
        if self._heartbeat_thread is None:
            self._heartbeat_thread = HeartbeatThread(recorder=self, stop_event=self._stop_event)
            self._heartbeat_thread.start()

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
        device_name: str | None = None,
        *,
        now_ms: int | None = None,
        event_ts: str | None = None,
    ) -> bool:
        """Emit a manual capture trigger.

        Args:
            device_name: Target monitor name. None (default) uses primary monitor.
            now_ms: Optional timestamp in milliseconds.
            event_ts: Optional ISO timestamp string.

        Returns:
            True if trigger was accepted, False if debounced.
        """
        return self._emit_trigger(
            TriggerEvent(
                capture_trigger=CaptureTrigger.MANUAL,
                device_name=device_name or "",
                event_ts=event_ts or utc_now_iso(),
            ),
            now_ms=now_ms,
        )

    def stop(self) -> None:
        """Stop the recorder and consumer thread gracefully.

        Shutdown order:
        1. Set stop event (signals all threads to stop)
        2. Stop event sources (they may produce events)
        3. Drain trigger channel (unblocks waiting threads)
        4. Stop consumers
        5. Wait for threads with timeout
        """
        # Signal stop to all threads
        self._stop_event.set()

        # Stop event sources first (they produce events)
        if self._event_tap is not None:
            self._event_tap.stop()
        if self._app_switch_monitor is not None:
            self._app_switch_monitor.stop()

        # Drain trigger channel to unblock any waiting get()
        while True:
            try:
                self._trigger_channel.get_nowait()
            except queue.Empty:
                break

        # Stop consumers
        if self.consumer is not None:
            self.consumer.stop()
        self._spool_uploader.stop()

        # Wait for threads with timeout
        if self.consumer is not None and self.consumer.is_alive():
            self.consumer.join(timeout=2.0)
        if self._spool_uploader.is_alive():
            self._spool_uploader.join(timeout=2.0)

        # Stop heartbeat thread
        if self._heartbeat_thread is not None and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=2.0)

        # Clean up MSS instance
        if self._mss_instance is not None:
            try:
                self._mss_instance.close()
            except Exception:
                pass
            self._mss_instance = None
            self._mss_monitors_signature = None

    def _refresh_monitors(self) -> list[MonitorDescriptor]:
        monitors = list_monitors(settings.primary_monitor_only)
        self._refresh_routing_state(monitors)
        return monitors

    def _refresh_routing_state(
        self,
        monitors: list[MonitorDescriptor],
        *,
        now_epoch: float | None = None,
    ) -> None:
        now = time.time() if now_epoch is None else now_epoch
        previous_snapshot = self._monitor_registry.snapshot()
        self._monitor_registry.refresh(monitors)
        current_snapshot = self._monitor_registry.snapshot()

        if previous_snapshot != current_snapshot:
            self._topology_epoch += 1
            self._trigger_debouncer.reset_all()
            self._click_debouncer.reset_all()  # Also reset click debouncer on topology change
            self._warned_blank_devices.clear()

        previous_devices = set(self._enabled_monitor_devices)
        current_devices = {monitor.device_name for monitor in monitors}
        removed = previous_devices - current_devices
        added = current_devices - previous_devices

        for device_name in removed:
            self._idle_deadlines.pop(device_name, None)

        for device_name in added:
            self._idle_deadlines[device_name] = now + self._idle_interval_seconds

        for device_name in current_devices & previous_devices:
            self._idle_deadlines.setdefault(
                device_name, now + self._idle_interval_seconds
            )

        self._enabled_monitor_devices = current_devices

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
            # New single-layer architecture: pass trigger_channel and lock-free debouncer
            self._event_tap = MacOSEventTap(
                trigger_channel=self._trigger_channel,
                debouncer=self._click_debouncer,
                monitor_lookup=self._monitor_registry.match_point,
            )
            self._event_tap.start()
        if self._app_switch_monitor is None:
            # App switch still uses callback pattern (runs in regular Python thread)
            self._app_switch_monitor = MacOSAppSwitchMonitor(
                callback=self._handle_app_switch_trigger,
                monitor_lookup=self._monitor_registry.match_point,
            )
            self._app_switch_monitor.start()

    def _handle_app_switch_trigger(self, event: TriggerEvent) -> None:
        """Handle APP_SWITCH triggers from MacOSAppSwitchMonitor.

        Note: CLICK events now go directly to trigger_channel via MacOSEventTap.
        This callback only handles APP_SWITCH events.
        """
        if self._permission_state_machine.is_degraded():
            logger.debug(
                "Ignoring app switch trigger while permission is degraded: status=%s reason=%s",
                self._last_permission_snapshot.status.value,
                self._last_permission_snapshot.reason,
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
    ) -> TriggerEvent:
        while True:
            try:
                return self._trigger_channel.get(timeout=timeout_seconds)
            except queue.Empty:
                due_monitors = self._next_idle_due_monitors(now_epoch=time.time())
                if not due_monitors:
                    timeout_seconds = self._get_next_idle_timeout(now_epoch=time.time())
                    continue
                first_monitor = due_monitors[0]
                for device_name in due_monitors[1:]:
                    idle_event = TriggerEvent(
                        capture_trigger=CaptureTrigger.IDLE,
                        device_name=device_name,
                        event_ts=utc_now_iso(),
                    )
                    _ = self._emit_trigger(idle_event)
                return TriggerEvent(
                    capture_trigger=CaptureTrigger.IDLE,
                    device_name=first_monitor,
                    event_ts=utc_now_iso(),
                )

    def _next_idle_due_monitors(self, *, now_epoch: float) -> list[str]:
        due: list[tuple[str, float]] = []
        with self._idle_deadlines_lock:
            for device_name in sorted(self._enabled_monitor_devices):
                deadline = self._idle_deadlines.get(device_name)
                if deadline is None:
                    self._idle_deadlines[device_name] = (
                        now_epoch + self._idle_interval_seconds
                    )
                    continue
                if deadline <= now_epoch:
                    due.append((device_name, deadline))
        if not due:
            return []
        due.sort(key=lambda item: item[1])
        return [item[0] for item in due]

    def _get_next_idle_timeout(self, *, now_epoch: float) -> float:
        min_deadline: float | None = None
        with self._idle_deadlines_lock:
            for device_name in self._enabled_monitor_devices:
                deadline = self._idle_deadlines.get(device_name)
                if deadline is not None:
                    if min_deadline is None or deadline < min_deadline:
                        min_deadline = deadline
        if min_deadline is None:
            return self._idle_interval_seconds
        timeout = min_deadline - now_epoch
        return max(0.1, min(timeout, self._idle_interval_seconds))

    def _snapshot_active_context(self) -> tuple[str, str, str | None]:
        active_app = get_active_app_name() or get_frontmost_app_name()
        active_window = get_active_window_title_for_app(active_app)

        all_monitors = self._monitor_registry.list_monitors()
        active_monitor = get_active_app_monitor(all_monitors)
        active_monitor_device_name = (
            active_monitor.device_name if active_monitor else None
        )

        return active_app, active_window, active_monitor_device_name

    def _build_capture_metadata(
        self,
        routed_task: RoutedCaptureTask | TriggerEvent,
        *,
        context_active_app: str,
        context_active_window: str,
        context_active_monitor_device_name: str | None = None,
        focused_monitor_device_name: str | None = None,
    ) -> dict[str, str | int | None]:
        # Identify target monitor name
        target_device_name = (
            routed_task.device_name
            if isinstance(routed_task, TriggerEvent)
            else routed_task.target_device_name
        )

        # Rule: Assign app/window metadata only if the active app is actually on this monitor
        # or if we couldn't determine the monitor (fallback to focused monitor logic).
        app_is_on_target_monitor = True
        if (
            context_active_monitor_device_name is not None
            and context_active_monitor_device_name != target_device_name
        ):
            app_is_on_target_monitor = False

        app_name: str | None = None
        window_name: str | None = None

        if isinstance(routed_task, TriggerEvent):
            if routed_task.capture_trigger is CaptureTrigger.APP_SWITCH:
                # For APP_SWITCH, the event already carries the correct monitor context
                app_name = routed_task.active_app or context_active_app
                window_name = routed_task.active_window or context_active_window
            elif app_is_on_target_monitor:
                app_name = context_active_app or routed_task.active_app
                window_name = context_active_window or routed_task.active_window

            return {
                "timestamp": utc_now_iso(),
                "capture_trigger": routed_task.capture_trigger.value,
                "device_name": target_device_name,
                "event_ts": routed_task.event_ts,
                "active_app": app_name,
                "active_window": window_name,
                "app_name": app_name,
                "window_name": window_name,
            }

        # RoutedCaptureTask branch
        if (
            app_is_on_target_monitor
            and focused_monitor_device_name == target_device_name
        ):
            app_name = context_active_app or None
            window_name = context_active_window or None

        last_known_app: str | None = None
        last_known_window: str | None = None
        if (
            routed_task.capture_trigger is CaptureTrigger.IDLE
            and target_device_name in self._monitor_last_context
        ):
            last_ctx = self._monitor_last_context[target_device_name]
            if time.time() - last_ctx[2] < 300:
                last_known_app = last_ctx[0]
                last_known_window = last_ctx[1]

        return {
            "timestamp": utc_now_iso(),
            "capture_trigger": routed_task.capture_trigger.value,
            "device_name": target_device_name,
            "event_ts": routed_task.event_ts,
            "app_name": app_name,
            "window_name": window_name,
            "active_app": app_name,
            "active_window": window_name,
            "last_known_app": last_known_app,
            "last_known_window": last_known_window,
        }

    def _route_targets(
        self,
        *,
        capture_trigger: CaptureTrigger,
        target_device_names: list[str],
        event_ts: str,
        hints: dict[str, object],
    ) -> list[RoutedCaptureTask]:
        routed: list[RoutedCaptureTask] = []
        for target_device_name in target_device_names:
            if target_device_name not in self._enabled_monitor_devices:
                self._last_capture_outcome = {
                    "outcome": "routing_filtered",
                    "trigger": capture_trigger.value,
                    "target_device_name": target_device_name,
                    "reason": str(hints.get("reason") or "target_not_enabled"),
                    "routing_topology_epoch": self._topology_epoch,
                    "event_ts": event_ts,
                    "timestamp": utc_now_iso(),
                }
                logger.info(
                    "routing_filtered trigger=%s target_device=%s reason=%s",
                    capture_trigger.value,
                    target_device_name,
                    self._last_capture_outcome["reason"],
                )
                continue
            routed.append(
                RoutedCaptureTask(
                    capture_trigger=capture_trigger,
                    target_device_name=target_device_name,
                    routing_topology_epoch=self._topology_epoch,
                    event_ts=event_ts,
                    routing_hints=dict(hints),  # Copy to prevent external mutation
                )
            )
        return routed

    def _route_trigger(self, event: TriggerEvent) -> list[RoutedCaptureTask]:
        # Context reset on APP_SWITCH (aligns with screenpipe event_driven_capture.rs:381-386)
        # This ensures first frame after app switch is always captured
        if event.capture_trigger == CaptureTrigger.APP_SWITCH:
            if event.device_name:
                self._phash_cache.clear_device(event.device_name)
            self._last_content_hash.pop(event.device_name or "", None)

        if not self._enabled_monitor_devices:
            return []

        primary_monitor = self._primary_monitor()
        if primary_monitor is None:
            return []

        if event.capture_trigger is CaptureTrigger.CLICK:
            targets = [event.device_name]
        elif event.capture_trigger is CaptureTrigger.APP_SWITCH:
            targets = [event.device_name or primary_monitor.device_name]
        elif event.capture_trigger is CaptureTrigger.IDLE:
            targets = [event.device_name]
        else:
            targets = [event.device_name or primary_monitor.device_name]

        if event.capture_trigger is CaptureTrigger.IDLE:
            all_monitors = self._monitor_registry.list_monitors()
            active_app_monitor = get_active_app_monitor(all_monitors)
            focused_device_name = (
                active_app_monitor.device_name
                if active_app_monitor
                else primary_monitor.device_name
            )
        else:
            focused_device_name = event.device_name or primary_monitor.device_name

        return self._route_targets(
            capture_trigger=event.capture_trigger,
            target_device_names=[target for target in targets if target],
            event_ts=event.event_ts,
            hints={
                "active_app": event.active_app,
                "active_window": event.active_window,
                "focused_device_name": focused_device_name,
                "reason": "primary_monitor_only"
                if settings.primary_monitor_only
                else "multi_monitor_mode",
            },
        )

    def _validate_routed_task(self, routed_task: RoutedCaptureTask) -> bool:
        if routed_task.routing_topology_epoch != self._topology_epoch:
            self._last_capture_outcome = {
                "outcome": "stale_routed_task",
                "trigger": routed_task.capture_trigger.value,
                "target_device_name": routed_task.target_device_name,
                "reason": "topology_epoch_mismatch",
                "routing_topology_epoch": routed_task.routing_topology_epoch,
                "active_topology_epoch": self._topology_epoch,
                "event_ts": routed_task.event_ts,
                "timestamp": utc_now_iso(),
            }
            return False

        if routed_task.target_device_name not in self._enabled_monitor_devices:
            self._last_capture_outcome = {
                "outcome": "stale_routed_task",
                "trigger": routed_task.capture_trigger.value,
                "target_device_name": routed_task.target_device_name,
                "reason": "target_not_enabled",
                "routing_topology_epoch": routed_task.routing_topology_epoch,
                "active_topology_epoch": self._topology_epoch,
                "event_ts": routed_task.event_ts,
                "timestamp": utc_now_iso(),
            }
            return False

        return True

    def _capture_single_monitor(self, monitor: MonitorDescriptor) -> ImageArray:
        # Try window-level capture for fullscreen windows first
        fullscreen_window_id = self._detect_fullscreen_window_on_monitor(monitor)
        if fullscreen_window_id is not None:
            screenshot = self._capture_window_by_id(fullscreen_window_id)
            if screenshot is not None:
                return screenshot
            # Fall through to mss fallback if screencapture failed

        captures = self._capture_monitors([monitor])
        screenshot = captures.get(monitor.device_name)
        if screenshot is None:
            raise RuntimeError(
                f"capture missing for target monitor {monitor.device_name}"
            )
        return screenshot

    def _on_capture_completed(
        self, target_device_name: str, *, now_epoch: float
    ) -> None:
        with self._idle_deadlines_lock:
            if target_device_name in self._enabled_monitor_devices:
                self._idle_deadlines[target_device_name] = (
                    now_epoch + self._idle_interval_seconds
                )

    def _update_monitor_context(
        self,
        device_name: str,
        app_name: str,
        window_name: str,
    ) -> None:
        """Update monitor context with size limit protection.

        Args:
            device_name: Target monitor device name
            app_name: Active application name
            window_name: Active window title
        """
        # If over max size, remove oldest entry to bound memory
        if len(self._monitor_last_context) >= self._monitor_last_context_max_size:
            oldest_device = min(
                self._monitor_last_context.keys(),
                key=lambda d: self._monitor_last_context[d][2],
            )
            del self._monitor_last_context[oldest_device]

        self._monitor_last_context[device_name] = (
            app_name,
            window_name,
            time.time(),
        )

    def _get_mss_signature(self) -> tuple:
        """Get current monitor signature for hot-plug detection.

        Returns a hashable tuple for efficient comparison.
        """
        try:
            with mss.mss() as sct:
                return tuple((m["width"], m["height"]) for m in sct.monitors[1:])
        except Exception:
            return ()

    def _ensure_mss_instance(self) -> mss.mss:
        """Get or create MSS instance, with throttled hot-plug detection.

        Hot-plug detection is throttled to once per second to avoid
        creating temporary MSS instances on every screenshot.

        Returns:
            MSS instance ready for use.
        """
        current_time = time.time()

        # Throttle: only check signature every 1 second
        if self._mss_instance is not None:
            if current_time - self._mss_last_check_time < 1.0:
                return self._mss_instance

            self._mss_last_check_time = current_time
            current_signature = self._get_mss_signature()

            if current_signature == self._mss_monitors_signature:
                return self._mss_instance

            # Monitor changed, recreate
            logger.debug(
                "MSS instance recreating due to monitor change: %s -> %s",
                self._mss_monitors_signature,
                current_signature,
            )
            try:
                self._mss_instance.close()
            except Exception:
                pass
            self._mss_instance = mss.mss()
            self._mss_monitors_signature = current_signature
            return self._mss_instance

        # First time or after cleanup
        self._mss_last_check_time = current_time
        self._mss_instance = mss.mss()
        self._mss_monitors_signature = self._get_mss_signature()
        return self._mss_instance

    def _capture_monitors(
        self,
        monitors: list[MonitorDescriptor],
    ) -> dict[str, ImageArray]:
        captures: dict[str, ImageArray] = {}
        sct = self._ensure_mss_instance()
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

    def _capture_window_by_id(self, window_id: int) -> ImageArray | None:
        """Capture a specific window by its kCGWindowNumber using screencapture CLI.

        Falls back to None on any error (non-zero exit, timeout, permission denied).
        This enables automatic fallback to mss display capture in the caller.

        Args:
            window_id: The kCGWindowNumber of the target window.

        Returns:
            numpy array (BGR order) or None if capture failed.
        """
        tmp_path = "/tmp/myrecall_window_cap.jpg"
        try:
            subprocess.run(
                ["screencapture", "-l", str(window_id), "-x", "-t", "jpg", tmp_path],
                capture_output=True,
                timeout=5,
            )
            if not os.path.exists(tmp_path):
                logger.debug("screencapture produced no output for window_id=%d", window_id)
                return None
            img = Image.open(tmp_path)
            screenshot = np.array(img)[:, :, [2, 1, 0]]
            os.remove(tmp_path)
            return screenshot
        except Exception:
            logger.debug("Window capture failed for window_id=%d", window_id)
            return None

    SYSTEM_WINDOW_APPS: frozenset[str] = frozenset({
        "Dock",
        "Window Server",
        "ControlCenter",
        "SystemUIServer",
        "NotificationCenter",
        "loginwindow",
        "WindowManager",
        "Contexts",
        "Screenshot",
    })

    def _detect_fullscreen_window_on_monitor(
        self, monitor: MonitorDescriptor
    ) -> int | None:
        """Detect if there's a fullscreen window on the given monitor.

        Uses get_all_windows_info() to enumerate all windows across Spaces,
        then finds one whose bounds cover >=95% of the monitor.

        Returns:
            kCGWindowNumber (int) of the fullscreen window, or None.
        """
        try:
            windows = get_all_windows_info()
        except Exception:
            return None

        for window in windows:
            layer = window.get("kCGWindowLayer", 0)
            if layer != 0:
                continue

            owner_name = window.get("kCGWindowOwnerName", "")
            if owner_name in self.SYSTEM_WINDOW_APPS:
                continue

            bounds = window.get("kCGWindowBounds")
            if bounds is None:
                continue

            win_x = bounds.get("X", 0)
            win_y = bounds.get("Y", 0)
            win_w = bounds.get("Width", 0)
            win_h = bounds.get("Height", 0)

            # Fullscreen window: fills >=95% of monitor
            if (
                win_w >= monitor.width * 0.95
                and win_h >= monitor.height * 0.95
                and abs(win_x - monitor.left) <= 10
                and abs(win_y - monitor.top) <= 10
            ):
                return window.get("kCGWindowNumber")

        return None

    def _record_permission_issue(self, reason: str) -> None:
        self._last_permission_snapshot = self._permission_state_machine.record_check(
            PermissionCheckResult(ok=False, reason=reason)
        )

    def _warn_if_blank_frame(
        self, device_name: str, trigger: CaptureTrigger, screenshot: ImageArray
    ) -> None:
        """Warn if the captured frame appears blank (possible permission issue).

        Args:
            device_name: The name of the target device
            trigger: The capture trigger enum
            screenshot: The captured screenshot as numpy array
        """
        if not device_name:
            device_name = "unknown"

        if device_name in self._warned_blank_devices:
            return
        if float(np.mean(screenshot)) >= 1.0 or float(np.std(screenshot)) >= 1.0:
            return

        self._warned_blank_devices.add(device_name)
        logger.warning(
            "Captured frames look blank for %s. trigger=%s permission_status=%s permission_reason=%s",
            device_name,
            trigger.value,
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
            self._poll_permissions(now_epoch=time.time())

            # Periodic stats logging
            current_time = time.time()
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

            idle_timeout = self._get_next_idle_timeout(now_epoch=time.time())
            event = self._wait_for_trigger(
                timeout_seconds=idle_timeout,
            )

            routed_tasks = self._route_trigger(event)
            if not routed_tasks:
                continue

            routed_task = routed_tasks[0]

            # Global debounce: skip if last capture completed too recently
            # This prevents duplicate captures when multiple triggers fire
            # in quick succession (e.g., CLICK + APP_SWITCH within same second)
            # Aligns with screenpipe's event_driven_capture.rs debounce logic:
            #   can_capture() checks last_capture.elapsed() >= min_capture_interval
            #   mark_captured() updates last_capture AFTER capture completes
            last_capture_end = self._last_successful_capture_time.get(
                routed_task.target_device_name, 0.0
            )
            min_interval_sec = settings.capture_debounce_ms / 1000.0
            if last_capture_end > 0 and time.time() - last_capture_end < min_interval_sec:
                logger.debug(
                    "Debounced trigger: device=%s trigger=%s (last_capture=%.2fs ago < %.2fs)",
                    routed_task.target_device_name,
                    routed_task.capture_trigger.value,
                    time.time() - last_capture_end,
                    min_interval_sec,
                )
                continue

            if not self._validate_routed_task(routed_task):
                continue

            monitor = self._monitor_registry.get(routed_task.target_device_name)
            if monitor is None:
                self._monitor_registry.drop(routed_task.target_device_name)
                self._trigger_debouncer.reset_device(routed_task.target_device_name)
                self._last_capture_outcome = {
                    "outcome": "routing_filtered",
                    "trigger": routed_task.capture_trigger.value,
                    "target_device_name": routed_task.target_device_name,
                    "reason": "monitor_not_available",
                    "routing_topology_epoch": routed_task.routing_topology_epoch,
                    "event_ts": routed_task.event_ts,
                    "timestamp": utc_now_iso(),
                }
                continue

            try:
                capture_start_time = time.time()
                screenshot = self._capture_single_monitor(monitor)
                image = Image.fromarray(screenshot)
                if settings.client_save_local_screenshots:
                    file_tag = int(time.time())
                    filepath = settings.client_screenshots_path / f"{file_tag}.webp"
                    image.save(str(filepath), format="webp", lossless=True)

                # PHash-based similarity detection (P1-S2b+)
                phash_value: int | None = None
                should_drop_frame = False

                # Max skip duration safety valve
                # Force capture if too much time has passed since last successful capture
                current_time = time.time()
                last_capture = self._last_successful_capture_time.get(
                    routed_task.target_device_name
                )
                force_capture = (
                    last_capture is not None
                    and (current_time - last_capture) >= settings.max_skip_duration_sec
                )

                if settings.simhash_dedup_enabled:
                    # Determine if simhash should be checked based on trigger type
                    # IDLE and MANUAL always skip simhash (ensures periodic/user-requested capture)
                    if routed_task.capture_trigger in (
                        CaptureTrigger.IDLE,
                        CaptureTrigger.MANUAL,
                    ):
                        should_check_simhash = False
                    elif force_capture:
                        # Safety valve: skip simhash to guarantee frame capture
                        should_check_simhash = False
                        self._pipeline_stall_count += 1
                        time_since_last = (
                            current_time - last_capture if last_capture else 0.0
                        )
                        logger.debug(
                            "Force-capturing frame for device=%s after %.1fs of skips (max_skip_duration=%ds)",
                            routed_task.target_device_name,
                            time_since_last,
                            settings.max_skip_duration_sec,
                        )
                    elif routed_task.capture_trigger == CaptureTrigger.CLICK:
                        should_check_simhash = settings.simhash_enabled_for_click
                    elif routed_task.capture_trigger == CaptureTrigger.APP_SWITCH:
                        should_check_simhash = settings.simhash_enabled_for_app_switch
                    else:
                        should_check_simhash = False

                    if should_check_simhash:
                        logger.info("DEBUG: Computing phash for capture")
                        try:
                            # Compute PHash
                            phash_value = compute_phash(image)
                            logger.info(f"DEBUG: phash computed = {phash_value}")

                            # Check similarity against cache
                            is_similar_frame = self._phash_cache.is_similar_to_cache(
                                routed_task.target_device_name,
                                phash_value,
                                threshold=settings.simhash_dedup_threshold,
                            )

                            if is_similar_frame:
                                # Drop the frame - similar to cached frame (Layer 2: phash)
                                should_drop_frame = True
                                logger.info(
                                    "MRV3 phash_dropped device=%s threshold=%d trigger=%s phash=%s",
                                    routed_task.target_device_name,
                                    settings.simhash_dedup_threshold,
                                    routed_task.capture_trigger.value,
                                    phash_value,
                                )
                        except Exception as e:
                            # On error, don't drop - continue with enqueue
                            logger.warning(
                                "PHash computation failed for device=%s, continuing with enqueue: %s",
                                routed_task.target_device_name,
                                e,
                            )
                            phash_value = None

                if should_drop_frame:
                    # Clean up image resources before dropping frame
                    image.close()
                    del screenshot
                    del image

                    self._on_capture_completed(
                        routed_task.target_device_name,
                        now_epoch=time.time(),
                    )
                    self._last_capture_outcome = {
                        "outcome": "simhash_dropped",
                        "trigger": routed_task.capture_trigger.value,
                        "target_device_name": routed_task.target_device_name,
                        "reason": "similar_to_cached_frame",
                        "routing_topology_epoch": routed_task.routing_topology_epoch,
                        "event_ts": routed_task.event_ts,
                        "timestamp": utc_now_iso(),
                    }
                    # Frame dropped due to similarity - skip enqueue
                    continue

                context_active_app, context_active_window, context_active_monitor = (
                    self._snapshot_active_context()
                )

                # Accessibility decision stage (Phase 3/4)
                ax_start_ms = time.time() * 1000

                # Check if accessibility debug mode is enabled
                ax_debug_dir = None
                if os.environ.get("OPENRECALL_ACCESSIBILITY_DEBUG"):
                    ax_debug_dir = str(settings.client_data_dir / "ax_debug")

                ax_decision = collect_for_capture(
                    app_name=context_active_app,
                    window_name=context_active_window,
                    target_device_name=routed_task.target_device_name,
                    focused_device_name=str(
                        routed_task.routing_hints.get("focused_device_name") or ""
                    ),
                    captured_at=utc_now_iso(),
                    debug_dir=ax_debug_dir,
                )
                self._last_ax_duration_ms = int(time.time() * 1000 - ax_start_ms)

                # Build base metadata
                base_metadata = self._build_capture_metadata(
                    routed_task,
                    context_active_app=context_active_app,
                    context_active_window=context_active_window,
                    context_active_monitor_device_name=context_active_monitor,
                    focused_monitor_device_name=str(
                        routed_task.routing_hints.get("focused_device_name") or ""
                    ),
                )

                # Merge accessibility metadata if snapshot exists
                if ax_decision.snapshot is not None:
                    metadata = _merge_accessibility_metadata(base_metadata, ax_decision)
                else:
                    metadata = base_metadata

                # Layer 1: Content exact dedup (before simhash fuzzy dedup)
                # Aligns with screenpipe's three-layer dedup architecture
                content_hash_value = metadata.get("content_hash")
                if isinstance(content_hash_value, int) and content_hash_value != 0:
                    last_hash = self._last_content_hash.get(
                        routed_task.target_device_name
                    )
                    last_capture_time = self._last_successful_capture_time.get(
                        routed_task.target_device_name
                    )

                    # Check for exact content match (skip for IDLE/MANUAL triggers)
                    if (
                        last_hash is not None
                        and content_hash_value == last_hash
                        and routed_task.capture_trigger
                        not in (CaptureTrigger.IDLE, CaptureTrigger.MANUAL)
                        and last_capture_time is not None
                        and (time.time() - last_capture_time) < 30.0
                    ):
                        # Exact content match - skip capture (Layer 1: content_hash)
                        logger.info(
                            "MRV3 content_dedup_dropped device=%s trigger=%s content_hash=%s",
                            routed_task.target_device_name,
                            routed_task.capture_trigger.value,
                            content_hash_value,
                        )
                        # Clean up and continue to next task
                        try:
                            image.close()
                            del screenshot
                            del image
                        except Exception:
                            pass
                        self._on_capture_completed(
                            routed_task.target_device_name,
                            now_epoch=time.time(),
                        )
                        self._last_capture_outcome = {
                            "outcome": "content_dedup_dropped",
                            "trigger": routed_task.capture_trigger.value,
                            "target_device_name": routed_task.target_device_name,
                            "reason": "exact_content_match",
                            "routing_topology_epoch": routed_task.routing_topology_epoch,
                            "event_ts": routed_task.event_ts,
                            "timestamp": utc_now_iso(),
                        }
                        continue

                    # Update last content hash for future dedup
                    self._last_content_hash[routed_task.target_device_name] = (
                        content_hash_value
                    )
                    logger.debug(
                        "Content hash: device=%s current=%s last=%s match=%s trigger=%s",
                        routed_task.target_device_name,
                        content_hash_value,
                        last_hash,
                        content_hash_value == last_hash,
                        routed_task.capture_trigger.value,
                    )

                # Add PHash to metadata if computed (separate from text simhash)
                # simhash is set by accessibility path; phash is for visual similarity
                if phash_value is not None:
                    metadata["phash"] = phash_value

                self._spool.enqueue(image, metadata)

                # Update last successful capture time for max_skip_duration safety valve
                self._last_successful_capture_time[routed_task.target_device_name] = (
                    time.time()
                )

                # Update SimhashCache after successful enqueue
                if phash_value is not None:
                    self._phash_cache.add(
                        routed_task.target_device_name,
                        phash_value,
                        timestamp=time.time(),
                    )

                if routed_task.capture_trigger in (
                    CaptureTrigger.CLICK,
                    CaptureTrigger.APP_SWITCH,
                ):
                    app_name = metadata.get("app_name")
                    window_name = metadata.get("window_name")
                    if app_name and window_name:
                        self._update_monitor_context(
                            routed_task.target_device_name,
                            str(app_name),
                            str(window_name),
                        )

                self._warn_if_blank_frame(
                    routed_task.target_device_name,
                    routed_task.capture_trigger,
                    screenshot,
                )
                self._on_capture_completed(
                    routed_task.target_device_name,
                    now_epoch=time.time(),
                )
                self._last_capture_outcome = {
                    "outcome": "capture_completed",
                    "trigger": routed_task.capture_trigger.value,
                    "target_device_name": routed_task.target_device_name,
                    "reason": "ok",
                    "routing_topology_epoch": routed_task.routing_topology_epoch,
                    "event_ts": routed_task.event_ts,
                    "timestamp": metadata.get("timestamp"),
                }

                latency_ms = int((time.time() - capture_start_time) * 1000)
                trigger_queue_depth = self.trigger_channel_snapshot().queue_depth
                spool_depth = self._spool.count()
                monitor_info = (
                    f"primary {monitor.width}x{monitor.height}"
                    if monitor and monitor.is_primary
                    else f"{monitor.width}x{monitor.height}"
                    if monitor
                    else "unknown"
                )

                self._capture_counts[routed_task.capture_trigger] += 1
                self._latency_samples.append(latency_ms)
                self._trigger_queue_peak = max(
                    self._trigger_queue_peak, trigger_queue_depth
                )
                self._spool_peak = max(self._spool_peak, spool_depth)

                logger.debug(
                    "📸 trigger=%s device=%s app=%s window=%s latency_ms=%d trigger_queue=%d spool=%d monitor=%s",
                    routed_task.capture_trigger.value,
                    routed_task.target_device_name,
                    metadata.get("app_name"),
                    metadata.get("window_name"),
                    latency_ms,
                    trigger_queue_depth,
                    spool_depth,
                    monitor_info,
                )

                # Explicitly clean up image resources to prevent memory pressure
                # Done after all processing, logging, and stats collection
                try:
                    if "image" in locals():
                        image.close()
                    if "screenshot" in locals():
                        del screenshot
                    if "image" in locals():
                        del image
                except Exception as cleanup_error:
                    logger.debug("Error during resource cleanup: %s", cleanup_error)

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
