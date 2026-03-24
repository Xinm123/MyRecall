# Fullscreen Window Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix macOS fullscreen window capture — when an app is fullscreened, capture the actual window content instead of the desktop background.

**Architecture:** In `_capture_single_monitor`, detect fullscreen windows via `CGWindowListCopyWindowInfo` + `kCGWindowListOptionAll`, then use `screencapture -l <window_id>` for window-level capture. Fall back to existing `mss` display capture on any failure.

**Tech Stack:** Python only — `subprocess`, `Quartz`/`CGWindowListCopyWindowInfo`, `PIL.Image`, `numpy`.

---

## File Map

| File | Role |
|------|------|
| `openrecall/client/events/macos.py` | Add `get_all_windows_info()` helper (extracts from existing `get_active_app_monitor`) |
| `openrecall/client/recorder.py` | Add `_capture_window_by_id`, `_detect_fullscreen_window_on_monitor`; modify `_capture_single_monitor` |
| `tests/test_p1_s2a_fullscreen_capture.py` | New unit test file |

---

## Verification Script (Before Implementation)

This is a **manual verification** step to confirm the core assumption before writing any production code.

- [x] **Step 1: Verify cross-Space window enumeration**

```python
# Save as ~/tmp/test_window_enum.py and run
import Quartz

options = Quartz.kCGWindowListOptionAll
window_list = Quartz.CGWindowListCopyWindowInfo(options, Quartz.kCGNullWindowID)
print(f"Total windows across all Spaces: {len(window_list)}")
for w in window_list:
    owner = w.get("kCGWindowOwnerName", "")
    layer = w.get("kCGWindowLayer", 0)
    bounds = w.get("kCGWindowBounds", {})
    wnd_id = w.get("kCGWindowNumber", 0)
    if layer == 0 and bounds.get("Width", 0) > 100 and bounds.get("Height", 0) > 100:
        print(f"  [{wnd_id}] {owner} layer={layer} bounds={bounds}")
```

Expected: When a browser tab is fullscreened, this should list the fullscreen window with its `kCGWindowNumber` and bounds matching the display resolution.

---

## Task 1: Extract `get_all_windows_info()` helper in `macos.py`

**Files:**
- Modify: `openrecall/client/events/macos.py:556-589`
- Test: `tests/test_p1_s2a_fullscreen_capture.py`

- [x] **Step 1: Create test file with imports, then write failing test**

Create `tests/test_p1_s2a_fullscreen_capture.py` with file-level imports:

```python
from __future__ import annotations

import os
import subprocess
from unittest.mock import MagicMock, patch

import pytest
from openrecall.client.events.base import MonitorDescriptor


@pytest.mark.unit
def test_get_all_windows_info_returns_list(monkeypatch):
    """get_all_windows_info returns a list of window dicts with required keys."""
    mock_window_list = [
        {
            "kCGWindowNumber": 123,
            "kCGWindowOwnerName": "Arc",
            "kCGWindowLayer": 0,
            "kCGWindowBounds": {"X": 0, "Y": 0, "Width": 2560, "Height": 1600},
            "kCGWindowName": "GitHub",
        },
        {
            "kCGWindowNumber": 456,
            "kCGWindowOwnerName": "Dock",
            "kCGWindowLayer": 0,
            "kCGWindowBounds": {"X": 0, "Y": 1560, "Width": 2560, "Height": 40},
        },
    ]
    monkeypatch.setattr(Quartz, "CGWindowListCopyWindowInfo", lambda *a, **kw: mock_window_list)

    from openrecall.client.events.macos import get_all_windows_info
    windows = get_all_windows_info()

    assert isinstance(windows, list)
    assert len(windows) == 2
    # Each window has required keys
    for w in windows:
        assert "kCGWindowNumber" in w
        assert "kCGWindowOwnerName" in w
        assert "kCGWindowLayer" in w
        assert "kCGWindowBounds" in w


@pytest.mark.unit
def test_get_all_windows_info_returns_empty_on_error(monkeypatch):
    """get_all_windows_info returns [] if CGWindowListCopyWindowInfo fails."""
    import Quartz
    monkeypatch.setattr(Quartz, "CGWindowListCopyWindowInfo", side_effect=Exception("fail"))
    from openrecall.client.events.macos import get_all_windows_info
    windows = get_all_windows_info()
    assert windows == []
```

Run: `pytest tests/test_p1_s2a_fullscreen_capture.py::test_get_all_windows_info_returns_list -v`
Expected: FAIL — `get_all_windows_info` not defined yet

- [x] **Step 2: Write minimal implementation**

In `openrecall/client/events/macos.py`, add new helper **before** `get_active_app_monitor` (around line 543):

```python
def get_all_windows_info() -> list[dict]:
    """Return list of window info dicts for all on-screen windows.

    Uses kCGWindowListOptionAll to include windows on all Spaces.
    Each dict contains: kCGWindowNumber, kCGWindowOwnerName, kCGWindowLayer, kCGWindowBounds, kCGWindowName.

    Returns:
        List of window dicts. Returns [] if Quartz unavailable or call fails.
    """
    if Quartz is None:
        return []

    try:
        cg_window_list = getattr(Quartz, "CGWindowListCopyWindowInfo", None)
        kcg_window_list_option_all = getattr(Quartz, "kCGWindowListOptionAll", None)
        null_window_id = getattr(Quartz, "kCGNullWindowID", None)

        if None in (cg_window_list, kcg_window_list_option_all, null_window_id):
            return []

        return cg_window_list(kcg_window_list_option_all, null_window_id) or []
    except Exception:
        return []
```

- [x] **Step 3: Run tests to verify they pass**

Run: `pytest tests/test_p1_s2a_fullscreen_capture.py -v`
Expected: PASS (or FAIL if other tests not yet written)

- [x] **Step 4: Commit**

```bash
git add openrecall/client/events/macos.py tests/test_p1_s2a_fullscreen_capture.py
git commit -m "feat(macos): extract get_all_windows_info() helper"
```

---

## Task 2: Add `_capture_window_by_id` in `recorder.py`

**Files:**
- Modify: `openrecall/client/recorder.py`
- Test: `tests/test_p1_s2a_fullscreen_capture.py`

- [x] **Step 1: Write failing test**

Append to `tests/test_p1_s2a_fullscreen_capture.py`:

```python
@pytest.mark.unit
def test_capture_window_by_id_returns_numpy_array(monkeypatch, tmp_path):
    """_capture_window_by_id returns a numpy array on success."""
    mock_result = MagicMock()
    mock_result.returncode = 0
    mock_result.stderr = b""

    # Create a real temp JPEG so PIL can open it
    from PIL import Image
    test_img = Image.new("RGB", (100, 100), color="red")
    test_jpg = tmp_path / "cap.jpg"
    test_img.save(str(test_jpg), "JPEG")

    captured_path = None
    def fake_run(cmd, *a, **kw):
        nonlocal captured_path
        captured_path = cmd[-1]
        import shutil
        shutil.copy(str(test_jpg), captured_path)
        return mock_result

    monkeypatch.setattr(subprocess, "run", fake_run)

    from openrecall.client.recorder import ScreenRecorder
    recorder = ScreenRecorder()
    result = recorder._capture_window_by_id(123)

    assert result is not None
    assert isinstance(result, np.ndarray)
    assert result.shape == (100, 100, 3)


@pytest.mark.unit
def test_capture_window_by_id_returns_none_on_failure(monkeypatch):
    """_capture_window_by_id returns None when screencapture fails."""
    import subprocess
    monkeypatch.setattr(subprocess, "run", side_effect=subprocess.TimeoutExpired("screencapture", 5))

    from openrecall.client.recorder import ScreenRecorder
    recorder = ScreenRecorder()
    result = recorder._capture_window_by_id(999)
    assert result is None
```

Run: `pytest tests/test_p1_s2a_fullscreen_capture.py::test_capture_window_by_id_returns_numpy_array -v`
Expected: FAIL — `_capture_window_by_id` not defined yet

- [x] **Step 2: Add imports**

In `recorder.py` imports (around line 1), add:

```python
import subprocess
```

- [x] **Step 3: Add `_capture_window_by_id` method**

Add after `_capture_monitors` (after line 998):

```python
    def _capture_window_by_id(self, window_id: int) -> ImageArray | None:
        """Capture a specific window by its kCGWindowNumber using screencapture CLI.

        Falls back to None on any error (non-zero exit, timeout, permission denied).
        This enables automatic fallback to mss display capture in the caller.

        Args:
            window_id: The kCGWindowNumber of the target window.

        Returns:
            numpy array (BGR order) or None if capture failed.
        """
        tmp_path = "/tmp/myrecall_window_cap.jpg"
        try:
            subprocess.run(
                ["screencapture", "-l", str(window_id), "-x", "-t", "jpg", tmp_path],
                capture_output=True,
                timeout=5,
            )
            if not os.path.exists(tmp_path):
                logger.debug("screencapture produced no output for window_id=%d", window_id)
                return None
            img = Image.open(tmp_path)
            screenshot = np.array(img)[:, :, [2, 1, 0]]
            os.remove(tmp_path)
            return screenshot
        except Exception:
            logger.debug("Window capture failed for window_id=%d", window_id)
            return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_p1_s2a_fullscreen_capture.py::test_capture_window_by_id_returns_numpy_array tests/test_p1_s2a_fullscreen_capture.py::test_capture_window_by_id_returns_none_on_failure -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add openrecall/client/recorder.py tests/test_p1_s2a_fullscreen_capture.py
git commit -m "feat(recorder): add _capture_window_by_id using screencapture"
```

---

## Task 3: Add `_detect_fullscreen_window_on_monitor` in `recorder.py`

**Files:**
- Modify: `openrecall/client/recorder.py`
- Test: `tests/test_p1_s2a_fullscreen_capture.py`

- [x] **Step 1: Write failing test**

```python
SYSTEM_APPS_FULLSCREEN = {
    "Dock", "Window Server", "ControlCenter", "SystemUIServer",
    "NotificationCenter", "loginwindow", "WindowManager", "Contexts", "Screenshot",
}


@pytest.mark.unit
def test_detect_fullscreen_window_returns_id(monkeypatch):
    """_detect_fullscreen_window_on_monitor returns kCGWindowNumber for fullscreen window."""
    mock_windows = [
        {
            "kCGWindowNumber": 123,
            "kCGWindowOwnerName": "Arc",
            "kCGWindowLayer": 0,
            "kCGWindowBounds": {"X": 0, "Y": 0, "Width": 2560, "Height": 1600},
        },
        {
            "kCGWindowNumber": 789,
            "kCGWindowOwnerName": "Dock",
            "kCGWindowLayer": 0,
            "kCGWindowBounds": {"X": 0, "Y": 1560, "Width": 2560, "Height": 40},
        },
    ]
    with patch("openrecall.client.events.macos.get_all_windows_info", return_value=mock_windows):
        from openrecall.client.recorder import ScreenRecorder
        recorder = ScreenRecorder()
        monitor = MonitorDescriptor(stable_id="1", left=0, top=0, width=2560, height=1600, is_primary=True)
        window_id = recorder._detect_fullscreen_window_on_monitor(monitor)
        assert window_id == 123


@pytest.mark.unit
def test_detect_fullscreen_window_returns_none_when_no_fullscreen(monkeypatch):
    """Returns None when no window fills the monitor."""
    mock_windows = [
        {
            "kCGWindowNumber": 200,
            "kCGWindowOwnerName": "Arc",
            "kCGWindowLayer": 0,
            "kCGWindowBounds": {"X": 100, "Y": 100, "Width": 800, "Height": 600},
        },
    ]
    with patch("openrecall.client.events.macos.get_all_windows_info", return_value=mock_windows):
        from openrecall.client.recorder import ScreenRecorder
        recorder = ScreenRecorder()
        monitor = MonitorDescriptor(stable_id="1", left=0, top=0, width=2560, height=1600, is_primary=True)
        window_id = recorder._detect_fullscreen_window_on_monitor(monitor)
        assert window_id is None


@pytest.mark.unit
def test_detect_fullscreen_window_returns_none_for_system_apps(monkeypatch):
    """Returns None for system apps even if they fill the screen."""
    mock_windows = [
        {
            "kCGWindowNumber": 999,
            "kCGWindowOwnerName": "Dock",
            "kCGWindowLayer": 0,
            "kCGWindowBounds": {"X": 0, "Y": 0, "Width": 2560, "Height": 1600},
        },
    ]
    with patch("openrecall.client.events.macos.get_all_windows_info", return_value=mock_windows):
        from openrecall.client.recorder import ScreenRecorder
        recorder = ScreenRecorder()
        monitor = MonitorDescriptor(stable_id="1", left=0, top=0, width=2560, height=1600, is_primary=True)
        window_id = recorder._detect_fullscreen_window_on_monitor(monitor)
        assert window_id is None


@pytest.mark.unit
def test_detect_fullscreen_window_skips_overlay_layers(monkeypatch):
    """Returns None for overlay windows (layer > 0)."""
    mock_windows = [
        {
            "kCGWindowNumber": 500,
            "kCGWindowOwnerName": "Arc",
            "kCGWindowLayer": 25,  # overlay
            "kCGWindowBounds": {"X": 0, "Y": 0, "Width": 2560, "Height": 1600},
        },
    ]
    with patch("openrecall.client.events.macos.get_all_windows_info", return_value=mock_windows):
        from openrecall.client.recorder import ScreenRecorder
        recorder = ScreenRecorder()
        monitor = MonitorDescriptor(stable_id="1", left=0, top=0, width=2560, height=1600, is_primary=True)
        window_id = recorder._detect_fullscreen_window_on_monitor(monitor)
        assert window_id is None
```

Run: `pytest tests/test_p1_s2a_fullscreen_capture.py::test_detect_fullscreen_window_returns_id -v`
Expected: FAIL — `_detect_fullscreen_window_on_monitor` not defined yet

- [x] **Step 2: Add import of helper**

In `recorder.py` (around line 28), add to the `macos` imports:

```python
from openrecall.client.events.macos import (
    get_active_app_monitor,
    get_all_windows_info,
    get_frontmost_app_name,
    list_monitors,
    MacOSAppSwitchMonitor,
    MacOSEventTap,
)
```

- [x] **Step 3: Add `_detect_fullscreen_window_on_monitor` method**

Add after `_capture_window_by_id` (after line ~1025):

```python
    SYSTEM_WINDOW_APPS: frozenset[str] = frozenset({
        "Dock",
        "Window Server",
        "ControlCenter",
        "SystemUIServer",
        "NotificationCenter",
        "loginwindow",
        "WindowManager",
        "Contexts",
        "Screenshot",
    })

    def _detect_fullscreen_window_on_monitor(
        self, monitor: MonitorDescriptor
    ) -> int | None:
        """Detect if there's a fullscreen window on the given monitor.

        Uses get_all_windows_info() to enumerate all windows across Spaces,
        then finds one whose bounds cover ≥95% of the monitor.

        Returns:
            kCGWindowNumber (int) of the fullscreen window, or None.
        """
        try:
            windows = get_all_windows_info()
        except Exception:
            return None

        for window in windows:
            layer = window.get("kCGWindowLayer", 0)
            if layer != 0:
                continue

            owner_name = window.get("kCGWindowOwnerName", "")
            if owner_name in self.SYSTEM_WINDOW_APPS:
                continue

            bounds = window.get("kCGWindowBounds")
            if bounds is None:
                continue

            win_x = bounds.get("X", 0)
            win_y = bounds.get("Y", 0)
            win_w = bounds.get("Width", 0)
            win_h = bounds.get("Height", 0)

            # Fullscreen window: fills ≥95% of monitor
            if (
                win_w >= monitor.width * 0.95
                and win_h >= monitor.height * 0.95
                and abs(win_x - monitor.left) <= 10
                and abs(win_y - monitor.top) <= 10
            ):
                return window.get("kCGWindowNumber")

        return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_p1_s2a_fullscreen_capture.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add openrecall/client/recorder.py tests/test_p1_s2a_fullscreen_capture.py
git commit -m "feat(recorder): add _detect_fullscreen_window_on_monitor"
```

---

## Task 4: Wire fullscreen capture into `_capture_single_monitor`

**Files:**
- Modify: `openrecall/client/recorder.py:882-889`

- [x] **Step 1: Write failing test (integration-level)**

```python
@pytest.mark.unit
def test_capture_single_monitor_uses_window_capture_for_fullscreen(monkeypatch):
    """_capture_single_monitor uses screencapture when fullscreen window detected."""
    from PIL import Image
    import numpy as np

    mock_windows = [
        {
            "kCGWindowNumber": 123,
            "kCGWindowOwnerName": "Arc",
            "kCGWindowLayer": 0,
            "kCGWindowBounds": {"X": 0, "Y": 0, "Width": 2560, "Height": 1600},
        },
    ]

    # Fake screencapture output — blue image, distinct from any mss fallback
    test_img = Image.new("RGB", (2560, 1600), color="blue")
    captured_cmd = [None]  # Track what command was passed to subprocess.run

    def fake_run(cmd, *a, **kw):
        nonlocal captured_cmd
        captured_cmd = cmd
        # Only intercept the screencapture call with -l flag
        if "-l" in cmd:
            test_img.save("/tmp/myrecall_window_cap.jpg", "JPEG")
        return MagicMock(returncode=0, stderr=b"")

    # Use patch() for os.path.exists to avoid global side effects
    # Only let it return True for our known temp file
    real_exists = os.path.exists
    def fake_exists(p):
        if "/tmp/myrecall_window_cap.jpg" in str(p):
            return True
        return real_exists(p)

    with patch("openrecall.client.events.macos.get_all_windows_info", return_value=mock_windows):
        monkeypatch.setattr(subprocess, "run", fake_run)
        monkeypatch.setattr(os.path, "exists", fake_exists)

        from openrecall.client.recorder import ScreenRecorder
        recorder = ScreenRecorder()
        monitor = MonitorDescriptor(stable_id="1", left=0, top=0, width=2560, height=1600, is_primary=True)
        result = recorder._capture_single_monitor(monitor)

        # Strong assertion: screencapture was called with -l 123
        assert captured_cmd[0] == "screencapture"
        assert "-l" in captured_cmd
        assert "123" in captured_cmd
        assert result is not None
        assert isinstance(result, np.ndarray)
        # Pixel at (0,0) should be blue (BGR order = [255, 0, 0])
        assert result[0, 0, 0] == 255   # B channel = 255 (blue)
        assert result[0, 0, 1] == 0     # G channel = 0
        assert result[0, 0, 2] == 0     # R channel = 0
```

Run: `pytest tests/test_p1_s2a_fullscreen_capture.py::test_capture_single_monitor_uses_window_capture_for_fullscreen -v`
Expected: FAIL — `_capture_single_monitor` not modified yet

- [x] **Step 2: Modify `_capture_single_monitor`**

Replace the existing method (lines 882-889):

```python
    def _capture_single_monitor(self, monitor: MonitorDescriptor) -> ImageArray:
        # Try window-level capture for fullscreen windows first
        fullscreen_window_id = self._detect_fullscreen_window_on_monitor(monitor)
        if fullscreen_window_id is not None:
            screenshot = self._capture_window_by_id(fullscreen_window_id)
            if screenshot is not None:
                return screenshot
            # Fall through to mss fallback if screencapture failed

        captures = self._capture_monitors([monitor])
        screenshot = captures.get(monitor.device_name)
        if screenshot is None:
            raise RuntimeError(
                f"capture missing for target monitor {monitor.device_name}"
            )
        return screenshot
```

- [x] **Step 3: Run tests to verify they pass**

Run: `pytest tests/test_p1_s2a_fullscreen_capture.py -v`
Expected: PASS

- [x] **Step 4: Run existing recorder tests to check for regressions**

Run: `pytest tests/test_p1_s2a_recorder.py -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add openrecall/client/recorder.py tests/test_p1_s2a_fullscreen_capture.py
git commit -m "feat(recorder): use screencapture for fullscreen windows with mss fallback"
```

---

## Task 5: Manual Integration Test

**No code changes. Verification only.**

- [x] **Step 1: Run the full test suite**

```bash
pytest tests/test_p1_s2a_fullscreen_capture.py tests/test_p1_s2a_recorder.py -v
```

Expected: All PASS

- [x] **Step 2: Manual verification on macOS**

1. Start Edge server: `./run_server.sh --debug`
2. Start client: `./run_client.sh --debug`
3. Open a browser, navigate to any page
4. Click the browser's fullscreen button (green button → "Enter Full Screen")
5. Wait 30s for capture cycle
6. Check saved frame in `~/MRC/spool/` or `~/MRS/frames/`
7. **Pass criteria**: Frame shows browser content, not just desktop background

- [x] **Step 3: Fallback verification**

1. Temporarily break screencapture: `chmod -x /usr/sbin/screencapture`
2. Trigger a capture (manual trigger or wait for idle)
3. Verify mss fallback still produces frames
4. Restore: `chmod +x /usr/sbin/screencapture`

---

## Summary

| Task | Change |
|------|--------|
| Task 1 | Extract `get_all_windows_info()` from `macos.py` |
| Task 2 | Add `_capture_window_by_id` to `recorder.py` |
| Task 3 | Add `_detect_fullscreen_window_on_monitor` to `recorder.py` |
| Task 4 | Modify `_capture_single_monitor` to use window capture for fullscreen |
| Task 5 | Unit tests + manual integration test |
