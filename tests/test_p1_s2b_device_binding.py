from __future__ import annotations

import pytest

from openrecall.client.events.base import CaptureTrigger, RoutedCaptureTask
from openrecall.client.recorder import ScreenRecorder


@pytest.mark.unit
def test_worker_binding_uses_routed_target_device_name() -> None:
    recorder = ScreenRecorder()
    task = RoutedCaptureTask(
        capture_trigger=CaptureTrigger.CLICK,
        target_device_name="monitor_display-a",
        routing_topology_epoch=1,
        event_ts="2026-03-15T00:00:00Z",
        routing_hints={},
    )

    metadata = recorder._build_capture_metadata(
        task,
        context_active_app="Finder",
        context_active_window="Desktop",
        focused_monitor_device_name="monitor_display-a",
    )

    assert metadata["device_name"] == "monitor_display-a"
    assert metadata["capture_trigger"] == "click"


@pytest.mark.unit
def test_non_focused_capture_writes_null_context() -> None:
    recorder = ScreenRecorder()
    task = RoutedCaptureTask(
        capture_trigger=CaptureTrigger.CLICK,
        target_device_name="monitor_display-b",
        routing_topology_epoch=1,
        event_ts="2026-03-15T00:00:00Z",
        routing_hints={"active_app": "Finder", "active_window": "Desktop"},
    )

    metadata = recorder._build_capture_metadata(
        task,
        context_active_app="Finder",
        context_active_window="Desktop",
        focused_monitor_device_name="monitor_display-a",
    )

    assert metadata["app_name"] is None
    assert metadata["window_name"] is None


@pytest.mark.unit
def test_alias_fields_are_kept_for_ingest_compatibility() -> None:
    recorder = ScreenRecorder()
    task = RoutedCaptureTask(
        capture_trigger=CaptureTrigger.APP_SWITCH,
        target_device_name="monitor_display-a",
        routing_topology_epoch=1,
        event_ts="2026-03-15T00:00:00Z",
        routing_hints={},
    )

    metadata = recorder._build_capture_metadata(
        task,
        context_active_app="Finder",
        context_active_window="Desktop",
        focused_monitor_device_name="monitor_display-a",
    )

    assert metadata["app_name"] == "Finder"
    assert metadata["window_name"] == "Desktop"
    assert metadata["active_app"] == "Finder"
    assert metadata["active_window"] == "Desktop"


@pytest.mark.unit
def test_timestamp_represents_capture_completion_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder = ScreenRecorder()
    monkeypatch.setattr(
        "openrecall.client.recorder.utc_now_iso", lambda: "2026-03-15T00:00:01Z"
    )
    task = RoutedCaptureTask(
        capture_trigger=CaptureTrigger.MANUAL,
        target_device_name="monitor_display-a",
        routing_topology_epoch=1,
        event_ts="2026-03-15T00:00:00Z",
        routing_hints={},
    )

    metadata = recorder._build_capture_metadata(
        task,
        context_active_app="Finder",
        context_active_window="Desktop",
        focused_monitor_device_name="monitor_display-a",
    )

    assert metadata["event_ts"] == "2026-03-15T00:00:00Z"
    assert metadata["timestamp"] == "2026-03-15T00:00:01Z"
