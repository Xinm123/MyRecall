from __future__ import annotations

import logging
import time

import numpy as np
import pytest

from openrecall.client.events.base import (
    CaptureTrigger,
    MonitorDescriptor,
    RoutedCaptureTask,
    TriggerEvent,
)
from openrecall.client.hash_utils import SimhashCache, is_similar
from openrecall.client.recorder import ScreenRecorder
from openrecall.shared.config import settings


def _run_two_frame_capture(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    *,
    heartbeat_interval_sec: float,
    inter_event_sleep_sec: float,
) -> list[dict[str, object]]:
    recorder = ScreenRecorder()
    monitor = MonitorDescriptor("monitor_display-a", 0, 0, 100, 100, is_primary=True)
    routed_task = RoutedCaptureTask(
        capture_trigger=CaptureTrigger.MANUAL,
        target_device_name=monitor.device_name,
        routing_topology_epoch=1,
        event_ts="2026-03-16T00:00:00Z",
        routing_hints={"focused_device_name": monitor.device_name},
    )
    frame = np.zeros((32, 32, 3), dtype=np.uint8)
    enqueued: list[dict[str, object]] = []
    event_count = {"value": 0}

    monkeypatch.setattr(settings, "simhash_dedup_enabled", True, raising=False)
    monkeypatch.setattr(settings, "simhash_dedup_threshold", 8, raising=False)
    monkeypatch.setattr(
        settings,
        "simhash_heartbeat_interval_sec",
        heartbeat_interval_sec,
        raising=False,
    )
    monkeypatch.setattr(settings, "client_save_local_screenshots", False, raising=False)

    monkeypatch.setattr(recorder, "start", lambda: None)
    monkeypatch.setattr(recorder, "_start_event_sources", lambda: None)
    monkeypatch.setattr(recorder, "_poll_permissions", lambda *, now_epoch: None)
    monkeypatch.setattr(recorder, "_send_heartbeat", lambda **kwargs: None)
    monkeypatch.setattr(
        recorder._permission_state_machine, "is_degraded", lambda: False
    )

    def _refresh_monitors() -> list[MonitorDescriptor]:
        recorder._monitor_registry.refresh([monitor])
        recorder._enabled_monitor_devices = {monitor.device_name}
        return [monitor]

    monkeypatch.setattr(recorder, "_refresh_monitors", _refresh_monitors)

    def _wait_for_trigger(**kwargs: object) -> TriggerEvent:
        idx = event_count["value"]
        event_count["value"] += 1
        if idx == 1 and inter_event_sleep_sec > 0:
            time.sleep(inter_event_sleep_sec)
        if idx >= 1:
            recorder._stop_requested = True
        return TriggerEvent(
            capture_trigger=CaptureTrigger.MANUAL,
            device_name=monitor.device_name,
            event_ts="2026-03-16T00:00:00Z",
        )

    monkeypatch.setattr(recorder, "_wait_for_trigger", _wait_for_trigger)
    monkeypatch.setattr(recorder, "_route_trigger", lambda event: [routed_task])
    monkeypatch.setattr(recorder, "_validate_routed_task", lambda task: True)
    monkeypatch.setattr(recorder._monitor_registry, "get", lambda _name: monitor)
    monkeypatch.setattr(
        recorder, "_capture_single_monitor", lambda _monitor: frame.copy()
    )
    monkeypatch.setattr(
        recorder, "_snapshot_active_context", lambda: ("Finder", "Desktop", "monitor_1")
    )
    monkeypatch.setattr(recorder, "_warn_if_blank_frame", lambda *args, **kwargs: None)

    monkeypatch.setattr(
        recorder._spool,
        "enqueue",
        lambda image, metadata: enqueued.append(dict(metadata)),
    )
    monkeypatch.setattr(recorder._spool, "count", lambda: len(enqueued))

    with caplog.at_level(logging.INFO):
        recorder.run_capture_loop()

    return enqueued


@pytest.mark.unit
def test_acceptance_4_1_similar_frames_are_skipped_and_logged(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    enqueued = _run_two_frame_capture(
        monkeypatch,
        caplog,
        heartbeat_interval_sec=300.0,
        inter_event_sleep_sec=0.0,
    )

    assert len(enqueued) == 1
    assert "MRV3 similar_frame_skipped device_name=monitor_display-a" in caplog.text


@pytest.mark.unit
def test_acceptance_4_2_heartbeat_timeout_forces_enqueue(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    enqueued = _run_two_frame_capture(
        monkeypatch,
        caplog,
        heartbeat_interval_sec=0.001,
        inter_event_sleep_sec=0.02,
    )

    assert len(enqueued) == 2


@pytest.mark.unit
def test_acceptance_4_3_gate_slo_thresholds_for_detection_and_volume() -> None:
    threshold = 8

    similar_pairs = [(0, 1 << (i % 8)) for i in range(20)]
    dissimilar_pairs = [(0, (0x1FF << (i % 4))) for i in range(20)]

    tp = tn = fp = fn = 0
    for left, right in similar_pairs:
        if is_similar(left, right, threshold):
            tp += 1
        else:
            fn += 1
    for left, right in dissimilar_pairs:
        if is_similar(left, right, threshold):
            fp += 1
        else:
            tn += 1

    total = tp + tn + fp + fn
    accuracy = (tp + tn) / total
    skip_accuracy = tp / (tp + fp)
    misdrop_rate = fp / (tn + fp)

    assert accuracy >= 0.95
    assert skip_accuracy >= 0.95
    assert misdrop_rate <= 0.05

    cache = SimhashCache(cache_size_per_device=1)
    event_times = [0.0, 1.0, 2.0, 3.0, 4.0, 6.0, 7.0, 8.0, 12.0, 13.0]
    heartbeat_interval = 5.0
    accepted = 0
    dropped = 0

    for now in event_times:
        phash = 0xABC
        similar = cache.is_similar_to_cache("monitor_display-a", phash, threshold)
        last_enqueue = cache.get_last_enqueue_time("monitor_display-a")
        heartbeat_timed_out = last_enqueue is None or (
            now - last_enqueue >= heartbeat_interval
        )
        should_enqueue = (not similar) or heartbeat_timed_out
        if should_enqueue:
            accepted += 1
            cache.add("monitor_display-a", phash, timestamp=now)
        else:
            dropped += 1

    storage_saving_rate = dropped / (accepted + dropped)
    assert storage_saving_rate > 0.5
