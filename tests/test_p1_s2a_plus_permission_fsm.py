from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Iterator

import numpy as np
import pytest
from flask import Flask

from openrecall.client.events.base import CaptureTrigger, TriggerEvent
from openrecall.client.events.base import MonitorDescriptor
from openrecall.client.events.permissions import (
    PermissionCheckResult,
    PermissionState,
    PermissionStateMachine,
)
from openrecall.client.recorder import ScreenRecorder
from openrecall.server import api_v1
from openrecall.server.config_runtime import runtime_settings


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@pytest.fixture(autouse=True)
def restore_runtime_settings() -> Iterator[None]:
    with runtime_settings._lock:
        original = {
            "capture_permission_status": runtime_settings.capture_permission_status,
            "capture_permission_reason": runtime_settings.capture_permission_reason,
            "last_permission_check_ts": runtime_settings.last_permission_check_ts,
            "last_permission_snapshot_epoch": runtime_settings.last_permission_snapshot_epoch,
            "queue_depth": runtime_settings.queue_depth,
            "queue_capacity": runtime_settings.queue_capacity,
            "collapse_trigger_count": runtime_settings.collapse_trigger_count,
            "overflow_drop_count": runtime_settings.overflow_drop_count,
        }

    yield

    with runtime_settings._lock:
        for key, value in original.items():
            setattr(runtime_settings, key, value)


def _make_health_client(monkeypatch: pytest.MonkeyPatch):
    fresh_now = _utc_now_iso()

    class _FakeStore:
        @staticmethod
        def get_last_frame_timestamp() -> str | None:
            return fresh_now

        @staticmethod
        def get_last_frame_ingested_at() -> str | None:
            return fresh_now

        @staticmethod
        def get_queue_counts() -> dict[str, int]:
            return {"pending": 0, "processing": 0, "failed": 0}

    monkeypatch.setattr(api_v1, "_get_frames_store", lambda: _FakeStore())

    app = Flask(__name__)
    app.register_blueprint(api_v1.v1_bp)
    return app.test_client()


def _mirror_snapshot(status: str, reason: str, *, is_fresh: bool = True) -> None:
    fresh_ts = _utc_now_iso()
    stale_ts = "1970-01-01T00:00:00Z"
    with runtime_settings._lock:
        runtime_settings.capture_permission_status = status
        runtime_settings.capture_permission_reason = reason
        runtime_settings.last_permission_check_ts = fresh_ts if is_fresh else stale_ts
        runtime_settings.last_permission_snapshot_epoch = 0.0 if not is_fresh else 1.0
        if is_fresh:
            runtime_settings.last_permission_snapshot_epoch = datetime.now(
                timezone.utc
            ).timestamp()


@pytest.mark.unit
def test_startup_not_determined_health_degraded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    machine = PermissionStateMachine()
    snapshot = machine.snapshot()

    assert snapshot.status is PermissionState.TRANSIENT_FAILURE
    assert snapshot.reason == "startup_not_determined"

    _mirror_snapshot(snapshot.status.value, snapshot.reason)
    client = _make_health_client(monkeypatch)
    response = client.get("/v1/health")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "degraded"
    assert payload["capture_permission_status"] == "transient_failure"
    assert payload["capture_permission_reason"] == "startup_not_determined"


@pytest.mark.unit
def test_startup_denied_transitions_to_denied_or_revoked() -> None:
    machine = PermissionStateMachine()

    machine.record_check(
        PermissionCheckResult(
            ok=False,
            reason="input_monitoring_denied",
            checked_at="2026-03-10T12:00:00Z",
        )
    )
    denied = machine.record_check(
        PermissionCheckResult(
            ok=False,
            reason="input_monitoring_denied",
            checked_at="2026-03-10T12:00:10Z",
        )
    )

    assert denied.status is PermissionState.DENIED_OR_REVOKED
    assert denied.reason == "input_monitoring_denied"


@pytest.mark.unit
def test_detect_permissions_uses_input_monitoring_event_tap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from openrecall.client.events import permissions

    calls: dict[str, int] = {"event_tap_create": 0}

    def _event_tap_create(*args):
        calls["event_tap_create"] += 1
        return object()

    def _unexpected_legacy_check() -> bool:
        raise AssertionError("legacy AX permission checks should not run")

    fake_quartz = SimpleNamespace(
        CGEventTapCreate=_event_tap_create,
        CGEventMaskBit=lambda event_type: 1 << event_type,
        kCGSessionEventTap=1,
        kCGHeadInsertEventTap=2,
        kCGEventTapOptionListenOnly=3,
        kCGEventLeftMouseDown=4,
        kCGEventRightMouseDown=5,
        kCGEventOtherMouseDown=6,
        CFMachPortInvalidate=lambda _tap: None,
        CFRelease=lambda _tap: None,
    )

    monkeypatch.setattr(permissions, "Quartz", fake_quartz)
    monkeypatch.setattr(
        permissions,
        "ApplicationServices",
        SimpleNamespace(AXIsProcessTrusted=_unexpected_legacy_check),
    )

    result = permissions.detect_permissions()

    assert result.ok is True
    assert result.reason == "granted"
    assert calls["event_tap_create"] == 1


@pytest.mark.unit
def test_detect_permissions_does_not_manually_release_event_tap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from openrecall.client.events import permissions

    def _event_tap_create(*args):
        return object()

    def _fail_invalidate(_tap: object) -> None:
        raise AssertionError("detect_permissions must not invalidate tap manually")

    def _fail_release(_tap: object) -> None:
        raise AssertionError("detect_permissions must not CFRelease tap manually")

    fake_quartz = SimpleNamespace(
        CGEventTapCreate=_event_tap_create,
        CGEventMaskBit=lambda event_type: 1 << event_type,
        kCGSessionEventTap=1,
        kCGHeadInsertEventTap=2,
        kCGEventTapOptionListenOnly=3,
        kCGEventLeftMouseDown=4,
        kCGEventRightMouseDown=5,
        kCGEventOtherMouseDown=6,
        CFMachPortInvalidate=_fail_invalidate,
        CFRelease=_fail_release,
    )

    monkeypatch.setattr(permissions, "Quartz", fake_quartz)

    result = permissions.detect_permissions()

    assert result.ok is True
    assert result.reason == "granted"


@pytest.mark.unit
def test_blank_frame_warning_is_observational_only() -> None:
    recorder = ScreenRecorder()
    recorder._last_permission_snapshot = (
        recorder._permission_state_machine.record_check(
            PermissionCheckResult(ok=True, reason="granted")
        )
    )
    before = recorder._last_permission_snapshot

    recorder._warn_if_blank_frame(
        "monitor_1",
        CaptureTrigger.CLICK,
        np.zeros((4, 4, 3), dtype=np.uint8),
    )

    after = recorder._last_permission_snapshot
    assert after.status is PermissionState.GRANTED
    assert after.reason == before.reason == "granted"


@pytest.mark.unit
def test_mid_run_revoked_stops_capture_and_degrades_health(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = ScreenRecorder()
    recorder._last_permission_snapshot = (
        recorder._permission_state_machine.record_check(
            PermissionCheckResult(ok=True, reason="granted")
        )
    )
    recorder._last_permission_snapshot = (
        recorder._permission_state_machine.record_check(
            PermissionCheckResult(ok=False, reason="input_monitoring_denied")
        )
    )
    recorder._last_permission_snapshot = (
        recorder._permission_state_machine.record_check(
            PermissionCheckResult(ok=False, reason="input_monitoring_denied")
        )
    )

    recorder._handle_external_trigger(
        TriggerEvent(
            capture_trigger=CaptureTrigger.CLICK,
            device_name="monitor_1",
            event_ts="2026-03-10T12:00:00Z",
        )
    )

    snapshot = recorder._last_permission_snapshot
    assert snapshot.status is PermissionState.DENIED_OR_REVOKED
    assert recorder.trigger_channel_snapshot().queue_depth == 0

    _mirror_snapshot(snapshot.status.value, snapshot.reason)
    client = _make_health_client(monkeypatch)
    response = client.get("/v1/health")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "degraded"
    assert payload["capture_permission_status"] == "denied_or_revoked"


@pytest.mark.unit
def test_degraded_capture_loop_blocks_idle_fallback_until_recovered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = ScreenRecorder()
    recorder._last_permission_snapshot = (
        recorder._permission_state_machine.record_check(
            PermissionCheckResult(ok=True, reason="granted")
        )
    )
    recorder._last_permission_snapshot = (
        recorder._permission_state_machine.record_check(
            PermissionCheckResult(ok=False, reason="input_monitoring_denied")
        )
    )
    recorder._last_permission_snapshot = (
        recorder._permission_state_machine.record_check(
            PermissionCheckResult(ok=False, reason="input_monitoring_denied")
        )
    )

    calls = {"heartbeat": 0, "wait_for_trigger": 0, "degraded_sleep": 0}

    monkeypatch.setattr(recorder, "start", lambda: None)
    monkeypatch.setattr(
        recorder,
        "_refresh_monitors",
        lambda: [
            MonitorDescriptor(
                stable_id="1",
                left=0,
                top=0,
                width=100,
                height=100,
                is_primary=True,
            )
        ],
    )
    monkeypatch.setattr(recorder, "_start_event_sources", lambda: None)
    monkeypatch.setattr(recorder, "_poll_permissions", lambda **_: None)
    monkeypatch.setattr(
        recorder,
        "_send_heartbeat",
        lambda **_: calls.__setitem__("heartbeat", calls["heartbeat"] + 1),
    )
    monkeypatch.setattr(recorder, "_report_stats", lambda: None)

    def _wait_for_trigger(**_: object) -> TriggerEvent:
        calls["wait_for_trigger"] += 1
        raise AssertionError("idle fallback should stay blocked while degraded")

    monkeypatch.setattr(recorder, "_wait_for_trigger", _wait_for_trigger)

    def _degraded_sleep() -> None:
        calls["degraded_sleep"] += 1
        recorder._stop_requested = True

    monkeypatch.setattr(recorder, "_degraded_sleep", _degraded_sleep)
    monkeypatch.setattr("openrecall.client.recorder.time.time", lambda: 100.0)

    recorder.run_capture_loop()

    assert calls == {
        "heartbeat": 1,
        "wait_for_trigger": 0,
        "degraded_sleep": 1,
    }


@pytest.mark.unit
def test_restored_after_denied_recovers_to_granted() -> None:
    machine = PermissionStateMachine()

    machine.record_check(
        PermissionCheckResult(ok=False, reason="input_monitoring_denied")
    )
    machine.record_check(
        PermissionCheckResult(ok=False, reason="input_monitoring_denied")
    )

    first_success = machine.record_check(
        PermissionCheckResult(ok=True, reason="granted")
    )
    second_success = machine.record_check(
        PermissionCheckResult(ok=True, reason="granted")
    )
    third_success = machine.record_check(
        PermissionCheckResult(ok=True, reason="granted")
    )

    assert first_success.status is PermissionState.RECOVERING
    assert first_success.reason == "input_monitoring_recovering"
    assert second_success.status is PermissionState.RECOVERING
    assert second_success.reason == "input_monitoring_recovering"
    assert third_success.status is PermissionState.GRANTED
    assert third_success.reason == "granted"


@pytest.mark.unit
def test_stale_permission_snapshot_forces_degraded_health(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mirror_snapshot("granted", "granted", is_fresh=False)
    client = _make_health_client(monkeypatch)

    response = client.get("/v1/health")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "degraded"
    assert payload["capture_permission_reason"] == "stale_permission_state"


@pytest.mark.unit
def test_runtime_settings_preserve_complete_permission_snapshot() -> None:
    with runtime_settings._lock:
        runtime_settings.capture_permission_status = "recovering"
        runtime_settings.capture_permission_reason = "input_monitoring_denied"
        runtime_settings.last_permission_check_ts = "1970-01-01T00:01:40Z"
        runtime_settings.last_permission_snapshot_epoch = 100.0

    runtime_settings.update_client_state(
        {
            "capture_permission_status": "granted",
            "capture_permission_reason": "granted",
        },
        now_epoch=150.0,
    )

    snapshot = runtime_settings.get_permission_snapshot(now_epoch=150.0)
    assert snapshot["capture_permission_status"] == "recovering"
    assert snapshot["capture_permission_reason"] == "input_monitoring_denied"
    assert snapshot["last_permission_check_ts"] == "1970-01-01T00:01:40Z"


@pytest.mark.unit
def test_health_contract_contains_permission_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _mirror_snapshot("recovering", "input_monitoring_denied")
    client = _make_health_client(monkeypatch)

    response = client.get("/v1/health")

    assert response.status_code == 200
    payload = response.get_json()
    assert set(payload) >= {
        "capture_permission_status",
        "capture_permission_reason",
        "last_permission_check_ts",
    }


@pytest.mark.unit
def test_layout_health_polling_handles_transient_permission_payload() -> None:
    content = Path(
        "/Users/pyw/old/MyRecall/openrecall/server/templates/layout.html"
    ).read_text(encoding="utf-8")

    assert "transient_failure" in content
    assert "权限待确认" in content
