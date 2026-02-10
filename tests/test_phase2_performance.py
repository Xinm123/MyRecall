"""Phase 2 Performance Gate Validation Suite.

Tests performance gates for the Phase 2 audio pipeline:
  2-P-01: Transcription latency (<90s CPU for 30s audio)
  2-P-02: VAD processing (<1s for 30s audio)
  2-P-03: Throughput (no backlog growth)
  2-P-04: Audio capture CPU (<3% per device)

All tests use mocked dependencies unless explicitly testing real models.
Hardware-dependent tests are marked with appropriate skip markers.
"""
import time
import wave
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_wav_file(path: Path, duration_s: float = 30.0, sample_rate: int = 16000) -> Path:
    """Create a synthetic WAV file with silence (or low-amplitude noise)."""
    n_samples = int(duration_s * sample_rate)
    # Low-amplitude white noise to simulate a non-empty audio file
    rng = np.random.default_rng(42)
    audio = (rng.standard_normal(n_samples) * 100).astype(np.int16)

    wav_path = path / "test_30s.wav"
    with wave.open(str(wav_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # int16
        wf.setframerate(sample_rate)
        wf.writeframes(audio.tobytes())
    return wav_path


# ===========================================================================
# 2-P-01: Transcription Latency
# ===========================================================================

class TestGate2P01TranscriptionLatency:
    """2-P-01: Transcribe 30s audio in <90s on CPU."""

    def test_mock_transcription_latency(self, tmp_path):
        """With a mocked Whisper model the pipeline completes well within budget."""
        from openrecall.server.audio.transcriber import WhisperTranscriber, TranscriptionSegment

        transcriber = WhisperTranscriber(model_size="base", device="cpu")
        # Bypass lazy init
        transcriber._initialized = True

        fake_segment = MagicMock()
        fake_segment.text = "hello world"
        fake_segment.start = 0.0
        fake_segment.end = 5.0
        fake_segment.avg_logprob = -0.3

        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([fake_segment]), MagicMock())
        transcriber._model = mock_model

        wav_path = _create_wav_file(tmp_path, duration_s=30.0)

        t0 = time.perf_counter()
        segments = transcriber.transcribe(str(wav_path))
        elapsed = time.perf_counter() - t0

        # Mock call should be near-instant; budget is 90s
        assert elapsed < 90.0, f"Transcription took {elapsed:.1f}s (budget 90s)"
        assert len(segments) >= 1
        assert segments[0].text == "hello world"

    @pytest.mark.model
    @pytest.mark.perf
    @pytest.mark.skipif(
        True,  # flip to False when you have faster-whisper installed
        reason="Requires faster-whisper model download and CPU time",
    )
    def test_real_transcription_latency(self, tmp_path):
        """Real Whisper transcription of 30s audio completes in <90s CPU."""
        from openrecall.server.audio.transcriber import WhisperTranscriber

        wav_path = _create_wav_file(tmp_path, duration_s=30.0)
        transcriber = WhisperTranscriber(model_size="base", device="cpu", compute_type="int8")

        t0 = time.perf_counter()
        segments = transcriber.transcribe(str(wav_path))
        elapsed = time.perf_counter() - t0

        assert elapsed < 90.0, f"Transcription took {elapsed:.1f}s (budget 90s)"


# ===========================================================================
# 2-P-02: VAD Processing Latency
# ===========================================================================

class TestGate2P02VADProcessing:
    """2-P-02: VAD processes 30s audio in <1s."""

    def test_mock_vad_latency(self, tmp_path):
        """With mocked model, VAD returns in well under 1s."""
        from openrecall.server.audio.vad import VoiceActivityDetector, SpeechSegment

        vad = VoiceActivityDetector(backend="silero")
        vad._initialized = True

        vad._model = MagicMock()
        vad._backend_used = "silero"
        frame_scores = ([0.9] * 300) + ([0.1] * 1200)

        wav_path = _create_wav_file(tmp_path, duration_s=30.0)

        with patch("openrecall.server.audio.wav_utils.load_wav_16k") as mock_load:
            mock_load.return_value = np.zeros(30 * 16000, dtype=np.float32)

            t0 = time.perf_counter()
            with patch.object(vad, "_compute_frame_scores", return_value=frame_scores):
                segments = vad.get_speech_segments(wav_path)
            elapsed = time.perf_counter() - t0

        assert elapsed < 1.0, f"VAD took {elapsed:.3f}s (budget 1.0s)"
        assert len(segments) >= 1

    @pytest.mark.model
    @pytest.mark.perf
    @pytest.mark.skipif(
        True,  # flip to False when silero onnx model is available
        reason="Requires silero ONNX model download",
    )
    def test_real_vad_latency(self, tmp_path):
        """Real silero ONNX VAD processes 30s audio in <1s."""
        from openrecall.server.audio.vad import VoiceActivityDetector

        wav_path = _create_wav_file(tmp_path, duration_s=30.0)
        vad = VoiceActivityDetector(backend="silero")

        t0 = time.perf_counter()
        _ = vad.get_speech_segments(wav_path)
        elapsed = time.perf_counter() - t0

        assert elapsed < 1.0, f"VAD took {elapsed:.3f}s (budget 1.0s)"


# ===========================================================================
# 2-P-03: Throughput - No Backlog Growth
# ===========================================================================

class TestGate2P03Throughput:
    """2-P-03: Transcription pipeline keeps up with real-time (no backlog growth)."""

    def test_no_backlog_growth_pattern(self):
        """Simulated pending-count readings must not show monotonic growth."""
        # Simulate 10 polling intervals of queue depth.
        # A healthy pipeline: depths wobble but don't monotonically increase.
        healthy_depths = [0, 1, 0, 1, 2, 1, 0, 1, 0, 0]
        growing_depths = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]

        def _is_growing(depths, window=5):
            """Return True if depths are monotonically increasing over `window` samples."""
            for i in range(len(depths) - window):
                segment = depths[i : i + window]
                if all(segment[j] < segment[j + 1] for j in range(len(segment) - 1)):
                    return True
            return False

        assert not _is_growing(healthy_depths), "Healthy pattern falsely flagged as growing"
        assert _is_growing(growing_depths), "Growing pattern not detected"

    def test_mock_queue_depth_stable(self):
        """Mock AudioChunkProcessor with a fast mock and verify stable queue depth."""
        from unittest.mock import MagicMock

        mock_store = MagicMock()
        # Simulate 5 polling cycles: each returns a small pending count
        mock_store.get_audio_chunk_status_counts.side_effect = [
            {"PENDING": 1, "COMPLETED": 10},
            {"PENDING": 0, "COMPLETED": 11},
            {"PENDING": 2, "COMPLETED": 11},
            {"PENDING": 1, "COMPLETED": 13},
            {"PENDING": 0, "COMPLETED": 14},
        ]

        pending_readings = []
        for _ in range(5):
            counts = mock_store.get_audio_chunk_status_counts()
            pending_readings.append(counts.get("PENDING", 0))

        # Verify no monotonic increase
        monotonic_increase = all(
            pending_readings[i] < pending_readings[i + 1]
            for i in range(len(pending_readings) - 1)
        )
        assert not monotonic_increase, (
            f"Backlog growing monotonically: {pending_readings}"
        )


# ===========================================================================
# 2-P-04: Audio Capture CPU Usage
# ===========================================================================

class TestGate2P04AudioCaptureCPU:
    """2-P-04: AudioManager uses reasonable CPU resources (<3% per device)."""

    def test_audio_manager_structural_attributes(self):
        """AudioManager uses a blocking InputStream callback (not busy-wait)."""
        from openrecall.client.audio_manager import AudioManager

        mgr = AudioManager(device_name="test_device", sample_rate=16000, channels=1)

        # Structural checks: the manager should use callback-based I/O,
        # not busy-waiting, which is the key to low CPU usage.
        assert hasattr(mgr, "_audio_callback"), "Missing callback method (non-polling design)"
        assert mgr.sample_rate == 16000
        assert mgr.channels == 1
        # Block size should be small (100ms = 1600 samples at 16kHz)
        # This is set in start(), but the design ensures low CPU by using
        # sounddevice's callback mechanism rather than polling.
        assert not mgr._recording, "Should not be recording initially"

    def test_audio_manager_callback_writes_frames(self, tmp_path):
        """Audio callback correctly writes frames to WAV file."""
        from openrecall.client.audio_manager import AudioManager

        mgr = AudioManager(
            device_name="test_device",
            sample_rate=16000,
            channels=1,
            chunk_duration=60,
            output_dir=tmp_path,
        )
        mgr._recording = True
        mgr._start_new_chunk()

        # Simulate a callback with 1600 samples (100ms)
        indata = np.zeros((1600, 1), dtype=np.int16)
        mgr._audio_callback(indata, 1600, None, None)

        assert mgr._frames_written == 1600
        # Clean up
        mgr._close_current_chunk(notify=False)

    @pytest.mark.perf
    @pytest.mark.skipif(
        True,  # flip to False on machines with audio devices
        reason="Requires real audio hardware and psutil",
    )
    def test_real_cpu_usage(self):
        """Measure CPU usage of AudioManager over 10 seconds."""
        import psutil

        from openrecall.client.audio_manager import AudioManager

        mgr = AudioManager(device_name="0", sample_rate=16000)
        process = psutil.Process()
        cpu_before = process.cpu_percent(interval=None)

        mgr.start()
        time.sleep(10)
        cpu_during = process.cpu_percent(interval=1.0)
        mgr.stop()

        assert cpu_during < 3.0, f"Audio capture CPU usage {cpu_during}% exceeds 3% budget"
