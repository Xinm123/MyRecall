from __future__ import annotations

import queue
import time

import pytest

from openrecall.client.events.base import (
    CaptureTrigger,
    MonitorDescriptor,
    TriggerEvent,
)
from openrecall.client.events.permissions import PermissionCheckResult
from openrecall.client.recorder import ScreenRecorder, take_screenshots


@pytest.mark.unit
def test_emit_manual_trigger_uses_shared_debounce_gate(monkeypatch):
    recorder = ScreenRecorder()

    accepted = recorder.emit_manual_trigger(
        device_name="monitor_1",
        now_ms=1000,
        event_ts="2026-03-10T00:00:00Z",
    )
    rejected = recorder.emit_manual_trigger(
        device_name="monitor_1",
        now_ms=1500,
        event_ts="2026-03-10T00:00:00.500Z",
    )

    assert accepted is True
    assert rejected is False
    snapshot = recorder.trigger_channel_snapshot()
    assert snapshot.queue_depth == 1
    queued_event = recorder._trigger_channel.get_nowait()
    assert queued_event.capture_trigger is CaptureTrigger.MANUAL
    assert queued_event.device_name == "monitor_1"


@pytest.mark.unit
def test_wait_for_trigger_returns_idle_after_timeout(monkeypatch):
    recorder = ScreenRecorder()
    # S2b: per-monitor idle scheduling - populate idle deadlines first
    recorder._enabled_monitor_devices = {"monitor_1"}
    recorder._idle_deadlines["monitor_1"] = time.time() - 1  # already due

    calls = {"n": 0}

    def _raise_empty(timeout: float):
        calls["n"] += 1
        raise queue.Empty

    monkeypatch.setattr(recorder._trigger_channel, "get", _raise_empty)

    event = recorder._wait_for_trigger(timeout_seconds=30.0)

    assert event.capture_trigger is CaptureTrigger.IDLE
    assert event.device_name == "monitor_1"


@pytest.mark.unit
def test_wait_for_trigger_applies_per_monitor_idle_scheduling(monkeypatch):
    """S2b: per-monitor idle scheduling replaces global shared debounce."""
    recorder = ScreenRecorder()

    # Setup: enable two monitors with different idle deadlines
    recorder._enabled_monitor_devices = {"monitor_1", "monitor_2"}
    now = time.time()
    recorder._idle_deadlines["monitor_1"] = now - 1  # already due
    recorder._idle_deadlines["monitor_2"] = now + 30  # not due yet

    def _raise_empty(timeout: float):
        raise queue.Empty

    monkeypatch.setattr(recorder._trigger_channel, "get", _raise_empty)

    event = recorder._wait_for_trigger(timeout_seconds=30.0)

    # Should return IDLE for monitor_1 (the only due monitor)
    assert event.capture_trigger is CaptureTrigger.IDLE
    assert event.device_name == "monitor_1"


@pytest.mark.unit
def test_build_capture_metadata_includes_required_section2_fields():
    recorder = ScreenRecorder()
    event = TriggerEvent(
        capture_trigger=CaptureTrigger.APP_SWITCH,
        device_name="monitor_2",
        event_ts="2026-03-10T00:00:00Z",
        active_app="Finder",
        active_window="Desktop",
    )

    metadata = recorder._build_capture_metadata(
        event,
        context_active_app="Google Chrome",
        context_active_window="Desktop",
    )

    assert metadata["capture_trigger"] == "app_switch"
    assert metadata["device_name"] == "monitor_2"
    assert metadata["event_ts"] == "2026-03-10T00:00:00Z"
    assert metadata["active_app"] == "Finder"
    assert metadata["active_window"] == "Desktop"
    assert "timestamp" in metadata


@pytest.mark.unit
def test_build_capture_metadata_prefers_live_app_for_click() -> None:
    recorder = ScreenRecorder()
    event = TriggerEvent(
        capture_trigger=CaptureTrigger.CLICK,
        device_name="monitor_1",
        event_ts="2026-03-10T00:00:00Z",
        active_app="Antigravity",
        active_window="MyRecall",
    )

    metadata = recorder._build_capture_metadata(
        event,
        context_active_app="Google Chrome",
        context_active_window="Chrome Tab",
    )

    assert metadata["active_app"] == "Google Chrome"


@pytest.mark.unit
def test_build_capture_metadata_prefers_live_window_for_click() -> None:
    recorder = ScreenRecorder()
    event = TriggerEvent(
        capture_trigger=CaptureTrigger.CLICK,
        device_name="monitor_1",
        event_ts="2026-03-10T00:00:00Z",
        active_app="Google Chrome",
        active_window="MyRecall",
    )

    metadata = recorder._build_capture_metadata(
        event,
        context_active_app="Google Chrome",
        context_active_window="Stack Overflow - Google Chrome",
    )

    assert metadata["active_window"] == "Stack Overflow - Google Chrome"


@pytest.mark.unit
def test_build_capture_metadata_mismatched_monitor_returns_none() -> None:
    recorder = ScreenRecorder()
    event = TriggerEvent(
        capture_trigger=CaptureTrigger.CLICK,
        device_name="monitor_1",
        event_ts="2026-03-10T00:00:00Z",
    )

    # Scenario: Click on monitor_1, but active app is on monitor_2
    metadata = recorder._build_capture_metadata(
        event,
        context_active_app="Google Chrome",
        context_active_window="MyRecall",
        context_active_monitor_device_name="monitor_2",
    )

    # Monitor 1 should NOT be tagged with Chrome
    assert metadata["app_name"] is None
    assert metadata["window_name"] is None
    assert metadata["active_app"] is None
    assert metadata["active_window"] is None


@pytest.mark.unit
def test_snapshot_active_context_uses_same_app_for_window_lookup(monkeypatch) -> None:
    recorder = ScreenRecorder()
    captured_app: list[str] = []

    monkeypatch.setattr(
        "openrecall.client.recorder.get_active_app_name", lambda: "Google Chrome"
    )
    monkeypatch.setattr(
        "openrecall.client.recorder.get_frontmost_app_name", lambda: "Antigravity"
    )

    def _window_for_app(app_name: str) -> str:
        captured_app.append(app_name)
        return "Stack Overflow - Google Chrome"

    monkeypatch.setattr(
        "openrecall.client.recorder.get_active_window_title_for_app",
        _window_for_app,
    )

    monkeypatch.setattr(
        "openrecall.client.recorder.get_active_app_monitor", lambda monitors: None
    )

    active_app, active_window, active_monitor = recorder._snapshot_active_context()

    assert active_app == "Google Chrome"
    assert active_window == "Stack Overflow - Google Chrome"
    assert active_monitor is None
    assert captured_app == ["Google Chrome"]


@pytest.mark.unit
def test_poll_permissions_uses_configured_cadence(monkeypatch):
    recorder = ScreenRecorder()
    calls: list[float] = []

    def _fake_detect_permissions():
        calls.append(1.0)
        from openrecall.client.events.permissions import PermissionCheckResult

        return PermissionCheckResult(ok=True, reason="granted")

    monkeypatch.setattr(
        "openrecall.client.recorder.detect_permissions", _fake_detect_permissions
    )

    recorder._poll_permissions(now_epoch=10.0)
    recorder._poll_permissions(now_epoch=15.0)
    recorder._poll_permissions(now_epoch=21.0)

    assert len(calls) == 2


@pytest.mark.unit
def test_start_event_sources_wires_both_macos_emitters(monkeypatch):
    recorder = ScreenRecorder()
    started: list[str] = []

    class _FakeTap:
        def __init__(self, trigger_channel, debouncer, monitor_lookup):
            self.trigger_channel = trigger_channel
            self.debouncer = debouncer
            self.monitor_lookup = monitor_lookup

        def start(self):
            started.append("tap")

    class _FakeSwitchMonitor:
        def __init__(self, callback, monitor_lookup):
            self.callback = callback
            self.monitor_lookup = monitor_lookup

        def start(self):
            started.append("switch")

    monkeypatch.setattr("openrecall.client.recorder.MacOSEventTap", _FakeTap)
    monkeypatch.setattr(
        "openrecall.client.recorder.MacOSAppSwitchMonitor",
        _FakeSwitchMonitor,
    )

    recorder._monitor_registry.refresh(
        [
            MonitorDescriptor(
                stable_id="1",
                left=0,
                top=0,
                width=100,
                height=100,
                is_primary=True,
            )
        ]
    )
    recorder._start_event_sources()

    assert started == ["tap", "switch"]


@pytest.mark.unit
def test_send_heartbeat_reports_permission_and_trigger_channel(monkeypatch):
    recorder = ScreenRecorder()
    recorder._last_permission_snapshot = (
        recorder._permission_state_machine.record_check(
            PermissionCheckResult(ok=True, reason="granted")
        )
    )
    recorder.emit_manual_trigger(
        device_name="monitor_1",
        now_ms=1000,
        event_ts="2026-03-10T00:00:00Z",
    )

    captured_url = ""
    captured_payload: dict[str, object] = {}

    class _Response:
        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict[str, object]:
            return {"config": {"recording_enabled": True, "upload_enabled": True}}

    def _fake_post(url: str, **kwargs: object):
        nonlocal captured_url, captured_payload
        captured_url = url
        payload = kwargs.get("json")
        assert isinstance(payload, dict)
        captured_payload = payload
        return _Response()

    monkeypatch.setattr("openrecall.client.recorder.requests.post", _fake_post)

    recorder._send_heartbeat()

    assert captured_url.endswith("/heartbeat")
    payload = captured_payload
    assert payload["capture_permission_status"] == "granted"
    assert payload["capture_permission_reason"] == "granted"
    assert payload["queue_depth"] == 1
    assert payload["queue_capacity"] == 64
    assert payload["collapse_trigger_count"] == 0
    assert payload["overflow_drop_count"] == 0


@pytest.mark.unit
def test_take_screenshots_logs_warning_for_out_of_bounds_monitor(monkeypatch, caplog):
    class _FakeMSS:
        def __init__(self) -> None:
            self.monitors = [{}]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb) -> bool:
            return False

    monkeypatch.setattr("openrecall.client.recorder.mss.mss", _FakeMSS)
    monkeypatch.setattr(
        "openrecall.client.recorder.settings.primary_monitor_only", True
    )

    with caplog.at_level("WARNING"):
        screenshots = take_screenshots()

    assert screenshots == []
    assert "Monitor index 1 out of bounds. Skipping." in caplog.text


@pytest.mark.unit
def test_stop_stops_app_switch_monitor(monkeypatch) -> None:
    recorder = ScreenRecorder()
    calls: list[str] = []

    class _FakeSwitchMonitor:
        def stop(self) -> None:
            calls.append("switch")

    class _FakeThread:
        def stop(self) -> None:
            calls.append("thread")

        def is_alive(self) -> bool:
            return False

    monkeypatch.setattr(recorder, "_app_switch_monitor", _FakeSwitchMonitor())
    monkeypatch.setattr(recorder, "consumer", _FakeThread())
    monkeypatch.setattr(recorder, "_spool_uploader", _FakeThread())

    recorder.stop()

    assert calls == ["switch", "thread", "thread"]
