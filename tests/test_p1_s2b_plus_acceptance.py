from __future__ import annotations

import logging

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
    trigger_type: CaptureTrigger = CaptureTrigger.MANUAL,
) -> list[dict[str, object]]:
    """Run a two-frame capture simulation for testing.

    Args:
        monkeypatch: pytest monkeypatch fixture
        caplog: pytest log capture fixture
        trigger_type: The capture trigger type to simulate
    """
    recorder = ScreenRecorder()
    monitor = MonitorDescriptor("monitor_display-a", 0, 0, 100, 100, is_primary=True)
    routed_task = RoutedCaptureTask(
        capture_trigger=trigger_type,
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
    # Set low debounce to test phash dedup without interference
    monkeypatch.setattr(settings, "click_debounce_ms", 0, raising=False)
    monkeypatch.setattr(settings, "trigger_debounce_ms", 0, raising=False)
    monkeypatch.setattr(settings, "capture_debounce_ms", 0, raising=False)
    # Note: simhash_enabled_for_click and simhash_enabled_for_app_switch
    # should be set by the caller before invoking this function
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
        if idx >= 1:
            recorder._stop_event.set()
        return TriggerEvent(
            capture_trigger=trigger_type,
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
    """Test that similar frames are skipped and logged for CLICK trigger with simhash enabled."""
    monkeypatch.setattr(settings, "simhash_enabled_for_click", True, raising=False)
    monkeypatch.setattr(settings, "simhash_enabled_for_app_switch", True, raising=False)

    enqueued = _run_two_frame_capture(
        monkeypatch,
        caplog,
        trigger_type=CaptureTrigger.CLICK,
    )

    # First frame enqueued, second skipped due to similarity
    assert len(enqueued) == 1
    assert "MRV3 phash_dropped device=monitor_display-a" in caplog.text


@pytest.mark.unit
def test_acceptance_4_2_idle_always_enqueues(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that IDLE trigger always enqueues, skipping simhash check."""
    monkeypatch.setattr(settings, "simhash_enabled_for_click", True, raising=False)
    monkeypatch.setattr(settings, "simhash_enabled_for_app_switch", True, raising=False)

    enqueued = _run_two_frame_capture(
        monkeypatch,
        caplog,
        trigger_type=CaptureTrigger.IDLE,
    )

    # Both frames should be enqueued because IDLE skips simhash
    assert len(enqueued) == 2


@pytest.mark.unit
def test_acceptance_4_3_simhash_disabled_for_trigger(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that frames are enqueued when simhash is disabled for the trigger type.

    Note: Content exact dedup (Layer 1) still applies, so identical content frames
    will still be deduplicated even when simhash (Layer 2) is disabled.
    """
    # Disable simhash for CLICK
    monkeypatch.setattr(settings, "simhash_enabled_for_click", False, raising=False)
    monkeypatch.setattr(settings, "simhash_enabled_for_app_switch", True, raising=False)

    enqueued = _run_two_frame_capture(
        monkeypatch,
        caplog,
        trigger_type=CaptureTrigger.CLICK,
    )

    # Only 1 frame because content exact dedup still applies
    # (simhash disabled only skips visual similarity check, not content identity)
    assert len(enqueued) == 1


@pytest.mark.unit
def test_acceptance_4_4_gate_slo_thresholds_for_detection_and_volume() -> None:
    """Test simhash detection accuracy meets SLO thresholds."""
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


@pytest.mark.unit
def test_acceptance_4_5_storage_saving_rate() -> None:
    """Test that simhash achieves reasonable storage saving rate."""
    cache = SimhashCache(cache_size_per_device=1)
    event_times = [0.0, 1.0, 2.0, 3.0, 4.0, 6.0, 7.0, 8.0, 12.0, 13.0]
    threshold = 8
    accepted = 0
    dropped = 0

    for now in event_times:
        phash = 0xABC  # Same hash each time
        similar = cache.is_similar_to_cache("monitor_display-a", phash, threshold)

        # Without heartbeat, we only enqueue when not similar
        should_enqueue = not similar
        if should_enqueue:
            accepted += 1
            cache.add("monitor_display-a", phash, timestamp=now)
        else:
            dropped += 1

    # First event is accepted, rest are dropped (same hash)
    storage_saving_rate = dropped / (accepted + dropped)
    assert storage_saving_rate >= 0.8  # At least 80% storage saved
    assert accepted == 1  # Only the first frame is accepted
    assert dropped == 9  # All subsequent similar frames are dropped
