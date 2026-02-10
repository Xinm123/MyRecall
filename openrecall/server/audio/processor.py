"""Audio chunk processing pipeline: VAD -> Whisper transcription -> DB insert."""

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from openrecall.server.database import SQLStore
from openrecall.shared.config import settings

logger = logging.getLogger(__name__)


@dataclass
class AudioProcessingResult:
    """Result of processing a single audio chunk."""

    audio_chunk_id: int
    transcriptions_count: int = 0
    elapsed_seconds: float = 0.0
    speech_ratio: float = 0.0
    segments_count: int = 0
    filtered_by_ratio: bool = False
    vad_backend: str = "unknown"
    error: Optional[str] = None


class AudioChunkProcessor:
    """Processes an audio chunk through the VAD -> Whisper pipeline.

    Pipeline per chunk:
    1. Load WAV audio
    2. VAD -> get speech segments
    3. For each speech segment: Whisper transcribe
    4. Insert transcriptions into DB + FTS index
    """

    def __init__(
        self,
        vad=None,
        transcriber=None,
        sql_store: Optional[SQLStore] = None,
    ):
        self.sql_store = sql_store or SQLStore()
        self._vad = vad
        self._transcriber = transcriber
        self._vad_initialized = vad is not None
        self._transcriber_initialized = transcriber is not None

    def _get_vad(self):
        """Lazy initialize VAD."""
        if not self._vad_initialized:
            try:
                from openrecall.server.audio.vad import VoiceActivityDetector

                self._vad = VoiceActivityDetector()
            except Exception as e:
                logger.error(f"Failed to initialize VAD: {e}")
            self._vad_initialized = True
        return self._vad

    def _get_transcriber(self):
        """Lazy initialize transcriber."""
        if not self._transcriber_initialized:
            try:
                from openrecall.server.audio.transcriber import WhisperTranscriber

                self._transcriber = WhisperTranscriber()
            except Exception as e:
                logger.error(f"Failed to initialize Whisper transcriber: {e}")
            self._transcriber_initialized = True
        return self._transcriber

    def process_chunk(
        self,
        chunk_id: int,
        chunk_path: str,
        chunk_timestamp: float,
    ) -> AudioProcessingResult:
        """Process a single audio chunk.

        Args:
            chunk_id: Database ID of the audio chunk.
            chunk_path: Path to the WAV file.
            chunk_timestamp: Unix timestamp of the chunk's start.

        Returns:
            AudioProcessingResult with counts and timing.
        """
        result = AudioProcessingResult(audio_chunk_id=chunk_id)
        t0 = time.perf_counter()
        device_name = "unknown"

        try:
            chunk_path_obj = Path(chunk_path)
            if not chunk_path_obj.exists():
                result.error = f"Audio file not found: {chunk_path}"
                return result

            # Get chunk metadata for device_name
            chunk_meta = self.sql_store.get_audio_chunk_by_id(chunk_id) or {}
            device_name = chunk_meta.get("device_name", "")

            # Step 1: VAD - detect speech segments
            vad = self._get_vad()
            if vad is None:
                result.error = "VAD not available"
                return result

            if hasattr(vad, "analyze_chunk"):
                analysis = vad.analyze_chunk(chunk_path)
                speech_segments = analysis.segments
                result.speech_ratio = float(analysis.speech_ratio)
                result.segments_count = len(speech_segments)
                result.vad_backend = analysis.backend_used or "unknown"
            else:
                speech_segments = vad.get_speech_segments(chunk_path)
                result.speech_ratio = 0.0 if not speech_segments else 1.0
                result.segments_count = len(speech_segments)
                result.vad_backend = "unknown"

            result.filtered_by_ratio = (
                result.speech_ratio < settings.audio_vad_min_speech_ratio
            )
            logger.info(
                "🎧 [AUDIO-SERVER] VAD analysis | chunk_id=%d | backend=%s | speech_ratio=%.4f | filtered=%s | segments=%d",
                chunk_id,
                result.vad_backend,
                result.speech_ratio,
                result.filtered_by_ratio,
                result.segments_count,
            )

            if result.filtered_by_ratio:
                result.elapsed_seconds = time.perf_counter() - t0
                return result

            if not speech_segments:
                logger.info(
                    "🎧 [AUDIO-SERVER] No speech detected | chunk_id=%d", chunk_id
                )
                result.elapsed_seconds = time.perf_counter() - t0
                return result

            logger.info(
                "🎧 [AUDIO-SERVER] VAD detected %d speech segment(s) | chunk_id=%d",
                len(speech_segments),
                chunk_id,
            )

            # Step 2: Transcribe each speech segment
            transcriber = self._get_transcriber()
            if transcriber is None:
                result.error = "Whisper transcriber not available"
                return result

            from openrecall.server.audio.wav_utils import load_wav_16k, extract_segment

            audio_data = load_wav_16k(chunk_path)

            offset_index = 0
            for seg in speech_segments:
                try:
                    # Extract the speech segment audio
                    segment_audio = extract_segment(
                        audio_data, seg.start_time, seg.end_time
                    )
                    if len(segment_audio) < 1600:  # Less than 0.1s at 16kHz
                        continue

                    # Transcribe the segment
                    transcription_segments = transcriber.transcribe(segment_audio)

                    for ts in transcription_segments:
                        if not ts.text.strip():
                            continue

                        # Calculate absolute timestamps
                        abs_start = chunk_timestamp + seg.start_time + ts.start_time
                        abs_end = chunk_timestamp + seg.start_time + ts.end_time
                        abs_timestamp = abs_start

                        # Insert transcription + FTS atomically via SQLStore
                        trans_id = self.sql_store.insert_audio_transcription_with_fts(
                            audio_chunk_id=chunk_id,
                            offset_index=offset_index,
                            timestamp=abs_timestamp,
                            transcription=ts.text.strip(),
                            transcription_engine=transcriber.engine_name,
                            speaker_id=None,
                            start_time=abs_start,
                            end_time=abs_end,
                            device=device_name,
                        )
                        if trans_id:
                            result.transcriptions_count += 1
                            offset_index += 1

                except Exception as e:
                    logger.error(
                        f"Failed to process speech segment "
                        f"[{seg.start_time:.1f}-{seg.end_time:.1f}] "
                        f"in chunk {chunk_id}: {e}"
                    )
                    continue

        except Exception as e:
            result.error = str(e)
            logger.exception(f"Audio chunk processing failed for chunk {chunk_id}")

        result.elapsed_seconds = time.perf_counter() - t0
        logger.info(
            "🎧 [AUDIO-SERVER] ✅ Chunk processed | id=%d | transcriptions=%d | elapsed=%.1fs | device=%s",
            chunk_id,
            result.transcriptions_count,
            result.elapsed_seconds,
            device_name,
        )
        return result
