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
        self._state: PermissionState = PermissionState.TRANSIENT_FAILURE
        self._consecutive_failures: int = 0
        self._consecutive_successes: int = 0
        self._last_check_ts: str = utc_now_iso()
        self._reason: str = "startup_not_determined"
        self._last_emit_epoch: float = 0.0
        self._has_confirmed_grant: bool = False

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
        } or (
            self._state is PermissionState.TRANSIENT_FAILURE
            and not self._has_confirmed_grant
        )

    def should_emit(self, now_epoch: float) -> bool:
        if now_epoch - self._last_emit_epoch < EMIT_COOLDOWN_SEC:
            return False
        self._last_emit_epoch = now_epoch
        return True

    def record_check(self, result: PermissionCheckResult) -> PermissionSnapshot:
        checked_at = result.checked_at or utc_now_iso()
        self._last_check_ts = checked_at

        if result.ok:
            self._consecutive_failures = 0
            self._has_confirmed_grant = True
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

        if self._state is PermissionState.RECOVERING:
            self._reason = "input_monitoring_recovering"
        elif self._state is PermissionState.GRANTED:
            self._reason = "granted"
        else:
            self._reason = result.reason

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

    if Quartz is None:
        return PermissionCheckResult(ok=True, reason="permission_check_unavailable")

    event_tap_create = getattr(Quartz, "CGEventTapCreate", None)
    event_mask_bit = getattr(Quartz, "CGEventMaskBit", None)
    session_event_tap = getattr(Quartz, "kCGSessionEventTap", None)
    head_insert_event_tap = getattr(Quartz, "kCGHeadInsertEventTap", None)
    tap_option_listen_only = getattr(Quartz, "kCGEventTapOptionListenOnly", None)
    left_mouse_down = getattr(Quartz, "kCGEventLeftMouseDown", None)
    right_mouse_down = getattr(Quartz, "kCGEventRightMouseDown", None)
    other_mouse_down = getattr(Quartz, "kCGEventOtherMouseDown", None)
    cf_mach_port_invalidate = getattr(Quartz, "CFMachPortInvalidate", None)

    if None in {
        event_tap_create,
        event_mask_bit,
        session_event_tap,
        head_insert_event_tap,
        tap_option_listen_only,
        left_mouse_down,
        right_mouse_down,
        other_mouse_down,
    }:
        return PermissionCheckResult(ok=True, reason="permission_check_unavailable")

    assert event_tap_create is not None
    assert event_mask_bit is not None
    assert session_event_tap is not None
    assert head_insert_event_tap is not None
    assert tap_option_listen_only is not None
    assert left_mouse_down is not None
    assert right_mouse_down is not None
    assert other_mouse_down is not None

    event_mask = (
        event_mask_bit(left_mouse_down)
        | event_mask_bit(right_mouse_down)
        | event_mask_bit(other_mouse_down)
    )

    def _handle_event(_proxy, _event_type, event, _refcon):
        return event

    event_tap = None
    try:
        event_tap = event_tap_create(
            session_event_tap,
            head_insert_event_tap,
            tap_option_listen_only,
            event_mask,
            _handle_event,
            None,
        )
    except Exception:
        logger.exception("Input Monitoring probe failed")
        return PermissionCheckResult(ok=False, reason="tcc_transient_failure")

    if event_tap is None:
        return PermissionCheckResult(ok=False, reason="input_monitoring_denied")

    # CRITICAL: Release the event tap to prevent resource leak
    # The tap is created but never added to a RunLoop, so we just need to invalidate it
    if cf_mach_port_invalidate is not None:
        try:
            cf_mach_port_invalidate(event_tap)
        except Exception:
            pass  # Ignore cleanup errors

    return PermissionCheckResult(ok=True, reason="granted")


def permission_poll_interval_sec() -> int:
    """Get permission poll interval, preferring runtime settings over TOML config.

    This function supports hot-reload: if the value is changed via WebUI,
    it will be picked up immediately without requiring a process restart.
    """
    from openrecall.client import runtime_config
    return runtime_config.get_permission_poll_interval_sec()
