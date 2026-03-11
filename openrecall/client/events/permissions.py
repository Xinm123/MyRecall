from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from enum import Enum

from openrecall.client.events.base import utc_now_iso
from openrecall.shared.config import settings

logger = logging.getLogger(__name__)

try:
    import ApplicationServices
except ImportError:
    ApplicationServices = None

try:
    import Quartz
except ImportError:
    Quartz = None


REQUIRED_CONSECUTIVE_FAILURES = 2
REQUIRED_CONSECUTIVE_SUCCESSES = 3
EMIT_COOLDOWN_SEC = 300


class PermissionState(str, Enum):
    GRANTED = "granted"
    TRANSIENT_FAILURE = "transient_failure"
    DENIED_OR_REVOKED = "denied_or_revoked"
    RECOVERING = "recovering"


@dataclass(frozen=True)
class PermissionCheckResult:
    ok: bool
    reason: str
    checked_at: str | None = None


@dataclass(frozen=True)
class PermissionSnapshot:
    status: PermissionState
    reason: str
    last_check_ts: str


class PermissionStateMachine:
    """Permission state owned by the ScreenRecorder capture-loop thread.

    External trigger callbacks must communicate through the trigger channel and
    must not access this state machine directly.
    """

    def __init__(self) -> None:
        self._state: PermissionState = PermissionState.GRANTED
        self._consecutive_failures: int = 0
        self._consecutive_successes: int = 0
        self._last_check_ts: str = utc_now_iso()
        self._reason: str = "granted"
        self._last_emit_epoch: float = 0.0

    @property
    def state(self) -> PermissionState:
        return self._state

    def snapshot(self) -> PermissionSnapshot:
        return PermissionSnapshot(
            status=self._state,
            reason=self._reason,
            last_check_ts=self._last_check_ts,
        )

    def is_degraded(self) -> bool:
        return self._state in {
            PermissionState.DENIED_OR_REVOKED,
            PermissionState.RECOVERING,
        }

    def should_emit(self, now_epoch: float) -> bool:
        if now_epoch - self._last_emit_epoch < EMIT_COOLDOWN_SEC:
            return False
        self._last_emit_epoch = now_epoch
        return True

    def record_check(self, result: PermissionCheckResult) -> PermissionSnapshot:
        checked_at = result.checked_at or utc_now_iso()
        self._last_check_ts = checked_at
        self._reason = result.reason

        if result.ok:
            self._consecutive_failures = 0
            self._consecutive_successes += 1
            if self._state is PermissionState.DENIED_OR_REVOKED:
                self._state = PermissionState.RECOVERING
                self._consecutive_successes = 1
            elif self._state is PermissionState.TRANSIENT_FAILURE:
                self._state = PermissionState.GRANTED
            elif self._state is PermissionState.RECOVERING:
                if self._consecutive_successes >= REQUIRED_CONSECUTIVE_SUCCESSES:
                    self._state = PermissionState.GRANTED
                else:
                    self._state = PermissionState.RECOVERING
            else:
                self._state = PermissionState.GRANTED
        else:
            self._consecutive_successes = 0
            self._consecutive_failures += 1
            if self._consecutive_failures >= REQUIRED_CONSECUTIVE_FAILURES:
                self._state = PermissionState.DENIED_OR_REVOKED
            else:
                self._state = PermissionState.TRANSIENT_FAILURE

        return self.snapshot()


def detect_permissions() -> PermissionCheckResult:
    # Dev mode bypass for Terminal TCC identity inheritance issue
    # When running from Terminal, the process inherits Terminal's TCC identity
    # which may not have Accessibility permission granted
    if os.environ.get("OPENRECALL_SKIP_PERMISSION_CHECK", "").lower() == "true":
        if settings.debug:
            logger.debug(
                "DEV MODE: Permission bypass active (OPENRECALL_SKIP_PERMISSION_CHECK=true)"
            )
        return PermissionCheckResult(ok=True, reason="dev_mode_bypass")

    if ApplicationServices is None or Quartz is None:
        return PermissionCheckResult(ok=True, reason="permission_check_unavailable")

    ax_is_process_trusted = getattr(ApplicationServices, "AXIsProcessTrusted", None)
    screen_capture_access = getattr(Quartz, "CGPreflightScreenCaptureAccess", None)
    if ax_is_process_trusted is None or screen_capture_access is None:
        return PermissionCheckResult(ok=True, reason="permission_check_unavailable")

    accessibility_ok = bool(ax_is_process_trusted())
    screen_capture_ok = bool(screen_capture_access())

    if accessibility_ok and screen_capture_ok:
        return PermissionCheckResult(ok=True, reason="granted")
    if not accessibility_ok:
        return PermissionCheckResult(ok=False, reason="accessibility_denied")
    return PermissionCheckResult(ok=False, reason="screen_recording_denied")


def permission_poll_interval_sec() -> int:
    return settings.permission_poll_interval_sec
