from __future__ import annotations

import pytest

from openrecall.client.events.base import (
    CaptureTrigger,
    MonitorDescriptor,
    RoutedCaptureTask,
    TriggerEvent,
)
from openrecall.client.recorder import ScreenRecorder


@pytest.mark.unit
def test_click_routes_to_specific_monitor() -> None:
    recorder = ScreenRecorder()
    monitor_a = MonitorDescriptor("display-a", 0, 0, 100, 100, is_primary=True)
    monitor_b = MonitorDescriptor("display-b", 100, 0, 100, 100)
    recorder._refresh_routing_state([monitor_a, monitor_b])

    event = TriggerEvent(
        capture_trigger=CaptureTrigger.CLICK,
        device_name=monitor_b.device_name,
        event_ts="2026-03-15T00:00:00Z",
    )

    routed = recorder._route_trigger(event)

    assert len(routed) == 1
    assert routed[0].capture_trigger is CaptureTrigger.CLICK
    assert routed[0].target_device_name == monitor_b.device_name


@pytest.mark.unit
def test_click_routes_to_primary_monitor_when_target_is_primary() -> None:
    recorder = ScreenRecorder()
    monitor_a = MonitorDescriptor("display-a", 0, 0, 100, 100, is_primary=True)
    monitor_b = MonitorDescriptor("display-b", 100, 0, 100, 100)
    recorder._refresh_routing_state([monitor_a, monitor_b])

    event = TriggerEvent(
        capture_trigger=CaptureTrigger.CLICK,
        device_name=monitor_a.device_name,
        event_ts="2026-03-15T00:00:00Z",
    )

    routed = recorder._route_trigger(event)

    assert len(routed) == 1
    assert routed[0].target_device_name == monitor_a.device_name


@pytest.mark.unit
def test_manual_without_target_defaults_to_primary_monitor() -> None:
    recorder = ScreenRecorder()
    monitor_a = MonitorDescriptor("display-a", 0, 0, 100, 100, is_primary=True)
    monitor_b = MonitorDescriptor("display-b", 100, 0, 100, 100)
    recorder._refresh_routing_state([monitor_a, monitor_b])

    event = TriggerEvent(
        capture_trigger=CaptureTrigger.MANUAL,
        device_name="",
        event_ts="2026-03-15T00:00:00Z",
    )

    routed = recorder._route_trigger(event)

    assert len(routed) == 1
    assert routed[0].target_device_name == monitor_a.device_name


@pytest.mark.unit
def test_idle_non_focused_monitor_uses_primary_focused_hint() -> None:
    recorder = ScreenRecorder()
    primary = MonitorDescriptor("display-a", 0, 0, 100, 100, is_primary=True)
    secondary = MonitorDescriptor("display-b", 100, 0, 100, 100)
    recorder._refresh_routing_state([primary, secondary])

    event = TriggerEvent(
        capture_trigger=CaptureTrigger.IDLE,
        device_name=secondary.device_name,
        event_ts="2026-03-15T00:00:00Z",
    )

    routed = recorder._route_trigger(event)

    assert len(routed) == 1
    task = routed[0]
    assert task.target_device_name == secondary.device_name
    assert task.routing_hints["focused_device_name"] == primary.device_name

    metadata = recorder._build_capture_metadata(
        task,
        context_active_app="Finder",
        context_active_window="Desktop",
        focused_monitor_device_name=str(task.routing_hints["focused_device_name"]),
    )
    assert metadata["app_name"] is None
    assert metadata["window_name"] is None


@pytest.mark.unit
def test_routing_filtered_sets_last_outcome_without_persisting_work() -> None:
    recorder = ScreenRecorder()
    recorder._enabled_monitor_devices = {"monitor_display-a"}

    routed = recorder._route_targets(
        capture_trigger=CaptureTrigger.APP_SWITCH,
        target_device_names=["monitor_display-b"],
        event_ts="2026-03-15T00:00:00Z",
        hints={"reason": "primary_monitor_only"},
    )

    assert routed == []
    assert recorder._last_capture_outcome["outcome"] == "routing_filtered"
    assert recorder._last_capture_outcome["target_device_name"] == "monitor_display-b"


@pytest.mark.unit
def test_per_monitor_idle_partitions_reset_independently() -> None:
    recorder = ScreenRecorder()
    monitor_a = MonitorDescriptor("display-a", 0, 0, 100, 100, is_primary=True)
    monitor_b = MonitorDescriptor("display-b", 100, 0, 100, 100)
    recorder._refresh_routing_state([monitor_a, monitor_b], now_epoch=100.0)

    before_b = recorder._idle_deadlines[monitor_b.device_name]
    recorder._on_capture_completed(monitor_a.device_name, now_epoch=120.0)

    assert recorder._idle_deadlines[monitor_a.device_name] == pytest.approx(
        120.0 + recorder._idle_interval_seconds
    )
    assert recorder._idle_deadlines[monitor_b.device_name] == before_b


@pytest.mark.unit
def test_stale_routed_task_is_rejected() -> None:
    recorder = ScreenRecorder()
    monitor_a = MonitorDescriptor("display-a", 0, 0, 100, 100, is_primary=True)
    recorder._refresh_routing_state([monitor_a])

    task = RoutedCaptureTask(
        capture_trigger=CaptureTrigger.CLICK,
        target_device_name=monitor_a.device_name,
        routing_topology_epoch=0,
        event_ts="2026-03-15T00:00:00Z",
        routing_hints={},
    )

    accepted = recorder._validate_routed_task(task)

    assert accepted is False
    assert recorder._last_capture_outcome["outcome"] == "stale_routed_task"


@pytest.mark.unit
def test_same_monitor_debounce_and_cross_monitor_independence() -> None:
    recorder = ScreenRecorder()

    first = recorder.emit_manual_trigger(
        device_name="monitor_display-a",
        now_ms=1000,
        event_ts="2026-03-15T00:00:00Z",
    )
    second_same_monitor = recorder.emit_manual_trigger(
        device_name="monitor_display-a",
        now_ms=1500,
        event_ts="2026-03-15T00:00:00.500Z",
    )
    cross_monitor = recorder.emit_manual_trigger(
        device_name="monitor_display-b",
        now_ms=1500,
        event_ts="2026-03-15T00:00:00.500Z",
    )

    assert first is True
    assert second_same_monitor is False
    assert cross_monitor is True


@pytest.mark.unit
def test_topology_rebuild_add_remove_and_recovery() -> None:
    recorder = ScreenRecorder()
    monitor_a = MonitorDescriptor("display-a", 0, 0, 100, 100, is_primary=True)
    monitor_b = MonitorDescriptor("display-b", 100, 0, 100, 100)

    recorder._refresh_routing_state([monitor_a], now_epoch=100.0)
    first_epoch = recorder._topology_epoch
    first_deadline = recorder._idle_deadlines[monitor_a.device_name]

    recorder._refresh_routing_state([monitor_a, monitor_b], now_epoch=120.0)
    assert recorder._topology_epoch == first_epoch + 1
    assert monitor_b.device_name in recorder._idle_deadlines
    assert recorder._idle_deadlines[monitor_a.device_name] == first_deadline

    recorder._refresh_routing_state([monitor_b], now_epoch=140.0)
    assert recorder._topology_epoch == first_epoch + 2
    assert monitor_a.device_name not in recorder._idle_deadlines

    recorder._refresh_routing_state([monitor_a, monitor_b], now_epoch=160.0)
    assert recorder._topology_epoch == first_epoch + 3
    assert recorder._idle_deadlines[monitor_a.device_name] == pytest.approx(
        160.0 + recorder._idle_interval_seconds
    )


@pytest.mark.unit
def test_topology_add_monitor_scenario() -> None:
    recorder = ScreenRecorder()
    monitor_a = MonitorDescriptor("display-a", 0, 0, 100, 100, is_primary=True)
    monitor_b = MonitorDescriptor("display-b", 100, 0, 100, 100)
    recorder._refresh_routing_state([monitor_a], now_epoch=100.0)

    recorder._refresh_routing_state([monitor_a, monitor_b], now_epoch=120.0)

    assert monitor_b.device_name in recorder._enabled_monitor_devices
    assert monitor_b.device_name in recorder._idle_deadlines


@pytest.mark.unit
def test_topology_remove_monitor_scenario() -> None:
    recorder = ScreenRecorder()
    monitor_a = MonitorDescriptor("display-a", 0, 0, 100, 100, is_primary=True)
    monitor_b = MonitorDescriptor("display-b", 100, 0, 100, 100)
    recorder._refresh_routing_state([monitor_a, monitor_b], now_epoch=100.0)

    recorder._refresh_routing_state([monitor_a], now_epoch=120.0)

    assert monitor_b.device_name not in recorder._enabled_monitor_devices
    assert monitor_b.device_name not in recorder._idle_deadlines


@pytest.mark.unit
def test_topology_primary_switch_updates_manual_target() -> None:
    recorder = ScreenRecorder()
    old_primary = MonitorDescriptor("display-a", 0, 0, 100, 100, is_primary=True)
    new_primary = MonitorDescriptor("display-b", 100, 0, 100, 100, is_primary=False)
    recorder._refresh_routing_state([old_primary, new_primary], now_epoch=100.0)

    switched_a = MonitorDescriptor("display-a", 0, 0, 100, 100, is_primary=False)
    switched_b = MonitorDescriptor("display-b", 100, 0, 100, 100, is_primary=True)
    recorder._refresh_routing_state([switched_a, switched_b], now_epoch=120.0)

    event = TriggerEvent(
        capture_trigger=CaptureTrigger.MANUAL,
        device_name="",
        event_ts="2026-03-15T00:00:00Z",
    )
    routed = recorder._route_trigger(event)

    assert len(routed) == 1
    assert routed[0].target_device_name == switched_b.device_name


@pytest.mark.unit
def test_filtered_routing_produces_outcome_without_spool_enqueue(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    recorder = ScreenRecorder()
    monitor = MonitorDescriptor("display-a", 0, 0, 100, 100, is_primary=True)
    enqueued: list[dict[str, object]] = []

    monkeypatch.setattr(recorder, "start", lambda: None)
    monkeypatch.setattr(recorder, "_start_event_sources", lambda: None)
    monkeypatch.setattr(recorder, "_poll_permissions", lambda *, now_epoch: None)
    monkeypatch.setattr(recorder, "_send_heartbeat", lambda **kwargs: None)
    monkeypatch.setattr(
        recorder._permission_state_machine, "is_degraded", lambda: False
    )
    monkeypatch.setattr(recorder, "_refresh_monitors", lambda: [monitor])
    recorder._monitor_registry.refresh([monitor])
    recorder._enabled_monitor_devices = {monitor.device_name}
    monkeypatch.setattr(
        recorder,
        "_wait_for_trigger",
        lambda **kwargs: (
            recorder._stop_event.set()
            or TriggerEvent(
                capture_trigger=CaptureTrigger.APP_SWITCH,
                device_name="monitor_display-b",
                event_ts="2026-03-15T00:00:00Z",
            )
        ),
    )
    monkeypatch.setattr(
        recorder._spool, "enqueue", lambda image, metadata: enqueued.append(metadata)
    )

    with caplog.at_level("INFO"):
        recorder.run_capture_loop()

    assert enqueued == []
    assert recorder._last_capture_outcome["outcome"] == "routing_filtered"
    assert "routing_filtered" in caplog.text


@pytest.mark.unit
def test_heartbeat_payload_contains_topology_and_outcome_evidence() -> None:
    recorder = ScreenRecorder()
    recorder._enabled_monitor_devices = {"monitor_display-a", "monitor_display-b"}
    recorder._topology_epoch = 7
    recorder._last_capture_outcome = {
        "outcome": "topology_rebuilt",
        "trigger": "manual",
        "target_device_name": "monitor_display-a",
        "reason": "monitor_added",
    }
    captured_payload: dict[str, object] = {}

    class _Response:
        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json() -> dict[str, object]:
            return {"config": {"recording_enabled": True, "upload_enabled": True}}

    def _fake_post(url: str, **kwargs: object):
        payload = kwargs.get("json")
        assert isinstance(payload, dict)
        captured_payload.update(payload)
        return _Response()

    from openrecall.client import recorder as recorder_module

    original_post = recorder_module.requests.post
    recorder_module.requests.post = _fake_post
    try:
        recorder._send_heartbeat()
    finally:
        recorder_module.requests.post = original_post

    capture_runtime = captured_payload.get("capture_runtime")
    assert isinstance(capture_runtime, dict)
    assert capture_runtime["topology_epoch"] == 7
    assert set(capture_runtime["active_monitors"]) == {
        "monitor_display-a",
        "monitor_display-b",
    }
    assert capture_runtime["last_capture_outcome"]["outcome"] == "topology_rebuilt"
