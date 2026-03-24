from __future__ import annotations

import os
import subprocess
from unittest.mock import MagicMock, patch

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
