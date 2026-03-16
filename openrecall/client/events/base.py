from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import TypeAlias

logger = logging.getLogger(__name__)

EventPayload: TypeAlias = dict[str, object]


class CaptureTrigger(str, Enum):
    IDLE = "idle"
    APP_SWITCH = "app_switch"
    MANUAL = "manual"
    CLICK = "click"


def utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )


def normalize_device_name(stable_monitor_id: str | int) -> str:
    raw_value = str(stable_monitor_id).strip()
    if not raw_value:
        return "monitor_unknown"
    if raw_value.startswith("monitor_"):
        return raw_value
    return f"monitor_{raw_value}"


@dataclass(frozen=True)
class MonitorDescriptor:
    stable_id: str
    left: int
    top: int
    width: int
    height: int
    is_primary: bool = False
    source: str = "unknown"

    @property
    def device_name(self) -> str:
        return normalize_device_name(self.stable_id)

    def contains_point(self, x: float, y: float) -> bool:
        return (
            self.left <= x < self.left + self.width
            and self.top <= y < self.top + self.height
        )


class MonitorRegistry:
    """Thread-safe monitor registry with Copy-on-Write pattern.

    Uses immutable tuple snapshots for lock-free reads. Writes (refresh, drop)
    acquire a lock and create new immutable snapshots. Reads (match_point, get,
    list_monitors) access the snapshot without any locking.

    This is critical for the CGEventTap processor thread which calls match_point()
    frequently - no lock contention with the main thread.
    """

    def __init__(self) -> None:
        self._lock: threading.Lock = threading.Lock()  # Simple Lock, not RLock
        # Immutable snapshot - updated atomically on write
        self._monitors_snapshot: tuple[MonitorDescriptor, ...] = ()
        # Mapping for dict-like operations (also immutable)
        self._monitors_by_device: dict[str, MonitorDescriptor] = {}

    def refresh(
        self, monitors: list[MonitorDescriptor]
    ) -> dict[str, MonitorDescriptor]:
        new_mapping = {monitor.device_name: monitor for monitor in monitors}
        with self._lock:
            previous_devices = set(self._monitors_by_device)
            current_devices = set(new_mapping)
            removed = sorted(previous_devices - current_devices)
            added = sorted(current_devices - previous_devices)

            for device_name in removed:
                logger.info(
                    "device_name binding removed: %s; rebuilding partition state",
                    device_name,
                )
            for device_name in added:
                logger.info(
                    "device_name binding added: %s; rebuilding partition state",
                    device_name,
                )

            # Atomically update both snapshot and mapping
            self._monitors_snapshot = tuple(monitors)
            self._monitors_by_device = new_mapping
            return dict(self._monitors_by_device)

    def snapshot(self) -> dict[str, str]:
        # Read from immutable snapshot - no lock needed
        return {
            monitor.device_name: monitor.stable_id
            for monitor in self._monitors_snapshot
        }

    def list_monitors(self) -> list[MonitorDescriptor]:
        # Read from immutable snapshot - no lock needed
        return list(self._monitors_snapshot)

    def get(self, device_name: str) -> MonitorDescriptor | None:
        # Read from immutable mapping - no lock needed
        return self._monitors_by_device.get(device_name)

    def match_point(self, x: float, y: float) -> MonitorDescriptor | None:
        """Lock-free point matching using immutable snapshot.

        This is the hot path called from the processor thread.
        """
        for monitor in self._monitors_snapshot:
            if monitor.contains_point(x, y):
                return monitor
        return None

    def drop(self, device_name: str) -> None:
        with self._lock:
            if device_name not in self._monitors_by_device:
                return
            new_mapping = dict(self._monitors_by_device)
            del new_mapping[device_name]
            self._monitors_by_device = new_mapping
            self._monitors_snapshot = tuple(new_mapping.values())


@dataclass(frozen=True)
class TriggerEvent:
    capture_trigger: CaptureTrigger
    device_name: str
    event_ts: str
    active_app: str | None = None
    active_window: str | None = None
    payload: EventPayload | None = None

    def with_context(
        self,
        *,
        active_app: str | None,
        active_window: str | None,
    ) -> "TriggerEvent":
        return TriggerEvent(
            capture_trigger=self.capture_trigger,
            device_name=self.device_name,
            event_ts=self.event_ts,
            active_app=active_app,
            active_window=active_window,
            payload=self.payload,
        )


@dataclass(frozen=True)
class RoutedCaptureTask:
    capture_trigger: CaptureTrigger
    target_device_name: str
    routing_topology_epoch: int
    event_ts: str
    routing_hints: EventPayload


class TriggerDebouncer:
    """Per-device debounce gate for capture triggers.

    Uses simple Lock (not RLock) since no re-entrant locking is needed.
    """

    def __init__(self, min_interval_ms: int) -> None:
        self._min_interval_ms: int = min_interval_ms
        self._lock: threading.Lock = threading.Lock()  # Simple Lock
        self._last_fire_ms: dict[str, int] = {}
        self._debounced_count: int = 0

    def should_fire(self, device_name: str, now_ms: int) -> bool:
        with self._lock:
            last_fire_ms = self._last_fire_ms.get(device_name)
            if last_fire_ms is None or now_ms - last_fire_ms >= self._min_interval_ms:
                self._last_fire_ms[device_name] = now_ms
                return True
            self._debounced_count += 1
            return False

    def reset_device(self, device_name: str) -> None:
        with self._lock:
            _ = self._last_fire_ms.pop(device_name, None)

    def reset_all(self) -> None:
        with self._lock:
            self._last_fire_ms.clear()

    def get_and_reset_debounced_count(self) -> int:
        with self._lock:
            count = self._debounced_count
            self._debounced_count = 0
            return count


class LockFreeDebouncer:
    """Lock-free debouncer for use in CGEventTap callback.

    Designed for the high-priority CGEventTap thread where blocking on locks
    would cause system lag. Uses atomic dict operations and accepts minor
    race conditions (worst case: an extra event fires or one is debounced).

    IMPORTANT: Only use should_fire() from the callback. Use reset_* methods
    from normal Python threads (they use locks for consistency).
    """

    def __init__(self, min_interval_ms: int) -> None:
        self._min_interval_ms: int = min_interval_ms
        # No lock for should_fire - relies on GIL atomicity for dict operations
        self._last_fire_ms: dict[str, int] = {}
        self._lock: threading.Lock = threading.Lock()  # Only for reset/get operations

    def should_fire(self, device_name: str, now_ms: int) -> bool:
        """Lock-free check - safe to call from CGEventTap callback.

        Uses atomic dict operations under GIL. Accepts minor race conditions:
        - Two threads might both pass the check simultaneously (rare)
        - This is acceptable for debouncing (just means an extra event)
        """
        last_fire_ms = self._last_fire_ms.get(device_name, 0)
        if now_ms - last_fire_ms >= self._min_interval_ms:
            # Atomic dict assignment under GIL
            self._last_fire_ms[device_name] = now_ms
            return True
        return False

    def reset_device(self, device_name: str) -> None:
        """Thread-safe reset - call from normal Python thread."""
        with self._lock:
            self._last_fire_ms.pop(device_name, None)

    def reset_all(self) -> None:
        """Thread-safe reset - call from normal Python thread."""
        with self._lock:
            self._last_fire_ms.clear()

    def update_interval(self, min_interval_ms: int) -> None:
        """Update the minimum interval."""
        self._min_interval_ms = min_interval_ms


@dataclass(frozen=True)
class TriggerEventSnapshot:
    queue_depth: int
    queue_capacity: int
    collapse_trigger_count: int
    overflow_drop_count: int


class TriggerEventChannel:
    """Thread-safe channel for trigger events.

    Uses queue.Queue which is already thread-safe for put/get operations.
    A simple Lock protects only the stats counters.
    """

    def __init__(self, capacity: int) -> None:
        self._queue: queue.Queue[TriggerEvent] = queue.Queue(maxsize=capacity)
        self._capacity: int = capacity
        self._collapse_trigger_count: int = 0
        self._overflow_drop_count: int = 0
        self._stats_lock: threading.Lock = threading.Lock()

    def put(self, event: TriggerEvent) -> bool:
        """Put event into channel, non-blocking with collapse on full.

        Returns True if event was queued, False if dropped.
        """
        try:
            self._queue.put_nowait(event)
            return True
        except queue.Full:
            pass

        # Queue is full - try to collapse (drop oldest, add newest)
        try:
            _ = self._queue.get_nowait()
        except queue.Empty:
            # Queue emptied between put_nowait and get_nowait - rare race
            with self._stats_lock:
                self._overflow_drop_count += 1
            return False

        try:
            self._queue.put_nowait(event)
        except queue.Full:
            # Queue filled again - extremely rare race
            with self._stats_lock:
                self._overflow_drop_count += 1
            return False

        with self._stats_lock:
            self._collapse_trigger_count += 1
        return True

    def get(self, timeout: float) -> TriggerEvent:
        return self._queue.get(timeout=timeout)

    def get_nowait(self) -> TriggerEvent:
        return self._queue.get_nowait()

    def snapshot(self) -> TriggerEventSnapshot:
        with self._stats_lock:
            return TriggerEventSnapshot(
                queue_depth=self._queue.qsize(),
                queue_capacity=self._capacity,
                collapse_trigger_count=self._collapse_trigger_count,
                overflow_drop_count=self._overflow_drop_count,
            )
