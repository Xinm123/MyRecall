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

`_record_frame` is called per-monitor, so fullscreen detection and capture are **per-monitor**. On a multi-monitor setup, each monitor is evaluated independently.

```
_record_frame(trigger, monitor):
  1. Try to detect fullscreen window on this monitor
     → CGWindowListCopyWindowInfo with kCGWindowListOptionAll
     → find window whose bounds ≈ monitor bounds (≥95% width/height)
     → extract kCGWindowNumber

  2. If fullscreen window found:
     → screencapture -l<window_id> -x -t jpg /tmp/cap.jpg   (5s timeout)
     → PIL.Image.open → numpy array (BGR)
     → if screencapture fails (any reason) or returns None → fallback to mss
     → save frame

  3. If no fullscreen window:
     → continue using existing mss display capture
```

**Timeout:** `subprocess.run(..., timeout=5)` — 5 seconds. Prevents blocking the capture loop. `screencapture` is fast (~5-30ms) but permission-denied or hung scenarios must not stall captures.

**Image format:** `-t jpg` is specified (matches project's JPEG contract). If format support varies by macOS version, PIL can re-encode from PNG as fallback (detect via `tmp_path` extension). `screencapture` without `-t` defaults to PNG.

### Fallback Chain

```
Per monitor capture:
  1. screencapture -l <window_id>   (for fullscreen windows, 5s timeout)
     ↓ if subprocess fails (non-zero exit, timeout, permission denied)
  2. mss display capture             (existing behavior, unchanged)
```

`_capture_window_by_id` returns `None` on **any** subprocess error (exit code != 0, timeout, `OSError`, `subprocess.TimeoutExpired`). This makes the fallback automatic — no caller needs to distinguish error types.

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
- Filters system apps: `Dock`, `Window Server`, `ControlCenter`, `SystemUIServer`, `NotificationCenter`, `loginwindow`, `WindowManager`, `Contexts`, `Screenshot`
- Checks if window bounds ≥ 95% of monitor dimensions
- Returns `kCGWindowNumber` or `None`

### 3. `openrecall/client/recorder.py` — Modified: `_record_frame`

Modified to call `_detect_fullscreen_window_on_monitor` before capture. If a fullscreen window is found, uses `_capture_window_by_id` instead of `_capture_monitors`.

### 4. `openrecall/client/events/macos.py` — Reuse existing `CGWindowListCopyWindowInfo`

The existing code at lines 556-589 already uses `CGWindowListCopyWindowInfo`. Extract window info extraction logic into a standalone helper function in `macos.py` (e.g., `get_all_windows_info()`) returning a list of window dicts with `kCGWindowNumber`, `kCGWindowOwnerName`, `kCGWindowLayer`, `kCGWindowBounds`. Both `get_active_app_monitor` and `_detect_fullscreen_window_on_monitor` call this helper.

## Risk: Cross-Space Window Enumeration

`CGWindowListCopyWindowInfo` with `kCGWindowListOptionAll` may not enumerate windows on all Spaces depending on macOS version and TCC permissions. **This is the primary risk.**

**Mitigation:** If `CGWindowListCopyWindowInfo` returns no windows in the fullscreen region, `_detect_fullscreen_window_on_monitor` returns `None` and we fall back to `mss` display capture. No functionality is lost.

**screencapture failure:** If the window is detected but `screencapture` fails (exit code != 0, timeout, permission denied), `_capture_window_by_id` returns `None` and the caller falls back to `mss`. Both failure modes are silent — the capture loop continues without error.

**Verification test:** Write a test script that enters fullscreen in an app and checks whether `CGWindowListCopyWindowInfo` enumerates the fullscreen window.

## Data Flow (unchanged)

All frame metadata (timestamp, app_name, window_title, etc.) remains unchanged. Only the pixel capture path differs for fullscreen windows.

## Testing

1. **Unit test** (`tests/test_p1_s2a_trigger_coverage.py` or new file): Mock `CGWindowListCopyWindowInfo` response with fullscreen window data, verify correct `window_id` is returned and `None` is returned when no fullscreen window exists
2. **Integration test**: Manual test procedure:
   - Start MyRecall client and server
   - Open a browser, navigate to any page
   - Click the browser's fullscreen button (green button → "Enter Full Screen")
   - Wait 10s for capture cycle
   - Check the saved frame: if it shows browser content → fix works; if only desktop → fix not working
3. **Fallback test**: Temporarily break `screencapture` (e.g., `chmod -x`), trigger capture, verify `mss` fallback still produces frames

## Relationship to screenpipe

screenpipe uses `sck-rs` (ScreenCaptureKit) / `xcap` for window-level capture. Our approach achieves the same result using macOS built-in `screencapture` CLI, with no new dependencies. This is a pragmatic alternative to PyO3 bindings for screenpipe's Rust capture code.
