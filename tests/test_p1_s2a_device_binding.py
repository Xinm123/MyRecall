from __future__ import annotations

import numpy as np
import pytest

from openrecall.client.events.base import (
    CaptureTrigger,
    MonitorDescriptor,
    MonitorRegistry,
    TriggerEvent,
)
from openrecall.client.recorder import ScreenRecorder


@pytest.mark.unit
def test_device_name_mapping_stays_stable_across_monitor_reorder() -> None:
    registry = MonitorRegistry()
    first = [
        MonitorDescriptor("display-a", 0, 0, 100, 100, is_primary=True),
        MonitorDescriptor("display-b", 100, 0, 100, 100),
    ]
    reordered = [
        MonitorDescriptor("display-b", 100, 0, 100, 100),
        MonitorDescriptor("display-a", 0, 0, 100, 100, is_primary=True),
    ]

    initial = registry.refresh(first)
    refreshed = registry.refresh(reordered)

    assert set(initial) == {"monitor_display-a", "monitor_display-b"}
    assert registry.snapshot() == {
        "monitor_display-a": "display-a",
        "monitor_display-b": "display-b",
    }
    assert refreshed == initial


@pytest.mark.unit
def test_refresh_monitors_rebuilds_partition_state_when_monitor_set_changes(
    monkeypatch,
) -> None:
    recorder = ScreenRecorder()
    recorder._warned_blank_devices.add("monitor_display-a")
    recorder.emit_manual_trigger(
        device_name="monitor_display-a",
        now_ms=1000,
        event_ts="2026-03-10T00:00:00Z",
    )

    monitor_rounds = iter(
        [
            [MonitorDescriptor("display-a", 0, 0, 100, 100, is_primary=True)],
            [MonitorDescriptor("display-c", 0, 0, 100, 100, is_primary=True)],
        ]
    )
    monkeypatch.setattr(
        "openrecall.client.recorder.list_monitors",
        lambda _primary_only: next(monitor_rounds),
    )

    first = recorder._refresh_monitors()
    second = recorder._refresh_monitors()

    assert first[0].device_name == "monitor_display-a"
    assert second[0].device_name == "monitor_display-c"
    assert recorder._warned_blank_devices == set()
    assert (
        recorder.emit_manual_trigger(
            device_name="monitor_display-c",
            now_ms=1500,
            event_ts="2026-03-10T00:00:00.500Z",
        )
        is True
    )


@pytest.mark.unit
def test_recorder_skips_cross_device_pairing_when_trigger_device_is_unavailable(
    monkeypatch,
) -> None:
    recorder = ScreenRecorder()
    monitor = MonitorDescriptor("display-a", 0, 0, 100, 100, is_primary=True)
    captured_metadata: list[dict[str, str]] = []

    monkeypatch.setattr(recorder, "start", lambda: None)
    monkeypatch.setattr(recorder, "_start_event_sources", lambda: None)
    monkeypatch.setattr(recorder, "_poll_permissions", lambda *, now_epoch: None)
    monkeypatch.setattr(recorder, "_send_heartbeat", lambda **kwargs: None)
    monkeypatch.setattr(
        recorder._permission_state_machine,
        "is_degraded",
        lambda: False,
    )
    monkeypatch.setattr(recorder, "_refresh_monitors", lambda: [monitor])
    monkeypatch.setattr(
        recorder,
        "_wait_for_trigger",
        lambda **kwargs: TriggerEvent(
            capture_trigger=CaptureTrigger.CLICK,
            device_name="monitor_display-b",
            event_ts="2026-03-10T00:00:00Z",
        ),
    )

    def _capture_monitors(_monitors):
        recorder._stop_requested = True
        return {monitor.device_name: np.zeros((2, 2, 3), dtype=np.uint8)}

    monkeypatch.setattr(recorder, "_capture_monitors", _capture_monitors)
    monkeypatch.setattr(
        recorder._spool,
        "enqueue",
        lambda image, metadata: captured_metadata.append(metadata),
    )

    recorder.run_capture_loop()

    assert captured_metadata == []
