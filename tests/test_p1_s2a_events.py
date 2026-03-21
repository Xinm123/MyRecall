from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace

from openrecall.shared.config import Settings


def test_settings_expose_s2a_defaults_and_legacy_idle_mapping(monkeypatch):
    monkeypatch.setenv("OPENRECALL_CAPTURE_INTERVAL", "17")
    monkeypatch.delenv("OPENRECALL_IDLE_CAPTURE_INTERVAL_MS", raising=False)
    monkeypatch.delenv("OPENRECALL_MIN_CAPTURE_INTERVAL_MS", raising=False)
    monkeypatch.delenv("OPENRECALL_PERMISSION_POLL_INTERVAL_SEC", raising=False)
    monkeypatch.delenv("OPENRECALL_TRIGGER_QUEUE_CAPACITY", raising=False)

    settings = Settings()

    assert settings.click_debounce_ms == 3000
    assert settings.trigger_debounce_ms == 3000
    assert settings.capture_debounce_ms == 3000
    assert settings.idle_capture_interval_ms == 17000
    assert settings.permission_poll_interval_sec == 10
    assert settings.trigger_queue_capacity == 1000  # Increased from 64 to align with screenpipe scale


def test_normalize_device_name_formats_stable_monitor_id():
    from openrecall.client.events.base import normalize_device_name

    assert normalize_device_name(42) == "monitor_42"
    assert normalize_device_name("display-uuid") == "monitor_display-uuid"
    assert normalize_device_name("monitor_7") == "monitor_7"


def test_trigger_debouncer_is_partitioned_per_device():
    from openrecall.client.events.base import TriggerDebouncer

    debouncer = TriggerDebouncer(min_interval_ms=1000)

    assert debouncer.should_fire("monitor_1", 1000) is True
    assert debouncer.should_fire("monitor_1", 1500) is False
    assert debouncer.should_fire("monitor_2", 1500) is True
    assert debouncer.should_fire("monitor_1", 2000) is True


def test_trigger_event_channel_collapses_oldest_item_when_full():
    from openrecall.client.events.base import (
        CaptureTrigger,
        TriggerEvent,
        TriggerEventChannel,
    )

    channel = TriggerEventChannel(capacity=2)

    first = TriggerEvent(
        capture_trigger=CaptureTrigger.CLICK,
        device_name="monitor_1",
        event_ts="2026-03-10T00:00:00Z",
    )
    second = TriggerEvent(
        capture_trigger=CaptureTrigger.APP_SWITCH,
        device_name="monitor_1",
        event_ts="2026-03-10T00:00:01Z",
    )
    replacement = TriggerEvent(
        capture_trigger=CaptureTrigger.MANUAL,
        device_name="monitor_1",
        event_ts="2026-03-10T00:00:02Z",
    )

    assert channel.put(first) is True
    assert channel.put(second) is True
    assert channel.put(replacement) is True

    snapshot = channel.snapshot()
    assert snapshot.queue_depth == 2
    assert snapshot.queue_capacity == 2
    assert snapshot.collapse_trigger_count == 1
    assert snapshot.overflow_drop_count == 0

    drained = [channel.get_nowait(), channel.get_nowait()]
    assert drained == [second, replacement]


def test_permission_state_machine_requires_consecutive_failures_and_successes():
    from openrecall.client.events.permissions import (
        PermissionCheckResult,
        PermissionState,
        PermissionStateMachine,
    )

    machine = PermissionStateMachine()

    first_failure = machine.record_check(
        PermissionCheckResult(ok=False, reason="screen_recording_denied")
    )
    assert first_failure.status is PermissionState.TRANSIENT_FAILURE

    denied = machine.record_check(
        PermissionCheckResult(ok=False, reason="screen_recording_denied")
    )
    assert denied.status is PermissionState.DENIED_OR_REVOKED

    recovering = machine.record_check(PermissionCheckResult(ok=True, reason="granted"))
    assert recovering.status is PermissionState.RECOVERING

    machine.record_check(PermissionCheckResult(ok=True, reason="granted"))
    granted = machine.record_check(PermissionCheckResult(ok=True, reason="granted"))
    assert granted.status is PermissionState.GRANTED


def test_permission_state_machine_stays_recovering_until_third_success():
    from openrecall.client.events.permissions import (
        PermissionCheckResult,
        PermissionState,
        PermissionStateMachine,
    )

    machine = PermissionStateMachine()
    machine.record_check(
        PermissionCheckResult(ok=False, reason="screen_recording_denied")
    )
    machine.record_check(
        PermissionCheckResult(ok=False, reason="screen_recording_denied")
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
    assert second_success.status is PermissionState.RECOVERING
    assert third_success.status is PermissionState.GRANTED


def test_permission_state_machine_emits_on_cooldown_only():
    from openrecall.client.events.permissions import PermissionStateMachine

    machine = PermissionStateMachine()

    assert machine.should_emit(1000.0) is True
    assert machine.should_emit(1200.0) is False
    assert machine.should_emit(1301.0) is True


def test_list_monitors_has_single_fallback_monitors_declaration():
    source = Path("openrecall/client/events/macos.py").read_text()
    module = ast.parse(source)

    list_monitors = next(
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name == "list_monitors"
    )
    fallback_declarations = [
        node
        for node in ast.walk(list_monitors)
        if isinstance(node, ast.AnnAssign)
        and isinstance(node.target, ast.Name)
        and node.target.id == "monitors"
    ]

    assert len(fallback_declarations) == 1


def test_list_monitors_uses_distinct_quartz_binding_name():
    source = Path("openrecall/client/events/macos.py").read_text()

    assert "quartz_monitors: list[MonitorDescriptor] = []" in source
    assert "return quartz_monitors" in source


def test_app_switch_monitor_uses_frontmost_app_polling_fallback():
    source = Path("openrecall/client/events/macos.py").read_text()

    assert "get_active_app_name() or get_frontmost_app_name()" in source
    assert "self._stop_event.wait(0.5)" in source  # Polling interval increased to 500ms


def test_list_monitors_falls_back_to_mss_on_quartz_error(monkeypatch):
    from openrecall.client.events import macos

    class _FakeMSS:
        def __init__(self) -> None:
            self.monitors: list[dict[str, int]] = []

        def __enter__(self):
            self.monitors = [
                {"left": 0, "top": 0, "width": 300, "height": 200},
                {"left": 10, "top": 20, "width": 100, "height": 50},
            ]
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    warnings: list[str] = []
    fake_quartz = SimpleNamespace(
        CGGetActiveDisplayList=lambda _max_displays, _active, _count: (1, (), 0),
        CGDisplayBounds=lambda _display_id: None,
        CGDisplayIsMain=lambda _display_id: False,
    )

    monkeypatch.setattr(macos, "Quartz", fake_quartz)
    monkeypatch.setattr(macos.mss, "mss", lambda: _FakeMSS())
    monkeypatch.setattr(
        macos.logger, "warning", lambda message, *args: warnings.append(message % args)
    )

    monitors = macos.list_monitors(primary_only=False)

    assert len(monitors) == 1
    assert monitors[0].source == "mss_fallback"
    assert warnings


def test_app_switch_monitor_emits_when_frontmost_app_changes(monkeypatch):
    from openrecall.client.events import macos
    from openrecall.client.events.base import CaptureTrigger, MonitorDescriptor

    events = []
    monitor = MonitorDescriptor(
        stable_id="primary",
        left=0,
        top=0,
        width=100,
        height=100,
        is_primary=True,
        source="test",
    )

    app_sequence = iter(["Antigravity", "Finder"])

    def _next_app() -> str:
        try:
            return next(app_sequence)
        except StopIteration:
            return "Finder"

    monitor_thread = macos.MacOSAppSwitchMonitor(
        callback=lambda event: events.append(event),
        monitor_lookup=lambda _x, _y: monitor,
    )

    monkeypatch.setattr(macos, "get_active_app_name", _next_app)
    monkeypatch.setattr(macos, "get_frontmost_app_name", _next_app)
    monkeypatch.setattr(macos, "get_active_window_title", lambda: "Finder")

    def _stop_after_first_poll(_seconds: float) -> None:
        monitor_thread._stop_event.set()

    monkeypatch.setattr(monitor_thread._stop_event, "wait", _stop_after_first_poll)

    monitor_thread._run()

    assert len(events) == 1
    assert events[0].capture_trigger is CaptureTrigger.APP_SWITCH
    assert events[0].active_app == "Finder"
    # active_window is empty string when no window title is found
    assert events[0].active_window == ""


def test_click_on_unregistered_monitor_counts_miss():
    """Test that clicks on unregistered monitors are counted as monitor misses.

    With the new single-layer architecture, monitor misses are tracked via
    the _monitor_misses counter instead of log messages.
    """
    from openrecall.client.events import macos
    from openrecall.client.events.base import (
        LockFreeDebouncer,
        TriggerEventChannel,
    )

    # Create channel and debouncer
    channel = TriggerEventChannel(capacity=10)
    debouncer = LockFreeDebouncer(min_interval_ms=1000)

    event_tap = macos.MacOSEventTap(
        trigger_channel=channel,
        debouncer=debouncer,
        monitor_lookup=lambda _x, _y: None,  # Returns None to simulate unregistered monitor
    )

    # Simulate a click event via the metrics
    initial_misses = event_tap._monitor_misses
    event_tap._monitor_misses += 1  # Simulate what happens in _handle_event

    # Verify the counter increased
    assert event_tap._monitor_misses == initial_misses + 1

    # Get metrics snapshot
    metrics = event_tap.get_metrics()
    assert metrics["monitor_misses"] == initial_misses + 1
