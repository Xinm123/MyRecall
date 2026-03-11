from __future__ import annotations

import logging
import threading
from typing import Callable

import mss

from openrecall.client.events.base import (
    CaptureTrigger,
    MonitorDescriptor,
    TriggerEvent,
    utc_now_iso,
)

logger = logging.getLogger(__name__)

try:
    import AppKit
except ImportError:
    AppKit = None

try:
    import Quartz
except ImportError:
    Quartz = None

from openrecall.shared.utils import get_active_app_name, get_active_window_title


def list_monitors(primary_only: bool = False) -> list[MonitorDescriptor]:
    if Quartz is not None:
        get_active_display_list = getattr(Quartz, "CGGetActiveDisplayList", None)
        display_bounds = getattr(Quartz, "CGDisplayBounds", None)
        display_is_main = getattr(Quartz, "CGDisplayIsMain", None)
        if get_active_display_list is not None and display_bounds is not None:
            error_code, active_displays, _ = get_active_display_list(32, None, None)
            if error_code == 0:
                quartz_monitors: list[MonitorDescriptor] = []
                for display_id in active_displays:
                    bounds = display_bounds(display_id)
                    is_primary = (
                        bool(display_is_main(display_id)) if display_is_main else False
                    )
                    descriptor = MonitorDescriptor(
                        stable_id=str(display_id),
                        left=int(bounds.origin.x),
                        top=int(bounds.origin.y),
                        width=int(bounds.size.width),
                        height=int(bounds.size.height),
                        is_primary=is_primary,
                        source="quartz",
                    )
                    quartz_monitors.append(descriptor)

                if primary_only:
                    return [
                        monitor for monitor in quartz_monitors if monitor.is_primary
                    ][:1]
                return quartz_monitors

            logger.warning(
                "CGGetActiveDisplayList failed with error code %s; falling back to mss",
                error_code,
            )

    monitors: list[MonitorDescriptor] = []
    with mss.mss() as sct:
        for index, monitor in enumerate(sct.monitors[1:], start=1):
            descriptor = MonitorDescriptor(
                stable_id=f"fallback_{monitor['left']}_{monitor['top']}_{monitor['width']}_{monitor['height']}",
                left=int(monitor["left"]),
                top=int(monitor["top"]),
                width=int(monitor["width"]),
                height=int(monitor["height"]),
                is_primary=index == 1,
                source="mss_fallback",
            )
            monitors.append(descriptor)
        if primary_only:
            return monitors[:1]
    return monitors


class MacOSEventTap:
    def __init__(
        self,
        callback: Callable[[TriggerEvent], None],
        monitor_lookup: Callable[[float, float], MonitorDescriptor | None],
    ) -> None:
        self._callback = callback
        self._monitor_lookup = monitor_lookup
        self._event_tap = None
        self._run_loop_source = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="MacOSEventTap"
        )
        self._thread.start()

    def _run(self) -> None:
        if Quartz is None:
            logger.warning("CGEventTap unavailable; click listener disabled")
            return

        event_tap_create = getattr(Quartz, "CGEventTapCreate", None)
        event_mask_bit = getattr(Quartz, "CGEventMaskBit", None)
        run_loop_source = getattr(Quartz, "CFMachPortCreateRunLoopSource", None)
        run_loop_get_current = getattr(Quartz, "CFRunLoopGetCurrent", None)
        run_loop_add_source = getattr(Quartz, "CFRunLoopAddSource", None)
        run_loop_run = getattr(Quartz, "CFRunLoopRun", None)
        session_event_tap = getattr(Quartz, "kCGSessionEventTap", None)
        head_insert_event_tap = getattr(Quartz, "kCGHeadInsertEventTap", None)
        tap_option_listen_only = getattr(Quartz, "kCGEventTapOptionListenOnly", None)
        left_mouse_down = getattr(Quartz, "kCGEventLeftMouseDown", None)
        right_mouse_down = getattr(Quartz, "kCGEventRightMouseDown", None)
        other_mouse_down = getattr(Quartz, "kCGEventOtherMouseDown", None)
        run_loop_default_mode = getattr(Quartz, "kCFRunLoopDefaultMode", None)

        if None in {
            event_tap_create,
            event_mask_bit,
            run_loop_source,
            run_loop_get_current,
            run_loop_add_source,
            session_event_tap,
            head_insert_event_tap,
            tap_option_listen_only,
            left_mouse_down,
            right_mouse_down,
            other_mouse_down,
            run_loop_default_mode,
            run_loop_run,
        }:
            logger.warning(
                "Quartz event tap symbols unavailable; click listener disabled"
            )
            return

        assert event_tap_create is not None
        assert event_mask_bit is not None
        assert run_loop_source is not None
        assert run_loop_get_current is not None
        assert run_loop_add_source is not None
        assert session_event_tap is not None
        assert head_insert_event_tap is not None
        assert tap_option_listen_only is not None
        assert left_mouse_down is not None
        assert right_mouse_down is not None
        assert other_mouse_down is not None
        assert run_loop_default_mode is not None
        assert run_loop_run is not None

        event_mask = (
            event_mask_bit(left_mouse_down)
            | event_mask_bit(right_mouse_down)
            | event_mask_bit(other_mouse_down)
        )
        self._event_tap = event_tap_create(
            session_event_tap,
            head_insert_event_tap,
            tap_option_listen_only,
            event_mask,
            self._handle_event,
            None,
        )
        if self._event_tap is None:
            logger.warning("Unable to create CGEventTap; click listener disabled")
            return

        self._run_loop_source = run_loop_source(
            None,
            self._event_tap,
            0,
        )
        run_loop_add_source(
            run_loop_get_current(),
            self._run_loop_source,
            run_loop_default_mode,
        )
        run_loop_run()

    def _handle_event(self, _proxy, event_type, event, _refcon):
        if Quartz is None:
            return event

        left_mouse_down = getattr(Quartz, "kCGEventLeftMouseDown", None)
        right_mouse_down = getattr(Quartz, "kCGEventRightMouseDown", None)
        other_mouse_down = getattr(Quartz, "kCGEventOtherMouseDown", None)
        event_get_location = getattr(Quartz, "CGEventGetLocation", None)

        if event_type not in {
            left_mouse_down,
            right_mouse_down,
            other_mouse_down,
        }:
            return event
        if event_get_location is None:
            return event

        location = event_get_location(event)
        monitor = self._monitor_lookup(location.x, location.y)
        if monitor is None:
            logger.debug(
                "dropped click trigger: no registered monitor matched point x=%.1f y=%.1f",
                location.x,
                location.y,
            )
            return event
        active_app = get_frontmost_app_name() or None
        active_window = get_active_window_title() or None
        self._callback(
            TriggerEvent(
                capture_trigger=CaptureTrigger.CLICK,
                device_name=monitor.device_name,
                event_ts=utc_now_iso(),
                active_app=active_app,
                active_window=active_window,
            )
        )
        return event


def emit_app_switch(
    callback: Callable[[TriggerEvent], None], monitor: MonitorDescriptor
) -> None:
    callback(
        TriggerEvent(
            capture_trigger=CaptureTrigger.APP_SWITCH,
            device_name=monitor.device_name,
            event_ts=utc_now_iso(),
        )
    )


class MacOSAppSwitchMonitor:
    def __init__(
        self,
        callback: Callable[[TriggerEvent], None],
        monitor_provider: Callable[[], MonitorDescriptor | None],
    ) -> None:
        self._callback = callback
        self._monitor_provider = monitor_provider
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_frontmost_app: str = ""

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            daemon=True,
            name="MacOSAppSwitchMonitor",
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    def _run(self) -> None:
        if AppKit is None:
            logger.warning("NSWorkspace unavailable; app switch listener disabled")
            return
        self._last_frontmost_app = get_active_app_name() or get_frontmost_app_name()
        while not self._stop_event.is_set():
            current_app = get_active_app_name() or get_frontmost_app_name()
            if (
                current_app
                and self._last_frontmost_app
                and current_app != self._last_frontmost_app
            ):
                self._emit_app_switch(current_app)
            self._last_frontmost_app = current_app or self._last_frontmost_app
            self._stop_event.wait(0.2)

    def _emit_app_switch(self, active_app: str) -> None:
        monitor = self._monitor_provider()
        if monitor is None:
            return
        active_window = get_active_window_title() or None
        self._callback(
            TriggerEvent(
                capture_trigger=CaptureTrigger.APP_SWITCH,
                device_name=monitor.device_name,
                event_ts=utc_now_iso(),
                active_app=active_app,
                active_window=active_window,
            )
        )


def get_frontmost_app_name() -> str:
    if AppKit is None:
        return ""
    try:
        workspace_class = getattr(AppKit, "NSWorkspace", None)
        if workspace_class is None:
            return ""
        frontmost = workspace_class.sharedWorkspace().frontmostApplication()
        if frontmost is None:
            return ""
        return str(frontmost.localizedName() or "")
    except Exception:
        logger.exception("Failed to query frontmost application")
        return ""
