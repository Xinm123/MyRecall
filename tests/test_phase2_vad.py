"""Phase 2 tests: Voice Activity Detector."""

import wave
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np


def _create_wav_file(path: Path, audio_data: np.ndarray, sr: int = 16000) -> Path:
    """Write float32 audio as 16-bit WAV."""
    audio_int16 = np.clip(audio_data * 32768.0, -32768, 32767).astype(np.int16)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(audio_int16.tobytes())
    return path


class TestSpeechSegment:
    """Tests for SpeechSegment dataclass."""

    def test_fields(self):
        from openrecall.server.audio.vad import SpeechSegment

        seg = SpeechSegment(start_time=1.0, end_time=2.5)
        assert seg.start_time == 1.0
        assert seg.end_time == 2.5


class TestVadAnalysisResult:
    """Tests for VadAnalysisResult dataclass."""

    def test_fields(self):
        from openrecall.server.audio.vad import SpeechSegment, VadAnalysisResult

        result = VadAnalysisResult(
            segments=[SpeechSegment(0.0, 1.0)],
            speech_duration_seconds=1.0,
            total_duration_seconds=2.0,
            speech_ratio=0.5,
            backend_used="silero",
        )
        assert len(result.segments) == 1
        assert result.speech_duration_seconds == 1.0
        assert result.total_duration_seconds == 2.0
        assert result.speech_ratio == 0.5
        assert result.backend_used == "silero"


class TestVoiceActivityDetector:
    """Tests for VoiceActivityDetector."""

    def test_init_defaults(self):
        with patch("openrecall.shared.config.settings") as mock_settings:
            mock_settings.audio_vad_threshold = 0.5
            mock_settings.audio_vad_backend = "silero"
            mock_settings.audio_vad_smoothing_window_frames = 10
            mock_settings.audio_vad_hysteresis_on_frames = 3
            mock_settings.audio_vad_hysteresis_off_frames = 5
            from openrecall.server.audio.vad import VoiceActivityDetector

            vad = VoiceActivityDetector()
            assert vad.threshold == 0.5
            assert vad.backend == "silero"
            assert vad.smoothing_window_frames == 10
            assert vad.hysteresis_on_frames == 3
            assert vad.hysteresis_off_frames == 5
            assert vad._initialized is False

    def test_init_custom(self):
        from openrecall.server.audio.vad import VoiceActivityDetector

        vad = VoiceActivityDetector(threshold=0.7, backend="webrtcvad")
        assert vad.threshold == 0.7
        assert vad.backend == "webrtcvad"

    def test_silero_init_failure_falls_back_to_webrtc(self):
        from openrecall.server.audio.vad import VoiceActivityDetector

        vad = VoiceActivityDetector(backend="silero")

        def _set_webrtc_backend():
            vad._model = MagicMock()
            vad._backend_used = "webrtcvad"
            vad._initialized = True

        with patch.object(
            vad,
            "_init_silero_onnx",
            side_effect=RuntimeError("init failed"),
        ), patch.object(vad, "_init_webrtcvad", side_effect=_set_webrtc_backend):
            vad._init_model()

        assert vad._initialized is True
        assert vad._backend_used == "webrtcvad"
        assert vad._model is not None

    def test_no_model_returns_empty(self, tmp_path):
        """When no VAD model is available, return empty segments."""
        from openrecall.server.audio.vad import VoiceActivityDetector

        vad = VoiceActivityDetector(backend="nonexistent")
        vad._initialized = True
        vad._model = None

        silence = np.zeros(16000, dtype=np.float32)
        wav_path = _create_wav_file(tmp_path / "silence.wav", silence)

        segments = vad.get_speech_segments(wav_path)
        assert segments == []

    def test_has_speech_delegates_to_get_segments(self):
        from openrecall.server.audio.vad import SpeechSegment, VoiceActivityDetector

        vad = VoiceActivityDetector()
        vad.get_speech_segments = MagicMock(return_value=[SpeechSegment(0.0, 1.0)])
        assert vad.has_speech("/fake/path.wav") is True

        vad.get_speech_segments = MagicMock(return_value=[])
        assert vad.has_speech("/fake/path.wav") is False

    @patch("openrecall.server.audio.wav_utils.load_wav_16k")
    def test_analyze_chunk_reports_ratio_and_backend(self, mock_load):
        """analyze_chunk should expose ratio metrics and backend used."""
        from openrecall.server.audio.vad import VoiceActivityDetector

        # 1 second audio -> 50 frames at 20ms
        mock_load.return_value = np.zeros(16000, dtype=np.float32)
        frame_scores = ([0.9] * 10) + ([0.1] * 40)

        vad = VoiceActivityDetector(backend="silero")
        vad._initialized = True
        vad._model = MagicMock()
        vad._backend_used = "silero"

        with patch.object(vad, "_compute_frame_scores", return_value=frame_scores):
            analysis = vad.analyze_chunk("/fake.wav")

        assert analysis.backend_used == "silero"
        assert analysis.total_duration_seconds == 1.0
        assert analysis.speech_ratio > 0.0
        assert analysis.speech_duration_seconds > 0.0
        assert len(analysis.segments) >= 1

    def test_hysteresis_reduces_boundary_chatter(self):
        """Smoothing+hysteresis should reduce segment fragmentation."""
        from openrecall.server.audio.vad import VoiceActivityDetector

        # Alternating scores around threshold: noisy boundary pattern.
        scores = [0.8 if i % 2 == 0 else 0.2 for i in range(60)]
        total_duration = len(scores) * 0.02

        jittery = VoiceActivityDetector(backend="webrtcvad")
        jittery.smoothing_window_frames = 1
        jittery.hysteresis_on_frames = 1
        jittery.hysteresis_off_frames = 1

        smooth = VoiceActivityDetector(backend="webrtcvad")
        smooth.smoothing_window_frames = 10
        smooth.hysteresis_on_frames = 3
        smooth.hysteresis_off_frames = 5

        segments_jittery = jittery._scores_to_segments(
            scores,
            frame_duration_seconds=0.02,
            total_duration_seconds=total_duration,
        )
        segments_smooth = smooth._scores_to_segments(
            scores,
            frame_duration_seconds=0.02,
            total_duration_seconds=total_duration,
        )

        assert len(segments_smooth) < len(segments_jittery)

    def test_invalid_wav_returns_empty(self, tmp_path):
        """Invalid WAV file should return empty segments gracefully."""
        from openrecall.server.audio.vad import VoiceActivityDetector

        bad_file = tmp_path / "bad.wav"
        bad_file.write_text("not a wav file")

        vad = VoiceActivityDetector(backend="webrtcvad")
        vad._initialized = True
        vad._model = MagicMock()

        segments = vad.get_speech_segments(bad_file)
        assert segments == []
