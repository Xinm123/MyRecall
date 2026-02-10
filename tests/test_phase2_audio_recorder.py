"""Phase 2 tests: AudioRecorder (producer with buffer integration)."""

import hashlib
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


def _create_wav(path: Path, duration_s: float = 1.0, sr: int = 16000) -> Path:
    """Create a minimal WAV file with silence."""
    n_samples = int(sr * duration_s)
    audio = np.zeros(n_samples, dtype=np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(audio.tobytes())
    return path


class TestAudioRecorder:
    """Tests for AudioRecorder class."""

    @patch("openrecall.shared.config.settings")
    def test_init_defaults(self, mock_settings):
        mock_settings.audio_enabled = True
        mock_buffer = MagicMock()
        from openrecall.client.audio_recorder import AudioRecorder

        rec = AudioRecorder(buffer=mock_buffer)
        assert rec.buffer is mock_buffer
        assert rec._running is False
        assert rec._managers == []

    @patch("openrecall.shared.config.settings")
    def test_is_running_false_when_stopped(self, mock_settings):
        from openrecall.client.audio_recorder import AudioRecorder

        rec = AudioRecorder(buffer=MagicMock())
        assert not rec.is_running()

    @patch("openrecall.shared.config.settings")
    def test_stop_when_not_running(self, mock_settings):
        from openrecall.client.audio_recorder import AudioRecorder

        rec = AudioRecorder(buffer=MagicMock())
        # Should not raise
        rec.stop()

    def test_on_chunk_complete_enqueues_with_metadata(self, tmp_path):
        wav_path = _create_wav(tmp_path / "test.wav", duration_s=1.0)
        mock_buffer = MagicMock()
        mock_buffer.enqueue_file.return_value = "item-id-123456789012345678"

        with patch("openrecall.client.audio_recorder.settings") as mock_settings:
            mock_settings.audio_chunk_duration = 60
            mock_settings.audio_sample_rate = 16000
            mock_settings.audio_channels = 1
            mock_settings.audio_format = "wav"
            from openrecall.client.audio_recorder import AudioRecorder

            rec = AudioRecorder(buffer=mock_buffer)
            rec._on_chunk_complete(wav_path, "test_mic", actual_duration=1.0)

        mock_buffer.enqueue_file.assert_called_once()
        call_args = mock_buffer.enqueue_file.call_args
        file_path_arg = call_args[0][0]
        metadata_arg = call_args[0][1]

        assert file_path_arg == str(wav_path)
        assert metadata_arg["type"] == "audio_chunk"
        assert metadata_arg["device_name"] == "test_mic"
        assert metadata_arg["sample_rate"] == 16000
        assert metadata_arg["channels"] == 1
        assert metadata_arg["format"] == "wav"
        assert metadata_arg["checksum"].startswith("sha256:")
        assert isinstance(metadata_arg["timestamp"], (int, float))
        assert "file_size_bytes" in metadata_arg
        assert metadata_arg["end_time"] >= metadata_arg["start_time"]
        assert metadata_arg["end_time"] - metadata_arg["start_time"] == pytest.approx(
            1.0, rel=1e-3
        )

    def test_on_chunk_complete_correct_checksum(self, tmp_path):
        wav_path = _create_wav(tmp_path / "test.wav", duration_s=0.5)
        mock_buffer = MagicMock()
        mock_buffer.enqueue_file.return_value = "item-id-123456789012345678"

        # Compute expected checksum
        h = hashlib.sha256()
        with open(wav_path, "rb") as f:
            for block in iter(lambda: f.read(8192), b""):
                h.update(block)
        expected = f"sha256:{h.hexdigest()}"

        with patch("openrecall.client.audio_recorder.settings") as mock_settings:
            mock_settings.audio_chunk_duration = 60
            mock_settings.audio_sample_rate = 16000
            mock_settings.audio_channels = 1
            mock_settings.audio_format = "wav"
            from openrecall.client.audio_recorder import AudioRecorder

            rec = AudioRecorder(buffer=mock_buffer)
            rec._on_chunk_complete(wav_path, "mic", actual_duration=0.5)

        metadata = mock_buffer.enqueue_file.call_args[0][1]
        assert metadata["checksum"] == expected

    def test_on_chunk_complete_skips_empty_wav(self, tmp_path):
        """WAV with header only (<=44 bytes) should be skipped."""
        wav_path = tmp_path / "empty.wav"
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
        # File should be exactly 44 bytes (header only)

        mock_buffer = MagicMock()

        with patch("openrecall.client.audio_recorder.settings") as mock_settings:
            mock_settings.audio_chunk_duration = 60
            from openrecall.client.audio_recorder import AudioRecorder

            rec = AudioRecorder(buffer=mock_buffer)
            rec._on_chunk_complete(wav_path, "mic", actual_duration=0.0)

        mock_buffer.enqueue_file.assert_not_called()

    def test_on_chunk_complete_nonexistent_file(self, tmp_path):
        """Non-existent file should be handled gracefully."""
        mock_buffer = MagicMock()
        from openrecall.client.audio_recorder import AudioRecorder

        rec = AudioRecorder(buffer=mock_buffer)
        rec._on_chunk_complete(tmp_path / "nonexistent.wav", "mic", actual_duration=0.0)

        mock_buffer.enqueue_file.assert_not_called()
