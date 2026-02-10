"""Phase 2 tests: AudioManager (low-level capture)."""

import sys
import types
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

# Ensure sounddevice is importable (stub if not installed)
if "sounddevice" not in sys.modules:
    _sd_stub = types.ModuleType("sounddevice")
    _sd_stub.query_devices = MagicMock()
    _sd_stub.InputStream = MagicMock()
    sys.modules["sounddevice"] = _sd_stub


class TestListAudioDevices:
    """Tests for list_audio_devices()."""

    @patch("sounddevice.query_devices")
    def test_returns_input_devices(self, mock_query):
        mock_query.return_value = [
            {"name": "Mic 1", "max_input_channels": 2, "max_output_channels": 0, "default_samplerate": 44100.0},
            {"name": "Speaker", "max_input_channels": 0, "max_output_channels": 2, "default_samplerate": 48000.0},
            {"name": "Mic 2", "max_input_channels": 1, "max_output_channels": 0, "default_samplerate": 16000.0},
        ]
        from openrecall.client.audio_manager import list_audio_devices

        devices = list_audio_devices()
        assert len(devices) == 2
        assert devices[0]["name"] == "Mic 1"
        assert devices[0]["channels"] == 2
        assert devices[1]["name"] == "Mic 2"

    @patch("sounddevice.query_devices", side_effect=Exception("no audio"))
    def test_returns_empty_on_error(self, mock_query):
        from openrecall.client.audio_manager import list_audio_devices

        devices = list_audio_devices()
        assert devices == []


class TestAudioManager:
    """Tests for AudioManager class."""

    def test_init_defaults(self, tmp_path):
        from openrecall.client.audio_manager import AudioManager

        mgr = AudioManager(device_name="test", output_dir=tmp_path)
        assert mgr.device_name == "test"
        assert mgr.sample_rate == 16000
        assert mgr.channels == 1
        assert mgr.chunk_duration == 60
        assert mgr.output_dir == tmp_path

    def test_is_alive_false_when_not_started(self, tmp_path):
        from openrecall.client.audio_manager import AudioManager

        mgr = AudioManager(device_name="test", output_dir=tmp_path)
        assert not mgr.is_alive()

    @patch("sounddevice.query_devices")
    def test_resolve_device_by_index(self, mock_query, tmp_path):
        mock_query.return_value = [
            {"name": "Mic", "max_input_channels": 1, "max_output_channels": 0, "default_samplerate": 16000.0},
        ]
        from openrecall.client.audio_manager import AudioManager

        mgr = AudioManager(device_name="0", output_dir=tmp_path)
        idx = mgr._resolve_device()
        assert idx == 0

    @patch("sounddevice.query_devices")
    def test_resolve_device_by_name(self, mock_query, tmp_path):
        mock_query.return_value = [
            {"name": "Output Only", "max_input_channels": 0, "max_output_channels": 2, "default_samplerate": 48000.0},
            {"name": "Built-in Microphone", "max_input_channels": 2, "max_output_channels": 0, "default_samplerate": 44100.0},
        ]
        from openrecall.client.audio_manager import AudioManager

        mgr = AudioManager(device_name="microphone", output_dir=tmp_path)
        idx = mgr._resolve_device()
        assert idx == 1

    @patch("sounddevice.query_devices")
    def test_resolve_device_not_found(self, mock_query, tmp_path):
        mock_query.return_value = [
            {"name": "Speaker", "max_input_channels": 0, "max_output_channels": 2, "default_samplerate": 48000.0},
        ]
        from openrecall.client.audio_manager import AudioManager

        mgr = AudioManager(device_name="nonexistent", output_dir=tmp_path)
        idx = mgr._resolve_device()
        assert idx is None

    def test_start_new_chunk_creates_wav(self, tmp_path):
        from openrecall.client.audio_manager import AudioManager

        mgr = AudioManager(device_name="test_dev", output_dir=tmp_path)
        mgr._start_new_chunk()

        assert mgr._current_path is not None
        assert mgr._current_path.exists()
        assert mgr._current_path.suffix == ".wav"
        assert "test_dev" in mgr._current_path.name
        assert mgr._frames_written == 0

        # Verify WAV parameters
        mgr._current_wav.close()
        with wave.open(str(mgr._current_path), "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 16000

    def test_close_chunk_fires_callback(self, tmp_path):
        from openrecall.client.audio_manager import AudioManager

        callback_events = []
        mgr = AudioManager(
            device_name="test",
            output_dir=tmp_path,
            on_chunk_complete=lambda p, d: callback_events.append((p, d)),
        )
        mgr._start_new_chunk()

        # Write some audio data
        fake_audio = np.zeros(1600, dtype=np.int16)
        mgr._current_wav.writeframes(fake_audio.tobytes())
        mgr._frames_written = 1600

        mgr._close_current_chunk(notify=True)
        assert len(callback_events) == 1
        assert callback_events[0][0].exists()
        assert callback_events[0][1] >= 0.0

    def test_close_empty_chunk_removes_file(self, tmp_path):
        from openrecall.client.audio_manager import AudioManager

        mgr = AudioManager(device_name="test", output_dir=tmp_path)
        mgr._start_new_chunk()
        chunk_path = mgr._current_path

        mgr._close_current_chunk(notify=True)
        # Empty chunk (header only, 44 bytes) should be removed
        assert not chunk_path.exists()

    def test_audio_callback_writes_frames(self, tmp_path):
        from openrecall.client.audio_manager import AudioManager

        mgr = AudioManager(device_name="test", output_dir=tmp_path)
        mgr._start_new_chunk()
        mgr._recording = True

        fake_data = np.zeros((1600, 1), dtype=np.int16)
        mgr._audio_callback(fake_data, 1600, None, None)

        assert mgr._frames_written == 1600

        mgr._close_current_chunk(notify=False)

    def test_audio_callback_rotates_on_duration(self, tmp_path):
        from openrecall.client.audio_manager import AudioManager

        rotated_events = []
        mgr = AudioManager(
            device_name="test",
            output_dir=tmp_path,
            chunk_duration=1,  # 1 second for fast rotation
            on_chunk_complete=lambda p, d: rotated_events.append((p, d)),
        )
        mgr._start_new_chunk()
        mgr._recording = True

        # Write enough frames to exceed 1s (16000 samples at 16kHz)
        fake_data = np.zeros((16000, 1), dtype=np.int16)
        mgr._audio_callback(fake_data, 16000, None, None)

        # Should have rotated
        assert len(rotated_events) == 1
        assert rotated_events[0][0].exists()
        assert rotated_events[0][1] >= 0.0
        assert mgr._frames_written == 0  # Reset after rotation

        mgr._close_current_chunk(notify=False)

    def test_stop_flushes_chunk(self, tmp_path):
        from openrecall.client.audio_manager import AudioManager

        flushed_events = []
        mgr = AudioManager(
            device_name="test",
            output_dir=tmp_path,
            on_chunk_complete=lambda p, d: flushed_events.append((p, d)),
        )
        mgr._start_new_chunk()
        mgr._recording = True

        # Write some data
        fake_data = np.zeros((1600, 1), dtype=np.int16)
        mgr._audio_callback(fake_data, 1600, None, None)

        # Mock stream
        mgr._stream = MagicMock()
        mgr.stop()

        assert not mgr._recording
        assert len(flushed_events) == 1
        assert flushed_events[0][0].exists()
        assert flushed_events[0][1] >= 0.0
