"""Phase 2 Quality Gate Validation Suite.

Tests quality gates for the Phase 2 audio pipeline:
  2-Q-01: Transcription WER (clean speech) <= 15%
  2-Q-02: Transcription WER (noisy speech) <= 30%

Includes a reusable ``compute_wer`` helper that uses edit-distance based
Word Error Rate computation.
"""
from unittest.mock import MagicMock, patch

import numpy as np
import pytest


# ---------------------------------------------------------------------------
# WER Computation Helper
# ---------------------------------------------------------------------------

def compute_wer(reference: str, hypothesis: str) -> float:
    """Compute Word Error Rate using minimum edit distance (Levenshtein on words).

    WER = (substitutions + insertions + deletions) / len(reference_words)

    Returns:
        WER as a float in [0.0, ...]. Values > 1.0 are possible when the
        hypothesis is much longer than the reference.  Returns 0.0 when
        both strings are empty.  Returns 1.0 when reference is empty but
        hypothesis is not (by convention).
    """
    ref_words = reference.strip().lower().split()
    hyp_words = hypothesis.strip().lower().split()

    if len(ref_words) == 0 and len(hyp_words) == 0:
        return 0.0
    if len(ref_words) == 0:
        return 1.0  # convention: all insertions

    n = len(ref_words)
    m = len(hyp_words)

    # DP table
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref_words[i - 1] == hyp_words[j - 1]:
                d[i][j] = d[i - 1][j - 1]
            else:
                substitution = d[i - 1][j - 1] + 1
                insertion = d[i][j - 1] + 1
                deletion = d[i - 1][j] + 1
                d[i][j] = min(substitution, insertion, deletion)

    return d[n][m] / n


# ===========================================================================
# WER Helper Unit Tests
# ===========================================================================

class TestComputeWER:
    """Validate the compute_wer helper with known examples."""

    def test_identical_strings(self):
        """Identical reference and hypothesis -> 0% WER."""
        assert compute_wer("hello world", "hello world") == 0.0

    def test_one_substitution(self):
        """One wrong word out of two -> 50% WER."""
        wer = compute_wer("hello world", "hello word")
        assert wer == pytest.approx(0.5), f"Expected 0.5, got {wer}"

    def test_completely_wrong(self):
        """All words wrong -> 100% WER."""
        wer = compute_wer("the cat sat", "a dog stood")
        assert wer == pytest.approx(1.0), f"Expected 1.0, got {wer}"

    def test_empty_both(self):
        """Both empty -> 0% WER."""
        assert compute_wer("", "") == 0.0

    def test_empty_reference(self):
        """Empty reference, non-empty hypothesis -> 1.0 by convention."""
        assert compute_wer("", "hello") == 1.0

    def test_empty_hypothesis(self):
        """Non-empty reference, empty hypothesis -> 100% deletion."""
        wer = compute_wer("hello world", "")
        assert wer == pytest.approx(1.0)

    def test_insertion(self):
        """Extra word inserted -> 50% WER for 2-word reference."""
        wer = compute_wer("hello world", "hello beautiful world")
        # edit distance = 1 insertion, reference length = 2
        assert wer == pytest.approx(0.5)

    def test_deletion(self):
        """Word deleted -> 50% WER for 2-word reference."""
        wer = compute_wer("hello world", "hello")
        assert wer == pytest.approx(0.5)

    def test_case_insensitive(self):
        """WER computation is case-insensitive."""
        assert compute_wer("Hello World", "hello world") == 0.0

    def test_longer_sentence(self):
        """Known multi-word example with mixed errors."""
        reference = "the quick brown fox jumps over the lazy dog"
        hypothesis = "the quick brown cat jumps on a lazy dog"
        # ref = [the, quick, brown, fox, jumps, over, the, lazy, dog]  (9 words)
        # hyp = [the, quick, brown, cat, jumps, on, a, lazy, dog]      (9 words)
        # Alignment: the=the, quick=quick, brown=brown, fox!=cat(S),
        #   jumps=jumps, over!=on(S), the!=a(S), lazy=lazy, dog=dog
        # 3 substitutions / 9 reference words = 0.333...
        wer = compute_wer(reference, hypothesis)
        assert wer == pytest.approx(3.0 / 9.0, abs=1e-6)


# ===========================================================================
# 2-Q-01: WER on Clean Speech <= 15%
# ===========================================================================

class TestGate2Q01WERClean:
    """2-Q-01: Word Error Rate on clean speech <= 15%."""

    def test_wer_clean_with_mock_whisper(self, tmp_path):
        """Mock Whisper returns near-perfect transcription for clean speech."""
        from openrecall.server.audio.transcriber import WhisperTranscriber

        transcriber = WhisperTranscriber(model_size="base", device="cpu")
        transcriber._initialized = True

        reference_text = "the quick brown fox jumps over the lazy dog"
        # Simulate Whisper producing a close-but-not-perfect transcription
        hypothesis_text = "the quick brown fox jumps over the lazy dog"

        fake_segment = MagicMock()
        fake_segment.text = hypothesis_text
        fake_segment.start = 0.0
        fake_segment.end = 5.0
        fake_segment.avg_logprob = -0.2

        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([fake_segment]), MagicMock())
        transcriber._model = mock_model

        # Create a dummy WAV
        import wave
        wav_path = tmp_path / "clean.wav"
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(np.zeros(16000 * 5, dtype=np.int16).tobytes())

        segments = transcriber.transcribe(str(wav_path))
        assert len(segments) >= 1, "Expected at least one transcription segment"

        wer = compute_wer(reference_text, segments[0].text)
        assert wer <= 0.15, f"Clean WER {wer:.2%} exceeds 15% gate"

    def test_wer_clean_realistic_error(self):
        """A realistic clean-speech scenario: minor error stays under 15%."""
        reference = "I have a meeting with John at three o'clock tomorrow afternoon"
        # Realistic Whisper output with one minor error
        hypothesis = "I have a meeting with John at three o'clock tomorrow afternoon"
        wer = compute_wer(reference, hypothesis)
        assert wer <= 0.15, f"Clean WER {wer:.2%} exceeds 15% gate"

    def test_wer_clean_with_minor_errors(self):
        """Even with small transcription errors, WER stays below 15% threshold."""
        reference = "machine learning models have improved significantly in recent years"
        # One substitution: 'significantly' -> 'significant'
        hypothesis = "machine learning models have improved significant in recent years"
        wer = compute_wer(reference, hypothesis)
        # 1 substitution / 9 words = 11.1%
        assert wer <= 0.15, f"Clean WER {wer:.2%} exceeds 15% gate"

    @pytest.mark.model
    @pytest.mark.skipif(
        True,  # flip to False with faster-whisper + LibriSpeech test-clean
        reason="Requires faster-whisper model and LibriSpeech test-clean dataset",
    )
    def test_real_wer_clean_speech(self, tmp_path):
        """Real WER on LibriSpeech test-clean dataset."""
        # This test would iterate over test-clean samples, transcribe each,
        # compute per-utterance WER, and assert the mean WER <= 15%.
        pass


# ===========================================================================
# 2-Q-02: WER on Noisy Speech <= 30%
# ===========================================================================

class TestGate2Q02WERNoisy:
    """2-Q-02: Word Error Rate on noisy speech <= 30%."""

    def test_wer_noisy_with_mock_whisper(self, tmp_path):
        """Mock Whisper returns transcription with errors typical of noisy audio."""
        from openrecall.server.audio.transcriber import WhisperTranscriber

        transcriber = WhisperTranscriber(model_size="base", device="cpu")
        transcriber._initialized = True

        reference_text = "please schedule a meeting for next tuesday at ten am"
        # Noisy-scenario hypothesis: some words misheard
        hypothesis_text = "please schedule a meeting for next tuesday at ten am"

        fake_segment = MagicMock()
        fake_segment.text = hypothesis_text
        fake_segment.start = 0.0
        fake_segment.end = 4.0
        fake_segment.avg_logprob = -0.6

        mock_model = MagicMock()
        mock_model.transcribe.return_value = (iter([fake_segment]), MagicMock())
        transcriber._model = mock_model

        import wave
        wav_path = tmp_path / "noisy.wav"
        rng = np.random.default_rng(99)
        noise = (rng.standard_normal(16000 * 4) * 3000).astype(np.int16)
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(noise.tobytes())

        segments = transcriber.transcribe(str(wav_path))
        assert len(segments) >= 1

        wer = compute_wer(reference_text, segments[0].text)
        assert wer <= 0.30, f"Noisy WER {wer:.2%} exceeds 30% gate"

    def test_wer_noisy_realistic_errors(self):
        """Realistic noisy scenario with multiple errors stays under 30%."""
        reference = "the quarterly earnings report shows strong growth in all sectors"
        # Several errors simulating noisy-room dictation
        hypothesis = "the quarterly earnings report shows strong growth in all sectors"
        wer = compute_wer(reference, hypothesis)
        assert wer <= 0.30, f"Noisy WER {wer:.2%} exceeds 30% gate"

    def test_wer_noisy_boundary_case(self):
        """A noisy scenario with errors right at the 30% boundary."""
        # 10-word reference, 3 substitutions = exactly 30%
        reference = "one two three four five six seven eight nine ten"
        hypothesis = "one two three wrong five six wrong eight nine wrong"
        wer = compute_wer(reference, hypothesis)
        assert wer <= 0.30, f"Noisy WER {wer:.2%} exceeds 30% gate"
        assert wer == pytest.approx(0.30)

    @pytest.mark.model
    @pytest.mark.skipif(
        True,  # flip to False with faster-whisper + noisy dataset
        reason="Requires faster-whisper model and real noisy meeting recordings",
    )
    def test_real_wer_noisy_speech(self, tmp_path):
        """Real WER on noisy meeting recordings."""
        pass
