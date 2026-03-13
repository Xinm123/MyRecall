"""Runtime settings singleton for OpenRecall server."""

from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime, timezone


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_iso_utc_epoch(value: str) -> float | None:
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    elif "+" not in normalized and "-" not in normalized[10:]:
        normalized = f"{normalized}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.timestamp()


def _coerce_int(value: object) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if stripped:
            try:
                return int(stripped)
            except ValueError:
                return None
    return None


class RuntimeSettings:
    """Thread-safe singleton for runtime configuration.

    Manages feature toggles and client state:
    - Recording enable/disable
    - Upload enable/disable
    - AI processing enable/disable
    - UI AI visibility
    - Client heartbeat tracking
    """

    PERMISSION_TTL_SEC: int = 60
    TRIGGER_CHANNEL_WINDOW_SEC: int = 300

    def __init__(self):
        """Initialize runtime settings with defaults."""
        # Feature toggles
        self.recording_enabled: bool = True
        """Whether the client recorder is active."""

        self.upload_enabled: bool = True
        """Whether uploads from client to server are enabled."""

        self.ai_processing_enabled: bool = True
        """Whether AI processing pipeline is active."""

        self.ai_processing_version: int = 0
        """Monotonic version for AI processing toggle; used to cancel in-flight tasks."""

        self.ui_show_ai: bool = True
        """Whether AI results are shown in the UI."""

        # Client state tracking
        self.last_heartbeat: float = time.time()
        """Unix timestamp of last client heartbeat."""

        self.capture_permission_status: str = "granted"
        self.capture_permission_reason: str = "granted"
        self.last_permission_check_ts: str = _utc_now_iso()
        self.last_permission_snapshot_epoch: float = 0.0

        self.queue_depth: int = 0
        self.queue_capacity: int = 0
        self.collapse_trigger_count: int = 0
        self.overflow_drop_count: int = 0
        self._trigger_channel_samples: deque[dict[str, object]] = deque()

        self._lock: threading.RLock = threading.RLock()
        self._change_event: threading.Event = threading.Event()

    def to_dict(self) -> dict[str, object]:
        """Convert all settings to dictionary.

        Returns:
            Dictionary with all runtime settings fields.
        """
        with self._lock:
            return {
                "recording_enabled": self.recording_enabled,
                "upload_enabled": self.upload_enabled,
                "ai_processing_enabled": self.ai_processing_enabled,
                "ai_processing_version": self.ai_processing_version,
                "ui_show_ai": self.ui_show_ai,
                "last_heartbeat": self.last_heartbeat,
                "capture_permission_status": self.capture_permission_status,
                "capture_permission_reason": self.capture_permission_reason,
                "last_permission_check_ts": self.last_permission_check_ts,
                "queue_depth": self.queue_depth,
                "queue_capacity": self.queue_capacity,
                "collapse_trigger_count": self.collapse_trigger_count,
                "overflow_drop_count": self.overflow_drop_count,
            }

    def _prune_trigger_channel_samples(self, now_epoch: float) -> None:
        cutoff = now_epoch - self.TRIGGER_CHANNEL_WINDOW_SEC
        while self._trigger_channel_samples:
            sample_ts = self._trigger_channel_samples[0].get("ts")
            if not isinstance(sample_ts, (int, float)):
                self._trigger_channel_samples.popleft()
                continue
            if sample_ts >= cutoff:
                break
            self._trigger_channel_samples.popleft()

    def update_client_state(
        self, payload: dict[str, object], *, now_epoch: float | None = None
    ) -> None:
        now = time.time() if now_epoch is None else now_epoch
        with self._lock:
            self.last_heartbeat = now

            permission_status = payload.get("capture_permission_status")
            permission_reason = payload.get("capture_permission_reason")
            permission_check_ts = payload.get("last_permission_check_ts")
            if (
                permission_status is not None
                and permission_reason is not None
                and permission_check_ts is not None
            ):
                self.capture_permission_status = str(permission_status)
                self.capture_permission_reason = str(permission_reason)
                self.last_permission_check_ts = str(permission_check_ts)
                self.last_permission_snapshot_epoch = now

            trigger_fields = (
                _coerce_int(payload.get("queue_depth")),
                _coerce_int(payload.get("queue_capacity")),
                _coerce_int(payload.get("collapse_trigger_count")),
                _coerce_int(payload.get("overflow_drop_count")),
            )
            if all(value is not None for value in trigger_fields):
                queue_depth, queue_capacity, collapse_count, overflow_count = (
                    trigger_fields
                )
                assert queue_depth is not None
                assert queue_capacity is not None
                assert collapse_count is not None
                assert overflow_count is not None
                self.queue_depth = queue_depth
                self.queue_capacity = queue_capacity
                self.collapse_trigger_count = collapse_count
                self.overflow_drop_count = overflow_count
                self._trigger_channel_samples.append(
                    {
                        "ts": now,
                        "queue_depth": self.queue_depth,
                        "queue_capacity": self.queue_capacity,
                        "collapse_trigger_count": self.collapse_trigger_count,
                        "overflow_drop_count": self.overflow_drop_count,
                    }
                )
                self._prune_trigger_channel_samples(now)

    def get_permission_snapshot(
        self, *, now_epoch: float | None = None
    ) -> dict[str, object]:
        now = time.time() if now_epoch is None else now_epoch
        with self._lock:
            last_check_epoch = _parse_iso_utc_epoch(self.last_permission_check_ts)
            is_stale = (
                last_check_epoch is None
                or (now - last_check_epoch) > self.PERMISSION_TTL_SEC
            )
            reason = (
                "stale_permission_state" if is_stale else self.capture_permission_reason
            )
            return {
                "capture_permission_status": self.capture_permission_status,
                "capture_permission_reason": reason,
                "last_permission_check_ts": self.last_permission_check_ts,
                "is_stale": is_stale,
            }

    def get_trigger_channel_snapshot(
        self, *, now_epoch: float | None = None
    ) -> dict[str, int]:
        now = time.time() if now_epoch is None else now_epoch
        with self._lock:
            self._prune_trigger_channel_samples(now)
            return {
                "queue_depth": self.queue_depth,
                "queue_capacity": self.queue_capacity,
                "collapse_trigger_count": self.collapse_trigger_count,
                "overflow_drop_count": self.overflow_drop_count,
            }

    def get_trigger_channel_samples(
        self, *, now_epoch: float | None = None
    ) -> list[dict[str, object]]:
        now = time.time() if now_epoch is None else now_epoch
        with self._lock:
            self._prune_trigger_channel_samples(now)
            return list(self._trigger_channel_samples)

    def notify_change(self) -> None:
        self._change_event.set()

    def wait_for_change(self, timeout: float) -> None:
        self._change_event.wait(timeout)
        self._change_event.clear()


# Module-level singleton instance
runtime_settings = RuntimeSettings()
