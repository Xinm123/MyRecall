"""Tests for automatic recovery probe from legacy mode."""

import importlib
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def recorder(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "MRS"))
    monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "MRC"))
    monkeypatch.setenv("OPENRECALL_SCK_RECOVERY_PROBE_SECONDS", "1")
    monkeypatch.setenv("OPENRECALL_SCK_AUTO_RECOVER_FROM_LEGACY", "true")

    import openrecall.shared.config
    importlib.reload(openrecall.shared.config)

    import openrecall.client.video_recorder
    importlib.reload(openrecall.client.video_recorder)

    from openrecall.client.video_recorder import VideoRecorder

    mock_buffer = MagicMock()
    mock_consumer = MagicMock()
    mock_consumer.is_alive.return_value = False

    recorder = VideoRecorder(buffer=mock_buffer, consumer=mock_consumer)
    recorder._legacy_ffmpeg = MagicMock()
    return recorder


def _make_monitor():
    from openrecall.client.sck_stream import MonitorInfo

    return MonitorInfo(
        monitor_id="1",
        name="display-1",
        width=1512,
        height=982,
        is_primary=True,
        backend="sck",
        fingerprint="1512x982:1",
        source_index=1,
    )


def test_recovery_probe_switches_back_to_sck_on_success(recorder):
    from openrecall.client.video_recorder import CaptureModeState

    recorder._capture_state = CaptureModeState.LEGACY_ACTIVE
    recorder._use_legacy_mode = True
    recorder._legacy_probe_at = 0.0
    recorder._legacy_ffmpeg.is_alive.return_value = True

    with patch.object(recorder, "_discover_target_monitors", return_value=([_make_monitor()], None)):
        with patch.object(recorder, "_start_monitor_capture", return_value=True) as mock_start:
            recorder._try_recover_from_legacy()

    assert recorder._capture_state == CaptureModeState.SCK_ACTIVE
    assert recorder._use_legacy_mode is False
    recorder._legacy_ffmpeg.stop.assert_called_once()
    mock_start.assert_called_once()


def test_recovery_probe_keeps_legacy_on_failure(recorder):
    from openrecall.client.video_recorder import CaptureModeState

    recorder._capture_state = CaptureModeState.LEGACY_ACTIVE
    recorder._use_legacy_mode = True
    recorder._legacy_probe_at = 0.0
    recorder._legacy_ffmpeg.is_alive.return_value = False

    with patch.object(recorder, "_discover_target_monitors", return_value=([_make_monitor()], None)):
        with patch.object(recorder, "_start_monitor_capture", return_value=False):
            recorder._try_recover_from_legacy()

    assert recorder._capture_state == CaptureModeState.LEGACY_ACTIVE
    assert recorder._use_legacy_mode is True
    recorder._legacy_ffmpeg.start.assert_called_once()
