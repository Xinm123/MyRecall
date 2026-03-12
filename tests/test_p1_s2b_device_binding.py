from __future__ import annotations

import threading
import time
import queue

import numpy as np
import pytest

import openrecall.client.recorder as recorder_module
from openrecall.client.accessibility.types import (
    AccessibilityRawHandoff,
    FocusedContext,
)
from openrecall.client.accessibility.service import FocusedContextSnapshot
from openrecall.client.events.base import (
    CaptureTrigger,
    MonitorDescriptor,
    TriggerBus,
    TriggerEvent,
    TriggerIntent,
)
from openrecall.client.recorder import MonitorWorker, ScreenRecorder


@pytest.mark.unit
def test_capture_metadata_uses_final_device_name_as_truth() -> None:
    recorder = ScreenRecorder()
    event = TriggerEvent(
        capture_trigger=CaptureTrigger.CLICK,
        device_name="monitor_hint",
        event_ts="2026-03-12T00:00:00Z",
    )
    handoff = AccessibilityRawHandoff(
        accessibility_text="hello",
        content_hash="sha256:" + "1" * 64,
        focused_context=FocusedContext(
            app_name="Google Chrome",
            window_name="Tab",
            browser_url="https://example.com",
        ),
        browser_url_classification="browser_url_success",
        event_device_hint="monitor_hint",
        final_device_name="monitor_final",
        outcome="capture_completed",
    )

    metadata = recorder._build_capture_metadata(
        event,
        context_active_app="Google Chrome",
        context_active_window="Tab",
        raw_handoff=handoff,
    )

    assert metadata["event_device_hint"] == "monitor_hint"
    assert metadata["device_name"] == "monitor_final"
    assert metadata["browser_url_classification"] == "browser_url_success"


@pytest.mark.unit
def test_capture_metadata_includes_runtime_evidence_fields() -> None:
    recorder = ScreenRecorder()
    event = TriggerEvent(
        capture_trigger=CaptureTrigger.CLICK,
        device_name="monitor_hint",
        event_ts="2026-03-12T00:00:00Z",
    )
    handoff = AccessibilityRawHandoff(
        accessibility_text="hello",
        content_hash="sha256:" + "1" * 64,
        focused_context=FocusedContext(
            app_name="Google Chrome",
            window_name="Tab",
            browser_url="https://example.com",
        ),
        browser_url_classification="browser_url_success",
        event_device_hint="monitor_hint",
        final_device_name="monitor_final",
        outcome="capture_completed",
    )

    metadata = recorder._build_capture_metadata(
        event,
        context_active_app="Google Chrome",
        context_active_window="Tab",
        raw_handoff=handoff,
        capture_cycle_latency_ms=137,
        host_pid=4242,
        runtime_started_at="2026-03-12T00:00:00Z",
    )

    assert metadata["capture_cycle_latency_ms"] == 137
    assert metadata["host_pid"] == 4242
    assert metadata["runtime_started_at"] == "2026-03-12T00:00:00Z"


@pytest.mark.unit
def test_dedup_state_is_bucketed_by_final_device_name() -> None:
    worker = MonitorWorker(
        worker_id="monitor_a",
        intent_queue=queue.Queue(),
        process_intent=lambda *_args: None,
    )
    same_hash = "sha256:" + "1" * 64

    worker.record_successful_spool_write(
        final_device_name="monitor_a",
        content_hash=same_hash,
        write_time_epoch=100.0,
    )

    assert (
        worker.should_skip_dedup(
            capture_trigger="click",
            final_device_name="monitor_a",
            content_hash=same_hash,
            now_epoch=129.9,
            permission_blocked=False,
        )
        is True
    )
    assert (
        worker.should_skip_dedup(
            capture_trigger="click",
            final_device_name="monitor_a",
            content_hash=same_hash,
            now_epoch=130.0,
            permission_blocked=False,
        )
        is False
    )
    assert (
        worker.should_skip_dedup(
            capture_trigger="click",
            final_device_name="monitor_b",
            content_hash=same_hash,
            now_epoch=129.9,
            permission_blocked=False,
        )
        is False
    )


@pytest.mark.unit
def test_monitor_worker_owns_dedup_state_per_final_device_name() -> None:
    worker = MonitorWorker(
        worker_id="monitor_1",
        intent_queue=queue.Queue(),
        process_intent=lambda *_args: None,
    )
    same_hash = "sha256:" + "1" * 64

    worker.record_successful_spool_write(
        final_device_name="monitor_1",
        content_hash=same_hash,
        write_time_epoch=100.0,
    )

    assert (
        worker.should_skip_dedup(
            capture_trigger="click",
            final_device_name="monitor_1",
            content_hash=same_hash,
            now_epoch=129.9,
            permission_blocked=False,
        )
        is True
    )
    assert (
        worker.should_skip_dedup(
            capture_trigger="click",
            final_device_name="monitor_2",
            content_hash=same_hash,
            now_epoch=129.9,
            permission_blocked=False,
        )
        is False
    )


@pytest.mark.unit
def test_recorder_dedup_state_moves_from_main_loop_to_monitor_worker() -> None:
    recorder = ScreenRecorder()
    monitor = MonitorDescriptor(
        stable_id="1",
        left=0,
        top=0,
        width=100,
        height=100,
        is_primary=True,
    )
    recorder._sync_trigger_bus_workers([monitor])
    worker = recorder._monitor_workers[monitor.device_name]
    same_hash = "sha256:" + "1" * 64

    worker.record_successful_spool_write(
        final_device_name=monitor.device_name,
        content_hash=same_hash,
        write_time_epoch=100.0,
    )

    assert not hasattr(recorder, "_dedup_state_by_device")
    assert (
        worker.should_skip_dedup(
            capture_trigger="click",
            final_device_name=monitor.device_name,
            content_hash=same_hash,
            now_epoch=129.9,
            permission_blocked=False,
        )
        is True
    )
    recorder.stop()


@pytest.mark.unit
def test_trigger_bus_broadcast_does_not_block_when_one_worker_is_slow() -> None:
    bus = TriggerBus(capacity=1)
    slow_queue = bus.ensure_worker("worker-slow")
    fast_queue = bus.ensure_worker("worker-fast")

    first = TriggerIntent(
        capture_trigger=CaptureTrigger.CLICK,
        event_ts="2026-03-12T00:00:00Z",
        event_device_hint="monitor_1",
    )
    second = TriggerIntent(
        capture_trigger=CaptureTrigger.CLICK,
        event_ts="2026-03-12T00:00:01Z",
        event_device_hint="monitor_1",
    )

    slow_queue.put_nowait(first)
    bus.broadcast(second)

    slow_latest = slow_queue.get_nowait()
    fast_latest = fast_queue.get_nowait()

    assert slow_latest.event_ts == "2026-03-12T00:00:01Z"
    assert fast_latest.event_ts == "2026-03-12T00:00:01Z"


@pytest.mark.unit
def test_monitor_workers_consume_their_trigger_bus_queues(monkeypatch) -> None:
    recorder = ScreenRecorder()
    completed: list[str] = []
    completion_event = threading.Event()

    def _fake_process(
        worker: MonitorWorker, intent: TriggerIntent, dequeued_at: float
    ) -> None:
        _ = intent
        _ = dequeued_at
        completed.append(worker.worker_id)
        if len(completed) >= 2:
            completion_event.set()

    monkeypatch.setattr(recorder, "_process_trigger_intent_for_monitor", _fake_process)

    recorder._sync_trigger_bus_workers(
        [
            MonitorDescriptor(
                stable_id="1",
                left=0,
                top=0,
                width=100,
                height=100,
                is_primary=True,
            ),
            MonitorDescriptor(
                stable_id="2",
                left=100,
                top=0,
                width=100,
                height=100,
                is_primary=False,
            ),
        ]
    )
    intent = TriggerIntent(
        capture_trigger=CaptureTrigger.CLICK,
        event_ts="2026-03-12T00:00:00Z",
        event_device_hint="monitor_1",
    )

    recorder._trigger_bus.broadcast(intent)

    assert completion_event.wait(timeout=1.0)
    assert set(completed) == {"monitor_1", "monitor_2"}
    recorder.stop()


@pytest.mark.unit
def test_slow_monitor_worker_does_not_block_other_workers(monkeypatch) -> None:
    recorder = ScreenRecorder()
    finished: list[str] = []
    fast_done = threading.Event()
    slow_done = threading.Event()

    def _fake_process(
        worker: MonitorWorker, intent: TriggerIntent, dequeued_at: float
    ) -> None:
        _ = intent
        _ = dequeued_at
        if worker.worker_id == "monitor_1":
            time.sleep(0.2)
            finished.append(worker.worker_id)
            slow_done.set()
            return
        finished.append(worker.worker_id)
        fast_done.set()

    monkeypatch.setattr(recorder, "_process_trigger_intent_for_monitor", _fake_process)

    recorder._sync_trigger_bus_workers(
        [
            MonitorDescriptor(
                stable_id="1",
                left=0,
                top=0,
                width=100,
                height=100,
                is_primary=True,
            ),
            MonitorDescriptor(
                stable_id="2",
                left=100,
                top=0,
                width=100,
                height=100,
                is_primary=False,
            ),
        ]
    )
    intent = TriggerIntent(
        capture_trigger=CaptureTrigger.CLICK,
        event_ts="2026-03-12T00:00:00Z",
        event_device_hint="monitor_1",
    )

    started_at = time.perf_counter()
    recorder._trigger_bus.broadcast(intent)

    assert fast_done.wait(timeout=0.5)
    assert not slow_done.is_set()
    assert time.perf_counter() - started_at < 0.2
    assert slow_done.wait(timeout=1.0)
    assert set(finished) == {"monitor_1", "monitor_2"}
    recorder.stop()


@pytest.mark.unit
def test_process_intent_does_not_depend_on_legacy_context_helper(monkeypatch) -> None:
    recorder = ScreenRecorder()
    monitor = MonitorDescriptor(
        stable_id="1",
        left=0,
        top=0,
        width=100,
        height=100,
        is_primary=True,
    )
    recorder._monitor_registry.refresh([monitor])
    worker = MonitorWorker(
        worker_id=monitor.device_name,
        intent_queue=queue.Queue(),
        process_intent=lambda *_args: None,
    )

    monkeypatch.setattr(
        recorder,
        "_snapshot_active_context",
        lambda: (_ for _ in ()).throw(AssertionError("legacy helper should not run")),
    )
    monkeypatch.setattr(
        recorder,
        "_capture_monitors",
        lambda _monitors: {
            monitor.device_name: np.ones((2, 2, 3), dtype=np.uint8) * 255,
        },
    )

    captured_metadata: list[dict[str, object]] = []
    monkeypatch.setattr(
        recorder._spool,
        "enqueue",
        lambda _image, metadata: captured_metadata.append(dict(metadata)),
    )
    monkeypatch.setattr(recorder, "_warn_if_blank_frame", lambda *_args: None)

    class _Service:
        def collect_raw_handoff(self, **_kwargs: object) -> AccessibilityRawHandoff:
            return AccessibilityRawHandoff(
                accessibility_text="ax text",
                content_hash="sha256:" + "1" * 64,
                focused_context=FocusedContext(
                    app_name="AX App",
                    window_name="AX Window",
                    browser_url="https://example.com",
                ),
                browser_url_classification="browser_url_success",
                event_device_hint="monitor_hint",
                final_device_name=monitor.device_name,
                outcome="capture_completed",
            )

    monkeypatch.setattr(recorder, "_accessibility_service", _Service(), raising=False)

    recorder._process_trigger_intent_for_monitor(
        worker,
        TriggerIntent(
            capture_trigger=CaptureTrigger.CLICK,
            event_ts="event-ts",
            event_device_hint="monitor_hint",
            active_app="Legacy App",
            active_window="Legacy Window",
        ),
        time.perf_counter(),
    )

    assert len(captured_metadata) == 1
    assert captured_metadata[0]["app_name"] == "AX App"
    assert captured_metadata[0]["window_name"] == "AX Window"


@pytest.mark.unit
def test_process_intent_keeps_unknown_focused_fields_as_none(monkeypatch) -> None:
    recorder = ScreenRecorder()
    monitor = MonitorDescriptor(
        stable_id="1",
        left=0,
        top=0,
        width=100,
        height=100,
        is_primary=True,
    )
    recorder._monitor_registry.refresh([monitor])
    worker = MonitorWorker(
        worker_id=monitor.device_name,
        intent_queue=queue.Queue(),
        process_intent=lambda *_args: None,
    )

    monkeypatch.setattr(
        recorder,
        "_capture_monitors",
        lambda _monitors: {
            monitor.device_name: np.ones((2, 2, 3), dtype=np.uint8) * 255,
        },
    )
    captured_metadata: list[dict[str, object]] = []
    monkeypatch.setattr(
        recorder._spool,
        "enqueue",
        lambda _image, metadata: captured_metadata.append(dict(metadata)),
    )
    monkeypatch.setattr(recorder, "_warn_if_blank_frame", lambda *_args: None)

    class _Service:
        def collect_raw_handoff(self, **_kwargs: object) -> AccessibilityRawHandoff:
            return AccessibilityRawHandoff(
                accessibility_text="ax text",
                content_hash="sha256:" + "1" * 64,
                focused_context=FocusedContext(
                    app_name=None,
                    window_name=None,
                    browser_url=None,
                ),
                browser_url_classification="browser_url_skipped",
                event_device_hint="monitor_hint",
                final_device_name=monitor.device_name,
                outcome="capture_completed",
            )

    monkeypatch.setattr(recorder, "_accessibility_service", _Service(), raising=False)

    recorder._process_trigger_intent_for_monitor(
        worker,
        TriggerIntent(
            capture_trigger=CaptureTrigger.CLICK,
            event_ts="event-ts",
            event_device_hint="monitor_hint",
            active_app="Legacy App",
            active_window="Legacy Window",
        ),
        time.perf_counter(),
    )

    assert len(captured_metadata) == 1
    assert captured_metadata[0]["app_name"] is None
    assert captured_metadata[0]["window_name"] is None


@pytest.mark.unit
def test_process_intent_uses_capture_snapshot_id_for_browser_coherence(
    monkeypatch,
) -> None:
    recorder = ScreenRecorder()
    monitor = MonitorDescriptor(
        stable_id="1",
        left=0,
        top=0,
        width=100,
        height=100,
        is_primary=True,
    )
    recorder._monitor_registry.refresh([monitor])
    worker = MonitorWorker(
        worker_id=monitor.device_name,
        intent_queue=queue.Queue(),
        process_intent=lambda *_args: None,
    )

    monkeypatch.setattr(recorder_module, "utc_now_iso", lambda: "capture-snapshot")
    monkeypatch.setattr(
        recorder,
        "_capture_monitors",
        lambda _monitors: {
            monitor.device_name: np.ones((2, 2, 3), dtype=np.uint8) * 255,
        },
    )
    monkeypatch.setattr(recorder._spool, "enqueue", lambda *_args: None)
    monkeypatch.setattr(recorder, "_warn_if_blank_frame", lambda *_args: None)
    expected_ax_root = object()
    monkeypatch.setattr(
        recorder_module,
        "get_frontmost_ax_root",
        lambda: expected_ax_root,
        raising=False,
    )

    captured_args: dict[str, object] = {}

    class _Service:
        def collect_raw_handoff(self, **kwargs: object) -> AccessibilityRawHandoff:
            captured_args.update(kwargs)
            return AccessibilityRawHandoff(
                accessibility_text="ax text",
                content_hash="sha256:" + "1" * 64,
                focused_context=FocusedContext(
                    app_name="AX App",
                    window_name="AX Window",
                    browser_url=None,
                ),
                browser_url_classification="browser_url_skipped",
                event_device_hint="monitor_hint",
                final_device_name=monitor.device_name,
                outcome="capture_completed",
            )

    monkeypatch.setattr(recorder, "_accessibility_service", _Service(), raising=False)

    recorder._process_trigger_intent_for_monitor(
        worker,
        TriggerIntent(
            capture_trigger=CaptureTrigger.CLICK,
            event_ts="event-ts",
            event_device_hint="monitor_hint",
        ),
        time.perf_counter(),
    )

    snapshot_obj = captured_args.get("focused_context_snapshot")
    assert isinstance(snapshot_obj, FocusedContextSnapshot)
    assert snapshot_obj.snapshot_id == "capture-snapshot"
    assert (
        captured_args["focused_context_snapshot_id_for_browser"] == "capture-snapshot"
    )
    assert captured_args["ax_root"] is expected_ax_root
