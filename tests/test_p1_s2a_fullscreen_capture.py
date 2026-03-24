from __future__ import annotations

import os
import subprocess
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from openrecall.client.events.base import MonitorDescriptor

# Import Quartz at module level for monkeypatching
import Quartz


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
    for w in windows:
        assert "kCGWindowNumber" in w
        assert "kCGWindowOwnerName" in w
        assert "kCGWindowLayer" in w
        assert "kCGWindowBounds" in w


@pytest.mark.unit
def test_get_all_windows_info_returns_empty_on_error(monkeypatch):
    """get_all_windows_info returns [] if CGWindowListCopyWindowInfo fails."""
    def raises(*a, **kw):
        raise Exception("fail")
    monkeypatch.setattr(Quartz, "CGWindowListCopyWindowInfo", raises)
    from openrecall.client.events.macos import get_all_windows_info
    windows = get_all_windows_info()
    assert windows == []


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
    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: (_ for _ in ()).throw(subprocess.TimeoutExpired("screencapture", 5)))

    from openrecall.client.recorder import ScreenRecorder
    recorder = ScreenRecorder()
    result = recorder._capture_window_by_id(999)
    assert result is None
