"""Tests for SCK delayed fallback policy in VideoRecorder."""

import importlib
import time
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def recorder(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENRECALL_SERVER_DATA_DIR", str(tmp_path / "MRS"))
    monkeypatch.setenv("OPENRECALL_CLIENT_DATA_DIR", str(tmp_path / "MRC"))
    monkeypatch.setenv("OPENRECALL_SCK_START_RETRY_MAX", "2")
    monkeypatch.setenv("OPENRECALL_SCK_RETRY_BACKOFF_SECONDS", "1")
    monkeypatch.setenv("OPENRECALL_SCK_PERMISSION_BACKOFF_SECONDS", "30")

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
    recorder._legacy_ffmpeg.is_alive.return_value = False
    return recorder


def test_retry_exhaustion_switches_to_legacy(recorder):
    from openrecall.client.sck_stream import SCKStreamError
    from openrecall.client.video_recorder import CaptureModeState

    error = SCKStreamError(code="display_not_found", detail="display missing", retryable=True)
    with patch.object(recorder, "_discover_target_monitors", return_value=([], error)):
        assert recorder._attempt_sck_start_once(force=True) is False
        assert recorder._capture_state == CaptureModeState.SCK_DEGRADED_RETRYING
        assert recorder._use_legacy_mode is False

        assert recorder._attempt_sck_start_once(force=True) is False
        assert recorder._capture_state == CaptureModeState.LEGACY_ACTIVE
        assert recorder._use_legacy_mode is True
        recorder._legacy_ffmpeg.start.assert_called_once()


def test_permission_denied_uses_long_backoff_before_fallback(recorder):
    from openrecall.client.sck_stream import SCKStreamError
    from openrecall.client.video_recorder import CaptureModeState

    error = SCKStreamError(code="permission_denied", detail="not authorized", retryable=True)
    with patch.object(recorder, "_discover_target_monitors", return_value=([], error)):
        now = time.time()
        assert recorder._attempt_sck_start_once(force=True) is False

    assert recorder._capture_state == CaptureModeState.SCK_DEGRADED_RETRYING
    assert recorder._use_legacy_mode is False
    assert recorder._next_sck_retry_at >= now + 29
    recorder._legacy_ffmpeg.start.assert_not_called()
