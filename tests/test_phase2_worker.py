"""Phase 2 tests: AudioProcessingWorker lifecycle."""

import sqlite3
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestAudioProcessingResult:
    """Tests for AudioProcessingResult dataclass."""

    def test_defaults(self):
        from openrecall.server.audio.processor import AudioProcessingResult

        r = AudioProcessingResult(audio_chunk_id=1)
        assert r.audio_chunk_id == 1
        assert r.transcriptions_count == 0
        assert r.elapsed_seconds == 0.0
        assert r.speech_ratio == 0.0
        assert r.segments_count == 0
        assert r.filtered_by_ratio is False
        assert r.vad_backend == "unknown"
        assert r.error is None

    def test_with_error(self):
        from openrecall.server.audio.processor import AudioProcessingResult

        r = AudioProcessingResult(audio_chunk_id=2, error="failed")
        assert r.error == "failed"


class TestAudioChunkProcessor:
    """Tests for AudioChunkProcessor."""

    def test_init_lazy(self):
        from openrecall.server.audio.processor import AudioChunkProcessor

        proc = AudioChunkProcessor(sql_store=MagicMock())
        assert proc._vad is None
        assert proc._transcriber is None

    def test_process_missing_file(self, tmp_path):
        from openrecall.server.audio.processor import AudioChunkProcessor

        mock_store = MagicMock()
        proc = AudioChunkProcessor(sql_store=mock_store)

        result = proc.process_chunk(1, str(tmp_path / "nonexistent.wav"), 1700000000.0)
        assert result.error is not None
        assert "not found" in result.error

    def test_process_no_speech(self, tmp_path):
        """When VAD finds no speech, result should have 0 transcriptions."""
        from openrecall.server.audio.processor import AudioChunkProcessor
        from openrecall.server.audio.vad import VadAnalysisResult

        # Create a minimal wav
        import wave
        import numpy as np

        wav_path = tmp_path / "silence.wav"
        audio = np.zeros(16000, dtype=np.int16)
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(audio.tobytes())

        mock_vad = MagicMock()
        mock_vad.analyze_chunk.return_value = VadAnalysisResult(
            segments=[],
            speech_duration_seconds=0.0,
            total_duration_seconds=1.0,
            speech_ratio=0.0,
            backend_used="silero",
        )

        mock_store = MagicMock()
        mock_store.get_audio_chunk_by_id.return_value = {"device_name": "mic"}

        proc = AudioChunkProcessor(vad=mock_vad, sql_store=mock_store)
        result = proc.process_chunk(1, str(wav_path), 1700000000.0)

        assert result.transcriptions_count == 0
        assert result.filtered_by_ratio is True
        assert result.vad_backend == "silero"
        assert result.error is None

    def test_process_filtered_by_ratio_skips_transcriber(self, tmp_path):
        """speech_ratio below threshold should bypass Whisper transcription."""
        from openrecall.server.audio.processor import AudioChunkProcessor
        from openrecall.server.audio.vad import SpeechSegment, VadAnalysisResult

        import numpy as np
        import wave

        wav_path = tmp_path / "low_ratio.wav"
        audio = np.zeros(16000, dtype=np.int16)
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(audio.tobytes())

        mock_vad = MagicMock()
        mock_vad.analyze_chunk.return_value = VadAnalysisResult(
            segments=[SpeechSegment(start_time=0.0, end_time=0.02)],
            speech_duration_seconds=0.02,
            total_duration_seconds=1.0,
            speech_ratio=0.02,
            backend_used="webrtcvad",
        )

        mock_transcriber = MagicMock()
        mock_store = MagicMock()
        mock_store.get_audio_chunk_by_id.return_value = {"device_name": "mic"}

        with patch("openrecall.server.audio.processor.settings") as mock_settings:
            mock_settings.audio_vad_min_speech_ratio = 0.05
            proc = AudioChunkProcessor(
                vad=mock_vad,
                transcriber=mock_transcriber,
                sql_store=mock_store,
            )
            result = proc.process_chunk(1, str(wav_path), 1700000000.0)

        assert result.filtered_by_ratio is True
        assert result.transcriptions_count == 0
        assert result.vad_backend == "webrtcvad"
        mock_transcriber.transcribe.assert_not_called()

    def test_process_with_speech(self, tmp_path):
        """Full pipeline with mocked VAD and Whisper."""
        from openrecall.server.audio.processor import AudioChunkProcessor
        from openrecall.server.audio.vad import SpeechSegment, VadAnalysisResult
        from openrecall.server.audio.transcriber import TranscriptionSegment

        # Create a wav file
        import wave
        import numpy as np

        wav_path = tmp_path / "speech.wav"
        audio = np.random.randint(-1000, 1000, 32000, dtype=np.int16)
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(16000)
            wf.writeframes(audio.tobytes())

        mock_vad = MagicMock()
        mock_vad.analyze_chunk.return_value = VadAnalysisResult(
            segments=[SpeechSegment(start_time=0.0, end_time=1.0)],
            speech_duration_seconds=1.0,
            total_duration_seconds=2.0,
            speech_ratio=0.5,
            backend_used="silero",
        )

        mock_transcriber = MagicMock()
        mock_transcriber.transcribe.return_value = [
            TranscriptionSegment(text="Hello world", start_time=0.0, end_time=1.0, confidence=0.9),
        ]
        mock_transcriber.engine_name = "faster-whisper:base"

        mock_store = MagicMock()
        mock_store.get_audio_chunk_by_id.return_value = {"device_name": "mic"}
        mock_store.insert_audio_transcription_with_fts.return_value = 1

        with patch("openrecall.server.audio.processor.settings") as mock_settings:
            mock_settings.audio_vad_min_speech_ratio = 0.05
            proc = AudioChunkProcessor(
                vad=mock_vad,
                transcriber=mock_transcriber,
                sql_store=mock_store,
            )
            result = proc.process_chunk(1, str(wav_path), 1700000000.0)

        assert result.transcriptions_count == 1
        assert result.filtered_by_ratio is False
        assert result.speech_ratio == 0.5
        assert result.segments_count == 1
        assert result.vad_backend == "silero"
        assert result.error is None
        mock_store.insert_audio_transcription_with_fts.assert_called_once()


class TestAudioProcessingWorker:
    """Tests for AudioProcessingWorker."""

    def test_init(self):
        from openrecall.server.audio.worker import AudioProcessingWorker

        worker = AudioProcessingWorker()
        assert worker.daemon is True
        assert worker.name == "AudioProcessingWorker"

    def test_stop_event(self):
        from openrecall.server.audio.worker import AudioProcessingWorker

        worker = AudioProcessingWorker()
        assert not worker._stop_event.is_set()
        worker.stop()
        assert worker._stop_event.is_set()


class TestSQLStoreAudioLifecycle:
    """Tests for SQLStore audio chunk state machine."""

    @pytest.fixture
    def sql_store(self, flask_app):
        from openrecall.server.database import SQLStore
        return SQLStore()

    def test_insert_audio_chunk(self, sql_store):
        chunk_id = sql_store.insert_audio_chunk(
            file_path="/tmp/test.wav",
            timestamp=1700000000.0,
            device_name="mic",
            checksum="sha256:test",
        )
        assert chunk_id is not None
        assert isinstance(chunk_id, int)

    def test_get_audio_chunk_by_id(self, sql_store):
        chunk_id = sql_store.insert_audio_chunk(
            file_path="/tmp/test2.wav",
            timestamp=1700000001.0,
            device_name="mic",
        )
        chunk = sql_store.get_audio_chunk_by_id(chunk_id)
        assert chunk is not None
        assert chunk["file_path"] == "/tmp/test2.wav"
        assert chunk["device_name"] == "mic"
        assert chunk["status"] == "PENDING"

    def test_pending_processing_completed_lifecycle(self, sql_store):
        from openrecall.shared.config import settings

        chunk_id = sql_store.insert_audio_chunk(
            file_path="/tmp/lifecycle.wav",
            timestamp=1700000002.0,
        )

        conn = sqlite3.connect(str(settings.db_path))
        try:
            # PENDING -> PROCESSING
            ok = sql_store.mark_audio_chunk_processing(conn, chunk_id)
            assert ok is True

            # PROCESSING -> COMPLETED
            ok = sql_store.mark_audio_chunk_completed(conn, chunk_id)
            assert ok is True

            chunk = sql_store.get_audio_chunk_by_id(chunk_id)
            assert chunk["status"] == "COMPLETED"
        finally:
            conn.close()

    def test_pending_processing_failed_lifecycle(self, sql_store):
        from openrecall.shared.config import settings

        chunk_id = sql_store.insert_audio_chunk(
            file_path="/tmp/failed.wav",
            timestamp=1700000003.0,
        )

        conn = sqlite3.connect(str(settings.db_path))
        try:
            sql_store.mark_audio_chunk_processing(conn, chunk_id)
            ok = sql_store.mark_audio_chunk_failed(conn, chunk_id)
            assert ok is True

            chunk = sql_store.get_audio_chunk_by_id(chunk_id)
            assert chunk["status"] == "FAILED"
        finally:
            conn.close()

    def test_reset_stuck_audio_chunks(self, sql_store):
        from openrecall.shared.config import settings

        chunk_id = sql_store.insert_audio_chunk(
            file_path="/tmp/stuck.wav",
            timestamp=1700000004.0,
        )

        conn = sqlite3.connect(str(settings.db_path))
        try:
            sql_store.mark_audio_chunk_processing(conn, chunk_id)
            count = sql_store.reset_stuck_audio_chunks(conn)
            assert count >= 1

            chunk = sql_store.get_audio_chunk_by_id(chunk_id)
            assert chunk["status"] == "PENDING"
        finally:
            conn.close()

    def test_get_next_pending_audio_chunk(self, sql_store):
        from openrecall.shared.config import settings

        sql_store.insert_audio_chunk(
            file_path="/tmp/pending1.wav",
            timestamp=1700000005.0,
        )

        conn = sqlite3.connect(str(settings.db_path))
        try:
            chunk = sql_store.get_next_pending_audio_chunk(conn)
            assert chunk is not None
            assert chunk["status"] == "PENDING"
        finally:
            conn.close()

    def test_audio_chunk_status_counts(self, sql_store):
        sql_store.insert_audio_chunk(file_path="/tmp/c1.wav", timestamp=1.0)
        sql_store.insert_audio_chunk(file_path="/tmp/c2.wav", timestamp=2.0)

        counts = sql_store.get_audio_chunk_status_counts()
        assert counts.get("PENDING", 0) >= 2
