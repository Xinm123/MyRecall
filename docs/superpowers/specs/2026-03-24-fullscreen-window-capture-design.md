# Fix Fullscreen Window Capture on macOS

**Date:** 2026-03-24
**Status:** Approved
**Reference:** Aligns with screenpipe's window-level capture approach

## Context

On macOS, when an app enters fullscreen mode (via the green button), the system moves the window to a **separate virtual Space**. The current screenshot capture uses `mss` library which calls `CGDisplayCreateImage` — a **display-level** API that only reads the framebuffer of the **currently active Space**. This means fullscreen apps on separate Spaces are invisible to the capture, resulting in screenshots showing only the desktop background.

**Observed behavior:** When a browser tab is fullscreened, MyRecall captures only the desktop background with "Screen 1" label — no actual app content.

## Decision

Use `screencapture -l <window_id>` (macOS built-in CLI) as a fallback when fullscreen windows are detected on a monitor. This provides window-level capture that bypasses the Space limitation.

## Root Cause Analysis

```
Current capture path:
  mss.grab(monitor_bounds)
    → CGDisplayCreateImage(display_id)
    → reads display framebuffer
    → only shows current Space's content
    → fullscreen window on separate Space → INVISIBLE

Fix: screencapture path:
  CGWindowListCopyWindowInfo → get kCGWindowNumber of fullscreen window
    → screencapture -l<window_id>
    → reads window pixel buffer directly
    → no Space dependency
```

## Architecture

### Capture Strategy

```
_record_frame(trigger, monitor):
  1. Try to detect fullscreen window on this monitor
     → CGWindowListCopyWindowInfo with kCGWindowListOptionAll
     → find window whose bounds ≈ monitor bounds (≥95% width/height)
     → extract kCGWindowNumber

  2. If fullscreen window found:
     → screencapture -l<window_id> -x -t jpg /tmp/cap.jpg
     → PIL.Image.open → numpy array (BGR)
     → save frame
     → else fallback to mss display capture

  3. If no fullscreen window:
     → continue using existing mss display capture
```

### Fallback Chain

```
Capture attempt:
  1. screencapture -l <window_id>   (for fullscreen windows)
     ↓ if fails
  2. mss display capture             (existing behavior)
```

### Permission

`/usr/sbin/screencapture` requires Screen Recording permission — same as `mss`. If `mss` works, `screencapture` will too. No new TCC permissions needed.

## Components

### 1. `openrecall/client/recorder.py` — New method: `_capture_window_by_id`

```python
def _capture_window_by_id(window_id: int) -> ImageArray | None:
    """Capture a specific window by its kCGWindowNumber using screencapture CLI.

    Args:
        window_id: The kCGWindowNumber of the target window.

    Returns:
        numpy array (BGR order) or None if capture failed.
    """
```

Uses `subprocess.run(["screencapture", "-l", str(window_id), "-x", "-t", "jpg", tmp_path])`. Falls back to `None` on error (non-blocking, ~5-30ms timeout).

### 2. `openrecall/client/recorder.py` — New method: `_detect_fullscreen_window_on_monitor`

```python
def _detect_fullscreen_window_on_monitor(
    self, monitor: MonitorDescriptor
) -> int | None:
    """Detect if there's a fullscreen window on the given monitor.

    Uses CGWindowListCopyWindowInfo to enumerate all windows (across Spaces)
    and find one whose bounds cover ≥95% of the monitor.

    Returns:
        kCGWindowNumber (int) of the fullscreen window, or None.
    """
```

Key logic:
- Uses `kCGWindowListOptionAll` to include windows on all Spaces
- Filters `kCGWindowLayer == 0` (normal windows, not overlay)
- Filters system apps (Dock, Window Server, ControlCenter, etc.)
- Checks if window bounds ≥ 95% of monitor dimensions

### 3. `openrecall/client/recorder.py` — Modified: `_record_frame`

Modified to call `_detect_fullscreen_window_on_monitor` before capture. If a fullscreen window is found, uses `_capture_window_by_id` instead of `_capture_monitors`.

### 4. `openrecall/client/events/macos.py` — Reuse existing `CGWindowListCopyWindowInfo`

The existing code at lines 556-589 already uses `CGWindowListCopyWindowInfo`. Extract window info extraction logic into a reusable helper.

## Risk: Cross-Space Window Enumeration

`CGWindowListCopyWindowInfo` with `kCGWindowListOptionAll` may not enumerate windows on all Spaces depending on macOS version and TCC permissions. **This is the primary risk.**

**Mitigation:** If `CGWindowListCopyWindowInfo` returns no windows in the fullscreen region, the method returns `None` and we fall back to `mss` display capture. No functionality is lost.

**Verification test:** Write a test script that enters fullscreen in an app and checks whether `CGWindowListCopyWindowInfo` enumerates the fullscreen window.

## Data Flow (unchanged)

All frame metadata (timestamp, app_name, window_title, etc.) remains unchanged. Only the pixel capture path differs for fullscreen windows.

## Testing

1. **Unit test**: Mock `CGWindowListCopyWindowInfo` response with fullscreen window data, verify correct `window_id` is returned
2. **Integration test**: Manual test — fullscreen a browser tab, verify screenshot contains actual content not just desktop
3. **Fallback test**: If `screencapture` fails, verify `mss` fallback still works

## Relationship to screenpipe

screenpipe uses `sck-rs` (ScreenCaptureKit) / `xcap` for window-level capture. Our approach achieves the same result using macOS built-in `screencapture` CLI, with no new dependencies. This is a pragmatic alternative to PyO3 bindings for screenpipe's Rust capture code.
