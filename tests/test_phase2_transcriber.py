"""Phase 2 tests: WhisperTranscriber."""

import sys
import types
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import numpy as np
import pytest

# Ensure faster_whisper is importable (stub if not installed)
if "faster_whisper" not in sys.modules:
    _fw_stub = types.ModuleType("faster_whisper")
    _fw_stub.WhisperModel = MagicMock()
    sys.modules["faster_whisper"] = _fw_stub


class TestTranscriptionSegment:
    """Tests for TranscriptionSegment dataclass."""

    def test_fields(self):
        from openrecall.server.audio.transcriber import TranscriptionSegment

        seg = TranscriptionSegment(text="hello", start_time=0.0, end_time=1.0, confidence=0.95)
        assert seg.text == "hello"
        assert seg.start_time == 0.0
        assert seg.end_time == 1.0
        assert seg.confidence == 0.95


class TestWhisperTranscriber:
    """Tests for WhisperTranscriber."""

    def test_init_defaults(self):
        with patch("openrecall.shared.config.settings") as mock_settings:
            mock_settings.audio_whisper_model = "base"
            mock_settings.device = "cpu"
            mock_settings.audio_whisper_compute_type = "int8"
            from openrecall.server.audio.transcriber import WhisperTranscriber

            t = WhisperTranscriber()
            assert t.model_size == "base"
            assert t.device == "cpu"
            assert t.compute_type == "int8"
            assert t._initialized is False

    def test_init_custom(self):
        from openrecall.server.audio.transcriber import WhisperTranscriber

        t = WhisperTranscriber(model_size="large", device="cuda", compute_type="float16")
        assert t.model_size == "large"
        assert t.device == "cuda"
        assert t.compute_type == "float16"

    def test_engine_name(self):
        from openrecall.server.audio.transcriber import WhisperTranscriber

        t = WhisperTranscriber(model_size="base", device="cpu", compute_type="int8")
        assert t.engine_name == "faster-whisper:base"

    def test_transcribe_no_model_returns_empty(self):
        from openrecall.server.audio.transcriber import WhisperTranscriber

        t = WhisperTranscriber(model_size="base", device="cpu", compute_type="int8")
        t._initialized = True
        t._model = None

        result = t.transcribe(np.zeros(16000, dtype=np.float32))
        assert result == []

    @patch("faster_whisper.WhisperModel")
    def test_transcribe_returns_segments(self, mock_model_class):
        with patch("openrecall.shared.config.settings") as mock_settings:
            mock_settings.audio_whisper_model = "base"
            mock_settings.device = "cpu"
            mock_settings.audio_whisper_compute_type = "int8"
            mock_settings.audio_whisper_language = "en"
            mock_settings.audio_whisper_beam_size = 5

            from openrecall.server.audio.transcriber import WhisperTranscriber

            # Mock segment
            mock_seg = MagicMock()
            mock_seg.text = " Hello world "
            mock_seg.start = 0.0
            mock_seg.end = 1.5
            mock_seg.avg_logprob = -0.3

            mock_model = MagicMock()
            mock_model.transcribe.return_value = ([mock_seg], MagicMock())
            mock_model_class.return_value = mock_model

            t = WhisperTranscriber()
            t._init_model()
            results = t.transcribe(np.zeros(16000, dtype=np.float32))

            assert len(results) == 1
            assert results[0].text == "Hello world"
            assert results[0].start_time == 0.0
            assert results[0].end_time == 1.5
            assert results[0].confidence == -0.3

    @patch("faster_whisper.WhisperModel")
    def test_transcribe_filters_empty_text(self, mock_model_class):
        with patch("openrecall.shared.config.settings") as mock_settings:
            mock_settings.audio_whisper_model = "base"
            mock_settings.device = "cpu"
            mock_settings.audio_whisper_compute_type = "int8"
            mock_settings.audio_whisper_language = "en"
            mock_settings.audio_whisper_beam_size = 5

            from openrecall.server.audio.transcriber import WhisperTranscriber

            mock_seg1 = MagicMock()
            mock_seg1.text = "  "  # Empty after strip
            mock_seg1.start = 0.0
            mock_seg1.end = 0.5

            mock_seg2 = MagicMock()
            mock_seg2.text = " Valid text "
            mock_seg2.start = 0.5
            mock_seg2.end = 1.0
            mock_seg2.avg_logprob = -0.2

            mock_model = MagicMock()
            mock_model.transcribe.return_value = ([mock_seg1, mock_seg2], MagicMock())
            mock_model_class.return_value = mock_model

            t = WhisperTranscriber()
            t._init_model()
            results = t.transcribe(np.zeros(16000, dtype=np.float32))

            assert len(results) == 1
            assert results[0].text == "Valid text"

    def test_reinit_on_cpu(self):
        from openrecall.server.audio.transcriber import WhisperTranscriber

        t = WhisperTranscriber(model_size="base", device="cuda", compute_type="float16")
        t._initialized = True
        t._model = MagicMock()

        with patch.object(t, "_init_model"):
            t._reinit_on_cpu()

        assert t.device == "cpu"
        assert t.compute_type == "int8"
        assert t._initialized is False
