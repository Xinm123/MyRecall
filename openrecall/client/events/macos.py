from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Callable

import mss

from openrecall.client.events.base import (
    CaptureTrigger,
    EventTapMetrics,
    MonitorDescriptor,
    RawClickEvent,
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

from openrecall.shared.utils import (
    get_active_app_name,
    get_active_window_title,
    get_active_window_title_for_app,
)


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
    """macOS event tap for click detection with lock-free callback.

    Architecture:
    - CGEventTap callback (in CGEventTap thread): Only captures coordinates
      and puts RawClickEvent into a queue - NO LOCKS, completely non-blocking.
    - Processor thread: Pulls raw events, does monitor lookup (which may need
      locks), and invokes the callback with full TriggerEvent.

    This prevents the system lag caused by blocking operations in the CGEventTap
    callback, which runs on a high-priority system thread.
    """

    def __init__(
        self,
        callback: Callable[[TriggerEvent], None],
        monitor_lookup: Callable[[float, float], MonitorDescriptor | None],
    ) -> None:
        self._callback = callback
        self._monitor_lookup = monitor_lookup
        self._event_tap = None
        self._run_loop_source = None
        self._run_loop = None
        self._event_tap_thread: threading.Thread | None = None

        # Lock-free raw event queue (put_nowait is non-blocking)
        # Increased from 256 to 1024 to reduce event drops during high-frequency operations
        self._raw_click_queue: queue.Queue[RawClickEvent] = queue.Queue(maxsize=1024)
        self._stop_event = threading.Event()
        self._processor_thread: threading.Thread | None = None

        # Observability metrics
        self._metrics = EventTapMetrics()

        # Cache Quartz constants to avoid getattr in callback
        if Quartz is not None:
            self._quartz_left_mouse_up = getattr(Quartz, "kCGEventLeftMouseUp", None)
            self._quartz_right_mouse_up = getattr(Quartz, "kCGEventRightMouseUp", None)
            self._quartz_other_mouse_up = getattr(Quartz, "kCGEventOtherMouseUp", None)
            self._quartz_event_get_location = getattr(Quartz, "CGEventGetLocation", None)
        else:
            self._quartz_left_mouse_up = None
            self._quartz_right_mouse_up = None
            self._quartz_other_mouse_up = None
            self._quartz_event_get_location = None

    @property
    def metrics(self) -> EventTapMetrics:
        """Access to observability metrics."""
        return self._metrics

    def start(self) -> None:
        """Start the event tap and processor thread."""
        if self._processor_thread is not None and self._processor_thread.is_alive():
            return

        # Start processor thread first (handles raw events)
        self._stop_event.clear()
        self._processor_thread = threading.Thread(
            target=self._process_raw_events,
            daemon=True,
            name="ClickEventProcessor",
        )
        self._processor_thread.start()

        # Then start CGEventTap thread
        self._event_tap_thread = threading.Thread(
            target=self._run_event_tap, daemon=True, name="MacOSEventTap"
        )
        self._event_tap_thread.start()

    def stop(self) -> None:
        """Stop event tap and processor thread gracefully.

        Cleanup order (critical for macOS):
        1. Signal stop to threads
        2. Disable CGEventTap BEFORE removing from RunLoop
        3. Stop RunLoop
        4. Remove RunLoop source
        5. Invalidate (release) the CFMachPort
        6. Wait for threads
        """
        self._stop_event.set()

        if Quartz is not None:
            # Step 1: Disable event tap FIRST to stop receiving new events
            if self._event_tap is not None:
                try:
                    cg_event_tap_enable = getattr(Quartz, "CGEventTapEnable", None)
                    if cg_event_tap_enable is not None:
                        cg_event_tap_enable(self._event_tap, False)
                except Exception as e:
                    logger.debug("Error disabling CGEventTap: %s", e)

            # Step 2: Stop the RunLoop so it exits the run loop
            if self._run_loop is not None:
                try:
                    cf_run_loop_stop = getattr(Quartz, "CFRunLoopStop", None)
                    if cf_run_loop_stop is not None:
                        cf_run_loop_stop(self._run_loop)
                except Exception as e:
                    logger.debug("Error stopping RunLoop: %s", e)

            # Step 3: Remove source from RunLoop
            if self._run_loop is not None and self._run_loop_source is not None:
                try:
                    run_loop_remove_source = getattr(Quartz, "CFRunLoopRemoveSource", None)
                    run_loop_default_mode = getattr(Quartz, "kCFRunLoopDefaultMode", None)
                    if run_loop_remove_source is not None and run_loop_default_mode is not None:
                        run_loop_remove_source(
                            self._run_loop,
                            self._run_loop_source,
                            run_loop_default_mode,
                        )
                except Exception as e:
                    logger.debug("Error removing RunLoop source: %s", e)

            # Step 4: Invalidate (release) the CFMachPort - critical for complete cleanup
            if self._event_tap is not None:
                try:
                    cf_mach_port_invalidate = getattr(Quartz, "CFMachPortInvalidate", None)
                    if cf_mach_port_invalidate is not None:
                        cf_mach_port_invalidate(self._event_tap)
                except Exception as e:
                    logger.debug("Error invalidating CFMachPort: %s", e)
                finally:
                    self._event_tap = None

            self._run_loop_source = None
            self._run_loop = None

        # Step 5: Wait for processor thread (increased timeout)
        if self._processor_thread is not None and self._processor_thread.is_alive():
            self._processor_thread.join(timeout=2.0)

        # Step 6: Wait for CGEventTap thread (increased timeout)
        if self._event_tap_thread is not None and self._event_tap_thread.is_alive():
            self._event_tap_thread.join(timeout=2.0)

        logger.info("CGEventTap stopped and resources released")

    def _process_raw_events(self) -> None:
        """Processor thread: handles raw click events from queue.

        This thread does the heavy lifting (monitor lookup, callback invocation)
        so the CGEventTap callback never blocks.
        """
        while not self._stop_event.is_set():
            try:
                # Get raw event with timeout to allow checking stop flag
                raw_event = self._raw_click_queue.get(timeout=0.05)
            except queue.Empty:
                continue

            start_time = time.time()
            try:
                # Monitor lookup (lock-free with Copy-on-Write registry)
                monitor = self._monitor_lookup(raw_event.x, raw_event.y)
                if monitor is None:
                    logger.debug(
                        "dropped click trigger: no monitor for point x=%.1f y=%.1f",
                        raw_event.x,
                        raw_event.y,
                    )
                    self._metrics.record_monitor_miss()
                    continue

                # Invoke callback with full TriggerEvent
                self._callback(
                    TriggerEvent(
                        capture_trigger=CaptureTrigger.CLICK,
                        device_name=monitor.device_name,
                        event_ts=raw_event.event_ts,
                        active_app=None,
                        active_window=None,
                    )
                )

                # Record processing latency
                latency_ms = (time.time() - start_time) * 1000
                self._metrics.record_processed(latency_ms)
            except Exception:
                logger.debug("Error processing raw click event", exc_info=True)

    def _run_event_tap(self) -> None:
        """Run CGEventTap in its own thread."""
        if Quartz is None:
            logger.warning("CGEventTap unavailable; click listener disabled")
            return

        event_tap_create = getattr(Quartz, "CGEventTapCreate", None)
        event_mask_bit = getattr(Quartz, "CGEventMaskBit", None)
        run_loop_source = getattr(Quartz, "CFMachPortCreateRunLoopSource", None)
        run_loop_get_current = getattr(Quartz, "CFRunLoopGetCurrent", None)
        run_loop_add_source = getattr(Quartz, "CFRunLoopAddSource", None)
        run_loop_run_in_mode = getattr(Quartz, "CFRunLoopRunInMode", None)
        session_event_tap = getattr(Quartz, "kCGSessionEventTap", None)
        tail_append_event_tap = getattr(Quartz, "kCGTailAppendEventTap", None)
        tap_option_listen_only = getattr(Quartz, "kCGEventTapOptionListenOnly", None)
        left_mouse_up = getattr(Quartz, "kCGEventLeftMouseUp", None)
        right_mouse_up = getattr(Quartz, "kCGEventRightMouseUp", None)
        other_mouse_up = getattr(Quartz, "kCGEventOtherMouseUp", None)
        run_loop_default_mode = getattr(Quartz, "kCFRunLoopDefaultMode", None)

        if None in {
            event_tap_create,
            event_mask_bit,
            run_loop_source,
            run_loop_get_current,
            run_loop_add_source,
            session_event_tap,
            tail_append_event_tap,
            tap_option_listen_only,
            left_mouse_up,
            right_mouse_up,
            other_mouse_up,
            run_loop_default_mode,
            run_loop_run_in_mode,
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
        assert tail_append_event_tap is not None
        assert tap_option_listen_only is not None
        assert left_mouse_up is not None
        assert right_mouse_up is not None
        assert other_mouse_up is not None
        assert run_loop_default_mode is not None
        assert run_loop_run_in_mode is not None

        event_mask = (
            event_mask_bit(left_mouse_up)
            | event_mask_bit(right_mouse_up)
            | event_mask_bit(other_mouse_up)
        )
        self._event_tap = event_tap_create(
            session_event_tap,
            tail_append_event_tap,
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
        self._run_loop = run_loop_get_current()
        run_loop_add_source(
            self._run_loop,
            self._run_loop_source,
            run_loop_default_mode,
        )
        logger.debug("CGEventTap started with TailAppend placement")

        # Run with timeout to allow checking stop flag
        while not self._stop_event.is_set():
            run_loop_run_in_mode(run_loop_default_mode, 0.05, False)

    def _handle_event(self, _proxy, event_type, event, _refcon):
        """CGEventTap callback - MUST be non-blocking.

        This runs on a high-priority system thread. ANY blocking operation
        (lock acquisition, I/O, sleep) will cause system lag.

        We only capture coordinates and put them in a queue - no locks needed.
        Metrics are updated inline (simple counter increments are atomic in Python).
        """
        # Quick filter for mouse up events
        if event_type not in {
            self._quartz_left_mouse_up,
            self._quartz_right_mouse_up,
            self._quartz_other_mouse_up,
        }:
            return event
        if self._quartz_event_get_location is None:
            return event

        try:
            # Get click location
            location = self._quartz_event_get_location(event)

            # Create minimal raw event - no locks, no monitor lookup
            raw_event = RawClickEvent(
                x=float(location.x),
                y=float(location.y),
                event_ts=utc_now_iso(),
            )

            # Non-blocking put - drops event if queue full rather than block
            self._raw_click_queue.put_nowait(raw_event)
            # Simple counter increment - atomic, no lock needed for just incrementing
            self._metrics.raw_events_received += 1
        except queue.Full:
            # Queue full - drop event rather than block
            self._metrics.raw_events_dropped += 1
        except Exception:
            # Never propagate exceptions in callback
            pass

        return event


def get_mouse_location() -> tuple[float, float] | None:
    """Get current mouse cursor position."""
    if Quartz is None:
        return None
    try:
        create_source = getattr(Quartz, "CGEventSourceCreate", None)
        hid_state = getattr(Quartz, "kCGEventSourceStateHIDSystemState", None)
        create_event = getattr(Quartz, "CGEventCreate", None)
        get_location = getattr(Quartz, "CGEventGetLocation", None)

        if None in (create_source, hid_state, create_event, get_location):
            return None

        event_source = create_source(hid_state)  # type: ignore[misc]
        if event_source is None:
            return None
        event = create_event(event_source)  # type: ignore[misc]
        if event is None:
            return None
        point = get_location(event)  # type: ignore[misc]
        return (float(point.x), float(point.y))
    except Exception:
        logger.debug("Failed to get mouse location")
        return None


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
    """Monitor for application switches using polling.

    Note: NSWorkspace notifications require an active NSApplication event loop
    to dispatch notifications. For background daemon processes without a GUI,
    polling is the most reliable approach with minimal CPU overhead.
    """

    def __init__(
        self,
        callback: Callable[[TriggerEvent], None],
        monitor_lookup: Callable[[float, float], MonitorDescriptor | None],
    ) -> None:
        self._callback = callback
        self._monitor_lookup = monitor_lookup
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
        logger.info("App switch monitor started in polling mode")

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
            self._stop_event.wait(0.5)  # Polling interval: 500ms (reduced from 200ms for lower CPU)

    def _emit_app_switch(self, active_app: str) -> None:
        monitor = None
        
        # Try to find which monitor actually contains the active app's window
        all_monitors = list_monitors(primary_only=False)
        if all_monitors:
            monitor = get_active_app_monitor(all_monitors, target_app_name=active_app)
            
        # Fallback to mouse position if app monitor couldn't be determined
        if monitor is None:
            mouse_pos = get_mouse_location()
            if mouse_pos is not None:
                monitor = self._monitor_lookup(mouse_pos[0], mouse_pos[1])

        device_name = monitor.device_name if monitor else ""
        active_window = get_active_window_title_for_app(active_app)

        self._callback(
            TriggerEvent(
                capture_trigger=CaptureTrigger.APP_SWITCH,
                device_name=device_name,
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


def get_active_app_monitor(
    monitors: list[MonitorDescriptor],
    target_app_name: str | None = None,
) -> MonitorDescriptor | None:
    if Quartz is None:
        return None

    active_app = (
        target_app_name or get_active_app_name() or get_frontmost_app_name()
    )
    if not active_app:
        return None

    try:
        cg_window_list = getattr(Quartz, "CGWindowListCopyWindowInfo", None)
        on_screen_only = getattr(Quartz, "kCGWindowListOptionOnScreenOnly", None)
        null_window_id = getattr(Quartz, "kCGNullWindowID", None)

        if None in (cg_window_list, on_screen_only, null_window_id):
            return None

        window_list = cg_window_list(on_screen_only, null_window_id)  # type: ignore[misc]

        for window in window_list:
            owner_name = window.get("kCGWindowOwnerName")
            if owner_name != active_app:
                continue

            layer = window.get("kCGWindowLayer")
            if layer != 0:
                continue

            bounds = window.get("kCGWindowBounds")
            if bounds is None:
                continue

            center_x = bounds.get("X", 0) + bounds.get("Width", 0) / 2
            center_y = bounds.get("Y", 0) + bounds.get("Height", 0) / 2

            for monitor in monitors:
                if monitor.contains_point(center_x, center_y):
                    return monitor

        return None
    except Exception:
        logger.debug("Failed to get active app monitor")
        return None
