from __future__ import annotations

import queue

import pytest

from openrecall.client.events.base import (
    CaptureTrigger,
    MonitorDescriptor,
    TriggerEvent,
)
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

    calls = {"n": 0}

    def _raise_empty(timeout: float):
        assert timeout == 30.0
        calls["n"] += 1
        if calls["n"] == 1:
            raise queue.Empty
        return recorder._trigger_channel.get_nowait()

    monkeypatch.setattr(recorder._trigger_channel, "get", _raise_empty)

    event = recorder._wait_for_trigger(
        timeout_seconds=30.0, fallback_device_name="monitor_1"
    )

    assert event.capture_trigger is CaptureTrigger.IDLE
    assert event.device_name == "monitor_1"


@pytest.mark.unit
def test_wait_for_trigger_applies_shared_debounce_to_idle(monkeypatch):
    recorder = ScreenRecorder()

    recorder.emit_manual_trigger(
        device_name="monitor_1",
        now_ms=1000,
        event_ts="2026-03-10T00:00:00Z",
    )
    _ = recorder._trigger_channel.get_nowait()

    calls = {"n": 0}

    def _raise_empty(timeout: float):
        calls["n"] += 1
        if calls["n"] == 1:
            monkeypatch.setattr("openrecall.client.recorder.time.time", lambda: 1.5)
            raise queue.Empty
        if calls["n"] == 2:
            monkeypatch.setattr("openrecall.client.recorder.time.time", lambda: 2.0)
            raise queue.Empty
        return recorder._trigger_channel.get_nowait()

    monkeypatch.setattr(recorder._trigger_channel, "get", _raise_empty)

    event = recorder._wait_for_trigger(
        timeout_seconds=30.0, fallback_device_name="monitor_1"
    )

    assert event.capture_trigger is CaptureTrigger.IDLE
    assert event.device_name == "monitor_1"
    assert calls["n"] == 3


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

    metadata = recorder._build_capture_metadata(event)

    assert metadata["capture_trigger"] == "app_switch"
    assert metadata["device_name"] == "monitor_2"
    assert metadata["event_ts"] == "2026-03-10T00:00:00Z"
    assert metadata["active_app"] == "Finder"
    assert metadata["active_window"] == "Desktop"
    assert "timestamp" in metadata


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
        def __init__(self, callback, monitor_lookup):
            self.callback = callback
            self.monitor_lookup = monitor_lookup

        def start(self):
            started.append("tap")

    class _FakeSwitchMonitor:
        def __init__(self, callback, monitor_provider):
            self.callback = callback
            self.monitor_provider = monitor_provider

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
    recorder._last_permission_snapshot = recorder._permission_state_machine.snapshot()
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
