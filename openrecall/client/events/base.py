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
    def __init__(self) -> None:
        self._lock: threading.RLock = threading.RLock()
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

            self._monitors_by_device = new_mapping
            return dict(self._monitors_by_device)

    def snapshot(self) -> dict[str, str]:
        with self._lock:
            return {
                device_name: monitor.stable_id
                for device_name, monitor in self._monitors_by_device.items()
            }

    def list_monitors(self) -> list[MonitorDescriptor]:
        with self._lock:
            return list(self._monitors_by_device.values())

    def get(self, device_name: str) -> MonitorDescriptor | None:
        with self._lock:
            return self._monitors_by_device.get(device_name)

    def match_point(self, x: float, y: float) -> MonitorDescriptor | None:
        with self._lock:
            for monitor in self._monitors_by_device.values():
                if monitor.contains_point(x, y):
                    return monitor
        return None

    def drop(self, device_name: str) -> None:
        with self._lock:
            _ = self._monitors_by_device.pop(device_name, None)


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


class TriggerDebouncer:
    def __init__(self, min_interval_ms: int) -> None:
        self._min_interval_ms: int = min_interval_ms
        self._lock: threading.RLock = threading.RLock()
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


@dataclass(frozen=True)
class TriggerEventSnapshot:
    queue_depth: int
    queue_capacity: int
    collapse_trigger_count: int
    overflow_drop_count: int


class TriggerEventChannel:
    def __init__(self, capacity: int) -> None:
        self._queue: queue.Queue[TriggerEvent] = queue.Queue(maxsize=capacity)
        self._capacity: int = capacity
        self._collapse_trigger_count: int = 0
        self._overflow_drop_count: int = 0
        self._lock: threading.RLock = threading.RLock()

    def put(self, event: TriggerEvent) -> bool:
        with self._lock:
            try:
                self._queue.put_nowait(event)
                return True
            except queue.Full:
                pass

            try:
                _ = self._queue.get_nowait()
            except queue.Empty:
                self._overflow_drop_count += 1
                return False

            try:
                self._queue.put_nowait(event)
            except queue.Full:
                self._overflow_drop_count += 1
                return False

            self._collapse_trigger_count += 1
            return True

    def get(self, timeout: float) -> TriggerEvent:
        return self._queue.get(timeout=timeout)

    def get_nowait(self) -> TriggerEvent:
        return self._queue.get_nowait()

    def snapshot(self) -> TriggerEventSnapshot:
        with self._lock:
            return TriggerEventSnapshot(
                queue_depth=self._queue.qsize(),
                queue_capacity=self._capacity,
                collapse_trigger_count=self._collapse_trigger_count,
                overflow_drop_count=self._overflow_drop_count,
            )
